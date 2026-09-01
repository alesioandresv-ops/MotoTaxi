"""Migración 0006: índice único parcial topup_requests.mp_payment_id.

Blinda la idempotencia de recargas MP a nivel BD (el pre-check en
_credit_mp_payment deja ventana de carrera ante webhooks concurrentes).
Bajo prueba contra SQLite temporal:
- crea el índice único parcial
- rechaza dos confirmaciones con el mismo mp_payment_id
- permite múltiples NULL (recargas manuales sin MP)
- es reversible
"""
import os
import sqlite3

import pytest
from alembic import command
from alembic.config import Config

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

# Esquema post-0005: solo la tabla involucrada. Sin FKs explícitas.
PRE_0006_DDL = """
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
CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY);
"""


def _prepare_db(path):
    con = sqlite3.connect(path)
    con.executescript(PRE_0006_DDL)
    con.execute("INSERT INTO alembic_version VALUES ('0005')")
    con.commit()
    con.close()


@pytest.fixture
def upgraded(tmp_path, monkeypatch):
    db_path = tmp_path / 'van_0006.db'
    _prepare_db(str(db_path))
    monkeypatch.setenv('DATABASE_URL', f"sqlite:///{db_path.as_posix()}")
    cfg = Config(os.path.join(PROJECT_ROOT, 'alembic.ini'))
    cfg.set_main_option('script_location', os.path.join(PROJECT_ROOT, 'migrations'))
    command.upgrade(cfg, '0006')
    return str(db_path)


def _fetch(db_path, sql):
    con = sqlite3.connect(db_path)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


class TestUpgrade0006:
    def test_version(self, upgraded):
        assert _fetch(upgraded, 'SELECT version_num FROM alembic_version') == [('0006',)]

    def test_indice_parcial_existe(self, upgraded):
        idx = _fetch(upgraded, "SELECT name FROM sqlite_master WHERE type='index'")
        assert any('uq_topup_requests_mp_payment_id' == r[0] for r in idx)

    def test_mp_payment_id_duplicado_rechazado(self, upgraded):
        con = sqlite3.connect(upgraded)
        con.execute(
            "INSERT INTO topup_requests (user_id, amount, method, mp_payment_id, status)"
            " VALUES (1, 500, 'mp_checkout', '9999', 'confirmed')"
        )
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(
                "INSERT INTO topup_requests (user_id, amount, method, mp_payment_id, status)"
                " VALUES (2, 500, 'mp_checkout', '9999', 'confirmed')"
            )
        con.close()

    def test_nulls_permitidos_en_multiples_filas(self, upgraded):
        """Recargas manuales (transferencia/efectivo) no tienen mp_payment_id."""
        con = sqlite3.connect(upgraded)
        for uid in (1, 2, 3):
            con.execute(
                "INSERT INTO topup_requests (user_id, amount, method, mp_payment_id, status)"
                f" VALUES ({uid}, 100, 'transferencia', NULL, 'pending')"
            )
        con.commit()
        con.close()
        assert _fetch(upgraded, 'SELECT COUNT(*) FROM topup_requests') == [(3,)]

    def test_ids_distintos_aceptados(self, upgraded):
        con = sqlite3.connect(upgraded)
        con.execute(
            "INSERT INTO topup_requests (user_id, amount, method, mp_payment_id, status)"
            " VALUES (1, 100, 'mp_checkout', '1', 'confirmed')"
        )
        con.execute(
            "INSERT INTO topup_requests (user_id, amount, method, mp_payment_id, status)"
            " VALUES (1, 200, 'mp_checkout', '2', 'confirmed')"
        )
        con.commit()
        con.close()


class TestDowngrade0006:
    def test_downgrade_elimina_indice(self, upgraded):
        db_path = upgraded
        monkey_cfg = Config(os.path.join(PROJECT_ROOT, 'alembic.ini'))
        monkey_cfg.set_main_option('script_location', os.path.join(PROJECT_ROOT, 'migrations'))
        import os as _os
        _os.environ['DATABASE_URL'] = f'sqlite:///{db_path}'
        command.downgrade(monkey_cfg, '0005')
        idx = _fetch(db_path, "SELECT name FROM sqlite_master WHERE type='index'")
        assert not any('uq_topup_requests_mp_payment_id' == r[0] for r in idx)
