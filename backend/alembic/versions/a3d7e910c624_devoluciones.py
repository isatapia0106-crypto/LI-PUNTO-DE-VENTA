"""Devoluciones de ventas y reembolsos auditados."""
from alembic import op
import sqlalchemy as sa
revision = 'a3d7e910c624'
down_revision = 'f2b3409ac871'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('sale_returns',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('empresa_id', sa.Integer(), nullable=False),
        sa.Column('sale_id', sa.Integer(), sa.ForeignKey('sales.id'), nullable=False),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('cash_session_id', sa.Integer(), sa.ForeignKey('cash_sessions.id'), nullable=True),
        sa.Column('reason', sa.String(160), nullable=False),
        sa.Column('payment_reference', sa.String(100), nullable=True),
        sa.Column('payload', sa.String(20000), nullable=False),
        sa.Column('total', sa.Numeric(12,2), nullable=False),
        sa.Column('request_key', sa.String(100), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('empresa_id', 'request_key'))
    op.create_index('ix_sale_returns_empresa_id', 'sale_returns', ['empresa_id'])
    op.create_table('sale_return_items',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('return_id', sa.Integer(), sa.ForeignKey('sale_returns.id'), nullable=False),
        sa.Column('sale_item_id', sa.Integer(), sa.ForeignKey('sale_items.id'), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('restock', sa.Boolean(), nullable=False),
        sa.Column('total', sa.Numeric(12,2), nullable=False),
        sa.UniqueConstraint('return_id', 'sale_item_id'))

def downgrade():
    raise RuntimeError('Restaura el respaldo completo: las devoluciones contienen movimientos financieros.')
