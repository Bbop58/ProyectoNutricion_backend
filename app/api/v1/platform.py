from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.database import get_db
from app.api.deps import get_current_user
from app.core.authorization import require_role
from app.core.exceptions import BadRequestException, NotFoundException, ConflictException
from app.models.commercial_plan import CommercialPlan, PlatformAudit
from app.models.tenant import Tenant
from app.models.company import Branch, CompanyAdministrator
from app.models.user import User
from app.models.subscription import Subscription
from app.services.commercial_plan_service import plan_dict

router = APIRouter(prefix='/platform', tags=['Administración de plataforma'])


def platform_user(user=Depends(get_current_user)):
    require_role(user, {'SUPERADMIN'})
    return user


def now(): return datetime.now(timezone.utc).replace(tzinfo=None)


def audit(db, actor, action, target, reason, before=None, after=None):
    db.add(PlatformAudit(actor_id=actor.id, action=action, target_id=target, reason=reason, before=before, after=after))


def company_or_404(db, identity):
    row = db.get(Tenant, identity)
    if row is None: raise NotFoundException('Empresa no encontrada.')
    return row


def subscription_dict(row):
    status = 'EXPIRED' if row.status == 'ACTIVE' and row.expires_at and row.expires_at < now() else row.status
    return dict(id=row.id, tenant_id=row.tenant_id, plan_name=row.plan_name, status=status,
                amount=row.amount, currency=row.currency, started_at=row.started_at, expires_at=row.expires_at,
                source=row.source, created_at=row.created_at)


def company_dict(db, row):
    assignment = db.get(CompanyAdministrator, row.id)
    admin = db.get(User, assignment.user_id) if assignment else None
    query = db.query(Subscription).filter(Subscription.tenant_id == row.id, ~Subscription.plan_name.like('CLIENTE_%'))
    subscription = query.filter(Subscription.status == 'ACTIVE', Subscription.expires_at > now()).order_by(Subscription.created_at.desc()).first()
    if subscription is None: subscription = query.order_by(Subscription.created_at.desc()).first()
    return dict(id=row.id, name=row.name, code=row.code, email=row.email, phone=row.phone,
                is_active=row.is_active, branch_count=db.query(Branch).filter_by(tenant_id=row.id).count(),
                administrator={'name': admin.full_name, 'email': admin.email} if admin else None,
                subscription=subscription_dict(subscription) if subscription else None)


@router.get('/overview')
def overview(user=Depends(platform_user), db: Session=Depends(get_db)):
    companies = db.query(Tenant).all()
    subscriptions = db.query(Subscription).filter(Subscription.tenant_id.isnot(None),
        ~Subscription.plan_name.like('CLIENTE_%')).all()
    active = [s for s in subscriptions if s.status == 'ACTIVE' and s.expires_at and s.expires_at > now()]
    return dict(companies=len(companies), active_companies=sum(c.is_active for c in companies),
        inactive_companies=sum(not c.is_active for c in companies), active_subscriptions=len(active),
        expiring_subscriptions=sum(s.expires_at <= now() + timedelta(days=7) for s in active))


@router.get('/companies')
def companies(q: str='', offset: int=Query(0, ge=0), limit: int=Query(50, ge=1, le=100),
              user=Depends(platform_user), db: Session=Depends(get_db)):
    query = db.query(Tenant)
    if q.strip(): query = query.filter(Tenant.name.ilike('%' + q.strip() + '%'))
    return dict(total=query.count(), items=[company_dict(db, c) for c in query.order_by(Tenant.name).offset(offset).limit(limit).all()])


@router.get('/companies/{identity}')
def company(identity: str, user=Depends(platform_user), db: Session=Depends(get_db)):
    return company_dict(db, company_or_404(db, identity))


class StatusChange(BaseModel):
    is_active: bool
    reason: str = Field(min_length=3, max_length=500)

    @field_validator('reason')
    @classmethod
    def valid_reason(cls, value):
        value = value.strip()
        if len(value) < 3: raise ValueError('Indica un motivo de al menos tres caracteres.')
        return value


@router.patch('/companies/{identity}/status')
def status(identity: str, data: StatusChange, user=Depends(platform_user), db: Session=Depends(get_db)):
    row = company_or_404(db, identity)
    before = {'is_active': row.is_active}
    row.is_active = data.is_active
    audit(db, user, 'EMPRESA_ESTADO', identity, data.reason, before, {'is_active': row.is_active})
    db.commit()
    return company_dict(db, row)


class PlanInput(BaseModel):
    code: str = Field(pattern=r'^[A-Z][A-Z0-9_]{1,49}$')
    display_name: str = Field(min_length=2, max_length=100)
    price: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    currency: Literal['USD'] = 'USD'
    duration_days: int = Field(30, ge=1, le=366)
    max_patients: int | None = Field(None, ge=1, le=1000000)
    max_branches: int | None = Field(None, ge=1, le=10000)
    is_active: bool = True
    reason: str = Field(min_length=3, max_length=500)

    @field_validator('display_name', 'reason')
    @classmethod
    def nonblank(cls, value, info):
        value = value.strip()
        if len(value) < (3 if info.field_name == 'reason' else 2): raise ValueError('Completa el campo sin dejar solo espacios.')
        return value


