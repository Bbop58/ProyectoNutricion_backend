"""One-shot, non-destructive photo backfill for known demo recipe IDs only."""
import argparse
import json

from app.config import settings
from app.database import get_session_local
from app.models.recipe import Recipe
from app.models.tenant import Tenant
from app.seeders.demo_business import DEMO_COMPANIES, DEMO_RECIPES, _id
from app.seeders.demo_recipes import demo_recipe_image_url

LEGACY_PLACEHOLDER = "https://images.unsplash.com/photo-1546069901-ba9599a7e63c"


def populate_demo_recipe_images(db):
    counts = dict(updated=0, preserved=0)
    for company in DEMO_COMPANIES:
        tenant = db.query(Tenant).filter_by(code=company.code).first()
        if not tenant:
            continue
        for item in DEMO_RECIPES:
            recipe = db.get(Recipe, _id("recipe", company.code, item.key))
            if not recipe:
                continue
            if recipe.tenant_id != tenant.id or recipe.title != item.title:
                counts['preserved'] += 1
                continue
            current = (recipe.image_url or '').strip()
            if current and current.split('?')[0].rstrip('/') != LEGACY_PLACEHOLDER:
                counts['preserved'] += 1
                continue
            recipe.image_url = demo_recipe_image_url(item.key)
            counts['updated'] += 1
    db.commit()
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--allow-production', action='store_true')
    args = parser.parse_args()
    if settings.ENVIRONMENT.lower() in {'production', 'prod'} and not args.allow_production:
        parser.error('Usa --allow-production para actualizar las imágenes demo en producción.')
    with get_session_local()() as db:
        try:
            result = populate_demo_recipe_images(db)
        except Exception:
            db.rollback()
            raise
    print('Imágenes demo: ' + json.dumps(result))


if __name__ == '__main__':
    main()
