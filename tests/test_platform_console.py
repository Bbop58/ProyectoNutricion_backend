from datetime import datetime, timedelta
import pytest
from app.core.security import create_access_token, get_password_hash
from app.models.user import User
from app.models.tenant import Tenant
from app.models.company import Branch, CompanyAdministrator
from app.models.rbac import Role
from app.models.commercial_plan import CommercialPlan, PlatformAudit
from app.models.subscription import Subscription
from app.models.subscription_receipt import SubscriptionReceipt
from app.models.payment import Payment


def headers(who='root'):
    return {'Authorization': 'Bearer ' + create_access_token(subject=who)}


@pytest.fixture
def platform(db_session):
    db = db_session
    for role in ['SUPERADMIN','ADMIN_ORGANIZATION','NUTRICIONISTA','CLIENTE']:
        db.add(Role(id=role, name=role, description=role, platform='Web'))
    db.add_all([Tenant(id='a', name='Empresa A', code='AA', department_code='01'), Tenant(id='b', name='Empresa B', code='BB')])
    db.flush()
    db.add_all([Branch(id='a1', tenant_id='a', name='Centro', code='CENTRO'), Branch(id='b1', tenant_id='b', name='Norte', code='NORTE')])
    password = get_password_hash('Password123!')
    for identity, role, tenant, branch in [('root','SUPERADMIN',None,None),('admin','ADMIN_ORGANIZATION','a','a1'),('other','ADMIN_ORGANIZATION','b','b1'),('doctor','NUTRICIONISTA','a','a1'),('patient','CLIENTE','a','a1')]:
        db.add(User(id=identity, email=identity+'@example.com', full_name=identity, hashed_password=password, role_id=role, tenant_id=tenant, branch_id=branch))
    db.flush()
    db.add(CompanyAdministrator(tenant_id='a', user_id='admin'))
    db.add(CommercialPlan(code='BASICO', display_name='Básico', price=9.99, currency='USD', duration_days=30, max_patients=10, max_branches=3, features=[]))
    db.add(Subscription(id='original', tenant_id='a', user_id='admin', branch_id='a1', plan_name='BASICO', plan_snapshot={'max_patients':10,'max_branches':3,'duration_days':30,'price':9.99}, source='PAYPAL', status='ACTIVE', amount=9.99, started_at=datetime.now(), expires_at=datetime.now()+timedelta(days=30)))
    db.commit()


def test_superadmin_only_has_platform_access(client, platform):
    for path in ['/platform/overview','/platform/companies','/platform/plans','/platform/subscriptions','/platform/audit','/users/me']:
        r = client.get('/api/v1'+path, headers=headers())
        assert r.status_code == 200, (path,r.text)
    for path in ['/users/patients','/tenants','/branches','/organization-users','/recipes','/payments','/appointments','/reports/entities','/backup/settings','/activity-logs','/roles','/users/me/workspace-options']:
        r = client.get('/api/v1'+path, headers=headers())
        assert r.status_code == 403, (path,r.text)
    r = client.post('/api/v1/reports/query', headers={**headers(), 'X-Report-Client':'mobile'}, json={'entity':'patients'})
    assert r.status_code == 403
    for who in ['admin','doctor','patient']:
        assert client.get('/api/v1/platform/companies', headers=headers(who)).status_code == 403
    companies = client.get('/api/v1/platform/companies', headers=headers()).json()['items']
    assert {c['name'] for c in companies} == {'Empresa A','Empresa B'}
    assert all('patients' not in c and 'payments' not in c for c in companies)


def test_plans_assignment_snapshot_and_audit(client, db_session, platform):
    body = dict(code='NUEVO', display_name='Nuevo', price=15, duration_days=60, max_patients=5, max_branches=2, is_active=True, reason='Alta comercial')
    r = client.post('/api/v1/platform/plans', headers=headers(), json=body)
    assert r.status_code == 201, r.text
    assert 'NUEVO' in {p['name'] for p in client.get('/api/v1/subscriptions/plans').json()}
    assigned = client.put('/api/v1/platform/companies/a/subscription', headers=headers(), json={'plan_code':'NUEVO','reason':'Acceso de cortesía'})
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()['source'] == 'MANUAL' and assigned.json()['amount'] == 0
    assert db_session.query(Payment).count() == 0 and db_session.query(SubscriptionReceipt).count() == 0
    assert db_session.get(Subscription,'original').amount == 9.99
    body['price'] = 99
    body['max_patients'] = 20
    updated = client.patch('/api/v1/platform/plans/NUEVO', headers=headers(), json=body)
    assert updated.status_code == 200, updated.text
    sub = db_session.get(Subscription, assigned.json()['id'])
    assert sub.plan_snapshot['price'] == 15 and sub.plan_snapshot['max_patients'] == 5
    body['is_active'] = False
    assert client.patch('/api/v1/platform/plans/NUEVO', headers=headers(), json=body).status_code == 200
    assert 'NUEVO' not in {p['name'] for p in client.get('/api/v1/subscriptions/plans').json()}
    assert client.put('/api/v1/platform/companies/a/subscription', headers=headers(), json={'plan_code':'NUEVO','reason':'No permitido'}).status_code == 400
    assert db_session.query(PlatformAudit).count() == 4


def test_suspension_blocks_existing_sessions_and_login(client, platform):
    r = client.patch('/api/v1/platform/companies/a/status', headers=headers(), json={'is_active':False, 'reason':'Suspensión administrativa'})
    assert r.status_code == 200, r.text
    assert client.get('/api/v1/recipes', headers=headers('admin')).status_code == 403
    assert client.post('/api/v1/auth/login', json={'email':'admin@example.com','password':'Password123!'}).status_code == 403
    assert client.get('/api/v1/recipes', headers=headers('other')).status_code == 200
    assert client.get('/api/v1/platform/companies', headers=headers()).status_code == 200
    assert client.patch('/api/v1/platform/companies/a/status', headers=headers(), json={'is_active':True,'reason':'Reactivación administrativa'}).status_code == 200
    assert client.get('/api/v1/recipes', headers=headers('admin')).status_code == 200


def test_capacity_and_duplicate_plan_validation(client, db_session, platform):
    plan = db_session.get(CommercialPlan, 'BASICO')
    plan.max_patients = 1
    plan.max_branches = 1
    db_session.commit()
    assert client.put('/api/v1/platform/companies/a/subscription', headers=headers(), json={'plan_code':'BASICO','reason':'Aplicar límites'}).status_code == 200
    body = {'email':'new@example.com','full_name':'Nuevo paciente','password':'Password123!','role_id':'CLIENTE','tenant_id':'a','branch_id':'a1'}
    r = client.post('/api/v1/organization-users', headers=headers('admin'), json=body)
    assert r.status_code == 400 and 'hasta 1 pacientes' in r.text, r.text
    r = client.post('/api/v1/branches', headers=headers('admin'), json={'tenant_id':'a','name':'Otra sede','code':'OTRA','province_code':'0101','municipality_code':'010101'})
    assert r.status_code == 400 and 'sucursales' in r.text, r.text
    assert client.post('/api/v1/platform/plans', headers=headers(), json={'code':'XX','display_name':'Mal','price':-1,'reason':'Prueba'}).status_code == 422
