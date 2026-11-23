import json
from datetime import datetime,timedelta,timezone
from tests.test_platform_console import platform,headers
from app.models.care import Measurement,CareAssessment,NutritionConfiguration,PlanReview,CareMessage,PatientImportBatch,PlatformIncident
from app.models.patient_link import PatientNutritionistLink
from app.models.ai_nutrition import FoodRecord,NutritionalPlan
from app.models.notification import Notification
from app.models.user import User


def link(db):
    db.add(PatientNutritionistLink(id='link',tenant_id='a',branch_id='a1',patient_id='patient',nutritionist_id='doctor',status='LINKED',pairing_code='CODE'))
    db.commit()


def test_admin_can_message_patient_without_specialist_link(client, db_session, platform):
    # An administrator can contact company patients without taking their link
    # away from the treating nutritionist.
    link(db_session)
    contacts=client.get('/api/v1/care/contacts',headers=headers('admin')).json()
    assert 'patient' in {x['id'] for x in contacts}
    patient_contacts=client.get('/api/v1/care/contacts',headers=headers('patient')).json()
    assert {'admin','doctor'} <= {x['id'] for x in patient_contacts}
    r=client.post('/api/v1/care/conversations/patient',headers=headers('admin'),json={'content':'Consulta administrativa'})
    assert r.status_code==201,r.text
    r=client.post('/api/v1/care/conversations/admin',headers=headers('patient'),json={'content':'Respuesta del paciente'})
    assert r.status_code==201,r.text
    thread=client.get('/api/v1/care/conversations/patient',headers=headers('admin')).json()
    assert len(thread['items'])==2
    assert client.get('/api/v1/care/conversations/patient',headers=headers('other')).status_code==403
    assert db_session.get(PatientNutritionistLink,'link').nutritionist_id=='doctor'


def test_admin_message_scope_follows_selected_branch(client, db_session, platform):
    from app.models.company import Branch
    db_session.add(Branch(id='a2',tenant_id='a',name='Sur',code='SUR'))
    db_session.flush()
    db_session.add(User(id='patient2',tenant_id='a',branch_id='a2',role_id='CLIENTE',
        email='second@example.test',full_name='Second',hashed_password='test'))
    db_session.commit()
    assert 'patient2' not in {x['id'] for x in client.get('/api/v1/care/contacts',headers=headers('admin')).json()}
    assert client.get('/api/v1/care/conversations/patient2',headers=headers('admin')).status_code==403
    selected={**headers('admin'),'X-Workspace-Company':'a','X-Workspace-Branch':'a2'}
    assert 'patient2' in {x['id'] for x in client.get('/api/v1/care/contacts',headers=selected).json()}
    assert client.post('/api/v1/care/conversations/patient2',headers=selected,json={'content':'Hola desde administración'}).status_code==201
    assert client.post('/api/v1/care/conversations/admin',headers=headers('patient2'),json={'content':'Respuesta desde Sur'}).status_code==201


def test_company_admin_is_available_as_appointment_specialist(client, db_session, platform):
    r=client.get('/api/v1/appointments/nutritionists',headers=headers('patient'))
    assert r.status_code==200,r.text
    assert {'admin','doctor'} <= {x['id'] for x in r.json()}
    assert 'other' not in {x['id'] for x in r.json()}
    future=datetime.now(timezone.utc)+timedelta(days=1)
    future=future.replace(hour=14,minute=0,second=0,microsecond=0)
    r=client.post('/api/v1/appointments',headers=headers('patient'),json={
        'nutritionist_id':'admin','scheduled_at':future.isoformat(),'reason':'Consulta con administrador'})
    assert r.status_code==200,r.text
    assert r.json()['nutritionist_id']=='admin'


