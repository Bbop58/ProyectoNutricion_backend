from datetime import datetime,timedelta,timezone
from decimal import Decimal
import pytest
from tests.test_platform_console import platform,headers
from app.models.subscription import Subscription
from app.models.subscription_receipt import SubscriptionReceipt
from app.models.subscription_wallet_refund import SubscriptionWalletRefund as Refund
from app.models.wallet import WalletMovement
from app.models.payment import Payment
from app.models.user import User
from app.services.consultation_payment_service import ConsultationPaymentService as Wallet
from app.services.payment_service import PaymentService


@pytest.fixture
def paid(db_session,platform,monkeypatch):
    from app.services.paypal_service import PayPalService
    monkeypatch.setattr(PayPalService,'get_order',lambda order_id:{'status':'COMPLETED',
        'purchase_units':[{'payments':{'captures':[{'id':'CAPTURE-TEST','status':'COMPLETED',
        'amount':{'value':'5.00','currency_code':'USD'}}]}}]})
    started=datetime.now(timezone.utc).replace(tzinfo=None)-timedelta(days=12)
    db_session.add(Subscription(id='personal',user_id='patient',tenant_id='a',branch_id='a1',
        plan_name='CLIENTE_PREMIUM',status='ACTIVE',source='PAYPAL',amount=5,currency='USD',
        paypal_order_id='ORDER-TEST',paypal_capture_id='CAPTURE-TEST',started_at=started,
        expires_at=started+timedelta(days=30)))
    db_session.flush()
    db_session.add(SubscriptionReceipt(id='personal',user_id='patient',tenant_id='a',branch_id='a1',
        buyer_name='patient',buyer_email='patient@example.com',plan_name='CLIENTE_PREMIUM',
        amount=Decimal('5.00'),currency='USD',paypal_order_id='ORDER-TEST',paypal_capture_id='CAPTURE-TEST',
        is_sandbox=True,paid_at=started,expires_at=started+timedelta(days=30)))
    db_session.commit()


def request(client):
    r=client.post('/api/v1/subscriptions/wallet-refunds',headers=headers('patient'),
        json={'subscription_id':'personal','reason':'Quiero devolver el plan completo a mi wallet'})
    assert r.status_code==200,r.text
    return r.json()


def decide(client,identity,decision='APPROVED',who='root'):
    return client.post('/api/v1/platform/wallet-refunds/'+identity+'/decision',headers=headers(who),
        json={'decision':decision,'reason':'Solicitud revisada y validada'})


def test_full_credit_once_and_pdf_and_cash_reconciliation(client,db_session,paid):
    row=request(client)
    assert float(row['amount'])==5 and row['status']=='PENDING'
    assert Wallet.balance(db_session,'patient')==0
    assert db_session.get(Subscription,'personal').status=='ACTIVE'
    assert request(client)['id']==row['id']
    assert client.get('/api/v1/subscriptions/wallet-refunds/'+row['id']+'/pdf',headers=headers('patient')).status_code==409
    for _ in range(2):
        r=decide(client,row['id']);assert r.status_code==200,r.text
    assert Wallet.balance(db_session,'patient')==Decimal('5.00')
    assert db_session.query(WalletMovement).count()==1
    assert db_session.query(Payment).filter_by(purpose='SUBSCRIPTION_REFUND').count()==1
    assert db_session.get(Subscription,'personal').status=='REFUNDED'
    assert db_session.get(Subscription,'original').status=='ACTIVE'
    assert PaymentService.get_payment_stats(db_session).total_collected==0
    assert client.get('/api/v1/subscriptions/current',headers=headers('patient')).json() is None
    r=client.get('/api/v1/subscriptions/wallet-refunds/'+row['id']+'/pdf',headers=headers('patient'))
    assert r.status_code==200 and r.content.startswith(b'%PDF')
    receipts=client.get('/api/v1/my-receipts',headers=headers('patient')).json()
    credit=next(p for p in receipts if p['kind']=='WALLET_REFUND')
    assert credit['pdf_path'].endswith('/'+row['id']+'/pdf')
    assert db_session.get(SubscriptionReceipt,'personal') is not None
    assert decide(client,row['id'],'REJECTED').status_code==409


def test_rejection_preserves_balance_and_access(client,db_session,paid):
    row=request(client);r=decide(client,row['id'],'REJECTED')
    assert r.status_code==200,r.text
    assert Wallet.balance(db_session,'patient')==0
    assert db_session.get(Subscription,'personal').status=='ACTIVE'
    assert decide(client,row['id']).status_code==409
    assert request(client)['status']=='REJECTED'


def test_roles_ownership_and_input_amount_are_not_trusted(client,db_session,paid):
    for who in ['admin','doctor','other','root']:
        assert client.post('/api/v1/subscriptions/wallet-refunds',headers=headers(who),json={
            'subscription_id':'personal','reason':'Quiero saldo'}).status_code==403
    assert client.post('/api/v1/subscriptions/wallet-refunds',headers=headers('patient'),json={
        'subscription_id':'original','reason':'Otro pago'}).status_code==404
    assert client.post('/api/v1/subscriptions/wallet-refunds',headers=headers('patient'),json={
        'subscription_id':'personal','reason':'Quiero saldo','amount':500}).status_code==422
    row=request(client)
    for who in ['admin','doctor','patient','other']:
        assert decide(client,row['id'],who=who).status_code==403
        assert client.get('/api/v1/platform/wallet-refunds',headers=headers(who)).status_code==403
    assert client.get('/api/v1/platform/wallet-refunds',headers=headers('root')).json()['total']==1
    assert client.get('/api/v1/subscriptions/wallet-refunds/'+row['id']+'/pdf',headers=headers('other')).status_code==403


