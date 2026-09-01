"""
Endpoints de conductor y geolocalización de la API v1 (/api/v1/drivers/*).

Agrupa:
- POST /drivers/location       — conductor envía ubicación (lat/lng)
- POST /drivers/online         — toggle online/offline
- GET  /drivers/nearby         — conductores cercanos al pasajero
"""
import base64
import json
import os
import uuid
from datetime import datetime, timezone

from flask import request

from backend.models import db, User, DriverProfile, Vehicle, PAYMENT_METHODS
from backend.api import api_bp, ok
from backend.api.jwt import jwt_required, current_user
from backend.api.decorators import require_mode
from backend.api.serializers import iso_dt
from backend.extensions import limiter
from backend.services.fare import calcular_distancia


# ── helpers locales ──────────────────────────────────────────────

def _parse_accepted_payments(raw):
    if not raw:
        return ['efectivo']
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [p for p in parsed if p in PAYMENT_METHODS]
    except (json.JSONDecodeError, TypeError):
        pass
    return ['efectivo']


def _vehicle_info(user):
    """Info pública del vehículo del conductor."""
    if not user or not user.driver_profile:
        return {'vehicle_type': None, 'accepted_payments': ['efectivo'], 'mercadopago_qr': None}
    profile = user.driver_profile
    v = profile.active_vehicle
    accepted = _parse_accepted_payments(profile.accepted_payments)
    if v is None:
        return {
            'vehicle_type': None, 'accepted_payments': accepted,
            'mercadopago_qr': profile.mercadopago_qr,
        }
    if v.type == 'auto':
        return {
            'vehicle_type': 'auto',
            'marca': v.marca or '',
            'modelo': v.modelo or '',
            'color': v.color or '',
            'placa': v.placa or '',
            'año': v.anio or '',
            'accepted_payments': accepted,
            'mercadopago_qr': profile.mercadopago_qr,
        }
    return {
        'vehicle_type': 'moto',
        'marca': v.marca or '',
        'modelo': v.modelo or '',
        'color': v.color or '',
        'placa': v.placa or '',
        'cilindrada': v.cilindrada or '',
        'tiene_casco': v.has_casco,
        'accepted_payments': accepted,
        'mercadopago_qr': profile.mercadopago_qr,
    }


def _nearby_drivers_query(vehicle_type=''):
    """Conductores online + libres (users ⋈ driver_profiles ⋈ vehicles)."""
    query = (
        db.session.query(User)
        .join(DriverProfile, DriverProfile.user_id == User.id)
        .filter(
            DriverProfile.is_online.is_(True),
            DriverProfile.is_busy.is_(False),
            DriverProfile.lat.isnot(None),
            DriverProfile.lng.isnot(None),
        )
    )
    if vehicle_type in ('moto', 'auto'):
        query = (
            query.join(Vehicle, Vehicle.driver_profile_id == DriverProfile.id)
            .filter(Vehicle.is_active.is_(True), Vehicle.type == vehicle_type)
            .distinct()
        )
    return query


# ── POST /drivers/location ──────────────────────────────────────

@api_bp.route('/drivers/location', methods=['POST'])
@jwt_required
@require_mode('driver')
def api_driver_location():
    """Conductor envía su ubicación actual."""
    profile = current_user().driver_profile
    if not profile.is_online:
        from backend.api import fail
        return fail('NOT_ONLINE', 'Debes estar online para enviar ubicación', 409)

    data = request.get_json(silent=True) or {}
    lat = data.get('lat')
    lng = data.get('lng')

    if lat is None or lng is None:
        from backend.api import fail
        return fail('VALIDATION_ERROR', 'lat y lng son requeridos')

    if not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)):
        from backend.api import fail
        return fail('VALIDATION_ERROR', 'lat/lng deben ser numéricos')
    if lat != lat or lng != lng:
        from backend.api import fail
        return fail('INVALID_COORDINATES', 'Coordenadas inválidas')
    if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
        from backend.api import fail
        return fail('INVALID_COORDINATES', 'Coordenadas fuera de rango')

    profile.lat = lat
    profile.lng = lng
    profile.last_location_update = datetime.now(timezone.utc)
    db.session.commit()

    return ok({'lat': lat, 'lng': lng})


# ── POST /drivers/online ────────────────────────────────────────

