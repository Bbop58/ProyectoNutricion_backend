"""Synthetic clinical fixtures. Never invokes AI or sends notifications/emails."""
from datetime import datetime, time, timedelta
import json
from uuid import NAMESPACE_URL, uuid5

from app.models.ai_nutrition import NutritionalPlan
from app.models.care import CareMessage, Measurement, NutritionConfiguration
from app.models.clinical import ClinicalRecord, PatientAnamnesis
from app.schemas.care import NutritionValues
from app.schemas.clinical import AnamnesisCreateOrUpdate


def stable(*parts):
    return str(uuid5(NAMESPACE_URL, "nutrisalud-demo-care:" + ":".join(map(str, parts))))


# Eight deliberately distinct adult profiles; these are not real medical records.
PROFILES = (
    ("Pérdida de grasa", "", "", "Moderado", "Verduras, quinoa", ""),
    ("Masa muscular", "", "", "Intenso", "Pollo, arroz", ""),
    ("Salud general", "", "Lactosa", "Ligero", "Fruta, avena", ""),
    ("Salud general", "Enfermedad celíaca", "Gluten", "Moderado", "Arroz, quinoa", ""),
    ("Control de peso", "Hipertensión", "", "Sedentario", "Verduras, legumbres", ""),
    ("Salud general", "Diabetes tipo 2", "", "Ligero", "Verduras, lentejas", ""),
    ("Salud general", "", "Maní, nueces", "Moderado", "Vegetariana; rechaza carnes y pescado", ""),
    ("Salud general", "", "Huevo, pescado", "Ligero", "Pollo, papa", "Reflujo"),
)


def ensure_demo_configuration(db, tenant, admin, report):
    if db.query(NutritionConfiguration.id).filter_by(tenant_id=tenant.id).first():
        return
    db.add(NutritionConfiguration(
        id=stable("configuration", tenant.id), tenant_id=tenant.id, version=1,
        values=NutritionValues().model_dump(), actor_id=admin.id,
        reason="DEMO SINTÉTICO: configuración inicial para probar CU22.",
        created_at=datetime(2026, 1, 1, 12),
    ))
    report["nutrition_configurations"] += 1


