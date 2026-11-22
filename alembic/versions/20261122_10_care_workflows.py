"""Follow-up, reviews, communication and confirmed patient imports."""
from alembic import op
revision = '20261122_10'
down_revision = '20261122_09'
branch_labels = None
depends_on = None


def upgrade():
    from app.models.care import Measurement, NutritionConfiguration, CareAssessment, PlanReview, CareMessage, PatientImportBatch, PlatformIncident
    for model in [Measurement, NutritionConfiguration, CareAssessment, PlanReview, CareMessage, PatientImportBatch, PlatformIncident]:
        model.__table__.create(op.get_bind(), checkfirst=True)


def downgrade():
    for name in ['platform_incidents','patient_import_batches','care_messages','plan_reviews','care_assessments','nutrition_configurations','patient_measurements']:
        op.drop_table(name)
