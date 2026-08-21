"""Etapa 1 — migración 0003: driver_profiles.status (contrato §7).

Verifica contra una BD SQLite temporal (archivo) que la migración:
- agrega la columna `status` (NOT NULL, server_default 'pending')
- backfillea TODOS los existentes a 'approved' (nadie queda bloqueado)
- preserva `is_verified` intacto (legacy/presentación, no autoriza)
- crea el CHECK chk_driver_profile_status (pending|approved|rejected)
- es reversible (downgrade sin pérdida de datos)
- en modo offline (--sql) no intenta el backfill de datos
Y que el modelo SQLAlchemy está alineado con la migración (mismo CHECK,
mismo default).
"""
import os
import sqlite3

import pytest
from alembic import command
from alembic.config import Config

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

PRE_0003_DDL = """
CREATE TABLE driver_profiles (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL UNIQUE,
    is_online BOOLEAN,
    is_busy BOOLEAN,
    lat FLOAT,
    lng FLOAT,
    last_location_update DATETIME,
    is_verified BOOLEAN,
    accepted_payments VARCHAR(500),
    mercadopago_qr VARCHAR(500),
    carnet_conducir VARCHAR(120),
    tipo_seguro VARCHAR(120),
    ultimo_servicio VARCHAR(120)
);
CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY);
"""


def _prepare_pre_0003_db(path):
    """Replica el esquema post-0002 (sin status) y lo marca en la versión 0002."""
    con = sqlite3.connect(path)
    con.executescript(PRE_0003_DDL)
    con.execute(
        "INSERT INTO driver_profiles (user_id, is_online, is_verified) "
        "VALUES (1, 1, 1), (2, 0, 0), (3, 1, NULL)"
    )
    con.execute("INSERT INTO alembic_version VALUES ('0002')")
    con.commit()
    con.close()


@pytest.fixture
def alembic_cfg(tmp_path, monkeypatch):
    db_path = tmp_path / 'van_0003.db'
    _prepare_pre_0003_db(str(db_path))
    monkeypatch.setenv('DATABASE_URL', f"sqlite:///{db_path.as_posix()}")
    cfg = Config(os.path.join(PROJECT_ROOT, 'alembic.ini'))
    cfg.set_main_option('script_location', os.path.join(PROJECT_ROOT, 'migrations'))
    return cfg, str(db_path)


@pytest.fixture
def upgraded(alembic_cfg):
    cfg, db_path = alembic_cfg
    command.upgrade(cfg, 'head')
    return cfg, db_path


def _fetch(db_path, sql, params=()):
    con = sqlite3.connect(db_path)
    try:
        return con.execute(sql, params).fetchall()
    finally:
        con.close()


class TestUpgrade:
    def test_version_0003(self, upgraded):
        _, db_path = upgraded
        assert _fetch(db_path, 'SELECT version_num FROM alembic_version') == [('0003',)]

    def test_columna_status_existe(self, upgraded):
        _, db_path = upgraded
        cols = {r[1] for r in _fetch(db_path, 'PRAGMA table_info(driver_profiles)')}
        assert 'status' in cols

    def test_backfill_todos_los_existentes_a_approved(self, upgraded):
        """is_verified=1, is_verified=0 y NULL → todos 'approved' (contrato §7)."""
        _, db_path = upgraded
        rows = _fetch(db_path, 'SELECT user_id, status FROM driver_profiles ORDER BY user_id')
        assert rows == [(1, 'approved'), (2, 'approved'), (3, 'approved')]

    def test_backfill_no_toca_is_verified(self, upgraded):
        """is_verified queda intacto: sigue siendo solo presentación/legacy."""
        _, db_path = upgraded
        rows = _fetch(db_path, 'SELECT user_id, is_verified FROM driver_profiles ORDER BY user_id')
        assert rows == [(1, 1), (2, 0), (3, None)]

    def test_server_default_pending_para_nuevos(self, upgraded):
        _, db_path = upgraded
        con = sqlite3.connect(db_path)
        con.execute("INSERT INTO driver_profiles (user_id) VALUES (4)")
        con.commit()
        con.close()
        assert _fetch(db_path, "SELECT status FROM driver_profiles WHERE user_id = 4") == [('pending',)]

    def test_check_constraint_rechaza_invalido(self, upgraded):
        _, db_path = upgraded
        con = sqlite3.connect(db_path)
        with pytest.raises(sqlite3.IntegrityError):
            con.execute("INSERT INTO driver_profiles (user_id, status) VALUES (5, 'bogus')")
        con.close()

    def test_check_constraint_acepta_approved_y_rejected(self, upgraded):
        _, db_path = upgraded
        con = sqlite3.connect(db_path)
        con.execute("INSERT INTO driver_profiles (user_id, status) VALUES (5, 'rejected')")
        con.execute("INSERT INTO driver_profiles (user_id, status) VALUES (6, 'approved')")
        con.commit()
        con.close()
        rows = _fetch(db_path, "SELECT user_id, status FROM driver_profiles WHERE user_id IN (5, 6)")
        assert rows == [(5, 'rejected'), (6, 'approved')]


