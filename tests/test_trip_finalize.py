"""Unit tests de backend.services.trips.finalize_trip.

La única vía hacia `completed` ahora cobra:
- FORBIDDEN: conductor equivocado.
- Retry idempotente: completed+paid → resumen sin re-cobrar.
- INVALID_STATUS: solo desde ongoing (cancelled NO se puede completar).
- INVALID_METHOD: método fuera del set de PAYMENT_METHODS.
- billetera: débito total al pasajero, crédito earnings al conductor,
  y saldo insuficiente → PAYMENT_INSUFFICIENT_BALANCE sin mutar nada.
- No-billetera: no toca saldos; marca paid + método + paid_at.
- Libera al conductor (is_busy=False).
- upsert_favorite_route: crea y luego incrementa el contador.
"""
from datetime import datetime, timedelta

import pytest

from backend.models import (
    DriverProfile, FavoriteAddress, Trip, User, WalletTransaction, db,
)
from backend.services.fare import as_decimal
from backend.services.trips import TripFinalizeError, finalize_trip, upsert_favorite_route


def _setup_ongoing(app, passenger_balance=1000.0):
    """Pasajero + conductor aprobado + viaje ongoing asignado al conductor."""
    from werkzeug.security import generate_password_hash

    with app.app_context():
        p = User(
            name='Pax', email='pax@t.com', password=generate_password_hash('x'),
            phone='3001111111', email_verified=True, balance=passenger_balance,
        )
        d = User(
            name='Drv', email='drv@t.com', password=generate_password_hash('x'),
            phone='3002222222', profile_picture='', email_verified=True,
            driver_profile=DriverProfile(
                is_online=True, is_busy=True, lat=-34.6, lng=-58.4,
            ),
        )
        db.session.add_all([p, d])
        db.session.commit()
        trip = Trip(
            passenger_id=p.id, driver_id=d.id,
            pickup_address='A', dropoff_address='B',
            pickup_lat=-34.60, pickup_lng=-58.38,
            dropoff_lat=-34.61, dropoff_lng=-58.39,
            distance_km=5.0, vehicle_type='moto', status='ongoing',
            requested_at=datetime.utcnow() - timedelta(minutes=15),
            started_at=datetime.utcnow() - timedelta(minutes=10),
            total_fare=10.5, platform_fee=as_decimal('0.53'),
            platform_fee_rate=0.05, driver_earnings=as_decimal('9.97'),
            currency='ARS', payment_method='billetera',
        )
        db.session.add(trip)
        db.session.commit()
        return p.id, d.id, trip.id


class TestFinalizeTrip:
    def test_billetera_cobra_y_completa(self, app):
        pid, did, tid = _setup_ongoing(app, passenger_balance=1000.0)
        with app.app_context():
            trip = db.session.get(Trip, tid)
            driver = db.session.get(User, did)
            summary = finalize_trip(trip, driver, 'billetera')
            db.session.commit()

            assert summary['status'] == 'completed'
            assert summary['payment_status'] == 'paid'
            assert summary['payment_method_collected'] == 'billetera'
            # Duración ~10 min → tarifa recalculada 3 + 5*1.5 + 10*0.25 = 13.0
            fare = float(summary['total_fare'])
            assert abs(fare - 13.0) < 0.5
            pax = db.session.get(User, pid)
            drv = db.session.get(User, did)
            assert float(pax.balance) == round(1000.0 - fare, 2)
            assert float(drv.balance) == round(float(summary['driver_earnings']), 2)
            # Dos transacciones espejadas del viaje
            txs = WalletTransaction.query.filter_by(trip_id=tid).all()
            assert len(txs) == 2

    def test_efectivo_no_toca_saldos(self, app):
        pid, did, tid = _setup_ongoing(app)
        with app.app_context():
            trip = db.session.get(Trip, tid)
            driver = db.session.get(User, did)
            finalize_trip(trip, driver, 'efectivo')
            db.session.commit()

            assert float(db.session.get(User, pid).balance) == 1000.0
            assert float(db.session.get(User, did).balance) == 0.0
            assert WalletTransaction.query.count() == 0
            t = db.session.get(Trip, tid)
            assert t.status == 'completed'
            assert t.payment_status == 'paid'
            assert t.payment_method_collected == 'efectivo'
            assert t.paid_at is not None

    def test_libera_al_conductor(self, app):
        _, did, tid = _setup_ongoing(app)
        with app.app_context():
            trip = db.session.get(Trip, tid)
            driver = db.session.get(User, did)
            finalize_trip(trip, driver, 'efectivo')
            db.session.commit()
            profile = DriverProfile.query.filter_by(user_id=did).first()
            assert profile.is_busy is False

    def test_retry_idempotente_no_recobra(self, app):
        pid, did, tid = _setup_ongoing(app, passenger_balance=100.0)
        with app.app_context():
            trip = db.session.get(Trip, tid)
            driver = db.session.get(User, did)
            finalize_trip(trip, driver, 'billetera')
            db.session.commit()
            balance_tras_primero = float(db.session.get(User, pid).balance)

            summary2 = finalize_trip(db.session.get(Trip, tid), driver, 'efectivo')
            db.session.commit()
            assert summary2['payment_method_collected'] == 'billetera'  # el original
            assert float(db.session.get(User, pid).balance) == balance_tras_primero
            assert WalletTransaction.query.count() == 2  # las del primer cobro


