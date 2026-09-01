"""idempotencia API v1 — api_idempotency_keys + trips.idempotency_key

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-20

Etapa 2 — Trips API (contrato §11 y §8.3):

- Tabla `api_idempotency_keys`: almacén de respuestas para replays.
  UNIQUE (user_id, key, method) — la clave es por usuario (un cliente no
  puede clonar claves de otro). Índice por created_at para limpieza perezosa
  (TTL 24 h).
- `trips.idempotency_key`: trazabilidad del viaje (nullable; el mecanismo
  principal es el header). UNIQUE (passenger_id, idempotency_key).

Nota: el contrato ubicaba estas columnas en "migración 0003", pero ese
número ya estaba tomado por driver_profiles.status → esta es 0004.

batch_alter_table: en PostgreSQL es passthrough (ALTER directo); en SQLite
(solo tests) recrea la tabla. Sin backfill de datos → no requiere _online().
"""
from alembic import op
import sqlalchemy as sa

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'api_idempotency_keys',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('key', sa.String(length=255), nullable=False),
        sa.Column('method', sa.String(length=10), nullable=False),
        sa.Column('path', sa.String(length=255), nullable=False),
        sa.Column('status_code', sa.Integer(), nullable=False),
        sa.Column('response_body', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'key', 'method', name='uq_idempotency_user_key_method'),
    )
    op.create_index(
        'ix_api_idempotency_keys_user_id', 'api_idempotency_keys', ['user_id'],
    )
    op.create_index(
        'ix_idempotency_created_at', 'api_idempotency_keys', ['created_at'],
    )

    with op.batch_alter_table('trips') as batch:
        batch.add_column(
            sa.Column('idempotency_key', sa.String(length=255), nullable=True),
        )
    with op.batch_alter_table('trips') as batch:
        batch.create_unique_constraint(
            'uq_trips_passenger_idempotency', ['passenger_id', 'idempotency_key'],
        )


def downgrade():
    with op.batch_alter_table('trips') as batch:
        batch.drop_constraint('uq_trips_passenger_idempotency', type_='unique')
    with op.batch_alter_table('trips') as batch:
        batch.drop_column('idempotency_key')
    op.drop_index('ix_idempotency_created_at', table_name='api_idempotency_keys')
    op.drop_index('ix_api_idempotency_keys_user_id', table_name='api_idempotency_keys')
    op.drop_table('api_idempotency_keys')
