"""Etapa 2 — migración 0004: idempotencia (contrato §8.3, §11).

Verifica contra una BD SQLite temporal (archivo) que la migración:
- crea `api_idempotency_keys` con UNIQUE(user_id, key, method)
- agrega `trips.idempotency_key` (nullable) con UNIQUE(passenger_id, idempotency_key)
- preserva las filas existentes de trips
- es reversible (downgrade sin pérdida de datos)
- en modo offline (--sql) solo renderiza DDL (no hay backfill)
Y que models.py está alineado con la migración (mismos nombres).

Nota: env.py resuelve la URL desde DATABASE_URL (ignora sqlalchemy.url del
Config en modo online), mismo patrón que tests/test_migration_0003.py.
"""
import os
import sqlite3

import pytest
from alembic import command
from alembic.config import Config

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

# Esquema mínimo post-0003: solo lo que 0004 toca (trips) + alembic_version.
PRE_0004_DDL = """
CREATE TABLE trips (
    id INTEGER PRIMARY KEY,
    passenger_id INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'requested'
);
INSERT INTO trips (id, passenger_id, status) VALUES
    (1, 10, 'requested'), (2, 10, 'completed'), (3, 20, 'requested');
CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY);
"""


def _prepare_pre_0004_db(path):
    con = sqlite3.connect(path)
    con.executescript(PRE_0004_DDL)
    con.execute("INSERT INTO alembic_version VALUES ('0003')")
    con.commit()
    con.close()


def _alembic_cfg():
    cfg = Config(os.path.join(PROJECT_ROOT, 'alembic.ini'))
    cfg.set_main_option('script_location', os.path.join(PROJECT_ROOT, 'migrations'))
    return cfg


@pytest.fixture
def migrated_db(tmp_path, monkeypatch):
    """BD SQLite estampada en 0003, migrada a 0004.

    Target fijo (no 'head'): este archivo prueba SOLO 0004. Si apuntara a
    head, migraciones futuras (0005+) tocarían tablas que este esquema
    mínimo no tiene.
    """
    db_path = str((tmp_path / 'mig0004.db').as_posix())
    _prepare_pre_0004_db(db_path)
    monkeypatch.setenv('DATABASE_URL', f'sqlite:///{db_path}')
    command.upgrade(_alembic_cfg(), '0004')
    yield db_path
    try:
        os.remove(db_path)
    except OSError:
        pass


class TestUpgrade:
    def test_creates_idempotency_table_with_unique(self, migrated_db):
        con = sqlite3.connect(migrated_db)
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert 'api_idempotency_keys' in tables
        sql = con.execute(
            "SELECT sql FROM sqlite_master WHERE name='api_idempotency_keys'"
        ).fetchone()[0]
        assert 'uq_idempotency_user_key_method' in sql
        cols = [r[1] for r in con.execute('PRAGMA table_info(api_idempotency_keys)')]
        assert cols == [
            'id', 'user_id', 'key', 'method', 'path',
            'status_code', 'response_body', 'created_at',
        ]

    def test_trips_gains_idempotency_key_preserving_rows(self, migrated_db):
        con = sqlite3.connect(migrated_db)
        cols = [r[1] for r in con.execute('PRAGMA table_info(trips)')]
        assert 'idempotency_key' in cols
        rows = list(con.execute('SELECT id, passenger_id FROM trips ORDER BY id'))
        assert rows == [(1, 10), (2, 10), (3, 20)]

    def test_trips_unique_constraint_named(self, migrated_db):
        con = sqlite3.connect(migrated_db)
        sql = con.execute("SELECT sql FROM sqlite_master WHERE name='trips'").fetchone()[0]
        assert 'uq_trips_passenger_idempotency' in sql


class TestDowngrade:
    def test_downgrade_removes_column_and_table(self, migrated_db):
        command.downgrade(_alembic_cfg(), '0003')
        con = sqlite3.connect(migrated_db)
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert 'api_idempotency_keys' not in tables
        cols = [r[1] for r in con.execute('PRAGMA table_info(trips)')]
        assert 'idempotency_key' not in cols
        rows = list(con.execute('SELECT id FROM trips ORDER BY id'))
        assert rows == [(1,), (2,), (3,)]


class TestOfflineMode:
    def test_render_sql_solo_ddl_sin_backfill(self, monkeypatch, capsys):
        """--sql contra PG: renderiza DDL sin UPDATE de backfill (0004 no tiene).

        Rango '0003:0004': offline no consulta el estado de la BD y sin
        rango renderizaría la cadena completa desde 0001 (incluyendo los
        UPDATE del merge defensivo de 0002).
        """
        monkeypatch.setenv(
            'DATABASE_URL', 'postgresql+psycopg://x:x@localhost:5432/van',
        )
        command.upgrade(_alembic_cfg(), '0003:0004', sql=True)
        out = capsys.readouterr().out
        assert 'CREATE TABLE api_idempotency_keys' in out
        assert 'ADD COLUMN idempotency_key' in out
        # 0004 no tiene backfill: el único UPDATE permitido es el
        # housekeeping de alembic_version que emite el propio Alembic.
        data_updates = [
            ln for ln in out.splitlines()
            if ln.strip().upper().startswith('UPDATE')
            and 'alembic_version' not in ln
        ]
        assert data_updates == []


class TestModeloAlineado:
    def test_model_aligned_with_migration(self, app):
        """models.ApiIdempotencyKey y Trip.idempotency_key alineados con 0004."""
        with app.app_context():
            from backend.models import ApiIdempotencyKey, db
            assert 'api_idempotency_keys' in db.metadata.tables
            trip_cols = {c.name for c in db.metadata.tables['trips'].columns}
            assert 'idempotency_key' in trip_cols
            uqs = [
                c.name for c in ApiIdempotencyKey.__table__.constraints
                if getattr(c, 'name', None)
            ]
            assert 'uq_idempotency_user_key_method' in uqs