def test_measurements_history_dates_and_scope(client,db_session,platform):
    link(db_session)
    body={'weight_kg':70,'height_cm':170,'measured_at':(datetime.now(timezone.utc)-timedelta(days=2)).isoformat()}
    for who,weight in [('patient',70),('doctor',69)]:
        r=client.post('/api/v1/care/patients/patient/measurements',headers=headers(who),json={**body,'weight_kg':weight})
        assert r.status_code==201,r.text
    rows=client.get('/api/v1/care/patients/patient/measurements',headers=headers('patient')).json()
    assert len(rows)==2 and rows[0]['bmi']>0
    assert client.get('/api/v1/care/patients/patient/measurements',headers=headers('other')).status_code in (403,404)
    assert client.get('/api/v1/care/patients/patient/measurements',headers=headers()).status_code==403
    assert client.post('/api/v1/care/patients/patient/measurements',headers=headers('patient'),json={**body,'measured_at':(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()}).status_code==422


def test_adherence_daily_cap_missing_days_and_config_snapshot(client,db_session,platform):
    today=datetime.now(timezone(timedelta(hours=-4))).date();first=today-timedelta(days=1)
    db_session.get(User,'patient').created_at=datetime.combine(first-timedelta(days=5),datetime.min.time())
    db_session.add(NutritionalPlan(id='plan',patient_id='patient',nutritionist_id='doctor',tenant_id='a',branch_id='a1',status='APPROVED',approved_at=datetime.combine(first-timedelta(days=1),datetime.min.time()),meals_json='[]',meals_per_day=2))
    for i in range(4):
        db_session.add(FoodRecord(id=f'food{i}',patient_id='patient',tenant_id='a',branch_id='a1',result_json=json.dumps({'consumed_at':first.isoformat()+'T12:00:00-04:00'})))
    db_session.commit()
    request={'start_date':first.isoformat(),'end_date':today.isoformat()}
    r=client.post('/api/v1/care/patients/patient/assessments',headers=headers('patient'),json=request)
    assert r.status_code==201,r.text
    result=r.json()
    assert result['adherence_percent']==50 and result['missing_days']==[today.isoformat()]
    assert result['expected']==4 and result['registered']==4 and result['days'][0]['covered']==2
    cfg={'values':{'meals_per_day':5,'inactivity_days':3,'water_liters':2.5,'sleep_hours':8},'reason':'Ajuste profesional'}
    assert client.put('/api/v1/care/configuration',headers=headers('admin'),json=cfg).status_code==200
    history=client.get('/api/v1/care/patients/patient/assessments',headers=headers('patient')).json()
    assert history[0]['snapshot']['configuration']['version']==0
    assert client.get('/api/v1/care/configuration',headers=headers('other')).json()['version']==0
    assert client.put('/api/v1/care/configuration',headers=headers('patient'),json=cfg).status_code==403
    assert client.post('/api/v1/care/patients/patient/assessments',headers=headers('patient'),json={'start_date':today.isoformat(),'end_date':first.isoformat()}).status_code==422


def test_inactivity_alert_deduplicated(client,db_session,platform):
    patient=db_session.get(User,'patient');patient.created_at=datetime.now()-timedelta(days=20);db_session.commit()
    today=datetime.now(timezone(timedelta(hours=-4))).date().isoformat()
    for _ in range(2):
        r=client.post('/api/v1/care/patients/patient/assessments',headers=headers('patient'),json={'start_date':today,'end_date':today})
        assert r.status_code==201,r.text
        assert r.json()['inactivity']['alert'] is True
    assert db_session.query(Notification).count()==1


def test_review_correction_rejection_and_approval_audit(client,db_session,platform):
    link(db_session)
    for identity in ['draft','reject']:
        db_session.add(NutritionalPlan(id=identity,patient_id='patient',nutritionist_id='doctor',tenant_id='a',branch_id='a1',status='DRAFT',meals_json='[{"meal_name":"Cena","foods":[]}]'))
    db_session.commit()
    path='/api/v1/care/plans/draft/reviews'
    correction={'decision':'CORRECTED','reason':'Ajuste de recomendación','clinical_notes':'Revisar porciones con el paciente.'}
    assert client.post(path,headers=headers('doctor'),json=correction).status_code==200
    assert client.post(path,headers=headers('patient'),json=correction).status_code==403
    assert client.post(path,headers=headers('other'),json=correction).status_code in (403,404)
    r=client.post(path,headers=headers('doctor'),json={'decision':'APPROVED','reason':'Revisión profesional completa'})
    assert r.status_code==200,r.text
    assert db_session.get(NutritionalPlan,'draft').status=='APPROVED'
    history=client.get(path,headers=headers('doctor')).json()
    assert len(history)==2 and history[0]['after']['status']=='APPROVED'
    assert client.post('/api/v1/care/plans/reject/reviews',headers=headers('doctor'),json={'decision':'REJECTED','reason':'Necesita otra propuesta'}).status_code==200
    assert db_session.get(NutritionalPlan,'reject').status=='REJECTED'
    assert client.post(path,headers=headers('doctor'),json=correction).status_code==409


def test_human_conversations_require_active_link(client,db_session,platform):
    link(db_session)
    assert 'doctor' in {x['id'] for x in client.get('/api/v1/care/contacts',headers=headers('patient')).json()}
    path='/api/v1/care/conversations/doctor'
    assert client.post(path,headers=headers('patient'),json={'content':'Hola, necesito consultar mis porciones.'}).status_code==201
    thread=client.get('/api/v1/care/conversations/patient',headers=headers('doctor')).json()
    assert thread['items'][0]['sender_id']=='patient'
    assert db_session.query(Notification).filter_by(user_id='doctor').count()==1
    assert client.get('/api/v1/care/conversations/patient',headers=headers('other')).status_code==403
    assert client.post(path,headers=headers('patient'),json={'content':'   '}).status_code==422
    db_session.get(PatientNutritionistLink,'link').status='CANCELLED';db_session.commit()
    assert client.get(path,headers=headers('patient')).status_code==403


def test_csv_preview_confirm_partial_and_retry(client,db_session,platform):
    csv='full_name,email,password,phone\nNuevo Uno,nuevo1@example.com,Password123!,76543210\nNuevo Uno,nuevo1@example.com,Password123!,76543210\nInvalido,no-es-correo,weak,\nNuevo Dos,nuevo2@example.com,Password123!,\n'
    before=db_session.query(User).count()
    r=client.post('/api/v1/care/patient-imports/preview',headers=headers('admin'),json={'csv_content':csv})
    assert r.status_code==200,r.text
    result=r.json();assert result['accepted']==2 and result['rejected']==2
    assert 'Password123!' not in r.text and 'hashed_password' not in r.text
    assert db_session.query(User).count()==before
    path='/api/v1/care/patient-imports/'+result['batch_id']+'/confirm'
    assert client.post(path,headers=headers('other')).status_code==404
    r=client.post(path,headers=headers('admin'));assert r.status_code==200,r.text
    assert r.json()['created']==2 and r.json()['rejected']==2
    assert client.post(path,headers=headers('admin')).json()==r.json()
    assert db_session.query(User).count()==before+2


def test_platform_periods_and_incidents_are_nonclinical(client,db_session,platform):
    db_session.add(PlatformIncident(id='incident',route='/care/patients/{patient_id}/assessments',method='POST',error_type='ValueError'))
    db_session.commit()
    r=client.get('/api/v1/platform/overview?tenant_id=a',headers=headers())
    assert r.status_code==200 and r.json()['companies']==1 and r.json()['generated_at'].endswith('Z')
    incidents=client.get('/api/v1/platform/incidents',headers=headers()).json()
    assert incidents[0]['error_type']=='ValueError' and 'patient_id' not in incidents[0]
    assert client.get('/api/v1/platform/incidents',headers=headers('admin')).status_code==403
    assert client.put('/api/v1/platform/incidents/incident/resolve',headers=headers(),json={'reason':'Corregida la causa','is_active':False}).status_code==200
    assert db_session.get(PlatformIncident,'incident').status=='RESOLVED'


def test_import_expiration_confirmation_rechecks_and_no_plaintext(client,db_session,platform):
    csv='full_name,email,password\nNueva Persona,nueva@example.com,Password123!\n'
    preview=client.post('/api/v1/care/patient-imports/preview',headers=headers('admin'),json={'csv_content':csv}).json()
    batch=db_session.get(PatientImportBatch,preview['batch_id'])
    assert 'Password123!' not in json.dumps(batch.rows)
    batch.expires_at=datetime.now()-timedelta(seconds=1);db_session.commit()
    assert client.post('/api/v1/care/patient-imports/'+batch.id+'/confirm',headers=headers('admin')).status_code==410
    preview=client.post('/api/v1/care/patient-imports/preview',headers=headers('admin'),json={'csv_content':csv}).json()
    db_session.add(User(id='concurrent',tenant_id='a',branch_id='a1',email='nueva@example.com',full_name='Otra persona',hashed_password='hash',role_id='CLIENTE'))
    db_session.commit()
    r=client.post('/api/v1/care/patient-imports/'+preview['batch_id']+'/confirm',headers=headers('admin'))
    assert r.status_code==200,r.text
    assert r.json()['created']==0 and r.json()['rejected']==1


def test_existing_plan_editor_records_review_history(client,db_session,platform):
    link(db_session)
    db_session.add(NutritionalPlan(id='old-editor',tenant_id='a',branch_id='a1',patient_id='patient',nutritionist_id='doctor',status='DRAFT',meals_json='[{"meal_name":"Cena","foods":[]}]'))
    db_session.commit()
    r=client.put('/api/v1/plans/old-editor',headers=headers('doctor'),json={'clinical_notes':'Corrección profesional'})
    assert r.status_code==200,r.text
    assert client.post('/api/v1/plans/old-editor/approve',headers=headers('doctor')).status_code==200
    history=client.get('/api/v1/care/plans/old-editor/reviews',headers=headers('doctor')).json()
    assert {h['decision'] for h in history}=={'CORRECTED','APPROVED'}


def test_habits_use_company_configuration_and_measurements_not_fabricated(client,db_session,platform):
    assert client.post('/api/v1/clinical/anamnesis/me',headers=headers('patient'),json={}).status_code==200
    assert db_session.query(Measurement).count()==0
    cfg={'values':{'meals_per_day':4,'inactivity_days':7,'water_liters':3,'sleep_hours':9},'reason':'Metas de seguimiento'}
    assert client.put('/api/v1/care/configuration',headers=headers('admin'),json=cfg).status_code==200
    today=datetime.now(timezone(timedelta(hours=-4))).date().isoformat()
    r=client.post('/api/v1/care/patients/patient/assessments',headers=headers('patient'),json={'start_date':today,'end_date':today})
    assert r.status_code==201,r.text
    assert [h['target'] for h in r.json()['habits']]==[3,9]


def test_period_before_account_registration_is_not_nonadherence(client,db_session,platform):
    patient=db_session.get(User,'patient');patient.created_at=datetime.now();db_session.commit()
    yesterday=(datetime.now(timezone(timedelta(hours=-4))).date()-timedelta(days=1)).isoformat()
    r=client.post('/api/v1/care/patients/patient/assessments',headers=headers('patient'),json={'start_date':yesterday,'end_date':yesterday})
    assert r.status_code==201,r.text
    assert r.json()['expected']==0 and r.json()['adherence_percent'] is None and r.json()['missing_days']==[]
