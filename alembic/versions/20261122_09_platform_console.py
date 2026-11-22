"""Persist company plans and preserve subscription conditions."""
from alembic import op
import sqlalchemy as sa
from datetime import datetime, timezone

revision = '20261122_09'
down_revision = '20261031_08'
branch_labels = None
depends_on = None


def upgrade():
    from app.models.commercial_plan import CommercialPlan, PlatformAudit
    from app.services.subscription_service import PLANS
    bind = op.get_bind()
    CommercialPlan.__table__.create(bind, checkfirst=True)
    PlatformAudit.__table__.create(bind, checkfirst=True)
    cols = {c['name'] for c in sa.inspect(bind).get_columns('subscriptions')}
    with op.batch_alter_table('subscriptions') as batch:
        if 'plan_snapshot' not in cols: batch.add_column(sa.Column('plan_snapshot', sa.JSON(), nullable=True))
        if 'source' not in cols: batch.add_column(sa.Column('source', sa.String(20), nullable=False, server_default='PAYPAL'))
    from app.models.subscription import Subscription
    for code, info in PLANS.items():
        if code.startswith('CLIENTE_'): continue
        if not bind.execute(sa.select(CommercialPlan.code).where(CommercialPlan.code == code)).first():
            bind.execute(CommercialPlan.__table__.insert().values(code=code, display_name=info['display_name'],
                price=info['price'], currency=info['currency'], duration_days=30, max_patients=info['max_patients'],
                max_branches=None, features=info['features'], is_active=True, created_at=datetime.now(timezone.utc)))
        historical = bind.execute(sa.select(Subscription.id, Subscription.amount, Subscription.currency).where(
            Subscription.plan_name == code, Subscription.plan_snapshot.is_(None))).all()
        for sub in historical:
            snapshot = dict(info, duration_days=30, max_branches=None, price=float(sub.amount), currency=sub.currency)
            bind.execute(Subscription.__table__.update().where(Subscription.id == sub.id).values(plan_snapshot=snapshot))


def downgrade():
    with op.batch_alter_table('subscriptions') as batch:
        batch.drop_column('plan_snapshot')
        batch.drop_column('source')
    op.drop_table('platform_audit')
    op.drop_table('commercial_plans')
