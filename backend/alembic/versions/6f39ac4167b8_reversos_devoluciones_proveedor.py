"""Reversos de abonos y devoluciones a proveedor sin borrar histórico."""
from alembic import op
import sqlalchemy as sa
revision='6f39ac4167b8'
down_revision='5e289b3056a7'
branch_labels=None
depends_on=None

def upgrade():
    with op.batch_alter_table('supplier_payments') as batch:
        batch.add_column(sa.Column('reversed_at',sa.DateTime(timezone=True),nullable=True))
        batch.add_column(sa.Column('reversed_by',sa.Integer(),nullable=True))
        batch.add_column(sa.Column('reversal_reason',sa.String(300),nullable=True))
    op.create_table('supplier_returns',sa.Column('id',sa.Integer(),primary_key=True),sa.Column('empresa_id',sa.Integer(),nullable=False),
        sa.Column('purchase_id',sa.Integer(),sa.ForeignKey('purchases.id'),nullable=False),
        sa.Column('payable_id',sa.Integer(),sa.ForeignKey('supplier_payables.id'),nullable=False),
        sa.Column('actor_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),sa.Column('reason',sa.String(300),nullable=False),
        sa.Column('credit_reference',sa.String(100),nullable=False),sa.Column('total',sa.Numeric(12,2),nullable=False),
        sa.Column('payload',sa.String(20000),nullable=False),sa.Column('request_key',sa.String(100),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),sa.UniqueConstraint('empresa_id','request_key'))
    op.create_index('ix_supplier_returns_empresa_id','supplier_returns',['empresa_id'])

def downgrade():
    raise RuntimeError('Restaura un respaldo para conservar créditos y reversos históricos.')
