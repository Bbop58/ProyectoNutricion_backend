"""Authorized, local patient/recipe actions; the model never supplies record IDs."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
import unicodedata
from uuid import NAMESPACE_URL, uuid4, uuid5

from fastapi import HTTPException
from jose import JWTError, jwt
from sqlalchemy import or_, select

from app.config import settings
from app.core.workspace import current
from app.models.activity_log import ActivityLog
from app.models.clinical import PatientAnamnesis
from app.models.company import Branch
from app.models.patient_link import PatientNutritionistLink
from app.models.recipe import Recipe, RecipeAssignment
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.staff_assistant import AssistantIntent
from app.services import staff_gemini

HELP = 'Puedo buscar pacientes y recomendar recetas de tu catálogo según su ficha, indicando paciente y tipo de comida. Las preferencias y restricciones adicionales se toman de la anamnesis. Primero revisas la propuesta y después confirmas la asignación. Citas, mensajes, reportes y pagos todavía no se ejecutan desde Carlitos.'
ALLERGENS = {
    'gluten': ('gluten', 'trigo', 'pan', 'pasta', 'fideo', 'fideos', 'cebada', 'centeno', 'avena'),
    'lactosa': ('lactosa', 'leche', 'lacteo', 'lacteos', 'queso', 'yogur', 'yogurt', 'crema', 'mantequilla'),
    'huevo': ('huevo', 'huevos'),
    'mani': ('mani', 'cacahuete', 'cacahuetes', 'cacahuate'),
    'nueces': ('nuez', 'nueces', 'almendra', 'almendras', 'avellana', 'avellanas', 'frutos secos'),
    'pescado': ('pescado', 'pescados', 'atun', 'salmon', 'sardina', 'sardinas'),
    'mariscos': ('marisco', 'mariscos', 'camaron', 'camarones', 'langostino', 'mejillon'),
    'soja': ('soja', 'soya', 'tofu'),
    'sesamo': ('sesamo', 'ajonjoli', 'tahini'),
}
NO_ALLERGIES = {'', 'no', 'ninguna', 'ninguno', 'sin alergias', 'ninguna conocida', 'sin alergias conocidas', 'no presenta alergias'}
MEAT = ('pollo', 'carne', 'res', 'cerdo', 'pavo', 'jamon', 'pescado', 'atun', 'salmon', 'mariscos', 'camaron')


def normal(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', value or '').lower() if not unicodedata.combining(c)).strip()


def mentions(text, phrase):
    return bool(re.search(r'(?<!\w)' + re.escape(phrase) + r'(?!\w)', text))


def scope_for(db, actor):
    if actor.role_id not in {'ADMIN_ORGANIZATION', 'NUTRICIONISTA'} or not actor.is_active:
        raise HTTPException(403, 'Carlitos profesional está disponible para administradores de empresa y nutricionistas.')
    scope = current(db)
    tenant_id = actor.tenant_id
    branch_id = scope.branch_id if scope else (actor.workspace_branch_id or actor.branch_id)
    if scope and scope.tenant_id != tenant_id:
        raise HTTPException(403, 'Selecciona una sucursal de tu empresa.')
    branch = db.query(Branch).filter_by(id=branch_id, tenant_id=tenant_id, is_active=True).first()
    tenant = db.query(Tenant).filter_by(id=tenant_id, is_active=True).first()
    if not branch or not tenant:
        raise HTTPException(403, 'Selecciona una empresa y sucursal activas.')
    return tenant_id, branch_id


def patient_query(db, actor):
    tenant_id, branch_id = scope_for(db, actor)
    query = db.query(User).filter(User.tenant_id == tenant_id, User.branch_id == branch_id,
                                  User.role_id == 'CLIENTE', User.is_active.is_(True))
    if actor.role_id == 'NUTRICIONISTA':
        links = select(PatientNutritionistLink.patient_id).where(
            PatientNutritionistLink.tenant_id == tenant_id, PatientNutritionistLink.branch_id == branch_id,
            PatientNutritionistLink.nutritionist_id == actor.id, PatientNutritionistLink.status == 'LINKED',
        )
        query = query.filter(User.id.in_(links))
    return query


def patient_summary(patient):
    return dict(id=patient.id, full_name=patient.full_name)


def search_patients(db, actor, search='', offset=0):
    query = patient_query(db, actor)
    for word in search.strip().split()[:6]:
        query = query.filter(User.full_name.ilike('%' + word.replace('%', '\\%').replace('_', '\\_') + '%', escape='\\'))
    rows = query.order_by(User.full_name, User.id).offset(offset).limit(11).all()
    return dict(patients=[patient_summary(p) for p in rows[:10]], has_more=len(rows) > 10)


def authorized_patient(db, actor, patient_id, lock=False):
    query = patient_query(db, actor).filter(User.id == patient_id)
    if lock:
        query = query.with_for_update()
    patient = query.first()
    if not patient:
        raise HTTPException(404, 'Paciente no disponible en tu sucursal o sin vinculación autorizada.')
    return patient


def profile_for(db, patient, lock=False):
    query = db.query(PatientAnamnesis).filter_by(patient_id=patient.id, tenant_id=patient.tenant_id)
    if lock:
        query = query.with_for_update()
    profile = query.first()
    if not profile:
        raise HTTPException(422, 'Este paciente todavía no tiene anamnesis. Completa su ficha antes de pedir recomendaciones.')
    if not profile.consent_data_processing:
        raise HTTPException(403, 'La ficha no tiene autorización para procesar sus datos de salud.')
    return profile


def fingerprint(row, fields):
    body = {field: getattr(row, field) for field in fields}
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=str, ensure_ascii=False).encode()).hexdigest()


PROFILE_FIELDS = ('id', 'goal', 'allergies', 'other_allergies', 'pathologies', 'other_pathologies',
                  'food_preferences', 'digestive_symptoms', 'medications', 'weight_kg', 'height_cm',
                  'is_pregnant_or_lactating', 'consent_data_processing', 'updated_at')
RECIPE_FIELDS = ('id', 'tenant_id', 'branch_id', 'title', 'ingredients', 'instructions', 'category',
                 'calories', 'protein', 'carbohydrates', 'fats', 'fiber', 'sodium', 'servings', 'is_active', 'updated_at')


def allergy_groups(profile):
    groups, unknown = set(), []
    for source in (profile.allergies, profile.other_allergies):
        text = normal(source)
        if text in NO_ALLERGIES:
            continue
        for token in re.split(r'[,;\n]|\s+y\s+', text):
            token = token.strip()
            if token in NO_ALLERGIES:
                continue
            matches = {group for group, aliases in ALLERGENS.items() if any(mentions(token, alias) for alias in aliases)}
            if not matches:
                unknown.append(token)
            groups.update(matches)
    if any(word in normal((profile.pathologies or '') + ' ' + (profile.other_pathologies or '')) for word in ('celiac', 'celiaqu')):
        groups.add('gluten')
    return groups, unknown


def evaluate_recipe(recipe, profile):
    groups, unknown = allergy_groups(profile)
    if unknown:
        return None
    ingredients = normal(recipe.ingredients)
    if any(mentions(ingredients, alias) for group in groups for alias in ALLERGENS[group]):
        return None
    # Mixtures or optional ingredients cannot establish compatibility with an allergy.
    if groups and any(phrase in ingredients for phrase in ('mixtas', 'mixtos', 'de preferencia', 'opcional')):
        return None
    preferences = normal(profile.food_preferences)
    vegetarian = 'vegetarian' in preferences or 'vegan' in preferences
    if vegetarian and any(mentions(ingredients, word) for word in MEAT):
        return None
    if 'vegan' in preferences and any(mentions(ingredients, word) for word in ALLERGENS['lactosa'] + ALLERGENS['huevo'] + ('miel',)):
        return None
    pathologies = normal((profile.pathologies or '') + ' ' + (profile.other_pathologies or ''))
    if 'hipertens' in pathologies and (not recipe.sodium or recipe.sodium > 400):
        return None
    goal = normal(profile.goal)
    score, reasons, warnings = 0, [], []
    if ('muscul' in goal or 'volumen' in goal) and recipe.protein >= 25:
        score += 4
        reasons.append(f'Aporta {recipe.protein:g} g de proteína por porción.')
    if any(word in goal for word in ('grasa', 'peso', 'perdida')) and recipe.calories <= 450:
        score += 3
        reasons.append(f'Porción de {recipe.calories:g} kcal para revisar dentro de su objetivo.')
    if recipe.fiber >= 5:
        score += 1
        reasons.append(f'Aporta {recipe.fiber:g} g de fibra.')
    if vegetarian:
        reasons.append('Ingredientes acordes a su preferencia vegetariana.')
    if 'hipertens' in pathologies:
        reasons.append(f'Sodio declarado: {recipe.sodium:g} mg por porción.')
    if 'diabet' in pathologies:
        warnings.append(f'Revisar porción y carbohidratos ({recipe.carbohydrates:g} g) según el control del paciente.')
    if normal(profile.digestive_symptoms):
        warnings.append('Revisar tolerancia digestiva y preparación con el paciente.')
    if profile.is_pregnant_or_lactating:
        warnings.append('Requiere valoración profesional específica por embarazo o lactancia.')
    if profile.allergies is None:
        warnings.append('Alergias sin informar: comprobar antes de asignar.')
    if not reasons:
        reasons.append('Receta del catálogo de tu empresa; revisar porción y objetivo.')
    return score, reasons[:3], warnings[:3]


def proposal_token(actor, patient, recipe, profile, branch_id):
    payload = dict(type='staff_recipe_proposal', sub=actor.id, sv=actor.session_version or 0,
                   jti=str(uuid4()),
                   tenant=patient.tenant_id, branch=branch_id, patient=patient.id, recipe=recipe.id,
                   profile_hash=fingerprint(profile, PROFILE_FIELDS), recipe_hash=fingerprint(recipe, RECIPE_FIELDS),
                   exp=datetime.now(timezone.utc) + timedelta(minutes=5))
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def recommendations(db, actor, patient, meal='', excluded=()):
    tenant_id, branch_id = scope_for(db, actor)
    profile = profile_for(db, patient)
    _, unknown = allergy_groups(profile)
    if unknown:
        return dict(kind='recipes', patient=patient_summary(patient), meal=meal, recipes=[],
                    message='La ficha contiene alergias que no puedo interpretar con certeza. Revisa esos datos y los ingredientes manualmente antes de asignar una receta.')
    query = db.query(Recipe).filter(Recipe.tenant_id == tenant_id, Recipe.is_active.is_(True),
                                    or_(Recipe.branch_id == branch_id, Recipe.branch_id.is_(None)))
    if meal:
        query = query.filter(Recipe.category == meal)
    if excluded:
        query = query.filter(Recipe.id.notin_(excluded))
    recipes = query.order_by(Recipe.title, Recipe.id).limit(100).all()
    assigned = {
        row[0] for row in db.query(RecipeAssignment.recipe_id).filter_by(patient_id=patient.id).all()
    }
    ranked = []
    for recipe in recipes:
        evaluation = evaluate_recipe(recipe, profile)
        if evaluation is not None and recipe.id not in assigned:
            ranked.append((recipe, evaluation))
    ranked.sort(key=lambda item: (-item[1][0], item[0].title))
    proposals = [dict(id=recipe.id, title=recipe.title, image_url=recipe.image_url, category=recipe.category,
                      ingredients=recipe.ingredients, instructions=recipe.instructions, servings=recipe.servings,
                      calories=recipe.calories, protein=recipe.protein, carbohydrates=recipe.carbohydrates,
                      fats=recipe.fats, reasons=evaluation[1], warnings=evaluation[2],
                      proposal_token=proposal_token(actor, patient, recipe, profile, branch_id))
                 for recipe, evaluation in ranked[:3]]
    return dict(kind='recipes', patient=patient_summary(patient), meal=meal, recipes=proposals,
                profile=dict(goal=profile.goal, allergies=profile.allergies, pathologies=profile.pathologies,
                             preferences=profile.food_preferences),
                message=(f'Te propongo {len(proposals)} opciones para {patient.full_name}. Revisa ingredientes, porción y ficha antes de confirmar.'
                         if proposals else 'No encontré otras recetas disponibles que cumplan los filtros. Revisa el catálogo, la categoría o las restricciones del paciente.'))


def query(db, actor, body):
    scope_for(db, actor)
    selected = authorized_patient(db, actor, body.patient_id) if body.patient_id else None
    if body.intent:
        intent, usage = AssistantIntent(action=body.intent, meal=body.meal), dict(engine='local', total_tokens=0)
    else:
        intent, usage = staff_gemini.interpret(body.message, actor.id, actor.tenant_id)
    if intent.action == 'help':
        return dict(kind='help', message=HELP, usage=usage)
    name = intent.patient_name.strip()
    if name and (not selected or not all(mentions(normal(selected.full_name), word) for word in normal(name).split())):
        results = search_patients(db, actor, name)
        if intent.action == 'patients' or len(results['patients']) != 1 or results['has_more']:
            return dict(kind='patients', message='Selecciona el paciente correcto.' if results['patients'] else 'No encontré pacientes autorizados con ese nombre en esta sucursal.',
                        **results, pending_action=intent.action, meal=intent.meal, usage=usage)
        selected = authorized_patient(db, actor, results['patients'][0]['id'])
    if intent.action == 'patients' or not selected:
        return dict(kind='patients', message='Selecciona un paciente para continuar.', **search_patients(db, actor, name),
                    pending_action=intent.action, meal=intent.meal, usage=usage)
    return dict(**recommendations(db, actor, selected, intent.meal, body.exclude_recipe_ids), usage=usage)


def confirm(db, actor, token):
    tenant_id, branch_id = scope_for(db, actor)
    try:
        data = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        raise HTTPException(409, 'La propuesta venció o no es válida. Pide una nueva recomendación.') from None
    if any((not data.get('jti'), data.get('type') != 'staff_recipe_proposal', data.get('sub') != actor.id,
            data.get('sv') != (actor.session_version or 0), data.get('tenant') != tenant_id, data.get('branch') != branch_id)):
        raise HTTPException(403, 'La propuesta pertenece a otro profesional o espacio de trabajo.')
    patient = authorized_patient(db, actor, data.get('patient'), lock=True)
    recipe = db.query(Recipe).filter(Recipe.id == data.get('recipe'), Recipe.tenant_id == tenant_id,
                                     Recipe.is_active.is_(True), or_(Recipe.branch_id == branch_id, Recipe.branch_id.is_(None))).with_for_update().first()
    if not recipe:
        raise HTTPException(409, 'La receta ya no está disponible. Pide una nueva recomendación.')
    profile = profile_for(db, patient, lock=True)
    if (fingerprint(profile, PROFILE_FIELDS) != data.get('profile_hash') or fingerprint(recipe, RECIPE_FIELDS) != data.get('recipe_hash')
            or evaluate_recipe(recipe, profile) is None):
        raise HTTPException(409, 'La ficha o la receta cambiaron. Revisa una nueva propuesta antes de asignar.')
    existing = db.query(RecipeAssignment).filter_by(recipe_id=recipe.id, patient_id=patient.id).first()
    audit_id = str(uuid5(NAMESPACE_URL, 'staff-recipe-proposal:' + data['jti']))
    if not existing and db.get(ActivityLog, audit_id):
        raise HTTPException(409, 'Esta propuesta ya fue procesada y la asignación fue retirada. Pide una nueva recomendación.')
    if not existing:
        existing = RecipeAssignment(tenant_id=tenant_id, branch_id=branch_id, recipe_id=recipe.id, patient_id=patient.id)
        db.add(existing)
        db.add(ActivityLog(id=audit_id, tenant_id=tenant_id, branch_id=branch_id, user_id=actor.id,
                           user_email=actor.email, user_name=actor.full_name, action='CARLITOS_RECETA_ASIGNADA',
                           category='CLINICAL', description=f'Asignación confirmada por el profesional: receta {recipe.id}, paciente {patient.id}.'))
        db.commit()
        db.refresh(existing)
    else:
        db.commit()
    return dict(message='Receta asignada. El paciente puede consultarla en su plan.', assignment_id=existing.id,
                patient_id=patient.id, recipe_id=recipe.id)
