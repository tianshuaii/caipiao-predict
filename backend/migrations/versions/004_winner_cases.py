"""Public winning-ticket report cases, separate from prediction evidence."""
from alembic import op
from lottery.models import WinnerCase
revision = '004'
down_revision = '003'

def upgrade():
    WinnerCase.__table__.create(op.get_bind(), checkfirst=True)

def downgrade():
    WinnerCase.__table__.drop(op.get_bind(), checkfirst=True)
