"""
Endpoints de autenticación de la API v1 (/api/v1/auth/*).

Contrato Flutter: Bearer tokens, sin cookies. Identidad única (`users`):
- role: passenger | driver | both | admin | company (persistido)
- active_mode: contexto del token (passenger | driver) — claim `mode`,
  nunca autoriza por sí solo.
"""
import os
import base64
import hmac
import secrets
import string
from datetime import datetime, timedelta, timezone

from flask import request, g
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.exc import IntegrityError

from backend.models import (
    db, User, DriverProfile, Vehicle, EmailVerification,
    ROLE_DRIVER, ROLE_BOTH, MODE_DRIVER, MODE_PASSENGER,
)
from backend.auth import send_verification_email, save_driver_photo
from backend.validators import (
    sanitize_input, normalize_email,
    validate_name, validate_email, validate_password, first_error,
)
from backend.extensions import limiter
from backend.api import api_bp, ApiError, ok
from backend.api.jwt import (
    jwt_required, issue_tokens, rotate_refresh_token,
    hash_token, _find_refresh, current_user,
)

VERIFY_CODE_TTL_MINUTES = 10


def _as_utc(dt):
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _smtp_configured():
    return bool(os.getenv('SMTP_SERVER') and os.getenv('SMTP_USER') and os.getenv('SMTP_PASS'))


def _require_verified(obj):
    if _smtp_configured() and not obj.email_verified:
        raise ApiError('EMAIL_NOT_VERIFIED', 'Debes verificar tu correo electrónico', 403)


def _send_verify_code(obj):
    """Si SMTP no está configurado, la cuenta queda verificada (igual que la web).
    Devuelve True si se envió un correo con código."""
    if not _smtp_configured():
        obj.email_verified = True
        db.session.commit()
        return False
    code = ''.join(secrets.choice(string.digits) for _ in range(6))
    ev = EmailVerification(
        user_id=obj.id,
        email=obj.email,
        code_hash=hash_token(code),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=VERIFY_CODE_TTL_MINUTES),
    )
    db.session.add(ev)
    db.session.commit()
    send_verification_email(obj.email, code)
    return True


def _user_payload(user, active_mode=None):
    payload = {
        'id': user.id,
        'role': user.role,
        'name': user.name,
        'email': user.email,
        'phone': user.phone or '',
        'email_verified': bool(user.email_verified),
        'rating_avg': float(user.rating_avg or 0),
        'rating_count': user.rating_count or 0,
        'profile_picture': user.profile_picture,
        'active_mode': active_mode,
    }
    profile = user.driver_profile
    if profile is not None:
        payload['driver'] = {
            'is_online': bool(profile.is_online),
            'is_busy': bool(profile.is_busy),
            'is_verified': bool(profile.is_verified),
            'vehicle_type': profile.active_vehicle.type if profile.active_vehicle else None,
        }
    return payload


def _tokens_payload(user, active_mode, with_verification_sent=False):
    access, refresh = issue_tokens(user.id, user.role, active_mode)
    payload = {
        'tokens': {'access_token': access, 'refresh_token': refresh, 'token_type': 'Bearer'},
        'user': _user_payload(user, active_mode),
    }
    if with_verification_sent:
        payload['verification_sent'] = True
    return payload


def _default_mode(user, requested):
    """Resuelve active_mode: explícito si es válido, si no el único disponible."""
    if user.role == ROLE_BOTH:
        if requested in (MODE_PASSENGER, MODE_DRIVER):
            return requested
        return MODE_PASSENGER
    return MODE_DRIVER if user.role == ROLE_DRIVER else MODE_PASSENGER


def _decode_photo(data):
    """Acepta data URL base64 (data:image/png;base64,...) o base64 puro."""
    if not data:
        return None, None
    try:
        if ',' in str(data)[:40]:
            header, encoded = str(data).split(',', 1)
        else:
            encoded = str(data)
        return save_driver_photo(base64.b64decode(encoded))
    except Exception:
        return None, 'invalid'


