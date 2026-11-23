import csv
import io
from datetime import timedelta
from sqlalchemy import or_, and_, select, func
from sqlalchemy.exc import IntegrityError
from pydantic import ValidationError
from fastapi import HTTPException
from app.models.user import User
from app.models.tenant import Tenant
from app.models.patient_link import PatientNutritionistLink
from app.models.notification import Notification
from app.models.care import CareMessage, PatientImportBatch
from app.core.authorization import require_role
from app.core.security import get_password_hash
from app.schemas.user import OrganizationUserCreate
from app.services.branch_scope import operation_branch
from app.services.commercial_plan_service import check_capacity
from app.services.care_service import STAFF, now, iso


def contacts(db,actor):
    if not actor.tenant_id: return []
    if actor.role_id=='ADMIN_ORGANIZATION':
        # The validated workspace still restricts this directory to the active
        # company/branch. No patient-specialist link is reassigned.
        return [dict(id=u.id,full_name=u.full_name,role_id=u.role_id) for u in
            db.query(User).filter(User.tenant_id==actor.tenant_id,User.role_id=='CLIENTE',
                                  User.is_active==True).order_by(User.full_name).all()]
    if actor.role_id=='CLIENTE': clause=PatientNutritionistLink.patient_id==actor.id
    elif actor.role_id=='NUTRICIONISTA': clause=PatientNutritionistLink.nutritionist_id==actor.id
    else: return []
    links=db.query(PatientNutritionistLink).filter(clause,PatientNutritionistLink.status=='LINKED',PatientNutritionistLink.tenant_id==actor.tenant_id).all()
    ids={x.nutritionist_id if actor.role_id=='CLIENTE' else x.patient_id for x in links}
    if actor.role_id=='CLIENTE':
        # Company administrators remain reachable when they work in another
        # branch; patients keep their own branch and existing specialist link.
        ids.update(row[0] for row in db.query(User.id).filter(
            User.tenant_id==actor.tenant_id,User.role_id=='ADMIN_ORGANIZATION',User.is_active==True).all())
    return [dict(id=u.id,full_name=u.full_name,role_id=u.role_id) for u in db.query(User).filter(User.id.in_(ids),User.is_active==True).order_by(User.full_name).all()]


def conversation_access(db,actor,peer_id):
    peer=db.query(User).filter_by(id=peer_id,is_active=True).first()
    if not peer or peer.id not in {x['id'] for x in contacts(db,actor)} or not actor.tenant_id or peer.tenant_id!=actor.tenant_id:
        raise HTTPException(403,'Solo puedes conversar con pacientes autorizados o con tu equipo de nutrición de la misma empresa.')
    return peer


def thread(db,actor,peer_id,offset=0,limit=50):
    conversation_access(db,actor,peer_id)
    rows=db.query(CareMessage).filter(CareMessage.tenant_id==actor.tenant_id,or_(
        and_(CareMessage.sender_id==actor.id,CareMessage.recipient_id==peer_id),
        and_(CareMessage.sender_id==peer_id,CareMessage.recipient_id==actor.id))).order_by(CareMessage.created_at.desc(),CareMessage.id.desc()).offset(offset).limit(limit+1).all()
    return dict(items=[dict(id=r.id,sender_id=r.sender_id,recipient_id=r.recipient_id,content=r.content,created_at=iso(r.created_at)) for r in reversed(rows[:limit])],has_more=len(rows)>limit)


def send_message(db,actor,peer_id,body):
    peer=conversation_access(db,actor,peer_id)
    row=CareMessage(tenant_id=actor.tenant_id,sender_id=actor.id,recipient_id=peer.id,content=body.content)
    db.add(row);db.flush()
    db.add(Notification(user_id=peer.id,tenant_id=peer.tenant_id,branch_id=peer.branch_id,title='Nuevo mensaje de tu equipo de nutrición',
        message=f'{actor.full_name} te escribió. Abre Seguimiento y mensajes para leerlo.',type='SISTEMA',reference_id=row.id))
    db.commit()
    return dict(id=row.id,content=row.content,sender_id=row.sender_id,recipient_id=row.recipient_id,created_at=iso(row.created_at))


def duplicate(db,tenant,email,name):
    if db.execute(select(User.__table__.c.id).where(User.__table__.c.email==email)).first(): return 'Correo ya registrado.'
    if db.query(User.id).filter(User.tenant_id==tenant,func.lower(User.full_name)==name.lower(),User.is_active==True).first(): return 'Nombre ya registrado en la empresa.'
    return None


