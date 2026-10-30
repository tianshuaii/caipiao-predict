"""Immutable research requests and single active slot."""
from alembic import op
from lottery.models import ResearchJob
revision='007'
down_revision='006'
def upgrade():ResearchJob.__table__.create(op.get_bind(),checkfirst=True)
def downgrade():ResearchJob.__table__.drop(op.get_bind(),checkfirst=True)
