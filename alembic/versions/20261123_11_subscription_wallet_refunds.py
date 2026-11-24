"""Personal Premium subscription refunds credited to the wallet."""
from alembic import op
revision = '20261123_11'
down_revision = '20261122_10'
branch_labels = None
depends_on = None


def upgrade():
    from app.models.subscription_wallet_refund import SubscriptionWalletRefund
    SubscriptionWalletRefund.__table__.create(op.get_bind(), checkfirst=True)


def downgrade():
    op.drop_table('subscription_wallet_refunds')
