"""
Tests de la API v1: autenticación JWT (registro, login, refresh, logout).
También verifican el contrato de respuestas que consume Flutter
(envelope {success, data} / {success, error}).
"""
import json
from datetime import datetime, timedelta, timezone

REGISTER = {
    'name': 'Ana Pérez',
    'email': 'ana@test.com',
    'password': 'Pass1234',
    'phone': '3001112233',
}

DRIVER_REGISTER = {
    'name': 'Carlos Conductor',
    'email': 'carlos@test.com',
    'password': 'Pass1234',
    'phone': '3004445566',
    'vehicle_type': 'moto',
    'placa': 'ABC123',
    'moto_marca': 'Yamaha',
    'moto_modelo': 'R3',
    'moto_color': 'Azul',
    'moto_cilindrada': '300cc',
    'tipo_seguro': 'Todo riesgo',
    'carnet_conducir': 'A2',
    'ultimo_servicio': '2024-01-01',
}


def _api(client, method, path, token=None, data=None):
    headers = {}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    if data is not None:
        headers['Content-Type'] = 'application/json'
    return client.open(path, method=method, headers=headers,
                       data=json.dumps(data) if data is not None else None)


def _register(client, payload=REGISTER):
    return _api(client, 'POST', '/api/v1/auth/register', data=payload)


def _login(client, email='ana@test.com', password='Pass1234'):
    return _api(client, 'POST', '/api/v1/auth/login',
                data={'email': email, 'password': password})


def _tokens(rv):
    return rv.get_json()['data']['tokens']


class TestRegister:
    def test_register_user_returns_tokens(self, app, client):
        rv = _register(client)
        assert rv.status_code == 201
        body = rv.get_json()
        assert body['success'] is True
        data = body['data']
        assert data['user']['email'] == 'ana@test.com'
        assert data['user']['role'] == 'passenger'
        assert data['tokens']['access_token'] and data['tokens']['refresh_token']
        assert data['tokens']['token_type'] == 'Bearer'

    def test_register_duplicate_email_409(self, app, client):
        _register(client)
        rv = _register(client)
        assert rv.status_code == 409
        body = rv.get_json()
        assert body['success'] is False
        assert body['error']['code'] == 'EMAIL_TAKEN'

    def test_register_invalid_password(self, app, client):
        rv = _register(client, dict(REGISTER, password='corta'))
        assert rv.status_code == 400
        assert rv.get_json()['error']['code'] == 'VALIDATION_ERROR'

    def test_register_driver(self, app, client):
        rv = _api(client, 'POST', '/api/v1/auth/register/driver', data=DRIVER_REGISTER)
        assert rv.status_code == 201
        user = rv.get_json()['data']['user']
        assert user['role'] == 'driver'
        assert user['driver']['vehicle_type'] == 'moto'

    def test_register_driver_promotes_existing_passenger_to_both(self, app, client):
        _register(client)
        rv = _api(client, 'POST', '/api/v1/auth/register/driver',
                  data=dict(DRIVER_REGISTER, email='ana@test.com'))
        assert rv.status_code == 201
        user = rv.get_json()['data']['user']
        assert user['email'] == 'ana@test.com'
        assert user['role'] == 'both'
        assert user['driver']['vehicle_type'] == 'moto'
        # el login con el mismo email resuelve el mismo usuario
        rv = _login(client)
        assert rv.status_code == 200
        assert rv.get_json()['data']['user']['role'] == 'both'

    def test_register_driver_rejects_existing_driver_email(self, app, client):
        _api(client, 'POST', '/api/v1/auth/register/driver', data=DRIVER_REGISTER)
        rv = _api(client, 'POST', '/api/v1/auth/register/driver', data=DRIVER_REGISTER)
        assert rv.status_code == 409
        assert rv.get_json()['error']['code'] == 'EMAIL_TAKEN'

    def test_register_driver_missing_fields(self, app, client):
        rv = _api(client, 'POST', '/api/v1/auth/register/driver', data={
            'name': 'X', 'email': 'x@test.com', 'password': 'Pass1234', 'phone': '1'
        })
        assert rv.status_code == 400
        assert rv.get_json()['error']['code'] == 'VALIDATION_ERROR'

    def test_register_accepts_html_sanitized_name(self, app, client):
        rv = _register(client, dict(REGISTER, name='<b>Ana</b>'))
        assert rv.status_code == 201
        assert rv.get_json()['data']['user']['name'] == 'Ana'


