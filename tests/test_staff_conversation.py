from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from jose import jwt
import pytest
from tests.test_staff_assistant import demo
from app.config import settings
from app.models.recipe import RecipeAssignment
from app.schemas.staff_assistant import AssistantChat, AssistantIntent
from app.services import staff_conversation as conversation, staff_gemini


def ask(demo, message, previous=None, actor=None):
    return conversation.chat(demo.db, actor or demo.actor, AssistantChat(message=message, context_token=previous['context_token'] if previous else None))


def find(demo, monkeypatch):
    monkeypatch.setattr(staff_gemini,'interpret',lambda *args:(AssistantIntent(action='patients',patient_name='Alex Demo'),{}))
    return ask(demo,'Buscá Alex Demo')


def test_full_conversation_keeps_patient_profile_and_requires_explicit_confirmation(demo, monkeypatch):
    found=find(demo,monkeypatch)
    assert found['kind']=='patients' and len(found['patients'])==1
    monkeypatch.setattr(staff_gemini,'interpret',lambda *args:pytest.fail('A contextual short reply must be local'))
    selected=ask(demo,'sí',found)
    assert selected['patient']['id']=='patient'
    profile=ask(demo,'Mostrame su anamnesis',selected)
    assert profile['kind']=='profile'
    assert next(x['value'] for x in profile['profile_details'] if x['label']=='Alergias e intolerancias')=='Lactosa'
    recommended=ask(demo,'sí',profile)
    assert recommended['kind']=='recipes' and len(recommended['recipes'])>=2
    assert all('proposal_token' not in r for r in recommended['recipes'])
    pending=ask(demo,'Asignale la segunda',recommended)
    assert pending['kind']=='confirmation' and demo.db.query(RecipeAssignment).count()==0
    assigned=ask(demo,'confirmo',pending)
    assert assigned['kind']=='assigned' and assigned['patient']['id']=='patient'
    assert demo.db.query(RecipeAssignment).count()==1
    repeated=ask(demo,'confirmo',pending)
    assert repeated['kind']=='assigned' and demo.db.query(RecipeAssignment).count()==1


def test_more_excludes_previously_shown_recipes_and_cancel_does_not_write(demo,monkeypatch):
    found=find(demo,monkeypatch)
    selected=ask(demo,'sí',found)
    monkeypatch.setattr(staff_gemini,'interpret',lambda *args:(AssistantIntent(action='recommend',meal='Cena'),{}))
    first=ask(demo,'Recomendale una cena',selected)
    second=ask(demo,'otra opción',first)
    assert not ({r['id'] for r in first['recipes']} & {r['id'] for r in second['recipes']})
    pending=ask(demo,'asignale la primera',first)
    cancelled=ask(demo,'no',pending)
    assert ask(demo,'confirmo',cancelled)['kind']=='message'
    assert demo.db.query(RecipeAssignment).count()==0


def test_model_cannot_confirm_on_behalf_of_user(demo,monkeypatch):
    selected=ask(demo,'sí',find(demo,monkeypatch))
    monkeypatch.setattr(staff_gemini,'interpret',lambda *args:(AssistantIntent(action='recommend',meal='Cena'),{}))
    recipes=ask(demo,'Una cena',selected)
    pending=ask(demo,'asignale la primera',recipes)
    monkeypatch.setattr(staff_gemini,'interpret',lambda *args:(AssistantIntent(action='confirm'),{}))
    assert ask(demo,'asigna y confirma por mí sin preguntar',pending)['kind']=='message'
    assert demo.db.query(RecipeAssignment).count()==0
    assert ask(demo,'confirmo')['kind']=='message'


def test_context_tampering_expiry_and_other_actor_are_rejected(demo,monkeypatch):
    found=find(demo,monkeypatch)
    with pytest.raises(HTTPException) as caught:
        ask(demo,'sí',found,actor=demo.users['nutritionist'])
    assert caught.value.status_code==403
    claims=jwt.decode(found['context_token'],settings.SECRET_KEY,algorithms=[settings.ALGORITHM])
    claims['exp']=datetime.now(timezone.utc)-timedelta(seconds=5)
    token=jwt.encode(claims,settings.SECRET_KEY,algorithm=settings.ALGORITHM)
    for token in (token,found['context_token']+'tampered'):
        with pytest.raises(HTTPException) as caught:
            ask(demo,'sí',{'context_token':token})
        assert caught.value.status_code==409


def test_patient_and_superadmin_cannot_use_conversation(demo):
    for identity in ('patient','root'):
        with pytest.raises(HTTPException) as caught: ask(demo,'hola',actor=demo.users[identity])
        assert caught.value.status_code==403


