"""Preserve the customer's display name on a sale when the profile changes.

Revision ID: e1a59c0d35f4
Revises: c40a2e71b95d
"""
from alembic import op
import sqlalchemy as sa

revision = 'e1a59c0d35f4'
down_revision = 'c40a2e71b95d'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('sales') as batch:
        batch.add_column(sa.Column('customer_name', sa.String(length=160), nullable=True))
    connection = op.get_bind()
    connection.execute(sa.text('UPDATE sales SET customer_name = (SELECT customers.name FROM customers WHERE customers.id = sales.customer_id) WHERE customer_id IS NOT NULL'))


def downgrade():
    with op.batch_alter_table('sales') as batch:
        batch.drop_column('customer_name')
