from app.core.workspace import Workspace
from app.models.recipe import Recipe
from app.models.tenant import Tenant
from app.models.company import Branch
from app.models.rbac import Role
from app.models.user import User


def test_company_catalog_visible_in_each_branch_without_leaking_other_branches(db_session):
    db = db_session
    db.add(Role(id='NUTRICIONISTA', name='Nutritionist', description='Test', platform='Web'))
    db.add_all([Tenant(id='a', name='A', code='A'), Tenant(id='b', name='B', code='B')])
    db.flush()
    db.add_all([Branch(id=branch, tenant_id=tenant, name=branch, code=branch)
                for branch, tenant in [('a1', 'a'), ('a2', 'a'), ('b1', 'b')]])
    db.add(User(id='staff', email='staff@example.test', full_name='Staff',
                hashed_password='test-only', role_id='NUTRICIONISTA', tenant_id='a', branch_id='a1'))
    db.flush()
    for recipe_id, tenant, branch in [('shared-a', 'a', None), ('local-a1', 'a', 'a1'),
                                      ('local-a2', 'a', 'a2'), ('shared-b', 'b', None)]:
        db.add(Recipe(id=recipe_id, tenant_id=tenant, branch_id=branch, created_by='staff',
                      title=recipe_id, ingredients='Demo', instructions='Demo'))
    db.commit()
    for branch in ['a1', 'a2']:
        db.info['workspace'] = Workspace('staff', 'a', branch, True)
        assert {r.id for r in db.query(Recipe).all()} == {'shared-a', f'local-{branch}'}
    db.info.pop('workspace')