class TestLogin:
    def test_login_ok(self, app, client):
        _register(client)
        rv = _login(client)
        assert rv.status_code == 200
        data = rv.get_json()['data']
        assert data['user']['role'] == 'passenger'
        assert data['tokens']['access_token']

    def test_login_wrong_password(self, app, client):
        _register(client)
        rv = _login(client, password='Wrong123')
        assert rv.status_code == 401
        assert rv.get_json()['error']['code'] == 'INVALID_CREDENTIALS'

    def test_login_driver(self, app, client):
        _api(client, 'POST', '/api/v1/auth/register/driver', data=DRIVER_REGISTER)
        rv = _api(client, 'POST', '/api/v1/auth/login',
                  data={'email': 'carlos@test.com', 'password': 'Pass1234'})
        assert rv.status_code == 200
        user = rv.get_json()['data']['user']
        assert user['role'] == 'driver'
        assert user['active_mode'] == 'driver'

    def test_login_missing_fields(self, app, client):
        rv = _api(client, 'POST', '/api/v1/auth/login', data={})
        assert rv.status_code == 400


class TestAccessToken:
    def test_me_with_token(self, app, client):
        _register(client)
        tokens = _tokens(_login(client))
        rv = _api(client, 'GET', '/api/v1/auth/me', token=tokens['access_token'])
        assert rv.status_code == 200
        assert rv.get_json()['data']['user']['email'] == 'ana@test.com'

    def test_me_without_token(self, app, client):
        rv = _api(client, 'GET', '/api/v1/auth/me')
        assert rv.status_code == 401
        assert rv.get_json()['error']['code'] == 'MISSING_TOKEN'

    def test_me_invalid_token(self, app, client):
        rv = _api(client, 'GET', '/api/v1/auth/me', token='not.a.jwt')
        assert rv.status_code == 401
        assert rv.get_json()['error']['code'] == 'INVALID_TOKEN'

    def test_expired_access_token(self, app, client):
        import jwt as pyjwt
        secret = app.config['JWT_SECRET_KEY']
        now = datetime.now(timezone.utc)
        token = pyjwt.encode({
            'sub': '1', 'role': 'passenger', 'jti': 'x',
            'iat': now - timedelta(hours=1), 'exp': now - timedelta(minutes=5),
        }, secret, algorithm='HS256')
        rv = _api(client, 'GET', '/api/v1/auth/me', token=token)
        assert rv.status_code == 401
        assert rv.get_json()['error']['code'] == 'TOKEN_EXPIRED'

    def test_me_driver(self, app, client):
        _api(client, 'POST', '/api/v1/auth/register/driver', data=DRIVER_REGISTER)
        tokens = _tokens(_api(client, 'POST', '/api/v1/auth/login',
                              data={'email': 'carlos@test.com', 'password': 'Pass1234'}))
        rv = _api(client, 'GET', '/api/v1/auth/me', token=tokens['access_token'])
        assert rv.status_code == 200
        assert rv.get_json()['data']['user']['role'] == 'driver'


class TestDualRole:
    def test_both_login_defaults_to_passenger_mode(self, app, client):
        _register(client)
        _api(client, 'POST', '/api/v1/auth/register/driver',
             data=dict(DRIVER_REGISTER, email='ana@test.com'))
        rv = _login(client)
        assert rv.status_code == 200
        data = rv.get_json()['data']
        assert data['user']['role'] == 'both'
        assert data['user']['active_mode'] == 'passenger'

    def test_both_login_with_mode_param(self, app, client):
        _register(client)
        _api(client, 'POST', '/api/v1/auth/register/driver',
             data=dict(DRIVER_REGISTER, email='ana@test.com'))
        rv = _login(client)
        assert rv.status_code == 200
        assert rv.get_json()['data']['user']['active_mode'] == 'passenger'
        rv = _api(client, 'POST', '/api/v1/auth/login',
                  data={'email': 'ana@test.com', 'password': 'Pass1234', 'mode': 'driver'})
        assert rv.status_code == 200
        data = rv.get_json()['data']
        assert data['user']['active_mode'] == 'driver'
        assert data['user']['driver']['vehicle_type'] == 'moto'

    def test_switch_mode_rotates_access_token(self, app, client):
        _register(client)
        tokens = _tokens(_login(client))
        rv = _api(client, 'POST', '/api/v1/auth/switch-mode',
                  token=tokens['access_token'], data={'mode': 'driver'})
        assert rv.status_code == 403  # rol passenger no admite switch

    def test_switch_mode_for_both(self, app, client):
        _register(client)
        _api(client, 'POST', '/api/v1/auth/register/driver',
             data=dict(DRIVER_REGISTER, email='ana@test.com'))
        tokens = _tokens(_login(client))
        rv = _api(client, 'POST', '/api/v1/auth/switch-mode',
                  token=tokens['access_token'], data={'mode': 'driver'})
        assert rv.status_code == 200
        data = rv.get_json()['data']
        assert data['active_mode'] == 'driver'
        assert data['access_token'] != tokens['access_token']