def _build_vehicle(data, vehicle_type):
    if vehicle_type == 'moto':
        return Vehicle(
            type='moto',
            placa=sanitize_input(data.get('placa')),
            marca=sanitize_input(data.get('moto_marca')),
            modelo=sanitize_input(data.get('moto_modelo')),
            color=sanitize_input(data.get('moto_color')),
            cilindrada=sanitize_input(data.get('moto_cilindrada')),
            tipo_seguro=sanitize_input(data.get('tipo_seguro')),
            carnet_conducir=sanitize_input(data.get('carnet_conducir')),
            ultimo_servicio=sanitize_input(data.get('ultimo_servicio')),
            is_active=True,
        )
    return Vehicle(
        type='auto',
        placa=sanitize_input(data.get('placa_auto')),
        marca=sanitize_input(data.get('auto_marca')),
        modelo=sanitize_input(data.get('auto_modelo')),
        color=sanitize_input(data.get('auto_color')),
        anio=sanitize_input(data.get('auto_año')),
        tipo_seguro=sanitize_input(data.get('tipo_seguro_auto')),
        carnet_conducir=sanitize_input(data.get('carnet_conducir_auto')),
        ultimo_servicio=sanitize_input(data.get('ultimo_servicio_auto')),
        is_active=True,
    )


@api_bp.route('/auth/register', methods=['POST'])
@limiter.limit('10 per minute')
def register():
    data = request.get_json(silent=True) or {}
    name = sanitize_input(data.get('name') or '')
    email = normalize_email(data.get('email'))
    password = data.get('password') or ''
    phone = sanitize_input(data.get('phone') or '')

    err = first_error(validate_name(name), validate_email(email), validate_password(password))
    if err:
        raise ApiError('VALIDATION_ERROR', err, 400)
    if User.query.filter_by(email=email).first():
        raise ApiError('EMAIL_TAKEN', 'Correo electrónico ya registrado', 409)

    user = User(name=name, email=email, password=generate_password_hash(password), phone=phone)
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise ApiError('EMAIL_TAKEN', 'Correo electrónico ya registrado', 409)

    sent = _send_verify_code(user)
    payload = _tokens_payload(user, MODE_PASSENGER)
    payload['verification_sent'] = sent
    return ok(payload), 201


@api_bp.route('/auth/register/driver', methods=['POST'])
@limiter.limit('10 per minute')
def register_driver():
    data = request.get_json(silent=True) or {}
    name = sanitize_input(data.get('name') or '')
    email = normalize_email(data.get('email'))
    password = data.get('password') or ''
    phone = sanitize_input(data.get('phone') or '')
    vehicle_type = data.get('vehicle_type', 'moto')
    if vehicle_type not in ('moto', 'auto'):
        raise ApiError('VALIDATION_ERROR', 'vehicle_type debe ser moto o auto', 400)

    err = first_error(validate_name(name), validate_email(email), validate_password(password))
    if err:
        raise ApiError('VALIDATION_ERROR', err, 400)

    profile_picture, perr = _decode_photo(data.get('profile_picture'))
    if perr:
        raise ApiError('VALIDATION_ERROR', 'Foto de perfil inválida', 400)

    vehicle = _build_vehicle(data, vehicle_type)
    required = [name, email, password, phone, vehicle.placa, vehicle.marca,
                vehicle.modelo, vehicle.color, vehicle.tipo_seguro,
                vehicle.carnet_conducir, vehicle.ultimo_servicio]
    if vehicle_type == 'auto':
        required.append(vehicle.anio)
    if not all(required):
        raise ApiError('VALIDATION_ERROR', 'Por favor completa todos los campos obligatorios', 400)

    # Identidad única: mismo email = misma cuenta. Pasajero existente → 'both'.
    existing = User.query.filter_by(email=email).first()
    if existing:
        if existing.role != 'passenger':
            raise ApiError('EMAIL_TAKEN', 'El correo electrónico ya está registrado', 409)
        user = existing
        user.role = ROLE_BOTH
        user.phone = user.phone or phone
        if not user.profile_picture:
            user.profile_picture = profile_picture or user.profile_picture
        if user.driver_profile is None:
            user.driver_profile = DriverProfile(user_id=user.id, vehicles=[vehicle])
        else:
            user.driver_profile.vehicles.append(vehicle)
    else:
        user = User(
            name=name, email=email, password=generate_password_hash(password),
            phone=phone, profile_picture=profile_picture or '', role=ROLE_DRIVER,
        )
        user.driver_profile = DriverProfile(user_id=user.id, vehicles=[vehicle])

    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise ApiError('EMAIL_TAKEN', 'Correo electrónico ya registrado', 409)

    sent = _send_verify_code(user)
    payload = _tokens_payload(user, MODE_DRIVER)
    payload['verification_sent'] = sent
    return ok(payload), 201