@api_bp.route('/drivers/online', methods=['POST'])
@jwt_required
@require_mode('driver')
def api_driver_online():
    """Conductor activa/desactiva modo online."""
    profile = current_user().driver_profile

    data = request.get_json(silent=True) or {}
    is_online = bool(data.get('is_online', False))

    profile.is_online = is_online
    if not is_online:
        profile.is_busy = False
    db.session.commit()

    return ok({'is_online': profile.is_online})


# ── GET /drivers/nearby ─────────────────────────────────────────

@api_bp.route('/drivers/nearby', methods=['GET'])
@jwt_required
def api_drivers_nearby():
    """Conductores online + libres cerca de una posición."""
    lat = request.args.get('lat', type=float)
    lng = request.args.get('lng', type=float)
    radius_km = request.args.get('radius', 10, type=float)
    vehicle_type = request.args.get('vehicle_type', '')

    if lat is None or lng is None:
        from backend.api import fail
        return fail('LOCATION_REQUIRED', 'lat y lng son requeridos')

    if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
        from backend.api import fail
        return fail('INVALID_COORDINATES', 'Coordenadas fuera de rango')

    drivers = _nearby_drivers_query(vehicle_type).limit(100).all()

    nearby = []
    for d in drivers:
        profile = d.driver_profile
        dist = calcular_distancia(lat, lng, profile.lat, profile.lng)
        if dist <= radius_km:
            vinfo = _vehicle_info(d)
            nearby.append({
                'id': d.id,
                'name': d.name,
                'rating_avg': d.rating_avg,
                'rating_count': d.rating_count,
                'vehicle_type': vinfo.get('vehicle_type'),
                'vehicle_info': vinfo,
                'lat': profile.lat,
                'lng': profile.lng,
                'distance_km': round(dist, 2),
                'profile_picture': d.profile_picture,
                'accepted_payments': vinfo.get('accepted_payments', ['efectivo']),
            })

    nearby.sort(key=lambda x: x['distance_km'])

    return ok({'count': len(nearby), 'drivers': nearby})


# ───────────────── Driver Config: accepted payments ─────────────────


@api_bp.route('/driver/accepted-payments', methods=['GET'])
@jwt_required
@require_mode('driver')
def get_accepted_payments():
    """GET /driver/accepted-payments — métodos de pago aceptados."""
    profile = current_user().driver_profile
    accepted = _parse_accepted_payments(profile.accepted_payments)
    return ok({'accepted_payments': accepted})


@api_bp.route('/driver/accepted-payments', methods=['PUT'])
@jwt_required
@require_mode('driver')
def update_accepted_payments():
    """PUT /driver/accepted-payments — actualizar métodos aceptados."""
    profile = current_user().driver_profile
    data = request.get_json(silent=True) or {}
    payments = data.get('accepted_payments', [])

    if not isinstance(payments, list):
        from backend.api import fail
        return fail('VALIDATION_ERROR', 'accepted_payments debe ser una lista')

    valid = [p for p in payments if p in PAYMENT_METHODS]
    if not valid:
        valid = ['efectivo']

    profile.accepted_payments = json.dumps(valid)
    db.session.commit()
    return ok({'accepted_payments': valid})


# ───────────────── Driver Config: QR upload ─────────────────

_UPLOAD_FOLDER = None


def _get_upload_folder():
    global _UPLOAD_FOLDER
    if _UPLOAD_FOLDER is None:
        import os
        _UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static', 'uploads')
    return _UPLOAD_FOLDER


@api_bp.route('/driver/qr', methods=['POST'])
@jwt_required
@require_mode('driver')
def upload_driver_qr():
    """POST /driver/qr — subir imagen de QR de MercadoPago (base64)."""
    profile = current_user().driver_profile
    data = request.get_json(silent=True) or {}
    image_data = data.get('image')
    if not image_data:
        from backend.api import fail
        return fail('VALIDATION_ERROR', 'image requerido (base64)')

    try:
        header = ''
        encoded = image_data
        if ',' in image_data:
            header, encoded = image_data.split(',', 1)
        raw = base64.b64decode(encoded)
        if len(raw) > 5 * 1024 * 1024:
            from backend.api import fail
            return fail('VALIDATION_ERROR', 'Imagen demasiado grande (máx 5MB)')
        ext = 'png' if 'png' in header else 'jpg'
        os.makedirs(_get_upload_folder(), exist_ok=True)
        filename = f'mp_qr_{uuid.uuid4().hex}.{ext}'
        filepath = os.path.join(_get_upload_folder(), filename)
        with open(filepath, 'wb') as f:
            f.write(raw)
        profile.mercadopago_qr = f'/static/uploads/{filename}'
        db.session.commit()
    except Exception:
        db.session.rollback()
        from backend.api import fail
        return fail('VALIDATION_ERROR', 'Imagen base64 inválida')

    return ok({'mercadopago_qr': profile.mercadopago_qr})


