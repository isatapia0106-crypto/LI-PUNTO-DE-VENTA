"""Observaciones del proveedor y reembolsos idempotentes de incidencias."""
from alembic import op
import sqlalchemy as sa
revision='1ae457fc1263'
down_revision='09d346eb0152'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column('payment_intents',sa.Column('resolved_by',sa.Integer(),nullable=True))
    op.add_column('payment_intents',sa.Column('resolved_at',sa.DateTime(timezone=True),nullable=True))
    op.create_table('payment_observations',
        sa.Column('payment_id',sa.String(100),primary_key=True),
        sa.Column('empresa_id',sa.Integer(),nullable=False),
        sa.Column('intent_id',sa.String(60),sa.ForeignKey('payment_intents.id'),nullable=False),
        sa.Column('status',sa.String(40),nullable=False),
        sa.Column('amount',sa.Numeric(12,2),nullable=False),
        sa.Column('refunded',sa.Numeric(12,2),nullable=False),
        sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_payment_observations_empresa_id','payment_observations',['empresa_id'])
    op.create_table('payment_refunds',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('empresa_id',sa.Integer(),nullable=False),
        sa.Column('intent_id',sa.String(60),sa.ForeignKey('payment_intents.id'),nullable=False),
        sa.Column('payment_id',sa.String(100),nullable=False,unique=True),
        sa.Column('amount',sa.Numeric(12,2),nullable=False),
        sa.Column('provider_key',sa.String(60),nullable=False,unique=True),
        sa.Column('provider_refund_id',sa.String(100),nullable=True),
        sa.Column('status',sa.String(30),nullable=False),
        sa.Column('reason',sa.String(300),nullable=False),
        sa.Column('actor_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('confirmed_at',sa.DateTime(timezone=True),nullable=True))
    op.create_index('ix_payment_refunds_empresa_id','payment_refunds',['empresa_id'])

def downgrade():
    raise RuntimeError('Restaura un respaldo conjunto para conservar la trazabilidad financiera.')
