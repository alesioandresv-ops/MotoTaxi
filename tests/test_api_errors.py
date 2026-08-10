"""Etapa 0 — catálogo de errores estables + serializers reutilizables.

El catálogo es la única fuente de status HTTP por código (contrato §12).
Los serializers garantizan dinero como string decimal (contrato §1.4).
"""
from decimal import Decimal

import pytest

from backend.api.errors import ERROR_CATALOG, ApiError, api_error, raise_api_error
from backend.api.serializers import iso_dt, money_str, public_user


class TestErrorCatalog:
    def test_catalogo_cubre_codigos_del_contrato(self):
        for code in (
            'TOKEN_EXPIRED', 'TOKEN_INVALID', 'TOKEN_REVOKED',
            'INVALID_CREDENTIALS', 'EMAIL_NOT_VERIFIED', 'EMAIL_TAKEN',
            'VALIDATION_ERROR', 'NOT_FOUND', 'FORBIDDEN', 'METHOD_NOT_ALLOWED',
            'MODE_NOT_ALLOWED', 'ACTIVE_TRIP_EXISTS', 'TRIP_NOT_AVAILABLE',
            'INVALID_TRANSITION', 'TRIP_FINALIZED', 'TRIP_NOT_COMPLETED',
            'ALREADY_RATED', 'INVALID_RATING', 'INSUFFICIENT_BALANCE',
            'TRIP_ALREADY_PAID', 'TOPUP_MIN', 'TOPUP_MAX', 'INVALID_AMOUNT',
            'MP_NOT_CONFIGURED', 'NOT_ONLINE', 'NOT_VERIFIED',
            'INVALID_COORDINATES', 'LOCATION_REQUIRED', 'MEMBER_EXISTS',
            'PLAN_LIMIT_REACHED', 'COMPANY_INACTIVE', 'RATE_LIMITED',
            'INTERNAL_ERROR',
        ):
            assert code in ERROR_CATALOG, f'falta {code} en el catálogo'

    def test_api_error_usa_status_del_catalogo(self):
        err = api_error('NOT_FOUND')
        assert err.status == 404
        assert err.code == 'NOT_FOUND'

    def test_api_error_mensaje_personalizado(self):
        err = api_error('NOT_FOUND', 'Viaje 999 no existe')
        assert err.message == 'Viaje 999 no existe'
        assert err.status == 404

    def test_status_explicito_gana(self):
        err = api_error('VALIDATION_ERROR', status=422)
        assert err.status == 422

    def test_code_desconocido_cae_en_INTERNAL_ERROR(self):
        err = api_error('CODIGO_INVENTADO')
        assert err.code == 'CODIGO_INVENTADO'
        assert err.status == 500
        assert err.message == ERROR_CATALOG['INTERNAL_ERROR'][1]

    def test_raise_api_error(self):
        with pytest.raises(ApiError) as exc:
            raise_api_error('FORBIDDEN')
        assert exc.value.status == 403

    def test_errorhandler_usa_envelope(self, app):
        """Ruta real del blueprint: ApiError → envelope del catálogo."""
        resp = app.test_client().get('/api/v1/auth/me')
        body = resp.get_json()
        assert resp.status_code == 401
        assert body == {'success': False,
                        'error': {'code': 'MISSING_TOKEN',
                                  'message': 'Token de acceso requerido'}}

    def test_api_error_default_message_del_catalogo(self):
        err = api_error('NOT_VERIFIED')
        assert err.message == 'Conductor no verificado (status distinto de approved)'


class TestSerializers:
    def test_money_str_dos_decimales(self):
        assert money_str(Decimal('14.8')) == '14.80'
        assert money_str(Decimal('14.80')) == '14.80'
        assert money_str(Decimal('0')) == '0.00'
        assert money_str(Decimal('0.5')) == '0.50'

    def test_money_str_desde_numeros_y_none(self):
        assert money_str('9.9') == '9.90'
        assert money_str(9) == '9.00'
        assert money_str(None) == '0.00'

    def test_iso_dt(self):
        from datetime import datetime, timezone
        assert iso_dt(None) is None
        dt = datetime(2026, 8, 10, 14, 0, 0)
        assert iso_dt(dt) == '2026-08-10T14:00:00Z'
        aware = datetime(2026, 8, 10, 14, 0, 0, tzinfo=timezone.utc)
        assert iso_dt(aware) == '2026-08-10T14:00:00Z'

    def test_public_user(self, app):
        from backend.models import User, db
        with app.app_context():
            u = User(name='Ana', email='ana@van.test', password='x',
                     role='passenger', rating_avg=4.9, rating_count=21)
            db.session.add(u)
            db.session.commit()
            payload = public_user(u)
        assert payload == {
            'id': u.id, 'name': 'Ana', 'rating_avg': 4.9,
            'rating_count': 21, 'profile_picture': None,
        }

    def test_public_user_none(self):
        assert public_user(None) is None
