"""Endpoints de viajes de la API v1 (/api/v1/trips) — Etapas 2 y 3.

Etapa 2: POST /trips (creación, idempotencia §11).
Etapa 3: ciclo de vida completo (contrato §§4.2, 5.2, 6): detalle, listado,
disponibles, accept/reject/start/complete/cancel/rate/eta.

Toda la lógica vive en backend/services/trips.py (contrato §15); aquí solo
se validan formas de entrada, se aplican guards (JWT + modo) y se mapean
TripServiceError → ApiError.
"""
from flask import current_app, request

from backend.api import api_bp, ok
from backend.api.errors import ApiError
from backend.api.jwt import jwt_required, current_user
from backend.api.decorators import require_mode
from backend.api.pagination import pagination_args
from backend.api.serializers import serialize_trip, serialize_available_trip, money_str
from backend.extensions import limiter
from backend.models import db, Trip
from backend.services.trips import (
    DEFAULT_RADIUS_KM,
    TripFinalizeError,
    TripServiceError,
    accept_trip,
    available_trips,
    cancel_stale_trips,
    cancel_trip,
    create_trip,
    finalize_trip,
    get_trip_checked,
    list_trips,
    rate_trip,
    start_trip,
    trip_eta,
)
from backend.validators import sanitize_input

MAX_KEY_LEN = 255

# Mapeo códigos internos de finalize_trip → catálogo estable §12:
_FINALIZE_CODE_MAP = {
    'INVALID_STATUS': 'INVALID_TRANSITION',
    'INVALID_METHOD': 'INVALID_PAYMENT_METHOD',
    'PAYMENT_INSUFFICIENT_BALANCE': 'INSUFFICIENT_BALANCE',
}


def _trip_or_404(trip_id):
    trip = Trip.query.get(trip_id)
    if trip is None:
        raise ApiError('NOT_FOUND', 'Viaje no encontrado')
    return trip


def _run_service(fn, *args, **kwargs):
    """Ejecuta un servicio del ciclo de vida mapeando su error a ApiError."""
    try:
        return fn(*args, **kwargs)
    except TripServiceError as exc:
        raise ApiError(exc.code, exc.message)


@api_bp.route('/trips', methods=['POST'])
@limiter.limit('30 per minute')
@jwt_required
@require_mode('passenger')
def create_trip_endpoint():
    """POST /trips — crea un viaje (201) o sirve el replay (200)."""
    user = current_user()
    payload = request.get_json(silent=True) or {}

    # Header obligatorio; body idempotency_key deprecated (contrato §11):
    # aceptado con warning si viene; el header gana siempre.
    key = (request.headers.get('Idempotency-Key') or '').strip()
    body_key = str(payload.get('idempotency_key') or '').strip()
    if body_key:
        if key and body_key != key:
            current_app.logger.warning(
                'POST /trips: idempotency_key del body difiere del header; se usa el header'
            )
        elif not key:
            current_app.logger.warning(
                'POST /trips: idempotency_key en body (deprecated); usar header Idempotency-Key'
            )
            key = body_key
    if not key:
        raise ApiError('VALIDATION_ERROR', 'Header Idempotency-Key es obligatorio')
    if len(key) > MAX_KEY_LEN:
        raise ApiError('VALIDATION_ERROR', 'Idempotency-Key demasiado larga (max 255)')

    data, _status, duplicate = create_trip(user, payload, key, path=request.path)
    # Contrato §5.2: replay idempotente → 200 con duplicate:true.
    return ok(data), (200 if duplicate else 201)


# ───────────────────────── Etapa 3: ciclo de vida ─────────────────────────

@api_bp.route('/trips/<int:trip_id>', methods=['GET'])
@jwt_required
def get_trip_endpoint(trip_id):
    """GET /trips/{id} — payload canónico §5.1; solo participantes."""
    trip = _run_service(get_trip_checked, trip_id, current_user().id)
    return ok({'trip': serialize_trip(trip)})


@api_bp.route('/trips/<int:trip_id>/status', methods=['GET'])
@jwt_required
def trip_status_endpoint(trip_id):
    """GET /trips/{id}/status — payload ligero para polling cada 5s.

    Devuelve estado del viaje + ubicación del conductor en tiempo real.
    Solo participantes (passenger o driver asignado).
    """
    trip = _run_service(get_trip_checked, trip_id, current_user().id)

    driver_info = None
    if trip.driver and trip.driver.driver_profile:
        profile = trip.driver.driver_profile
        vehicle = profile.active_vehicle
        vehicle_info = None
        if vehicle:
            vehicle_info = {
                'type': vehicle.type,
                'placa': vehicle.placa,
                'marca': vehicle.marca,
                'modelo': vehicle.modelo,
            }
        driver_info = {
            'id': trip.driver.id,
            'name': trip.driver.name,
            'phone': trip.driver.phone,
            'profile_picture': trip.driver.profile_picture,
            'rating_avg': float(trip.driver.rating_avg or 0),
            'rating_count': trip.driver.rating_count or 0,
            'lat': profile.lat,
            'lng': profile.lng,
            'vehicle_info': vehicle_info,
        }

    return ok({
        'id': trip.id,
        'status': trip.status,
        'vehicle_type': trip.vehicle_type,
        'pickup_address': trip.pickup_address,
        'dropoff_address': trip.dropoff_address,
        'pickup_lat': trip.pickup_lat,
        'pickup_lng': trip.pickup_lng,
        'dropoff_lat': trip.dropoff_lat,
        'dropoff_lng': trip.dropoff_lng,
        'fare': money_str(trip.total_fare),
        'distance_km': float(trip.distance_km) if trip.distance_km is not None else None,
        'payment_method': trip.payment_method,
        'payment_status': trip.payment_status,
        'payment_method_collected': trip.payment_method_collected,
        'driver': driver_info,
    })


