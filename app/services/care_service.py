import json
import uuid
from collections import Counter
from datetime import datetime, date, time, timedelta, timezone
from fastapi import HTTPException
from app.core.authorization import require_patient_access, require_role
from app.models.care import Measurement, NutritionConfiguration, CareAssessment, PlanReview
from app.models.ai_nutrition import FoodRecord, NutritionalPlan
from app.models.clinical import PatientAnamnesis, ClinicalRecord
from app.models.notification import Notification
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.care import NutritionValues

STAFF = {'ADMIN_ORGANIZATION', 'NUTRICIONISTA'}
BOLIVIA = timezone(timedelta(hours=-4))
UNITS = {'meals_per_day':'comidas/día','inactivity_days':'días','water_liters':'L/día','sleep_hours':'h/día'}


def utc(value):
    return value.replace(tzinfo=value.tzinfo or timezone.utc).astimezone(timezone.utc).replace(tzinfo=None)


def local_day(value): return utc(value).replace(tzinfo=timezone.utc).astimezone(BOLIVIA).date()
def iso(value): return utc(value).isoformat()+'Z' if value else None
def now(): return datetime.now(timezone.utc).replace(tzinfo=None)


def configuration(db, tenant_id):
    row = db.query(NutritionConfiguration).filter_by(tenant_id=tenant_id).order_by(NutritionConfiguration.version.desc()).first() if tenant_id else None
    return dict(id=row.id if row else None,version=row.version if row else 0,
        values=dict(row.values) if row else NutritionValues().model_dump(), units=UNITS,
        reason=row.reason if row else 'Valores iniciales; el profesional puede ajustarlos.',
        actor_id=row.actor_id if row else None,created_at=iso(row.created_at) if row else None)


def save_configuration(db, actor, body):
    require_role(actor, STAFF)
    company=db.query(Tenant).filter_by(id=actor.tenant_id).with_for_update().first()
    if not company: raise HTTPException(400,'Selecciona una empresa.')
    version=configuration(db,company.id)['version']+1
    row=NutritionConfiguration(tenant_id=company.id,actor_id=actor.id,version=version,
        values=body.values.model_dump(),reason=body.reason)
    db.add(row);db.commit()
    return configuration(db,company.id)


def measurement_dict(row):
    return dict(id=row.id,weight_kg=row.weight_kg,height_cm=row.height_cm,
        bmi=round(row.weight_kg/(row.height_cm/100)**2,2),measured_at=iso(row.measured_at),actor_id=row.actor_id)


def capture_anamnesis(db, anamnesis, actor):
    """Keep new measurements without fabricating a series for earlier dates."""
    if not anamnesis.weight_kg or not anamnesis.height_cm: return
    last=db.query(Measurement).filter_by(patient_id=anamnesis.patient_id,tenant_id=anamnesis.tenant_id).order_by(Measurement.measured_at.desc()).first()
    if last and last.weight_kg==anamnesis.weight_kg and last.height_cm==anamnesis.height_cm: return
    db.add(Measurement(tenant_id=anamnesis.tenant_id,patient_id=anamnesis.patient_id,actor_id=actor.id,
        weight_kg=anamnesis.weight_kg,height_cm=anamnesis.height_cm,measured_at=now()))


def add_measurement(db,actor,patient_id,body):
    patient=require_patient_access(db,actor,patient_id,allow_self=True)
    measured=utc(body.measured_at) if body.measured_at else now()
    if measured>now()+timedelta(minutes=5): raise HTTPException(422,'La medición no puede estar en el futuro.')
    row=Measurement(tenant_id=patient.tenant_id,patient_id=patient.id,actor_id=actor.id,
        weight_kg=body.weight_kg,height_cm=body.height_cm,measured_at=measured)
    db.add(row)
    db.commit();db.refresh(row)
    return measurement_dict(row)


