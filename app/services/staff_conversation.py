"""Single conversational interface with signed, scoped, short-lived context."""
from datetime import datetime, timedelta, timezone
import re
from fastapi import HTTPException
from jose import JWTError, jwt

from app.config import settings
from app.models.recipe import Recipe
from app.schemas.staff_assistant import AssistantIntent
from app.services import staff_assistant_service as actions, staff_gemini

YES = {'si', 'si confirmo', 'confirmo', 'confirmar', 'confirmar asignacion', 'si asignala', 'confirmo la asignacion', 'adelante', 'de acuerdo'}
NO = {'no', 'cancelar', 'cancela', 'no confirmo', 'descartar', 'descartala', 'mejor no', 'no gracias'}
MORE = {'otra', 'otras', 'otra opcion', 'otras opciones', 'mostrame otra', 'muestrame otra', 'mostrame otras opciones', 'ver otras opciones', 'otra por favor'}
ORDINAL = {'primera':1, 'primero':1, 'segunda':2, 'segundo':2, 'tercera':3, 'tercero':3,
           'cuarta':4, 'cuarto':4, 'quinta':5, 'quinto':5}


def read_context(db, actor, token):
    tenant, branch = actions.scope_for(db, actor)
    if not token:
        return dict(patient=None, candidates=[], recipes=[], meal='', seen=[], pending=None, awaiting=None)
    try:
        state = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        raise HTTPException(409, 'La conversación venció. Inicia un nuevo chat para continuar.') from None
    if (state.get('type') != 'staff_assistant_context' or state.get('sub') != actor.id
            or state.get('sv') != (actor.session_version or 0) or state.get('tenant') != tenant or state.get('branch') != branch):
        raise HTTPException(403, 'Esta conversación pertenece a otro profesional o espacio de trabajo. Inicia un nuevo chat.')
    return {key:state.get(key) for key in ('patient','candidates','recipes','meal','seen','pending','awaiting')}


