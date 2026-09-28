"""Customers and optional sale linkage.

Revision ID: c40a2e71b95d
Revises: 9b64d21f70c2
"""
from alembic import op
import sqlalchemy as sa

revision = 'c40a2e71b95d'
down_revision = '9b64d21f70c2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'customers',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('empresa_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=160), nullable=False),
        sa.Column('phone', sa.String(length=30), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_customers_empresa_id', 'customers', ['empresa_id'])
    with op.batch_alter_table('sales') as batch:
        batch.add_column(sa.Column('customer_id', sa.Integer(), nullable=True))
        batch.create_foreign_key('fk_sales_customer_id', 'customers', ['customer_id'], ['id'])


def downgrade():
    with op.batch_alter_table('sales') as batch:
        batch.drop_constraint('fk_sales_customer_id', type_='foreignkey')
        batch.drop_column('customer_id')
    op.drop_index('ix_customers_empresa_id', table_name='customers')
    op.drop_table('customers')
