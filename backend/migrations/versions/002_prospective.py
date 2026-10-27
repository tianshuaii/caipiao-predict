"""Add prospective forecasts, revision scores and selection audit."""
from alembic import op
from lottery.models import CandidateForecast, CandidateScore, StrategyDecision
revision = '002'
down_revision = '001'

def upgrade():
    for model in (CandidateForecast, CandidateScore, StrategyDecision):
        model.__table__.create(op.get_bind(), checkfirst=True)

def downgrade():
    for model in (StrategyDecision, CandidateScore, CandidateForecast):
        model.__table__.drop(op.get_bind(), checkfirst=True)
