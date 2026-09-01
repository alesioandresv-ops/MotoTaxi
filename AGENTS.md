# VAN

Flask + app de solicitud de viajes (motos y autos). Backend para app móvil
Flutter + frontend web Jinja2. PostgreSQL (Fase 5 ya adoptada); MySQL legacy
solo para migración de datos.

## Roadmap (orden aprobado, no saltar fases)

1. **Fase 1 — Backend para Flutter** (✅ COMPLETA): API REST `/api/v1`, JWT + refresh tokens, OpenAPI/Swagger, web intacta. 24 endpoints, 441 tests.
2. **Fase 2 — App Flutter** (EN CURSO): pasajero + conductor, publicar MVP en Google Play. Estructura base en `flutter/`.
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

- `backend/app.py` — `create_app()` factory. Al arrancar llama a `backend.migration.run_all()` → `alembic upgrade head`. Sentry opcional via `SENTRY_DSN`. Log level configurable via `LOG_LEVEL`. Cache busting en prod (`SEND_FILE_MAX_AGE_DEFAULT=31536000`). HTTP→HTTPS redirect automático en producción. CSP permite tiles OSM (`img-src https://*.tile.openstreetmap.org`).
- `backend/migration.py` — Alembic (PostgreSQL). Import de `pymysql` condicional (solo se carga si se detecta MySQL legacy).
- `migrations/` — Alembic. `7234ca128813` (0001) = baseline del esquema legacy pre-refactor (tabla `drivers`, FKs duales); `0002` = refactor a identidad unificada `users` + `driver_profiles` + `vehicles` (reversible, merge defensivo de `drivers`); `0003` = `driver_profiles.status` (backfill existentes → `approved`, nuevos → `pending`, CHECK `chk_driver_profile_status`; usa `batch_alter_table` para ser testeable en SQLite); `0004` = idempotencia API v1 (`api_idempotency_keys` + `trips.idempotency_key`, sin backfill); `0005` = cobro al finalizar (`trips.payment_status`/`paid_at`/`payment_method_collected`, backfill completed→paid); `0006` = índice único parcial `topup_requests.mp_payment_id` (dedup recargas MP a nivel BD); `0007` = `topup_requests.preference_id` (trazabilidad de preferencias MP, nullable sin backfill). Migraciones de datos protegidas con `is_offline_mode()` para `--sql`. IDs de revisión cortos (`'0005'`), no el nombre de archivo.
- `backend/models.py` — SQLAlchemy: `User` (única identidad, campo `role`: passenger|driver|both|admin|company), `DriverProfile` (1:1, `status` pending|approved|rejected = única fuente de autorización; `is_online`/`is_busy`), `Vehicle` (1:N), `Trip`, `Review`, `RefreshToken`, `EmailVerification`, `TopUpRequest`, `WalletTransaction`, `Company*`, `ApiIdempotencyKey`.
- `backend/services/identity.py` — sesión unificada: `user_id` único, `user_role`, `active_mode` (contexto, nunca autoriza), helpers `allowed_modes()` / `switch_mode()` / `driver_view()` (capa plana legacy para templates).
- `backend/services/fare.py` — dinero Decimal, `build_fare()` con `platform_fee` (comisión 5% persistida, NO cobrada aún — Fase 4).
- `backend/auth.py` — Blueprint `auth`: registro pasajero/conductor, login por rol, `/select-mode` (usuario `both`), `/switch-mode`, perfil, verificación email (web, sesiones).
- `backend/api/` — Blueprint `api` (`/api/v1`): JWT Bearer para Flutter. Envelope `{success, data}` / `{success, error:{code,message}}`. Auth + trips + wallet + driver + extras completos. Spec en `backend/api/openapi.yaml`, Swagger UI en `/api/v1/docs`.
- `backend/services/trips.py` — lógica de viajes compartida web/API: `create_trip()` con idempotencia (replay desde `api_idempotency_keys`, TTL 24 h), distancia coords→geocode→fallback 1.0 km, `company_id` solo por membership activa; ciclo de vida Etapa 3 (`accept_trip` claim atómico, `start/cancel/rate/trip_eta`, `list_trips`, `available_trips`) con `TripServiceError(code)` = catálogo API; `cancel_stale_trips()` (requested >5 min → system) vive AQUÍ y routes.py lo importa; `finalize_trip()` ÚNICA vía hacia `completed` (cobra y completa en la misma transacción, retry idempotente).
- `backend/services/wallet.py` — `wallet_transfer()`: débito/crédito atómico con locks en orden determinista por id; NUNCA commitea (el caller commitea todo-o-nada); montos asimétricos vía `credit_amount` (comisión).
- `backend/services/mercadopago.py` — punto único MP: credenciales por entorno (`MP_ENV` test|production), firma de webhooks manifest ts/v1 (`validate_webhook_signature`, SDK ≥3.4), `create_topup_preference()` persiste TopUpRequest pending con `preference_id`, back_urls por cliente (`back_urls_for`: web = BASE_URL, mobile = deep links `van://` vía `app_scheme()`). Webhooks fail-closed si hay `MP_WEBHOOK_SECRET`; acreditación SIEMPRE con verificación server-side.
- `backend/validators.py` — reglas compartidas web/API (nombre, email, password, sanitize).
- `backend/routes.py` — Blueprint `main`: rutas HTML + JSON APIs (CSRF protegidas).
- `backend/templates/` — Jinja2 + Leaflet.js. VSCode asocia como django-html. `select_mode.html` es nuevo.
- `demo/index.html` — SPA JS vainilla con datos mock (landing page en `/`).
- `tests/` — Pytest con SQLite `:memory:`, app fresca por método.
- `flutter/` — App Flutter (Fase 2, EN CURSO). Estructura feature-first clean architecture. Dependencias: dio, flutter_secure_storage, go_router, google_maps_flutter, geolocator, geocoding, permission_handler, cached_network_image, qr_flutter, url_launcher, image_picker. 23 screens planificados.
  - `lib/core/` = modelos (User, Trip, Wallet, Driver, Review), servicios (auth, trip, wallet, driver, location), API client (Dio + JWT auto-refresh + secure storage).
  - `lib/features/auth/` = login, register.
  - `lib/features/passenger/` = passenger_home (mapa + wallet card), request_trip (formulario + nearby search).
  - `lib/features/trip/` = active_trip (polling status + mapa + driver info), rate_trip (estrellas + comment).
  - `lib/features/driver/` = driver_home (online toggle + available trips), driver_trip (start/complete).
  - `lib/features/wallet/` = wallet_screen (saldo + topup + transacciones).
  - `lib/features/profile/` = profile_screen (info + driver payments + edit links).
  - `lib/features/history/` = history_screen (completed + cancelled trips).

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
| PUT | `/api/v1/auth/profile` | Editar nombre y teléfono |
| POST | `/api/v1/auth/profile/photo` | Subir foto de perfil (base64) |
| POST | `/api/v1/auth/password` | Cambiar contraseña (requiere current_password) |
| GET | `/api/v1/auth/guidelines` | Verificar si aceptó guidelines |
| POST | `/api/v1/auth/guidelines` | Aceptar guidelines de la comunidad |