def evaluate(db, actor, patient_id, body):
    patient=require_patient_access(db,actor,patient_id,allow_self=True)
    db.query(User).filter_by(id=patient.id).with_for_update().one()
    today=datetime.now(BOLIVIA).date()
    if body.end_date<body.start_date or (body.end_date-body.start_date).days>365 or body.end_date>today:
        raise HTTPException(422,'Usa un período de hasta 366 días, sin fechas futuras y en orden.')
    cfg=configuration(db,patient.tenant_id)
    anamnesis=db.query(PatientAnamnesis).filter_by(patient_id=patient.id).first()
    habits=[]
    if anamnesis:
        for label,value,key in [('Agua declarada',anamnesis.water_intake_liters,'water_liters'),('Sueño declarado',anamnesis.sleep_hours,'sleep_hours')]:
            habits.append(dict(label=label,value=value,target=cfg['values'][key],unit=UNITS[key],fulfilled=value is not None and value>=cfg['values'][key]))
    measurements=db.query(Measurement).filter_by(patient_id=patient.id,tenant_id=patient.tenant_id).order_by(Measurement.measured_at).all()
    foods=db.query(FoodRecord).filter_by(patient_id=patient.id).all()
    counts=Counter();activity=[]
    for row in foods:
        consumed=row.created_at
        try:
            raw=json.loads(row.result_json).get('consumed_at')
            if raw: consumed=datetime.fromisoformat(raw.replace('Z','+00:00'))
        except (ValueError,TypeError,AttributeError): pass
        day=local_day(consumed)
        if utc(row.created_at)<=now(): activity.append(utc(row.created_at))
        if body.start_date<=day<=body.end_date: counts[day]+=1
    activity.extend(utc(m.created_at) for m in measurements if utc(m.created_at)<=now())
    plans=db.query(NutritionalPlan).filter(NutritionalPlan.patient_id==patient.id,
        NutritionalPlan.status.in_(['APPROVED','ARCHIVED']),NutritionalPlan.approved_at.isnot(None)).all()
    days=[];day=body.start_date
    while day<=body.end_date:
        eligible=[p for p in plans if local_day(p.approved_at)<=day]
        plan=max(eligible,key=lambda p:utc(p.approved_at)) if eligible else None
        target=plan.meals_per_day if plan else cfg['values']['meals_per_day']
        target=max(1,target or cfg['values']['meals_per_day'])
        applicable=day>=local_day(patient.created_at)
        if not applicable: target=0
        days.append(dict(date=day.isoformat(),registered=counts[day],expected=target,
            covered=min(counts[day],target),plan_id=plan.id if plan else None,applicable=applicable))
        day+=timedelta(days=1)
    expected=sum(d['expected'] for d in days);covered=sum(d['covered'] for d in days)
    latest=max([utc(patient.created_at),*activity])
    inactive=max(0,(today-local_day(latest)).days)
    alert=inactive>=cfg['values']['inactivity_days']
    notification_id=str(uuid.uuid5(uuid.NAMESPACE_URL,f'care-inactive:{patient.id}:{latest.isoformat()}:{cfg["version"]}'))
    if alert and not db.query(Notification.id).filter_by(id=notification_id).first():
        db.add(Notification(id=notification_id,user_id=patient.id,tenant_id=patient.tenant_id,branch_id=patient.branch_id,
            title='Seguimiento nutricional',message=f'No hay registros de alimentación ni mediciones desde hace {inactive} días. Retoma tu seguimiento o contacta a tu nutricionista.',
            type='SISTEMA',reference_id=patient.id))
    result=dict(patient_id=patient.id,patient_name=patient.full_name,start_date=body.start_date.isoformat(),end_date=body.end_date.isoformat(),
        generated_at=iso(now()),configuration=cfg,days=days,registered=sum(counts.values()),expected=expected,
        habits=habits,
        adherence_percent=round(100*covered/expected,1) if expected else None,
        missing_days=[d['date'] for d in days if d['applicable'] and d['registered']==0],
        formula='100 × suma diaria de min(comidas registradas, meta diaria) / suma de metas diarias.',
        explanation='Adherencia al REGISTRO de comidas: no evalúa composición, porciones ni cumplimiento clínico. Cada día sin registros aporta 0; las comidas extra no compensan otro día. Meta del plan aprobado para el día; sin plan se usa la configuración indicada. Los días anteriores al alta de la cuenta no generan una meta.',
        measurements=[measurement_dict(m) for m in measurements if body.start_date<=local_day(m.measured_at)<=body.end_date],
        inactivity=dict(days=inactive,threshold=cfg['values']['inactivity_days'],alert=alert,last_record_at=iso(latest)),
        notes=['Las mediciones históricas se conservan desde su registro; no se reconstruyen desde la anamnesis actual.']+
            (['El período contiene días sin datos.'] if any(d['registered']==0 for d in days) else []))
    row=CareAssessment(tenant_id=patient.tenant_id,patient_id=patient.id,actor_id=actor.id,snapshot=result)
    db.add(row);db.commit();db.refresh(row)
    return dict(result,id=row.id)


def review_plan(db,actor,identity,body):
    require_role(actor,STAFF)
    plan=db.query(NutritionalPlan).filter_by(id=identity).with_for_update().first()
    if not plan: raise HTTPException(404,'Plan no encontrado.')
    require_patient_access(db,actor,plan.patient_id)
    if plan.status!='DRAFT': raise HTTPException(409,'Solo se revisan borradores. Genera un nuevo borrador para cambiar un plan vigente.')
    before=dict(status=plan.status,clinical_notes=plan.clinical_notes)
    if body.decision=='CORRECTED':
        if not body.clinical_notes or not body.clinical_notes.strip(): raise HTTPException(422,'Escribe la corrección de la recomendación.')
        plan.clinical_notes=body.clinical_notes.strip()
    elif body.decision=='REJECTED': plan.status='REJECTED'
    after=dict(status='APPROVED' if body.decision=='APPROVED' else plan.status,clinical_notes=plan.clinical_notes)
    db.add(PlanReview(tenant_id=plan.tenant_id,plan_id=plan.id,actor_id=actor.id,decision=body.decision,reason=body.reason,before=before,after=after))
    if body.decision=='APPROVED':
        from app.services.ai_plan_service import AIPlanService
        try: AIPlanService.approve_plan(db,plan.id,actor.id)
        except ValueError as e:
            db.rollback();raise HTTPException(422,str(e))
    else: db.commit()
    return dict(id=plan.id,status=after['status'],message='Decisión profesional registrada.')
