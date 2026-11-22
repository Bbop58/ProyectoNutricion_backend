from datetime import datetime, timezone
import json

import pytest

from app.core.workspace import Workspace
from app.models.appointment import Appointment
from app.models.ai_nutrition import FoodRecord
from app.models.company import Branch
from app.models.payment import Payment
from app.models.recipe import Recipe
from app.models.rbac import Role
from app.models.subscription import Subscription
from app.models.subscription_receipt import SubscriptionReceipt
from app.models.tenant import Tenant
from app.models.user import User
from app.seeders.demo_business import DEMO_COMPANIES, PERIOD_END, seed_demo_businesses
from app.services.bolivia_locations import validate_location
from app.services.payment_service import PaymentService
from app.services.personal_reports_service import PersonalReportsService
from app.services.subscription_service import PLANS, SubscriptionService
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
    assert first["appointments"] == 352
    assert first["patient_links"] == 159
    assert first["payments"] == first["appointments"]
    assert first["subscription_receipts"] == first["subscriptions"]
    assert first["recipes"] == 24
    assert first["food_records"] > 159

    expected_subscription_sales = sum(11 * PLANS[company.plan]["price"] for company in DEMO_COMPANIES)
    assert expected_subscription_sales == pytest.approx(1319.45)
    assert sum(float(row[0]) for row in db_session.query(SubscriptionReceipt.amount).all()) == pytest.approx(
        expected_subscription_sales
    )
    expected_consultation_sales = first["payments"] * 5.0
    assert expected_consultation_sales == pytest.approx(1760.00)
    assert first["subscription_revenue_usd"] == pytest.approx(expected_subscription_sales)
    assert first["consultation_revenue_usd"] == pytest.approx(expected_consultation_sales)
    assert first["gross_revenue_usd"] == pytest.approx(
        expected_subscription_sales + expected_consultation_sales
    )
    assert first["gross_revenue_usd"] == pytest.approx(3079.45)
    all_cash_stats = PaymentService.get_payment_stats(db_session)
    assert all_cash_stats.completed_count == first["payments"]
    assert all_cash_stats.total_collected == pytest.approx(expected_consultation_sales)
    assert {row[0].month for row in db_session.query(Payment.paid_at).all()} == set(range(1, 12))

    for company in DEMO_COMPANIES:
        tenant = db_session.query(Tenant).filter_by(code=company.code).one()
        branches = db_session.query(Branch).filter_by(tenant_id=tenant.id, is_active=True).all()
        patients = db_session.query(User).filter_by(tenant_id=tenant.id, role_id="CLIENTE").all()
        subscriptions = db_session.query(Subscription).filter_by(tenant_id=tenant.id).order_by(Subscription.started_at).all()
        admin = db_session.query(User).filter_by(tenant_id=tenant.id, role_id="ADMIN_ORGANIZATION").one()
        db_session.info["workspace"] = Workspace(
            user_id=admin.id, tenant_id=tenant.id, branch_id=admin.branch_id, staff=True
        )
        subscription_history = SubscriptionService.get_history(
            db_session, tenant_id=tenant.id, user_id=admin.id
        )
        receipts = db_session.query(SubscriptionReceipt).filter_by(user_id=admin.id).all()
        db_session.info.pop("workspace")
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
        assert len(subscription_history) == 11
        assert len(receipts) == 11
        assert [row.status for row in subscriptions].count("ACTIVE") == 1
        assert [row.status for row in subscriptions].count("REPLACED") == 10
        assert subscriptions[-1].started_at == datetime(2026, 10, 28)
        assert subscriptions[-1].expires_at == datetime(2026, 11, 27)
        assert all(row.plan_name == company.plan for row in subscriptions)
        assert all(row.user_id == admin.id and row.branch_id == admin.branch_id for row in subscriptions), [
            (row.id, row.user_id, row.branch_id, admin.id) for row in subscriptions
            if row.user_id != admin.id or row.branch_id != admin.branch_id
        ]
        assert all(row.paypal_order_id is None and row.paypal_capture_id is None for row in subscriptions)
        assert all(
            receipt.tenant_id == tenant.id
            and receipt.branch_id == admin.branch_id
            and receipt.plan_name == company.plan
            and float(receipt.amount) == pytest.approx(PLANS[company.plan]["price"])
            and receipt.currency == PLANS[company.plan]["currency"]
            and receipt.user_id == admin.id
            and receipt.buyer_email == admin.email
            and receipt.is_sandbox is True
            and receipt.paypal_order_id.startswith("DEMO-ORDER-")
            and receipt.paypal_capture_id.startswith("DEMO-CAPTURE-")
            and receipt.paid_at == subscription.started_at
            for receipt, subscription in zip(
                sorted(receipts, key=lambda row: row.paid_at),
                sorted(subscriptions, key=lambda row: row.started_at),
            )
        )
        assert all(row.status == "COMPLETED" for row in appointments)
        assert all(row.scheduled_at.date() <= PERIOD_END for row in appointments)
        assert all(row.status == "COMPLETED" and row.payment_method == "EFECTIVO" for row in payments)
        assert all(row.amount == 5.0 and row.currency == "USD" for row in payments)
        assert all(row.paypal_order_id is None and row.paypal_capture_id is None for row in payments)
        assert all(row.appointment_id is not None for row in payments)
        company_cash_stats = PaymentService.get_payment_stats(db_session, tenant_id=tenant.id)
        assert company_cash_stats.completed_count == len(appointments)
        assert company_cash_stats.total_collected == pytest.approx(len(appointments) * 5.0)
        receipt_report = PersonalReportsService.generate(
            db_session, admin, "subscriptions", start_date=datetime(2026, 1, 1).date(),
            end_date=PERIOD_END,
        )
        assert receipt_report.total_rows == 11
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
    count_keys = (
        "companies", "branches", "users", "patient_links", "subscriptions",
        "subscription_receipts", "appointments", "payments", "recipes", "food_records",
    )
    assert all(second[key] == 0 for key in count_keys)
    assert second["subscription_revenue_usd"] == pytest.approx(first["subscription_revenue_usd"])
    assert second["consultation_revenue_usd"] == pytest.approx(first["consultation_revenue_usd"])
    assert second["gross_revenue_usd"] == pytest.approx(first["gross_revenue_usd"])
    assert db_session.query(Tenant).count() == 5
    assert db_session.query(Branch).count() == 12
    assert db_session.query(Subscription).count() == 55
    assert db_session.query(SubscriptionReceipt).count() == 55
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


