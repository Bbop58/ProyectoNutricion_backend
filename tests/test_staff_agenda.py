from datetime import date,datetime
import pytest
from fastapi import HTTPException
from tests.test_staff_assistant import demo
from tests.test_staff_conversation import ask,find
from app.models.appointment import Appointment
from app.models.notification import Notification
from app.models.user import User
from app.schemas.staff_assistant import AssistantIntent
from app.services import staff_assistant_agenda as agenda,staff_gemini


@pytest.fixture
def scheduled(demo):
    scope=demo.db.info.pop('workspace')
    demo.db.add_all([User(id='nutri-a2',role_id='NUTRICIONISTA',tenant_id='a',branch_id='a2',full_name='Nutri segunda sucursal',email='nutri-a2@example.com',hashed_password='test',is_active=True),
                     User(id='nutri-b',role_id='NUTRICIONISTA',tenant_id='b',branch_id='b1',full_name='Nutri otra empresa',email='nutri-b@example.com',hashed_password='test',is_active=True)])
    demo.db.flush()
    values=[('pending','a','a1','patient','nutritionist','PENDING',datetime(2026,11,24,14)),
            ('admin-pending','a','a1','homonym','admin','PENDING',datetime(2026,11,24,15)),
            ('confirmed','a','a1','patient','nutritionist','CONFIRMED',datetime(2026,11,24,16)),
            ('accepted','a','a1','patient','nutritionist','ACCEPTED',datetime(2026,11,24,17)),
            ('previous','a','a1','patient','nutritionist','PENDING',datetime(2026,11,24,3,59)),
            ('last','a','a1','patient','nutritionist','PENDING',datetime(2026,11,25,3,59)),
            ('next','a','a1','patient','nutritionist','PENDING',datetime(2026,11,25,4)),
            ('other-branch','a','a2','other-branch','nutri-a2','PENDING',datetime(2026,11,24,14)),
            ('foreign','b','b1','other-company','nutri-b','PENDING',datetime(2026,11,24,14))]
    for identity,tenant,branch,patient,nutri,status,when in values:
        demo.db.add(Appointment(id=identity,tenant_id=tenant,branch_id=branch,patient_id=patient,nutritionist_id=nutri,status=status,scheduled_at=when,reason='PRIVATE CLINICAL NOTES'))
    demo.db.commit();demo.db.info['workspace']=scope
    return demo


def test_admin_pending_agenda_is_branch_scoped_and_excludes_accepted_confirmed(scheduled):
    d=scheduled
    facts,_=agenda.read(d.db,d.actor,None,AssistantIntent(action='question',topic='appointments',appointment_status='PENDING'))
    assert facts['total']==5 and len(facts['appointments'])==5
    assert all(r['status']=='pendientes de aceptación' for r in facts['appointments'])
    assert {r['patient'] for r in facts['appointments']}=={'Alex Demo','Alex Segundo'}
    assert 'PRIVATE CLINICAL' not in str(facts) and 'nutritionist_id' not in str(facts)
    assert d.db.query(Notification).count()==0


def test_nutritionist_only_gets_own_appointments(scheduled):
    d=scheduled
    facts,_=agenda.read(d.db,d.users['nutritionist'],None,AssistantIntent(action='question',topic='appointments',appointment_status='PENDING'))
    assert facts['total']==4
    assert all(r['professional']=='Nutricionista' for r in facts['appointments'])


def test_dates_are_inclusive_in_bolivia_and_do_not_include_next_day(scheduled):
    d=scheduled
    facts,_=agenda.read(d.db,d.actor,None,AssistantIntent(action='question',topic='appointments',appointment_status='PENDING',date_from=date(2026,11,24),date_to=date(2026,11,24)))
    assert facts['total']==3
    assert all(r['scheduled_at'].startswith('2026-11-24') for r in facts['appointments'])
    assert any('23:59' in r['scheduled_at'] for r in facts['appointments'])


def test_bad_range_and_foreign_patient_cannot_be_queried(scheduled):
    d=scheduled
    with pytest.raises(HTTPException):agenda.read(d.db,d.actor,None,AssistantIntent(action='question',topic='appointments',date_from=date(2026,12,1),date_to=date(2026,11,1)))
    with pytest.raises(HTTPException):agenda.read(d.db,d.actor,d.users['other-company'],AssistantIntent(action='question',topic='appointments',appointment_scope='patient'))


def test_my_agenda_does_not_accidentally_filter_by_previous_patient(scheduled,monkeypatch):
    d=scheduled
    selected=ask(d,'sí',find(d,monkeypatch))
    monkeypatch.setattr(staff_gemini,'interpret',lambda *args:(AssistantIntent(action='question',topic='appointments',appointment_status='PENDING'),{'engine':'gemini','total_tokens':10}))
    def answer(message,facts,*args,**kwargs):
        assert facts['total']==5 and '_display_lines' not in facts
        assert {r['patient'] for r in facts['appointments']}=={'Alex Demo','Alex Segundo'}
        return 'Encontré cinco citas pendientes en tu sucursal.',{'engine':'gemini','total_tokens':20}
    monkeypatch.setattr(staff_gemini,'answer',answer)
    result=ask(d,'mostrame mis citas pendientes',selected)
    assert 'Alex Segundo' in result['message'] and '24/11/2026' in result['message']
    assert 'PRIVATE CLINICAL' not in result['message']


def test_explicit_patient_scope_filters_only_that_patient(scheduled):
    d=scheduled
    facts,_=agenda.read(d.db,d.actor,d.users['homonym'],AssistantIntent(action='question',topic='appointments',appointment_scope='patient'))
    assert facts['total']==1 and facts['appointments'][0]['patient']=='Alex Segundo'


def test_named_patient_and_dates_survive_ambiguity_in_signed_context(scheduled,monkeypatch):
    d=scheduled
    monkeypatch.setattr(staff_gemini,'interpret',lambda *args:(AssistantIntent(action='question',topic='appointments',appointment_scope='patient',patient_name='Alex',date_from=date(2026,11,24),date_to=date(2026,11,24)),{'engine':'gemini','total_tokens':10}))
    found=ask(d,'Mostrame las citas de Alex del 24 de noviembre de 2026')
    assert found['kind']=='patients' and len(found['patients'])==2
    def answer(message,facts,*args,**kwargs):
        assert facts['date_from']=='2026-11-24' and facts['date_to']=='2026-11-24'
        assert all(r['patient']=='Alex Demo' for r in facts['appointments'])
        return 'Citas de Alex del 24 de noviembre.',{'engine':'gemini','total_tokens':20}
    monkeypatch.setattr(staff_gemini,'answer',answer)
    result=ask(d,'Selecciono el 1',found)
    assert result['answer_source']=='gemini_with_authorized_data'
