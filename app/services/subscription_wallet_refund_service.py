from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid5, NAMESPACE_URL
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from app.models.subscription import Subscription
from app.models.subscription_receipt import SubscriptionReceipt
from app.models.subscription_wallet_refund import SubscriptionWalletRefund as Refund
from app.models.user import User
from app.models.payment import Payment
from app.models.wallet import WalletMovement
from app.models.notification import Notification
from app.models.commercial_plan import PlatformAudit
from app.core.authorization import require_role
from app.services.paypal_service import PayPalService


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def naive(value):
    return value.replace(tzinfo=value.tzinfo or timezone.utc).astimezone(timezone.utc).replace(tzinfo=None)


def view(row):
    return {key: getattr(row, key) for key in ['id','subscription_id','amount','currency','is_sandbox',
        'status','reason','decision_reason','created_at','decided_at']}


def eligible(db, user, sub):
    if sub is None or sub.user_id != user.id:
        raise HTTPException(404, 'Suscripción no encontrada para tu cuenta.')
    if sub.plan_name != 'CLIENTE_PREMIUM' or sub.source != 'PAYPAL':
        raise HTTPException(409, 'Solo se devuelve el Premium IA personal pagado con PayPal.')
    if sub.status != 'ACTIVE' or not sub.expires_at or naive(sub.expires_at) <= now():
        raise HTTPException(409, 'La suscripción debe estar vigente para solicitar o aprobar la devolución.')
    receipt = db.get(SubscriptionReceipt, sub.id)
    if not receipt or receipt.user_id != user.id or receipt.plan_name != 'CLIENTE_PREMIUM':
        raise HTTPException(409, 'Falta el comprobante de pago confirmado de esta suscripción.')
    amount = Decimal(str(receipt.amount)).quantize(Decimal('0.01'))
    if (amount <= 0 or receipt.currency != 'USD' or sub.currency != 'USD'
        or amount != Decimal(str(sub.amount)).quantize(Decimal('0.01'))
        or not receipt.paypal_capture_id or not receipt.paypal_order_id
        or receipt.paypal_capture_id != sub.paypal_capture_id or receipt.paypal_order_id != sub.paypal_order_id
        or receipt.paypal_capture_id.upper().startswith('DEMO-') or receipt.paypal_order_id.upper().startswith('DEMO-')):
        raise HTTPException(409, 'El pago no es válido para devolverlo a la wallet. Los datos DEMO no son reembolsables.')
    if not user.tenant_id or not user.branch_id:
        raise HTTPException(409, 'Tu cuenta necesita empresa y sucursal para utilizar la wallet.')
    return receipt, amount


def request_refund(db, user, subscription_id, reason):
    require_role(user, {'CLIENTE'})
    sub = db.query(Subscription).filter_by(id=subscription_id, user_id=user.id).with_for_update(of=Subscription).first()
    if sub is None: raise HTTPException(404, 'Suscripción no encontrada para tu cuenta.')
    previous = db.query(Refund).filter_by(subscription_id=sub.id).first()
    if previous: return view(previous)
    receipt, amount = eligible(db, user, sub)
    if db.query(Refund).filter_by(capture_id=receipt.paypal_capture_id).first():
        raise HTTPException(409, 'Este pago ya tiene una solicitud de devolución.')
    identity = str(uuid5(NAMESPACE_URL, 'premium-wallet-refund:'+sub.id))
    row = Refund(id=identity, subscription_id=sub.id, user_id=user.id, capture_id=receipt.paypal_capture_id,
                 amount=amount, currency='USD', is_sandbox=receipt.is_sandbox, reason=reason)
    db.add(row)
    db.add(PlatformAudit(actor_id=user.id,action='DEVOLUCION_SOLICITADA',target_id=row.id,reason=reason,
                        after={'subscription_id':sub.id,'amount':str(amount),'currency':'USD'}))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        previous=db.query(Refund).filter_by(subscription_id=subscription_id,user_id=user.id).first()
        if previous: return view(previous)
        raise HTTPException(409,'Este pago ya tiene una solicitud de devolución.')
    return view(row)


