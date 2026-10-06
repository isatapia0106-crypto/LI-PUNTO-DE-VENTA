"""Turno de entrega y fecha de pagos integrados."""
from alembic import op
import sqlalchemy as sa
revision = '09d346eb0152'
down_revision = 'f8c235da9041'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('payment_intents', sa.Column('delivery_cash_session_id', sa.Integer(), nullable=True))
    op.add_column('payment_intents', sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True))
    # Backfill completed records from the idempotent sale reference without
    # guessing delivery details for intents that have no sale.
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, empresa_id FROM payment_intents WHERE status = 'completed'"))
    for row in rows:
        sale = bind.execute(sa.text("SELECT cash_session_id, created_at FROM sales WHERE empresa_id=:company AND request_key=:key"),
            {'company':row.empresa_id,'key':'mp-sale-'+row.id}).first()
        if sale:
            bind.execute(sa.text('UPDATE payment_intents SET delivery_cash_session_id=:cash, delivered_at=:at WHERE id=:id'),
                {'cash':sale.cash_session_id,'at':sale.created_at,'id':row.id})

def downgrade():
    raise RuntimeError('Restaura un respaldo conjunto para conservar la trazabilidad financiera.')
