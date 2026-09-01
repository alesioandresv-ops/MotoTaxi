"""Etapa 2 — POST /trips (contrato §§4.2, 5.1, 5.2, 5.6.1, 11, 16.1).

Cubre: validaciones, ACTIVE_TRIP_EXISTS, fare estimate (rate 0.05 y
desactivado), company auto-asignado (D9, ignora el del cliente) e
idempotencia completa (replay 200, claves distintas, aislamiento por
usuario, expiración 24h, body deprecated).
"""
import json
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

REGISTER = {
    'name': 'Ana Pérez',
    'email': 'ana@test.com',
    'password': 'Pass1234',
    'phone': '3001112233',
}

# Coordenadas fijas (CABA): evitan cualquier llamada a Nominatim en tests.
BASE_TRIP = {
    'pickup_address': 'Av Siempre Viva 742',
    'dropoff_address': 'Calle Falsa 123',
    'pickup_lat': -34.60,
    'pickup_lng': -58.38,
    'dropoff_lat': -34.62,
    'dropoff_lng': -58.40,
    'vehicle_type': 'moto',
    'payment_method': 'efectivo',
}


def _api(client, method, path, token=None, data=None, headers=None):
    hdrs = dict(headers or {})
    if token:
        hdrs['Authorization'] = f'Bearer {token}'
    return client.open(
        path, method=method, headers=hdrs,
        data=json.dumps(data) if data is not None else None,
        content_type='application/json',
    )


def _register(client, email='ana@test.com'):
    payload = dict(REGISTER, email=email)
    rv = _api(client, 'POST', '/api/v1/auth/register', data=payload)
    assert rv.status_code == 201, rv.get_json()
    return rv.get_json()['data']['tokens']['access_token']


def _create(client, token, key=None, **overrides):
    payload = dict(BASE_TRIP, **overrides)
    hdrs = {'Idempotency-Key': key} if key is not None else {}
    return _api(client, 'POST', '/api/v1/trips', token=token,
                data=payload, headers=hdrs)


def _new_key():
    return str(uuid.uuid4())


def _expected_fare(dist_km, vehicle_type):
    from backend.services.fare import build_fare
    return build_fare(dist_km, 0, vehicle_type)


# ─────────────────────────── Auth / modo ───────────────────────────

class TestAuth:
    def test_requires_token(self, client):
        rv = _api(client, 'POST', '/api/v1/trips', data=BASE_TRIP)
        assert rv.status_code == 401
        assert rv.get_json()['error']['code'] == 'MISSING_TOKEN'

    def test_requires_passenger_role(self, app, client):
        token = _register(client)
        with app.app_context():
            from backend.models import db, User
            user = User.query.filter_by(email='ana@test.com').first()
            user.role = 'driver'
            db.session.commit()
        rv = _create(client, token, key=_new_key())
        assert rv.status_code == 403
        assert rv.get_json()['error']['code'] == 'FORBIDDEN'


# ─────────────────────────── Validaciones ───────────────────────────

