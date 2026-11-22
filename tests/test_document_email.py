from datetime import datetime
import base64
import httpx
from tests.test_platform_console import platform, headers
from app.models.appointment import Appointment
from app.services.email_service import EmailService
from app.config import settings


def test_edited_recipient_and_document_permissions(client, db_session, platform, monkeypatch):
    db_session.add(Appointment(id='visit',tenant_id='a',branch_id='a1',patient_id='patient',nutritionist_id='doctor',scheduled_at=datetime.now(),status='CANCELLED',cancellation_reason='Reprogramación'))
    db_session.commit()
    sent=[]
    monkeypatch.setattr(EmailService,'send_documents',lambda email, attachments: sent.append((email, attachments)) or True)
    body={'email':'real.recipient@gmail.com','paths':['/appointments/visit/pdf']}
    r=client.post('/api/v1/documents/email',headers=headers('patient'),json=body)
    assert r.status_code == 200,r.text
    assert sent[0][0] == body['email']
    assert sent[0][1][0][1].startswith(b'%PDF')
    assert db_session.get(__import__('app.models.user',fromlist=['User']).User,'patient').email == 'patient@example.com'
    assert client.post('/api/v1/documents/email',headers=headers('other'),json=body).status_code in (403,404)
    assert client.post('/api/v1/platform/documents/email',headers=headers(),json=body).status_code == 403
    assert len(sent)==1
    for path in ['https://example.com/a.pdf','/backup/download','//example.com/a','/reports/mine/export?file_format=zip']:
        assert client.post('/api/v1/documents/email',headers=headers('admin'),json={**body,'paths':[path]}).status_code == 422
    assert client.post('/api/v1/documents/email',headers=headers('admin'),json={**body,'email':'invalid'}).status_code == 422


def test_reports_pdf_excel_and_provider_failure(client, platform, monkeypatch):
    sent=[]
    monkeypatch.setattr(EmailService,'send_documents',lambda email, attachments: sent.append(attachments) or True)
    query={'entity':'patients','columns':['full_name','email'],'tenant_ids':['a']}
    body={'email':'test@gmail.com','paths':['/reports/export/pdf','/reports/export/excel'],'report_request':query}
    r=client.post('/api/v1/documents/email',headers=headers('admin'),json=body)
    assert r.status_code == 200,r.text
    assert len(sent[0]) == 2
    assert sent[0][0][1].startswith(b'%PDF') and sent[0][1][1].startswith(b'PK')
    monkeypatch.setattr(EmailService,'send_documents',lambda *args:False)
    assert client.post('/api/v1/documents/email',headers=headers('admin'),json=body).status_code == 503
    assert client.post('/api/v1/documents/email',headers=headers('admin'),json={**body,'report_request':None}).status_code == 422


def test_platform_note_can_be_emailed_only_by_authorized_user(client, platform, monkeypatch):
    monkeypatch.setattr(EmailService,'send_documents',lambda *args:True)
    assigned=client.put('/api/v1/platform/companies/a/subscription',headers=headers(),json={'plan_code':'BASICO','reason':'Cortesía'}).json()
    body={'email':'test@gmail.com','paths':['/platform/subscriptions/'+assigned['id']+'/pdf']}
    assert client.post('/api/v1/platform/documents/email',headers=headers(),json=body).status_code == 200
    assert client.post('/api/v1/documents/email',headers=headers('admin'),json=body).status_code == 403
    body['paths']=['/subscriptions/current/assignment/pdf']
    assert client.post('/api/v1/documents/email',headers=headers('admin'),json=body).status_code == 200


def test_brevo_attachment_payload_and_errors(monkeypatch):
    monkeypatch.setattr(settings,'BREVO_API_KEY','test-key')
    captured=[]
    def post(*args,**kwargs):
        captured.append(kwargs['json'])
        return httpx.Response(201,json={'messageId':'test'})
    monkeypatch.setattr(httpx,'post',post)
    assert EmailService.send_documents('edited@gmail.com',[('test.pdf',b'%PDF document')])
    assert captured[0]['to']==[{'email':'edited@gmail.com'}]
    assert base64.b64decode(captured[0]['attachment'][0]['content'])==b'%PDF document'
    monkeypatch.setattr(httpx,'post',lambda *a,**k:httpx.Response(400))
    assert not EmailService.send_documents('edited@gmail.com',[('test.pdf',b'%PDF')])
