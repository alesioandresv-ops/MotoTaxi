"""Etapa A1 — Driver & Location API v1 (/api/v1/drivers/*).

Cubre: location update, online/offline toggle, nearby drivers con
filtros de radio y tipo de vehículo.
"""
import json
import uuid


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

REGISTER_PAX = {
    'name': 'Ana Pérez',
    'password': 'Pass1234',
    'phone': '3001112233',
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


def _register_driver(app, client, approve=True, online=True, lat=-34.59, lng=-58.39):
    email = _uniq('carlos')
    rv = _api(client, 'POST', '/api/v1/auth/register/driver',
              data=dict(REGISTER_DRIVER, email=email))
    assert rv.status_code == 201, rv.get_json()
    token = rv.get_json()['data']['tokens']['access_token']
    _setup_profile(app, email, approve=approve, online=online, lat=lat, lng=lng)
    return email, token


def _setup_profile(app, email, approve=True, online=True, lat=-34.59, lng=-58.39):
    from backend.models import db, User
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        profile = user.driver_profile
        if approve:
            profile.status = 'approved'
        profile.is_online = online
        profile.is_busy = False
        profile.lat = lat
        profile.lng = lng
        db.session.commit()


def _register_pax(client):
    email = _uniq('ana')
    rv = _api(client, 'POST', '/api/v1/auth/register',
              data=dict(REGISTER_PAX, email=email))
    assert rv.status_code == 201, rv.get_json()
    return email, rv.get_json()['data']['tokens']['access_token']


# ═══════════════════════ POST /drivers/location ═══════════════════

class TestDriverLocation:

    def test_update_location(self, app, client):
        _, token = _register_driver(app, client, online=True)
        rv = _api(client, 'POST', '/api/v1/drivers/location',
                  token=token, data={'lat': -34.60, 'lng': -58.40})
        assert rv.status_code == 200
        d = rv.get_json()['data']
        assert d['lat'] == -34.60
        assert d['lng'] == -58.40

    def test_not_online_rejected(self, app, client):
        _, token = _register_driver(app, client, online=False)
        rv = _api(client, 'POST', '/api/v1/drivers/location',
                  token=token, data={'lat': -34.60, 'lng': -58.40})
        assert rv.status_code == 409
        assert rv.get_json()['error']['code'] == 'NOT_ONLINE'

    def test_missing_coords(self, app, client):
        _, token = _register_driver(app, client, online=True)
        rv = _api(client, 'POST', '/api/v1/drivers/location',
                  token=token, data={})
        assert rv.status_code == 400

    def test_missing_lat(self, app, client):
        _, token = _register_driver(app, client, online=True)
        rv = _api(client, 'POST', '/api/v1/drivers/location',
                  token=token, data={'lng': -58.40})
        assert rv.status_code == 400

    def test_missing_lng(self, app, client):
        _, token = _register_driver(app, client, online=True)
        rv = _api(client, 'POST', '/api/v1/drivers/location',
                  token=token, data={'lat': -34.60})
        assert rv.status_code == 400

    def test_non_numeric_coords(self, app, client):
        _, token = _register_driver(app, client, online=True)
        rv = _api(client, 'POST', '/api/v1/drivers/location',
                  token=token, data={'lat': 'foo', 'lng': -58.40})
        assert rv.status_code == 400

    def test_nan_coords(self, app, client):
        _, token = _register_driver(app, client, online=True)
        rv = _api(client, 'POST', '/api/v1/drivers/location',
                  token=token, data={'lat': float('nan'), 'lng': -58.40})
        assert rv.status_code == 400

    def test_out_of_range_lat(self, app, client):
        _, token = _register_driver(app, client, online=True)
        rv = _api(client, 'POST', '/api/v1/drivers/location',
                  token=token, data={'lat': 91, 'lng': -58.40})
        assert rv.status_code == 400

    def test_out_of_range_lng(self, app, client):
        _, token = _register_driver(app, client, online=True)
        rv = _api(client, 'POST', '/api/v1/drivers/location',
                  token=token, data={'lat': -34.60, 'lng': 181})
        assert rv.status_code == 400

    def test_boundary_zero(self, app, client):
        _, token = _register_driver(app, client, online=True)
        rv = _api(client, 'POST', '/api/v1/drivers/location',
                  token=token, data={'lat': 0, 'lng': 0})
        assert rv.status_code == 200

    def test_pax_cannot_use(self, app, client):
        _, token = _register_pax(client)
        rv = _api(client, 'POST', '/api/v1/drivers/location',
                  token=token, data={'lat': -34.60, 'lng': -58.40})
        assert rv.status_code == 403

    def test_unauthenticated_rejected(self, client):
        rv = _api(client, 'POST', '/api/v1/drivers/location',
                  data={'lat': -34.60, 'lng': -58.40})
        assert rv.status_code == 401

    def test_persisted_in_db(self, app, client):
        email, token = _register_driver(app, client, online=True)
        _api(client, 'POST', '/api/v1/drivers/location',
             token=token, data={'lat': -33.0, 'lng': -57.0})
        from backend.models import User
        with app.app_context():
            u = User.query.filter_by(email=email).first()
            assert u.driver_profile.lat == -33.0
            assert u.driver_profile.lng == -57.0


# ═══════════════════════ POST /drivers/online ═════════════════════

class TestDriverOnline:

    def test_go_online(self, app, client):
        _, token = _register_driver(app, client, online=False)
        rv = _api(client, 'POST', '/api/v1/drivers/online',
                  token=token, data={'is_online': True})
        assert rv.status_code == 200
        assert rv.get_json()['data']['is_online'] is True

    def test_go_offline(self, app, client):
        _, token = _register_driver(app, client, online=True)
        rv = _api(client, 'POST', '/api/v1/drivers/online',
                  token=token, data={'is_online': False})
        assert rv.status_code == 200
        assert rv.get_json()['data']['is_online'] is False

    def test_offline_clears_busy(self, app, client):
        email, token = _register_driver(app, client, online=True)
        from backend.models import db, User
        with app.app_context():
            u = User.query.filter_by(email=email).first()
            u.driver_profile.is_busy = True
            db.session.commit()

        rv = _api(client, 'POST', '/api/v1/drivers/online',
                  token=token, data={'is_online': False})
        assert rv.status_code == 200

        with app.app_context():
            u = User.query.filter_by(email=email).first()
            assert u.driver_profile.is_busy is False

    def test_pax_cannot_use(self, app, client):
        _, token = _register_pax(client)
        rv = _api(client, 'POST', '/api/v1/drivers/online',
                  token=token, data={'is_online': True})
        assert rv.status_code == 403

    def test_unauthenticated_rejected(self, client):
        rv = _api(client, 'POST', '/api/v1/drivers/online',
                  data={'is_online': True})
        assert rv.status_code == 401

    def test_missing_body(self, app, client):
        _, token = _register_driver(app, client, online=False)
        rv = _api(client, 'POST', '/api/v1/drivers/online', token=token)
        assert rv.status_code == 200
        assert rv.get_json()['data']['is_online'] is False

    def test_persisted_in_db(self, app, client):
        email, token = _register_driver(app, client, online=False)
        _api(client, 'POST', '/api/v1/drivers/online',
             token=token, data={'is_online': True})
        from backend.models import User
        with app.app_context():
            u = User.query.filter_by(email=email).first()
            assert u.driver_profile.is_online is True


# ═══════════════════════ GET /drivers/nearby ══════════════════════

class TestDriversNearby:

    def _setup_drivers(self, app, n=3):
        """Create n online drivers at fixed positions."""
        emails_tokens = []
        for i in range(n):
            lat = -34.59 + i * 0.01
            lng = -58.39 + i * 0.01
            e, t = _register_driver(app, app.test_client(), online=True, lat=lat, lng=lng)
            emails_tokens.append((e, t, lat, lng))
        return emails_tokens

    def test_nearby_returns_drivers(self, app, client):
        emails_tokens = self._setup_drivers(app, 3)
        _, pax_token = _register_pax(client)
        rv = _api(client, 'GET', '/api/v1/drivers/nearby?lat=-34.59&lng=-58.39&radius=50',
                  token=pax_token)
        assert rv.status_code == 200
        data = rv.get_json()['data']
        assert data['count'] >= 1
        assert isinstance(data['drivers'], list)

    def test_nearby_sorted_by_distance(self, app, client):
        emails_tokens = self._setup_drivers(app, 3)
        _, pax_token = _register_pax(client)
        rv = _api(client, 'GET', '/api/v1/drivers/nearby?lat=-34.59&lng=-58.39&radius=50',
                  token=pax_token)
        distances = [d['distance_km'] for d in rv.get_json()['data']['drivers']]
        assert distances == sorted(distances)

    def test_nearby_radius_filter(self, app, client):
        # Driver far away
        _register_driver(app, client, online=True, lat=-40.0, lng=-60.0)
        # Driver nearby
        _register_driver(app, client, online=True, lat=-34.59, lng=-58.39)
        _, pax_token = _register_pax(client)
        rv = _api(client, 'GET', '/api/v1/drivers/nearby?lat=-34.59&lng=-58.39&radius=1',
                  token=pax_token)
        data = rv.get_json()['data']
        for d in data['drivers']:
            assert d['distance_km'] <= 1.0

    def test_nearby_excludes_offline(self, app, client):
        _register_driver(app, client, online=False, lat=-34.59, lng=-58.39)
        _, pax_token = _register_pax(client)
        rv = _api(client, 'GET', '/api/v1/drivers/nearby?lat=-34.59&lng=-58.39&radius=50',
                  token=pax_token)
        assert rv.get_json()['data']['count'] == 0

    def test_nearby_excludes_busy(self, app, client):
        email, _ = _register_driver(app, client, online=True, lat=-34.59, lng=-58.39)
        from backend.models import db, User
        with app.app_context():
            u = User.query.filter_by(email=email).first()
            u.driver_profile.is_busy = True
            db.session.commit()
        _, pax_token = _register_pax(client)
        rv = _api(client, 'GET', '/api/v1/drivers/nearby?lat=-34.59&lng=-58.39&radius=50',
                  token=pax_token)
        assert rv.get_json()['data']['count'] == 0

    def test_nearby_vehicle_type_filter(self, app, client):
        _register_driver(app, client, online=True, lat=-34.59, lng=-58.39)
        _, pax_token = _register_pax(client)
        rv = _api(client, 'GET', '/api/v1/drivers/nearby?lat=-34.59&lng=-58.39&vehicle_type=moto',
                  token=pax_token)
        assert rv.status_code == 200

    def test_nearby_missing_lat(self, app, client):
        _, pax_token = _register_pax(client)
        rv = _api(client, 'GET', '/api/v1/drivers/nearby?lng=-58.39',
                  token=pax_token)
        assert rv.status_code == 400

    def test_nearby_missing_lng(self, app, client):
        _, pax_token = _register_pax(client)
        rv = _api(client, 'GET', '/api/v1/drivers/nearby?lat=-34.59',
                  token=pax_token)
        assert rv.status_code == 400

    def test_nearby_invalid_lat(self, app, client):
        _, pax_token = _register_pax(client)
        rv = _api(client, 'GET', '/api/v1/drivers/nearby?lat=91&lng=-58.39',
                  token=pax_token)
        assert rv.status_code == 400

    def test_nearby_unauthenticated(self, client):
        rv = _api(client, 'GET', '/api/v1/drivers/nearby?lat=-34.59&lng=-58.39')
        assert rv.status_code == 401

    def test_nearby_driver_fields(self, app, client):
        _register_driver(app, client, online=True, lat=-34.59, lng=-58.39)
        _, pax_token = _register_pax(client)
        rv = _api(client, 'GET', '/api/v1/drivers/nearby?lat=-34.59&lng=-58.39&radius=50',
                  token=pax_token)
        d = rv.get_json()['data']['drivers'][0]
        assert 'id' in d
        assert 'name' in d
        assert 'rating_avg' in d
        assert 'vehicle_type' in d
        assert 'vehicle_info' in d
        assert 'lat' in d
        assert 'lng' in d
        assert 'distance_km' in d

    def test_nearby_large_radius(self, app, client):
        _register_driver(app, client, online=True, lat=-34.59, lng=-58.39)
        _, pax_token = _register_pax(client)
        rv = _api(client, 'GET', '/api/v1/drivers/nearby?lat=-34.59&lng=-58.39&radius=10000',
                  token=pax_token)
        assert rv.get_json()['data']['count'] >= 1

    def test_nearby_no_drivers_in_area(self, app, client):
        _register_driver(app, client, online=True, lat=-34.59, lng=-58.39)
        _, pax_token = _register_pax(client)
        rv = _api(client, 'GET', '/api/v1/drivers/nearby?lat=0&lng=0&radius=1',
                  token=pax_token)
        assert rv.get_json()['data']['count'] == 0

    def test_nearby_default_radius(self, app, client):
        _register_driver(app, client, online=True, lat=-34.59, lng=-58.39)
        _, pax_token = _register_pax(client)
        rv = _api(client, 'GET', '/api/v1/drivers/nearby?lat=-34.59&lng=-58.39',
                  token=pax_token)
        assert rv.status_code == 200


# ═══════════════════════ Driver Config ══════════════════════════════

class TestAcceptedPayments:

    def test_get_default(self, app, client):
        _, token = _register_driver(app, client)
        rv = _api(client, 'GET', '/api/v1/driver/accepted-payments', token=token)
        assert rv.status_code == 200
        assert rv.get_json()['data']['accepted_payments'] == ['efectivo']

    def test_update_payments(self, app, client):
        _, token = _register_driver(app, client)
        rv = _api(client, 'PUT', '/api/v1/driver/accepted-payments',
                  token=token, data={'accepted_payments': ['efectivo', 'mercadopago']})
        assert rv.status_code == 200
        assert rv.get_json()['data']['accepted_payments'] == ['efectivo', 'mercadopago']

    def test_invalid_payments_fallback(self, app, client):
        _, token = _register_driver(app, client)
        rv = _api(client, 'PUT', '/api/v1/driver/accepted-payments',
                  token=token, data={'accepted_payments': ['invalido']})
        assert rv.status_code == 200
        assert rv.get_json()['data']['accepted_payments'] == ['efectivo']

    def test_pax_cannot_use(self, app, client):
        _, token = _register_pax(client)
        rv = _api(client, 'GET', '/api/v1/driver/accepted-payments', token=token)
        assert rv.status_code == 403

    def test_persisted(self, app, client):
        email, token = _register_driver(app, client)
        _api(client, 'PUT', '/api/v1/driver/accepted-payments',
             token=token, data={'accepted_payments': ['mercadopago', 'tarjeta']})
        rv = _api(client, 'GET', '/api/v1/driver/accepted-payments', token=token)
        assert sorted(rv.get_json()['data']['accepted_payments']) == ['mercadopago', 'tarjeta']


class TestDriverQR:

    def test_upload_qr(self, app, client):
        _, token = _register_driver(app, client)
        tiny_png = (
            'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=='
        )
        rv = _api(client, 'POST', '/api/v1/driver/qr',
                  token=token, data={'image': tiny_png})
        assert rv.status_code == 200
        url = rv.get_json()['data']['mercadopago_qr']
        assert url.startswith('/static/uploads/')

    def test_missing_image(self, app, client):
        _, token = _register_driver(app, client)
        rv = _api(client, 'POST', '/api/v1/driver/qr',
                  token=token, data={})
        assert rv.status_code == 400

    def test_pax_cannot_use(self, app, client):
        _, token = _register_pax(client)
        rv = _api(client, 'POST', '/api/v1/driver/qr',
                  token=token, data={'image': 'abc'})
        assert rv.status_code == 403


class TestPaymentMethods:

    def test_list_empty(self, app, client):
        _, token = _register_driver(app, client)
        rv = _api(client, 'GET', '/api/v1/driver/payment-methods', token=token)
        assert rv.status_code == 200
        assert rv.get_json()['data']['methods'] == []

    def test_create_method(self, app, client):
        _, token = _register_driver(app, client)
        rv = _api(client, 'POST', '/api/v1/driver/payment-methods',
                  token=token, data={'type': 'mercadopago', 'details': {'cvu': '123'}})
        assert rv.status_code == 201
        assert rv.get_json()['data']['type'] == 'mercadopago'

    def test_create_invalid_type(self, app, client):
        _, token = _register_driver(app, client)
        rv = _api(client, 'POST', '/api/v1/driver/payment-methods',
                  token=token, data={'type': 'bitcoin', 'details': {}})
        assert rv.status_code == 400

    def test_delete_method(self, app, client):
        _, token = _register_driver(app, client)
        rv = _api(client, 'POST', '/api/v1/driver/payment-methods',
                  token=token, data={'type': 'card', 'details': {}})
        method_id = rv.get_json()['data']['id']
        rv = _api(client, 'DELETE', f'/api/v1/driver/payment-methods/{method_id}',
                  token=token)
        assert rv.status_code == 200

    def test_delete_nonexistent(self, app, client):
        _, token = _register_driver(app, client)
        rv = _api(client, 'DELETE', '/api/v1/driver/payment-methods/99999',
                  token=token)
        assert rv.status_code == 404

    def test_pax_cannot_use(self, app, client):
        _, token = _register_pax(client)
        rv = _api(client, 'GET', '/api/v1/driver/payment-methods', token=token)
        assert rv.status_code == 403
