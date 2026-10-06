"""Checkouts y conciliación de Mercado Pago."""
from alembic import op
import sqlalchemy as sa
revision='d6a013be7829'
down_revision='c5f902ad6718'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('payment_intents',
        sa.Column('id',sa.String(60),primary_key=True),
        sa.Column('empresa_id',sa.Integer(),nullable=False),
        sa.Column('branch_id',sa.Integer(),sa.ForeignKey('branches.id'),nullable=False),
        sa.Column('actor_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('payload',sa.String(20000),nullable=False),
        sa.Column('amount',sa.Numeric(12,2),nullable=False),
        sa.Column('status',sa.String(40),nullable=False),
        sa.Column('preference_id',sa.String(100),nullable=True),
        sa.Column('checkout_url',sa.String(2000),nullable=True),
        sa.Column('payment_id',sa.String(100),nullable=True,unique=True),
        sa.Column('request_key',sa.String(100),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.UniqueConstraint('empresa_id','request_key'))
    op.create_index('ix_payment_intents_empresa_id','payment_intents',['empresa_id'])

def downgrade():
    raise RuntimeError('Los registros financieros requieren restauración conjunta del respaldo.')
