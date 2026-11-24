from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace

from fastapi import HTTPException
import httpx
from jose import jwt
import pytest

from app.api.deps import get_current_user
from app.config import settings
from app.core.workspace import Workspace
from app.models.activity_log import ActivityLog
from app.models.clinical import PatientAnamnesis
from app.models.company import Branch
from app.models.patient_link import PatientNutritionistLink
from app.models.notification import Notification
from app.models.rbac import Role
from app.models.recipe import Recipe, RecipeAssignment
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.staff_assistant import AssistantIntent, AssistantQuery
from app.services import staff_assistant_service as service, staff_gemini


@pytest.fixture
def demo(db_session, monkeypatch):
    db = db_session
    for role in ('ADMIN_ORGANIZATION', 'NUTRICIONISTA', 'CLIENTE', 'SUPERADMIN'):
        db.add(Role(id=role, name=role, description='Test', platform='Web'))
    db.add_all([Tenant(id='a', name='A', code='A'), Tenant(id='b', name='B', code='B')])
    db.flush()
    db.add_all([Branch(id=branch, tenant_id=company, name=branch, code=branch)
                for branch, company in [('a1', 'a'), ('a2', 'a'), ('b1', 'b')]])
    db.flush()
    users = {}
    for identity, role, company, branch, name in [
        ('admin', 'ADMIN_ORGANIZATION', 'a', 'a1', 'Admin'),
        ('nutritionist', 'NUTRICIONISTA', 'a', 'a1', 'Nutricionista'),
        ('patient', 'CLIENTE', 'a', 'a1', 'Alex Demo'),
        ('homonym', 'CLIENTE', 'a', 'a1', 'Alex Segundo'),
        ('unlinked', 'CLIENTE', 'a', 'a1', 'Paciente sin vincular'),
        ('other-branch', 'CLIENTE', 'a', 'a2', 'Paciente sucursal dos'),
        ('other-company', 'CLIENTE', 'b', 'b1', 'Paciente privado'),
        ('root', 'SUPERADMIN', None, None, 'Root'),
    ]:
        users[identity] = User(id=identity, role_id=role, tenant_id=company, branch_id=branch,
                               full_name=name, email=identity+'@example.com', hashed_password='test-only', is_active=True)
        db.add(users[identity])
    db.flush()
    db.add(PatientNutritionistLink(id='link', pairing_code='LINKED', tenant_id='a', branch_id='a1',
                                   patient_id='patient', nutritionist_id='nutritionist', status='LINKED'))
    db.add(PatientAnamnesis(id='profile', patient_id='patient', tenant_id='a', branch_id='a1',
                           goal='Pérdida de grasa', allergies='Lactosa', consent_data_processing=True))
    for identity, company, branch, ingredients, category in [
        ('shared', 'a', None, 'Pollo 100 g, arroz 120 g y zanahoria 80 g.', 'Cena'),
        ('milk', 'a', None, 'Yogur natural de leche de vaca.', 'Cena'),
        ('vegetarian', 'a', 'a1', 'Lentejas 160 g, arroz 100 g y zapallo 80 g.', 'Cena'),
        ('breakfast', 'a', None, 'Huevo y papa.', 'Desayuno'),
        ('private-branch', 'a', 'a2', 'Arroz y zanahoria.', 'Cena'),
        ('private-company', 'b', None, 'Arroz y zanahoria.', 'Cena'),
    ]:
        db.add(Recipe(id=identity, tenant_id=company, branch_id=branch, created_by='nutritionist',
                      title=identity, ingredients=ingredients, instructions='Cocinar completamente.',
                      calories=400, protein=30, carbohydrates=40, fats=12, fiber=8, sodium=90, category=category))
    db.commit()
    db.info['workspace'] = Workspace('admin', 'a', 'a1', True)
    monkeypatch.setattr(staff_gemini, 'interpret', lambda *args: (AssistantIntent(action='recommend', meal='Cena'), {'engine':'gemini','total_tokens':50}))
    yield SimpleNamespace(db=db, users=users, actor=users['admin'])
    db.info.pop('workspace', None)


def proposal(demo, actor=None):
    result = service.query(demo.db, actor or demo.actor, AssistantQuery(message='Recomendar cena', patient_id='patient', intent='recommend', meal='Cena'))
    return result, next(r['proposal_token'] for r in result['recipes'] if r['id'] == 'shared')


