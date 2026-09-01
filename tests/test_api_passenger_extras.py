"""Etapa A5 — Passenger extras: geocode, favorites, reviews, voucher.

Cubre: GET /geo/geocode, GET /favorites, GET /users/{id}/reviews,
POST /wallet/topups/{id}/voucher.
"""
import json
import uuid
from decimal import Decimal


REGISTER_PAX = {
    'name': 'Ana Pérez',
    'password': 'Pass1234',
    'phone': '3001112233',
}

REGISTER_DRIVER = {
    'name': 'Carlos Ruiz',
    'password': 'Pass1234',
    'phone': '3004445566',
    'vehicle_type': 'moto',
    'placa': 'ABC123',
    'moto_marca': 'Yamaha',
    'moto_modelo': 'R3',
    'moto_color': 'Rojo',
    'moto_cilindrada': '321',
    'tipo_seguro': 'Responsabilidad civil',
    'carnet_conducir': 'A1234567',
    'ultimo_servicio': '2026-07-01',
}

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


def _uniq(prefix):
    return f'{prefix}-{uuid.uuid4().hex[:8]}@test.com'


def _register_pax(client):
    email = _uniq('ana')
    rv = _api(client, 'POST', '/api/v1/auth/register',
              data=dict(REGISTER_PAX, email=email))
    assert rv.status_code == 201, rv.get_json()
    return email, rv.get_json()['data']['tokens']['access_token']


def _register_driver(app, client, approve=True, online=True):
    email = _uniq('carlos')
    rv = _api(client, 'POST', '/api/v1/auth/register/driver',
              data=dict(REGISTER_DRIVER, email=email))
    assert rv.status_code == 201, rv.get_json()
    token = rv.get_json()['data']['tokens']['access_token']
    from backend.models import db, User
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        profile = user.driver_profile
        if approve:
            profile.status = 'approved'
        profile.is_online = online
        db.session.commit()
    return email, token


def _fund(app, email, amount):
    from backend.models import db, User
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        user.balance = Decimal(str(amount))
        db.session.commit()


# ═══════════════════════ GET /geo/geocode ═══════════════════

class TestGeocode:

    def test_missing_q(self, app, client):
        _, token = _register_pax(client)
        rv = _api(client, 'GET', '/api/v1/geo/geocode', token=token)
        assert rv.status_code == 400

    def test_unauthenticated(self, client):
        rv = _api(client, 'GET', '/api/v1/geo/geocode?q=Buenos+Aires')
        assert rv.status_code == 401

    def test_valid_query(self, app, client):
        _, token = _register_pax(client)
        rv = _api(client, 'GET', '/api/v1/geo/geocode?q=Buenos+Aires', token=token)
        assert rv.status_code in (200, 404, 500)  # network-dependent
        if rv.status_code == 200:
            data = rv.get_json()['data']
            assert 'lat' in data
            assert 'lng' in data


# ═══════════════════════ GET /favorites ═══════════════════

class TestFavorites:

    def test_empty_initially(self, app, client):
        _, token = _register_pax(client)
        rv = _api(client, 'GET', '/api/v1/favorites', token=token)
        assert rv.status_code == 200
        assert rv.get_json()['data']['favorites'] == []

    def test_unauthenticated(self, client):
        rv = _api(client, 'GET', '/api/v1/favorites')
        assert rv.status_code == 401

    def test_with_frequent_routes(self, app, client):
        email, token = _register_pax(client)
        from backend.models import db, User, FavoriteAddress
        with app.app_context():
            user = User.query.filter_by(email=email).first()
            fa = FavoriteAddress(
                user_id=user.id, name='Casa',
                pickup_address='A', dropoff_address='B', count=5,
            )
            db.session.add(fa)
            db.session.commit()
        rv = _api(client, 'GET', '/api/v1/favorites', token=token)
        assert rv.status_code == 200
        favs = rv.get_json()['data']['favorites']
        assert len(favs) == 1
        assert favs[0]['name'] == 'Casa'

    def test_excludes_low_count(self, app, client):
        email, token = _register_pax(client)
        from backend.models import db, User, FavoriteAddress
        with app.app_context():
            user = User.query.filter_by(email=email).first()
            fa = FavoriteAddress(
                user_id=user.id, name='Oficina',
                pickup_address='C', dropoff_address='D', count=2,
            )
            db.session.add(fa)
            db.session.commit()
        rv = _api(client, 'GET', '/api/v1/favorites', token=token)
        assert rv.get_json()['data']['favorites'] == []