@api_bp.route('/auth/login', methods=['POST'])
@limiter.limit('10 per minute')
def login():
    data = request.get_json(silent=True) or {}
    email = normalize_email(data.get('email'))
    password = data.get('password') or ''
    if not email or not password:
        raise ApiError('VALIDATION_ERROR', 'email y password requeridos', 400)

    user = User.query.filter_by(email=email).first()
    if not user or not check_password_hash(user.password, password):
        raise ApiError('INVALID_CREDENTIALS', 'Credenciales inválidas', 401)

    _require_verified(user)
    active_mode = _default_mode(user, data.get('mode'))
    return ok(_tokens_payload(user, active_mode))


@api_bp.route('/auth/refresh', methods=['POST'])
@limiter.limit('20 per minute')
def refresh():
    data = request.get_json(silent=True) or {}
    raw = data.get('refresh_token')
    if not raw:
        raise ApiError('VALIDATION_ERROR', 'refresh_token requerido', 400)
    access, new_refresh = rotate_refresh_token(raw)
    return ok({'access_token': access, 'refresh_token': new_refresh, 'token_type': 'Bearer'})


@api_bp.route('/auth/logout', methods=['POST'])
def logout():
    data = request.get_json(silent=True) or {}
    raw = data.get('refresh_token')
    if raw:
        rt = _find_refresh(raw)
        if rt and rt.revoked_at is None:
            rt.revoked_at = datetime.now(timezone.utc)
            db.session.commit()
    return ok({'success': True})


@api_bp.route('/auth/me')
@jwt_required
def me():
    user = current_user()
    if not user:
        raise ApiError('NOT_FOUND', 'Usuario no encontrado', 404)
    return ok({'user': _user_payload(user, g.active_mode)})


@api_bp.route('/auth/switch-mode', methods=['POST'])
@jwt_required
def switch_mode():
    """Cambia el contexto del token (solo si el rol lo permite)."""
    data = request.get_json(silent=True) or {}
    target = data.get('mode', '')
    user = current_user()
    if not user:
        raise ApiError('NOT_FOUND', 'Usuario no encontrado', 404)
    if target not in (MODE_PASSENGER, MODE_DRIVER):
        raise ApiError('VALIDATION_ERROR', 'mode debe ser passenger o driver', 400)
    if user.role == ROLE_BOTH:
        if target == MODE_DRIVER and user.driver_profile is None:
            raise ApiError('FORBIDDEN', 'No tienes perfil de conductor', 403)
        access, _ = issue_tokens(user.id, user.role, target)
        return ok({'access_token': access, 'active_mode': target})
    raise ApiError('FORBIDDEN', 'Tu rol no admite cambio de modo', 403)


