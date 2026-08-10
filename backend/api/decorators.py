"""Decorators de autenticación/autorización de la API v1 (Etapa 0).

`require_mode(mode)` es la autorización estándar de la API: valida SIEMPRE
contra la DB (contrato §3, §9):

- Modo pasajero: `users.role ∈ (passenger, both)`.
- Modo conductor: `users.role ∈ (driver, both)` + `driver_profiles` existe
  + `driver_profiles.status == 'approved'` (única fuente de autorización).
- `role` se lee de la DB en cada request (el claim del JWT no se confía).
- El claim `mode` del token es solo contexto: si declara un modo y no
  coincide con el requerido → MODE_NOT_ALLOWED. Nunca autoriza por sí solo.

Errores (catálogo estable): FORBIDDEN (403) por rol no permitido,
MODE_NOT_ALLOWED (403) por modo/contexto o perfil inexistente,
NOT_VERIFIED (403) por status != approved, NOT_FOUND (404) si el user no
existe en DB.
"""
from functools import wraps

from flask import g

from backend.models import (
    MODE_DRIVER,
    MODE_PASSENGER,
    ROLE_BOTH,
    ROLE_DRIVER,
    ROLE_PASSENGER,
    DRIVER_STATUS_APPROVED,
)
from backend.api.errors import api_error
from backend.api.jwt import current_user

_PASSENGER_ROLES = (ROLE_PASSENGER, ROLE_BOTH)
_DRIVER_ROLES = (ROLE_DRIVER, ROLE_BOTH)


def require_mode(mode):
    """Exige que el usuario autenticado opere en `mode` (passenger|driver).

    Uso: `@jwt_required` + `@require_mode('driver')`.
    """
    if mode not in (MODE_PASSENGER, MODE_DRIVER):
        raise ValueError(f'mode inválido: {mode!r}')

    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            user = current_user()
            if user is None:
                raise api_error('NOT_FOUND', 'Usuario no encontrado')

            if user.role == ROLE_BOTH and g.active_mode not in (None, mode):
                raise api_error(
                    'MODE_NOT_ALLOWED',
                    f'Tu modo actual no permite esta operación (requiere modo {mode})',
                )

            if mode == MODE_PASSENGER:
                if user.role not in _PASSENGER_ROLES:
                    raise api_error('FORBIDDEN', 'Solo pasajeros pueden realizar esta operación')
            else:
                if user.role not in _DRIVER_ROLES:
                    raise api_error('FORBIDDEN', 'Solo conductores pueden realizar esta operación')
                profile = user.driver_profile
                if profile is None:
                    raise api_error('MODE_NOT_ALLOWED', 'No tienes perfil de conductor')
                if profile.status != DRIVER_STATUS_APPROVED:
                    raise api_error('NOT_VERIFIED')

            return f(*args, **kwargs)

        return decorated

    return decorator
