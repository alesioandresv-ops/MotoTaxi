"""Etapa 0 — decorators de autorización (require_mode) + validación contra DB.

Cubre: 401 sin token / token inválido / token expirado; 403 FORBIDDEN;
MODE_NOT_ALLOWED; role='both'; modo passenger/driver; driver sin
driver_profile; status pending/rejected/approved; role validado en DB
(el claim del JWT no se confía).
"""
import uuid

import pytest

from backend.api.jwt import create_access_token
from backend.models import (
    MODE_DRIVER,
    MODE_PASSENGER,
    ROLE_BOTH,
    ROLE_DRIVER,
    ROLE_PASSENGER,
    DRIVER_STATUS_APPROVED,
    DRIVER_STATUS_PENDING,
    DRIVER_STATUS_REJECTED,
    DriverProfile,
    User,
    db,
)


def _user(app, role=ROLE_PASSENGER, profile=None):
    """Crea un user (con driver_profile opcional). Devuelve (user_id, email)."""
    email = f'test-{uuid.uuid4().hex[:10]}@van.test'
    with app.app_context():
        user = User(name='Test User', email=email, password='x', role=role)
        if profile is not None:
            user.driver_profile = DriverProfile(user_id=user.id, status=profile)
        db.session.add(user)
        db.session.commit()
        return user.id, email


def _token(app, user_id, role, mode=None):
    with app.app_context():
        return create_access_token(user_id, role, mode)


@pytest.fixture
def guarded(app):
    """Registra rutas de prueba protegidas con jwt_required + require_mode.

    Se registran en la app (no en el blueprint, que ya está registrado) y se
    replica el envelope: cualquier ApiError → fail(code, message, status).
    En producción las rutas van en api_bp y su errorhandler hace esto mismo.
    """
    from backend.api import fail, ok
    from backend.api.decorators import require_mode
    from backend.api.errors import ApiError
    from backend.api.jwt import jwt_required

    @app.errorhandler(ApiError)
    def _api_error(e):
        return fail(e.code, e.message, e.status)

    @app.route('/t/passenger')
    @jwt_required
    @require_mode(MODE_PASSENGER)
    def t_passenger():
        return ok({'ok': True})

    @app.route('/t/driver')
    @jwt_required
    @require_mode(MODE_DRIVER)
    def t_driver():
        return ok({'ok': True})

    return app.test_client()


class TestAuthn:
    def test_401_sin_token(self, guarded):
        resp = guarded.get('/t/passenger')
        assert resp.status_code == 401
        body = resp.get_json()
        assert body['success'] is False
        assert body['error']['code'] == 'MISSING_TOKEN'

    def test_token_invalido(self, guarded):
        resp = guarded.get('/t/passenger', headers={'Authorization': 'Bearer no-es-un-jwt'})
        assert resp.status_code == 401
        assert resp.get_json()['error']['code'] == 'INVALID_TOKEN'

    def test_token_expirado(self, app, guarded):
        uid, _ = _user(app)
        app.config['JWT_ACCESS_TTL_MINUTES'] = -1
        token = _token(app, uid, ROLE_PASSENGER, MODE_PASSENGER)
        resp = guarded.get('/t/passenger', headers={'Authorization': f'Bearer {token}'})
        assert resp.status_code == 401
        assert resp.get_json()['error']['code'] == 'TOKEN_EXPIRED'


class TestRoles:
    def test_403_pasajero_en_ruta_conductor(self, app, guarded):
        uid, _ = _user(app, role=ROLE_PASSENGER)
        token = _token(app, uid, ROLE_PASSENGER, MODE_PASSENGER)
        resp = guarded.get('/t/driver', headers={'Authorization': f'Bearer {token}'})
        assert resp.status_code == 403
        assert resp.get_json()['error']['code'] == 'FORBIDDEN'

    def test_403_conductor_en_ruta_pasajero(self, app, guarded):
        uid, _ = _user(app, role=ROLE_DRIVER, profile=DRIVER_STATUS_APPROVED)
        token = _token(app, uid, ROLE_DRIVER, MODE_DRIVER)
        resp = guarded.get('/t/passenger', headers={'Authorization': f'Bearer {token}'})
        assert resp.status_code == 403
        assert resp.get_json()['error']['code'] == 'FORBIDDEN'

    def test_modo_passenger_ok(self, app, guarded):
        uid, _ = _user(app, role=ROLE_PASSENGER)
        token = _token(app, uid, ROLE_PASSENGER, MODE_PASSENGER)
        resp = guarded.get('/t/passenger', headers={'Authorization': f'Bearer {token}'})
        assert resp.status_code == 200
        assert resp.get_json()['data'] == {'ok': True}

    def test_modo_driver_ok(self, app, guarded):
        uid, _ = _user(app, role=ROLE_DRIVER, profile=DRIVER_STATUS_APPROVED)
        token = _token(app, uid, ROLE_DRIVER, MODE_DRIVER)
        resp = guarded.get('/t/driver', headers={'Authorization': f'Bearer {token}'})
        assert resp.status_code == 200
        assert resp.get_json()['data'] == {'ok': True}


