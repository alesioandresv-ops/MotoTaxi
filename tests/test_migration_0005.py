"""Migración 0005: trips.payment_status / paid_at / payment_method_collected.

Verifica contra una BD SQLite temporal (archivo) que la migración:
- agrega las 3 columnas de cobro (payment_status NOT NULL default 'pending')
- backfillea SOLO los viajes completados a 'paid' (ya cobrados por definición)
- deja requested/accepted/ongoing/cancelled como 'pending'
- crea el CHECK chk_trip_payment_status (pending|paid)
- es reversible (downgrade sin pérdida de datos)
- en modo offline (--sql, rango 0004:0005) no intenta el backfill de datos
Y que el modelo SQLAlchemy está alineado con la migración.
"""
import os
import sqlite3

import pytest
from alembic import command
from alembic.config import Config

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

# Esquema post-0004 (sin las columnas de cobro). Sin FKs explícitas:
# SQLite no las enforcea por defecto y el fixture mínimo no crea users.
PRE_0005_DDL = """
CREATE TABLE trips (
    id INTEGER PRIMARY KEY,
    passenger_id INTEGER NOT NULL,
    driver_id INTEGER,
    vehicle_type VARCHAR(10),
    pickup_address VARCHAR(255),
    dropoff_address VARCHAR(255),
    distance_km NUMERIC,
    duration_min INTEGER,
    total_fare NUMERIC(12,2) NOT NULL,
    platform_fee NUMERIC(12,2),
    driver_earnings NUMERIC(12,2),
    currency VARCHAR(3),
    status VARCHAR(20) NOT NULL,
    requested_at DATETIME,
    started_at DATETIME,
    completed_at DATETIME,
    cancelled_by VARCHAR(20),
    payment_method VARCHAR(50),
    idempotency_key VARCHAR(255)
);
CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY);
"""


def _prepare_pre_0005_db(path):
    """Replica el esquema post-0004 con viajes en varios estados y marca 0004."""
    con = sqlite3.connect(path)
    con.executescript(PRE_0005_DDL)

    def _trip(n, status):
        con.execute(
            "INSERT INTO trips (passenger_id, pickup_address, dropoff_address,"
            " total_fare, platform_fee, driver_earnings, currency, status)"
            f" VALUES ({n}, 'A{n}', 'B{n}', 50, 0, 50, 'ARS', '{status}')"
        )

    _trip(1, 'completed')   # → backfill 'paid'
    _trip(2, 'completed')   # → backfill 'paid'
    _trip(3, 'requested')   # → queda 'pending'
    _trip(4, 'ongoing')     # → queda 'pending'
    _trip(5, 'cancelled')   # → queda 'pending'
    con.execute("INSERT INTO alembic_version VALUES ('0004')")
    con.commit()
    con.close()


@pytest.fixture
def alembic_cfg(tmp_path, monkeypatch):
    db_path = tmp_path / 'van_0005.db'
    _prepare_pre_0005_db(str(db_path))
    monkeypatch.setenv('DATABASE_URL', f"sqlite:///{db_path.as_posix()}")
    cfg = Config(os.path.join(PROJECT_ROOT, 'alembic.ini'))
    cfg.set_main_option('script_location', os.path.join(PROJECT_ROOT, 'migrations'))
    return cfg, str(db_path)


@pytest.fixture
def upgraded(alembic_cfg):
    cfg, db_path = alembic_cfg
    # Target fijo (no 'head'): este archivo prueba SOLO 0005.
    command.upgrade(cfg, '0005')
    return cfg, db_path


def _fetch(db_path, sql, params=()):
    con = sqlite3.connect(db_path)
    try:
        return con.execute(sql, params).fetchall()
    finally:
        con.close()


