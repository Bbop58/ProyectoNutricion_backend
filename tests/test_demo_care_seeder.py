import json
from pathlib import Path

from app.models.ai_nutrition import NutritionalPlan
from app.models.care import CareMessage, Measurement, NutritionConfiguration
from app.models.clinical import ClinicalRecord, PatientAnamnesis
from app.models.rbac import Role
from app.models.recipe import Recipe
from app.models.user import User
from app.schemas.ai_nutrition import MealItem
from app.schemas.clinical import AnamnesisResponse
from app.seeders.demo_business import PERIOD_END, seed_demo_businesses
from app.seeders.demo_care import PROFILES, stable
from app.services.care_communication_service import thread


def seed(db):
    if not db.get(Role, "CLIENTE"):
        db.add_all([Role(id=role, name=role, description="Demo", platform="Web")
                    for role in ("CLIENTE", "NUTRICIONISTA", "ADMIN_ORGANIZATION")])
        db.commit()
    return seed_demo_businesses(db, "Demo-fixtures-2026!", environment="test")


def test_care_fixtures_cover_all_companies_patients_and_branches(db_session):
    db = db_session
    counts = seed(db)
    assert counts["anamneses"] == 159
    assert counts["measurements"] == 477
    assert counts["clinical_records"] == counts["draft_plans"] == 159
    assert counts["care_messages"] == 318
    assert counts["nutrition_configurations"] == 5
    assert counts["recipes"] == 96
    branches = set()
    profiles = set()
    for patient in db.query(User).filter_by(role_id="CLIENTE"):
        branches.add(patient.branch_id)
        anamnesis = db.query(PatientAnamnesis).filter_by(patient_id=patient.id).one()
        AnamnesisResponse.model_validate(anamnesis)
        profiles.add((anamnesis.goal, anamnesis.allergies, anamnesis.pathologies))
        assert anamnesis.tenant_id == patient.tenant_id
        assert anamnesis.branch_id == patient.branch_id
        assert "DEMO SINTÉTICO" in anamnesis.medications
        measurements = db.query(Measurement).filter_by(patient_id=patient.id).order_by(Measurement.measured_at).all()
        assert len(measurements) == 3
        assert len({row.measured_at for row in measurements}) == 3
        assert measurements[-1].weight_kg == anamnesis.weight_kg
        for row in measurements:
            assert patient.created_at <= row.measured_at
            assert row.measured_at.date() <= PERIOD_END
            assert row.tenant_id == patient.tenant_id
            professional = db.get(User, row.actor_id)
            assert (professional.tenant_id, professional.branch_id) == (patient.tenant_id, patient.branch_id)
        clinical = db.query(ClinicalRecord).filter_by(patient_id=patient.id).one()
        assert "ficticia" in clinical.diagnosis
        plan = db.query(NutritionalPlan).filter_by(patient_id=patient.id).one()
        assert plan.status == "DRAFT" and plan.approved_at is None
        assert plan.requires_special_review is True
        meals = [MealItem.model_validate(item) for item in json.loads(plan.meals_json)]
        assert len(meals) == plan.meals_per_day == 4
        assert sum(item.total_calories for item in meals) == plan.daily_calories
        specialist = db.get(User, plan.nutritionist_id)
        assert specialist.branch_id == patient.branch_id
        conversation = thread(db, patient, specialist.id)
        assert len(conversation["items"]) == 2
        assert all("DEMO SINTÉTICO" in item["content"] for item in conversation["items"])
    assert len(branches) == 12
    assert len(profiles) == len(PROFILES)
    assert db.query(CareMessage).count() == 318
    # Prove the supplied CSV works with the real preview/confirmation services.
    from app.schemas.care import ImportIn
    from app.services.care_communication_service import preview_import, confirm_import
    admin = db.query(User).filter_by(email="admin.vitalia@example.test").one()
    csv_path = Path(__file__).resolve().parents[1] / "docs/fixtures/importacion_cu23_vitalia.csv"
    preview = preview_import(db, admin, ImportIn(csv_content=csv_path.read_text(encoding="utf-8"), branch_id=admin.branch_id))
    assert (preview["accepted"], preview["rejected"]) == (2, 2)
    imported = confirm_import(db, admin, preview["batch_id"])
    assert imported["created"] == 2 and imported["rejected"] == 2
    assert confirm_import(db, admin, preview["batch_id"]) == imported


def test_reseed_preserves_professional_edits_and_existing_clinical_data(db_session):
    db = db_session
    seed(db)
    patient = db.query(User).filter_by(email="patient.vitalia.001@example.test").one()
    anamnesis = db.query(PatientAnamnesis).filter_by(patient_id=patient.id).one()
    # Simulate an existing manual ficha replacing the seeded one.
    anamnesis.id = "manual-authoritative-anamnesis"
    anamnesis.allergies = "Dato registrado manualmente"
    plan = db.get(NutritionalPlan, stable("draft-plan", patient.id))
    plan.status = "REJECTED"
    plan.clinical_notes = "Decisión posterior del profesional"
    config = db.query(NutritionConfiguration).filter_by(tenant_id=patient.tenant_id).one()
    config.values = {**config.values, "water_liters": 2.5}
    config.reason = "Cambio profesional que debe conservarse"
    recipe = db.query(Recipe).filter_by(tenant_id=patient.tenant_id).first()
    recipe.instructions = "Instrucciones corregidas manualmente"
    db.commit()
    result = seed(db)
    assert result["preserved_anamneses"] == 1
    for name in ("anamneses", "measurements", "clinical_records", "draft_plans", "care_messages", "nutrition_configurations", "recipes"):
        assert result[name] == 0
    assert anamnesis.allergies == "Dato registrado manualmente"
    assert plan.status == "REJECTED" and plan.clinical_notes == "Decisión posterior del profesional"
    assert config.values["water_liters"] == 2.5
    assert recipe.instructions == "Instrucciones corregidas manualmente"
    assert db.query(Measurement).count() == 477
    assert db.query(NutritionalPlan).count() == 159


def test_new_recipes_have_explicit_ingredients_sodium_and_no_external_side_effects(db_session, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Seeding must not call an external API")
    from app.services.gemini_service import GeminiService
    from app.services.paypal_service import PayPalService
    monkeypatch.setattr(GeminiService, "generate_text", forbidden)
    monkeypatch.setattr(PayPalService, "get_order", forbidden)
    seed(db_session)
    recipes = db_session.query(Recipe).all()
    assert len(recipes) == 96
    new = [recipe for recipe in recipes if "nutrientes estimados" in recipe.description]
    assert len(new) == 72
    assert all(recipe.sodium > 0 and " g" in recipe.ingredients and recipe.branch_id is None for recipe in new)
    assert len({recipe.category for recipe in recipes}) == 5
    assert all(recipe.created_at.date() <= PERIOD_END for recipe in recipes)
    from app.models.notification import Notification
    assert db_session.query(Notification).count() == 0
