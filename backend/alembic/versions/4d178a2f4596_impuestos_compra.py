"""Tasa de impuesto histórica por partida de compra."""
from alembic import op
import sqlalchemy as sa
revision='4d178a2f4596'
down_revision='3c06791e3485'
branch_labels=None
depends_on=None

def upgrade():
    with op.batch_alter_table('purchase_items') as batch:
        batch.add_column(sa.Column('tax_rate',sa.Numeric(6,4),nullable=False,server_default='0'))

def downgrade():
    raise RuntimeError('Restaura un respaldo para conservar el histórico de impuestos.')
