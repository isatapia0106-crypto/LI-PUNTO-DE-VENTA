"""Cancelación de pendientes de compras con motivo y responsable."""
from alembic import op
import sqlalchemy as sa
revision='3c06791e3485'
down_revision='2bf5680d2374'
branch_labels=None
depends_on=None

def upgrade():
    with op.batch_alter_table('purchases') as batch:
        batch.add_column(sa.Column('cancel_reason',sa.String(300),nullable=True))
        batch.add_column(sa.Column('cancelled_by',sa.Integer(),nullable=True))
        batch.add_column(sa.Column('cancelled_at',sa.DateTime(timezone=True),nullable=True))

def downgrade():
    raise RuntimeError('Restaura un respaldo para conservar la trazabilidad de compras.')