def test_candidates_are_local_scoped_and_exclude_known_allergens(demo):
    result, _ = proposal(demo)
    assert {r['id'] for r in result['recipes']} == {'shared', 'vegetarian'}
    assert result['usage'] == {'engine':'local','total_tokens':0}
    assert demo.db.query(RecipeAssignment).count() == 0
    assert demo.db.query(Notification).count() == 0
    assert demo.db.query(ActivityLog).count() == 0
    assert service.search_patients(demo.db, demo.users['nutritionist'])['patients'] == [{'id':'patient','full_name':'Alex Demo'}]
    assert all(p['id'] not in {'other-branch','other-company'} for p in service.search_patients(demo.db, demo.actor)['patients'])


def test_homonyms_require_selection_and_selected_name_cannot_redirect_silently(demo, monkeypatch):
    monkeypatch.setattr(staff_gemini, 'interpret', lambda *args:(AssistantIntent(action='recommend',patient_name='Alex',meal='Cena'),{}))
    result = service.query(demo.db, demo.actor, AssistantQuery(message='Cena para Alex'))
    assert result['kind'] == 'patients' and len(result['patients']) == 2
    assert not result.get('recipes')
    result = service.query(demo.db, demo.actor, AssistantQuery(message='Cena para Alex',patient_id='patient'))
    assert result['patient']['id'] == 'patient'
    monkeypatch.setattr(staff_gemini, 'interpret', lambda *args:(AssistantIntent(action='recommend',patient_name='privado'),{}))
    result = service.query(demo.db, demo.actor, AssistantQuery(message='Para privado',patient_id='patient'))
    assert result['kind'] == 'patients' and result['patients'] == []


def test_shared_catalog_assignment_is_confirmed_idempotent_and_audited(demo):
    _, token = proposal(demo)
    first = service.confirm(demo.db, demo.actor, token)
    second = service.confirm(demo.db, demo.actor, token)
    assert first['assignment_id'] == second['assignment_id']
    assignments = demo.db.query(RecipeAssignment).all()
    assert len(assignments) == 1
    assert (assignments[0].tenant_id, assignments[0].branch_id, assignments[0].patient_id) == ('a','a1','patient')
    assert demo.db.query(ActivityLog).filter_by(action='CARLITOS_RECETA_ASIGNADA').count() == 1
    result, _ = proposal_without_shared(demo)
    assert 'shared' not in {r['id'] for r in result['recipes']}


def test_used_proposal_cannot_restore_an_assignment_removed_afterwards(demo):
    _,token=proposal(demo)
    result=service.confirm(demo.db,demo.actor,token)
    demo.db.delete(demo.db.get(RecipeAssignment,result['assignment_id']))
    demo.db.commit()
    with pytest.raises(HTTPException) as error:service.confirm(demo.db,demo.actor,token)
    assert error.value.status_code==409


def proposal_without_shared(demo):
    result=service.query(demo.db,demo.actor,AssistantQuery(message='Otras',patient_id='patient',intent='recommend',meal='Cena'))
    return result, None


@pytest.mark.parametrize('identity', ['root','patient'])
def test_clients_and_platform_admin_are_rejected_before_ai(demo, identity, monkeypatch):
    monkeypatch.setattr(staff_gemini, 'interpret', lambda *args:pytest.fail('No authorized AI call'))
    with pytest.raises(HTTPException) as error:
        service.query(demo.db,demo.users[identity],AssistantQuery(message='Busca pacientes'))
    assert error.value.status_code == 403


@pytest.mark.parametrize('identity', ['other-branch','other-company','unlinked'])
def test_nutritionist_cannot_read_or_recommend_for_unauthorized_patient(demo, identity):
    with pytest.raises(HTTPException) as error:
        service.query(demo.db,demo.users['nutritionist'],AssistantQuery(message='Receta',patient_id=identity,intent='recommend'))
    assert error.value.status_code == 404


@pytest.mark.parametrize('change', ['workspace','actor','expired','tampered','profile','recipe','unlinked'])
def test_stale_or_foreign_proposals_cannot_write(demo, change):
    actor = demo.users['nutritionist'] if change == 'unlinked' else demo.actor
    _, token = proposal(demo, actor)
    if change == 'workspace':
        demo.db.info['workspace'] = Workspace(actor.id, 'a', 'a2', True)
    elif change == 'actor':
        actor=demo.users['nutritionist']
    elif change == 'expired':
        data=jwt.decode(token,settings.SECRET_KEY,algorithms=[settings.ALGORITHM])
        data['exp']=datetime.now(timezone.utc)-timedelta(minutes=1)
        token=jwt.encode(data,settings.SECRET_KEY,algorithm=settings.ALGORITHM)
    elif change == 'tampered':
        token='invalid.'+token
    elif change == 'profile':
        demo.db.query(PatientAnamnesis).one().allergies='Huevo'
        demo.db.commit()
    elif change == 'recipe':
        # Simulate a separate catalogue update; shared catalogue edits are not branch writes.
        demo.db.execute(Recipe.__table__.update().where(Recipe.__table__.c.id=='shared').values(ingredients='Leche de vaca'))
        demo.db.commit()
    elif change == 'unlinked':
        demo.db.query(PatientNutritionistLink).one().status='CANCELLED'
        demo.db.commit()
    with pytest.raises(HTTPException) as error:
        service.confirm(demo.db,actor,token)
    assert error.value.status_code in {403,404,409}
    assert demo.db.query(RecipeAssignment).count() == 0
    assert demo.db.query(Notification).count() == 0