class TestDowngrade:
    def test_downgrade_elimina_status_sin_perder_datos(self, upgraded):
        cfg, db_path = upgraded
        command.downgrade(cfg, '0002')
        cols = {r[1] for r in _fetch(db_path, 'PRAGMA table_info(driver_profiles)')}
        assert 'status' not in cols
        assert _fetch(db_path, 'SELECT version_num FROM alembic_version') == [('0002',)]
        assert _fetch(db_path, 'SELECT COUNT(*) FROM driver_profiles') == [(3,)]


class TestOfflineMode:
    def test_render_sql_no_ejecuta_backfill(self, monkeypatch, capsys):
        """--sql: renderiza ADD COLUMN + CHECK pero NO el UPDATE de backfill."""
        monkeypatch.setenv('DATABASE_URL', 'postgresql+psycopg://x:x@localhost:5432/van')
        cfg = Config(os.path.join(PROJECT_ROOT, 'alembic.ini'))
        cfg.set_main_option('script_location', os.path.join(PROJECT_ROOT, 'migrations'))
        command.upgrade(cfg, 'head', sql=True)
        out = capsys.readouterr().out
        assert 'ADD COLUMN status' in out
        assert 'chk_driver_profile_status' in out
        assert 'SET status' not in out


class TestModeloAlineado:
    def test_model_check_rechaza_status_invalido(self, app):
        from sqlalchemy.exc import IntegrityError

        from backend.models import DRIVER_STATUS_APPROVED, DRIVER_STATUS_PENDING, DriverProfile, User, db
        with app.app_context():
            user = User(name='C', email='c-model@van.test', password='x', role='driver')
            user.driver_profile = DriverProfile(user_id=user.id, status='bogus')
            db.session.add(user)
            with pytest.raises(IntegrityError):
                db.session.commit()
            db.session.rollback()

    def test_model_default_pending_y_approved_ok(self, app):
        from backend.models import DRIVER_STATUS_APPROVED, DRIVER_STATUS_PENDING, DriverProfile, User, db
        with app.app_context():
            u1 = User(name='A', email='a-model@van.test', password='x', role='driver')
            u1.driver_profile = DriverProfile(user_id=u1.id)
            u2 = User(name='B', email='b-model@van.test', password='x', role='driver')
            u2.driver_profile = DriverProfile(user_id=u2.id, status=DRIVER_STATUS_APPROVED)
            db.session.add_all([u1, u2])
            db.session.commit()
            assert u1.driver_profile.status == DRIVER_STATUS_PENDING
            assert u2.driver_profile.status == DRIVER_STATUS_APPROVED

    def test_constantes_coinciden_con_la_migracion(self):
        from backend.models import DRIVER_STATUSES
        assert DRIVER_STATUSES == ('pending', 'approved', 'rejected')
