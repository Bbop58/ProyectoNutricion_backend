from app.models.rbac import Role
from app.models.recipe import Recipe
from app.seeders.demo_business import seed_demo_businesses
from seed_demo_recipe_images import LEGACY_PLACEHOLDER, populate_demo_recipe_images


def test_backfill_only_updates_missing_or_legacy_demo_photos_and_is_idempotent(db_session):
    db = db_session
    db.add_all([Role(id=role, name=role, description='Demo', platform='Web')
                for role in ('CLIENTE', 'NUTRICIONISTA', 'ADMIN_ORGANIZATION')])
    db.commit()
    seed_demo_businesses(db, 'Demo-images-2026!', environment='test')
    recipes = db.query(Recipe).all()
    assert len(recipes) == 96
    assert len({r.image_url for r in recipes}) == 32
    assert all(r.image_url.startswith('https://nutrisalud-web.vercel.app/assets/recipes/demo/')
               and r.image_url.endswith('.webp') for r in recipes)
    recipes[0].image_url = None
    recipes[1].image_url = LEGACY_PLACEHOLDER + '?w=500'
    recipes[2].image_url = 'https://example.com/foto-propia.jpg'
    recipes[3].title = 'Receta cambiada por el profesional'
    recipes[3].image_url = None
    own = Recipe(id='user-created', tenant_id=recipes[0].tenant_id, branch_id=None,
                 created_by=recipes[0].created_by, title='Receta propia', ingredients='Ingredientes',
                 instructions='Preparación', image_url=None)
    db.add(own)
    db.commit()
    assert populate_demo_recipe_images(db) == dict(updated=2, preserved=94)
    assert recipes[0].image_url.endswith('.webp') and recipes[1].image_url.endswith('.webp')
    assert recipes[2].image_url == 'https://example.com/foto-propia.jpg'
    assert recipes[3].image_url is None and own.image_url is None
    assert populate_demo_recipe_images(db) == dict(updated=0, preserved=96)
