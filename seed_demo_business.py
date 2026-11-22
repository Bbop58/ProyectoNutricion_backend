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

    print("Carga demo completada (número de registros nuevos):")
    for label, count in counts.items():
        print(f"  {label}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
