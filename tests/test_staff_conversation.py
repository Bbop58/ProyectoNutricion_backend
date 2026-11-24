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