def ensure_demo_patient_care(db, patient, nutritionist, patient_number, joined_at, period_end, report):
    identity = stable("anamnesis", patient.id)
    anamnesis = db.query(PatientAnamnesis).filter_by(patient_id=patient.id).first()
    if anamnesis and anamnesis.id != identity:
        # A manually entered ficha is authoritative: do not invent its history.
        report["preserved_anamneses"] += 1
        return
    goal, pathologies, allergies, activity, preferences, digestive = PROFILES[(patient_number - 1) % len(PROFILES)]
    end = datetime.combine(period_end, time(12))
    span = end - joined_at
    dates = [joined_at + span * fraction for fraction in (0, .5, 1)]
    height = 155.0 + patient_number % 26
    initial_weight = 62.0 + patient_number % 31
    delta = 1.2 if goal == "Masa muscular" else (-1.8 if "peso" in goal or "grasa" in goal else -.3)
    weights = [round(initial_weight + delta * fraction, 1) for fraction in (0, .5, 1)]
    if anamnesis is None:
        body = AnamnesisCreateOrUpdate(
            birth_date=datetime(1970 + patient_number % 30, 6, 15),
            gender="F" if patient_number % 2 == 0 else "M",
            weight_kg=weights[-1], height_cm=height,
            target_weight_kg=round(weights[-1] + (2 if goal == "Masa muscular" else -2), 1),
            target_weeks=12, pathologies=pathologies, allergies=allergies,
            medications="DEMO SINTÉTICO: sin medicación registrada para esta prueba.",
            food_preferences=preferences, physical_activity=activity,
            digestive_symptoms=digestive, goal=goal, water_intake_liters=1.2 + (patient_number % 4) * .4,
            sleep_hours=6 + patient_number % 3, coffee_cups=patient_number % 3,
            fruits_vegetables_daily=2 + patient_number % 4,
            sugary_drinks_weekly=patient_number % 5, meals_per_day=4,
            consent_data_processing=True,
        )
        anamnesis = PatientAnamnesis(
            id=identity, patient_id=patient.id, tenant_id=patient.tenant_id,
            branch_id=patient.branch_id, **body.model_dump(), created_at=dates[0], updated_at=end,
        )
        db.add(anamnesis)
        report["anamneses"] += 1
    for index, (measured_at, weight) in enumerate(zip(dates, weights)):
        measurement_id = stable("measurement", patient.id, index)
        if not db.get(Measurement, measurement_id):
            db.add(Measurement(id=measurement_id, tenant_id=patient.tenant_id, patient_id=patient.id,
                               actor_id=nutritionist.id, weight_kg=weight, height_cm=height,
                               measured_at=measured_at, created_at=measured_at))
            report["measurements"] += 1
    record_id = stable("clinical-record", patient.id)
    if not db.get(ClinicalRecord, record_id):
        db.add(ClinicalRecord(
            id=record_id, tenant_id=patient.tenant_id, branch_id=patient.branch_id,
            patient_id=patient.id, nutritionist_id=nutritionist.id,
            diagnosis="DEMO SINTÉTICO: ficha educativa ficticia; no constituye diagnóstico real.",
            clinical_goals="DEMO: " + goal,
            evolution_notes="Historia ficticia para CU19. Condiciones simuladas: " + (pathologies or "ninguna") +
                            ". Revisar alergias y preferencias antes de personalizar recetas.",
            created_at=end, updated_at=end,
        ))
        report["clinical_records"] += 1
    plan_id = stable("draft-plan", patient.id)
    # Do not recreate a seed draft after the professional approved/rejected it.
    if not db.get(NutritionalPlan, plan_id) and not db.query(NutritionalPlan.id).filter_by(patient_id=patient.id, status="DRAFT").first():
        meals = [dict(meal_name=name, time_suggestion=hour, total_calories=500,
                      foods=[dict(name="Arroz integral, lentejas, zapallo y aceite vegetal (demo)",
                                  portion="400 g de preparación ficticia", calories=500,
                                  protein_g=20, carbs_g=80, fats_g=11)])
                 for name, hour in [("Desayuno", "08:00"), ("Almuerzo", "12:30"), ("Merienda", "16:00"), ("Cena", "19:30")]]
        db.add(NutritionalPlan(
            id=plan_id, tenant_id=patient.tenant_id, branch_id=patient.branch_id,
            patient_id=patient.id, nutritionist_id=nutritionist.id, status="DRAFT",
            title="DEMO SINTÉTICO — borrador para revisar (CU20)", goal=goal,
            daily_calories=2000, protein_g=80, carbs_g=320, fats_g=44, meals_per_day=4,
            meals_json=json.dumps(meals, ensure_ascii=False), requires_special_review=True,
            clinical_notes="DEMO SINTÉTICO: plantilla repetida deliberadamente para corregir, rechazar o aprobar en CU20. "
                           "No fue generada por Gemini ni revisada por un profesional. Revisar porciones, variedad y restricciones antes de aprobar.",
            created_at=end, updated_at=end,
        ))
        report["draft_plans"] += 1
    for index, (sender, recipient, content) in enumerate((
        (patient.id, nutritionist.id, "DEMO SINTÉTICO CU21: quisiera revisar mi alimentación y mis registros de comidas."),
        (nutritionist.id, patient.id, "DEMO SINTÉTICO CU21: recibí tu consulta; revisaremos tu ficha y preferencias en la próxima atención."),
    )):
        message_id = stable("message", patient.id, index)
        if not db.get(CareMessage, message_id):
            db.add(CareMessage(id=message_id, tenant_id=patient.tenant_id, sender_id=sender,
                               recipient_id=recipient, content=content, created_at=end + timedelta(minutes=index)))
            report["care_messages"] += 1