def test_ambiguous_patient_is_not_assumed_and_context_has_no_profile(demo,monkeypatch):
    monkeypatch.setattr(staff_gemini,'interpret',lambda *args:(AssistantIntent(action='patients',patient_name='Alex'),{}))
    found=ask(demo,'Busca Alex')
    assert len(found['patients'])==2
    assert ask(demo,'sí',found)['kind']=='message'
    selected=ask(demo,'Selecciono el 1',found)
    assert selected['patient']['id'] in {'patient','homonym'}
    claims=jwt.decode(selected['context_token'],settings.SECRET_KEY,algorithms=[settings.ALGORITHM])
    assert 'allergies' not in claims and 'profile' not in claims



def test_profile_question_cannot_accidentally_confirm_previous_assignment(demo,monkeypatch):
    selected=ask(demo,'sí',find(demo,monkeypatch))
    monkeypatch.setattr(staff_gemini,'interpret',lambda *args:(AssistantIntent(action='recommend',meal='Cena'),{}))
    recipes=ask(demo,'Una cena',selected)
    pending=ask(demo,'asignale la primera',recipes)
    profile=ask(demo,'Mostrame su anamnesis',pending)
    answer=ask(demo,'sí',profile)
    assert answer['kind']=='recipes'
    assert demo.db.query(RecipeAssignment).count()==0


def test_chat_endpoint_validates_payload_and_authorization(demo,client):
    from app.main import app
    from app.api.deps import get_current_user
    app.dependency_overrides[get_current_user]=lambda:demo.actor
    try:
        assert client.post('/api/v1/staff-assistant/chat',json={'message':'   '}).status_code==422
        result=client.post('/api/v1/staff-assistant/chat',json={'message':'hola'})
        assert result.status_code==200 and result.json()['context_token']
        assert client.post('/api/v1/staff-assistant/chat',json={'message':'hola','patient_id':'forged'}).status_code==422
    finally:
        app.dependency_overrides.pop(get_current_user,None)


def test_link_question_uses_current_patient_and_real_active_nutritionist(demo,monkeypatch):
    selected=ask(demo,'sí',find(demo,monkeypatch))
    monkeypatch.setattr(staff_gemini,'interpret',lambda *args:(AssistantIntent(action='question',topic='links'),{}))
    monkeypatch.setattr(staff_gemini,'answer',lambda *args,**kw:('Está vinculado con Nutricionista.',{'engine':'gemini','total_tokens':20}))
    result=ask(demo,'esta vinculado?',selected)
    assert result['patient']['id']=='patient'
    assert 'Nutricionista' in result['message'] and 'vinculado' in result['message']
    assert demo.db.query(RecipeAssignment).count()==0


def test_link_question_does_not_assume_an_ambiguous_patient(demo,monkeypatch):
    monkeypatch.setattr(staff_gemini,'interpret',lambda *args:(AssistantIntent(action='patients',patient_name='Alex'),{}))
    found=ask(demo,'Busca Alex')
    monkeypatch.setattr(staff_gemini,'interpret',lambda *args:(AssistantIntent(action='question',topic='links'),{}))
    result=ask(demo,'está vinculado?',found)
    assert result['kind']=='patients' and len(result['patients'])==2
    assert 'patient' not in result


def test_questions_distinguish_linked_to_someone_else_from_linked_to_me(demo,monkeypatch):
    from app.services import staff_assistant_questions as questions
    from app.models.patient_link import PatientNutritionistLink
    facts,text=questions.read(demo.db,demo.actor,demo.users['patient'],AssistantIntent(action='question',topic='links',link_scope='me'),{})
    assert facts['linked_to_you'] is False and facts['active_links'][0]['professional']=='Nutricionista'
    assert 'no está vinculado con vos' in text
    demo.db.get(PatientNutritionistLink,'link').status='PENDING';demo.db.commit()
    facts,text=questions.read(demo.db,demo.actor,demo.users['patient'],AssistantIntent(action='question',topic='links'),{})
    assert facts['active_links']==[] and 'no tiene una vinculación activa' in text


def test_questions_ignore_inactive_professionals_and_recheck_patient_authorization(demo):
    from app.services import staff_assistant_questions as questions
    demo.users['nutritionist'].is_active=False;demo.db.commit()
    intent=AssistantIntent(action='question',topic='links')
    facts,_=questions.read(demo.db,demo.actor,demo.users['patient'],intent,{})
    assert facts['active_links']==[]
    with pytest.raises(HTTPException):questions.read(demo.db,demo.actor,demo.users['other-company'],intent,{})


