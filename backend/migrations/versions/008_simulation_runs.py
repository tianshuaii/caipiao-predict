"""Frozen historical virtual accounts."""
from alembic import op
from lottery.models import SimulationRun
revision='008'
down_revision='007'
def upgrade():SimulationRun.__table__.create(op.get_bind(),checkfirst=True)
def downgrade():SimulationRun.__table__.drop(op.get_bind(),checkfirst=True)
