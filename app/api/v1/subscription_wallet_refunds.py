from typing import Literal
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator, ConfigDict
from sqlalchemy.orm import Session
from app.api.deps import get_current_user
from app.database import get_db
from app.core.authorization import require_role
from app.models.subscription_wallet_refund import SubscriptionWalletRefund as Refund
from app.models.user import User
from app.services import subscription_wallet_refund_service as service

router=APIRouter(tags=['Devoluciones de Premium a wallet'])


class RequestRefund(BaseModel):
    model_config=ConfigDict(extra='forbid')
    subscription_id: str = Field(min_length=1,max_length=36)
    reason: str = Field(min_length=3,max_length=500)

    @field_validator('reason')
    @classmethod
    def reason_not_blank(cls,value):
        value=value.strip()
        if len(value)<3: raise ValueError('Explica el motivo con al menos tres caracteres.')
        return value


class Decision(BaseModel):
    model_config=ConfigDict(extra='forbid')
    decision: Literal['APPROVED','REJECTED']
    reason: str = Field(min_length=3,max_length=500)
    _reason=field_validator('reason')(RequestRefund.reason_not_blank.__func__)


@router.get('/subscriptions/wallet-refunds')
def mine(limit:int=Query(20,ge=1,le=100),offset:int=Query(0,ge=0),db:Session=Depends(get_db),user=Depends(get_current_user)):
    require_role(user,{'CLIENTE'})
    rows=db.query(Refund).filter_by(user_id=user.id).order_by(Refund.created_at.desc(),Refund.id).offset(offset).limit(limit).all()
    return [service.view(r) for r in rows]


@router.post('/subscriptions/wallet-refunds')
def request_refund(body:RequestRefund,db:Session=Depends(get_db),user=Depends(get_current_user)):
    return service.request_refund(db,user,body.subscription_id,body.reason)


@router.get('/subscriptions/wallet-refunds/{identity}/pdf')
def document(identity:str,db:Session=Depends(get_db),user=Depends(get_current_user)):
    require_role(user,{'CLIENTE'})
    return StreamingResponse(service.receipt_pdf(db,user,identity),media_type='application/pdf',headers={
        'Content-Disposition':f'attachment; filename="Devolucion_wallet_{identity}.pdf"','Cache-Control':'private, no-store'})


@router.get('/platform/wallet-refunds')
def pending(limit:int=Query(20,ge=1,le=100),offset:int=Query(0,ge=0),db:Session=Depends(get_db),user=Depends(get_current_user)):
    require_role(user,{'SUPERADMIN'})
    q=db.query(Refund,User.full_name,User.email).join(User,User.id==Refund.user_id)
    total=q.count()
    rows=q.order_by(Refund.created_at.desc(),Refund.id).offset(offset).limit(limit).all()
    return {'total':total,'items':[{**service.view(row),'buyer_name':name,'buyer_email':email} for row,name,email in rows]}


@router.post('/platform/wallet-refunds/{identity}/decision')
def decision(identity:str,body:Decision,db:Session=Depends(get_db),user=Depends(get_current_user)):
    return service.decide(db,user,identity,body.decision,body.reason)
