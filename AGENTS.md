# VAN

Flask + app de solicitud de viajes (motos y autos). Backend para app móvil
Flutter + frontend web Jinja2. PostgreSQL (Fase 5 ya adoptada); MySQL legacy
solo para migración de datos.

## Roadmap (orden aprobado, no saltar fases)

1. **Fase 1 — Backend para Flutter** (EN CURSO): API REST `/api/v1`, JWT + refresh tokens, OpenAPI/Swagger, web intacta.
2. **Fase 2 — App Flutter**: pasajero + conductor, publicar MVP en Google Play.
3. **Fase 3 — Tiempo real**: Socket.IO + Redis, ubicación en vivo, matching.
4. **Fase 4 — Monetización**: comisión por viaje, suscripciones empresa, wallet, Mercado Pago.
5. **Fase 5 — Infraestructura**: PostgreSQL + Alembic, Cloudflare R2, Celery.
6. **Fase 6 — Escalabilidad**: multi-ciudad, referidos, surge pricing, analíticas, IA.

Decisiones de arquitectura en `docs/adr/` (ADR-001 API+JWT, ADR-002 refresh en BD, ADR-003 identidad unificada).

## Ramp up

```bash
# Tests (SQLite in-memory, no DB needed)
python -m pytest tests/ -v

# Setup + run server full-stack (PostgreSQL)
# 1. Editar backend/.env (copiar de .env.example): DATABASE_URL=postgresql+psycopg://...
# 2. Crear la base (vacia) en el servidor
# 3. python backend/app.py          # corre alembic upgrade head + arranca en :5000
# 4. python create_demo_users.py    # pasajero@demo.com / 1234, conductor@demo.com / 1234

# Migrar sin servidor
python migrate.py   # usa la config de backend/.env (alembic upgrade head)

# Producción (Railway/Docker)
# start.sh → migrate.py → waitress-serve backend.app:app
```

## Arquitectura

- `backend/app.py` — `create_app()` factory. Al arrancar llama a `backend.migration.run_all()` → `alembic upgrade head`.
- `backend/migration.py` — Alembic (PostgreSQL). El branch pymysql legacy emite WARN: incompatible con los modelos unificados.
- `migrations/` — Alembic. `7234ca128813` (0001) = baseline del esquema legacy pre-refactor (tabla `drivers`, FKs duales); `0002` = refactor a identidad unificada `users` + `driver_profiles` + `vehicles` (reversible, merge defensivo de `drivers`); `0003` = `driver_profiles.status` (backfill existentes → `approved`, nuevos → `pending`, CHECK `chk_driver_profile_status`; usa `batch_alter_table` para ser testeable en SQLite). Migraciones de datos protegidas con `is_offline_mode()` para `--sql`.
- `backend/models.py` — SQLAlchemy: `User` (única identidad, campo `role`: passenger|driver|both|admin|company), `DriverProfile` (1:1, `status` pending|approved|rejected = única fuente de autorización; `is_online`/`is_busy`), `Vehicle` (1:N), `Trip`, `Review`, `RefreshToken`, `EmailVerification`, `TopUpRequest`, `WalletTransaction`, `Company*`.
- `backend/services/identity.py` — sesión unificada: `user_id` único, `user_role`, `active_mode` (contexto, nunca autoriza), helpers `allowed_modes()` / `switch_mode()` / `driver_view()` (capa plana legacy para templates).
- `backend/services/fare.py` — dinero Decimal, `build_fare()` con `platform_fee` (comisión 5% persistida, NO cobrada aún — Fase 4).
- `backend/auth.py` — Blueprint `auth`: registro pasajero/conductor, login por rol, `/select-mode` (usuario `both`), `/switch-mode`, perfil, verificación email (web, sesiones).
- `backend/api/` — Blueprint `api` (`/api/v1`): JWT Bearer para Flutter. Envelope `{success, data}` / `{success, error:{code,message}}`. Spec en `backend/api/openapi.yaml`, Swagger UI en `/api/v1/docs`.
- `backend/validators.py` — reglas compartidas web/API (nombre, email, password, sanitize).
- `backend/routes.py` — Blueprint `main`: rutas HTML + JSON APIs (CSRF protegidas).
- `backend/templates/` — Jinja2 + Leaflet.js. VSCode asocia como django-html. `select_mode.html` es nuevo.
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
| POST | `/api/v1/auth/register/driver` | Registro conductor (vehículo) → tokens + perfil (promueve a `both` si el email ya es pasajero) |
| POST | `/api/v1/auth/login` | `{email, password, mode?}` → tokens + perfil |
| POST | `/api/v1/auth/refresh` | `{refresh_token}` → par nuevo (rotación) |
| POST | `/api/v1/auth/logout` | `{refresh_token}` → revoca |
| GET | `/api/v1/auth/me` | Perfil del token |
| POST | `/api/v1/auth/switch-mode` | Cambia `mode` (solo `both`) → access token nuevo |
| POST | `/api/v1/auth/verify-email` | `{code}` con Bearer |

JWT claims: `sub` (user_id), `role`, `mode` (contexto, nunca autoriza),
`jti`, `iat`, `exp`. Flujo: login/register → guardar ambos tokens. Cuando la
API devuelva `TOKEN_EXPIRED`, llamar `/auth/refresh`. El access token se
manda como `Authorization: Bearer <token>`.

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

Al completar el viaje se persiste `total_fare = platform_fee + driver_earnings`
(comisión 5%, `PLATFORM_FEE_RATE` en env — calculada pero NO cobrada aún, Fase 4).

Geocodificación real vía Nominatim. Fallback a longitud de dirección si falla.

## Quirks para el agente

- En el esquema unificado el campo de perfil es `is_busy`; `is_ocupado` sigue
  existiendo solo como alias de presentación en `driver_view()` para templates.
- `.env` va en `backend/.env`, no en raíz. `.env.example` en raíz. `DATABASE_URL`
  en `backend/.env` (PostgreSQL `postgresql+psycopg://...`); sin él, arranca
  contra SQLite local.
- `FLASK_DEBUG=1` en `.env` activa debug mode. `PORT` variable de entorno (default 5000).
- La landing page `/` sirve `demo/index.html` si existe, sino `templates/index.html`.
- Sin lint/CI configurados. Tests existen en `tests/` (149 tests, suite completa — baseline `python -m pytest -q`).
- Refresh tokens: nunca loguear el valor; la tabla guarda hash SHA-256 (ADR-002).
- La web y la API comparten validaciones de `backend/validators.py` — no duplicar reglas.
- Pitfall SQLAlchemy: no usar `user.driver_profile or DriverProfile(...)` tras
  asignar el profile — SQLAlchemy cachea el `None`; asignar
  `user.driver_profile = DriverProfile(...)` y commitear de inmediato.