def test_unknown_allergies_missing_consent_and_missing_profile_require_review(demo):
    profile=demo.db.query(PatientAnamnesis).one()
    profile.allergies='Alergia no identificada'
    demo.db.commit()
    result=service.query(demo.db,demo.actor,AssistantQuery(message='Receta',patient_id='patient',intent='recommend'))
    assert result['recipes'] == [] and 'certeza' in result['message']
    profile.consent_data_processing=False
    demo.db.commit()
    with pytest.raises(HTTPException) as error:
        service.query(demo.db,demo.actor,AssistantQuery(message='Receta',patient_id='patient',intent='recommend'))
    assert error.value.status_code == 403
    with pytest.raises(HTTPException) as error:
        service.query(demo.db,demo.actor,AssistantQuery(message='Receta',patient_id='homonym',intent='recommend'))
    assert error.value.status_code == 422


@pytest.mark.parametrize('allergy,ingredient', [('Maní','Mani tostado'),('Gluten','Avena'),('Nueces','Almendras'),('Pescado','Atún')])
def test_allergy_aliases_and_accents_are_excluded(demo, allergy, ingredient):
    profile=demo.db.query(PatientAnamnesis).one();profile.allergies=allergy
    recipe=demo.db.query(Recipe).filter_by(id='shared').one();recipe.ingredients=ingredient
    assert service.evaluate_recipe(recipe,profile) is None


def test_quick_search_and_query_endpoint_validate_payloads(client,demo):
    client.app.dependency_overrides[get_current_user]=lambda:demo.actor
    response=client.get('/api/v1/staff-assistant/patients?search=Alex')
    assert response.status_code==200 and len(response.json()['patients'])==2
    response=client.post('/api/v1/staff-assistant/query',json={'message':' ', 'intent':'recommend'})
    assert response.status_code==422
    response=client.post('/api/v1/staff-assistant/query',json={'message':'x'*801})
    assert response.status_code==422
    response=client.post('/api/v1/staff-assistant/query',json={'message':'Cena','intent':'recommend','patient_id':'patient','meal':'Cena'})
    assert response.status_code==200 and response.json()['recipes']


def test_patient_reads_assigned_recipe_without_other_patient_ids(client,demo):
    _,token=proposal(demo)
    service.confirm(demo.db,demo.actor,token)
    demo.db.add(RecipeAssignment(tenant_id='a',branch_id='a1',recipe_id='shared',patient_id='homonym'))
    demo.db.commit()
    client.app.dependency_overrides[get_current_user]=lambda:demo.users['patient']
    response=client.get('/api/v1/recipes/my-plan')
    assert response.status_code==200
    assert response.json()[0]['assigned_patient_ids']==['patient']


def test_legacy_recipe_assignment_also_requires_linked_patient(client,demo):
    client.app.dependency_overrides[get_current_user]=lambda:demo.users['nutritionist']
    assert client.post('/api/v1/recipes/shared/assign/unlinked').status_code==403
    assert client.post('/api/v1/recipes/shared/assign/patient').status_code==200


def test_shared_catalog_does_not_allow_foreign_company_assignments(demo):
    demo.db.add(RecipeAssignment(recipe_id='private-company',patient_id='patient',tenant_id='a',branch_id='a1'))
    with pytest.raises(HTTPException) as error:demo.db.commit()
    demo.db.rollback()
    assert error.value.status_code==403


def test_missing_staff_key_never_uses_general_key(monkeypatch):
    monkeypatch.setattr(settings,'GEMINI_STAFF_API_KEY','')
    monkeypatch.setattr(settings,'GEMINI_API_KEY','general-key-must-not-be-used')
    def forbidden(request):pytest.fail('Dedicated key missing; do not call Gemini')
    monkeypatch.setattr(staff_gemini,'_client',httpx.Client(transport=httpx.MockTransport(forbidden)))
    with pytest.raises(HTTPException) as error:staff_gemini.interpret('Pedido','user','tenant')
    assert error.value.status_code==503