# ═══════════════════════ GET /users/{id}/reviews ═══════════════════

class TestReviews:

    def test_empty_reviews(self, app, client):
        _, token = _register_pax(client)
        rv = _api(client, 'GET', '/api/v1/users/1/reviews', token=token)
        assert rv.status_code == 200
        assert rv.get_json()['data']['reviews'] == []

    def test_unauthenticated(self, client):
        rv = _api(client, 'GET', '/api/v1/users/1/reviews')
        assert rv.status_code == 401

    def test_reviews_exist_after_rate(self, app, client):
        pax_email, pax_token = _register_pax(client)
        drv_email, drv_token = _register_driver(app, client)
        _fund(app, pax_email, 10000)
        key = str(uuid.uuid4())
        rv = _api(client, 'POST', '/api/v1/trips', token=pax_token,
                  data=BASE_TRIP, headers={'Idempotency-Key': key})
        trip_id = rv.get_json()['data']['trip']['id']
        _api(client, 'POST', f'/api/v1/trips/{trip_id}/accept', token=drv_token)
        _api(client, 'POST', f'/api/v1/trips/{trip_id}/start', token=drv_token)
        _api(client, 'POST', f'/api/v1/trips/{trip_id}/complete', token=drv_token)
        _api(client, 'POST', f'/api/v1/trips/{trip_id}/rate', token=pax_token,
             data={'rating': 5, 'comment': 'Buen viaje'})
        from backend.models import User
        with app.app_context():
            drv_user = User.query.filter_by(email=drv_email).first()
            drv_id = drv_user.id
        rv = _api(client, 'GET', f'/api/v1/users/{drv_id}/reviews?role=passenger',
                  token=pax_token)
        assert rv.status_code == 200
        reviews = rv.get_json()['data']['reviews']
        assert len(reviews) >= 1


# ═══════════════════════ POST /wallet/topups/{id}/voucher ═══════════════════

class TestVoucherUpload:

    def _create_topup(self, client, token):
        rv = _api(client, 'POST', '/api/v1/wallet/topups',
                  token=token, data={'amount': 500, 'method': 'cvu'})
        assert rv.status_code == 201
        return rv.get_json()['data']['topup']['id']

    def test_upload_voucher(self, app, client):
        email, token = _register_pax(client)
        _fund(app, email, 0)
        topup_id = self._create_topup(client, token)
        tiny_png = (
            'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=='
        )
        rv = _api(client, 'POST', f'/api/v1/wallet/topups/{topup_id}/voucher',
                  token=token, data={'image': tiny_png})
        assert rv.status_code == 200
        url = rv.get_json()['data']['voucher_url']
        assert url.startswith('/static/uploads/vouchers/')

    def test_missing_image(self, app, client):
        email, token = _register_pax(client)
        _fund(app, email, 0)
        topup_id = self._create_topup(client, token)
        rv = _api(client, 'POST', f'/api/v1/wallet/topups/{topup_id}/voucher',
                  token=token, data={})
        assert rv.status_code == 400

    def test_wrong_owner(self, app, client):
        email1, token1 = _register_pax(client)
        _fund(app, email1, 0)
        topup_id = self._create_topup(client, token1)
        _, token2 = _register_pax(client)
        tiny_png = (
            'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=='
        )
        rv = _api(client, 'POST', f'/api/v1/wallet/topups/{topup_id}/voucher',
                  token=token2, data={'image': tiny_png})
        assert rv.status_code == 404

    def test_nonexistent_topup(self, app, client):
        _, token = _register_pax(client)
        rv = _api(client, 'POST', '/api/v1/wallet/topups/99999/voucher',
                  token=token, data={'image': 'abc'})
        assert rv.status_code == 404
