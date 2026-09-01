"""trips: tracking de cobro (payment_status, paid_at, payment_method_collected)

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-24

Cobro en finalización (web + contrato futuro Etapa 3):

- `payment_status` VARCHAR(20) NOT NULL con server_default 'pending'
  (pending | paid). Los viajes completados previos se backfillean a 'paid':
  se cobraron por definición (billetera auto-debitada o efectivo fuera de la
  app) — sin esto el historial quedaría inconsistente.
- `paid_at`: momento del cobro confirmado.
- `payment_method_collected`: método REAL con el que se cobró (puede diferir
  del `payment_method` elegido por el pasajero si el conductor lo cambió al
  finalizar).
- CHECK `chk_trip_payment_status` (mismo nombre que en models.py).

batch_alter_table: en PostgreSQL es passthrough (ALTER directo); en SQLite
(solo tests) recrea la tabla. El backfill se protege con `_online()` (patrón
de 0002/0003): en modo offline (`alembic upgrade --sql`) solo DDL.
"""
from alembic import op
import sqlalchemy as sa

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def _online():
    from alembic import context
    return not context.is_offline_mode()


def upgrade():
    with op.batch_alter_table('trips') as batch:
        batch.add_column(
            sa.Column(
                'payment_status',
                sa.String(length=20),
                nullable=False,
                server_default='pending',
            ),
        )
        batch.add_column(sa.Column('paid_at', sa.DateTime(), nullable=True))
        batch.add_column(
            sa.Column('payment_method_collected', sa.String(length=50), nullable=True),
        )
    if _online():
        # Viajes ya completados = cobrados (billetera debitó o pago físico).
        op.get_bind().execute(
            sa.text(
                "UPDATE trips SET payment_status = 'paid' "
                "WHERE status = 'completed'"
            )
        )
    with op.batch_alter_table('trips') as batch:
        batch.create_check_constraint(
            'chk_trip_payment_status',
            "payment_status IN ('pending', 'paid')",
        )


def downgrade():
    with op.batch_alter_table('trips') as batch:
        batch.drop_constraint('chk_trip_payment_status', type_='check')
    with op.batch_alter_table('trips') as batch:
        batch.drop_column('payment_method_collected')
        batch.drop_column('paid_at')
        batch.drop_column('payment_status')