JWT claims: `sub` (user_id), `role`, `mode` (contexto, nunca autoriza),
`jti`, `iat`, `exp`. Flujo: login/register → guardar ambos tokens. Cuando la
API devuelva `TOKEN_EXPIRED`, llamar `/auth/refresh`. El access token se
manda como `Authorization: Bearer <token>`.

## API v1 — trips (Etapas 2-3)

| Método | Ruta | Propósito |
|--------|------|-----------|
| POST | `/api/v1/trips` | Crea viaje. Header `Idempotency-Key` OBLIGATORIO (body `idempotency_key` deprecated; header gana). 201 nuevo / 200 replay (`duplicate:true`). Errores: VALIDATION_ERROR, INVALID_VEHICLE_TYPE, INVALID_PAYMENT_METHOD, ACTIVE_TRIP_EXISTS |
| GET | `/api/v1/trips/{id}` | Detalle canónico §5.1. Solo participantes (403 si no) |
| GET | `/api/v1/trips?role=passenger\|driver&status=&page=&limit=` | Listado propio paginado |
| GET | `/api/v1/trips/available?lat&lng&radius&vehicle_type` | Requested cercanos al conductor (LOCATION_REQUIRED sin posición; expira stale >5 min → `cancelled_by=system`) |
| POST | `/api/v1/trips/{id}/accept` | Claim atómico; exige online+libre+approved. 409 TRIP_NOT_AVAILABLE / NOT_ONLINE; 403 NOT_VERIFIED |
| POST | `/api/v1/trips/{id}/reject` | Sin efecto sobre el viaje. `{ok:true}` |
| POST | `/api/v1/trips/{id}/start` | accepted→ongoing (solo asignado). INVALID_TRANSITION / FORBIDDEN |
| POST | `/api/v1/trips/{id}/complete` | ongoing→completed vía `finalize_trip()`; body `{}` o `{"method": ...}` real del conductor (paridad web). INSUFFICIENT_BALANCE → sigue ongoing; retry idempotente |
| POST | `/api/v1/trips/{id}/cancel` | Pax dueño o driver asignado; libera is_busy; finalizados → TRIP_FINALIZED |
| POST | `/api/v1/trips/{id}/rate` | {rating 1-5, comment?} — solo completed, 1 vez por rol |
| GET | `/api/v1/trips/{id}/eta` | ETA del conductor hacia el pickup (nulls si no hay posición) |
| GET | `/api/v1/trips/{id}/status` | Estado del viaje + ubicación del conductor (polling cada 5s). Solo participantes. Payload ligero. |

