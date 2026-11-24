from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.api.deps import get_current_user
from app.database import get_db
from app.schemas.staff_assistant import AssistantConfirm, AssistantQuery
from app.services import staff_assistant_service as assistant

router = APIRouter(prefix='/staff-assistant', tags=['Carlitos profesional'])


@router.get('/patients')
def patients(search: str = Query('', max_length=80), offset: int = Query(0, ge=0, le=10000),
             actor=Depends(get_current_user), db: Session = Depends(get_db)):
    return assistant.search_patients(db, actor, search, offset)


@router.post('/query')
def query(body: AssistantQuery, actor=Depends(get_current_user), db: Session = Depends(get_db)):
    return assistant.query(db, actor, body)


@router.post('/confirm')
def confirm(body: AssistantConfirm, actor=Depends(get_current_user), db: Session = Depends(get_db)):
    return assistant.confirm(db, actor, body.proposal_token)
