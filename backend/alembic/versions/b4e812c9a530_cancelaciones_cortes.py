"""Cancelaciones y snapshot inmutable de corte."""
from alembic import op
import sqlalchemy as sa
revision = 'b4e812c9a530'
down_revision = 'a3d7e910c624'
branch_labels = None
depends_on = None

def upgrade():
    with op.batch_alter_table('sale_returns') as batch:
        batch.add_column(sa.Column('kind', sa.String(20), nullable=False, server_default='return'))
    with op.batch_alter_table('cash_sessions') as batch:
        batch.add_column(sa.Column('close_snapshot', sa.String(20000), nullable=True))

def downgrade():
    raise RuntimeError('Restaura el respaldo completo para conservar dinero y auditoría.')