def preview_import(db,actor,body):
    require_role(actor,STAFF)
    if not actor.tenant_id: raise HTTPException(400,'Selecciona una empresa.')
    branch=operation_branch(db,actor.tenant_id,requested=body.branch_id,default=actor.branch_id)
    try:
        reader=csv.DictReader(io.StringIO(body.csv_content.lstrip('\ufeff')),strict=True)
        if not reader.fieldnames or not {'full_name','email','password'}<=set(reader.fieldnames) or set(reader.fieldnames)-{'full_name','email','password','phone'}:
            raise HTTPException(422,'Columnas CSV: full_name,email,password y phone opcional. Usa la plantilla.')
        if len(reader.fieldnames)!=len(set(reader.fieldnames)): raise HTTPException(422,'Hay columnas repetidas.')
        raw=list(reader)
    except csv.Error:
        raise HTTPException(422,'El archivo CSV no tiene una estructura válida.')
    if not raw or len(raw)>100: raise HTTPException(422,'El CSV debe contener entre 1 y 100 pacientes.')
    accepted=[];review=[];emails=set();names=set()
    for number,row in enumerate(raw,2):
        item=dict(row=number,full_name=(row.get('full_name') or '').strip()[:250],email=(row.get('email') or '').strip().lower()[:254],error=None)
        try:
            if None in row or any(v is None for v in row.values()): raise ValueError('Cantidad de columnas incorrecta.')
            data=OrganizationUserCreate(full_name=row['full_name'],email=item['email'],password=row['password'],phone=row.get('phone') or None,
                role_id='CLIENTE',tenant_id=actor.tenant_id,branch_id=branch)
            error=duplicate(db,actor.tenant_id,item['email'],data.full_name)
            if item['email'] in emails or data.full_name.lower() in names: error='Paciente duplicado dentro del archivo.'
            if error: raise ValueError(error)
            accepted.append(dict(row=number,email=item['email'],full_name=data.full_name,phone=data.phone,hashed_password=get_password_hash(data.password),branch_id=branch))
            emails.add(item['email']);names.add(data.full_name.lower())
        except ValidationError as e:
            item['error']='; '.join(str(x['loc'][-1])+': '+x['msg'] for x in e.errors())
        except ValueError as e: item['error']=str(e)
        review.append(item)
    report=dict(total=len(raw),accepted=len(accepted),rejected=len(raw)-len(accepted),rows=review)
    batch=PatientImportBatch(tenant_id=actor.tenant_id,actor_id=actor.id,rows=accepted,preview=report,expires_at=now()+timedelta(minutes=15))
    db.add(batch);db.commit();db.refresh(batch)
    return dict(report,batch_id=batch.id,expires_at=iso(batch.expires_at))


def confirm_import(db,actor,identity):
    require_role(actor,STAFF)
    db.query(Tenant).filter_by(id=actor.tenant_id).with_for_update().first()
    batch=db.query(PatientImportBatch).filter_by(id=identity,actor_id=actor.id,tenant_id=actor.tenant_id).with_for_update().first()
    if not batch: raise HTTPException(404,'Lote no encontrado para tu cuenta.')
    if batch.result is not None: return batch.result
    if batch.expires_at<now(): raise HTTPException(410,'La vista previa venció. Analiza el archivo nuevamente.')
    if not batch.rows: raise HTTPException(422,'No hay filas aceptadas para importar.')
    created=[];errors=[dict(row=r['row'],error=r['error']) for r in batch.preview['rows'] if r.get('error')]
    for values in batch.rows:
        try:
            with db.begin_nested():
                error=duplicate(db,actor.tenant_id,values['email'],values['full_name'])
                if error: raise ValueError(error)
                branch=operation_branch(db,actor.tenant_id,requested=values['branch_id'])
                check_capacity(db,actor.tenant_id,'patients')
                patient=User(email=values['email'],full_name=values['full_name'],phone=values['phone'],hashed_password=values['hashed_password'],
                    role_id='CLIENTE',tenant_id=actor.tenant_id,branch_id=branch,is_active=True,is_verified=True)
                db.add(patient);db.flush()
                if actor.role_id=='NUTRICIONISTA':
                    from app.models.care import identity as new_id
                    db.add(PatientNutritionistLink(tenant_id=actor.tenant_id,branch_id=branch,nutritionist_id=actor.id,patient_id=patient.id,
                        pairing_code=new_id().replace('-','')[:30],status='LINKED',linked_at=now()))
            created.append(dict(row=values['row'],id=patient.id,full_name=patient.full_name))
        except (ValueError,HTTPException,IntegrityError) as e:
            errors.append(dict(row=values['row'],error='Correo duplicado durante la confirmación.' if isinstance(e,IntegrityError) else str(getattr(e,'detail',e))))
    result=dict(total=batch.preview['total'],created=len(created),rejected=len(errors),patients=created,errors=errors)
    batch.result=result;batch.rows=[]
    db.commit()
    return result
