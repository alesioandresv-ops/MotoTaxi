"""Catálogo estable de errores de la API v1 (contrato §12).

Reglas:
- `code` es estable en el tiempo: Flutter parsea SOLO `code`, nunca `message`.
- `ERROR_CATALOG` es la única fuente de status HTTP por código.
- HTTP coherente: 400 validación/negocio, 401 auth, 403 permisos, 404,
  409 estado conflictivo, 405 método, 429 rate limit, 500 interno.

Nota de compatibilidad: el código existente usa VALIDATION_ERROR con 400
(no 422); se mantiene 400 para no cambiar el contrato ya emitido por la API.

ApiError vive aquí (único hogar) y se re-exporta desde `backend.api` para no
romper los imports existentes (jwt.py, auth.py).
"""
# code → (status, mensaje por defecto)
ERROR_CATALOG = {
    # ── auth / tokens (401) ──
    'MISSING_TOKEN': (401, 'Token de acceso requerido'),
    'INVALID_TOKEN': (401, 'Token de acceso inválido'),
    'TOKEN_INVALID': (401, 'Token de acceso inválido'),
    'TOKEN_EXPIRED': (401, 'Token de acceso expirado'),
    'TOKEN_REVOKED': (401, 'Token de acceso revocado'),
    'INVALID_REFRESH': (401, 'Token de refresco inválido'),
    'TOKEN_REUSE_DETECTED': (401, 'Sesión comprometida: todos los tokens fueron revocados'),
    'INVALID_CREDENTIALS': (401, 'Credenciales inválidas'),
    'EMAIL_NOT_VERIFIED': (403, 'Debes verificar tu correo electrónico'),
    'EMAIL_TAKEN': (409, 'Correo electrónico ya registrado'),
    'CODE_EXPIRED': (400, 'Código expirado. Solicita uno nuevo.'),
    'INVALID_CODE': (400, 'Código incorrecto'),

    # ── validación / forma (400) ──
    'VALIDATION_ERROR': (400, 'Datos de entrada inválidos'),
    'INVALID_RATING': (400, 'La calificación debe ser un entero entre 1 y 5'),
    'INVALID_AMOUNT': (400, 'Monto inválido'),
    'TOPUP_MIN': (400, 'El monto mínimo de recarga no se cumple'),
    'TOPUP_MAX': (400, 'El monto excede el máximo permitido'),
    'MP_NOT_CONFIGURED': (400, 'Mercado Pago no está configurado'),
    'INVALID_COORDINATES': (400, 'Coordenadas fuera de rango'),
    'LOCATION_REQUIRED': (400, 'Se requiere la ubicación del conductor'),
    'INSUFFICIENT_BALANCE': (400, 'Saldo insuficiente'),
    'INVALID_VEHICLE_TYPE': (400, 'Tipo de vehículo inválido'),
    'INVALID_PAYMENT_METHOD': (400, 'Método de pago inválido'),
    'MERCADOPAGO_CONFIG': (500, 'Mercado Pago no está configurado correctamente'),
    'MERCADOPAGO_API': (502, 'Error al comunicarse con Mercado Pago'),

    # ── no encontrado / método (404 / 405) ──
    'NOT_FOUND': (404, 'Recurso no encontrado'),
    'METHOD_NOT_ALLOWED': (405, 'Método no permitido'),

    # ── permisos / modo (403) ──
    'FORBIDDEN': (403, 'No autorizado para esta operación'),
    'MODE_NOT_ALLOWED': (403, 'Tu modo actual no permite esta operación'),
    'NOT_VERIFIED': (403, 'Conductor no verificado (status distinto de approved)'),
    'COMPANY_INACTIVE': (403, 'La empresa no está activa'),

    # ── estado conflictivo (409) ──
    'ACTIVE_TRIP_EXISTS': (409, 'Ya tienes un viaje activo'),
    'TRIP_NOT_AVAILABLE': (409, 'El viaje ya no está disponible'),
    'INVALID_TRANSITION': (409, 'Transición de estado inválida'),
    'TRIP_FINALIZED': (409, 'El viaje ya está finalizado'),
    'TRIP_NOT_COMPLETED': (409, 'El viaje no está completado'),
    'TRIP_ALREADY_PAID': (409, 'El viaje ya está pagado'),
    'ALREADY_RATED': (409, 'Ya calificaste este viaje'),
    'NOT_ONLINE': (409, 'Debes estar online para esta operación'),
    'MEMBER_EXISTS': (409, 'El usuario ya es miembro de la empresa'),
    'PLAN_LIMIT_REACHED': (409, 'Se alcanzó el límite de miembros del plan'),

    # ── límites / servidor ──
    'RATE_LIMITED': (429, 'Demasiadas peticiones, intenta más tarde'),
    'INTERNAL_ERROR': (500, 'Error interno del servidor'),
}


class ApiError(Exception):
    """Excepción de la API v1 con `code` estable (contrato §12).

    Si no se pasa `status`, se toma del catálogo (única fuente).
    Cualquier code fuera del catálogo cae en INTERNAL_ERROR (500).
    """

    def __init__(self, code, message=None, status=None):
        catalog_status, default_message = ERROR_CATALOG.get(code, ERROR_CATALOG['INTERNAL_ERROR'])
        super().__init__(message or default_message)
        self.code = code
        self.message = message or default_message
        self.status = status or catalog_status


def api_error(code, message=None, status=None):
    """Construye ApiError desde el catálogo (no lo lanza)."""
    return ApiError(code, message=message, status=status)


def raise_api_error(code, message=None, status=None):
    """Lanza ApiError desde el catálogo."""
    raise api_error(code, message=message, status=status)