class TestValidation:
    def test_missing_pickup_address(self, client):
        token = _register(client)
        rv = _create(client, token, key=_new_key(), pickup_address='')
        assert rv.status_code == 400
        assert rv.get_json()['error']['code'] == 'VALIDATION_ERROR'

    def test_missing_dropoff_address(self, client):
        token = _register(client)
        rv = _create(client, token, key=_new_key(), dropoff_address=None)
        assert rv.status_code == 400
        assert rv.get_json()['error']['code'] == 'VALIDATION_ERROR'

    def test_invalid_vehicle_type(self, client):
        token = _register(client)
        rv = _create(client, token, key=_new_key(), vehicle_type='avion')
        assert rv.status_code == 400
        assert rv.get_json()['error']['code'] == 'INVALID_VEHICLE_TYPE'

    def test_invalid_payment_method(self, client):
        token = _register(client)
        rv = _create(client, token, key=_new_key(), payment_method='cripto')
        assert rv.status_code == 400
        assert rv.get_json()['error']['code'] == 'INVALID_PAYMENT_METHOD'

    def test_missing_idempotency_key(self, client):
        token = _register(client)
        rv = _create(client, token, key='')  # sin header ni body
        assert rv.status_code == 400
        assert rv.get_json()['error']['code'] == 'VALIDATION_ERROR'

    def test_body_key_deprecated_accepted(self, client):
        """Body idempotency_key funciona (deprecated) y hace replay."""
        token = _register(client)
        key = _new_key()
        rv1 = _api(client, 'POST', '/api/v1/trips', token=token,
                   data=dict(BASE_TRIP, idempotency_key=key))
        assert rv1.status_code == 201
        rv2 = _api(client, 'POST', '/api/v1/trips', token=token,
                   data=dict(BASE_TRIP, idempotency_key=key))
        assert rv2.status_code == 200
        assert rv2.get_json()['data']['duplicate'] is True

    def test_header_wins_over_body(self, app, client):
        """Header y body distintos → gana el header (contrato §11)."""
        token = _register(client)
        header_key, body_key = _new_key(), _new_key()
        rv = _api(client, 'POST', '/api/v1/trips', token=token,
                  data=dict(BASE_TRIP, idempotency_key=body_key),
                  headers={'Idempotency-Key': header_key})
        assert rv.status_code == 201
        trip_id = rv.get_json()['data']['trip']['id']
        with app.app_context():
            from backend.models import Trip
            assert Trip.query.get(trip_id).idempotency_key == header_key

    def test_oversized_key_rejected(self, client):
        token = _register(client)
        rv = _create(client, token, key='x' * 256)
        assert rv.status_code == 400
        assert rv.get_json()['error']['code'] == 'VALIDATION_ERROR'

    def test_envelope_shape(self, client):
        token = _register(client)
        rv = _create(client, token, key=_new_key())
        body = rv.get_json()
        assert rv.status_code == 201
        assert body['success'] is True
        assert set(body['data'].keys()) == {'trip', 'duplicate'}
        assert body['data']['duplicate'] is False
        trip = body['data']['trip']
        assert trip['status'] == 'requested'
        assert trip['driver'] is None
        assert trip['fare']['final'] is None
        assert isinstance(trip['fare']['estimate']['total_fare'], str)
        # Desglose canónico de 5 campos (§5.1)
        assert set(trip['fare']['estimate'].keys()) == {
            'total_fare', 'platform_fee', 'platform_fee_rate',
            'driver_earnings', 'currency',
        }
        assert trip['wallet'] == {'charged': False, 'passenger_txn_id': None, 'driver_txn_id': None}
        assert trip['passenger']['name'] == 'Ana Pérez'


# ─────────────────────── Viaje activo único ───────────────────────

class TestActiveTripExists:
    def test_second_active_rejected(self, client):
        token = _register(client)
        rv1 = _create(client, token, key=_new_key())
        assert rv1.status_code == 201
        rv2 = _create(client, token, key=_new_key())  # clave distinta → nueva ejecución
        assert rv2.status_code == 409
        assert rv2.get_json()['error']['code'] == 'ACTIVE_TRIP_EXISTS'


# ─────────────────────────── Fare estimate ───────────────────────────

class TestFareEstimate:
    def test_estimate_with_platform_fee_rate(self, client, monkeypatch):
        monkeypatch.setenv('PLATFORM_FEE_RATE', '0.05')
        token = _register(client)
        rv = _create(client, token, key=_new_key())
        assert rv.status_code == 201
        trip = rv.get_json()['data']['trip']
        est = trip['fare']['estimate']
        assert est['platform_fee_rate'] == '0.05'
        total = Decimal(est['total_fare'])
        fee = Decimal(est['platform_fee'])
        earn = Decimal(est['driver_earnings'])
        assert fee > 0
        assert total == fee + earn  # invariante I1 (§8.1)
        assert trip['fare']['final'] is None  # requested → sin desglose final

    def test_estimate_sin_comision(self, client, monkeypatch):
        monkeypatch.delenv('PLATFORM_FEE_RATE', raising=False)
        token = _register(client)
        rv = _create(client, token, key=_new_key())
        assert rv.status_code == 201
        est = rv.get_json()['data']['trip']['fare']['estimate']
        assert est['platform_fee_rate'] is None
        assert Decimal(est['platform_fee']) == 0
        assert Decimal(est['driver_earnings']) == Decimal(est['total_fare'])

    def test_estimate_matches_build_fare_snapshot(self, client):
        token = _register(client)
        rv = _create(client, token, key=_new_key())
        assert rv.status_code == 201
        trip = rv.get_json()['data']['trip']
        from backend.services.fare import build_fare
        expected = build_fare(trip['distance_km'], 0, trip['vehicle_type'])
        est = trip['fare']['estimate']
        assert Decimal(est['total_fare']) == expected['total_fare']
        assert Decimal(est['platform_fee']) == expected['platform_fee']
        assert Decimal(est['driver_earnings']) == expected['driver_earnings']
        assert est['currency'] == expected['currency']


