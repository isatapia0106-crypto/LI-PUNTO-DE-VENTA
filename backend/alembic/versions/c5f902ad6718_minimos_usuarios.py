"""Mínimos de inventario y revocación de sesiones de usuarios."""
from alembic import op
import sqlalchemy as sa
revision='c5f902ad6718'
down_revision='b4e812c9a530'
branch_labels=None
depends_on=None

def upgrade():
    with op.batch_alter_table('stock') as batch:
        batch.add_column(sa.Column('minimum', sa.Integer(), nullable=False, server_default='0'))
    with op.batch_alter_table('users') as batch:
        batch.add_column(sa.Column('token_version', sa.Integer(), nullable=False, server_default='0'))

def downgrade():
    raise RuntimeError('Restaura el respaldo completo junto con la versión anterior.')
