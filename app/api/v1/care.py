from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from app.api.deps import get_current_user
from app.database import get_db
from app.core.authorization import require_patient_access, require_role
from app.models.care import Measurement, CareAssessment, PlanReview, NutritionConfiguration
from app.models.ai_nutrition import NutritionalPlan
from app.models.user import User
from app.schemas.care import MeasurementIn, AssessmentIn, NutritionConfigIn, ReviewIn, MessageIn, ImportIn
from app.services import care_service as care
from app.services import care_communication_service as communication

router=APIRouter(prefix='/care',tags=['Seguimiento y comunicación'])


@router.get('/patients/{patient_id}/measurements')
def measurements(patient_id:str,user=Depends(get_current_user),db:Session=Depends(get_db)):
    patient=require_patient_access(db,user,patient_id,allow_self=True)
    return [care.measurement_dict(r) for r in db.query(Measurement).filter_by(patient_id=patient.id,tenant_id=patient.tenant_id).order_by(Measurement.measured_at).all()]


@router.post('/patients/{patient_id}/measurements',status_code=201)
def measurement(patient_id:str,body:MeasurementIn,user=Depends(get_current_user),db:Session=Depends(get_db)):
    return care.add_measurement(db,user,patient_id,body)


@router.post('/patients/{patient_id}/assessments',status_code=201)
def assess(patient_id:str,body:AssessmentIn,user=Depends(get_current_user),db:Session=Depends(get_db)):
    return care.evaluate(db,user,patient_id,body)


@router.get('/patients/{patient_id}/assessments')
def assessments(patient_id:str,user=Depends(get_current_user),db:Session=Depends(get_db)):
    patient=require_patient_access(db,user,patient_id,allow_self=True)
    return [dict(id=r.id,created_at=care.iso(r.created_at),snapshot=r.snapshot) for r in db.query(CareAssessment).filter_by(patient_id=patient.id,tenant_id=patient.tenant_id).order_by(CareAssessment.created_at.desc()).limit(10).all()]


@router.get('/configuration')
def configuration(user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_role(user,care.STAFF)
    return care.configuration(db,user.tenant_id)


@router.put('/configuration')
def save_configuration(body:NutritionConfigIn,user=Depends(get_current_user),db:Session=Depends(get_db)):
    return care.save_configuration(db,user,body)


@router.get('/configuration/history')
def configuration_history(user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_role(user,care.STAFF)
    return [dict(version=r.version,values=r.values,units=care.UNITS,reason=r.reason,actor_id=r.actor_id,created_at=care.iso(r.created_at)) for r in db.query(NutritionConfiguration).filter_by(tenant_id=user.tenant_id).order_by(NutritionConfiguration.version.desc()).limit(20).all()]


@router.post('/plans/{plan_id}/reviews')
def review(plan_id:str,body:ReviewIn,user=Depends(get_current_user),db:Session=Depends(get_db)):
    return care.review_plan(db,user,plan_id,body)


@router.get('/plans/{plan_id}/reviews')
def reviews(plan_id:str,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_role(user,care.STAFF)
    plan=db.query(NutritionalPlan).filter_by(id=plan_id).first()
    if not plan: raise HTTPException(404,'Plan no encontrado.')
    require_patient_access(db,user,plan.patient_id)
    return [dict(id=r.id,decision=r.decision,reason=r.reason,before=r.before,after=r.after,actor_id=r.actor_id,actor_name=name,created_at=care.iso(r.created_at))
        for r,name in db.query(PlanReview,User.full_name).join(User,User.id==PlanReview.actor_id).filter(PlanReview.plan_id==plan.id,PlanReview.tenant_id==plan.tenant_id).order_by(PlanReview.created_at.desc()).all()]


@router.get('/contacts')
def contacts(user=Depends(get_current_user),db:Session=Depends(get_db)):
    return communication.contacts(db,user)


@router.get('/conversations/{peer_id}')
def conversation(peer_id:str,offset:int=Query(0,ge=0),user=Depends(get_current_user),db:Session=Depends(get_db)):
    return communication.thread(db,user,peer_id,offset)


@router.post('/conversations/{peer_id}',status_code=201)
def send(peer_id:str,body:MessageIn,user=Depends(get_current_user),db:Session=Depends(get_db)):
    return communication.send_message(db,user,peer_id,body)


@router.post('/patient-imports/preview')
def preview(body:ImportIn,user=Depends(get_current_user),db:Session=Depends(get_db)):
    return communication.preview_import(db,user,body)


@router.post('/patient-imports/{batch_id}/confirm')
def confirm(batch_id:str,user=Depends(get_current_user),db:Session=Depends(get_db)):
    return communication.confirm_import(db,user,batch_id)
