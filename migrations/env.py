"""Alembic env — VAN.

Carga backend/.env y usa DATABASE_URL (PostgreSQL). En modo offline
(sqlalchemy.url del ini) no conecta: solo renderiza SQL.
"""
import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(PROJECT_ROOT, 'backend', '.env'))

from backend.models import db  # noqa: E402

config = context.config
target_metadata = db.metadata

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

_DB_URL = os.environ.get('DATABASE_URL', '')


def _normalize_pg(url):
    if url.startswith('postgres://'):
        url = 'postgresql://' + url[len('postgres://'):]
    if url.startswith('postgresql://') and '+psycopg' not in url:
        url = url.replace('postgresql://', 'postgresql+psycopg://', 1)
    return url


def run_migrations_offline() -> None:
    url = _normalize_pg(_DB_URL) if _DB_URL.startswith('postgres') else config.get_main_option('sqlalchemy.url')
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={'paramstyle': 'named'},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # PostgreSQL en producción; SQLite (archivo) solo para autogenerate local.
    if not (_DB_URL.startswith('postgres') or _DB_URL.startswith('sqlite:///')):
        raise RuntimeError(
            'Alembic requiere DATABASE_URL PostgreSQL. '
            f'Se obtuvo: {_DB_URL or "(vacío)"}'
        )
    url = _normalize_pg(_DB_URL) if _DB_URL.startswith('postgres') else _DB_URL
    config.set_main_option('sqlalchemy.url', url)
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix='sqlalchemy.',
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