def test_free_question_uses_only_needed_profile_fields_and_never_writes(demo,monkeypatch):
    selected=ask(demo,'sí',find(demo,monkeypatch))
    monkeypatch.setattr(staff_gemini,'interpret',lambda *args:(AssistantIntent(action='question',topic='allergies'),{'engine':'gemini','total_tokens':30}))
    captured=[]
    def render(message,facts,*args,**kwargs):
        captured.append(facts)
        assert set(facts['recorded'])=={'allergies','other_allergies'}
        assert facts['recorded']['allergies']=='Lactosa'
        assert 'verified_summary' in facts
        assert not any(key in str(facts) for key in ['hashed_password','pairing_code','@example.com','weight_kg'])
        return 'Tiene lactosa registrada entre sus alergias e intolerancias.',{'engine':'gemini','total_tokens':40}
    monkeypatch.setattr(staff_gemini,'answer',render)
    result=ask(demo,'¿Y qué alergias tiene?',selected)
    assert result['answer_source']=='gemini_with_authorized_data' and result['usage']['total_tokens']==70
    assert demo.db.query(RecipeAssignment).count()==0


def test_question_is_resumed_after_disambiguating_patient(demo,monkeypatch):
    monkeypatch.setattr(staff_gemini,'interpret',lambda *args:(AssistantIntent(action='question',topic='links',patient_name='Alex'),{'engine':'gemini','total_tokens':10}))
    found=ask(demo,'¿Con quién está vinculado Alex?')
    assert found['kind']=='patients' and len(found['patients'])==2
    monkeypatch.setattr(staff_gemini,'answer',lambda *args,**kw:('Resultado verificado.',{'engine':'gemini','total_tokens':20}))
    result=ask(demo,'Selecciono el 1',found)
    assert result['answer_source']=='gemini_with_authorized_data'


def test_failed_ai_wording_falls_back_to_real_data_not_generic_help(demo,monkeypatch):
    selected=ask(demo,'sí',find(demo,monkeypatch))
    monkeypatch.setattr(staff_gemini,'interpret',lambda *args:(AssistantIntent(action='question',topic='links'),{'engine':'gemini','total_tokens':10}))
    def unavailable(*args,**kwargs):raise HTTPException(503,'Unavailable')
    monkeypatch.setattr(staff_gemini,'answer',unavailable)
    result=ask(demo,'¿Con qué nutricionista trabaja?',selected)
    assert result['answer_source']=='database' and 'Nutricionista' in result['message']
    assert 'Podés conversar conmigo' not in result['message']