def respond(db, actor, state, **reply):
    tenant, branch = actions.scope_for(db, actor)
    claims = dict(**state, type='staff_assistant_context', sub=actor.id, sv=actor.session_version or 0,
                  tenant=tenant, branch=branch, exp=datetime.now(timezone.utc)+timedelta(minutes=20))
    reply['context_token'] = jwt.encode(claims, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    reply.setdefault('usage', {'engine':'local','total_tokens':0})
    return reply


def clear_proposals(state):
    state.update(recipes=[], pending=None, seen=[], meal='', awaiting=None)


def choose_patient(db, actor, state, identity):
    patient = actions.authorized_patient(db, actor, identity)
    if state['patient'] != identity:
        clear_proposals(state)
    state.update(patient=patient.id, candidates=[])
    return patient


def profile_details(profile):
    labels = [('goal','Objetivo'),('birth_date','Fecha de nacimiento'),('gender','Sexo registrado'),
              ('weight_kg','Peso actual (kg)'),('height_cm','Estatura (cm)'),('target_weight_kg','Peso objetivo (kg)'),
              ('target_weeks','Plazo objetivo (semanas)'),('allergies','Alergias e intolerancias'),
              ('other_allergies','Otras alergias'),('pathologies','Antecedentes'),('other_pathologies','Otros antecedentes'),
              ('medications','Medicación registrada'),('food_preferences','Preferencias alimentarias'),
              ('physical_activity','Actividad física'),('digestive_symptoms','Síntomas digestivos'),
              ('water_intake_liters','Agua (L/día)'),('sleep_hours','Sueño (horas)'),('meals_per_day','Comidas por día'),
              ('fruits_vegetables_daily','Frutas y verduras (porciones/día)'),('sugary_drinks_weekly','Bebidas azucaradas (por semana)'),
              ('alcohol_frequency','Alcohol'),('smoke_habit','Tabaco'),('coffee_cups','Café (tazas/día)')]
    result=[]
    for field,label in labels:
        value=getattr(profile,field)
        if isinstance(value,datetime):value=value.date().isoformat()
        if value is None:value='Sin informar'
        elif value=='':value='Ninguna declarada' if field=='allergies' else 'Sin registro'
        result.append(dict(label=label,value=value))
    return result


def local_intent(message, state):
    text=re.sub(r'[.!¡¿?]+$', '', actions.normal(message)).strip()
    if text in YES:
        if state['pending']:return AssistantIntent(action='confirm')
        if len(state['candidates'])==1:return AssistantIntent(action='select',choice=1)
        if state.get('awaiting')=='recommend':return AssistantIntent(action='recommend')
        return AssistantIntent(action='confirm')
    if text in NO:return AssistantIntent(action='cancel')
    if text in MORE:return AssistantIntent(action='more')
    if text in {'hola','ayuda','que podes hacer','que puedes hacer'}:return AssistantIntent(action='help')
    match=re.fullmatch(r'(?:(?:asigna(?:le|la|r)?|elegi|elige|selecciona|selecciono|quiero)\s+)?(?:la |el |opcion |receta )?(primera|primero|segunda|segundo|tercera|tercero|cuarta|cuarto|quinta|quinto|[1-9]|10)(?: opcion| receta| paciente)?(?: por favor)?',text)
    if match:
        word=match.group(1)
        return AssistantIntent(action='select',choice=int(word) if word.isdigit() else ORDINAL[word])
    if text in {'mostrame su anamnesis','mostrame su anamesis','muestrame su anamnesis','mostrame la ficha','ver anamnesis','ver su ficha','su anamnesis','si mostrame su anamnesis','si, mostrame su anamnesis'}:
        return AssistantIntent(action='profile')
    return None


def chat(db, actor, body):
    state=read_context(db,actor,body.context_token)
    intent=local_intent(body.message,state)
    usage={'engine':'local','total_tokens':0}
    if intent is None:
        hints=dict(patient_selected=bool(state['patient']),patient_options=len(state['candidates']),
                   recipe_options=len(state['recipes']),awaiting_confirmation=bool(state['pending']),meal=state['meal'])
        intent,usage=staff_gemini.interpret(body.message,actor.id,actor.tenant_id,hints)

    def reply(**values):
        return respond(db,actor,state,usage=usage,**values)

    # Confirmation applies only to the immediately preceding proposal prompt.
    if intent.action != 'confirm':
        state['pending'] = None

    if intent.action=='cancel':
        clear_proposals(state);state['candidates']=[]
        return reply(kind='message',message='De acuerdo, descarté lo pendiente. No guardé una asignación nueva. ¿Qué querés hacer ahora?')
    if intent.action=='confirm':
        # A model classification alone can NEVER authorize a write.
        if actions.normal(body.message).strip(' .!¡¿?') not in YES or not state['pending']:
            state['pending'] = None
            return reply(kind='message',message='Todavía no hay una asignación pendiente para confirmar. Primero elegí una receta de las propuestas.')
        result=actions.confirm(db,actor,state['pending'])
        state.update(pending=None,recipes=[],awaiting=None)
        return reply(kind='assigned',message=result['message'],patient=actions.patient_summary(actions.authorized_patient(db,actor,result['patient_id'])))
    if intent.action=='select':
        if state['recipes']:
            index=intent.choice-1
            if index<0 or index>=len(state['recipes']):
                return reply(kind='message',message=f'¿Cuál receta elegís? Indicá un número del 1 al {len(state["recipes"])}.')
            token=state['recipes'][index]['token']
            try:data=jwt.decode(token,settings.SECRET_KEY,algorithms=[settings.ALGORITHM])
            except JWTError:
                clear_proposals(state)
                return reply(kind='message',message='Esas propuestas vencieron. Pedime una nueva recomendación.')
            patient=actions.authorized_patient(db,actor,data['patient'])
            recipe=db.query(Recipe).filter_by(id=data['recipe'],tenant_id=patient.tenant_id,is_active=True).first()
            if not recipe:raise HTTPException(409,'La receta ya no está disponible. Pide otra propuesta.')
            state.update(pending=token,awaiting='confirmation')
            return reply(kind='confirmation',patient=actions.patient_summary(patient),
                         message=f'¿Confirmás asignar «{recipe.title}» a {patient.full_name}? Revisá ingredientes y porción. Escribí «confirmo» para guardar o «no» para descartar.',
                         confirmation=dict(title=recipe.title,patient_name=patient.full_name))
        if state['candidates'] and 1<=intent.choice<=len(state['candidates']):
            patient=choose_patient(db,actor,state,state['candidates'][intent.choice-1])
            return reply(kind='message',patient=actions.patient_summary(patient),message=f'Perfecto, trabajamos con {patient.full_name}. Podés pedirme su anamnesis o una receta.')
        return reply(kind='message',message='Primero busquemos un paciente o pidamos recetas. No hay opciones claras para elegir en este momento.')
    if intent.action=='help':
        return reply(kind='message',message='Podés conversar conmigo: «Buscá al paciente Alex», «Mostrame su anamnesis», «Recomendale una cena», «Otra opción» y «Asignale la segunda». Te pediré «confirmo» antes de guardar. Por ahora trabajo con pacientes y recetas de tu espacio autorizado.')

    name=intent.patient_name.strip()
    selected=actions.authorized_patient(db,actor,state['patient']) if state['patient'] else None
    if intent.action=='patients' or (name and (not selected or not all(actions.mentions(actions.normal(selected.full_name),word) for word in actions.normal(name).split()))):
        matches=actions.search_patients(db,actor,name)
        clear_proposals(state)
        state.update(patient=None,candidates=[p['id'] for p in matches['patients']])
        if intent.action!='patients' and len(matches['patients'])==1 and not matches['has_more']:
            selected=choose_patient(db,actor,state,matches['patients'][0]['id'])
        else:
            text=('Encontré a '+matches['patients'][0]['full_name']+'. ¿Trabajamos con este paciente? Podés responder «sí».'
                  if len(matches['patients'])==1 and not matches['has_more'] else
                  'Encontré estas coincidencias. Decime el número o el nombre completo del paciente.' if matches['patients'] else
                  'No encontré pacientes autorizados con ese nombre en esta sucursal. ¿Con qué nombre lo buscamos?')
            return reply(kind='patients',message=text,**matches)
    if not selected and len(state['candidates'])==1:
        selected=choose_patient(db,actor,state,state['candidates'][0])
    if not selected:
        return reply(kind='message',message='¿Para qué paciente? Escribí su nombre o elegí una coincidencia de la búsqueda anterior.')
    if intent.action=='profile':
        profile=actions.profile_for(db,selected)
        state['awaiting']='recommend'
        return reply(kind='profile',patient=actions.patient_summary(selected),profile_details=profile_details(profile),
                     message=f'Esta es la anamnesis registrada de {selected.full_name}. ¿Querés que busque una receta según esta ficha?')
    if intent.action in {'recommend','more'}:
        meal=intent.meal or state['meal'] or ''
        if intent.action=='more':
            state['seen']=list(dict.fromkeys(state['seen']+[r['id'] for r in state['recipes']]))[-32:]
        else:state['seen']=[]
        result=actions.recommendations(db,actor,selected,meal,state['seen'])
        state.update(meal=meal,pending=None,awaiting=None,candidates=[],recipes=[dict(id=r['id'],token=r['proposal_token']) for r in result['recipes']])
        result['recipes']=[{key:value for key,value in r.items() if key!='proposal_token'} for r in result['recipes']]
        if result['recipes']:result['message']+=' Podés decir «otra opción» o «asignale la segunda».'
        return reply(**result)
    return reply(kind='message',message='No entendí cómo continuar. Podés pedirme buscar un paciente, ver su ficha o recomendarle una receta.')
