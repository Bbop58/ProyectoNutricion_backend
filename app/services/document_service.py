from datetime import timezone, timedelta
from io import BytesIO
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from app.core.exceptions import ForbiddenException, NotFoundException, BadRequestException
from app.models.appointment import Appointment
from app.models.payment import Payment
from app.models.company import Branch
from app.models.subscription import Subscription
from app.models.tenant import Tenant
from app.models.commercial_plan import PlatformAudit


def stamp(value):
    if not value: return 'Sin fecha'
    return value.replace(tzinfo=value.tzinfo or timezone.utc).astimezone(timezone(timedelta(hours=-4))).strftime('%d/%m/%Y %H:%M')


def pdf(title, rows, note):
    stream = BytesIO()
    styles = getSampleStyleSheet()
    def text(value): return Paragraph(escape(str(value or '—')), styles['BodyText'])
    table = Table([[text(label), text(value)] for label, value in rows], colWidths=[140, 350])
    table.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'), ('BOTTOMPADDING',(0,0),(-1,-1),10),
        ('LINEBELOW',(0,0),(-1,-1),0.3,colors.HexColor('#dfece9'))]))
    SimpleDocTemplate(stream, title=title, author='NutriSalud').build([
        Paragraph('NutriSalud', styles['Title']), Paragraph(title, styles['Heading2']), Spacer(1,16),
        table, Spacer(1,20), text(note), text('Fechas en horario de Bolivia (UTC−4).')])
    stream.seek(0)
    return stream


def appointment_access(db, user, identity):
    row = db.query(Appointment).filter_by(id=identity).first()
    if not row: raise NotFoundException('Cita no encontrada.')
    if user.role_id == 'CLIENTE':
        if row.patient_id != user.id: raise ForbiddenException('Solo puedes descargar tus citas.')
    elif user.role_id in {'ADMIN_ORGANIZATION','NUTRICIONISTA'}:
        if row.tenant_id != user.tenant_id or (user.role_id == 'NUTRICIONISTA' and row.nutritionist_id != user.id):
            raise ForbiddenException('No tienes acceso a esta cita.')
    else: raise ForbiddenException('No tienes acceso a esta cita.')
    return row


def appointment_pdf(db, user, identity):
    row = appointment_access(db,user,identity)
    branch = db.get(Branch,row.branch_id) if row.branch_id else None
    payment = db.query(Payment).filter_by(appointment_id=row.id,status='COMPLETED').first()
    states = {'PENDING':'Solicitada','ACCEPTED':'Aceptada, pendiente de pago','CONFIRMED':'Confirmada','COMPLETED':'Atendida','CANCELLED':'Cancelada'}
    rows = [('Referencia', row.id), ('Empresa',row.tenant.name if row.tenant else None),('Sucursal',branch.name if branch else None),
        ('Paciente',row.patient.full_name),('Profesional',row.nutritionist.full_name),('Fecha y hora',stamp(row.scheduled_at)),
        ('Estado',states.get(row.status,row.status)),('Motivo de consulta',row.reason),
        ('Pago','Confirmado' if payment else 'Sin pago confirmado')]
    if row.status == 'CANCELLED': rows.append(('Motivo de cancelación',row.cancellation_reason))
    return pdf('Constancia de cancelación' if row.status == 'CANCELLED' else 'Constancia de cita', rows,
        'Esta constancia refleja el estado actual de la cita. No sustituye un recibo de pago ni acredita un reembolso.')


def assignment_pdf(db, user, identity):
    row = db.query(Subscription).filter_by(id=identity,source='MANUAL').first()
    if not row: raise NotFoundException('Asignación manual no encontrada.')
    if user.role_id != 'SUPERADMIN' and (user.role_id != 'ADMIN_ORGANIZATION' or row.tenant_id != user.tenant_id):
        raise ForbiddenException('No tienes acceso a esta asignación.')
    company = db.get(Tenant,row.tenant_id)
    event = db.query(PlatformAudit).filter_by(action='PLAN_ASIGNADO',target_id=row.tenant_id).order_by(PlatformAudit.created_at.desc()).all()
    event = next((e for e in event if (e.after or {}).get('subscription_id') == row.id), None)
    from app.models.user import User
    actor = db.get(User,event.actor_id) if event else None
    return pdf('Nota de asignación de plan', [('Referencia',row.id),('Empresa',company.name if company else None),
        ('Plan',(row.plan_snapshot or {}).get('display_name',row.plan_name)),('Inicio',stamp(row.started_at)),
        ('Vencimiento',stamp(row.expires_at)),('Estado',row.status),('Asignado por',actor.full_name if actor else 'Administración de plataforma'),
        ('Motivo',event.reason if event else 'Asignación administrativa'),('Cobro','Sin cobro')],
        'Asignación administrativa sin cobro. Esta nota no es un recibo de pago ni una factura fiscal.')
