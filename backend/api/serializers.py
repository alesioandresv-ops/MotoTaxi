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
