"""
Tests de wallet: balance, transacciones, atomicidad.
"""
import json
import re


def _create_user(app, email='test@user.com', balance=1000.0):
    from backend.models import db, User
    from werkzeug.security import generate_password_hash
    with app.app_context():
        u = User(name='Test User', email=email, password=generate_password_hash('Pass1234'),
                 phone='3001112233', email_verified=True, balance=balance)
        db.session.add(u)
        db.session.commit()
        return u.id


def _create_driver(app, email='test@driver.com', balance=0.0):
    from backend.models import db, Driver
    from werkzeug.security import generate_password_hash
    with app.app_context():
        d = Driver(name='Test Driver', email=email, password=generate_password_hash('Pass1234'),
                   phone='3004445566', profile_picture='', vehicle_type='moto',
                   placa='ABC123', moto_marca='Yamaha', moto_modelo='R3',
                   moto_color='Azul', moto_cilindrada='300cc', tipo_seguro='Todo riesgo',
                   carnet_conducir='A2', ultimo_servicio='2024-01-01', email_verified=True,
                   is_online=True, is_ocupado=False, lat=19.43, lng=-99.13, balance=balance)
        db.session.add(d)
        db.session.commit()
        return d.id


def _login(client, email, password):
    rv = client.get('/login')
    match = re.search(rb'window\.CSRF_TOKEN\s*=\s*"([^"]+)"', rv.data)
    csrf = match.group(1).decode() if match else ''
    client.post('/login', data={'email': email, 'password': password, 'csrf_token': csrf},
                follow_redirects=True)
    return csrf


def _get_csrf(client):
    rv = client.get('/login')
    match = re.search(rb'window\.CSRF_TOKEN\s*=\s*"([^"]+)"', rv.data)
    return match.group(1).decode() if match else ''


class TestWalletBalance:
    def test_passenger_balance_api(self, app, client):
        _create_user(app, balance=500.0)
        _login(client, 'test@user.com', 'Pass1234')
        rv = client.get('/api/wallet/balance')
        assert rv.status_code == 200
        assert rv.get_json()['balance'] == 500.0

    def test_driver_balance_api(self, app, client):
        _create_driver(app, balance=250.0)
        _login(client, 'test@driver.com', 'Pass1234')
        rv = client.get('/api/driver/wallet/balance')
        assert rv.status_code == 200
        assert rv.get_json()['balance'] == 250.0

    def test_wallet_requires_auth(self, app, client):
        rv = client.get('/api/wallet/balance')
        assert rv.status_code in (302, 401)


class TestWalletTransactions:
    def test_empty_transactions(self, app, client):
        _create_user(app)
        _login(client, 'test@user.com', 'Pass1234')
        rv = client.get('/api/wallet/transactions')
        assert rv.status_code == 200
        assert rv.get_json()['transactions'] == []


class TestWalletPayDriver:
    def test_pay_driver_reduces_balance(self, app, client):
        uid = _create_user(app, balance=500.0)
        did = _create_driver(app, balance=0.0)
        _login(client, 'test@user.com', 'Pass1234')
        csrf = _get_csrf(client)
        rv = client.post('/api/wallet/pay-driver', data=json.dumps({
            'driver_id': did, 'amount': 100.0, 'csrf_token': csrf
        }), content_type='application/json')
        assert rv.status_code == 200
        assert rv.get_json()['success']

        from backend.models import User, Driver
        with app.app_context():
            u = User.query.get(uid)
            d = Driver.query.get(did)
            assert float(u.balance) == 400.0
            assert float(d.balance) == 100.0

    def test_pay_driver_insufficient_balance(self, app, client):
        uid = _create_user(app, balance=50.0)
        did = _create_driver(app)
        _login(client, 'test@user.com', 'Pass1234')
        csrf = _get_csrf(client)
        rv = client.post('/api/wallet/pay-driver', data=json.dumps({
            'driver_id': did, 'amount': 100.0, 'csrf_token': csrf
        }), content_type='application/json')
        assert rv.status_code == 400
        assert 'insuficiente' in rv.get_json()['error']

    def test_pay_driver_invalid_amount(self, app, client):
        _create_user(app, balance=500.0)
        did = _create_driver(app)
        _login(client, 'test@user.com', 'Pass1234')
        csrf = _get_csrf(client)
        rv = client.post('/api/wallet/pay-driver', data=json.dumps({
            'driver_id': did, 'amount': -10, 'csrf_token': csrf
        }), content_type='application/json')
        assert rv.status_code == 400