@pytest.mark.parametrize('case',['expired','replaced','demo','unpaid','mismatch','currency','company','missing_receipt','zero','manual'])
def test_ineligible_payments_never_credit(client,db_session,paid,case):
    sub=db_session.get(Subscription,'personal');receipt=db_session.get(SubscriptionReceipt,'personal')
    if case=='expired': sub.expires_at=datetime.now()-timedelta(days=2)
    if case=='replaced': sub.status='REPLACED'
    if case=='demo': sub.paypal_capture_id=receipt.paypal_capture_id='DEMO-CAPTURE'
    if case=='unpaid': sub.status='PENDING'
    if case=='mismatch': receipt.amount=10
    if case=='currency': receipt.currency=sub.currency='EUR'
    if case=='company': receipt.plan_name=sub.plan_name='BASICO'
    if case=='missing_receipt': db_session.delete(receipt)
    if case=='zero': receipt.amount=sub.amount=0
    if case=='manual': sub.source='MANUAL'
    db_session.commit()
    r=client.post('/api/v1/subscriptions/wallet-refunds',headers=headers('patient'),json={
        'subscription_id':'personal','reason':'Devolver a wallet'})
    assert r.status_code==409,r.text
    assert db_session.query(Refund).count()==0
    assert Wallet.balance(db_session,'patient')==0


def test_payment_rechecked_before_approval(client,db_session,paid):
    row=request(client)
    db_session.get(Subscription,'personal').status='CANCELLED';db_session.commit()
    assert decide(client,row['id']).status_code==409
    assert Wallet.balance(db_session,'patient')==0
    assert db_session.get(Refund,row['id']).status=='PENDING'


def test_approval_rollback_is_atomic(client,db_session,paid):
    from sqlalchemy import event
    from app.services.subscription_wallet_refund_service import decide as approve
    row=request(client)
    def fail_during_credit(session,context,instances):
        if any(isinstance(x,WalletMovement) for x in session.new):
            raise RuntimeError('simulated storage failure')
    event.listen(db_session,'before_flush',fail_during_credit)
    try:
        with pytest.raises(RuntimeError,match='simulated'):
            approve(db_session,db_session.get(User,'root'),row['id'],'APPROVED','Revisión completa')
    finally:
        event.remove(db_session,'before_flush',fail_during_credit)
        db_session.rollback()
    assert Wallet.balance(db_session,'patient')==0
    assert db_session.query(Payment).filter_by(purpose='SUBSCRIPTION_REFUND').count()==0
    assert db_session.get(Subscription,'personal').status=='ACTIVE'
    assert db_session.get(Refund,row['id']).status=='PENDING'


def test_credit_can_pay_a_consultation_without_new_cash_income(client,db_session,paid):
    from app.models.appointment import Appointment
    row=request(client);assert decide(client,row['id']).status_code==200
    db_session.add(Appointment(id='use-credit',tenant_id='a',branch_id='a1',patient_id='patient',
        nutritionist_id='doctor',scheduled_at=datetime.now()+timedelta(days=1),status='ACCEPTED'))
    db_session.commit()
    result=Wallet.pay(db_session,db_session.get(User,'patient'),'use-credit','WALLET','')
    assert result['status']=='COMPLETED'
    assert Wallet.balance(db_session,'patient')==0
    assert db_session.query(WalletMovement).count()==2
    assert PaymentService.get_payment_stats(db_session).total_collected==0


@pytest.mark.parametrize('failure',['outage','refunded'])
def test_paypal_is_rechecked_before_wallet_credit(client,db_session,paid,monkeypatch,failure):
    from app.services.paypal_service import PayPalService
    row=request(client)
    if failure=='outage':
        def unavailable(order_id): raise RuntimeError('network unavailable')
        monkeypatch.setattr(PayPalService,'get_order',unavailable)
    else:
        monkeypatch.setattr(PayPalService,'get_order',lambda _: {'status':'COMPLETED',
            'purchase_units':[{'payments':{'captures':[{'id':'CAPTURE-TEST','status':'REFUNDED',
            'amount':{'value':'5.00','currency_code':'USD'}}]}}]})
    assert decide(client,row['id']).status_code==(503 if failure=='outage' else 409)
    assert Wallet.balance(db_session,'patient')==0
    assert db_session.get(Subscription,'personal').status=='ACTIVE'
    assert db_session.get(Refund,row['id']).status=='PENDING'


def test_another_customer_cannot_read_or_refund_the_payment(client,db_session,paid):
    db_session.add(User(id='second',tenant_id='a',branch_id='a1',role_id='CLIENTE',
        full_name='Second customer',email='second@example.test',hashed_password='test'))
    db_session.commit()
    row=request(client);assert decide(client,row['id']).status_code==200
    assert client.get('/api/v1/subscriptions/wallet-refunds',headers=headers('second')).json()==[]
    assert client.get('/api/v1/subscriptions/wallet-refunds/'+row['id']+'/pdf',headers=headers('second')).status_code==404
    assert client.post('/api/v1/subscriptions/wallet-refunds',headers=headers('second'),json={
        'subscription_id':'personal','reason':'Intento de otro cliente'}).status_code==404
    assert Wallet.balance(db_session,'second')==0
