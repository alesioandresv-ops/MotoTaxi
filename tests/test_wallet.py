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
    from backend.models import db, User, DriverProfile, Vehicle, ROLE_DRIVER
    from werkzeug.security import generate_password_hash
    with app.app_context():
        d = User(name='Test Driver', email=email, password=generate_password_hash('Pass1234'),
                 phone='3004445566', profile_picture='', role=ROLE_DRIVER, email_verified=True,
                 balance=balance,
                 driver_profile=DriverProfile(
                     is_online=True, is_busy=False, lat=19.43, lng=-99.13,
                     vehicles=[Vehicle(
                         type='moto', placa='ABC123', marca='Yamaha', modelo='R3',
                         color='Azul', cilindrada='300cc', tipo_seguro='Todo riesgo',
                         carnet_conducir='A2', ultimo_servicio='2024-01-01', is_active=True,
                     )],
                 ))
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

        from backend.models import User
        with app.app_context():
            u = User.query.get(uid)
            d = User.query.get(did)
            assert float(u.balance) == 400.0
            assert float(d.balance) == 100.0

    def test_pay_driver_requires_own_trip(self, app, client):
        """Seguridad: un pasajero no puede pagar un viaje ajeno por su id."""
        _create_user(app, balance=500.0)
        _create_driver(app)
        other = _create_user(app, email='other@test.com', balance=0.0)
        from backend.models import Trip
        with app.app_context():
            trip = Trip(
                passenger_id=other, pickup_address='A', dropoff_address='B',
                total_fare=50, platform_fee=0, driver_earnings=50,
                vehicle_type='moto', status='requested',
            )
            db = Trip.query.session
            db.add(trip)
            db.commit()
            trip_id = trip.id

        _login(client, 'test@user.com', 'Pass1234')
        csrf = _get_csrf(client)
        rv = client.post('/api/wallet/pay-driver', data=json.dumps({
            'driver_id': 2, 'amount': 50.0, 'trip_id': trip_id, 'csrf_token': csrf
        }), content_type='application/json')
        assert rv.status_code == 404

    def test_pay_driver_amount_capped_by_fare(self, app, client):
        """Seguridad: el importe no puede exceder la tarifa del viaje."""
        uid = _create_user(app, balance=500.0)
        did = _create_driver(app)
        from backend.models import Trip
        with app.app_context():
            trip = Trip(
                passenger_id=uid, pickup_address='A', dropoff_address='B',
                total_fare=50, platform_fee=0, driver_earnings=50,
                vehicle_type='moto', status='requested',
            )
            db = Trip.query.session
            db.add(trip)
            db.commit()
            trip_id = trip.id

        _login(client, 'test@user.com', 'Pass1234')
        csrf = _get_csrf(client)
        rv = client.post('/api/wallet/pay-driver', data=json.dumps({
            'driver_id': did, 'amount': 200.0, 'trip_id': trip_id, 'csrf_token': csrf
        }), content_type='application/json')
        assert rv.status_code == 400
        assert 'exceder' in rv.get_json()['error']

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
    def _flow_to_ongoing(self, app, client, passenger_balance):
        """Pasajero pide viaje en billetera; conductor acepta e inicia.
        Devuelve (uid, did, trip_id) con el viaje en estado ongoing."""
        uid = _create_user(app, balance=passenger_balance)
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
        return uid, did, trip_id

    def _collect(self, client, trip_id, method='billetera'):
        csrf = _get_csrf(client)
        return client.post(f'/api/trip/{trip_id}/collect-payment', data=json.dumps({
            'method': method, 'csrf_token': csrf,
        }), content_type='application/json')

    def test_wallet_payment_on_trip_collect(self, app, client):
        uid, did, trip_id = self._flow_to_ongoing(app, client, passenger_balance=1000.0)
        rv = self._collect(client, trip_id, method='billetera')
        assert rv.status_code == 200, f'Expected 200, got {rv.status_code}: {rv.data}'
        body = rv.get_json()
        assert body['success'] is True
        assert body['status'] == 'completed'
        assert body['payment_method_collected'] == 'billetera'

        from backend.models import User, Trip
        with app.app_context():
            u = User.query.get(uid)
            d = User.query.get(did)
            t = Trip.query.get(trip_id)
            assert t.status == 'completed'
            assert t.payment_status == 'paid'
            assert t.payment_method_collected == 'billetera'
            # Pasajero debita el total; conductor acredita earnings (comisión aparte)
            assert float(u.balance) == round(1000.0 - float(t.fare), 2)
            assert float(d.balance) == round(float(t.fare) - float(t.platform_fee), 2)

    def test_insufficient_wallet_blocks_completion(self, app, client):
        """Saldo insuficiente: el cobro se bloquea (409), no hay deuda
        fantasma y el conductor puede cobrar por otro método."""
        uid, did, trip_id = self._flow_to_ongoing(app, client, passenger_balance=1.0)
        rv = self._collect(client, trip_id, method='billetera')
        assert rv.status_code == 409
        assert rv.get_json()['code'] == 'PAYMENT_INSUFFICIENT_BALANCE'

        from backend.models import User, Trip, WalletTransaction
        with app.app_context():
            u = User.query.get(uid)
            d = User.query.get(did)
            t = Trip.query.get(trip_id)
            # Nada cambió: viaje ongoing, saldos intactos, cero transacciones fantasma
            assert t.status == 'ongoing'
            assert t.payment_status == 'pending'
            assert float(u.balance) == 1.0
            assert float(d.balance) == 0.0
            assert WalletTransaction.query.count() == 0

        # El conductor cambia de método y completa
        rv = self._collect(client, trip_id, method='efectivo')
        assert rv.status_code == 200
        with app.app_context():
            u = User.query.get(uid)
            d = User.query.get(did)
            t = Trip.query.get(trip_id)
            assert t.status == 'completed'
            assert t.payment_status == 'paid'
            assert t.payment_method_collected == 'efectivo'
            # Efectivo no toca billeteras
            assert float(u.balance) == 1.0
            assert float(d.balance) == 0.0

    def test_collect_requires_ongoing_status(self, app, client):
        """No se puede cobrar un viaje que no está en curso (p.ej. cancelled)."""
        uid, did, trip_id = self._flow_to_ongoing(app, client, passenger_balance=1000.0)
        with app.app_context():
            from backend.models import db, Trip
            t = Trip.query.get(trip_id)
            t.status = 'cancelled'
            db.session.commit()

        rv = self._collect(client, trip_id, method='efectivo')
        assert rv.status_code == 409
        assert rv.get_json()['code'] == 'INVALID_STATUS'

    def test_collect_rejects_invalid_method(self, app, client):
        uid, did, trip_id = self._flow_to_ongoing(app, client, passenger_balance=1000.0)
        rv = self._collect(client, trip_id, method='cripto')
        assert rv.status_code in (400, 409)

    def test_collect_is_for_driver_of_trip(self, app, client):
        """Otro conductor no puede cobrar el viaje ajeno."""
        uid, did, trip_id = self._flow_to_ongoing(app, client, passenger_balance=1000.0)
        _create_driver(app, email='otro@driver.com')
        _login(client, 'otro@driver.com', 'Pass1234')
        rv = self._collect(client, trip_id, method='efectivo')
        assert rv.status_code in (302, 403)


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