def test_seed_does_not_issue_receipt_for_unpaid_subscription(db_session):
    add_roles(db_session)
    seed_demo_businesses(db_session, "Valid-demo-passphrase-2026!", environment="development")

    company = DEMO_COMPANIES[0]
    tenant = db_session.query(Tenant).filter_by(code=company.code).one()
    subscription = db_session.query(Subscription).filter_by(
        tenant_id=tenant.id,
        started_at=datetime(2026, 1, 1),
    ).one()
    receipt = db_session.get(SubscriptionReceipt, subscription.id)
    assert receipt is not None
    assert (receipt.branch_id, receipt.is_sandbox, receipt.paypal_order_id, receipt.paypal_capture_id) == (
        db_session.query(Branch).filter_by(tenant_id=tenant.id, code="PRINCIPAL").one().id,
        True,
        f"DEMO-ORDER-{subscription.id}",
        f"DEMO-CAPTURE-{subscription.id}",
    )
    db_session.delete(receipt)
    subscription.status = "PENDING"
    db_session.flush()

    result = seed_demo_businesses(
        db_session,
        "Valid-demo-passphrase-2026!",
        environment="development",
    )

    assert db_session.get(SubscriptionReceipt, subscription.id) is None
    assert result["subscription_receipts"] == 0
    assert result["subscription_revenue_usd"] == pytest.approx(1319.45 - PLANS[company.plan]["price"])


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
