from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import Column, String, Integer, Numeric, Boolean, DateTime, JSON, Text
from app.database import Base


class CommercialPlan(Base):
    __tablename__ = 'commercial_plans'
    code = Column(String(50), primary_key=True)
    display_name = Column(String(100), nullable=False)
    price = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(3), nullable=False, default='USD')
    duration_days = Column(Integer, nullable=False, default=30)
    max_patients = Column(Integer, nullable=True)
    max_branches = Column(Integer, nullable=True)
    features = Column(JSON, nullable=False, default=list)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


class PlatformAudit(Base):
    __tablename__ = 'platform_audit'
    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    actor_id = Column(String(36), nullable=False)
    action = Column(String(60), nullable=False)
    target_id = Column(String(50), nullable=False)
    reason = Column(Text, nullable=False)
    before = Column(JSON, nullable=True)
    after = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
