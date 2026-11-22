"""Email existing authorized downloads; never accept arbitrary URLs or attachments."""
import re
from urllib.parse import urlsplit, parse_qs
from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session
from app.api.deps import get_current_user
from app.database import get_db
from app.schemas.report import ReportQueryRequest
from app.services.email_service import EmailService

router = APIRouter(tags=['Documentos por correo'])


class DocumentEmailRequest(BaseModel):
    email: EmailStr
    paths: list[str] = Field(min_length=1, max_length=2)
    report_request: ReportQueryRequest | None = None


def resolve_download(path, report_request, user, db):
    from app.api.v1 import appointments, subscriptions, payments, platform, reports
    url = urlsplit(path)
    if url.scheme or url.netloc or url.fragment or not path.startswith('/'):
        raise HTTPException(422, 'Documento no válido.')
    route = url.path
    is_platform_note = re.fullmatch(r'/platform/subscriptions/([\w-]+)/pdf', route)
    if user.role_id == 'SUPERADMIN' and not is_platform_note:
        raise HTTPException(403, 'Solo puedes enviar notas de asignación de la plataforma.')
    if is_platform_note:
        if user.role_id != 'SUPERADMIN':
            raise HTTPException(403, 'No tienes acceso a la plataforma.')
        return platform.assignment_document(is_platform_note[1], user, db)
    match = re.fullmatch(r'/appointments/([\w-]+)/(pdf|receipt/pdf)', route)
    if match:
        action = appointments.appointment_document if match[2] == 'pdf' else appointments.appointment_receipt
        return action(match[1], db, user)
    match = re.fullmatch(r'/payments/([\w-]+)/pdf', route)
    if match:
        return payments.export_payment_pdf(match[1], db, user)
    match = re.fullmatch(r'/subscriptions/receipts/([\w-]+)/pdf', route)
    if match:
        return subscriptions.download_receipt(match[1], db, user)
    match = re.fullmatch(r'/subscriptions/([\w-]+)/assignment/pdf', route)
    if match:
        from app.services.document_service import assignment_pdf
        from fastapi.responses import StreamingResponse
        identity = match[1]
        if identity == 'current':
            sub = subscriptions.get_current_subscription(db,user)
            if sub is None:
                raise HTTPException(404, 'No tienes una asignación de plan vigente.')
            identity = sub.id
        return StreamingResponse(assignment_pdf(db,user,identity), media_type='application/pdf',
            headers={'Content-Disposition': f'attachment; filename="Nota_plan_{identity}.pdf"'})
    if route.startswith('/reports/'):
        reports.report_user(user, db, '')
        reports.ensure_staff(user)
        query = parse_qs(url.query)
        if set(query) - {'file_format', 'entity', 'start_date', 'end_date'} or any(len(v) != 1 for v in query.values()):
            raise HTTPException(422, 'Parámetros de reporte no válidos.')
        fmt = query.get('file_format', ['pdf'])[0]
        if fmt not in {'pdf', 'excel'}:
            raise HTTPException(422, 'Formato no válido.')
        match = re.fullmatch(r'/reports/export/(pdf|excel)', route)
        if match:
            if report_request is None:
                raise HTTPException(422, 'Falta la consulta del reporte.')
            action = reports.export_report_pdf if match[1] == 'pdf' else reports.export_report_excel
            return action(report_request, user, db)
        match = re.fullmatch(r'/reports/saved/([\w-]+)/export', route)
        if match:
            return reports.export_saved_report(match[1], fmt, user, db)
        if route == '/reports/mine/export':
            entity = query.get('entity', ['food'])[0]
            if entity not in {'food', 'appointments', 'payments', 'subscriptions'}:
                raise HTTPException(422, 'Reporte personal no válido.')
            return reports.export_my_report(entity, fmt, query.get('start_date',[None])[0],
                query.get('end_date',[None])[0], user, db)
    raise HTTPException(422, 'Este documento no está disponible para envío.')


@router.post('/documents/email')
@router.post('/platform/documents/email')
async def email_documents(body: DocumentEmailRequest, user=Depends(get_current_user), db: Session=Depends(get_db)):
    attachments = []
    total = 0
    for path in dict.fromkeys(body.paths):
        response = await run_in_threadpool(resolve_download, path, body.report_request, user, db)
        content = bytearray()
        async for chunk in response.body_iterator:
            content.extend(chunk if isinstance(chunk, bytes) else chunk.encode())
            if total + len(content) > 8 * 1024 * 1024:
                raise HTTPException(413, 'Los adjuntos superan 8 MB. Reduce el reporte o envía un formato a la vez.')
        total += len(content)
        disposition = response.headers.get('content-disposition', '')
        filename = re.search(r'filename="?([^";]+)', disposition)
        attachments.append((filename[1] if filename else 'Documento.pdf', bytes(content)))
    sent = await run_in_threadpool(EmailService.send_documents, str(body.email), attachments)
    if not sent:
        raise HTTPException(503, 'No se pudo enviar el correo. Revisa el destinatario o intenta nuevamente.')
    return {'message': 'Documentos enviados al correo.', 'email': str(body.email)}
