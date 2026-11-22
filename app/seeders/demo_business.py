"""Idempotent synthetic SaaS and clinic history for browser demos."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy.orm import Session

from app.core.security import get_password_hash
from app.models.appointment import Appointment
from app.models.company import Branch, CompanyAdministrator
from app.models.ai_nutrition import FoodRecord
from app.models.patient_link import PatientNutritionistLink
from app.models.payment import Payment, cash_register_filter
from app.models.recipe import Recipe
from app.models.rbac import Role
from app.models.subscription import Subscription
from app.models.subscription_receipt import SubscriptionReceipt
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.ai_nutrition import FoodRecordCreate
from app.services.consultation_payment_service import ConsultationPaymentService
from app.services.subscription_service import PLANS

PERIOD_START = date(2026, 1, 1)
PERIOD_END = date(2026, 11, 22)


@dataclass(frozen=True)
class DemoCompany:
    code: str
    name: str
    plan: str
    patient_count: int
    branch_names: tuple[str, ...]
    department_code: str = "01"  # Chuquisaca
    province_code: str = "0101"  # Oropeza
    municipality_code: str = "010101"  # Sucre
    address: str = "Sucre, Chuquisaca, Bolivia"


# Branch counts are illustrative sample sizes. The current plan catalogue has
# patient limits, but no per-plan branch limits.
DEMO_COMPANIES = (
    DemoCompany("VIDASANA", "Clínica NutriSalud Vida Sana", "BASICO", 8, ("Sucursal principal",),
                department_code="07", province_code="0701", municipality_code="070101",
                address="Santa Cruz de la Sierra, Santa Cruz, Bolivia"),
    DemoCompany("NUTRIFIT", "Centro NutriFit Sucre", "BASICO", 10, ("Sucursal principal",)),
    DemoCompany("EQUILIBRIO", "Nutrición Equilibrio", "PROFESIONAL", 32,
                ("Sucursal principal", "Sucursal Norte")),
    DemoCompany("ANDINA", "Clínica Andina de Nutrición", "PROFESIONAL", 45,
                ("Sucursal principal", "Sucursal Centro", "Sucursal Sur")),
    DemoCompany("VITALIA", "Centro Integral Vitalia", "PREMIUM", 64,
                ("Sucursal principal", "Sucursal Norte", "Sucursal Centro", "Sucursal Sur", "Sucursal Este")),
)


@dataclass(frozen=True)
class DemoRecipe:
    key: str
    title: str
    description: str
    calories: float
    protein: float
    carbohydrates: float
    fats: float
    fiber: float
    category: str
    prep_time_minutes: int
    ingredients: str
    instructions: str


DEMO_RECIPES = (
    DemoRecipe("avena-fruta", "Avena demo con plátano y chía",
               "Receta ficticia de catálogo general; revisar con un profesional antes de personalizar.",
               350, 12, 57, 9, 9, "Desayuno", 15,
               "Avena, plátano, chía, agua o bebida de preferencia.",
               "Cocer la avena; servir con plátano en rodajas y chía."),
    DemoRecipe("huevo-verduras", "Tortilla demo de verduras",
               "Receta ficticia de catálogo general; revisar con un profesional antes de personalizar.",
               330, 22, 28, 14, 6, "Desayuno", 20,
               "Huevo, tomate, espinaca, cebolla y papa cocida.",
               "Saltear las verduras, añadir el huevo batido y cocinar hasta cuajar."),
    DemoRecipe("pollo-quinoa", "Pollo demo con quinoa y verduras",
               "Receta ficticia de catálogo general; revisar con un profesional antes de personalizar.",
               520, 38, 55, 15, 8, "Almuerzo", 35,
               "Pechuga de pollo, quinoa, zanahoria, tomate y aceite vegetal.",
               "Cocinar la quinoa; asar el pollo y acompañar con verduras cocidas."),
    DemoRecipe("lentejas-arroz", "Guiso demo de lentejas con arroz",
               "Receta ficticia de catálogo general; revisar con un profesional antes de personalizar.",
               480, 22, 75, 8, 16, "Almuerzo", 40,
               "Lentejas, arroz, cebolla, zanahoria, ajo y hierbas.",
               "Cocer lentejas y arroz por separado; preparar un sofrito suave y servir juntos."),
    DemoRecipe("quinua-ensalada", "Ensalada demo de quinua y verduras",
               "Receta ficticia de catálogo general; revisar con un profesional antes de personalizar.",
               410, 14, 63, 11, 10, "Almuerzo", 25,
               "Quinua, pepino, tomate, zanahoria, limón y aceite vegetal.",
               "Enfriar la quinua cocida, mezclar con verduras picadas y aliñar al servir."),
    DemoRecipe("sopa-verduras", "Sopa demo de verduras y papa",
               "Receta ficticia de catálogo general; revisar con un profesional antes de personalizar.",
               300, 9, 52, 7, 8, "Cena", 35,
               "Papa, zapallo, zanahoria, cebolla, agua y hierbas.",
               "Cocer todos los ingredientes hasta que estén tiernos y servir caliente."),
    DemoRecipe("yogur-fruta", "Yogur demo con fruta y avena",
               "Receta ficticia de catálogo general; revisar con un profesional antes de personalizar.",
               290, 13, 45, 7, 6, "Merienda", 5,
               "Yogur natural, fruta de estación y avena.",
               "Servir el yogur con fruta picada y avena; ajustar ingredientes según preferencias."),
    DemoRecipe("fruta-semillas", "Fruta demo con semillas",
               "Receta ficticia de catálogo general; revisar con un profesional antes de personalizar.",
               220, 6, 32, 9, 7, "Snack", 5,
               "Fruta de estación y semillas mixtas.",
               "Lavar y cortar la fruta; servir con una pequeña porción de semillas."),
)

DEMO_MEALS = (
    ("Desayuno", "Registro demo: avena con fruta", 350, 12, 57, 9, 9, 8, 0),
    ("Almuerzo", "Registro demo: pollo con quinua y verduras", 520, 38, 55, 15, 8, 13, 0),
    ("Merienda", "Registro demo: yogur con fruta", 290, 13, 45, 7, 6, 16, 0),
    ("Cena", "Registro demo: lentejas con verduras", 430, 21, 63, 9, 13, 20, 0),
    ("Snack", "Registro demo: fruta de estación", 100, 1, 25, 0, 4, 15, 30),
)

_PATIENT_GIVEN_NAMES = (
    "Alex", "Sam", "Cris", "Noa", "Dani", "Ari", "Luz", "Sol", "René", "Vale",
    "Ángel", "Paz", "Robin", "Mica", "Nico", "Fran",
)
_PATIENT_FAMILY_NAMES = (
    "Demo", "Muestra", "Prueba", "Ejemplo", "Nutrición", "Paciente", "Salud", "Ficticio",
)


def _id(*parts: object) -> str:
    return str(uuid5(NAMESPACE_URL, "nutrisalud-demo-business:" + ":".join(map(str, parts))))


def _utc_naive(value: datetime) -> datetime:
    return value.replace(tzinfo=None) if value.tzinfo else value


def _demo_user(db: Session, *, email: str, full_name: str, role_id: str,
               tenant_id: str, branch_id: str | None, password_hash: str,
               created_at: datetime, report: dict[str, int]) -> User:
    stable_id = _id("user", email)
    user = db.get(User, stable_id)
    by_email = db.query(User).filter(User.email == email).first()
    if by_email and by_email.id != stable_id:
        raise ValueError(f"El correo reservado para demo ya pertenece a otra cuenta: {email}")
    if user:
        if user.tenant_id != tenant_id or user.role_id != role_id:
            raise ValueError(f"La cuenta demo {email} ya existe con una empresa o rol distinto.")
        if branch_id and user.branch_id != branch_id:
            raise ValueError(f"La cuenta demo {email} ya está asignada a otra sucursal.")
        return user

    user = User(
        id=stable_id,
        email=email,
        hashed_password=password_hash,
        full_name=full_name,
        role_id=role_id,
        tenant_id=tenant_id,
        branch_id=branch_id,
        is_active=True,
        is_verified=True,
        created_at=_utc_naive(created_at),
    )
    db.add(user)
    db.flush()
    report["users"] += 1
    return user


def _ensure_tenant(db: Session, company: DemoCompany, report: dict[str, int]) -> Tenant:
    tenant = db.query(Tenant).filter(Tenant.code == company.code).first()
    if tenant:
        if tenant.name != company.name:
            raise ValueError(f"El código de empresa demo {company.code} ya pertenece a otra empresa.")
        if not tenant.is_active:
            raise ValueError(f"La empresa demo {company.code} está inactiva; no se sembró información.")
        # VIDA SANA is created by init_db. Fill only missing geographic data; do
        # not rewrite existing names, activity, contacts, or dates.
        if not tenant.department_code:
            tenant.department_code = company.department_code
        return tenant

    tenant = Tenant(
        id=_id("tenant", company.code),
        name=company.name,
        code=company.code,
        email=f"contacto.{company.code.lower()}@example.test",
        address=company.address,
        department_code=company.department_code,
        description="Empresa de muestra con información ficticia para pruebas.",
        is_active=True,
        created_at=datetime.combine(PERIOD_START, time.min),
    )
    db.add(tenant)
    db.flush()
    report["companies"] += 1
    return tenant


def _ensure_branches(db: Session, tenant: Tenant, company: DemoCompany,
                     report: dict[str, int]) -> list[Branch]:
    # Legacy migrations may already have inserted PRINCIPAL. Reuse it as-is.
    existing = {branch.code: branch for branch in db.query(Branch).filter(Branch.tenant_id == tenant.id).all()}
    selected: list[Branch] = []
    candidate_index = 1
    while len(selected) < len(company.branch_names):
        code = "PRINCIPAL" if candidate_index == 1 else f"SEDE_{candidate_index:02d}"
        name = company.branch_names[len(selected)]
        branch = existing.get(code)
        if branch is None:
            branch = Branch(
                id=_id("branch", company.code, code),
                tenant_id=tenant.id,
                name=name,
                code=code,
                address=company.address,
                province_code=company.province_code,
                municipality_code=company.municipality_code,
                is_active=True,
                created_at=datetime.combine(PERIOD_START, time.min),
            )
            db.add(branch)
            db.flush()
            existing[code] = branch
            report["branches"] += 1
        if branch.is_active:
            selected.append(branch)
        candidate_index += 1
        if candidate_index > len(company.branch_names) + len(existing) + 5:
            raise RuntimeError(f"No se pudo encontrar sucursal activa para {company.code}.")
    return selected


def _ensure_subscriptions(db: Session, tenant: Tenant, branch: Branch,
                          company: DemoCompany, buyer: User,
                          report: dict[str, int]) -> None:
    plan = PLANS.get(company.plan)
    if not plan:
        raise ValueError(f"El plan {company.plan} no existe en SubscriptionService.PLANS.")
    max_patients = plan["max_patients"]
    if max_patients is not None and company.patient_count > max_patients:
        raise ValueError(
            f"{company.code} supera el límite de {max_patients} pacientes del plan {company.plan}."
        )

    # The real service uses successive 30-day paid periods. November is covered
    # by the active period that started on 2026-10-28 and expires 2026-11-27.
    for period_index in range(11):
        started_at = datetime.combine(PERIOD_START, time.min) + timedelta(days=30 * period_index)
        expires_at = started_at + timedelta(days=30)
        status = "ACTIVE" if period_index == 10 else "REPLACED"
        subscription_id = _id("subscription", company.code, period_index + 1)
        existing = db.get(Subscription, subscription_id)
        if existing:
            if (
                existing.tenant_id != tenant.id
                or existing.plan_name != company.plan
                or existing.amount != plan["price"]
                or existing.currency != plan["currency"]
                or existing.started_at != started_at
                or existing.expires_at != expires_at
            ):
                raise ValueError(f"La suscripción demo {subscription_id} ya existe con datos distintos.")
            if existing.user_id not in (None, buyer.id):
                raise ValueError(f"La suscripción demo {subscription_id} está asociada a otro comprador.")
            if existing.user_id is None:
                if existing.paypal_order_id or existing.paypal_capture_id:
                    raise ValueError(
                        f"La suscripción demo {subscription_id} tiene referencias de pago; no se modificó el comprador."
                    )
                # Backfill rows created by the first version of this seeder so
                # the real subscription-history query can find the purchaser.
                existing.user_id = buyer.id
            if not existing.paypal_order_id and not existing.paypal_capture_id and not existing.branch_id:
                # Match the real checkout workspace. Branch scope is applied
                # by the API to subscription history and receipt queries.
                existing.branch_id = buyer.branch_id or branch.id
            continue
        db.add(Subscription(
            id=subscription_id,
            tenant_id=tenant.id,
            branch_id=buyer.branch_id or branch.id,
            user_id=buyer.id,
            plan_name=company.plan,
            status=status,
            amount=plan["price"],
            currency=plan["currency"],
            started_at=started_at,
            expires_at=expires_at,
            created_at=started_at,
        ))
        report["subscriptions"] += 1
    db.flush()


def _ensure_subscription_receipts(db: Session, tenant: Tenant, buyer: User,
                                   company: DemoCompany, report: dict[str, int]) -> None:
    """Create clearly simulated sandbox receipts; never call or impersonate PayPal."""
    for period_index in range(11):
        subscription_id = _id("subscription", company.code, period_index + 1)
        subscription = db.get(Subscription, subscription_id)
        if not subscription:
            raise RuntimeError(f"Falta la suscripción demo {subscription_id} para emitir su recibo de muestra.")
        if subscription.user_id != buyer.id or subscription.tenant_id != tenant.id:
            raise ValueError(f"La suscripción demo {subscription_id} no pertenece a su comprador esperado.")

        existing = db.get(SubscriptionReceipt, subscription.id)
        if existing:
            if (
                existing.user_id != buyer.id
                or existing.tenant_id != tenant.id
                or existing.branch_id != subscription.branch_id
                or existing.plan_name != subscription.plan_name
                or Decimal(str(existing.amount)) != Decimal(str(subscription.amount)).quantize(Decimal("0.01"))
                or existing.currency != subscription.currency
                or existing.is_sandbox is not True
                or not existing.paypal_order_id.startswith("DEMO-ORDER-")
                or not existing.paypal_capture_id.startswith("DEMO-CAPTURE-")
                or existing.paid_at != subscription.started_at
            ):
                raise ValueError(f"El recibo de suscripción demo {subscription_id} ya existe con datos distintos.")
            continue

        # Only paid-like lifecycle states may produce a demo receipt. A
        # pending, failed, or cancelled subscription must not inflate revenue.
        if subscription.status not in {"ACTIVE", "REPLACED", "EXPIRED"}:
            continue

        # DEMO-* references are intentionally not PayPal transaction IDs.
        # is_sandbox makes the PDF say that no real money was collected.
        db.add(SubscriptionReceipt(
            id=subscription.id,
            tenant_id=tenant.id,
            branch_id=subscription.branch_id,
            user_id=buyer.id,
            buyer_name=buyer.full_name,
            buyer_email=buyer.email,
            plan_name=subscription.plan_name,
            amount=Decimal(str(subscription.amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            currency=subscription.currency,
            paypal_order_id=f"DEMO-ORDER-{subscription.id}",
            paypal_capture_id=f"DEMO-CAPTURE-{subscription.id}",
            is_sandbox=True,
            paid_at=subscription.started_at,
            expires_at=subscription.expires_at,
            issued_at=subscription.started_at,
        ))
        report["subscription_receipts"] += 1
    db.flush()


def _ensure_admin(db: Session, tenant: Tenant, branch: Branch, company: DemoCompany,
                  password_hash: str, report: dict[str, int]) -> User:
    admin = _demo_user(
        db,
        email=f"admin.{company.code.lower()}@example.test",
        full_name=f"Administración Demo · {company.name}",
        role_id="ADMIN_ORGANIZATION",
        tenant_id=tenant.id,
        branch_id=branch.id,
        password_hash=password_hash,
        created_at=datetime.combine(PERIOD_START, time.min),
        report=report,
    )
    if not db.query(CompanyAdministrator).filter_by(tenant_id=tenant.id).first():
        if db.query(CompanyAdministrator).filter_by(user_id=admin.id).first():
            raise ValueError(f"La cuenta demo {admin.email} ya administra otra empresa.")
        db.add(CompanyAdministrator(tenant_id=tenant.id, user_id=admin.id))
        db.flush()
    return admin


def _ensure_nutritionists(db: Session, tenant: Tenant, branches: list[Branch],
                          company: DemoCompany, password_hash: str,
                          report: dict[str, int]) -> dict[str, User]:
    result: dict[str, User] = {}
    for index, branch in enumerate(branches, start=1):
        email = f"nutritionist.{company.code.lower()}.{index:02d}@example.test"
        nutritionist = _demo_user(
            db,
            email=email,
            full_name=f"Nutricionista Demo {company.code} {index:02d}",
            role_id="NUTRICIONISTA",
            tenant_id=tenant.id,
            branch_id=branch.id,
            password_hash=password_hash,
            created_at=datetime.combine(PERIOD_START, time.min),
            report=report,
        )
        result[branch.id] = nutritionist
    return result


def _ensure_recipe_catalog(db: Session, tenant: Tenant, nutritionist: User,
                          company: DemoCompany, report: dict[str, int]) -> None:
    plan = PLANS[company.plan]
    has_recipe_feature = any(
        feature["text"] == "Recetario & Macros" and feature["included"]
        for feature in plan["features"]
    )
    if not has_recipe_feature:
        return

    for recipe_index, item in enumerate(DEMO_RECIPES):
        recipe_id = _id("recipe", company.code, item.key)
        existing = db.get(Recipe, recipe_id)
        if existing:
            if existing.tenant_id != tenant.id or existing.title != item.title:
                raise ValueError(f"La receta demo {item.title!r} ya existe con otro contenido.")
            continue
        duplicate_title = db.query(Recipe).filter(
            Recipe.tenant_id == tenant.id,
            Recipe.is_active.is_(True),
            Recipe.title.ilike(item.title),
        ).first()
        if duplicate_title:
            raise ValueError(f"El título de receta reservado ya existe en {company.code}: {item.title}.")
        created_at = datetime(2026, 1 + recipe_index, 3)
        db.add(Recipe(
            id=recipe_id,
            tenant_id=tenant.id,
            branch_id=None,  # Shared company catalog, as in the web recipe flow.
            created_by=nutritionist.id,
            title=item.title,
            description=item.description,
            image_url=None,
            calories=item.calories,
            protein=item.protein,
            carbohydrates=item.carbohydrates,
            fats=item.fats,
            fiber=item.fiber,
            sodium=0,
            servings=1,
            prep_time_minutes=item.prep_time_minutes,
            cook_time_minutes=0,
            difficulty="Fácil",
            category=item.category,
            ingredients=item.ingredients,
            instructions=item.instructions,
            is_active=True,
            created_at=created_at,
            updated_at=created_at,
        ))
        report["recipes"] += 1
    db.flush()


def _ensure_food_diary(db: Session, patient: User, branch: Branch,
                       company: DemoCompany, patient_number: int,
                       joined_month: int, report: dict[str, int]) -> None:
    """Store synthetic self-reported meals in the same shape as /food/records."""
    for month_index in range(joined_month, 11):
        records_this_month = 1 + ((patient_number + month_index) % 2)
        for meal_index in range(records_this_month):
            meal = DEMO_MEALS[(patient_number + month_index + meal_index) % len(DEMO_MEALS)]
            meal_type, description, calories, protein, carbs, fats, fiber, hour, minute = meal
            consumed_at = datetime(
                2026, month_index + 1, 12 + meal_index, hour, minute, tzinfo=timezone.utc
            )
            client_record_id = UUID(_id(
                "food-client-record", company.code, patient_number, month_index + 1, meal_index + 1
            ))
            payload_model = FoodRecordCreate(
                client_record_id=client_record_id,
                description=description,
                meal_type=meal_type,
                consumed_at=consumed_at,
                calories=calories,
                protein_g=protein,
                carbs_g=carbs,
                fats_g=fats,
            )
            payload = payload_model.model_dump(mode="json")
            fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
            record_id = str(uuid5(NAMESPACE_URL, f"food:{patient.id}:{client_record_id}"))
            existing = db.get(FoodRecord, record_id)
            if existing:
                if existing.patient_id != patient.id:
                    raise ValueError(f"El registro de comida demo {record_id} pertenece a otro paciente.")
                continue
            db.add(FoodRecord(
                id=record_id,
                patient_id=patient.id,
                tenant_id=patient.tenant_id,
                branch_id=branch.id,
                image_url=None,
                result_json=json.dumps({"source": "manual", "fingerprint": fingerprint, **payload}),
                estimated_calories=calories,
                estimated_protein=protein,
                estimated_carbs=carbs,
                estimated_fats=fats,
                estimated_fiber=fiber,
                confidence="manual",
                notes=f"{meal_type}: {description}",
                created_at=consumed_at.replace(tzinfo=None),
            ))
            report["food_records"] += 1
    db.flush()


def _ensure_patient_history(db: Session, tenant: Tenant, branches: list[Branch],
                            admin: User, nutritionists: dict[str, User],
                            company: DemoCompany, password_hash: str,
                            report: dict[str, int]) -> None:
    if not branches:
        raise RuntimeError(f"{company.code} necesita al menos una sucursal activa.")

    # Slot counters are branch/month-specific, keeping 30-minute appointments
    # conflict-free and within clinic hours, like AppointmentService.
    slots: dict[tuple[str, int], int] = {}
    for patient_index in range(company.patient_count):
        branch = branches[patient_index % len(branches)]
        nutritionist = nutritionists[branch.id]
        patient_number = patient_index + 1
        patient_email = f"patient.{company.code.lower()}.{patient_number:03d}@example.test"
        given = _PATIENT_GIVEN_NAMES[patient_index % len(_PATIENT_GIVEN_NAMES)]
        family = _PATIENT_FAMILY_NAMES[(patient_index // len(_PATIENT_GIVEN_NAMES)) % len(_PATIENT_FAMILY_NAMES)]
        joined_month = (patient_index * 11) // max(1, company.patient_count - 1) if company.patient_count > 1 else 0
        joined_month = min(joined_month, 10)
        joined_day = 1 + (patient_index % 10)
        joined_at = datetime(2026, joined_month + 1, joined_day)
        patient = _demo_user(
            db,
            email=patient_email,
            full_name=f"{given} {family} {company.code} {patient_number:03d}",
            role_id="CLIENTE",
            tenant_id=tenant.id,
            branch_id=branch.id,
            password_hash=password_hash,
            created_at=joined_at,
            report=report,
        )

        link_id = _id("patient-link", company.code, patient_number)
        if not db.get(PatientNutritionistLink, link_id):
            db.add(PatientNutritionistLink(
                id=link_id,
                tenant_id=tenant.id,
                branch_id=branch.id,
                nutritionist_id=nutritionist.id,
                patient_id=patient.id,
                pairing_code=f"DEMO-{company.code}-{patient_number:03d}",
                whatsapp_number="0000000000",
                status="LINKED",
                notes="Vinculación de demostración; identidad y datos ficticios.",
                created_at=joined_at,
                linked_at=joined_at,
            ))
            report["patient_links"] += 1

        _ensure_food_diary(db, patient, branch, company, patient_number,
                           joined_month, report)

        available_months = 11 - joined_month
        visit_count = min(1 + (patient_index % 4), available_months)
        for visit_index in range(visit_count):
            if visit_count == 1:
                visit_month = joined_month
            else:
                visit_month = joined_month + ((available_months - 1) * visit_index // (visit_count - 1))
            slot_key = (branch.id, visit_month)
            slot = slots.get(slot_key, 0)
            slots[slot_key] = slot + 1
            scheduled_at = datetime(2026, visit_month + 1, 12 + slot // 18,
                                    8 + (slot % 18) // 2, 30 if slot % 2 else 0)
            # A late-November slot remains within the requested historical range.
            if scheduled_at.date() > PERIOD_END:
                scheduled_at = scheduled_at.replace(day=PERIOD_END.day)
            appointment_id = _id("appointment", company.code, patient_number, visit_index + 1)
            appointment = db.get(Appointment, appointment_id)
            if not appointment:
                appointment = Appointment(
                    id=appointment_id,
                    tenant_id=tenant.id,
                    branch_id=branch.id,
                    patient_id=patient.id,
                    nutritionist_id=nutritionist.id,
                    scheduled_at=scheduled_at,
                    reason="Control nutricional de seguimiento",
                    status="COMPLETED",
                    completed_at=scheduled_at + timedelta(minutes=30),
                    created_at=scheduled_at - timedelta(days=1),
                    updated_at=scheduled_at + timedelta(minutes=30),
                )
                db.add(appointment)
                report["appointments"] += 1

            payment_id = _id("consultation-payment", company.code, patient_number, visit_index + 1)
            if not db.get(Payment, payment_id):
                paid_at = (scheduled_at - timedelta(minutes=15)).replace(tzinfo=timezone.utc)
                db.add(Payment(
                    id=payment_id,
                    tenant_id=tenant.id,
                    branch_id=branch.id,
                    cashier_id=admin.id,
                    patient_id=patient.id,
                    appointment_id=appointment_id,
                    purpose="CONSULTATION",
                    customer_name=patient.full_name,
                    customer_email=patient.email,
                    concept="Consulta general",
                    amount=ConsultationPaymentService.CONSULTATION_FEE_USD,
                    currency="USD",
                    status="COMPLETED",
                    payment_method="EFECTIVO",
                    notes="Cobro sintético en efectivo para datos de demostración.",
                    created_at=paid_at - timedelta(minutes=15),
                    paid_at=paid_at,
                ))
                report["payments"] += 1
    db.flush()


def _demo_revenue_summary(db: Session) -> dict[str, float]:
    """Summarize only stable demo rows, separating SaaS sales from clinic cash."""
    subscription_ids: list[str] = []
    payment_ids: list[str] = []
    for company in DEMO_COMPANIES:
        subscription_ids.extend(
            _id("subscription", company.code, period_index + 1)
            for period_index in range(11)
        )
        for patient_index in range(company.patient_count):
            patient_number = patient_index + 1
            joined_month = (
                (patient_index * 11) // (company.patient_count - 1)
                if company.patient_count > 1 else 0
            )
            joined_month = min(joined_month, 10)
            available_months = 11 - joined_month
            visit_count = min(1 + (patient_index % 4), available_months)
            payment_ids.extend(
                _id("consultation-payment", company.code, patient_number, visit_index + 1)
                for visit_index in range(visit_count)
            )

    receipts = db.query(SubscriptionReceipt).filter(
        SubscriptionReceipt.id.in_(subscription_ids)
    ).all()
    payments = db.query(Payment).filter(
        Payment.id.in_(payment_ids),
        Payment.status == "COMPLETED",
        cash_register_filter(),
    ).all()
    subscription_revenue = sum((Decimal(str(row.amount)) for row in receipts), Decimal("0.00"))
    consultation_revenue = sum((Decimal(str(row.amount)) for row in payments), Decimal("0.00"))
    gross_revenue = subscription_revenue + consultation_revenue
    return {
        "subscription_revenue_usd": float(subscription_revenue.quantize(Decimal("0.01"))),
        "consultation_revenue_usd": float(consultation_revenue.quantize(Decimal("0.01"))),
        "gross_revenue_usd": float(gross_revenue.quantize(Decimal("0.01"))),
    }


def seed_demo_businesses(db: Session, password: str, *, environment: str,
                         allow_production: bool = False) -> dict[str, int | float]:
    """Seed five fictional companies and Jan-Nov 2026 history, safely repeatable."""
    if not password or not password.strip():
        raise ValueError("Define una contraseña no vacía para crear las cuentas demo.")
    if environment.strip().lower() in {"production", "prod"} and not allow_production:
        raise RuntimeError("Se bloqueó el seeder en producción; usa --allow-production de forma explícita.")

    expected_roles = {"ADMIN_ORGANIZATION", "NUTRICIONISTA", "CLIENTE"}
    actual_roles = {row[0] for row in db.query(Role.id).filter(Role.id.in_(expected_roles)).distinct().all()}
    if actual_roles != expected_roles:
        missing = ", ".join(sorted(expected_roles - actual_roles))
        raise RuntimeError(f"Faltan roles requeridos ({missing}). Ejecuta primero prepare_db.py.")

    report = {
        "companies": 0, "branches": 0, "users": 0, "patient_links": 0,
        "subscriptions": 0, "subscription_receipts": 0,
        "appointments": 0, "payments": 0,
        "recipes": 0, "food_records": 0,
    }
    password_hash = get_password_hash(password)
    try:
        for company in DEMO_COMPANIES:
            tenant = _ensure_tenant(db, company, report)
            branches = _ensure_branches(db, tenant, company, report)
            admin = _ensure_admin(db, tenant, branches[0], company, password_hash, report)
            _ensure_subscriptions(db, tenant, branches[0], company, admin, report)
            _ensure_subscription_receipts(db, tenant, admin, company, report)
            nutritionists = _ensure_nutritionists(db, tenant, branches, company, password_hash, report)
            _ensure_recipe_catalog(db, tenant, nutritionists[branches[0].id], company, report)
            _ensure_patient_history(db, tenant, branches, admin, nutritionists, company,
                                    password_hash, report)
        db.flush()
        report.update(_demo_revenue_summary(db))
        db.commit()
    except Exception:
        db.rollback()
        raise
    return report