# ───────────────── Driver Config: payment methods CRUD ─────────────────


@api_bp.route('/driver/payment-methods', methods=['GET'])
@jwt_required
@require_mode('driver')
def list_payment_methods():
    """GET /driver/payment-methods — listar métodos de cobro del conductor."""
    from backend.models import DriverPaymentMethod
    from backend.extensions import decrypt_details

    profile = current_user().driver_profile
    methods = DriverPaymentMethod.query.filter_by(driver_profile_id=profile.id).all()
    return ok({'methods': [{
        'id': m.id,
        'type': m.type,
        'details': decrypt_details(m.details),
        'is_active': m.is_active,
    } for m in methods]})


@api_bp.route('/driver/payment-methods', methods=['POST'])
@jwt_required
@require_mode('driver')
def create_payment_method():
    """POST /driver/payment-methods — agregar método de cobro."""
    from backend.models import DriverPaymentMethod
    from backend.extensions import encrypt_details

    profile = current_user().driver_profile
    data = request.get_json(silent=True) or {}
    pm_type = data.get('type')
    details = data.get('details', {})

    if pm_type not in ('card', 'mercadopago', 'transfer'):
        from backend.api import fail
        return fail('VALIDATION_ERROR', 'type debe ser card, mercadopago o transfer')

    method = DriverPaymentMethod(
        driver_profile_id=profile.id,
        type=pm_type,
        details=encrypt_details(details),
        is_active=True,
    )
    db.session.add(method)
    db.session.commit()
    return ok({'id': method.id, 'type': method.type, 'is_active': method.is_active}), 201


@api_bp.route('/driver/payment-methods/<int:method_id>', methods=['DELETE'])
@jwt_required
@require_mode('driver')
def delete_payment_method(method_id):
    """DELETE /driver/payment-methods/{id} — eliminar método de cobro."""
    from backend.models import DriverPaymentMethod

    profile = current_user().driver_profile
    method = DriverPaymentMethod.query.get(method_id)
    if not method or method.driver_profile_id != profile.id:
        from backend.api import fail
        return fail('NOT_FOUND', 'Método no encontrado', 404)
    db.session.delete(method)
    db.session.commit()
    return ok({'success': True})


# ───────────────── Geocode ─────────────────


@api_bp.route('/geo/geocode', methods=['GET'])
@jwt_required
@limiter.limit('30 per minute')
def api_geocode():
    """GET /geo/geocode?q= — geocodificación Nominatim (proxy)."""
    import urllib.parse
    import urllib.request

    q = request.args.get('q')
    if not q:
        from backend.api import fail
        return fail('VALIDATION_ERROR', 'q requerido')

    try:
        url = 'https://nominatim.openstreetmap.org/search?' + urllib.parse.urlencode({
            'q': q, 'format': 'json', 'limit': 1, 'addressdetails': 0,
        })
        req = urllib.request.Request(url, headers={'User-Agent': 'VAN/1.0'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            if data:
                return ok({
                    'lat': float(data[0]['lat']),
                    'lng': float(data[0]['lon']),
                    'display_name': data[0].get('display_name', ''),
                })
        from backend.api import fail
        return fail('NOT_FOUND', 'Dirección no encontrada', 404)
    except Exception:
        from backend.api import fail
        return fail('INTERNAL_ERROR', 'Error de geocodificación', 500)


# ───────────────── Reviews ─────────────────


@api_bp.route('/users/<int:user_id>/reviews', methods=['GET'])
@jwt_required
def api_user_reviews(user_id):
    """GET /users/{id}/reviews — reseñas de un usuario (driver o passenger)."""
    from backend.models import Review

    role = request.args.get('role', '')  # 'driver' o 'passenger'
    query = Review.query.filter_by(to_user_id=user_id)
    if role in ('driver', 'passenger'):
        query = query.filter_by(role=role)
    reviews = query.order_by(Review.created_at.desc()).limit(20).all()

    result = []
    for r in reviews:
        from_user = User.query.get(r.from_user_id)
        result.append({
            'id': r.id,
            'rating': r.rating,
            'comment': r.comment,
            'created_at': iso_dt(r.created_at),
            'from_user': from_user.name if from_user else None,
        })
    return ok({'reviews': result})
