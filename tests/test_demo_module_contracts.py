"""Exercise real demo records through API serialization, not just ORM queries."""
from app.seeders.demo_business import seed_demo_businesses
from app.models.rbac import Role


def test_demo_admin_module_contracts(client, db_session):
    for role in ('ADMIN_ORGANIZATION', 'NUTRICIONISTA', 'CLIENTE'):
        db_session.add(Role(id=role, name=role, description='Demo', platform='Web'))
    db_session.commit()
    password = 'Demo-module-check-2026!'
    seed_demo_businesses(db_session, password, environment='test')
    login = client.post('/api/v1/auth/login', json={
        'email': 'admin.nutrifit@example.test', 'password': password,
    })
    assert login.status_code == 200, login.text
    headers = {'Authorization': 'Bearer ' + login.json()['access_token']}
    company = login.json()['user']['tenant_id']
    endpoints = [
        '/users/me', '/users/me/workspace-options', '/tenants',
        '/branches?tenant_id=' + company, '/organization-users', '/users/patients',
        '/patient-links', '/appointments', '/appointments/nutritionists', '/recipes',
        '/payments', '/payments/stats', '/subscriptions/plans', '/subscriptions/current',
        '/subscriptions/history', '/subscriptions/receipts', '/notifications',
        '/notifications/unread-count', '/reports/entities', '/reports/scope', '/reports/saved',
        '/backup/history',
    ]
    failures = []
    for endpoint in endpoints:
        response = client.get('/api/v1' + endpoint, headers=headers)
        if response.status_code != 200:
            failures.append((endpoint, response.status_code, response.text[:500]))
    assert not failures, failures
    for entity in ('patients', 'appointments', 'payments', 'recipes', 'clinical_records', 'nutritional_plans'):
        response = client.post('/api/v1/reports/query', headers=headers, json={'entity': entity})
        assert response.status_code == 200, (entity, response.text)
