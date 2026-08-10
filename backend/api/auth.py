"""
Endpoints de autenticación de la API v1 (/api/v1/auth/*).

La web (sesiones + CSRF) no cambia. Estos endpoints son el contrato que
consume la app Flutter: Bearer tokens, sin cookies.
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

from backend.models import db, User, Driver, EmailVerification
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


def _require_verified(user_type, obj):
    if _smtp_configured() and not obj.email_verified:
        raise ApiError('EMAIL_NOT_VERIFIED', 'Debes verificar tu correo electrónico', 403)


def _send_verify_code(user_type, obj):
    """Si SMTP no está configurado, la cuenta queda verificada (igual que la web).
    Devuelve True si se envió un correo con código."""
    if not _smtp_configured():
        obj.email_verified = True
        db.session.commit()
        return False
    code = ''.join(secrets.choice(string.digits) for _ in range(6))
    ev = EmailVerification(
        user_type=user_type,
        user_id=obj.id,
        email=obj.email,
        code_hash=hash_token(code),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=VERIFY_CODE_TTL_MINUTES),
    )
    db.session.add(ev)
    db.session.commit()
    send_verification_email(obj.email, code)
    return True


def _user_payload(user_type, obj):
    if user_type == 'user':
        return {
            'id': obj.id, 'type': 'user', 'name': obj.name, 'email': obj.email,
            'phone': obj.phone or '', 'email_verified': bool(obj.email_verified),
            'rating_avg': float(obj.rating_avg or 0), 'rating_count': obj.rating_count or 0,
            'profile_picture': obj.profile_picture,
        }
    return {
        'id': obj.id, 'type': 'driver', 'name': obj.name, 'email': obj.email,
        'phone': obj.phone or '', 'email_verified': bool(obj.email_verified),
        'rating_avg': float(obj.rating_avg or 0), 'rating_count': obj.rating_count or 0,
        'vehicle_type': obj.vehicle_type, 'is_verified': bool(obj.is_verified),
        'profile_picture': obj.profile_picture,
    }


def _tokens_payload(user_type, obj, with_verification_sent=False):
    access, refresh = issue_tokens(user_type, obj.id)
    payload = {
        'tokens': {'access_token': access, 'refresh_token': refresh, 'token_type': 'Bearer'},
        'user': _user_payload(user_type, obj),
    }
    if with_verification_sent:
        payload['verification_sent'] = True
    return payload


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

    sent = _send_verify_code('user', user)
    payload = _tokens_payload('user', user)
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

    carnet_conducir = sanitize_input(data.get('carnet_conducir'))

    if vehicle_type == 'moto':
        placa = sanitize_input(data.get('placa'))
        moto_marca = sanitize_input(data.get('moto_marca'))
        moto_modelo = sanitize_input(data.get('moto_modelo'))
        moto_color = sanitize_input(data.get('moto_color'))
        moto_cilindrada = sanitize_input(data.get('moto_cilindrada'))
        tipo_seguro = sanitize_input(data.get('tipo_seguro'))
        ultimo_servicio = sanitize_input(data.get('ultimo_servicio'))
        required = [name, email, password, phone, placa, moto_marca, moto_modelo,
                    moto_color, moto_cilindrada, tipo_seguro, carnet_conducir, ultimo_servicio]
        if not all(required):
            raise ApiError('VALIDATION_ERROR', 'Por favor completa todos los campos obligatorios para moto', 400)
        driver = Driver(
            name=name, email=email, password=generate_password_hash(password),
            phone=phone, profile_picture=profile_picture or '', vehicle_type='moto',
            placa=placa, moto_marca=moto_marca, moto_modelo=moto_modelo,
            moto_color=moto_color, moto_cilindrada=moto_cilindrada,
            tipo_seguro=tipo_seguro, carnet_conducir=carnet_conducir,
            ultimo_servicio=ultimo_servicio,
        )
    else:
        placa_auto = sanitize_input(data.get('placa_auto'))
        auto_marca = sanitize_input(data.get('auto_marca'))
        auto_modelo = sanitize_input(data.get('auto_modelo'))
        auto_color = sanitize_input(data.get('auto_color'))
        auto_año = sanitize_input(data.get('auto_año'))
        tipo_seguro_auto = sanitize_input(data.get('tipo_seguro_auto'))
        carnet_conducir_auto = sanitize_input(data.get('carnet_conducir_auto')) or carnet_conducir
        ultimo_servicio_auto = sanitize_input(data.get('ultimo_servicio_auto'))
        required = [name, email, password, phone, placa_auto, auto_marca, auto_modelo,
                    auto_color, auto_año, tipo_seguro_auto, carnet_conducir_auto]
        if not all(required):
            raise ApiError('VALIDATION_ERROR', 'Por favor completa todos los campos obligatorios para auto', 400)
        driver = Driver(
            name=name, email=email, password=generate_password_hash(password),
            phone=phone, profile_picture=profile_picture or '', vehicle_type='auto',
            placa_auto=placa_auto, auto_marca=auto_marca, auto_modelo=auto_modelo,
            auto_color=auto_color, auto_año=auto_año,
            tipo_seguro_auto=tipo_seguro_auto, carnet_conducir_auto=carnet_conducir_auto,
            ultimo_servicio_auto=ultimo_servicio_auto,
        )

    db.session.add(driver)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise ApiError('EMAIL_TAKEN', 'Correo electrónico de conductor ya registrado', 409)

    sent = _send_verify_code('driver', driver)
    payload = _tokens_payload('driver', driver)
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
    if user and check_password_hash(user.password, password):
        _require_verified('user', user)
        return ok(_tokens_payload('user', user))

    driver = Driver.query.filter_by(email=email).first()
    if driver and check_password_hash(driver.password, password):
        _require_verified('driver', driver)
        return ok(_tokens_payload('driver', driver))

    raise ApiError('INVALID_CREDENTIALS', 'Credenciales inválidas', 401)


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
    obj = current_user()
    if not obj:
        raise ApiError('NOT_FOUND', 'Usuario no encontrado', 404)
    return ok({'user': _user_payload(g.user_type, obj)})


@api_bp.route('/auth/verify-email', methods=['POST'])
@jwt_required
def verify_email():
    data = request.get_json(silent=True) or {}
    code = str(data.get('code', ''))
    if not code:
        raise ApiError('VALIDATION_ERROR', 'code requerido', 400)
    ev = EmailVerification.query.filter_by(
        user_type=g.user_type, user_id=g.user_id, verified_at=None
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
    obj = current_user()
    if obj:
        obj.email_verified = True
    ev.verified_at = datetime.now(timezone.utc)
    db.session.commit()
    return ok({'email_verified': True})
