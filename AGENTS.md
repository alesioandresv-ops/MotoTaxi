# MotoTaxi

Flask + MySQL app de solicitud de mototaxis.

## Ramp up

```bash
# Tests (SQLite in-memory, no MySQL needed)
python -m pytest tests/ -v

# Setup + run server full-stack
# 1. Editar backend/.env (copiar de .env.example)
# 2. mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS mototaxi"
# 3. python backend/app.py          # migra + arranca en :5000
# 4. python create_demo_users.py    # pasajero@demo.com / 1234, conductor@demo.com / 1234

# Migrar sin servidor
python migrate.py   # pymysql directo (MySQL)
python setup.py     # igual pero verifica conexión primero

# Producción (Railway/Docker)
# start.sh → migrate.py → waitress-serve backend.app:app
```

## Arquitectura

- `backend/app.py` — `create_app()` factory. Al arrancar llama a `backend.migration.run_all()`.
- `backend/migration.py` — migraciones vía pymysql (columnas + tablas) + `db.create_all()`. Usado por `app.py`, `migrate.py`, `setup.py`.
- `backend/models.py` — SQLAlchemy: `User`, `Driver`, `Trip`, `Review`.
- `backend/auth.py` — Blueprint `auth`: registro, login, perfil, verificación email.
- `backend/routes.py` — Blueprint `main`: rutas HTML + JSON APIs (CSRF protegidas).
- `backend/templates/` — Jinja2 + Leaflet.js. VSCode asocia como django-html.
- `demo/index.html` — SPA JS vainilla con datos mock (landing page en `/`).
- `tests/` — Pytest con SQLite `:memory:`, app fresca por método.

## Seguridad

- **CSRF**: todas las rutas de mutación requieren `csrf_token` (form) o `X-CSRF-Token` (JSON) o `{csrf_token}` en JSON body. `window.CSRF_TOKEN` se inyecta en templates.
- **Auth**: `@login_required` + `@csrf_required` en rutas protegidas. GET routes (status, eta, nearby, geocode) solo requieren login.
- **Input sanitized**: `sanitize_input()` elimina HTML tags y trunca a 500 chars.
- **SECRET_KEY**: requerida en `backend/.env` o producción (app no arranca sin ella).
- **Email verification**: exigida al login solo si SMTP está configurado en `.env`.

## APIs JSON clave

Todas requieren `X-CSRF-Token` header (obtener de `window.CSRF_TOKEN`).

| Método | Ruta | Propósito |
|--------|------|-----------|
| POST | `/api/location/update` | Conductor envía `{lat, lng}` (solo si online) |
| POST | `/api/driver/toggle_online` | `{is_online: bool}` |
| POST | `/api/driver/respond/<id>` | `{action: "accept"\|"reject"}` |
| GET | `/api/drivers/nearby?lat=&lng=&radius=` | Conductores online+libres c/distancia |
| POST | `/api/trip/<id>/cancel` | `{reason}` |
| POST | `/api/trip/<id>/rate` | `{rating: 1-5, comment}` |
| GET | `/api/trips/available` | Viajes solicitados |
| GET | `/api/geocode?q=` | Geocodificación Nominatim (OSM) |

## Ciclo de vida del viaje

`requested` → `accepted` → `ongoing` → `completed` | `cancelled`

Rutas HTML (POST con CSRF): `/passenger/request`, `/driver/accept/<id>`, `/driver/start/<id>`, `/driver/complete/<id>`.

## Tarifa

```
fare = max(BASE + km * POR_KM + min * POR_MIN, MINIMA)
BASE=3.0, POR_KM=1.5, POR_MIN=0.25, MINIMA=5.0
```

Geocodificación real vía Nominatim. Fallback a longitud de dirección si falla.

## Quirks para el agente

- `is_ocupado` es typo intencional en DB (no `ocupado`) — así está en models y migration.
- `.env` va en `backend/.env`, no en raíz. `.env.example` en raíz.
- `FLASK_DEBUG=1` en `.env` activa debug mode. `PORT` variable de entorno (default 5000).
- La landing page `/` sirve `demo/index.html` si existe, sino `templates/index.html`.
- Sin lint/CI configurados. Tests existen en `tests/`.
