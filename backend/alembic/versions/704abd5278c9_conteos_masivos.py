"""Registro durable para conciliación de conteos masivos."""
from alembic import op
import sqlalchemy as sa
revision='704abd5278c9'
down_revision='6f39ac4167b8'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('inventory_count_batches',sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('empresa_id',sa.Integer(),nullable=False),sa.Column('branch_id',sa.Integer(),sa.ForeignKey('branches.id'),nullable=False),
        sa.Column('actor_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),sa.Column('request_key',sa.String(100),nullable=False),
        sa.Column('payload',sa.String(20000),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.UniqueConstraint('empresa_id','request_key'))
    op.create_index('ix_inventory_count_batches_empresa_id','inventory_count_batches',['empresa_id'])

def downgrade():
    raise RuntimeError('Restaura un respaldo para conservar grupos de conteo e idempotencia.')