class TestUpgrade:
    def test_version_0005(self, upgraded):
        _, db_path = upgraded
        assert _fetch(db_path, 'SELECT version_num FROM alembic_version') == [('0005',)]

    def test_columnas_cobro_existen(self, upgraded):
        _, db_path = upgraded
        cols = {r[1] for r in _fetch(db_path, 'PRAGMA table_info(trips)')}
        assert {'payment_status', 'paid_at', 'payment_method_collected'} <= cols

    def test_backfill_solo_completados_a_paid(self, upgraded):
        _, db_path = upgraded
        rows = dict(_fetch(db_path, 'SELECT id, payment_status FROM trips'))
        assert rows == {1: 'paid', 2: 'paid', 3: 'pending', 4: 'pending', 5: 'pending'}

    def test_backfill_no_toca_otras_columnas(self, upgraded):
        _, db_path = upgraded
        rows = _fetch(
            db_path,
            "SELECT id, status FROM trips ORDER BY id",
        )
        assert rows == [
            (1, 'completed'), (2, 'completed'), (3, 'requested'),
            (4, 'ongoing'), (5, 'cancelled'),
        ]

    def test_server_default_pending_para_nuevos(self, upgraded):
        _, db_path = upgraded
        con = sqlite3.connect(db_path)
        con.execute(
            "INSERT INTO trips (passenger_id, pickup_address, dropoff_address,"
            " total_fare, platform_fee, driver_earnings, currency, status)"
            " VALUES (9, 'A9', 'B9', 50, 0, 50, 'ARS', 'requested')"
        )
        con.commit()
        con.close()
        rows = _fetch(db_path, 'SELECT payment_status FROM trips WHERE passenger_id = 9')
        assert rows == [('pending',)]

    def test_check_constraint_rechaza_invalido(self, upgraded):
        _, db_path = upgraded
        con = sqlite3.connect(db_path)
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(
                "UPDATE trips SET payment_status = 'bogus' WHERE id = 1"
            )
        con.close()

    def test_paid_y_pending_aceptados(self, upgraded):
        _, db_path = upgraded
        con = sqlite3.connect(db_path)
        con.execute("UPDATE trips SET payment_status = 'paid' WHERE id = 3")
        con.commit()
        con.close()
        rows = dict(_fetch(db_path, 'SELECT id, payment_status FROM trips'))
        assert rows[3] == 'paid'


class TestDowngrade:
    def test_downgrade_elimina_columnas_sin_perder_datos(self, upgraded):
        cfg, db_path = upgraded
        command.downgrade(cfg, '0004')
        cols = {r[1] for r in _fetch(db_path, 'PRAGMA table_info(trips)')}
        assert not {'payment_status', 'paid_at', 'payment_method_collected'} & cols
        assert _fetch(db_path, 'SELECT version_num FROM alembic_version') == [('0004',)]
        assert _fetch(db_path, 'SELECT COUNT(*) FROM trips') == [(5,)]


class TestOfflineMode:
    def test_render_sql_no_ejecuta_backfill(self, monkeypatch, capsys):
        """--sql (rango 0004:0005): DDL sí, UPDATE de backfill no."""
        monkeypatch.setenv('DATABASE_URL', 'postgresql+psycopg://x:x@localhost:5432/van')
        cfg = Config(os.path.join(PROJECT_ROOT, 'alembic.ini'))
        cfg.set_main_option('script_location', os.path.join(PROJECT_ROOT, 'migrations'))
        command.upgrade(cfg, '0004:0005', sql=True)
        out = capsys.readouterr().out
        assert 'ADD COLUMN payment_status' in out
        assert 'chk_trip_payment_status' in out
        assert "SET payment_status" not in out


class TestModeloAlineado:
    def test_model_check_rechaza_payment_status_invalido(self, app):
        from sqlalchemy.exc import IntegrityError

        from backend.models import Trip, db
        with app.app_context():
            trip = Trip(
                passenger_id=1, pickup_address='A', dropoff_address='B',
                total_fare=50, platform_fee=0, driver_earnings=50,
                vehicle_type='moto', status='requested', payment_status='bogus',
            )
            db.session.add(trip)
            with pytest.raises(IntegrityError):
                db.session.commit()
            db.session.rollback()

    def test_model_default_pending(self, app):
        from backend.models import TRIP_PAYMENT_PENDING, Trip, db
        with app.app_context():
            trip = Trip(
                passenger_id=1, pickup_address='A', dropoff_address='B',
                total_fare=50, platform_fee=0, driver_earnings=50,
                vehicle_type='moto', status='requested',
            )
            db.session.add(trip)
            db.session.commit()
            assert trip.payment_status == TRIP_PAYMENT_PENDING

    def test_constantes_coinciden_con_la_migracion(self):
        from backend.models import TRIP_PAYMENT_STATUSES
        assert TRIP_PAYMENT_STATUSES == ('pending', 'paid')