class TestFinalizeTripErrores:
    def test_forbidden_otro_conductor(self, app):
        from werkzeug.security import generate_password_hash

        _, _, tid = _setup_ongoing(app)
        with app.app_context():
            other = User(
                name='Otro', email='otro@t.com',
                password=generate_password_hash('x'), phone='3003333333',
            )
            db.session.add(other)
            db.session.commit()
            with pytest.raises(TripFinalizeError) as exc:
                finalize_trip(db.session.get(Trip, tid), other, 'efectivo')
            assert exc.value.code == 'FORBIDDEN'

    def test_invalid_status_cancelled(self, app):
        _, did, tid = _setup_ongoing(app)
        with app.app_context():
            t = db.session.get(Trip, tid)
            t.status = 'cancelled'
            db.session.commit()
            with pytest.raises(TripFinalizeError) as exc:
                finalize_trip(t, db.session.get(User, did), 'efectivo')
            assert exc.value.code == 'INVALID_STATUS'

    def test_invalid_method(self, app):
        _, did, tid = _setup_ongoing(app)
        with app.app_context():
            with pytest.raises(TripFinalizeError) as exc:
                finalize_trip(
                    db.session.get(Trip, tid),
                    db.session.get(User, did), 'trueque',
                )
            assert exc.value.code == 'INVALID_METHOD'

    def test_billetera_insuficiente_no_muta_nada(self, app):
        """El viaje NO se completa si la billetera no alcanza: nada de deuda
        fantasma ni estado parcial."""
        pid, did, tid = _setup_ongoing(app, passenger_balance=1.0)
        with app.app_context():
            with pytest.raises(TripFinalizeError) as exc:
                finalize_trip(
                    db.session.get(Trip, tid),
                    db.session.get(User, did), 'billetera',
                )
            assert exc.value.code == 'PAYMENT_INSUFFICIENT_BALANCE'
            db.session.rollback()

            t = db.session.get(Trip, tid)
            assert t.status == 'ongoing'
            assert t.payment_status == 'pending'
            assert t.paid_at is None
            assert float(db.session.get(User, pid).balance) == 1.0
            assert WalletTransaction.query.count() == 0


class TestUpsertFavoriteRoute:
    def test_crea_y_luego_incrementa(self, app):
        pid, _, tid = _setup_ongoing(app)
        with app.app_context():
            trip = db.session.get(Trip, tid)
            upsert_favorite_route(trip)
            favs = FavoriteAddress.query.filter_by(user_id=pid).all()
            assert len(favs) == 1
            assert favs[0].count == 1

            upsert_favorite_route(trip)
            favs = FavoriteAddress.query.filter_by(user_id=pid).all()
            assert len(favs) == 1
            assert favs[0].count == 2
