"""Atomic stock transfers between branches.

Revision ID: 9b64d21f70c2
Revises: 77f0a8ca18aa
"""
from alembic import op
import sqlalchemy as sa

revision = '9b64d21f70c2'
down_revision = '77f0a8ca18aa'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'stock_transfers',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('empresa_id', sa.Integer(), nullable=False),
        sa.Column('source_branch_id', sa.Integer(), sa.ForeignKey('branches.id'), nullable=False),
        sa.Column('target_branch_id', sa.Integer(), sa.ForeignKey('branches.id'), nullable=False),
        sa.Column('product_id', sa.Integer(), sa.ForeignKey('products.id'), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('request_key', sa.String(length=100), nullable=False),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('empresa_id', 'request_key'),
    )
    op.create_index('ix_stock_transfers_empresa_id', 'stock_transfers', ['empresa_id'])


def downgrade():
    op.drop_index('ix_stock_transfers_empresa_id', table_name='stock_transfers')
    op.drop_table('stock_transfers')
