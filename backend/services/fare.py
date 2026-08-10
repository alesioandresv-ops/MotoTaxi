"""Tarifas y dinero de VAN.

Regla: todo dinero se manipula como Decimal (Numeric en DB), nunca float.
Invariante de viaje: total_fare = platform_fee + driver_earnings
(verificada además por CHECK chk_trip_money en PostgreSQL).

platform_fee_rate: porcentaje snapshot aplicado al crear el viaje.
  - None → comisión nunca aplicada (viajes históricos / comisión desactivada)
  - 0.05 → 5% de la tarifa base
La comisión NO se cobra hoy: build_fare() la calcula y la persiste,
pero el cobro real es Fase 4 (monetización).
"""
import math
import os
from decimal import Decimal, ROUND_HALF_UP

from backend.models import VEHICLE_TYPES

TARIFAS = {
    'moto': {
        'base': Decimal('3.0'),
        'por_km': Decimal('1.5'),
        'por_min': Decimal('0.25'),
        'minima': Decimal('5.0'),
    },
    'auto': {
        'base': Decimal('4.5'),
        'por_km': Decimal('2.0'),
        'por_min': Decimal('0.30'),
        'minima': Decimal('7.0'),
    },
}


def as_decimal(value):
    """Convierte a Decimal sin romper con None o float. Nunca devuelve float."""
    if value is None:
        return Decimal('0')
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def round_money(value):
    return as_decimal(value).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def default_currency():
    return (os.getenv('DEFAULT_CURRENCY') or 'ARS').strip().upper()[:3]


def commission_rate():
    """PLATFORM_FEE_RATE env: '0.05' → 5%. Vacío/inválido → None (sin comisión)."""
    raw = (os.getenv('PLATFORM_FEE_RATE') or '').strip()
    if not raw:
        return None
    try:
        return Decimal(raw)
    except Exception:
        return None


def calcular_tarifa_real(distance_km, duration_min, vehicle_type='moto'):
    """Tarifa base (sin comisión). Devuelve Decimal."""
    if vehicle_type not in VEHICLE_TYPES:
        vehicle_type = 'moto'
    t = TARIFAS[vehicle_type]
    fare = (
        t['base']
        + as_decimal(distance_km) * t['por_km']
        + as_decimal(duration_min) * t['por_min']
    )
    return max(fare, t['minima']).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def build_fare(distance_km, duration_min, vehicle_type='moto'):
    """Desglose completo para crear un viaje.

    Devuelve {total_fare, platform_fee, platform_fee_rate, driver_earnings, currency}
    garantizando total_fare = platform_fee + driver_earnings.
    """
    total = calcular_tarifa_real(distance_km, duration_min, vehicle_type)
    rate = commission_rate()
    if rate is not None:
        fee = round_money(total * rate)
        if fee > 0:
            return {
                'total_fare': total,
                'platform_fee': fee,
                'platform_fee_rate': rate,
                'driver_earnings': round_money(total - fee),
                'currency': default_currency(),
            }
    return {
        'total_fare': total,
        'platform_fee': Decimal('0'),
        'platform_fee_rate': None,
        'driver_earnings': total,
        'currency': default_currency(),
    }


def calcular_distancia(lat1, lng1, lat2, lng2):
    """Distancia haversine en km (float: solo para geo, no para dinero)."""
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(
        math.radians(lat2)
    ) * math.sin(dlng / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(R * c, 2)


def vehicle_emoji(vtype):
    return '🚗' if vtype == 'auto' else '🛵'


def vehicle_label(vtype):
    return 'Auto' if vtype == 'auto' else 'Moto'
