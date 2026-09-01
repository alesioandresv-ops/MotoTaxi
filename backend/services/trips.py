"""Lógica de negocio de viajes compartida web/API (contrato §15).

Etapa 2: creación de viajes (POST /trips) con idempotencia (§11).
Etapa 3: ciclo de vida completo (§6): accept/reject/start/complete/cancel/
rate/eta + listados. La web (routes.py) conserva su flujo legacy; la API
consume este servicio.

Reglas:
- Dinero SIEMPRE Decimal vía services/fare.py; nunca float en negocio.
- company_id se asigna SOLO por membership activa (D9): el valor que mande
  el cliente se ignora.
- Idempotencia: replay devuelve la respuesta original guardada sin
  re-ejecutar. Trip + ApiIdempotencyKey se persisten en el MISMO commit
  (UNIQUE(user_id, key, method) protege la carrera de requests concurrentes).
- Máquina de estados §6: completed SOLO vía finalize_trip(); cancel libera
  is_busy; stale (>5 min requested) → cancelled_by='system'.
"""
import json
import math
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from backend.models import (
    db, Trip, User, Review, Company, CompanyMember, ApiIdempotencyKey,
    DriverProfile, FavoriteAddress, PAYMENT_METHODS, VEHICLE_TYPES,
    COMPANY_STATUSES_ACTIVE, TRIP_PAYMENT_PENDING, TRIP_PAYMENT_PAID,
    TRIP_STATUSES,
)
from backend.validators import sanitize_input
from backend.services.fare import build_fare, calcular_distancia
from backend.services.wallet import WalletTransferError, wallet_transfer

# NOTA: NO importar backend.api.errors a nivel de módulo — backend/api/__init__
# importa api.trips que importa este módulo → ciclo. ApiError se importa
# tardío dentro de create_trip (mismo patrón que routes.py).

IDEMPOTENCY_TTL_HOURS = 24
FALLBACK_DISTANCE_KM = 1.0
TRIP_ACTIVE_STATUSES = ('requested', 'accepted', 'ongoing')
NOMINATIM_URL = 'https://nominatim.openstreetmap.org/search'


