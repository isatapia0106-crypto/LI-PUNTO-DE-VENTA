"""Cuentas por pagar y abonos históricos de proveedores."""
from alembic import op
import sqlalchemy as sa
revision='5e289b3056a7'
down_revision='4d178a2f4596'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('supplier_payables',sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('empresa_id',sa.Integer(),nullable=False),sa.Column('branch_id',sa.Integer(),sa.ForeignKey('branches.id'),nullable=False),
        sa.Column('supplier_id',sa.Integer(),sa.ForeignKey('suppliers.id'),nullable=False),sa.Column('purchase_id',sa.Integer(),sa.ForeignKey('purchases.id'),nullable=False,unique=True),
        sa.Column('invoice',sa.String(100),nullable=False),sa.Column('due_date',sa.Date(),nullable=False),sa.Column('amount',sa.Numeric(12,2),nullable=False),
        sa.Column('actor_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.UniqueConstraint('empresa_id','supplier_id','invoice'))
    op.create_index('ix_supplier_payables_empresa_id','supplier_payables',['empresa_id'])
    op.create_table('supplier_payments',sa.Column('id',sa.Integer(),primary_key=True),sa.Column('empresa_id',sa.Integer(),nullable=False),
        sa.Column('payable_id',sa.Integer(),sa.ForeignKey('supplier_payables.id'),nullable=False),sa.Column('amount',sa.Numeric(12,2),nullable=False),
        sa.Column('reference',sa.String(100),nullable=False),sa.Column('method',sa.String(30),nullable=False),
        sa.Column('actor_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),sa.Column('request_key',sa.String(100),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),sa.UniqueConstraint('empresa_id','request_key'))
    op.create_index('ix_supplier_payments_empresa_id','supplier_payments',['empresa_id'])

def downgrade():
    raise RuntimeError('Restaura un respaldo para conservar el histórico de saldos y abonos.')
