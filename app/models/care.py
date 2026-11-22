"""Small, explicitly scoped records for nutritional follow-up and communication."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Float, Integer, DateTime, JSON, Text, ForeignKey, UniqueConstraint
from app.database import Base


def identity(): return str(uuid.uuid4())
def now(): return datetime.now(timezone.utc).replace(tzinfo=None)


class Measurement(Base):
    __tablename__ = 'patient_measurements'
    id = Column(String(36), primary_key=True, default=identity)
    tenant_id = Column(String(36), ForeignKey('tenants.id'), index=True)
    patient_id = Column(String(36), ForeignKey('users.id'), nullable=False, index=True)
    actor_id = Column(String(36), ForeignKey('users.id'), nullable=False)
    weight_kg = Column(Float, nullable=False)
    height_cm = Column(Float, nullable=False)
    measured_at = Column(DateTime, nullable=False, default=now)
    created_at = Column(DateTime, nullable=False, default=now)


class NutritionConfiguration(Base):
    __tablename__ = 'nutrition_configurations'
    __table_args__ = (UniqueConstraint('tenant_id', 'version'),)
    id = Column(String(36), primary_key=True, default=identity)
    tenant_id = Column(String(36), ForeignKey('tenants.id'), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    values = Column(JSON, nullable=False)
    actor_id = Column(String(36), ForeignKey('users.id'), nullable=False)
    reason = Column(String(500), nullable=False)
    created_at = Column(DateTime, nullable=False, default=now)


class CareAssessment(Base):
    __tablename__ = 'care_assessments'
    id = Column(String(36), primary_key=True, default=identity)
    tenant_id = Column(String(36), ForeignKey('tenants.id'), index=True)
    patient_id = Column(String(36), ForeignKey('users.id'), nullable=False, index=True)
    actor_id = Column(String(36), ForeignKey('users.id'), nullable=False)
    snapshot = Column(JSON, nullable=False)
    created_at = Column(DateTime, nullable=False, default=now)


class PlanReview(Base):
    __tablename__ = 'plan_reviews'
    id = Column(String(36), primary_key=True, default=identity)
    tenant_id = Column(String(36), ForeignKey('tenants.id'), index=True)
    plan_id = Column(String(36), ForeignKey('nutritional_plans.id'), nullable=False, index=True)
    actor_id = Column(String(36), ForeignKey('users.id'), nullable=False)
    decision = Column(String(20), nullable=False)
    reason = Column(String(2000), nullable=False)
    before = Column(JSON, nullable=False)
    after = Column(JSON, nullable=False)
    created_at = Column(DateTime, nullable=False, default=now)


class CareMessage(Base):
    __tablename__ = 'care_messages'
    id = Column(String(36), primary_key=True, default=identity)
    tenant_id = Column(String(36), ForeignKey('tenants.id'), nullable=False, index=True)
    sender_id = Column(String(36), ForeignKey('users.id'), nullable=False, index=True)
    recipient_id = Column(String(36), ForeignKey('users.id'), nullable=False, index=True)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=now)


class PatientImportBatch(Base):
    __tablename__ = 'patient_import_batches'
    id = Column(String(36), primary_key=True, default=identity)
    tenant_id = Column(String(36), ForeignKey('tenants.id'), nullable=False, index=True)
    actor_id = Column(String(36), ForeignKey('users.id'), nullable=False)
    rows = Column(JSON, nullable=False)
    preview = Column(JSON, nullable=False)
    result = Column(JSON, nullable=True)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, nullable=False, default=now)


class PlatformIncident(Base):
    __tablename__ = 'platform_incidents'
    id = Column(String(36), primary_key=True, default=identity)
    method = Column(String(10), nullable=False)
    route = Column(String(200), nullable=False)
    error_type = Column(String(100), nullable=False)
    status = Column(String(20), nullable=False, default='OPEN')
    resolution = Column(String(500), nullable=True)
    resolved_by = Column(String(36), ForeignKey('users.id'), nullable=True)
    created_at = Column(DateTime, nullable=False, default=now)
    resolved_at = Column(DateTime, nullable=True)