Reglas: `vehicle_type` moto/auto; `payment_method` mismo set que la web
(5 claves); distancia la calcula el backend (coords → geocode → fallback
1.0 km); `company_id` lo asigna el backend por membership trial/active
(el del cliente se ignora). Ciclo de vida completo en
`backend/services/trips.py` con `TripServiceError(code)` mapeada 1:1 al
catálogo de errores.

## API v1 — wallet (Etapa 4)

| Método | Ruta | Propósito |
|--------|------|-----------|
| GET | `/api/v1/wallet` | Saldo + currency del usuario autenticado |
| GET | `/api/v1/wallet/transactions?type=&page=&limit=` | Movimientos de billetera paginados, filtro por tipo |
| POST | `/api/v1/wallet/topups` | Crear recarga: `mercadopago` → preference MP + `init_point`; `cvu`/`bank` → pending manual. Amount 100–500.000 |
| GET | `/api/v1/wallet/topups?status=&page=&limit=` | Listar recargas propias |
| GET | `/api/v1/wallet/topups/{id}` | Detalle de recarga propia |

Topup methods: `mercadopago` (automático, usa `create_topup_preference` de
`services/mercadopago.py` con `X-Client-Type: mobile` → deep links), `cvu`
y `bank` (aprobación manual, `init_point: null`). `paginate()` devuelve
dict `{'items': [...], 'pagination': {...}}` (no tupla).

## API v1 — driver (A1 + A4)