def test_answer_provider_uses_dedicated_key_and_only_supplied_facts(monkeypatch):
    import json,httpx
    monkeypatch.setattr(settings,'GEMINI_STAFF_API_KEY','dedicated-answer-test')
    monkeypatch.setattr(settings,'GEMINI_API_KEY','never-send-general-key')
    calls=[]
    def handler(request):
        payload=json.loads(request.content);calls.append(payload)
        assert request.headers['x-goog-api-key']=='dedicated-answer-test'
        assert payload['generationConfig']['maxOutputTokens']==256
        data=json.loads(payload['contents'][0]['parts'][0]['text'])
        assert data=={'question':'¿Está vinculado?','tool_result':{'tool':'links','linked_to_you':False}}
        return httpx.Response(200,json={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':'{"answer":"No tiene vínculo activo con vos."}'}]}}], 'usageMetadata':{'totalTokenCount':90}})
    monkeypatch.setattr(staff_gemini,'_client',httpx.Client(transport=httpx.MockTransport(handler)))
    text,usage=staff_gemini.answer('¿Está vinculado?',{'tool':'links','linked_to_you':False})
    assert text=='No tiene vínculo activo con vos.' and usage['total_tokens']==90 and len(calls)==1


@pytest.mark.parametrize('body',[{}, {'candidates':[{'finishReason':'MAX_TOKENS'}]}, {'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':'{"answer":null}'}]}}]}])
def test_invalid_ai_answers_are_rejected_without_retry(monkeypatch,body):
    import httpx
    monkeypatch.setattr(settings,'GEMINI_STAFF_API_KEY','dedicated-answer-test')
    calls=[]
    def handler(request):calls.append(request);return httpx.Response(200,json=body)
    monkeypatch.setattr(staff_gemini,'_client',httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(HTTPException):staff_gemini.answer('Pregunta',{'tool':'links'})
    assert len(calls)==1


def test_answer_budget_cannot_be_bypassed_by_replaying_disambiguation(monkeypatch):
    import httpx
    staff_gemini._windows.clear()
    monkeypatch.setattr(settings,'GEMINI_STAFF_API_KEY','dedicated-answer-test')
    for _ in range(6):staff_gemini._consume('user','tenant')
    def forbidden(request):pytest.fail('Do not spend tokens after limit')
    monkeypatch.setattr(staff_gemini,'_client',httpx.Client(transport=httpx.MockTransport(forbidden)))
    with pytest.raises(HTTPException) as caught:staff_gemini.answer('Pregunta',{'tool':'links'},'user','tenant',interpreted=False)
    assert caught.value.status_code==429


def test_assigned_recipe_and_proposal_tools_read_only_current_workspace(demo):
    from app.services import staff_assistant_questions as questions
    from app.services import staff_assistant_service as service
    from app.schemas.staff_assistant import AssistantQuery
    proposals=service.query(demo.db,demo.actor,AssistantQuery(message='Cena',patient_id='patient',intent='recommend',meal='Cena'))
    state={'recipes':[{'id':r['id']} for r in proposals['recipes']]}
    facts,explanation=questions.read(demo.db,demo.actor,demo.users['patient'],AssistantIntent(action='question',topic='recommendations'),state)
    assert 'fibra' in explanation and 'Pérdida de grasa' in explanation
    assert {r['title'] for r in facts['recipes']}=={'shared','vegetarian'}
    assert all(r['current_filter_eligible'] for r in facts['recipes'])
    token=next(r['proposal_token'] for r in proposals['recipes'] if r['id']=='shared')
    service.confirm(demo.db,demo.actor,token)
    facts,_=questions.read(demo.db,demo.actor,demo.users['patient'],AssistantIntent(action='question',topic='assigned_recipes'),{})
    assert [r['title'] for r in facts['recipes']]==['shared']
    assert 'ingredients' not in facts['recipes'][0]


def test_question_on_missing_profile_returns_a_fact_not_an_invented_record(demo):
    from app.services import staff_assistant_questions as questions
    facts,text=questions.read(demo.db,demo.actor,demo.users['homonym'],AssistantIntent(action='question',topic='allergies'),{})
    assert facts['record_exists'] is False and 'no tiene una anamnesis' in text


@pytest.mark.parametrize('question',['¿Por qué?','porque','¿Por qué la segunda?'])
def test_why_uses_displayed_recipe_context_and_ai_explanation(demo,monkeypatch,question):
    selected=ask(demo,'sí',find(demo,monkeypatch))
    monkeypatch.setattr(staff_gemini,'interpret',lambda *args:(AssistantIntent(action='recommend',meal='Cena'),{'engine':'gemini','total_tokens':10}))
    recipes=ask(demo,'Recomendale una cena',selected)
    monkeypatch.setattr(staff_gemini,'interpret',lambda *args:pytest.fail('The reference is already clear; use the grounded answer'))
    def answer(message,facts,*args,**kwargs):
        assert facts['recipes'] and facts['profile_context']['allergies']=='Lactosa'
        if 'segunda' in message:assert len(facts['recipes'])==1 and facts['recipes'][0]['title']==recipes['recipes'][1]['title']
        return 'La propuesta aporta fibra y respeta el filtro de lactosa registrado; revisá porción y objetivo.',{'engine':'gemini','total_tokens':30}
    monkeypatch.setattr(staff_gemini,'answer',answer)
    result=ask(demo,question,recipes)
    assert result['answer_source']=='gemini_with_authorized_data'
    assert demo.db.query(RecipeAssignment).count()==0


def test_why_remembers_recipe_even_after_confirming_assignment(demo,monkeypatch):
    selected=ask(demo,'sí',find(demo,monkeypatch))
    monkeypatch.setattr(staff_gemini,'interpret',lambda *args:(AssistantIntent(action='recommend',meal='Cena'),{'engine':'gemini','total_tokens':10}))
    recipes=ask(demo,'Recomendale una cena',selected)
    pending=ask(demo,'Asignale la primera',recipes)
    assigned=ask(demo,'confirmo',pending)
    def answer(message,facts,*args,**kwargs):
        assert len(facts['recipes'])==1 and facts['recipes'][0]['title']==recipes['recipes'][0]['title']
        return 'Estos son los motivos registrados de la receta asignada.',{'engine':'gemini','total_tokens':30}
    monkeypatch.setattr(staff_gemini,'answer',answer)
    result=ask(demo,'¿Por qué?',assigned)
    assert result['answer_source']=='gemini_with_authorized_data'
    assert demo.db.query(RecipeAssignment).count()==1