def test_provider_uses_only_dedicated_key_and_bounded_json_payload(monkeypatch):
    staff_gemini._windows.clear()
    monkeypatch.setattr(settings,'GEMINI_STAFF_API_KEY','staff-only-test-key')
    monkeypatch.setattr(settings,'GEMINI_API_KEY','general-key-must-not-be-used')
    calls=[]
    def handler(request):
        calls.append(request)
        assert request.headers['x-goog-api-key']=='staff-only-test-key'
        assert 'key=' not in str(request.url)
        payload=json.loads(request.content)
        assert payload['generationConfig']['maxOutputTokens']==192
        assert '' not in payload['generationConfig']['responseSchema']['properties']['meal']['enum']
        assert len(payload['contents'])==1
        assert 'anamnesis' not in payload['contents'][0]['parts'][0]['text']
        return httpx.Response(200,json={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':'{"action":"recommend","patient_name":"Alex","meal":"Cena"}'}]}}],
                                        'usageMetadata':{'promptTokenCount':150,'candidatesTokenCount':30,'totalTokenCount':180}})
    monkeypatch.setattr(staff_gemini,'_client',httpx.Client(transport=httpx.MockTransport(handler)))
    intent,usage=staff_gemini.interpret('Recomienda una cena para Alex','user','tenant')
    assert intent.patient_name=='Alex' and usage['total_tokens']==180
    for _ in range(5): staff_gemini.interpret('Cena para Alex','user','tenant')
    with pytest.raises(HTTPException) as error: staff_gemini.interpret('Otra','user','tenant')
    assert error.value.status_code==429 and len(calls)==6


@pytest.mark.parametrize('status,body',[(429,{}),(200,{'candidates':[{'finishReason':'MAX_TOKENS'}]}),(200,{'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':'{"action":"delete","patient_name":"Alex","meal":""}'}]}}]})])
def test_provider_failures_are_not_retried_or_exposed(monkeypatch,status,body):
    staff_gemini._windows.clear()
    monkeypatch.setattr(settings,'GEMINI_STAFF_API_KEY','staff-only-test-key')
    calls=[]
    def handler(request):
        calls.append(request)
        return httpx.Response(status,json=body)
    monkeypatch.setattr(staff_gemini,'_client',httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(HTTPException) as error: staff_gemini.interpret('Pedido','user','tenant')
    assert error.value.status_code==503 and len(calls)==1
    assert 'staff-only-test-key' not in error.value.detail


def test_confirm_notifies_only_patient_once_and_queues_push_after_commit(demo,monkeypatch):
    from app.services.push_service import PushService
    queued=[]
    def enqueue(ids):
        for identity in ids:
            row=demo.db.get(Notification,identity)
            assert row is not None and row.user_id=='patient'
        queued.extend(ids)
    monkeypatch.setattr(PushService,'enqueue',staticmethod(enqueue))
    _,token=proposal(demo)
    _,second_token=proposal(demo)
    assert demo.db.query(Notification).count()==0 and queued==[]
    first=service.confirm(demo.db,demo.actor,token)
    service.confirm(demo.db,demo.actor,token)
    service.confirm(demo.db,demo.actor,second_token)
    rows=demo.db.query(Notification).all()
    assert len(rows)==1 and queued==[rows[0].id]
    notification=rows[0]
    assert (notification.user_id,notification.tenant_id,notification.branch_id)==('patient','a','a1')
    assert notification.type=='RECETA_ASIGNADA' and notification.reference_id=='shared'
    assert notification.is_read is False and 'Mi plan nutricional' in notification.message
    assert demo.db.get(RecipeAssignment,first['assignment_id']) is not None


def test_failed_assignment_transaction_does_not_leave_notification_or_send_push(demo,monkeypatch):
    from app.services.push_service import PushService
    queued=[]
    monkeypatch.setattr(PushService,'enqueue',staticmethod(lambda ids:queued.extend(ids)))
    _,token=proposal(demo)
    def fail_commit():
        demo.db.flush()
        raise RuntimeError('Simulated transaction failure')
    with monkeypatch.context() as patch:
        patch.setattr(demo.db,'commit',fail_commit)
        with pytest.raises(RuntimeError):service.confirm(demo.db,demo.actor,token)
        demo.db.rollback()
    assert demo.db.query(RecipeAssignment).count()==0
    assert demo.db.query(Notification).count()==0 and queued==[]
