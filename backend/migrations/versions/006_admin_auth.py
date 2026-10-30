"""Revocable management sessions and atomic login throttle."""
from alembic import op
from lottery.models import AdminSession, LoginThrottle
revision='006'
down_revision='005'

def upgrade():
    for model in (AdminSession,LoginThrottle):model.__table__.create(op.get_bind(),checkfirst=True)

def downgrade():
    for model in (LoginThrottle,AdminSession):model.__table__.drop(op.get_bind(),checkfirst=True)