def decide(db, actor, identity, decision, reason):
    require_role(actor, {'SUPERADMIN'})
    existing = db.get(Refund, identity)
    if existing is None: raise HTTPException(404, 'Solicitud no encontrada.')
    # Lock subscription first, matching request/cancel/capture, then the decision.
    sub = db.query(Subscription).filter_by(id=existing.subscription_id).with_for_update(of=Subscription).one()
    row = db.query(Refund).filter_by(id=identity).with_for_update(of=Refund).populate_existing().one()
    if row.status != 'PENDING':
        if row.status == decision: return view(row)
        raise HTTPException(409, 'La solicitud ya tiene una decisión definitiva.')
    user = db.query(User).filter_by(id=row.user_id).with_for_update(of=User).one()
    if decision == 'APPROVED':
        if not user.is_active: raise HTTPException(409, 'La cuenta del cliente está inactiva.')
        receipt, amount = eligible(db,user,sub)
        if amount != row.amount or receipt.paypal_capture_id != row.capture_id or receipt.is_sandbox != row.is_sandbox:
            raise HTTPException(409, 'El pago cambió desde la solicitud; revisa la operación.')
        try:
            order=PayPalService.get_order(receipt.paypal_order_id)
        except Exception:
            raise HTTPException(503,'No se pudo verificar el pago con PayPal. La solicitud sigue pendiente y no se acreditó saldo.')
        try:
            capture=PayPalService.validate_completed_payment(order,amount,'USD')
            if capture['id'] != row.capture_id: raise ValueError('Otra captura')
        except ValueError:
            raise HTTPException(409,'PayPal no confirma el pago original íntegro. No se acreditó saldo; revisa si ya fue reembolsado.')
        payment = Payment(id=row.id,tenant_id=user.tenant_id,branch_id=user.branch_id,patient_id=user.id,
            purpose='SUBSCRIPTION_REFUND',customer_name=user.full_name,customer_email=user.email,
            concept='Devolución total de Premium IA a wallet',amount=float(amount),currency='USD',
            status='COMPLETED',payment_method='WALLET_CREDIT',paid_at=now(),
            notes='Crédito interno por devolución de suscripción; no es un cobro ni un reembolso a PayPal.')
        db.add(payment)
        db.flush()
        db.add(WalletMovement(id=row.id,user_id=user.id,tenant_id=user.tenant_id,branch_id=user.branch_id,
            payment_id=payment.id,amount=amount,concept=payment.concept))
        row.payment_id=payment.id
        sub.status='REFUNDED'
        message=f'Se acreditaron USD {amount:.2f} a tu wallet y se cerró el Premium de ese período. Tu comprobante está disponible.'
    else:
        message='Tu solicitud de devolución fue rechazada. Revisa el motivo en Devoluciones a wallet.'
    row.status=decision;row.decision_reason=reason;row.decided_by=actor.id;row.decided_at=now()
    db.add(PlatformAudit(actor_id=actor.id,action='DEVOLUCION_'+decision,target_id=row.id,reason=reason,
        after={'subscription_id':sub.id,'amount':str(row.amount),'currency':row.currency,'payment_id':row.payment_id}))
    db.add(Notification(user_id=user.id,tenant_id=user.tenant_id,branch_id=user.branch_id,
        title='Devolución a wallet aprobada' if decision=='APPROVED' else 'Devolución a wallet rechazada',
        message=message,type='PAGO',reference_id=row.id))
    db.commit()
    return view(row)


def receipt_pdf(db, user, identity):
    row=db.get(Refund,identity)
    if row is None or (user.role_id!='SUPERADMIN' and (user.role_id!='CLIENTE' or row.user_id!=user.id)):
        raise HTTPException(404,'Comprobante no encontrado para tu cuenta.')
    if row.status!='APPROVED': raise HTTPException(409,'El comprobante se emite cuando la devolución está aprobada.')
    from app.services.document_service import pdf, stamp
    owner=db.get(User,row.user_id)
    return pdf('Comprobante de devolución a wallet',[
        ('Referencia',row.id),('Cliente',owner.full_name),('Correo',owner.email),
        ('Suscripción',row.subscription_id),('Importe acreditado',f'{row.amount:.2f} {row.currency}'),
        ('Destino','Wallet del cliente · saldo para consultas'),('Aprobado',stamp(row.decided_at)),
        ('Motivo de solicitud',row.reason),('Motivo de aprobación',row.decision_reason)],
        ('SANDBOX: operación de prueba. ' if row.is_sandbox else '')+
        'Se devolvió todo el importe como crédito interno y se cerró el Premium de ese período. '
        'No se transfirió dinero a PayPal. No es una factura fiscal.')