@api_bp.route('/trips', methods=['GET'])
@jwt_required
def list_trips_endpoint():
    """GET /trips?role=passenger|driver&status=&page=&limit= — propios."""
    user = current_user()
    role = (request.args.get('role') or 'passenger').strip()
    status = (request.args.get('status') or '').strip() or None
    page, limit = pagination_args(request.args)
    result = _run_service(list_trips, user, role, status=status, page=page, limit=limit)
    result['items'] = [serialize_trip(t) for t in result['items']]
    return ok(result)


@api_bp.route('/trips/available', methods=['GET'])
@limiter.limit('60 per minute')
@jwt_required
@require_mode('driver')
def available_trips_endpoint():
    """GET /trips/available — requested cercanos al conductor (§5.2.4).

    lat/lng del query tienen prioridad; si faltan se usa la posición
    persistida del perfil. Expira primero los requested viejos (>5 min).
    """
    profile = current_user().driver_profile
    lat = request.args.get('lat', type=float)
    lng = request.args.get('lng', type=float)
    radius = request.args.get('radius', type=float)
    vehicle_type = (request.args.get('vehicle_type') or '').strip()
    page, limit = pagination_args(request.args)

    cancel_stale_trips()
    try:
        result = available_trips(
            profile, lat=lat, lng=lng,
            radius_km=radius if radius and radius > 0 else DEFAULT_RADIUS_KM,
            vehicle_type=vehicle_type, page=page, limit=limit,
        )
    except TripServiceError as exc:
        raise ApiError(exc.code, exc.message)

    items = [
        serialize_available_trip(it['trip'], it['distance_km'])
        for it in result['items']
    ]
    return ok({
        'items': items,
        'pagination': result['pagination'],
        'driver_lat': result['driver_lat'],
        'driver_lng': result['driver_lng'],
    })


@api_bp.route('/trips/<int:trip_id>/accept', methods=['POST'])
@limiter.limit('30 per minute')
@jwt_required
@require_mode('driver')
def accept_trip_endpoint(trip_id):
    """POST /trips/{id}/accept — claim atómico (§6). Perdedor: TRIP_NOT_AVAILABLE."""
    trip = _run_service(accept_trip, current_user(), trip_id)
    return ok({'trip': serialize_trip(trip)})


@api_bp.route('/trips/<int:trip_id>/reject', methods=['POST'])
@jwt_required
@require_mode('driver')
def reject_trip_endpoint(trip_id):
    """POST /trips/{id}/reject — sin efecto sobre el viaje (solo debe existir)."""
    _trip_or_404(trip_id)
    return ok({'ok': True})


@api_bp.route('/trips/<int:trip_id>/start', methods=['POST'])
@jwt_required
@require_mode('driver')
def start_trip_endpoint(trip_id):
    """POST /trips/{id}/start — accepted → ongoing (conductor asignado)."""
    user = current_user()
    trip = _trip_or_404(trip_id)
    _run_service(start_trip, trip, user)
    db.session.commit()
    return ok({'trip': serialize_trip(trip)})


@api_bp.route('/trips/<int:trip_id>/complete', methods=['POST'])
@jwt_required
@require_mode('driver')
def complete_trip_endpoint(trip_id):
    """POST /trips/{id}/complete — ongoing → completed vía finalize_trip().

    Body {} o {"method": ...}: el conductor confirma el método real de pago
    (default: el elegido por el pasajero — misma regla que la web).
    Billetera sin saldo → INSUFFICIENT_BALANCE y el viaje sigue ongoing.
    """
    user = current_user()
    trip = _trip_or_404(trip_id)
    payload = request.get_json(silent=True) or {}
    method = sanitize_input(str(payload.get('method') or '')).strip() or trip.payment_method

    try:
        finalize_trip(trip, user, method)
        db.session.commit()
    except TripFinalizeError as exc:
        db.session.rollback()
        raise ApiError(_FINALIZE_CODE_MAP.get(exc.code, exc.code), exc.message)
    return ok({'trip': serialize_trip(trip)})


@api_bp.route('/trips/<int:trip_id>/cancel', methods=['POST'])
@limiter.limit('20 per minute')
@jwt_required
def cancel_trip_endpoint(trip_id):
    """POST /trips/{id}/cancel — pasajero dueño o conductor asignado (§6)."""
    trip = _trip_or_404(trip_id)
    payload = request.get_json(silent=True) or {}
    reason = payload.get('reason')
    if reason is not None and not isinstance(reason, str):
        raise ApiError('VALIDATION_ERROR', 'reason debe ser texto')
    _run_service(cancel_trip, trip, current_user(), reason or '')
    return ok({'trip': serialize_trip(trip)})


@api_bp.route('/trips/<int:trip_id>/rate', methods=['POST'])
@limiter.limit('10 per minute')
@jwt_required
def rate_trip_endpoint(trip_id):
    """POST /trips/{id}/rate — {rating: 1-5, comment?}; 1 vez por rol."""
    trip = _trip_or_404(trip_id)
    payload = request.get_json(silent=True) or {}
    rating = payload.get('rating')
    comment = payload.get('comment')
    if comment is not None and not isinstance(comment, str):
        raise ApiError('VALIDATION_ERROR', 'comment debe ser texto')
    review = _run_service(rate_trip, trip, current_user(), rating, comment or '')
    db.session.commit()
    return ok({'ok': True})


@api_bp.route('/trips/<int:trip_id>/eta', methods=['GET'])
@jwt_required
def trip_eta_endpoint(trip_id):
    """GET /trips/{id}/eta — ETA del conductor hacia el pickup."""
    trip = _run_service(get_trip_checked, trip_id, current_user().id)
    return ok(trip_eta(trip))