def _geocode_address(address):
    """Nominatim → (lat, lng) | None. Nunca lanza (fallback controlado)."""
    if not address:
        return None
    try:
        url = NOMINATIM_URL + '?' + urllib.parse.urlencode(
            {'q': address, 'format': 'json', 'limit': 1, 'addressdetails': 0},
        )
        req = urllib.request.Request(url, headers={'User-Agent': 'VAN/1.0'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            if data:
                return float(data[0]['lat']), float(data[0]['lon'])
    except Exception:
        return None
    return None


def _opt_float(value):
    """float | None tolerante: coords inválidas se tratan como ausentes."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def resolve_distance_km(payload):
    """Distancia del viaje en km (contrato §5.2).

    Coordenadas completas → haversine. Sin coordenadas → geocode de las
    direcciones (Nominatim); si falla → fallback 1.0 km.
    """
    p_lat = _opt_float(payload.get('pickup_lat'))
    p_lng = _opt_float(payload.get('pickup_lng'))
    d_lat = _opt_float(payload.get('dropoff_lat'))
    d_lng = _opt_float(payload.get('dropoff_lng'))
    if None not in (p_lat, p_lng, d_lat, d_lng):
        return max(1.0, round(calcular_distancia(p_lat, p_lng, d_lat, d_lng), 2))
    origin = _geocode_address(sanitize_input(payload.get('pickup_address')))
    target = _geocode_address(sanitize_input(payload.get('dropoff_address')))
    if origin and target:
        return max(1.0, round(calcular_distancia(origin[0], origin[1], target[0], target[1]), 2))
    return FALLBACK_DISTANCE_KM


def _find_replay(user_id, key):
    """Respuesta guardada vigente → (body_dict, status_code).

    Expirada (>24 h, contrato §11): se borra y devuelve None para que la
    operación se re-ejecute (limpieza perezosa).
    """
    rec = ApiIdempotencyKey.query.filter_by(
        user_id=user_id, key=key, method='POST',
    ).first()
    if rec is None:
        return None
    age_hours = (datetime.utcnow() - rec.created_at).total_seconds() / 3600.0
    if age_hours >= IDEMPOTENCY_TTL_HOURS:
        db.session.delete(rec)
        db.session.commit()
        return None
    return json.loads(rec.response_body), rec.status_code


def _active_company_id(user):
    """Empresa del usuario si tiene membership con empresa trial|active (D9)."""
    row = (
        db.session.query(Company.id)
        .join(CompanyMember, CompanyMember.company_id == Company.id)
        .filter(
            CompanyMember.user_id == user.id,
            Company.status.in_(COMPANY_STATUSES_ACTIVE),
        )
        .first()
    )
    return row[0] if row else None


def create_trip(user, payload, idempotency_key, path='/api/v1/trips'):
    """Crea el viaje o sirve el replay idempotente.

    Devuelve (data_dict, status_code, duplicate). `data` es el contenido
    del envelope ok(data) del endpoint.
    """
    # Import tardío: rompe el ciclo services.trips ↔ backend.api (ver cabecera)
    from backend.api.errors import ApiError

    stored = _find_replay(user.id, idempotency_key)
    if stored is not None:
        body, status_code = stored
        data = dict(body.get('data') or {})
        data['duplicate'] = True  # contrato §5.2.1: replay marca duplicate:true
        return data, status_code, True

    # ── Validaciones (contrato §5.6.1) ──
    pickup = sanitize_input(payload.get('pickup_address'))
    dropoff = sanitize_input(payload.get('dropoff_address'))
    if not pickup or not dropoff:
        raise ApiError('VALIDATION_ERROR', 'pickup_address y dropoff_address son requeridos')

    vehicle_type = payload.get('vehicle_type') or 'moto'
    if vehicle_type not in VEHICLE_TYPES:
        raise ApiError('INVALID_VEHICLE_TYPE')

    payment_method = payload.get('payment_method') or 'efectivo'
    if payment_method not in PAYMENT_METHODS:
        raise ApiError('INVALID_PAYMENT_METHOD')

    active = Trip.query.filter(
        Trip.passenger_id == user.id,
        Trip.status.in_(TRIP_ACTIVE_STATUSES),
    ).first()
    if active:
        raise ApiError('ACTIVE_TRIP_EXISTS')

    # ── Construcción ──
    distance_km = resolve_distance_km(payload)
    fare_fields = build_fare(distance_km, 0, vehicle_type)

    trip = Trip(
        passenger_id=user.id,
        vehicle_type=vehicle_type,
        pickup_address=pickup,
        dropoff_address=dropoff,
        pickup_lat=_opt_float(payload.get('pickup_lat')),
        pickup_lng=_opt_float(payload.get('pickup_lng')),
        dropoff_lat=_opt_float(payload.get('dropoff_lat')),
        dropoff_lng=_opt_float(payload.get('dropoff_lng')),
        distance_km=distance_km,
        total_fare=fare_fields['total_fare'],
        platform_fee=fare_fields['platform_fee'],
        platform_fee_rate=fare_fields['platform_fee_rate'],
        driver_earnings=fare_fields['driver_earnings'],
        currency=fare_fields['currency'],
        status='requested',
        payment_method=payment_method,
        company_id=_active_company_id(user),
        idempotency_key=idempotency_key,
    )
    db.session.add(trip)
    db.session.flush()  # trip.id disponible para serializar antes del commit único

    from backend.api.serializers import serialize_trip  # import tardío evita ciclo
    data = {'trip': serialize_trip(trip), 'duplicate': False}
    db.session.add(ApiIdempotencyKey(
        user_id=user.id,
        key=idempotency_key,
        method='POST',
        path=path,
        status_code=201,
        response_body=json.dumps({'success': True, 'data': data}),
    ))
    try:
        db.session.commit()
    except IntegrityError:
        # Carrera: otro request creó el mismo (user, key) → servir su respuesta.
        db.session.rollback()
        stored = _find_replay(user.id, idempotency_key)
        if stored is not None:
            body, status_code = stored
            data = dict(body.get('data') or {})
            data['duplicate'] = True
            return data, status_code, True
        raise
    return data, 201, False


# ═══════════════════════════════════════════════════════════════
# ─── Finalización con cobro (web; base del contrato Etapa 3) ───
# ═══════════════════════════════════════════════════════════════

class TripFinalizeError(Exception):
    """Rechazo de la finalización con código estable para la capa HTTP."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message

    def __repr__(self):
        return f'TripFinalizeError({self.code!r})'


def _duration_min(started_at, completed_at):
    """Minutos transcurridos (mínimo 1) o None si no hay marca de inicio."""
    if not started_at:
        return None
    s = started_at.replace(tzinfo=None) if started_at.tzinfo else started_at
    c = completed_at.replace(tzinfo=None) if completed_at.tzinfo else completed_at
    return max(1, int((c - s).total_seconds() / 60))


def _finalize_summary(trip):
    return {
        'trip_id': trip.id,
        'status': trip.status,
        'payment_status': trip.payment_status,
        'payment_method_collected': trip.payment_method_collected,
        'total_fare': trip.total_fare,
        'driver_earnings': trip.driver_earnings,
        'currency': trip.currency,
    }


def upsert_favorite_route(trip):
    """Ruta frecuente del pasajero. Best-effort con commit propio: un fallo
    aquí NUNCA debe afectar al viaje ya cobrado."""
    try:
        fav = FavoriteAddress.query.filter_by(
            user_id=trip.passenger_id,
            pickup_address=trip.pickup_address,
            dropoff_address=trip.dropoff_address,
        ).first()
        if fav:
            fav.count += 1
        else:
            count = FavoriteAddress.query.filter_by(user_id=trip.passenger_id).count()
            fav = FavoriteAddress(
                user_id=trip.passenger_id,
                name=f'Ruta Frecuente {count + 1}',
                pickup_address=trip.pickup_address,
                dropoff_address=trip.dropoff_address,
                count=1,
            )
            db.session.add(fav)
        db.session.commit()
    except Exception:
        db.session.rollback()


def finalize_trip(trip, driver_user, payment_method):
    """Cobra y finaliza el viaje — ÚNICA vía hacia `completed`.

    Reglas (aprobadas por producto):
    - Solo el conductor asignado y solo desde `ongoing`. Retry idempotente:
      si ya está completed+paid devuelve el resumen SIN re-cobrar.
    - Tarifa final recalculada con la duración real (desde started_at).
    - Cobro según método final elegido por el conductor en el momento:
      * billetera → wallet_transfer atómica (pasajero debita el TOTAL,
        conductor acredita driver_earnings; la diferencia es comisión VAN,
        aún no cobrada — Fase 4). Sin saldo suficiente NO se completa el
        viaje: PAYMENT_INSUFFICIENT_BALANCE.
      * efectivo/mercadopago/tarjeta/transferencia → pago físico fuera de
        la app que el conductor atesta al confirmar.
    - Libera al conductor (is_busy=False).

    NO commitea: el caller commitea todo-o-nada (cobro + estado del viaje).
    Ante TripFinalizeError el caller debe hacer rollback para descartar los
    cambios ya staged (ej: desglose de tarifa recalculado).
    """
    if trip.driver_id != driver_user.id:
        raise TripFinalizeError('FORBIDDEN', 'No puedes finalizar este viaje')

    if (
        trip.status == 'completed'
        and trip.payment_status == TRIP_PAYMENT_PAID
    ):
        return _finalize_summary(trip)  # retry idempotente: ya cobrado

    if trip.status != 'ongoing':
        raise TripFinalizeError(
            'INVALID_STATUS',
            f'El viaje está en estado {trip.status}, no se puede finalizar',
        )

    if payment_method not in PAYMENT_METHODS:
        raise TripFinalizeError('INVALID_METHOD', 'Método de pago inválido')

    completed_at = datetime.utcnow()
    duration_min = _duration_min(trip.started_at, completed_at)

    fare_fields = None
    fare_total = trip.total_fare
    earnings = trip.driver_earnings
    if duration_min is not None:
        fare_fields = build_fare(float(trip.distance_km or 0), duration_min, trip.vehicle_type)
        fare_total = fare_fields['total_fare']
        earnings = fare_fields['driver_earnings']

    if payment_method == 'billetera':
        try:
            wallet_transfer(
                trip.passenger_id, driver_user.id, fare_total,
                credit_amount=earnings,
                tx_type='trip_payment', trip_id=trip.id,
                description=f'Viaje #{trip.id}',
            )
        except WalletTransferError as exc:
            if exc.code == 'INSUFFICIENT_BALANCE':
                raise TripFinalizeError(
                    'PAYMENT_INSUFFICIENT_BALANCE',
                    'Saldo insuficiente del pasajero: elegí otro método de pago',
                )
            raise TripFinalizeError(exc.code, exc.message)

    trip.status = 'completed'
    trip.completed_at = completed_at
    trip.duration_min = duration_min
    if fare_fields is not None:
        trip.total_fare = fare_fields['total_fare']
        trip.platform_fee = fare_fields['platform_fee']
        trip.platform_fee_rate = fare_fields['platform_fee_rate']
        trip.driver_earnings = fare_fields['driver_earnings']
        trip.currency = fare_fields['currency']
    trip.payment_status = TRIP_PAYMENT_PAID
    trip.payment_method_collected = payment_method
    trip.paid_at = completed_at

    profile = (
        db.session.query(DriverProfile)
        .filter_by(user_id=driver_user.id)
        .with_for_update()
        .first()
    )
    if profile:
        profile.is_busy = False

    return _finalize_summary(trip)


# ─────────────────── Etapa 3: ciclo de vida (contrato §6) ───────────────────

STALE_TRIP_MINUTES = 5
AVAILABLE_SCAN_LIMIT = 200
DEFAULT_RADIUS_KM = 10.0
AVG_SPEED_KMH = 30


class TripServiceError(Exception):
    """Rechazo de una acción del ciclo de vida con code estable (§12).

    Los codes coinciden 1:1 con el catálogo de ApiError para que la capa
    HTTP mapee directo. La web puede reutilizar estas funciones capturando
    esta excepción.
    """

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message

    def __repr__(self):
        return f'TripServiceError({self.code!r})'


def _err(code, message):
    raise TripServiceError(code, message)


def cancel_stale_trips():
    """Viajes requested con más de STALE_TRIP_MINUTES → cancelled(system).

    Movido desde routes.py (Etapa 3): única implementación compartida por
    web y API. Se invoca antes de listar disponibles / dashboard.
    """
    timeout = datetime.utcnow() - timedelta(minutes=STALE_TRIP_MINUTES)
    stale = Trip.query.filter(
        Trip.status == 'requested',
        Trip.requested_at < timeout,
    ).all()
    for t in stale:
        t.status = 'cancelled'
        t.cancelled_by = 'system'
    if stale:
        db.session.commit()
    return len(stale)


def participant_role(trip, user_id):
    "'passenger' | 'driver' según participación en el viaje; None si no participa."
    if trip.passenger_id == user_id:
        return 'passenger'
    if trip.driver_id == user_id:
        return 'driver'
    return None


def get_trip_checked(trip_id, user_id):
    """Trip por id verificando participación; si no → NOT_FOUND | FORBIDDEN."""
    trip = Trip.query.get(trip_id)
    if trip is None:
        _err('NOT_FOUND', 'Viaje no encontrado')
    if participant_role(trip, user_id) is None:
        _err('FORBIDDEN', 'No participas de este viaje')
    return trip


def list_trips(user, role, status=None, page=1, limit=20):
    """Viajes propios paginados (contrato §5.2.3). Orden: requested DESC."""
    if role not in ('passenger', 'driver'):
        _err('VALIDATION_ERROR', "role debe ser 'passenger' o 'driver'")
    if status is not None and status not in TRIP_STATUSES:
        _err('VALIDATION_ERROR', f'status debe ser uno de: {", ".join(TRIP_STATUSES)}')
    column = Trip.passenger_id if role == 'passenger' else Trip.driver_id
    query = Trip.query.filter(column == user.id).order_by(
        Trip.requested_at.desc(), Trip.id.desc(),
    )
    if status:
        query = query.filter(Trip.status == status)
    total = query.count()
    pages = math.ceil(total / limit) if total else 0
    items = query.offset((page - 1) * limit).limit(limit).all()
    return {
        'items': items,
        'pagination': {'page': page, 'limit': limit, 'total': total, 'pages': pages},
    }


def available_trips(profile, lat=None, lng=None, radius_km=DEFAULT_RADIUS_KM,
                    vehicle_type='', page=1, limit=20):
    """Viajes requested cercanos a la posición del conductor (§5.2.4).

    Posición: params lat/lng; si faltan usa la persistida en el perfil;
    sin ninguna → LOCATION_REQUIRED. Distancia al pickup, orden por
    cercanía. Paginación manual (el orden es por distancia calculada).
    """
    lat = lat if lat is not None else profile.lat
    lng = lng if lng is not None else profile.lng
    if lat is None or lng is None:
        _err('LOCATION_REQUIRED', 'Envía tu ubicación (lat/lng) para ver viajes')

    trips = (
        Trip.query.filter_by(status='requested')
        .order_by(Trip.requested_at.asc())
        .limit(AVAILABLE_SCAN_LIMIT)
        .all()
    )
    scored = []
    for t in trips:
        if vehicle_type and t.vehicle_type != vehicle_type:
            continue
        if t.pickup_lat is None or t.pickup_lng is None:
            continue
        dist = calcular_distancia(lat, lng, t.pickup_lat, t.pickup_lng)
        if dist > radius_km:
            continue
        scored.append((dist, t))
    scored.sort(key=lambda pair: pair[0])

    total = len(scored)
    pages = math.ceil(total / limit) if total else 0
    start = (page - 1) * limit
    return {
        'items': [{'trip': t, 'distance_km': d} for d, t in scored[start:start + limit]],
        'pagination': {'page': page, 'limit': limit, 'total': total, 'pages': pages},
        'driver_lat': lat,
        'driver_lng': lng,
    }


def accept_trip(driver_user, trip_id):
    """Conductor toma un viaje requested (§6). Commitea.

    Carrera: claim atómico UPDATE ... WHERE status='requested'; el perdedor
    recibe TRIP_NOT_AVAILABLE. Checks previos: online → libre.
    """
    profile = DriverProfile.query.filter_by(user_id=driver_user.id).first()
    if not profile or not profile.is_online:
        _err('NOT_ONLINE', 'Debes estar online para aceptar viajes')
    if profile.is_busy:
        _err('TRIP_NOT_AVAILABLE', 'Ya tienes un viaje asignado')

    trip = Trip.query.get(trip_id)
    if trip is None:
        _err('NOT_FOUND', 'Viaje no encontrado')

    result = db.session.execute(
        update(Trip)
        .where(Trip.id == trip.id, Trip.status == 'requested')
        .values(driver_id=driver_user.id, status='accepted')
    )
    if result.rowcount == 0:
        _err('TRIP_NOT_AVAILABLE', 'El viaje ya no está disponible')

    locked = (
        DriverProfile.query.filter_by(user_id=driver_user.id).with_for_update().first()
    )
    locked.is_busy = True
    db.session.commit()
    return Trip.query.get(trip_id)


def start_trip(trip, driver_user):
    """accepted → ongoing con started_at (solo conductor asignado). NO commitea."""
    if trip.driver_id != driver_user.id:
        _err('FORBIDDEN', 'No puedes iniciar este viaje')
    if trip.status != 'accepted':
        _err(
            'INVALID_TRANSITION',
            f'El viaje está en estado {trip.status}; solo accepted puede iniciarse',
        )
    trip.status = 'ongoing'
    trip.started_at = datetime.utcnow()
    return trip


def cancel_trip(trip, user, reason=''):
    """Cancelación por pasajero dueño o conductor asignado (§6). Commitea.

    Estados completed/cancelled → TRIP_FINALIZED. Libera is_busy del
    conductor en el MISMO commit. `reason` se sanitiza pero no se persiste
    (sin columna; D8 deja preparado cancelled_by para sanciones futuras).
    """
    role = participant_role(trip, user.id)
    if role is None:
        _err('FORBIDDEN', 'No participas de este viaje')
    if trip.status in ('completed', 'cancelled'):
        _err('TRIP_FINALIZED', f'El viaje ya está {trip.status}')
    sanitize_input(reason or '')  # validación de forma; aún sin columna destino

    trip.status = 'cancelled'
    trip.cancelled_by = role
    if trip.driver_id:
        profile = DriverProfile.query.filter_by(user_id=trip.driver_id).first()
        if profile:
            profile.is_busy = False
    db.session.commit()
    return trip


def rate_trip(trip, user, rating, comment=''):
    """Review cruzada post-completed, 1 vez por rol (§6). NO commitea.

    role en Review = lado de quien califica ('passenger'|'driver'), igual
    que la web (paridad con dashboards existentes).
    """
    if not isinstance(rating, int) or isinstance(rating, bool) or not 1 <= rating <= 5:
        _err('INVALID_RATING', 'La calificación debe ser un entero entre 1 y 5')
    role = participant_role(trip, user.id)
    if role is None:
        _err('FORBIDDEN', 'No participas de este viaje')
    if trip.status != 'completed':
        _err('TRIP_NOT_COMPLETED', 'Solo puedes calificar viajes completados')

    existing = Review.query.filter_by(
        trip_id=trip.id, from_user_id=user.id, role=role,
    ).first()
    if existing:
        _err('ALREADY_RATED', 'Ya calificaste este viaje')

    target_id = trip.driver_id if role == 'passenger' else trip.passenger_id
    review = Review(
        trip_id=trip.id,
        from_user_id=user.id,
        to_user_id=target_id,
        rating=rating,
        comment=sanitize_input(comment or ''),
        role=role,
    )
    db.session.add(review)

    target = User.query.get(target_id)
    if target:
        reviews = Review.query.filter_by(to_user_id=target_id).all()
        target.rating_avg = round(sum(r.rating for r in reviews) / len(reviews), 1)
        target.rating_count = len(reviews)
    return review


def trip_eta(trip):
    """ETA del conductor asignado hacia el pickup (§5.2.5).

    Sin conductor o sin posición → valores None (la app muestra "calculando").
    """
    profile = (
        trip.driver.driver_profile if trip.driver and trip.driver.driver_profile else None
    )
    if not profile or profile.lat is None or profile.lng is None:
        return {'eta_min': None, 'distance_km': None,
                'driver_lat': None, 'driver_lng': None}
    dist = calcular_distancia(
        profile.lat, profile.lng,
        trip.pickup_lat or 0, trip.pickup_lng or 0,
    )
    eta_min = max(1, int((dist / AVG_SPEED_KMH) * 60)) if AVG_SPEED_KMH > 0 else None
    return {
        'eta_min': eta_min,
        'distance_km': dist,
        'driver_lat': profile.lat,
        'driver_lng': profile.lng,
    }
