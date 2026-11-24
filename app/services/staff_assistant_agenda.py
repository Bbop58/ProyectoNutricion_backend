"""Authorized read-only agenda tool; no appointment mutations or clinical notes."""
from datetime import datetime, time, timedelta, timezone
from fastapi import HTTPException
from sqlalchemy.orm import joinedload
from app.models.appointment import Appointment
from app.services import staff_assistant_service as actions

BOLIVIA=timezone(timedelta(hours=-4))
LABELS={'ALL':'todos los estados','PENDING':'pendientes de aceptación','ACCEPTED':'aceptadas, pendientes de pago',
        'CONFIRMED':'confirmadas','CANCELLED':'canceladas','COMPLETED':'completadas'}


def read(db, actor, patient, intent):
    tenant,branch=actions.scope_for(db,actor)
    query=db.query(Appointment).filter(Appointment.tenant_id==tenant,Appointment.branch_id==branch)
    coverage='Citas de la empresa y sucursal activas'
    if actor.role_id=='NUTRICIONISTA':
        query=query.filter(Appointment.nutritionist_id==actor.id)
        coverage='Solo tus citas como profesional en la empresa y sucursal activas'
    if intent.appointment_scope=='patient':
        if patient is None:raise HTTPException(422,'Elegí el paciente para consultar sus citas.')
        patient=actions.authorized_patient(db,actor,patient.id)
        query=query.filter(Appointment.patient_id==patient.id)
        coverage+='; paciente '+patient.full_name
    if intent.appointment_status!='ALL':query=query.filter(Appointment.status==intent.appointment_status)
    if intent.date_to and intent.date_to.year==9999:
        raise HTTPException(422,'Indicá un período válido para consultar la agenda.')
    if intent.date_from and intent.date_to and intent.date_from>intent.date_to:
        raise HTTPException(422,'La fecha inicial debe ser anterior o igual a la final. Indicá nuevamente el período.')
    if intent.date_from:
        lower=datetime.combine(intent.date_from,time.min,tzinfo=BOLIVIA).astimezone(timezone.utc).replace(tzinfo=None)
        query=query.filter(Appointment.scheduled_at>=lower)
    if intent.date_to:
        upper=datetime.combine(intent.date_to+timedelta(days=1),time.min,tzinfo=BOLIVIA).astimezone(timezone.utc).replace(tzinfo=None)
        query=query.filter(Appointment.scheduled_at<upper)
    total=query.count()
    rows=(query.options(joinedload(Appointment.patient),joinedload(Appointment.nutritionist))
          .order_by(Appointment.scheduled_at,Appointment.id).limit(10).all())
    records=[];lines=[]
    for index,row in enumerate(rows,1):
        when=row.scheduled_at
        when=(when.replace(tzinfo=timezone.utc) if when.tzinfo is None else when).astimezone(BOLIVIA)
        patient_name=row.patient.full_name if row.patient else 'Paciente no disponible'
        professional=row.nutritionist.full_name if row.nutritionist else 'Profesional no disponible'
        status=LABELS.get(row.status,row.status)
        records.append(dict(patient=patient_name,professional=professional,scheduled_at=when.isoformat(),status=status))
        lines.append(f'{index}. {when:%d/%m/%Y %H:%M} — {patient_name} — {professional} — {status}.')
    period=(f'Desde {intent.date_from.isoformat()}' if intent.date_from else 'Sin fecha inicial')+'; '+(f'hasta {intent.date_to.isoformat()}' if intent.date_to else 'sin fecha final')
    summary=f'{coverage}. Estado: {LABELS[intent.appointment_status]}. {period}. Horario de Bolivia. Encontré {total} cita(s).'
    if total>len(rows):summary+=f' Mostrando las primeras {len(rows)}; pedí un período más específico para acotar la lista.'
    facts=dict(tool='appointments',read_only=True,coverage=coverage,timezone='America/La_Paz',
               status=LABELS[intent.appointment_status],date_from=str(intent.date_from) if intent.date_from else None,
               date_to=str(intent.date_to) if intent.date_to else None,total=total,shown=len(rows),
               has_more=total>len(rows),appointments=records,_display_lines='\n'.join(lines))
    return facts,summary
