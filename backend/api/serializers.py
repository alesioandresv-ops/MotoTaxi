"""Serializers reutilizables de la API v1 (Etapa 0).

Reglas del contrato:
- Dinero: SIEMPRE string decimal en JSON (ej. "14.80"), nunca float.
  El backend opera en Decimal (`services/fare.py`); aquí solo se serializa.
- Fechas: ISO 8601 UTC ("2026-08-10T14:00:00Z").
- Los payloads de negocio (trip, wallet, company…) se construyen en las
  etapas siguientes reutilizando estas funciones.
"""
from datetime import timezone

from backend.models import User
from backend.services.fare import as_decimal, round_money


def money_str(value):
    """Decimal → string con 2 decimales ("14.80"). None → "0.00"."""
    return format(round_money(as_decimal(value)), 'f')


def iso_dt(dt):
    """datetime → "YYYY-MM-DDTHH:MM:SSZ" (UTC). None → None."""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime('%Y-%m-%dT%H:%M:%SZ')


def public_user(user):
    """Perfil público mínimo de un user (contrato §5.1: passenger/driver)."""
    if user is None:
        return None
    return {
        'id': user.id,
        'name': user.name,
        'rating_avg': float(user.rating_avg or 0),
        'rating_count': user.rating_count or 0,
        'profile_picture': user.profile_picture,
    }


def public_driver(user):
    """Perfil público de conductor (contrato §4.4: /drivers/nearby)."""
    if user is None:
        return None
    profile = user.driver_profile
    payload = public_user(user)
    payload['vehicle_type'] = profile.active_vehicle.type if profile and profile.active_vehicle else None
    payload['vehicle_info'] = None
    payload['lat'] = profile.lat if profile else None
    payload['lng'] = profile.lng if profile else None
    payload['distance_km'] = None
    payload['accepted_payments'] = []
    payload['phone'] = user.phone or ''
    return payload


def _rate_str(rate):
    """Numeric(5,4) → "0.05" (sin ceros de escala). None → None."""
    if rate is None:
        return None
    return format(as_decimal(rate).normalize(), 'f')


def _fare_breakdown(trip):
    """Desglose canónico de 5 campos (contrato §5.1)."""
    return {
        'total_fare': money_str(trip.total_fare),
        'platform_fee': money_str(trip.platform_fee),
        'platform_fee_rate': _rate_str(trip.platform_fee_rate),
        'driver_earnings': money_str(trip.driver_earnings),
        'currency': trip.currency,
    }


def serialize_trip(trip):
    """Payload canónico del viaje (contrato §5.1).

    - fare.estimate: snapshot persistido (al crear, duration=0).
    - fare.final: solo cuando status == completed (la DB sobreescribe los
      campos al completar, por lo que ambos bloques muestran el desglose final).
    - driver: solo cuando el viaje tiene conductor asignado.
    - wallet.charged: true solo si complete movió saldo (etapa 4).
    """
    completed = trip.status == 'completed'
    breakdown = _fare_breakdown(trip)

    charged_txns = [
        t for t in trip.wallet_transactions
        if t.type == 'trip_payment' and t.status == 'completed'
    ]
    passenger_txn = next((t.id for t in charged_txns if t.user_id == trip.passenger_id), None)
    driver_txn = next(
        (t.id for t in charged_txns if trip.driver_id and t.user_id == trip.driver_id),
        None,
    )

    driver_payload = None
    if trip.driver is not None:
        driver_payload = public_driver(trip.driver)
        vehicle = (
            trip.driver.driver_profile.active_vehicle
            if trip.driver.driver_profile else None
        )
        if vehicle:
            driver_payload['vehicle_info'] = {
                'placa': vehicle.placa,
                'marca': vehicle.marca,
                'modelo': vehicle.modelo,
            }

    return {
        'id': trip.id,
        'status': trip.status,
        'vehicle_type': trip.vehicle_type,
        'pickup_address': trip.pickup_address,
        'dropoff_address': trip.dropoff_address,
        'pickup_lat': trip.pickup_lat,
        'pickup_lng': trip.pickup_lng,
        'dropoff_lat': trip.dropoff_lat,
        'dropoff_lng': trip.dropoff_lng,
        'distance_km': float(trip.distance_km) if trip.distance_km is not None else None,
        'duration_min': trip.duration_min,
        'payment_method': trip.payment_method,
        'company_id': trip.company_id,
        'requested_at': iso_dt(trip.requested_at),
        'started_at': iso_dt(trip.started_at),
        'completed_at': iso_dt(trip.completed_at),
        'cancelled_by': trip.cancelled_by,
        'fare': {
            'estimate': breakdown,
            'final': breakdown if completed else None,
        },
        'wallet': {
            'charged': bool(charged_txns),
            'passenger_txn_id': passenger_txn,
            'driver_txn_id': driver_txn,
        },
        'passenger': public_user(trip.passenger),
        'driver': driver_payload,
    }


def serialize_available_trip(trip, distance_km):
    """Item de GET /trips/available (contrato §5.2.4): resumen ligero del
    viaje requested + distancia del conductor al pickup."""
    return {
        'id': trip.id,
        'pickup_address': trip.pickup_address,
        'dropoff_address': trip.dropoff_address,
        'pickup_lat': trip.pickup_lat,
        'pickup_lng': trip.pickup_lng,
        'vehicle_type': trip.vehicle_type,
        'payment_method': trip.payment_method,
        'fare': {'estimate': _fare_breakdown(trip)},
        'distance_km': round(distance_km, 2),
        'requested_at': iso_dt(trip.requested_at),
    }
