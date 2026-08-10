"""Identidad web (sesión) sobre el esquema unificado.

Claves de sesión:
  user_id     → id real en `users` (única identidad)
  user_name   → nombre en caché para headers/templates
  user_role   → rol persistido (passenger | driver | both | admin | company)
  active_mode → contexto de la sesión (passenger | driver). SOLO sesión,
                nunca se persiste en DB y nunca se usa para autorizar:
                la autorización se decide por user.role + driver_profile.
  is_admin    → flag legacy del portal admin (clave ADMIN_SECRET_KEY)

Templates legacy: driver_view() expone un objeto de presentación con los
nombres de campo planos que espera el HTML (vehicle_type, placa, moto_*,
auto_año, is_ocupado, etc.) — así las plantillas no se reescriben.
"""
from types import SimpleNamespace

from flask import session

from backend.models import (
    ROLE_ADMIN,
    ROLE_BOTH,
    ROLE_COMPANY,
    ROLE_DRIVER,
    ROLE_PASSENGER,
    MODE_DRIVER,
    MODE_PASSENGER,
    User,
)

SESSION_USER_ID = 'user_id'
SESSION_USER_NAME = 'user_name'
SESSION_USER_ROLE = 'user_role'
SESSION_ACTIVE_MODE = 'active_mode'
SESSION_IS_ADMIN = 'is_admin'
SESSION_IS_COMPANY = 'is_company'


def is_logged_in():
    return bool(session.get(SESSION_USER_ID))


def current_user():
    uid = session.get(SESSION_USER_ID)
    if not uid:
        return None
    return User.query.get(uid)


def current_driver_profile():
    user = current_user()
    if not user:
        return None
    return user.driver_profile


def current_active_mode():
    return session.get(SESSION_ACTIVE_MODE)


def is_driver_session():
    return (
        session.get(SESSION_ACTIVE_MODE) == MODE_DRIVER
        and current_driver_profile() is not None
    )


def allowed_modes(user):
    """Modos disponibles según rol + perfil existente."""
    modes = []
    if user.role in (ROLE_PASSENGER, ROLE_BOTH):
        modes.append(MODE_PASSENGER)
    if user.role in (ROLE_DRIVER, ROLE_BOTH) and user.driver_profile is not None:
        modes.append(MODE_DRIVER)
    return modes


def set_session(user, mode=None, csrf=True):
    """Inicia sesión con identidad unificada. mode se valida contra el rol."""
    session.clear()
    session[SESSION_USER_ID] = user.id
    session[SESSION_USER_NAME] = user.name
    session[SESSION_USER_ROLE] = user.role
    session[SESSION_ACTIVE_MODE] = mode if mode in allowed_modes(user) else None
    if user.role == ROLE_ADMIN:
        session[SESSION_IS_ADMIN] = True
    if user.role == ROLE_COMPANY:
        session[SESSION_IS_COMPANY] = True
    if csrf:
        import secrets

        session['csrf_token'] = secrets.token_hex(32)
    session.permanent = True


def switch_mode(target):
    """Cambia el contexto de sesión (solo si el rol lo permite)."""
    user = current_user()
    if not user:
        return False
    if target not in allowed_modes(user):
        return False
    session[SESSION_ACTIVE_MODE] = target
    return True


def driver_view(user):
    """Objeto de presentación para templates de conductor (esquema plano legacy).

    Expone campos del driver_profile + vehículo activo con los nombres que
    usan profile.html, edit_profile.html, dashboard.html y admin/drivers.html.
    """
    if user is None:
        return None
    profile = user.driver_profile
    vehicle = profile.active_vehicle if profile else None
    vtype = vehicle.type if vehicle else ''
    is_moto = vtype == 'moto'
    is_auto = vtype == 'auto'

    def vattr(name, default=''):
        return getattr(vehicle, name, None) if vehicle is not None else None or default

    def pattr(name, default=None):
        return getattr(profile, name, None) if profile is not None else None or default

    data = {
        # identidad
        'id': user.id,
        'name': user.name,
        'email': user.email,
        'phone': user.phone,
        'profile_picture': user.profile_picture,
        'rating_avg': user.rating_avg,
        'rating_count': user.rating_count,
        'balance': user.balance,
        'created_at': user.created_at,
        'role': user.role,
        # perfil de conductor
        'is_online': pattr('is_online', False),
        'is_busy': pattr('is_busy', False),
        'is_ocupado': pattr('is_busy', False),
        'lat': pattr('lat'),
        'lng': pattr('lng'),
        'last_location_update': pattr('last_location_update'),
        'is_verified': pattr('is_verified', False),
        'accepted_payments': pattr('accepted_payments', '["efectivo"]'),
        'mercadopago_qr': pattr('mercadopago_qr'),
        # vehículo
        'vehicle_type': vtype,
        'placa': vattr('placa'),
        'moto_marca': vattr('marca') if is_moto else '',
        'moto_modelo': vattr('modelo') if is_moto else '',
        'moto_color': vattr('color') if is_moto else '',
        'moto_cilindrada': vattr('cilindrada') if is_moto else '',
        'moto_anio': vattr('anio') if is_moto else '',
        'tiene_patente': vattr('has_patente', False),
        'tiene_casco': vattr('has_casco', False),
        'seguro_moto': vattr('has_seguro', False),
        'placa_auto': vattr('placa') if is_auto else '',
        'auto_marca': vattr('marca') if is_auto else '',
        'auto_modelo': vattr('modelo') if is_auto else '',
        'auto_color': vattr('color') if is_auto else '',
        'auto_año': vattr('anio') if is_auto else '',
        'anio': vattr('anio'),
        'tiene_patente_auto': vattr('has_patente', False),
        'seguro_auto': vattr('has_seguro', False),
        'tipo_seguro': vattr('tipo_seguro') or pattr('tipo_seguro') or '',
        'carnet_conducir': vattr('carnet_conducir') or pattr('carnet_conducir') or '',
        'ultimo_servicio': vattr('ultimo_servicio') or pattr('ultimo_servicio') or '',
        'carnet_conducir_auto': vattr('carnet_conducir') or pattr('carnet_conducir') or '',
        'tipo_seguro_auto': vattr('tipo_seguro') or pattr('tipo_seguro') or '',
        'ultimo_servicio_auto': vattr('ultimo_servicio') or pattr('ultimo_servicio') or '',
    }
    return SimpleNamespace(**data)
