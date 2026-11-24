"""Read-only, scoped tools that ground professional conversational answers."""
from fastapi import HTTPException
from sqlalchemy import or_
from app.models.patient_link import PatientNutritionistLink
from app.models.recipe import Recipe, RecipeAssignment
from app.models.user import User
from app.services import staff_assistant_service as actions

CAPABILITIES = ['Buscar pacientes autorizados', 'Consultar anamnesis y vinculación',
                'Consultar agenda y citas por estado o fechas', 'Consultar recetas ya asignadas', 'Proponer recetas del catálogo y explicar las propuestas',
                'Preparar asignación y guardarla solo con confirmación explícita en otro turno']
PROFILE_SECTIONS = {
    'allergies': ('allergies','other_allergies'),
    'goals': ('goal','weight_kg','height_cm','target_weight_kg','target_weeks'),
    'habits': ('food_preferences','physical_activity','water_intake_liters','sleep_hours','meals_per_day',
               'fruits_vegetables_daily','sugary_drinks_weekly','alcohol_frequency','smoke_habit','coffee_cups'),
    'medications': ('medications',),
    'profile': ('birth_date','gender','weight_kg','height_cm','target_weight_kg','target_weeks','goal','allergies','other_allergies','pathologies','other_pathologies','medications',
                'food_preferences','physical_activity','digestive_symptoms','is_pregnant_or_lactating'),
}


def read(db, actor, patient, intent, state):
    tenant, branch = actions.scope_for(db, actor)
    base = {'tool':intent.topic, 'read_only':True, 'patient':patient.full_name if patient else None}
    if intent.topic == 'appointments':
        from app.services.staff_assistant_agenda import read as read_agenda
        return read_agenda(db,actor,patient,intent)
    if intent.topic == 'help':
        return dict(**base,capabilities=CAPABILITIES,
                    unsupported=['Aceptar/cancelar/modificar citas, enviar mensajes, ejecutar cobros o reportes desde este chat', 'Consultar pacientes fuera del espacio autorizado']), 'Puedo consultar pacientes, su anamnesis, vinculación y recetas, y preparar recomendaciones con confirmación antes de asignar.'
    # Recheck access at the tool boundary, independently of the conversation planner.
    patient = actions.authorized_patient(db,actor,patient.id)
    if intent.topic == 'links':
        links = (db.query(PatientNutritionistLink,User).join(User,User.id==PatientNutritionistLink.nutritionist_id)
                 .filter(PatientNutritionistLink.patient_id==patient.id,PatientNutritionistLink.tenant_id==tenant,
                         PatientNutritionistLink.branch_id==branch,PatientNutritionistLink.status=='LINKED',
                         User.tenant_id==tenant,User.is_active.is_(True),
                         User.role_id.in_(['NUTRICIONISTA','ADMIN_ORGANIZATION']))
                 .order_by(User.full_name,PatientNutritionistLink.id).limit(20).all())
        records=[dict(professional=user.full_name,is_you=user.id==actor.id,
                      linked_since=link.linked_at.date().isoformat() if link.linked_at else None) for link,user in links]
        mine=any(r['is_you'] for r in records)
        names=', '.join(dict.fromkeys(r['professional'] for r in records))
        summary=(f'{patient.full_name} está vinculado con {names}.' if records else
                 f'{patient.full_name} no tiene una vinculación activa con un profesional activo en esta sucursal.')
        if intent.link_scope=='me':
            summary=(f'Sí, {patient.full_name} está vinculado con vos.' if mine else
                     f'No, {patient.full_name} no está vinculado con vos. '+summary)
        return dict(**base,question_scope=intent.link_scope,linked_to_you=mine,active_links=records,
                    coverage='Solo vínculos activos del paciente en la empresa y sucursal autorizadas; no se consultaron otras sucursales.'),summary
    if intent.topic in PROFILE_SECTIONS:
        try:
            profile=actions.profile_for(db,patient)
        except HTTPException as error:
            if error.status_code!=422:raise
            return dict(**base,record_exists=False),f'{patient.full_name} todavía no tiene una anamnesis registrada; no puedo confirmar esos datos.'
        fields={field:(getattr(profile,field).date().isoformat() if field=='birth_date' and getattr(profile,field) else getattr(profile,field)) for field in PROFILE_SECTIONS[intent.topic]}
        summary='Datos registrados de '+patient.full_name+': '+ '; '.join(f'{key}: {value if value is not None else "sin informar"}' for key,value in fields.items())
        return dict(**base,recorded=fields,missing_value_means='No informado; no inferir ausencia de condición',
                    empty_allergies_means='Ninguna declarada en la ficha; no equivale a evaluación clínica'),summary
    recipe_query=db.query(Recipe).filter(Recipe.tenant_id==tenant,Recipe.is_active.is_(True),
                                         or_(Recipe.branch_id==branch,Recipe.branch_id.is_(None)))
    if intent.topic=='assigned_recipes':
        recipes=(recipe_query.join(RecipeAssignment,RecipeAssignment.recipe_id==Recipe.id)
                 .filter(RecipeAssignment.patient_id==patient.id,RecipeAssignment.tenant_id==tenant,
                         RecipeAssignment.branch_id==branch).order_by(RecipeAssignment.assigned_at.desc()).limit(20).all())
    else:
        identities=[r['id'] for r in state['recipes']]
        if intent.choice and intent.choice<=len(identities):identities=[identities[intent.choice-1]]
        elif not intent.choice:identities=state.get('discussed_recipes') or identities
        recipes=recipe_query.filter(Recipe.id.in_(identities)).order_by(Recipe.title).limit(3).all()
    details=[]
    profile=actions.profile_for(db,patient) if intent.topic=='recommendations' else None
    for recipe in recipes:
        original_options=[r['id'] for r in state.get('recipes',[])]
        item=dict(option_number=original_options.index(recipe.id)+1 if recipe.id in original_options else None,
                  title=recipe.title,category=recipe.category,servings=recipe.servings,
                  calories=recipe.calories,protein=recipe.protein,carbohydrates=recipe.carbohydrates,fats=recipe.fats)
        if profile:
            evaluation=actions.evaluate_recipe(recipe,profile)
            item.update(ingredients=recipe.ingredients[:1500],current_filter_eligible=evaluation is not None,
                        reasons=evaluation[1] if evaluation else [],warnings=evaluation[2] if evaluation else ['La ficha o receta actual requiere revisión; no afirmar que es apropiada.'])
        details.append(item)
    summary=(('Recetas asignadas a ' if intent.topic=='assigned_recipes' else 'Propuestas actuales para ')+patient.full_name+': '+
             (', '.join(r['title'] for r in details) if details else 'no hay registros disponibles.'))
    if intent.topic=='recommendations' and details:
        explanations=[r['title']+': '+'; '.join(r['reasons']+r['warnings']) for r in details]
        summary=f'Objetivo registrado: {profile.goal}. Motivos de las recetas: '+' | '.join(explanations)
    profile_context=({field:getattr(profile,field) for field in ('goal','allergies','other_allergies','pathologies','other_pathologies','food_preferences')} if profile else None)
    return dict(**base,recipes=details,requested_option=intent.choice or None,profile_context=profile_context,limited_to=len(details),clinical_decision='Requiere revisión profesional de ficha, ingredientes y porción'),summary
