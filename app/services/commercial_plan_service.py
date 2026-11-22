from datetime import datetime, timezone
from sqlalchemy import select, func
from app.models.commercial_plan import CommercialPlan
from app.models.subscription import Subscription
from app.models.user import User
from app.models.company import Branch
from app.models.tenant import Tenant
from app.core.exceptions import BadRequestException


def plan_dict(row):
    return dict(name=row.code, display_name=row.display_name, price=float(row.price), currency=row.currency,
                period='mes' if row.duration_days == 30 else f'{row.duration_days} días',
                duration_days=row.duration_days, max_patients=row.max_patients, max_branches=row.max_branches,
                features=row.features or [], recommended=False)


def catalog(db, *, active_only=True):
    from app.services.subscription_service import PLANS
    rows = db.query(CommercialPlan).all()
    if not rows:
        return {code: dict(info, duration_days=30, max_branches=None) for code, info in PLANS.items()}
    result = {code: info for code, info in PLANS.items() if code.startswith('CLIENTE_')}
    result.update({row.code: plan_dict(row) for row in rows if row.is_active or not active_only})
    return result


def effective_plan(db, tenant_id):
    table = Subscription.__table__
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    row = db.execute(select(table.c.plan_name, table.c.plan_snapshot).where(
        table.c.tenant_id == tenant_id, table.c.status == 'ACTIVE', table.c.expires_at > now,
        ~table.c.plan_name.like('CLIENTE_%')).order_by(table.c.created_at.desc())).first()
    return (row.plan_snapshot or catalog(db, active_only=False).get(row.plan_name)) if row else None


def check_capacity(db, tenant_id, resource):
    if not tenant_id: return
    # Serialize competing admissions/branch creations for the same company.
    db.execute(select(Tenant.id).where(Tenant.id == tenant_id).with_for_update())
    plan = effective_plan(db, tenant_id)
    key = 'max_patients' if resource == 'patients' else 'max_branches'
    limit = plan.get(key) if plan else None
    if limit is None: return
    table = User.__table__ if resource == 'patients' else Branch.__table__
    conditions = [table.c.tenant_id == tenant_id]
    if resource == 'patients': conditions.append(table.c.role_id == 'CLIENTE')
    else: conditions.append(table.c.is_active.is_(True))
    count = db.execute(select(func.count()).select_from(table).where(*conditions)).scalar()
    if count >= limit:
        raise BadRequestException(f'El plan de la empresa permite hasta {limit} ' + ('pacientes.' if resource == 'patients' else 'sucursales activas.'))


def check_plan_fit(db, tenant_id, plan):
    if not tenant_id: return
    for table, limit, conditions in [
        (User.__table__, plan.get('max_patients'), [User.role_id == 'CLIENTE']),
        (Branch.__table__, plan.get('max_branches'), [Branch.is_active.is_(True)]),
    ]:
        if limit is None: continue
        count = db.execute(select(func.count()).select_from(table).where(table.c.tenant_id == tenant_id, *conditions)).scalar()
        if count > limit:
            raise BadRequestException('La empresa supera la capacidad del plan seleccionado. Elige un plan con límites suficientes.')