| Método | Ruta | Propósito |
|--------|------|-----------|
| POST | `/api/v1/drivers/location` | Conductor envía ubicación `{lat, lng}`. Solo si online (409 NOT_ONLINE) |
| POST | `/api/v1/drivers/online` | Toggle online/offline. Actualiza `is_online` + `last_online_at`. Guarda posición si la tiene. |
| GET | `/api/v1/drivers/nearby?lat=&lng=&radius=&vehicle_type=` | Conductores online+libres ordenados por distancia. Excluye al propio conductor. |
| GET | `/api/v1/driver/accepted-payments` | Métodos de pago aceptados por el conductor |
| PUT | `/api/v1/driver/accepted-payments` | Actualizar lista completa de métodos aceptados |
| POST | `/api/v1/driver/qr` | Subir imagen QR de MercadoPago (base64) |
| GET | `/api/v1/driver/payment-methods` | Listar métodos de cobro del conductor |
| POST | `/api/v1/driver/payment-methods` | Agregar método de cobro `{type, details}` |
| DELETE | `/api/v1/driver/payment-methods/{id}` | Eliminar método de cobro propio |
| GET | `/api/v1/geo/geocode?q=` | Proxy Nominatim para Flutter (sin CORS issues). Retorna `{lat, lng, display_name}`. |
| GET | `/api/v1/users/{id}/reviews?role=` | Reseñas recibidas por un usuario |
| GET | `/api/v1/favorites` | Rutas frecuentes del pasajero (≥3 usos) |
| POST | `/api/v1/wallet/topups/{id}/voucher` | Subir comprobante de transferencia (base64). Solo propio, pending. |

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
| POST | `/api/trip/<id>/collect-payment` | `{method}` — conductor cobra y finaliza. 409 `PAYMENT_INSUFFICIENT_BALANCE` (billetera sin saldo: elige otro método) / `INVALID_STATUS`; 403 FORBIDDEN; éxito `{status:'completed', payment_status:'paid', payment_method_collected, fare}` |
| GET | `/api/trips/available` | Viajes solicitados |
| GET | `/api/geocode?q=` | Geocodificación Nominatim (OSM) |
| POST | `/api/wallet/topup` | `{amount, method:'mp_checkout'}` → preferencia Checkout Pro (persiste TopUpRequest pending con `preference_id`, migración 0007) → `{init_point}`. Lógica en `services/mercadopago.py` |
| POST+GET | `/api/wallet/topup/webhook` | Webhook MP: firma manifest ts/v1 fail-closed si hay `MP_WEBHOOK_SECRET` (403 si inválida); acredita SOLO tras verificar el pago contra la API (`_credit_mp_payment`) |
| POST | `/api/wallet/topup/verify` | `{payment_id}` — acredita con verificación server-side; lo llama la página de éxito (`topup_success.html`) mientras muestra "Validando pago…". `{credited, amount}`, idempotente |

## Ciclo de vida del viaje

`requested` → `accepted` → `ongoing` → `collect-payment` (cobro) → `completed` | `cancelled`

- `completed` SOLO vía `finalize_trip()` (`backend/services/trips.py`), invocada por
  `POST /api/trip/<id>/collect-payment` (web, CSRF): el conductor confirma el método real
  (puede cambiar el del pasajero). Billetera sin saldo → 409, viaje sigue ongoing, SIN deuda pendiente.
- Rutas HTML (POST con CSRF): `/passenger/request`, `/driver/accept/<id>`, `/driver/start/<id>`
  (valida estado `accepted`). `/driver/complete/<id>` fue ELIMINADO.

## Tarifa

```
fare = max(BASE + km * POR_KM + min * POR_MIN, MINIMA)
BASE=3.0, POR_KM=1.5, POR_MIN=0.25, MINIMA=5.0
```

Al completar el viaje se persiste `total_fare = platform_fee + driver_earnings`
(comisión 5%, `PLATFORM_FEE_RATE` en env — calculada pero NO cobrada aún, Fase 4).

Geocodificación real vía Nominatim. Fallback a longitud de dirección si falla.

## Producción (hardening completado)

- `LOG_LEVEL` env var (default `INFO`).
- `SENTRY_DSN` env var — si se define, init automático con FlaskIntegration.
- `SEND_FILE_MAX_AGE_DEFAULT=31536000` (1 año) en prod; `0` en dev.
- HTTP→HTTPS redirect automático (301) en `before_request` cuando `RAILWAY_ENVIRONMENT` o `SSL_ENABLED` están definidos.
- CSP: `img-src` incluye `https://*.tile.openstreetmap.org` para que Leaflet cargue tiles.
- `requirements.txt` = producción (sin pytest); `requirements-dev.txt` incluye pytest/pytest-flask.
- `Pillow==11.1.0` (pin exacto, antes `>=10.0.0`). PyMySQL eliminado (legacy MySQL no soportado).
- `sentry-sdk[flask]==2.22.0` en requirements.txt.
- Checklist de lanzamiento: `BASE_URL=https://van.com.ar`, `MP_ENV=production` + credenciales prod, `MP_WEBHOOK_SECRET` en panel MP.