# ─────────────────── Company auto-asignado (contrato §10/D9) ───────────────────

class TestCompanyAutoAssign:
    def _seed_company(self, app, status='active'):
        with app.app_context():
            from backend.models import db, Company, CompanyMember, User
            user = User.query.filter_by(email='ana@test.com').first()
            company = Company(
                name='ACME SA',
                email=f'acme-{uuid.uuid4().hex[:8]}@test.com',
                password='x', plan='basic', status=status,
            )
            db.session.add(company)
            db.session.flush()
            db.session.add(CompanyMember(
                company_id=company.id, user_id=user.id, role='admin',
            ))
            db.session.commit()
            return company.id

    def test_auto_assigned_active(self, app, client):
        token = _register(client)
        company_id = self._seed_company(app, status='active')
        rv = _create(client, token, key=_new_key())
        assert rv.status_code == 201
        assert rv.get_json()['data']['trip']['company_id'] == company_id

    def test_auto_assigned_trial(self, app, client):
        token = _register(client)
        company_id = self._seed_company(app, status='trial')
        rv = _create(client, token, key=_new_key())
        assert rv.get_json()['data']['trip']['company_id'] == company_id

    def test_client_company_id_ignored(self, app, client):
        """El company_id que manda el cliente NO se usa (D9)."""
        token = _register(client)
        company_id = self._seed_company(app, status='active')
        rv = _create(client, token, key=_new_key(), company_id=9999)
        assert rv.status_code == 201
        assert rv.get_json()['data']['trip']['company_id'] == company_id

    def test_inactive_company_not_assigned(self, app, client):
        token = _register(client)
        self._seed_company(app, status='inactive')
        rv = _create(client, token, key=_new_key())
        assert rv.status_code == 201
        assert rv.get_json()['data']['trip']['company_id'] is None

    def test_no_membership_null(self, client):
        token = _register(client)
        rv = _create(client, token, key=_new_key())
        assert rv.get_json()['data']['trip']['company_id'] is None


# ─────────────────────── Idempotencia (contrato §11) ───────────────────────

class TestIdempotencyReplay:
    def test_same_header_key_replays(self, client):
        token = _register(client)
        key = _new_key()
        rv1 = _create(client, token, key=key)
        assert rv1.status_code == 201
        id1 = rv1.get_json()['data']['trip']['id']
        rv2 = _create(client, token, key=key)
        assert rv2.status_code == 200
        data2 = rv2.get_json()['data']
        assert data2['duplicate'] is True
        assert data2['trip']['id'] == id1

    def test_distinct_keys_new_trip(self, app, client):
        """Clave distinta → nueva ejecución (no replay del viaje anterior)."""
        token = _register(client)
        k1 = _new_key()
        rv1 = _create(client, token, key=k1)
        assert rv1.status_code == 201
        id1 = rv1.get_json()['data']['trip']['id']
        with app.app_context():
            from backend.models import db, Trip
            Trip.query.get(id1).status = 'cancelled'
            db.session.commit()
        rv2 = _create(client, token, key=_new_key())
        assert rv2.status_code == 201
        assert rv2.get_json()['data']['trip']['id'] != id1

    def test_keys_isolated_per_user(self, client):
        """La misma clave en otro usuario NO sirve el replay (UNIQUE por user)."""
        t1 = _register(client, email='u1@test.com')
        t2 = _register(client, email='u2@test.com')
        key = _new_key()
        rv1 = _create(client, t1, key=key)
        assert rv1.status_code == 201
        rv2 = _create(client, t2, key=key)
        assert rv2.status_code == 201
        assert rv2.get_json()['data']['duplicate'] is False

    def test_expired_key_reexecutes(self, app, client):
        """TTL 24 h vencido → la operación se re-ejecuta (limpieza perezosa)."""
        token = _register(client)
        key = _new_key()
        rv1 = _create(client, token, key=key)
        assert rv1.status_code == 201
        with app.app_context():
            from backend.models import ApiIdempotencyKey, User, db
            user = User.query.filter_by(email='ana@test.com').first()
            rec = ApiIdempotencyKey.query.filter_by(user_id=user.id, key=key).first()
            rec.created_at = datetime.utcnow() - timedelta(hours=25)
            db.session.commit()
        rv2 = _create(client, token, key=key)
        # Re-ejecutó la lógica (el viaje activo sigue → ACTIVE_TRIP_EXISTS),
        # no sirvió la respuesta guardada.
        assert rv2.status_code == 409
        assert rv2.get_json()['error']['code'] == 'ACTIVE_TRIP_EXISTS'
