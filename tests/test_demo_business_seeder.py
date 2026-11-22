from datetime import datetime, timezone
import json

import pytest

from app.models.appointment import Appointment
from app.models.ai_nutrition import FoodRecord
from app.models.company import Branch
from app.models.payment import Payment
from app.models.recipe import Recipe
from app.models.rbac import Role
from app.models.subscription import Subscription
from app.models.tenant import Tenant
from app.models.user import User
from app.seeders.demo_business import DEMO_COMPANIES, PERIOD_END, seed_demo_businesses
from app.services.bolivia_locations import validate_location
from app.services.subscription_service import PLANS
from init_sprint1_db import ensure_sample_tenant_primary_branch


def add_roles(db):
    db.add_all([
        Role(id="ADMIN_ORGANIZATION", name="Admin", description="Demo", platform="Web"),
        Role(id="NUTRICIONISTA", name="Nutricionista", description="Demo", platform="Web"),
        Role(id="CLIENTE", name="Cliente", description="Demo", platform="Móvil / Web"),
    ])
    db.commit()


def test_seed_creates_business_history_within_plan_rules_and_is_idempotent(db_session):
    add_roles(db_session)
    password = "Valid-demo-passphrase-2026!"

    first = seed_demo_businesses(db_session, password, environment="development")

    assert first["companies"] == 5
    assert first["branches"] == 12
    assert first["subscriptions"] == 55
    assert first["patient_links"] == 159
    assert first["payments"] == first["appointments"]
    assert first["recipes"] == 24
    assert first["food_records"] > 159

    for company in DEMO_COMPANIES:
        tenant = db_session.query(Tenant).filter_by(code=company.code).one()
        branches = db_session.query(Branch).filter_by(tenant_id=tenant.id, is_active=True).all()
        patients = db_session.query(User).filter_by(tenant_id=tenant.id, role_id="CLIENTE").all()
        subscriptions = db_session.query(Subscription).filter_by(tenant_id=tenant.id).order_by(Subscription.started_at).all()
        appointments = db_session.query(Appointment).filter_by(tenant_id=tenant.id).all()
        payments = db_session.query(Payment).filter_by(tenant_id=tenant.id).all()
        recipes = db_session.query(Recipe).filter_by(tenant_id=tenant.id).all()
        food_records = db_session.query(FoodRecord).filter_by(tenant_id=tenant.id).all()

        assert len(branches) == len(company.branch_names)
        assert len(patients) == company.patient_count
        max_patients = PLANS[company.plan]["max_patients"]
        assert max_patients is None or len(patients) <= max_patients
        validate_location(company.department_code, company.province_code, company.municipality_code)
        assert len(subscriptions) == 11
        assert [row.status for row in subscriptions].count("ACTIVE") == 1
        assert [row.status for row in subscriptions].count("REPLACED") == 10
        assert subscriptions[-1].started_at == datetime(2026, 10, 28)
        assert subscriptions[-1].expires_at == datetime(2026, 11, 27)
        assert all(row.plan_name == company.plan for row in subscriptions)
        assert all(row.paypal_order_id is None and row.paypal_capture_id is None for row in subscriptions)
        assert all(row.status == "COMPLETED" for row in appointments)
        assert all(row.scheduled_at.date() <= PERIOD_END for row in appointments)
        assert all(row.status == "COMPLETED" and row.payment_method == "EFECTIVO" for row in payments)
        assert all(row.amount == 5.0 and row.currency == "USD" for row in payments)
        assert all(row.paypal_order_id is None and row.paypal_capture_id is None for row in payments)
        assert all(row.appointment_id is not None for row in payments)
        recipe_feature = any(
            item["text"] == "Recetario & Macros" and item["included"]
            for item in PLANS[company.plan]["features"]
        )
        assert len(recipes) == (8 if recipe_feature else 0)
        assert all("ficticia" in row.description.lower() for row in recipes)
        assert all(row.created_by and row.branch_id is None for row in recipes)
        assert food_records
        assert all(row.confidence == "manual" and row.image_url is None for row in food_records)
        assert all("Registro demo" in row.notes for row in food_records)
        assert all(datetime(2026, 1, 1).date() <= row.created_at.date() <= PERIOD_END for row in food_records)
        assert all(json.loads(row.result_json)["source"] == "manual" for row in food_records)

    # A retry creates nothing and leaves every synthetic entity count stable.
    second = seed_demo_businesses(db_session, password, environment="development")
    assert all(value == 0 for value in second.values())
    assert db_session.query(Tenant).count() == 5
    assert db_session.query(Branch).count() == 12
    assert db_session.query(Subscription).count() == 55
    assert db_session.query(Recipe).count() == 24
    assert db_session.query(FoodRecord).count() == first["food_records"]


def test_production_guard_rejects_before_writing(db_session):
    with pytest.raises(RuntimeError, match="--allow-production"):
        seed_demo_businesses(
            db_session,
            "Valid-demo-passphrase-2026!",
            environment="production",
        )
    assert db_session.query(Tenant).count() == 0


def test_builtin_sample_clinic_gets_reusable_primary_branch(db_session):
    tenant = Tenant(id="vidasana-test", name="Vida Sana", code="VIDASANA", is_active=True)
    db_session.add(tenant)
    db_session.commit()

    first = ensure_sample_tenant_primary_branch(db_session, tenant)
    db_session.commit()
    second = ensure_sample_tenant_primary_branch(db_session, tenant)
    db_session.commit()

    assert first.id == second.id
    assert first.code == "PRINCIPAL"
    assert first.is_active is True
    assert first.province_code == "0701"
    assert first.municipality_code == "070101"
    assert tenant.department_code == "07"
    assert db_session.query(Branch).filter_by(tenant_id=tenant.id).count() == 1


def test_seed_preserves_unrelated_tenant_and_account(db_session):
    add_roles(db_session)
    tenant = Tenant(id="customer-tenant", name="Cliente real", code="CLIENTE-REAL", is_active=False)
    user = User(
        id="customer-user",
        email="real.customer@example.com",
        hashed_password="keep-me",
        full_name="Cuenta Existente",
        role_id="CLIENTE",
        tenant_id=tenant.id,
        is_active=False,
        created_at=datetime(2025, 5, 5, tzinfo=timezone.utc),
    )
    db_session.add_all([tenant, user])
    db_session.commit()

    seed_demo_businesses(db_session, "Valid-demo-passphrase-2026!", environment="development")

    assert db_session.get(Tenant, tenant.id).name == "Cliente real"
    assert db_session.get(Tenant, tenant.id).is_active is False
    preserved = db_session.get(User, user.id)
    assert preserved.email == "real.customer@example.com"
    assert preserved.hashed_password == "keep-me"
    assert preserved.is_active is False
