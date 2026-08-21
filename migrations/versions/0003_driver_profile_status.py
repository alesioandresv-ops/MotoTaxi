"""driver_profiles.status — verificación del conductor (contrato §7)

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-10

`status` (pending | approved | rejected) pasa a ser la ÚNICA fuente de
autorización del conductor. `is_verified` (legacy) NO autoriza: se conserva
intacto solo como alias de presentación para templates (driver_view()).

- Columna: `status VARCHAR(10) NOT NULL` con `server_default 'pending'`
  (nuevos registros → pending).
- Backfill: TODOS los driver_profiles existentes → 'approved'
  (compatibilidad total, nadie queda bloqueado — contrato §7).
- CHECK `chk_driver_profile_status` (mismo nombre que en models.py).

batch_alter_table: en PostgreSQL es passthrough (ALTER directo); en SQLite
(solo tests) recrea la tabla — permite verificar la migración sin Docker.
El backfill de datos se protege con `_online()` (patrón de 0002): en modo
offline (`alembic upgrade --sql`) solo se renderiza el DDL.
"""
from alembic import op
import sqlalchemy as sa

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def _online():
    from alembic import context
    return not context.is_offline_mode()


def upgrade():
    with op.batch_alter_table('driver_profiles') as batch:
        batch.add_column(
            sa.Column(
                'status',
                sa.String(length=10),
                nullable=False,
                server_default='pending',
            ),
        )
    if _online():
        # Contrato §7: existentes → approved (is_verified no es gate).
        op.get_bind().execute(
            sa.text("UPDATE driver_profiles SET status = 'approved'")
        )
    with op.batch_alter_table('driver_profiles') as batch:
        batch.create_check_constraint(
            'chk_driver_profile_status',
            "status IN ('pending', 'approved', 'rejected')",
        )


def downgrade():
    with op.batch_alter_table('driver_profiles') as batch:
        batch.drop_constraint('chk_driver_profile_status', type_='check')
    with op.batch_alter_table('driver_profiles') as batch:
        batch.drop_column('status')
