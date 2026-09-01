"""Migración 0007: topup_requests.preference_id.

Trazabilidad de recargas MP checkout: la preferencia se persiste (pending)
antes de redirigir al usuario. Bajo prueba contra SQLite temporal:
- agrega la columna nullable preference_id
- acepta filas con y sin preference_id
- es reversible
"""
import os
import sqlite3

import pytest
from alembic import command
from alembic.config import Config

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

# Esquema post-0006: topup_requests con índice único parcial, sin preference_id.
PRE_0007_DDL = """
CREATE TABLE topup_requests (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    amount NUMERIC(12,2) NOT NULL,
    method VARCHAR(30),
    voucher_url VARCHAR(500),
    mp_payment_id VARCHAR(100),
    status VARCHAR(20),
    admin_note VARCHAR(200),
    created_at DATETIME,
    confirmed_at DATETIME
);
CREATE UNIQUE INDEX uq_topup_requests_mp_payment_id
    ON topup_requests (mp_payment_id) WHERE mp_payment_id IS NOT NULL;
CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY);
"""


def _prepare_db(path):
    con = sqlite3.connect(path)
    con.executescript(PRE_0007_DDL)
    con.execute("INSERT INTO alembic_version VALUES ('0006')")
    con.commit()
    con.close()


@pytest.fixture
def upgraded(tmp_path, monkeypatch):
    db_path = tmp_path / 'van_0007.db'
    _prepare_db(str(db_path))
    monkeypatch.setenv('DATABASE_URL', f"sqlite:///{db_path.as_posix()}")
    cfg = Config(os.path.join(PROJECT_ROOT, 'alembic.ini'))
    cfg.set_main_option('script_location', os.path.join(PROJECT_ROOT, 'migrations'))
    command.upgrade(cfg, '0007')
    return str(db_path)


def _fetch(db_path, sql):
    con = sqlite3.connect(db_path)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


class TestUpgrade0007:
    def test_version(self, upgraded):
        assert _fetch(upgraded, 'SELECT version_num FROM alembic_version') == [('0007',)]

    def test_columna_existe(self, upgraded):
        cols = [r[1] for r in _fetch(upgraded, "PRAGMA table_info(topup_requests)")]
        assert 'preference_id' in cols

    def test_filas_sin_preference_id_aceptadas(self, upgraded):
        con = sqlite3.connect(upgraded)
        con.execute(
            "INSERT INTO topup_requests (user_id, amount, method, status)"
            " VALUES (1, 100, 'transferencia', 'confirmed')"
        )
        con.commit()
        con.close()
        assert _fetch(upgraded, 'SELECT COUNT(*) FROM topup_requests') == [(1,)]

    def test_preference_id_se_puede_guardar(self, upgraded):
        con = sqlite3.connect(upgraded)
        con.execute(
            "INSERT INTO topup_requests (user_id, amount, method, preference_id, status)"
            " VALUES (2, 500, 'mp_checkout', 'PREF-ABC', 'pending')"
        )
        con.commit()
        con.close()
        assert _fetch(
            upgraded, "SELECT preference_id FROM topup_requests WHERE user_id=2"
        ) == [('PREF-ABC',)]

    def test_indice_previo_sobrevive(self, upgraded):
        idx = _fetch(upgraded, "SELECT name FROM sqlite_master WHERE type='index'")
        assert any('uq_topup_requests_mp_payment_id' == r[0] for r in idx)


class TestDowngrade0007:
    def test_downgrade_elimina_columna(self, upgraded):
        cfg = Config(os.path.join(PROJECT_ROOT, 'alembic.ini'))
        cfg.set_main_option('script_location', os.path.join(PROJECT_ROOT, 'migrations'))
        os.environ['DATABASE_URL'] = f'sqlite:///{upgraded}'
        try:
            command.downgrade(cfg, '0006')
        finally:
            os.environ.pop('DATABASE_URL', None)
        cols = [r[1] for r in _fetch(upgraded, "PRAGMA table_info(topup_requests)")]
        assert 'preference_id' not in cols
