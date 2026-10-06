"""Reservas y revisión persistente de pagos."""
from alembic import op
import sqlalchemy as sa
revision = 'e7b124cf8930'
down_revision = 'd6a013be7829'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('payment_intents', sa.Column('reservation_active', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('payment_intents', sa.Column('review_reason', sa.String(500), nullable=True))
    op.add_column('payment_intents', sa.Column('price_snapshot', sa.String(20000), nullable=True))
    # Existing checkouts were created without reservations; never claim inventory
    # that may already have been sold. They require supervised confirmation.

def downgrade():
    raise RuntimeError('Restaura un respaldo conjunto para conservar la trazabilidad financiera.')