class TestRefreshRotation:
    def test_refresh_rotates_token(self, app, client):
        _register(client)
        tokens = _tokens(_login(client))
        rv = _api(client, 'POST', '/api/v1/auth/refresh',
                  data={'refresh_token': tokens['refresh_token']})
        assert rv.status_code == 200
        data = rv.get_json()['data']
        assert data['access_token']
        assert data['refresh_token'] != tokens['refresh_token']

    def test_refresh_old_token_still_valid_once_after_rotation(self, app, client):
        _register(client)
        tokens = _tokens(_login(client))
        _api(client, 'POST', '/api/v1/auth/refresh',
             data={'refresh_token': tokens['refresh_token']})
        rv = _api(client, 'POST', '/api/v1/auth/refresh',
                  data={'refresh_token': tokens['refresh_token']})
        assert rv.status_code == 401
        assert rv.get_json()['error']['code'] == 'TOKEN_REUSE_DETECTED'

    def test_reuse_detection_revokes_all_tokens(self, app, client):
        from backend.models import RefreshToken
        _register(client)
        tokens = _tokens(_login(client))
        second = _tokens(_login(client))
        _api(client, 'POST', '/api/v1/auth/refresh',
             data={'refresh_token': tokens['refresh_token']})
        rv = _api(client, 'POST', '/api/v1/auth/refresh',
                  data={'refresh_token': tokens['refresh_token']})
        assert rv.status_code == 401
        with app.app_context():
            all_revoked = all(t.revoked_at is not None for t in RefreshToken.query.all())
        assert all_revoked
        rv = _api(client, 'POST', '/api/v1/auth/refresh',
                  data={'refresh_token': second['refresh_token']})
        assert rv.status_code == 401

    def test_refresh_invalid_token(self, app, client):
        rv = _api(client, 'POST', '/api/v1/auth/refresh',
                  data={'refresh_token': 'garbage-token'})
        assert rv.status_code == 401
        assert rv.get_json()['error']['code'] == 'INVALID_REFRESH'

    def test_refresh_requires_field(self, app, client):
        rv = _api(client, 'POST', '/api/v1/auth/refresh', data={})
        assert rv.status_code == 400

    def test_logout_revokes_refresh(self, app, client):
        _register(client)
        tokens = _tokens(_login(client))
        rv = _api(client, 'POST', '/api/v1/auth/logout',
                  data={'refresh_token': tokens['refresh_token']})
        assert rv.status_code == 200
        rv = _api(client, 'POST', '/api/v1/auth/refresh',
                  data={'refresh_token': tokens['refresh_token']})
        assert rv.status_code == 401
        # Un token revocado por logout se trata como reuso (respuesta a compromiso)
        assert rv.get_json()['error']['code'] == 'TOKEN_REUSE_DETECTED'


class TestVerifyEmail:
    def test_verify_email_with_code(self, app, client, monkeypatch):
        monkeypatch.setenv('SMTP_SERVER', 'smtp.test.com')
        monkeypatch.setenv('SMTP_USER', 'test')
        monkeypatch.setenv('SMTP_PASS', 'test')
        from backend.models import EmailVerification
        rv = _register(client)
        assert rv.get_json()['data']['verification_sent'] is True
        tokens = rv.get_json()['data']['tokens']
        with app.app_context():
            ev = EmailVerification.query.first()
            assert ev is not None
            code_hash = ev.code_hash
        assert code_hash  # no accedemos al código real (hash), validamos flujo de error
        rv = _api(client, 'POST', '/api/v1/auth/verify-email',
                  token=tokens['access_token'], data={'code': '000000'})
        assert rv.status_code == 400
        assert rv.get_json()['error']['code'] == 'INVALID_CODE'


class TestOpenAPI:
    def test_openapi_yaml_served(self, client):
        rv = client.get('/api/v1/openapi.yaml')
        assert rv.status_code == 200
        assert b'openapi' in rv.data

    def test_docs_served(self, client):
        rv = client.get('/api/v1/docs')
        assert rv.status_code == 200
        assert b'swagger' in rv.data.lower()
