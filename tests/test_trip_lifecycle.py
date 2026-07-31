"""
Tests del ciclo de vida completo del viaje en VAN.
Cada test es independiente (pytest crea app fresca por metodo).
Ejecutar: python -m pytest tests/ -v
"""
import json
import re


def _create_passenger(app):
    from backend.models import db, User
    from werkzeug.security import generate_password_hash
    with app.app_context():
        u = User(
            name='Test Pasajero', email='test@pasajero.com',
            password=generate_password_hash('1234'), phone='3001112233',
            email_verified=True
        )
        db.session.add(u)
        db.session.commit()
        return u.id


def _create_driver(app):
    from backend.models import db, Driver
    from werkzeug.security import generate_password_hash
    with app.app_context():
        d = Driver(
            name='Test Conductor', email='test@conductor.com',
            password=generate_password_hash('1234'), phone='3004445566',
            profile_picture='',
            placa='ABC123', moto_marca='Yamaha', moto_modelo='R3',
            moto_color='Azul', moto_cilindrada='300cc',
            tipo_seguro='Todo riesgo', carnet_conducir='A2',
            ultimo_servicio='2024-01-01',
            email_verified=True,
            is_online=True, is_ocupado=False,
            lat=19.43, lng=-99.13,
        )
        db.session.add(d)
        db.session.commit()
        return d.id


def _create_both(app):
    return _create_passenger(app), _create_driver(app)


def _login(client, email, password):
    rv = client.get('/login')
    match = re.search(rb'window\.CSRF_TOKEN\s*=\s*"([^"]+)"', rv.data)
    csrf = match.group(1).decode() if match else ''
    rv = client.post('/login', data={
        'email': email, 'password': password, 'csrf_token': csrf
    }, follow_redirects=True)
    return csrf


def _get_csrf(client):
    rv = client.get('/login')
    match = re.search(rb'window\.CSRF_TOKEN\s*=\s*"([^"]+)"', rv.data)
    return match.group(1).decode() if match else ''


def _request_trip(client, csrf):
    return client.post('/passenger/request', data={
        'pickup_address': 'Calle 123',
        'dropoff_address': 'Av. Central 456',
        'csrf_token': csrf,
        'pickup_lat': 19.43, 'pickup_lng': -99.13,
        'dropoff_lat': 19.44, 'dropoff_lng': -99.14,
        'distance_km': 5.0,
        'payment_method': 'efectivo',
    }, follow_redirects=True)