class TestWalletTripPayment:
    def test_wallet_payment_on_trip_complete(self, app, client):
        uid = _create_user(app, balance=1000.0)
        did = _create_driver(app)
        _login(client, 'test@user.com', 'Pass1234')
        csrf = _get_csrf(client)
        client.post('/passenger/request', data={
            'pickup_address': 'A', 'dropoff_address': 'B',
            'csrf_token': csrf, 'pickup_lat': 19.43, 'pickup_lng': -99.13,
            'dropoff_lat': 19.44, 'dropoff_lng': -99.14, 'distance_km': 5.0,
            'payment_method': 'billetera',
        }, follow_redirects=True)

        from backend.models import Trip
        with app.app_context():
            trip_id = Trip.query.first().id

        _login(client, 'test@driver.com', 'Pass1234')
        csrf = _get_csrf(client)
        client.post(f'/driver/accept/{trip_id}', data={'csrf_token': csrf}, follow_redirects=True)
        csrf = _get_csrf(client)
        client.post(f'/driver/start/{trip_id}', data={'csrf_token': csrf}, follow_redirects=True)
        csrf = _get_csrf(client)
        rv = client.post(f'/driver/complete/{trip_id}', data={'csrf_token': csrf}, follow_redirects=True)
        assert rv.status_code == 200

        from backend.models import User, Driver, Trip
        with app.app_context():
            u = User.query.get(uid)
            d = Driver.query.get(did)
            t = Trip.query.get(trip_id)
            assert float(u.balance) < 1000.0
            assert float(d.balance) > 0.0
            assert t.status == 'completed'

    def test_insufficient_wallet_doesnt_deduct(self, app, client):
        uid = _create_user(app, balance=1.0)
        did = _create_driver(app)
        _login(client, 'test@user.com', 'Pass1234')
        csrf = _get_csrf(client)
        client.post('/passenger/request', data={
            'pickup_address': 'A', 'dropoff_address': 'B',
            'csrf_token': csrf, 'pickup_lat': 19.43, 'pickup_lng': -99.13,
            'dropoff_lat': 19.44, 'dropoff_lng': -99.14, 'distance_km': 5.0,
            'payment_method': 'billetera',
        }, follow_redirects=True)

        from backend.models import Trip
        with app.app_context():
            trip_id = Trip.query.first().id

        _login(client, 'test@driver.com', 'Pass1234')
        csrf = _get_csrf(client)
        client.post(f'/driver/accept/{trip_id}', data={'csrf_token': csrf}, follow_redirects=True)
        csrf = _get_csrf(client)
        client.post(f'/driver/start/{trip_id}', data={'csrf_token': csrf}, follow_redirects=True)
        csrf = _get_csrf(client)
        client.post(f'/driver/complete/{trip_id}', data={'csrf_token': csrf}, follow_redirects=True)

        from backend.models import User
        with app.app_context():
            u = User.query.get(uid)
            assert float(u.balance) == 1.0


class TestLatLongValidation:
    def test_negative_91_lat_rejected(self, app, client):
        _create_driver(app)
        _login(client, 'test@driver.com', 'Pass1234')
        csrf = _get_csrf(client)
        rv = client.post('/api/location/update', data=json.dumps({
            'lat': -91, 'lng': 0, 'csrf_token': csrf
        }), content_type='application/json')
        assert rv.status_code == 400

    def test_181_lng_rejected(self, app, client):
        _create_driver(app)
        _login(client, 'test@driver.com', 'Pass1234')
        csrf = _get_csrf(client)
        rv = client.post('/api/location/update', data=json.dumps({
            'lat': 0, 'lng': 181, 'csrf_token': csrf
        }), content_type='application/json')
        assert rv.status_code == 400

    def test_boundary_valid(self, app, client):
        _create_driver(app)
        _login(client, 'test@driver.com', 'Pass1234')
        csrf = _get_csrf(client)
        rv = client.post('/api/location/update', data=json.dumps({
            'lat': 90, 'lng': 180, 'csrf_token': csrf
        }), content_type='application/json')
        assert rv.status_code == 200
