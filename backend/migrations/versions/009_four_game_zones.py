"""Add lookup indexes for registry-shaped draw records without rewriting history."""
from alembic import op


revision = '009'
down_revision = '008'


def upgrade():
    op.create_index('ix_draws_game_draw_date', 'draws', ['game', 'draw_date'], unique=False)
    op.create_index('ix_raw_fetches_source_fetched_at', 'raw_fetches', ['source', 'fetched_at'], unique=False)


def downgrade():
    op.drop_index('ix_raw_fetches_source_fetched_at', table_name='raw_fetches')
    op.drop_index('ix_draws_game_draw_date', table_name='draws')