class TestRoleBoth:
    def test_both_modo_passenger_en_ruta_pasajero(self, app, guarded):
        uid, _ = _user(app, role=ROLE_BOTH, profile=DRIVER_STATUS_APPROVED)
        token = _token(app, uid, ROLE_BOTH, MODE_PASSENGER)
        resp = guarded.get('/t/passenger', headers={'Authorization': f'Bearer {token}'})
        assert resp.status_code == 200

    def test_both_modo_driver_en_ruta_conductor(self, app, guarded):
        uid, _ = _user(app, role=ROLE_BOTH, profile=DRIVER_STATUS_APPROVED)
        token = _token(app, uid, ROLE_BOTH, MODE_DRIVER)
        resp = guarded.get('/t/driver', headers={'Authorization': f'Bearer {token}'})
        assert resp.status_code == 200

    def test_both_modo_passenger_en_ruta_conductor_MODE_NOT_ALLOWED(self, app, guarded):
        uid, _ = _user(app, role=ROLE_BOTH, profile=DRIVER_STATUS_APPROVED)
        token = _token(app, uid, ROLE_BOTH, MODE_PASSENGER)
        resp = guarded.get('/t/driver', headers={'Authorization': f'Bearer {token}'})
        assert resp.status_code == 403
        assert resp.get_json()['error']['code'] == 'MODE_NOT_ALLOWED'

    def test_both_modo_driver_en_ruta_pasajero_MODE_NOT_ALLOWED(self, app, guarded):
        uid, _ = _user(app, role=ROLE_BOTH, profile=DRIVER_STATUS_APPROVED)
        token = _token(app, uid, ROLE_BOTH, MODE_DRIVER)
        resp = guarded.get('/t/passenger', headers={'Authorization': f'Bearer {token}'})
        assert resp.status_code == 403
        assert resp.get_json()['error']['code'] == 'MODE_NOT_ALLOWED'

    def test_both_sin_claim_mode_no_bloquea(self, app, guarded):
        # token de /auth/refresh se emite sin mode: el contexto no debe bloquear
        uid, _ = _user(app, role=ROLE_BOTH, profile=DRIVER_STATUS_APPROVED)
        token = _token(app, uid, ROLE_BOTH, None)
        resp = guarded.get('/t/driver', headers={'Authorization': f'Bearer {token}'})
        assert resp.status_code == 200


class TestDriverProfileStatus:
    def test_driver_sin_driver_profile(self, app, guarded):
        uid, _ = _user(app, role=ROLE_DRIVER)
        token = _token(app, uid, ROLE_DRIVER, MODE_DRIVER)
        resp = guarded.get('/t/driver', headers={'Authorization': f'Bearer {token}'})
        assert resp.status_code == 403
        assert resp.get_json()['error']['code'] == 'MODE_NOT_ALLOWED'

    @pytest.mark.parametrize('status', [DRIVER_STATUS_PENDING, DRIVER_STATUS_REJECTED])
    def test_status_no_aprobado_NOT_VERIFIED(self, app, guarded, status):
        uid, _ = _user(app, role=ROLE_DRIVER, profile=status)
        token = _token(app, uid, ROLE_DRIVER, MODE_DRIVER)
        resp = guarded.get('/t/driver', headers={'Authorization': f'Bearer {token}'})
        assert resp.status_code == 403
        assert resp.get_json()['error']['code'] == 'NOT_VERIFIED'

    def test_status_approved_ok(self, app, guarded):
        uid, _ = _user(app, role=ROLE_DRIVER, profile=DRIVER_STATUS_APPROVED)
        token = _token(app, uid, ROLE_DRIVER, MODE_DRIVER)
        resp = guarded.get('/t/driver', headers={'Authorization': f'Bearer {token}'})
        assert resp.status_code == 200


class TestRoleContraDB:
    def test_claim_mentira_ok_si_db_autoriza(self, app, guarded):
        """El token dice 'passenger' pero en DB el rol es driver+approved."""
        uid, _ = _user(app, role=ROLE_DRIVER, profile=DRIVER_STATUS_APPROVED)
        token = _token(app, uid, ROLE_PASSENGER, MODE_DRIVER)
        resp = guarded.get('/t/driver', headers={'Authorization': f'Bearer {token}'})
        assert resp.status_code == 200

    def test_claim_mentira_forbidden_si_db_no_autoriza(self, app, guarded):
        """El token dice 'driver' pero en DB el rol es passenger."""
        uid, _ = _user(app, role=ROLE_PASSENGER)
        token = _token(app, uid, ROLE_DRIVER, MODE_DRIVER)
        resp = guarded.get('/t/driver', headers={'Authorization': f'Bearer {token}'})
        assert resp.status_code == 403
        assert resp.get_json()['error']['code'] == 'FORBIDDEN'
