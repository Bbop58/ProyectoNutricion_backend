from datetime import datetime
from tests.test_platform_console import platform, headers
from app.models.appointment import Appointment
from app.models.payment import Payment


def test_appointment_documents_and_receipts(client, db_session, platform):
    a = Appointment(id='visit', tenant_id='a', branch_id='a1', patient_id='patient', nutritionist_id='doctor', scheduled_at=datetime(2026,11,22,16), status='PENDING', reason='Consulta <de control>')
    db_session.add(a); db_session.commit()
    for who in ['patient','doctor','admin']:
        r = client.get('/api/v1/appointments/visit/pdf', headers=headers(who))
        assert r.status_code == 200, r.text
        assert r.content.startswith(b'%PDF') and 'attachment' in r.headers['content-disposition']
    for who in ['other','root']:
        assert client.get('/api/v1/appointments/visit/pdf',headers=headers(who)).status_code in (403,404)
    assert client.get('/api/v1/appointments/visit/receipt/pdf',headers=headers('patient')).status_code == 404
    a.status='CANCELLED';a.cancellation_reason='Cancelada por el paciente';db_session.commit()
    assert client.get('/api/v1/appointments/visit/pdf',headers=headers('patient')).status_code == 200
    db_session.add(Payment(id='paid',tenant_id='a',branch_id='a1',patient_id='patient',appointment_id='visit',purpose='CONSULTATION',customer_name='patient',concept='Consulta',amount=5,currency='USD',status='COMPLETED',payment_method='EFECTIVO',paid_at=datetime.now()))
    db_session.commit()
    r=client.get('/api/v1/appointments/visit/receipt/pdf',headers=headers('patient'))
    assert r.status_code == 200, r.text
    assert r.content.startswith(b'%PDF')


def test_manual_assignment_note_is_authorized_and_without_charge(client, db_session, platform):
    assigned=client.put('/api/v1/platform/companies/a/subscription',headers=headers(),json={'plan_code':'BASICO','reason':'Acceso de cortesía'})
    assert assigned.status_code == 200,assigned.text
    identity=assigned.json()['id']
    for path,who in [(f'/platform/subscriptions/{identity}/pdf','root'),(f'/subscriptions/{identity}/assignment/pdf','admin')]:
        r=client.get('/api/v1'+path,headers=headers(who))
        assert r.status_code == 200,r.text
        assert r.content.startswith(b'%PDF')
    assert client.get(f'/api/v1/subscriptions/{identity}/assignment/pdf',headers=headers('other')).status_code in (403,404)
    assert client.get('/api/v1/subscriptions/original/assignment/pdf',headers=headers('admin')).status_code == 404
    assert db_session.query(Payment).count() == 0
