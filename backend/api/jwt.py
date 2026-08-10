"""
Núcleo JWT de la API v1.

- Access token: JWT HS256, corto (30 min por defecto), stateless.
  Claims: sub (user_id en `users`), role (persistido), mode (active_mode de
  sesión, contexto). NUNCA se autoriza por `mode`: la autorización se decide
  por role + driver_profile en BD (igual que la web).
- Refresh token: opaco (urlsafe), guardado en BD hasheado (sha256), rotativo.
  Rotación + detección de reuso: si un refresh ya usado aparece de nuevo,
  se revocan TODOS los tokens del usuario (respuesta a sesión comprometida).
"""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt as pyjwt
from flask import current_app, g, request

from backend.models import RefreshToken, User, ROLES, db
from backend.api import ApiError

ALGORITHM = 'HS256'


def _secret():
    return current_app.config['JWT_SECRET_KEY']


def _now():
    return datetime.now(timezone.utc)


def create_access_token(user_id, role, active_mode=None):
    now = _now()
    payload = {
        'sub': str(user_id),
        'role': role,
        'mode': active_mode,
        'jti': secrets.token_hex(16),
        'iat': now,
        'exp': now + timedelta(minutes=current_app.config['JWT_ACCESS_TTL_MINUTES']),
    }
    return pyjwt.encode(payload, _secret(), algorithm=ALGORITHM)


def hash_token(token):
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def issue_tokens(user_id, role, active_mode=None):
    access = create_access_token(user_id, role, active_mode)
    refresh = secrets.token_urlsafe(48)
    rt = RefreshToken(
        user_id=user_id,
        token_hash=hash_token(refresh),
        expires_at=_now() + timedelta(days=current_app.config['JWT_REFRESH_TTL_DAYS']),
        user_agent=(request.headers.get('User-Agent', '') or '')[:255],
    )
    db.session.add(rt)
    db.session.commit()
    return access, refresh


def _find_refresh(raw_token):
    return RefreshToken.query.filter_by(token_hash=hash_token(raw_token)).first()


def _as_utc(dt):
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _revoke_all_for(user_id):
    now = _now()
    for t in RefreshToken.query.filter_by(user_id=user_id, revoked_at=None).all():
        t.revoked_at = now
    db.session.commit()


def rotate_refresh_token(raw_token):
    token = _find_refresh(raw_token)
    if not token:
        raise ApiError('INVALID_REFRESH', 'Token de refresco inválido', 401)
    if token.revoked_at is not None:
        _revoke_all_for(token.user_id)
        raise ApiError('TOKEN_REUSE_DETECTED', 'Sesión comprometida: todos los tokens fueron revocados', 401)
    if _as_utc(token.expires_at) < _now():
        raise ApiError('TOKEN_EXPIRED', 'Token de refresco expirado', 401)
    user = User.query.get(token.user_id)
    access, new_refresh = issue_tokens(
        token.user_id, user.role if user else 'passenger'
    )
    new_token = _find_refresh(new_refresh)
    token.revoked_at = _now()
    token.replaced_by_id = new_token.id
    db.session.commit()
    return access, new_refresh


def _parse_bearer():
    header = request.headers.get('Authorization', '')
    if not header.startswith('Bearer '):
        return None
    return header[7:].strip()


def jwt_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = _parse_bearer()
        if not token:
            raise ApiError('MISSING_TOKEN', 'Token de acceso requerido', 401)
        try:
            payload = pyjwt.decode(token, _secret(), algorithms=[ALGORITHM])
        except pyjwt.ExpiredSignatureError:
            raise ApiError('TOKEN_EXPIRED', 'Token de acceso expirado', 401)
        except pyjwt.InvalidTokenError:
            raise ApiError('INVALID_TOKEN', 'Token de acceso inválido', 401)
        user_id = payload.get('sub')
        role = payload.get('role')
        if not user_id or not str(user_id).isdigit() or role not in ROLES:
            raise ApiError('INVALID_TOKEN', 'Token de acceso inválido', 401)
        g.user_id = int(user_id)
        g.role = role
        g.active_mode = payload.get('mode')
        g.token_jti = payload.get('jti')
        return f(*args, **kwargs)
    return decorated


def roles_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if g.role not in roles:
                raise ApiError('FORBIDDEN', 'No autorizado para esta operación', 403)
            return f(*args, **kwargs)
        return decorated
    return decorator


def current_user():
    return User.query.get(g.user_id)


def current_driver_profile():
    user = current_user()
    if not user:
        return None
    return user.driver_profile