@router.get('/plans')
def plans(user=Depends(platform_user), db: Session=Depends(get_db)):
    return [dict(**plan_dict(row), code=row.code, is_active=row.is_active) for row in db.query(CommercialPlan).order_by(CommercialPlan.price).all()]


def write_plan(db, user, data, row=None):
    if data.code.startswith('CLIENTE_'): raise BadRequestException('Este catálogo administra planes de empresas.')
    before = dict(plan_dict(row), is_active=row.is_active) if row else None
    if row and row.code != data.code: raise BadRequestException('El código de un plan no se puede cambiar.')
    if not row:
        if db.get(CommercialPlan, data.code): raise ConflictException('Ese código de plan ya existe.')
        row = CommercialPlan(code=data.code)
        db.add(row)
    for field in ('display_name','price','currency','duration_days','max_patients','max_branches','is_active'):
        setattr(row, field, getattr(data, field))
    row.features = [dict(text=f"Hasta {data.max_patients} pacientes" if data.max_patients else 'Pacientes ilimitados', included=True),
                    dict(text=f"Hasta {data.max_branches} sucursales" if data.max_branches else 'Sucursales ilimitadas', included=True)]
    after = dict(plan_dict(row), is_active=row.is_active)
    audit(db, user, 'PLAN_EDITADO' if before else 'PLAN_CREADO', row.code, data.reason, before, after)
    db.commit()
    return dict(after, code=row.code)


@router.post('/plans', status_code=201)
def create_plan(data: PlanInput, user=Depends(platform_user), db: Session=Depends(get_db)):
    return write_plan(db, user, data)


@router.patch('/plans/{code}')
def update_plan(code: str, data: PlanInput, user=Depends(platform_user), db: Session=Depends(get_db)):
    row = db.get(CommercialPlan, code)
    if not row: raise NotFoundException('Plan no encontrado.')
    return write_plan(db, user, data, row)


class Assignment(BaseModel):
    plan_code: str
    reason: str = Field(min_length=3, max_length=500)

    _valid_reason = field_validator('reason')(StatusChange.valid_reason.__func__)


@router.put('/companies/{identity}/subscription')
def assign(identity: str, data: Assignment, user=Depends(platform_user), db: Session=Depends(get_db)):
    company_or_404(db, identity)
    db.execute(select(Tenant.id).where(Tenant.id == identity).with_for_update())
    plan = db.get(CommercialPlan, data.plan_code)
    if not plan or not plan.is_active: raise BadRequestException('Selecciona un plan publicado.')
    patient_count = db.execute(select(func.count()).select_from(User.__table__).where(User.tenant_id == identity, User.role_id == 'CLIENTE')).scalar()
    branch_count = db.query(Branch).filter_by(tenant_id=identity, is_active=True).count()
    if (plan.max_patients is not None and patient_count > plan.max_patients) or (plan.max_branches is not None and branch_count > plan.max_branches):
        raise BadRequestException('La empresa supera los límites de ese plan. Elige uno con capacidad suficiente.')
    old = db.query(Subscription).filter_by(tenant_id=identity, status='ACTIVE').all()
    before = {'plans': [s.plan_name for s in old]}
    for s in old: s.status = 'REPLACED'
    assignment = db.get(CompanyAdministrator, identity)
    admin = db.get(User, assignment.user_id) if assignment else None
    subscription = Subscription(tenant_id=identity, user_id=admin.id if admin else None,
        branch_id=admin.branch_id if admin else None, plan_name=plan.code, plan_snapshot=plan_dict(plan),
        source='MANUAL', status='ACTIVE', amount=0, currency=plan.currency, started_at=now(), expires_at=now()+timedelta(days=plan.duration_days))
    db.add(subscription)
    audit(db, user, 'PLAN_ASIGNADO', identity, data.reason, before, {'plan': plan.code, 'source': 'MANUAL'})
    db.commit()
    return subscription_dict(subscription)


@router.get('/subscriptions')
def subscriptions(offset: int=Query(0, ge=0), limit: int=Query(50, ge=1, le=100),
                  user=Depends(platform_user), db: Session=Depends(get_db)):
    query = db.query(Subscription, Tenant.name).join(Tenant, Tenant.id == Subscription.tenant_id).filter(~Subscription.plan_name.like('CLIENTE_%'))
    return dict(total=query.count(), items=[dict(subscription_dict(s), company_name=name) for s, name in query.order_by(Subscription.created_at.desc()).offset(offset).limit(limit).all()])


@router.get('/audit')
def history(offset: int=Query(0, ge=0), limit: int=Query(50, ge=1, le=100),
            user=Depends(platform_user), db: Session=Depends(get_db)):
    query = db.query(PlatformAudit)
    items = []
    for r in query.order_by(PlatformAudit.created_at.desc()).offset(offset).limit(limit).all():
        company = db.get(Tenant, r.target_id)
        plan = db.get(CommercialPlan, r.target_id) if not company else None
        actor = db.get(User, r.actor_id)
        items.append(dict(id=r.id, action=r.action, target_id=r.target_id,
            target_name=company.name if company else plan.display_name if plan else r.target_id,
            actor_name=actor.full_name if actor else 'Administrador',
            reason=r.reason, before=r.before, after=r.after, created_at=r.created_at))
    return dict(total=query.count(), items=items)