## Quirks para el agente

- En el esquema unificado el campo de perfil es `is_busy`; `is_ocupado` sigue
  existiendo solo como alias de presentación en `driver_view()` para templates.
- `.env` va en `backend/.env`, no en raíz. `.env.example` en raíz. `DATABASE_URL`
  en `backend/.env` (PostgreSQL `postgresql+psycopg://...`); sin él, arranca
  contra SQLite local.
- `FLASK_DEBUG=1` en `.env` activa debug mode. `PORT` variable de entorno (default 5000).
- La landing page `/` sirve `demo/index.html` si existe, sino `templates/index.html`.
- Sin lint/CI configurados. Tests existen en `tests/` (441 tests, suite completa — baseline `python -m pytest -q`).
- Refresh tokens: nunca loguear el valor; la tabla guarda hash SHA-256 (ADR-002).
- MercadoPago: TODO por `backend/services/mercadopago.py` — nada lee tokens MP
  directo de `os.getenv`. `MP_ENV=test` usa credenciales de PRUEBA (solo pagan
  usuarios compradores de prueba con tarjetas de prueba; pagar con cuenta real
  = dinero real). Webhooks fail-closed si hay `MP_WEBHOOK_SECRET`.
- Preferencias MP: `auto_return='approved'` SIEMPRE (sin él MP muestra su
  pantalla "¡Listo!" y no vuelve a VAN — bug 2026-08-24); `notification_url`
  solo con BASE_URL público. Header `X-Client-Type: mobile` → back_urls con
  deep links `APP_SCHEME` (`van://...`, misma ruta que la web). La página
  `/wallet/topup/success` renderiza loader que llama `/api/wallet/topup/verify`.
- Tests herméticos ante dotenv: `tests/conftest.py` precarga sentinelas de
  `MP_ENV`/tokens MP porque `load_dotenv()` en `backend/app.py` filtra el
  `.env` real al proceso pytest. Ajustá entornos MP con monkeypatch, no asumas
  el `.env`.
- La web y la API comparten validaciones de `backend/validators.py` — no duplicar reglas.
- Pitfall SQLAlchemy: no usar `user.driver_profile or DriverProfile(...)` tras
  asignar el profile — SQLAlchemy cachea el `None`; asignar
  `user.driver_profile = DriverProfile(...)` y commitear de inmediato.
- Import circular: `services/trips.py` NO debe importar `backend.api.*` en el tope
  (`api/__init__` → `api.trips` → `services.trips`); `ApiError` se importa tardío
  dentro de `create_trip()`. En `routes.py`, los servicios se importan dentro de
  las funciones que los usan.
- Los tests de migración fijan target explícito (`'0005'`, etc.), nunca `'head'`.
- `ACTIVE_TRIP_EXISTS`: un pasajero no puede tener dos viajes activos
  (requested|accepted|ongoing). En tests, cancelar/completar el viaje previo
  (o usar otro pasajero) antes de crear otro.

### Flutter
- **Flutter no está instalado** en el entorno actual. El usuario debe instalar Flutter SDK y ejecutar `flutter pub get` en `flutter/`.
- **Google Maps**: en `android/app/src/main/AndroidManifest.xml` reemplazar `YOUR_API_KEY` con la API key real. En iOS configurar en `ios/Runner/AppDelegate.swift`.
- **Fonts**: reemplazar `assets/fonts/Montserrat-*.ttf` con los archivos reales de Montserrat (o usar google_fonts package).
- **API base URL**: en desarrollo usa `http://10.0.2.2:5000` (emulador Android) o `http://localhost:5000` (iOS). En producción `https://van.com.ar`.
- **Estructura**: `lib/core/` = modelos, servicios, API client (feature-agnostic). `lib/features/` = pantallas por feature (auth, passenger, driver, trip, wallet, profile, history).
