"""Estado durable y confirmación del reembolso de devoluciones."""
from alembic import op
import sqlalchemy as sa
revision='2bf5680d2374'
down_revision='1ae457fc1263'
branch_labels=None
depends_on=None

def upgrade():
    with op.batch_alter_table('sale_returns') as batch:
        batch.add_column(sa.Column('status',sa.String(30),nullable=False,server_default='completed'))
        batch.add_column(sa.Column('requested_at',sa.DateTime(timezone=True),nullable=True))
        batch.add_column(sa.Column('finalized_at',sa.DateTime(timezone=True),nullable=True))
        batch.add_column(sa.Column('provider_payment_id',sa.String(100),nullable=True))
        batch.add_column(sa.Column('provider_key',sa.String(60),nullable=True))
        batch.add_column(sa.Column('provider_refund_id',sa.String(100),nullable=True))
        batch.add_column(sa.Column('provider_refunded_before',sa.Numeric(12,2),nullable=True))
        batch.create_unique_constraint('uq_sale_return_provider_key',['provider_key'])
    op.execute('UPDATE sale_returns SET requested_at=created_at, finalized_at=created_at')

def downgrade():
    raise RuntimeError('Restaura un respaldo conjunto para conservar la trazabilidad financiera.')