class TestTripLifecycle:
    def test_01_create_trip(self, app, client):
        _create_both(app)
        _login(client, 'test@pasajero.com', '1234')
        csrf = _get_csrf(client)
        rv = _request_trip(client, csrf)
        assert rv.status_code == 200

        from backend.models import Trip
        with app.app_context():
            trip = Trip.query.first()
            assert trip is not None
            assert trip.status == 'requested'
            assert trip.pickup_address == 'Calle 123'
            assert trip.fare > 0

    def test_02_block_duplicate_trip(self, app, client):
        _create_both(app)
        _login(client, 'test@pasajero.com', '1234')
        csrf = _get_csrf(client)
        _request_trip(client, csrf)
        csrf = _get_csrf(client)
        rv = client.post('/passenger/request', data={
            'pickup_address': 'Otra Calle', 'dropoff_address': 'Otro Destino',
            'csrf_token': csrf,
        }, follow_redirects=True)
        assert rv.status_code == 200
        assert b'Ya tienes un viaje en curso' in rv.data or b'warning' in rv.data

    def test_03_accept_trip(self, app, client):
        _create_both(app)
        _login(client, 'test@pasajero.com', '1234')
        csrf = _get_csrf(client)
        _request_trip(client, csrf)
        from backend.models import Trip
        with app.app_context():
            trip = Trip.query.first()
            trip_id = trip.id

        _login(client, 'test@conductor.com', '1234')
        csrf = _get_csrf(client)
        rv = client.post(f'/driver/accept/{trip_id}', data={
            'csrf_token': csrf,
        }, follow_redirects=True)
        assert rv.status_code == 200
        assert b'Has aceptado el viaje' in rv.data
        with app.app_context():
            t = Trip.query.get(trip_id)
            assert t.status == 'accepted'
            assert t.driver_id is not None

    def test_04_start_trip(self, app, client):
        _create_both(app)
        _login(client, 'test@pasajero.com', '1234')
        csrf = _get_csrf(client)
        _request_trip(client, csrf)
        from backend.models import Trip
        with app.app_context():
            trip_id = Trip.query.first().id

        _login(client, 'test@conductor.com', '1234')
        csrf = _get_csrf(client)
        client.post(f'/driver/accept/{trip_id}', data={'csrf_token': csrf}, follow_redirects=True)
        csrf = _get_csrf(client)
        rv = client.post(f'/driver/start/{trip_id}', data={
            'csrf_token': csrf,
        }, follow_redirects=True)
        assert rv.status_code == 200
        assert b'Viaje iniciado' in rv.data
        with app.app_context():
            t = Trip.query.get(trip_id)
            assert t.status == 'ongoing'
            assert t.started_at is not None

    def test_05_complete_trip(self, app, client):
        _create_both(app)
        _login(client, 'test@pasajero.com', '1234')
        csrf = _get_csrf(client)
        _request_trip(client, csrf)
        from backend.models import Trip
        with app.app_context():
            trip_id = Trip.query.first().id

        _login(client, 'test@conductor.com', '1234')
        csrf = _get_csrf(client)
        client.post(f'/driver/accept/{trip_id}', data={'csrf_token': csrf}, follow_redirects=True)
        csrf = _get_csrf(client)
        client.post(f'/driver/start/{trip_id}', data={'csrf_token': csrf}, follow_redirects=True)
        csrf = _get_csrf(client)
        rv = client.post(f'/driver/complete/{trip_id}', data={
            'csrf_token': csrf,
        }, follow_redirects=True)
        assert rv.status_code == 200
        assert b'completado' in rv.data
        with app.app_context():
            t = Trip.query.get(trip_id)
            assert t.status == 'completed'
            assert t.completed_at is not None

    def test_06_cancel_trip(self, app, client):
        _create_both(app)
        _login(client, 'test@pasajero.com', '1234')
        csrf = _get_csrf(client)
        _request_trip(client, csrf)
        from backend.models import Trip
        with app.app_context():
            trip_id = Trip.query.first().id

        csrf = _get_csrf(client)
        rv = client.post(f'/api/trip/{trip_id}/cancel', data=json.dumps({'csrf_token': csrf}),
            content_type='application/json')
        assert rv.status_code == 200, f'Expected 200, got {rv.status_code}: {rv.data}'
        data = rv.get_json()
        assert data['success']
        with app.app_context():
            t = Trip.query.get(trip_id)
            assert t.status == 'cancelled'

    def test_07_apis_require_auth(self, app, client):
        endpoints = [
            ('/api/drivers/nearby?lat=19.43&lng=-99.13', 'GET'),
            ('/api/trip/1/status', 'GET'),
            ('/api/trip/1/eta', 'GET'),
        ]
        for url, method in endpoints:
            rv = client.open(url, method=method)
            assert rv.status_code in (302, 401), f'{method} {url} should require auth, got {rv.status_code}'

    def test_08_csrf_blocks_unsafe(self, app, client):
        _create_driver(app)
        _login(client, 'test@conductor.com', '1234')
        rv = client.post('/api/driver/toggle_online',
            data=json.dumps({'is_online': True}),
            content_type='application/json')
        assert rv.status_code == 403

    def test_09_location_requires_online(self, app, client):
        _create_driver(app)
        from backend.models import Driver, db
        with app.app_context():
            d = Driver.query.first()
            d.is_online = False
            db.session.commit()

        _login(client, 'test@conductor.com', '1234')
        csrf = _get_csrf(client)
        rv = client.post('/api/location/update', data=json.dumps({
            'lat': 19.43, 'lng': -99.13, 'csrf_token': csrf
        }), content_type='application/json')
        assert rv.status_code == 403
