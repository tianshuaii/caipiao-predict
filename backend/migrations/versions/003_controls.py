"""Frozen matched random controls and revision-aware group scores."""
from alembic import op
from lottery.models import RandomControl, ControlScore
revision = '003'
down_revision = '002'

def upgrade():
    for model in (RandomControl, ControlScore):
        model.__table__.create(op.get_bind(), checkfirst=True)

def downgrade():
    for model in (ControlScore, RandomControl):
        model.__table__.drop(op.get_bind(), checkfirst=True)
