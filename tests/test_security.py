"""
Tests de seguridad: CSRF, auth admin, validación lat/lng, session management.
"""
import json
import re


def _create_user(app, email='test@user.com', name='Test User'):
    from backend.models import db, User
    from werkzeug.security import generate_password_hash
    with app.app_context():
        u = User(name=name, email=email, password=generate_password_hash('Pass1234'),
                 phone='3001112233', email_verified=True)
        db.session.add(u)
        db.session.commit()
        return u.id


def _create_driver(app, email='test@driver.com', name='Test Driver'):
    from backend.models import db, Driver
    from werkzeug.security import generate_password_hash
    with app.app_context():
        d = Driver(name=name, email=email, password=generate_password_hash('Pass1234'),
                   phone='3004445566', profile_picture='', vehicle_type='moto',
                   placa='ABC123', moto_marca='Yamaha', moto_modelo='R3',
                   moto_color='Azul', moto_cilindrada='300cc', tipo_seguro='Todo riesgo',
                   carnet_conducir='A2', ultimo_servicio='2024-01-01', email_verified=True,
                   is_online=True, is_ocupado=False, lat=19.43, lng=-99.13)
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


class TestCSRF:
    def test_json_post_without_csrf_returns_403(self, app, client):
        _create_driver(app)
        _login(client, 'test@driver.com', 'Pass1234')
        rv = client.post('/api/driver/toggle_online',
                         data=json.dumps({'is_online': True}),
                         content_type='application/json')
        assert rv.status_code == 403

    def test_form_post_without_csrf_returns_403(self, app, client):
        _create_user(app)
        _create_driver(app)
        _login(client, 'test@user.com', 'Pass1234')
        rv = client.post('/passenger/request', data={
            'pickup_address': 'A', 'dropoff_address': 'B',
        })
        assert rv.status_code == 403

    def test_valid_csrf_allows_post(self, app, client):
        _create_user(app)
        _login(client, 'test@user.com', 'Pass1234')
        csrf = _get_csrf(client)
        rv = client.post('/passenger/request', data={
            'pickup_address': 'Calle 123', 'dropoff_address': 'Av. Central',
            'csrf_token': csrf, 'pickup_lat': 19.43, 'pickup_lng': -99.13,
            'dropoff_lat': 19.44, 'dropoff_lng': -99.14, 'distance_km': 3.0,
            'payment_method': 'efectivo',
        }, follow_redirects=True)
        assert rv.status_code == 200


class TestAdminAuth:
    def test_admin_topups_requires_session(self, app, client):
        rv = client.get('/admin/topups')
        assert rv.status_code == 302
        assert '/admin/login' in rv.headers.get('Location', '')

    def test_admin_login_with_wrong_key(self, app, client):
        import os
        os.environ['ADMIN_SECRET_KEY'] = 'test-admin-key'
        csrf = _get_csrf(client)
        rv = client.post('/admin/login', data={'key': 'wrong-key', 'csrf_token': csrf},
                         follow_redirects=True)
        assert b'Clave incorrecta' in rv.data

    def test_admin_login_with_correct_key(self, app, client):
        import os
        os.environ['ADMIN_SECRET_KEY'] = 'test-admin-key'
        csrf = _get_csrf(client)
        rv = client.post('/admin/login', data={'key': 'test-admin-key', 'csrf_token': csrf},
                         follow_redirects=True)
        assert rv.status_code == 200
        assert b'Panel de comprobantes' in rv.data

    def test_admin_logout(self, app, client):
        import os
        os.environ['ADMIN_SECRET_KEY'] = 'test-admin-key'
        csrf = _get_csrf(client)
        client.post('/admin/login', data={'key': 'test-admin-key', 'csrf_token': csrf},
                     follow_redirects=True)
        csrf2 = _get_csrf(client)
        rv = client.post('/admin/logout', data={'csrf_token': csrf2}, follow_redirects=True)
        assert rv.status_code == 200

    def test_admin_confirm_requires_csrf(self, app, client):
        import os
        os.environ['ADMIN_SECRET_KEY'] = 'test-admin-key'
        _create_user(app)
        csrf = _get_csrf(client)
        client.post('/admin/login', data={'key': 'test-admin-key', 'csrf_token': csrf},
                     follow_redirects=True)
        rv = client.post('/admin/topups/1/confirm', data={})
        assert rv.status_code == 403


class TestLocationValidation:
    def test_invalid_lat_rejected(self, app, client):
        _create_driver(app)
        _login(client, 'test@driver.com', 'Pass1234')
        csrf = _get_csrf(client)
        rv = client.post('/api/location/update', data=json.dumps({
            'lat': 999, 'lng': -99.13, 'csrf_token': csrf
        }), content_type='application/json')
        assert rv.status_code == 400
        assert 'rango' in rv.get_json()['error']

    def test_nan_lat_rejected(self, app, client):
        _create_driver(app)
        _login(client, 'test@driver.com', 'Pass1234')
        csrf = _get_csrf(client)
        rv = client.post('/api/location/update', data=json.dumps({
            'lat': 'abc', 'lng': -99.13, 'csrf_token': csrf
        }), content_type='application/json')
        assert rv.status_code == 400

    def test_valid_coordinates_accepted(self, app, client):
        _create_driver(app)
        _login(client, 'test@driver.com', 'Pass1234')
        csrf = _get_csrf(client)
        rv = client.post('/api/location/update', data=json.dumps({
            'lat': 19.43, 'lng': -99.13, 'csrf_token': csrf
        }), content_type='application/json')
        assert rv.status_code == 200
        assert rv.get_json()['success']

    def test_missing_coords_rejected(self, app, client):
        _create_driver(app)
        _login(client, 'test@driver.com', 'Pass1234')
        csrf = _get_csrf(client)
        rv = client.post('/api/location/update', data=json.dumps({
            'csrf_token': csrf
        }), content_type='application/json')
        assert rv.status_code == 400


class TestSecurityHeaders:
    def test_x_content_type_options(self, app, client):
        rv = client.get('/')
        assert rv.headers.get('X-Content-Type-Options') == 'nosniff'

    def test_x_frame_options(self, app, client):
        rv = client.get('/')
        assert rv.headers.get('X-Frame-Options') == 'DENY'

    def test_x_xss_protection(self, app, client):
        rv = client.get('/')
        assert '1; mode=block' in rv.headers.get('X-XSS-Protection', '')

    def test_csp_header(self, app, client):
        rv = client.get('/')
        assert 'Content-Security-Policy' in rv.headers
        assert "default-src 'self'" in rv.headers['Content-Security-Policy']
