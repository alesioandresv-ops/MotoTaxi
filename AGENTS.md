# VAN

Flask + MySQL app de solicitud de viajes (motos y autos). Backend para app
móvil Flutter + frontend web Jinja2.

## Roadmap (orden aprobado, no saltar fases)

1. **Fase 1 — Backend para Flutter** (EN CURSO): API REST `/api/v1`, JWT + refresh tokens, OpenAPI/Swagger, web intacta.
2. **Fase 2 — App Flutter**: pasajero + conductor, publicar MVP en Google Play.
3. **Fase 3 — Tiempo real**: Socket.IO + Redis, ubicación en vivo, matching.
4. **Fase 4 — Monetización**: comisión por viaje, suscripciones empresa, wallet, Mercado Pago.
5. **Fase 5 — Infraestructura**: PostgreSQL + Alembic, Cloudflare R2, Celery.
6. **Fase 6 — Escalabilidad**: multi-ciudad, referidos, surge pricing, analíticas, IA.

Decisiones de arquitectura en `docs/adr/` (ADR-001 API+JWT, ADR-002 refresh en BD).

## Ramp up

```bash
# Tests (SQLite in-memory, no MySQL needed)
python -m pytest tests/ -v

# Setup + run server full-stack
# 1. Editar backend/.env (copiar de .env.example)
# 2. mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS van"
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
- `backend/models.py` — SQLAlchemy: `User`, `Driver`, `Trip`, `Review`, `RefreshToken`, `EmailVerification`.
- `backend/auth.py` — Blueprint `auth`: registro, login, perfil, verificación email (web, sesiones).
- `backend/api/` — Blueprint `api` (`/api/v1`): JWT Bearer para Flutter. Envelope `{success, data}` / `{success, error:{code,message}}`. Spec en `backend/api/openapi.yaml`, Swagger UI en `/api/v1/docs`.
- `backend/validators.py` — reglas compartidas web/API (nombre, email, password, sanitize).
- `backend/routes.py` — Blueprint `main`: rutas HTML + JSON APIs (CSRF protegidas).
- `backend/templates/` — Jinja2 + Leaflet.js. VSCode asocia como django-html.
- `demo/index.html` — SPA JS vainilla con datos mock (landing page en `/`).
- `tests/` — Pytest con SQLite `:memory:`, app fresca por método.

## Seguridad

- **Web (sesiones)**: CSRF en todas las rutas de mutación (`csrf_token` form, `X-CSRF-Token` header, o `{csrf_token}` JSON). `window.CSRF_TOKEN` en templates.
- **API v1 (JWT)**: Bearer token, sin cookies ni CSRF. Access token 30 min (stateless); refresh token opaco en tabla `refresh_tokens` (hash SHA-256), rotativo, con detección de reuso (reuso → revoca TODOS los tokens del usuario). `JWT_SECRET_KEY` env (fallback `SECRET_KEY`).
- **Input sanitized**: `sanitize_input()` elimina HTML tags y trunca a 500 chars.
- **SECRET_KEY**: requerida en `backend/.env` o producción (app no arranca sin ella).
- **Email verification**: exigida al login solo si SMTP está configurado en `.env`.

## API v1 — auth (contrato Flutter)

| Método | Ruta | Propósito |
|--------|------|-----------|
| POST | `/api/v1/auth/register` | Registro pasajero → tokens + perfil |
| POST | `/api/v1/auth/register/driver` | Registro conductor (vehículo) → tokens + perfil |
| POST | `/api/v1/auth/login` | `{email, password}` → tokens + perfil |
| POST | `/api/v1/auth/refresh` | `{refresh_token}` → par nuevo (rotación) |
| POST | `/api/v1/auth/logout` | `{refresh_token}` → revoca |
| GET | `/api/v1/auth/me` | Perfil del token |
| POST | `/api/v1/auth/verify-email` | `{code}` con Bearer |

Flujo: login/register → guardar ambos tokens. Cuando la API devuelva
`TOKEN_EXPIRED`, llamar `/auth/refresh`. El access token se manda como
`Authorization: Bearer <token>`.

## APIs JSON legadas (web)

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
- Refresh tokens: nunca loguear el valor; la tabla guarda hash SHA-256 (ADR-002).
- La web y la API comparten validaciones de `backend/validators.py` — no duplicar reglas.
