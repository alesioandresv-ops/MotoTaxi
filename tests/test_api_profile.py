"""Etapa A3 — Profile, photo, password, guidelines API v1.

Cubre: PUT /auth/profile, POST /auth/profile/photo, POST /auth/password,
GET/POST /auth/guidelines.
"""
import json
import uuid


REGISTER_PAX = {
    'name': 'Ana Pérez',
    'email': None,
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


def _register_pax(client):
    email = _uniq('ana')
    rv = _api(client, 'POST', '/api/v1/auth/register',
              data=dict(REGISTER_PAX, email=email))
    assert rv.status_code == 201, rv.get_json()
    return email, rv.get_json()['data']['tokens']['access_token']


# ═══════════════════════ PUT /auth/profile ═══════════════════

class TestUpdateProfile:

    def test_update_name(self, app, client):
        email, token = _register_pax(client)
        rv = _api(client, 'PUT', '/api/v1/auth/profile',
                  token=token, data={'name': 'Nuevo Nombre'})
        assert rv.status_code == 200
        assert rv.get_json()['data']['user']['name'] == 'Nuevo Nombre'

    def test_update_phone(self, app, client):
        email, token = _register_pax(client)
        rv = _api(client, 'PUT', '/api/v1/auth/profile',
                  token=token, data={'phone': '3009998877'})
        assert rv.status_code == 200
        assert rv.get_json()['data']['user']['phone'] == '3009998877'

    def test_update_both(self, app, client):
        email, token = _register_pax(client)
        rv = _api(client, 'PUT', '/api/v1/auth/profile',
                  token=token, data={'name': 'Xavier', 'phone': '111'})
        assert rv.status_code == 200

    def test_name_too_short(self, app, client):
        _, token = _register_pax(client)
        rv = _api(client, 'PUT', '/api/v1/auth/profile',
                  token=token, data={'name': 'A'})
        assert rv.status_code == 400

    def test_unauthenticated(self, client):
        rv = _api(client, 'PUT', '/api/v1/auth/profile',
                  data={'name': 'X'})
        assert rv.status_code == 401

    def test_empty_body_ok(self, app, client):
        _, token = _register_pax(client)
        rv = _api(client, 'PUT', '/api/v1/auth/profile',
                  token=token, data={})
        assert rv.status_code == 200

    def test_name_sanitized(self, app, client):
        _, token = _register_pax(client)
        rv = _api(client, 'PUT', '/api/v1/auth/profile',
                  token=token, data={'name': '<b>Test</b>'})
        assert rv.status_code == 200
        name = rv.get_json()['data']['user']['name']
        assert '<b>' not in name


# ═══════════════════════ POST /auth/password ═══════════════════

class TestChangePassword:

    def test_change_password_success(self, app, client):
        email, token = _register_pax(client)
        rv = _api(client, 'POST', '/api/v1/auth/password',
                  token=token, data={
                      'current_password': 'Pass1234',
                      'new_password': 'NewPass5678',
                  })
        assert rv.status_code == 200
        assert rv.get_json()['data']['success'] is True

    def test_wrong_current_password(self, app, client):
        _, token = _register_pax(client)
        rv = _api(client, 'POST', '/api/v1/auth/password',
                  token=token, data={
                      'current_password': 'WrongPass123',
                      'new_password': 'NewPass5678',
                  })
        assert rv.status_code == 401

    def test_missing_current_password(self, app, client):
        _, token = _register_pax(client)
        rv = _api(client, 'POST', '/api/v1/auth/password',
                  token=token, data={'new_password': 'NewPass5678'})
        assert rv.status_code == 400

    def test_missing_new_password(self, app, client):
        _, token = _register_pax(client)
        rv = _api(client, 'POST', '/api/v1/auth/password',
                  token=token, data={'current_password': 'Pass1234'})
        assert rv.status_code == 400

    def test_new_password_too_short(self, app, client):
        _, token = _register_pax(client)
        rv = _api(client, 'POST', '/api/v1/auth/password',
                  token=token, data={
                      'current_password': 'Pass1234',
                      'new_password': 'Short1',
                  })
        assert rv.status_code == 400

    def test_unauthenticated(self, client):
        rv = _api(client, 'POST', '/api/v1/auth/password',
                  data={'current_password': 'Pass1234', 'new_password': 'NewPass5678'})
        assert rv.status_code == 401

    def test_login_with_new_password(self, app, client):
        email, token = _register_pax(client)
        _api(client, 'POST', '/api/v1/auth/password',
             token=token, data={
                 'current_password': 'Pass1234',
                 'new_password': 'NewPass5678',
             })
        rv = _api(client, 'POST', '/api/v1/auth/login',
                  data={'email': email, 'password': 'NewPass5678'})
        assert rv.status_code == 200


# ═══════════════════════ POST /auth/profile/photo ═══════════════════

class TestProfilePhoto:

    def test_upload_photo(self, app, client):
        _, token = _register_pax(client)
        tiny_png = (
            'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=='
        )
        rv = _api(client, 'POST', '/api/v1/auth/profile/photo',
                  token=token, data={'image': tiny_png})
        assert rv.status_code == 200
        url = rv.get_json()['data']['profile_picture']
        assert url and url.startswith('/static/uploads/')

    def test_upload_photo_with_prefix(self, app, client):
        _, token = _register_pax(client)
        tiny_png = (
            'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=='
        )
        rv = _api(client, 'POST', '/api/v1/auth/profile/photo',
                  token=token, data={'image': tiny_png})
        assert rv.status_code == 200

    def test_missing_image(self, app, client):
        _, token = _register_pax(client)
        rv = _api(client, 'POST', '/api/v1/auth/profile/photo',
                  token=token, data={})
        assert rv.status_code == 400

    def test_invalid_image(self, app, client):
        _, token = _register_pax(client)
        rv = _api(client, 'POST', '/api/v1/auth/profile/photo',
                  token=token, data={'image': 'notbase64!!!'})
        assert rv.status_code == 400

    def test_unauthenticated(self, client):
        rv = _api(client, 'POST', '/api/v1/auth/profile/photo',
                  data={'image': 'abc'})
        assert rv.status_code == 401

    def test_photo_persisted(self, app, client):
        email, token = _register_pax(client)
        tiny_png = (
            'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=='
        )
        _api(client, 'POST', '/api/v1/auth/profile/photo',
             token=token, data={'image': tiny_png})
        from backend.models import User
        with app.app_context():
            u = User.query.filter_by(email=email).first()
            assert u.profile_picture is not None
            assert '/static/uploads/' in u.profile_picture


# ═══════════════════════ GET/POST /auth/guidelines ═══════════════════

class TestGuidelines:

    def test_not_accepted_initially(self, app, client):
        _, token = _register_pax(client)
        rv = _api(client, 'GET', '/api/v1/auth/guidelines', token=token)
        assert rv.status_code == 200
        assert rv.get_json()['data']['accepted'] is False

    def test_accept_guidelines(self, app, client):
        _, token = _register_pax(client)
        rv = _api(client, 'POST', '/api/v1/auth/guidelines', token=token)
        assert rv.status_code == 200
        assert rv.get_json()['data']['accepted'] is True

    def test_persisted_after_accept(self, app, client):
        email, token = _register_pax(client)
        _api(client, 'POST', '/api/v1/auth/guidelines', token=token)
        rv = _api(client, 'GET', '/api/v1/auth/guidelines', token=token)
        assert rv.get_json()['data']['accepted'] is True

    def test_unauthenticated(self, client):
        rv = _api(client, 'GET', '/api/v1/auth/guidelines')
        assert rv.status_code == 401
        rv = _api(client, 'POST', '/api/v1/auth/guidelines')
        assert rv.status_code == 401
