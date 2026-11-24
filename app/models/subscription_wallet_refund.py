import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, ForeignKey, Numeric, DateTime, Boolean
from app.database import Base


class SubscriptionWalletRefund(Base):
    """Platform financial record; never part of company operational restores."""
    __tablename__ = 'subscription_wallet_refunds'
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    subscription_id = Column(String(36), ForeignKey('subscriptions.id'), nullable=False, unique=True)
    user_id = Column(String(36), ForeignKey('users.id'), nullable=False, index=True)
    capture_id = Column(String(100), nullable=False, unique=True)
    amount = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(3), nullable=False, default='USD')
    is_sandbox = Column(Boolean, nullable=False)
    status = Column(String(20), nullable=False, default='PENDING', index=True)
    reason = Column(String(500), nullable=False)
    decision_reason = Column(String(500))
    decided_by = Column(String(36), ForeignKey('users.id'))
    decided_at = Column(DateTime)
    payment_id = Column(String(36), ForeignKey('payments.id'), unique=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