@api_bp.route('/auth/verify-email', methods=['POST'])
@jwt_required
def verify_email():
    data = request.get_json(silent=True) or {}
    code = str(data.get('code', ''))
    if not code:
        raise ApiError('VALIDATION_ERROR', 'code requerido', 400)
    ev = EmailVerification.query.filter_by(
        user_id=g.user_id, verified_at=None
    ).order_by(EmailVerification.created_at.desc()).first()
    if not ev:
        raise ApiError('VALIDATION_ERROR', 'No hay código pendiente', 400)
    if _as_utc(ev.expires_at) < datetime.now(timezone.utc):
        raise ApiError('CODE_EXPIRED', 'Código expirado. Solicita uno nuevo.', 400)
    if not hmac.compare_digest(hash_token(code), ev.code_hash):
        ev.attempts += 1
        if ev.attempts >= 5:
            ev.verified_at = datetime.now(timezone.utc)
        db.session.commit()
        raise ApiError('INVALID_CODE', 'Código incorrecto', 400)
    user = current_user()
    if user:
        user.email_verified = True
    ev.verified_at = datetime.now(timezone.utc)
    db.session.commit()
    return ok({'email_verified': True})


# ─────────────────── Profile, photo, password ───────────────────


@api_bp.route('/auth/profile', methods=['PUT'])
@jwt_required
def update_profile():
    """PUT /auth/profile — editar nombre y teléfono."""
    user = current_user()
    if not user:
        raise ApiError('NOT_FOUND', 'Usuario no encontrado', 404)

    data = request.get_json(silent=True) or {}
    name = sanitize_input(data.get('name'))
    phone = sanitize_input(data.get('phone'))

    if name is not None:
        err = validate_name(name)
        if err:
            raise ApiError('VALIDATION_ERROR', err)
        user.name = name

    if phone is not None:
        user.phone = phone

    db.session.commit()
    return ok({'user': _user_payload(user, g.active_mode)})


@api_bp.route('/auth/profile/photo', methods=['POST'])
@jwt_required
def upload_profile_photo():
    """POST /auth/profile/photo — subir foto de perfil (base64)."""
    user = current_user()
    if not user:
        raise ApiError('NOT_FOUND', 'Usuario no encontrado', 404)

    data = request.get_json(silent=True) or {}
    image_data = data.get('image')
    if not image_data:
        raise ApiError('VALIDATION_ERROR', 'image requerido (base64)')

    try:
        raw = base64.b64decode(
            image_data.split(',', 1)[1] if ',' in image_data else image_data
        )
    except Exception:
        raise ApiError('VALIDATION_ERROR', 'Imagen base64 inválida')

    url = save_driver_photo(raw)
    if not url or not url[0]:
        raise ApiError('VALIDATION_ERROR', 'Imagen inválida o demasiado grande (máx 2MB)')

    user.profile_picture = url[0]
    db.session.commit()
    return ok({'profile_picture': user.profile_picture})


@api_bp.route('/auth/password', methods=['POST'])
@jwt_required
def change_password():
    """POST /auth/password — cambiar contraseña."""
    user = current_user()
    if not user:
        raise ApiError('NOT_FOUND', 'Usuario no encontrado', 404)

    data = request.get_json(silent=True) or {}
    current_password = data.get('current_password', '')
    new_password = data.get('new_password', '')

    if not current_password or not new_password:
        raise ApiError('VALIDATION_ERROR', 'current_password y new_password requeridos')

    if not check_password_hash(user.password, current_password):
        raise ApiError('INVALID_CREDENTIALS', 'Contraseña actual incorrecta')

    err = validate_password(new_password)
    if err:
        raise ApiError('VALIDATION_ERROR', err)

    user.password = generate_password_hash(new_password)
    db.session.commit()
    return ok({'success': True})


@api_bp.route('/auth/guidelines', methods=['GET'])
@jwt_required
def guidelines_status():
    """GET /auth/guidelines — verificar si el usuario aceptó las guidelines."""
    user = current_user()
    if not user:
        raise ApiError('NOT_FOUND', 'Usuario no encontrado', 404)
    return ok({'accepted': bool(user.accepted_guidelines)})


@api_bp.route('/auth/guidelines', methods=['POST'])
@jwt_required
def accept_guidelines():
    """POST /auth/guidelines — aceptar las guidelines de la comunidad."""
    user = current_user()
    if not user:
        raise ApiError('NOT_FOUND', 'Usuario no encontrado', 404)
    user.accepted_guidelines = True
    db.session.commit()
    return ok({'accepted': True})
