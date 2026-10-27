"""Index retained observations for historical visibility; no row rewrite."""
from alembic import op
from sqlalchemy import inspect
revision='005'
down_revision='004'
INDEX='ix_observations_draw_created'

def upgrade():
    if INDEX not in {i['name'] for i in inspect(op.get_bind()).get_indexes('draw_observations')}:
        op.create_index(INDEX,'draw_observations',['draw_id','created_at'])

def downgrade():
    if INDEX in {i['name'] for i in inspect(op.get_bind()).get_indexes('draw_observations')}:
        op.drop_index(INDEX,table_name='draw_observations')
