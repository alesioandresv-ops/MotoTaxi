"""0007: topup_requests.preference_id

Trazabilidad de recargas MercadoPago checkout: al crear la preferencia se
persiste TopUpRequest(status='pending', preference_id=...) ANTES de redirigir
al usuario. Si el webhook nunca llega (localhost, caída de MP), queda
evidencia para reconciliación manual contra /v1/payments/search.

Nullable: recargas manuales (transferencia/efectivo) no tienen preferencia y
las filas históricas tampoco. Sin backfill.
"""
from alembic import op
import sqlalchemy as sa


revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('topup_requests') as batch:
        batch.add_column(
            sa.Column('preference_id', sa.String(length=100), nullable=True),
        )


def downgrade():
    with op.batch_alter_table('topup_requests') as batch:
        batch.drop_column('preference_id')
