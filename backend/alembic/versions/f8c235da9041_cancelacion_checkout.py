"""Cancelación durable de checkout antes de liberar reservas."""
from alembic import op
import sqlalchemy as sa
revision = 'f8c235da9041'
down_revision = 'e7b124cf8930'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('payment_intents', sa.Column('cancel_requested_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('payment_intents', sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('payment_intents', sa.Column('cancel_actor_id', sa.Integer(), nullable=True))
    op.add_column('payment_intents', sa.Column('cancel_reason', sa.String(300), nullable=True))

def downgrade():
    raise RuntimeError('Restaura un respaldo conjunto para conservar la trazabilidad financiera.')
