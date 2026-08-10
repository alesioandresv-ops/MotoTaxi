"""Paginación común de la API v1 (contrato §13).

- `?page=1&limit=20` (default page=1, limit=20; máx 100 con clamp).
- Respuesta canónica: `{"items": [...], "pagination": {"page": 1,
  "limit": 20, "total": 34, "pages": 2}}`.
- Orden estable (responsabilidad del caller): `created_at DESC, id DESC`.
"""
import math

from backend.api.errors import ApiError

DEFAULT_PAGE = 1
DEFAULT_LIMIT = 20
MAX_LIMIT = 100

MIN_PAGE = 1
MIN_LIMIT = 1


def pagination_args(args=None):
    """Parsea y valida `page`/`limit` desde los query args.

    Reglas:
    - ausentes → defaults (1, 20)
    - `page` debe ser entero ≥ 1; si no → VALIDATION_ERROR (400)
    - `limit` debe ser entero ≥ 1; `limit > MAX_LIMIT` se clampa a MAX_LIMIT
    Devuelve (page, limit).
    """
    args = args or {}

    def _int(value, name, default, minimum, clamp_max=None):
        if value is None or str(value).strip() == '':
            return default
        try:
            parsed = int(str(value).strip())
        except (TypeError, ValueError):
            raise ApiError('VALIDATION_ERROR', f'{name} debe ser un entero', 400)
        if parsed < minimum:
            raise ApiError('VALIDATION_ERROR', f'{name} debe ser >= {minimum}', 400)
        if clamp_max is not None and parsed > clamp_max:
            return clamp_max
        return parsed

    page = _int(args.get('page'), 'page', DEFAULT_PAGE, MIN_PAGE)
    limit = _int(args.get('limit'), 'limit', DEFAULT_LIMIT, MIN_LIMIT, clamp_max=MAX_LIMIT)
    return page, limit


def paginate(query, page=DEFAULT_PAGE, limit=DEFAULT_LIMIT):
    """Aplica paginación a un query SQLAlchemy.

    Devuelve `{"items": [...], "pagination": {"page", "limit", "total",
    "pages"}}`. El caller construye el query con orden estable
    (`created_at DESC, id DESC`).
    """
    total = query.count()
    pages = math.ceil(total / limit) if total else 0
    items = query.offset((page - 1) * limit).limit(limit).all()
    return {
        'items': items,
        'pagination': {
            'page': page,
            'limit': limit,
            'total': total,
            'pages': pages,
        },
    }
