"""0006: índice único parcial en topup_requests.mp_payment_id

Blinda la idempotencia de recargas MercadoPago a nivel BD: el webhook IPN
puede recibir retries concurrentes del mismo payment_id y el pre-check de
`_credit_mp_payment()` (SELECT-then-INSERT) deja una ventana de carrera que
podría acreditar el saldo dos veces. Con este índice, un INSERT duplicado
revienta con IntegrityError y la transacción se revierte.

Parcial (WHERE mp_payment_id IS NOT NULL) porque las recargas manuales
(transferencia/efectivo aprobadas por admin) no tienen mp_payment_id.
"""
from alembic import op
from sqlalchemy import text


revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None

IDX = 'uq_topup_requests_mp_payment_id'


def upgrade():
    with op.batch_alter_table('topup_requests') as batch:
        batch.create_index(
            IDX,
            ['mp_payment_id'],
            unique=True,
            sqlite_where=text('mp_payment_id IS NOT NULL'),
            postgresql_where=text('mp_payment_id IS NOT NULL'),
        )


def downgrade():
    with op.batch_alter_table('topup_requests') as batch:
        batch.drop_index(IDX)
