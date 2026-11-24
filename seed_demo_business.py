"""One-shot CLI to create synthetic demo businesses and historical activity."""

import argparse
import os

from app.config import settings
from app.database import get_session_local
from app.seeders.demo_business import seed_demo_businesses


def main() -> int:
    parser = argparse.ArgumentParser(description="Genera cinco empresas ficticias con actividad ene-nov 2026.")
    parser.add_argument(
        "--allow-production",
        action="store_true",
        help="Permite añadir datos sintéticos cuando ENVIRONMENT=production/prod.",
    )
    args = parser.parse_args()
    password = os.getenv("DEMO_BUSINESS_SEED_PASSWORD", "")
    db = get_session_local()()
    try:
        counts = seed_demo_businesses(
            db,
            password,
            environment=settings.ENVIRONMENT,
            allow_production=args.allow_production,
        )
    except Exception as exc:
        print(f"No se completó la carga demo: {exc}")
        return 1
    finally:
        db.close()

    count_labels = (
        "companies", "branches", "users", "patient_links", "subscriptions",
        "subscription_receipts", "appointments", "payments", "recipes", "food_records",
        "anamneses", "preserved_anamneses", "measurements", "clinical_records",
        "draft_plans", "care_messages", "nutrition_configurations",
    )
    print("Carga demo completada (registros nuevos):")
    for label in count_labels:
        print(f"  {label}: {counts[label]}")
    print("Ingresos brutos simulados, separados por origen (USD):")
    print(f"  suscripciones de empresas: {counts['subscription_revenue_usd']:.2f}")
    print(f"  consultas cobradas en caja: {counts['consultation_revenue_usd']:.2f}")
    print(f"  total bruto: {counts['gross_revenue_usd']:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
