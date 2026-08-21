# VAN — MASTER SPEC

> Documento maestro del proyecto. Define visión, decisiones técnicas aprobadas, arquitectura, roadmap, reglas de desarrollo, estándares de código, convenciones de API, modelo de negocio y workstreams.
>
> Última actualización: 2026-08-10 · Estado: **Activo** · Fuente de verdad técnica: código en `backend/`, `tests/`, `migrations/`, ADRs en `docs/adr/`, `docs/api-contract-v1.md` y `AGENTS.md` (en ese orden de autoridad).

---

## 1. Visión del proyecto

**VAN** es una plataforma de solicitud de viajes urbano en moto y auto (estilo ride-hailing) pensada para el mercado hispanohablante, con foco en:

1. **Conectar pasajeros con conductores** en tiempo real: solicitud → aceptación → viaje → pago → calificación.
2. **Monetizar de dos formas**: tarifas por viaje (pasajero → conductor, comisión futura) y **suscripción B2B** (empresas que contratan viajes para empleados).
3. **Pagos flexibles**: efectivo, MercadoPago, transferencia, tarjeta y billetera interna con top-up.
4. **Cero dependencias de mapas propietarios**: Leaflet.js + OpenStreetMap y geocodificación con Nominatim.
5. **MVP móvil**: app Flutter (Fase 2) sobre la **API REST v1** (`/api/v1`, JWT) en desarrollo en la Fase 1.

La visión a mediano plazo: alternativa local y accesible a las apps internacionales de viajes, diferenciándose por **pago en billetera con carga manual, soporte de empresas y conductores verificados**, con tarifas transparentes.

---

## 2. Decisiones técnicas aprobadas

### 2.1 Decisiones vigentes

| # | Decisión | Estado | Detalle |
|---|----------|--------|---------|
| D1 | **Stack backend: Flask 3.1 (Python 3.12)** | ✅ Aprobada | Monolito simple, una sola app `create_app()` en `backend/app.py`. |
| D23 | **Base de datos objetivo: PostgreSQL** | ✅ Aprobada (Fase 5, ya adoptada) | `postgresql+psycopg://` vía `DATABASE_URL` (backend/.env). **Supera a D3 (MySQL)**. SQLite (en memoria o archivo) solo para tests y dev sin BD. |
| D24 | **Migraciones con Alembic** | ✅ Aprobada | `migrations/` con cadena `7234ca128813 → 0002 → 0003`. `backend/migration.py` corre `alembic upgrade head` al arrancar. **Supera a D4 (migraciones propias pymysql)**. |
| D25 | **API v1: JWT Bearer para la app móvil** | ✅ Aprobada (ADR-001) | Blueprint `/api/v1` en `backend/api/`. Access token 30 min stateless; refresh opaco en BD (D26). **Supera a D7 para la API** (la web conserva sesiones). |
| D26 | **Refresh tokens opacos en BD** | ✅ Aprobada (ADR-002) | Hash SHA-256 en `refresh_tokens`, rotación + detección de reuso (reuso → revoca TODOS los tokens del usuario). |
| D27 | **Identidad unificada** | ✅ Aprobada (ADR-003) | `users.role` (passenger\|driver\|both\|admin\|company) + `driver_profiles` (1:1) + `vehicles` (1:N). **Supera al diseño legacy de dos tablas (users + drivers)**. |
| D28 | **`driver_profiles.status` = única fuente de autorización del conductor** | ✅ Aprobada | `pending` \| `approved` \| `rejected` (migración 0003). `is_verified` queda como legacy/presentación (alias en `driver_view()`) y **NO autoriza**. |
| D29 | **`active_mode` / claim `mode` como contexto, nunca autoriza** | ✅ Aprobada | La autorización se decide SIEMPRE contra la DB (`users.role` + `driver_profiles.status`). Sesión web: `active_mode`; JWT: claim `mode`. |
| D30 | **Envelope API v1 + catálogo de errores + paginación** | ✅ Aprobada | `{success, data}` / `{success, error:{code,message}}`; `code` estable (`backend/api/errors.py`); paginación `?page=&limit=` (`backend/api/pagination.py`). |
| D31 | **Dinero en Decimal y comisión persistida (no cobrada)** | ✅ Aprobada | `backend/services/fare.py`: `build_fare()` con `platform_fee` (5% vía `PLATFORM_FEE_RATE`), invariante `total_fare = platform_fee + driver_earnings` (CHECK `chk_trip_money` en PG). Cobro real = Fase 4. |
| D5 | **Frontend web: Jinja2 server-side + Leaflet.js** | ✅ Aprobada | Templates en `backend/templates/`, mapas OSM. `demo/index.html` es la landing SPA servida en `/` si existe. |
| D6 | **JS vainilla, sin framework** | ✅ Aprobada | No hay React/Vue. `window.CSRF_TOKEN` inyectado desde template. |
| D7 | **Autenticación web por sesión (cookies)** | ✅ Aprobada (web) | Session Flask, cookie `HttpOnly`, `SameSite=Lax`, `Secure` en prod, lifetime 4 h. **Para la API móvil la reemplaza D25**. |
| D8 | **CSRF manual por sesión** | ✅ Aprobada (web) | Token en `session['csrf_token']`, `hmac.compare_digest`, decorador `@csrf_required`. Acepta form, header `X-CSRF-Token` o campo JSON. La API v1 NO usa CSRF (JWT). |
| D9 | **Rate limiting: Flask-Limiter** | ✅ Aprobada | Límites por IP en login y rutas sensibles; en API v1 por endpoint (login/register 10/min, etc.). Handler 429 global. |
| D10 | **Sanitización: bleach** | ✅ Aprobada | `sanitize_input()`: strip HTML + truncado a 500 chars (compartida web/API en `backend/validators.py`). |
| D11 | **Cifrado de datos de pago: Fernet** | ✅ Aprobada | `backend/extensions.py`: `encrypt_details()`/`decrypt_details()` con `ENCRYPTION_KEY`. Prefijo `enc:`. |
| D12 | **Pagos: SDK mercadopago + webhooks** | ✅ Aprobada | Checkout para empresas y top-ups de billetera (web legacy); API v1 lo expondrá en Fase 1 etapas de wallet. |
| D13 | **Geocodificación: Nominatim (OSM)** | ✅ Aprobada | `/api/geocode` (web) y `GET /geocode` (v1, futuro). Fallback a longitud de dirección. |
| D14 | **Cálculo de distancia: haversine propio** | ✅ Aprobada | `calcular_distancia()` en `backend/services/fare.py` (radio 6371 km). |
| D15 | **Tests: pytest + pytest-flask con SQLite `:memory:`** | ✅ Aprobada | App fresca por método. Suite actual: **149 tests** (ver §12). |
| D16 | **Servidor prod: Waitress** | ✅ Aprobada | `waitress-serve --listen=0.0.0.0:$PORT backend.app:app` en `start.sh`. |
| D17 | **Deploy: Railway + Docker** | ✅ Aprobada | `Dockerfile` (python:3.12-slim, usuario no-root) + `railway.json` (healthcheck `/health`). `docker-compose.yml` para PostgreSQL local. |
| D18 | **HTTPS**: Railway automático / Caddy+Let's Encrypt / Cloudflare Tunnel / cert autofirmado (`generate_cert.py`) | ✅ Aprobada | Cámara requiere HTTPS; documentado en README. |
| D19 | **Email de verificación SMTP** | ✅ Aprobada (opcional) | Solo se exige si SMTP está configurado (web y API v1). |
| D20 | **Multi-vehículo: moto y auto** | ✅ Aprobada | `vehicles.type` (moto/auto), `Vehicle` 1:N por conductor, tarifas diferenciadas en `fare.py`. |
| D21 | **`is_ocupado` (typo intencional)** | ✅ Aprobada (legacy) | Columna histórica del esquema legacy; en el esquema unificado es `driver_profiles.is_busy` y `driver_view()` expone `is_ocupado` como alias de presentación para templates. NO renombrar. |
| D22 | **Datos de pago cifrados** | ✅ Aprobada | `PassengerPaymentConfig.details` y `DriverPaymentMethod.details` con Fernet. |

### 2.2 Decisiones históricas REEMPLAZADAS (historial — NO son la arquitectura actual)

| # | Decisión original | Estado hoy | Reemplazada por |
|---|-------------------|------------|-----------------|
| D3 | **MySQL (PyMySQL) como BD** | 🔄 SUPERADA | **D23 — PostgreSQL**. MySQL queda SOLO como origen de datos para la migración legacy (Alembic 0002) y el branch pymysql de `migration.py` emite WARN: incompatible con los modelos unificados. |
| D4 | **Migraciones propias (sin Alembic)** | 🔄 SUPERADA | **D24 — Alembic**. El dict `COLUMNAS`/`COLUMN_MODIFY`/`TABLAS` de `backend/migration.py` sobrevive únicamente para el branch MySQL legacy. |
| D7 | **Sesión/cookies como único mecanismo de auth** | 🔄 SUPERADA (solo API) | **D25 — JWT Bearer** para `/api/v1`. La web mantiene sesiones+CSRF. Conviven ambos mecanismos (ADR-001, consecuencias). |
| (histórica) | **Alembic rechazado** como sistema de migraciones | 🔄 SUPERADA | Adoptado en Fase 5 (D24). |
| (histórica) | **JWT rechazado** para auth | 🔄 SUPERADA | Adoptado para la API móvil (D25). Sigue vigente el rechazo para la web (sesiones). |
| (histórica) | **Identidad en dos tablas: `users` (pasajeros) + `drivers` (conductores)** | 🔄 SUPERADA | **D27 — identidad unificada** (ADR-003). |

### 2.3 Decisiones explícitamente rechazadas (vigentes)

- **Google Maps / Mapbox** (descartado: Leaflet + OSM). `MAPBOX_TOKEN` ya no se usa.
- **Framework JS frontend** (React/Vue/etc.).
- **Celery / tareas asíncronas** (no hay colas; todo es síncrono o webhooks) — **revisar en Fase 5** (roadmap contempla Celery).
- **Redis con TTL para refresh tokens** — postergado a Fase 3/5 (ADR-002: hoy la BD basta).
- **Flask-JWT-Extended** — PyJWT + decoradores propios dan control total (ADR-001).
- **Refresh JWT firmado sin estado** — sin revocación real (ADR-002).
- **API sin versionar** (`/api/v2` ad-hoc) — el versionado es obligatorio desde el día uno (ADR-001).
- **Sesiones por cookie para la app móvil** — inseguro en móvil (ADR-001).
- **Seguir con dos tablas de identidad / tabla intermedia `identities`** (ADR-003).

---

## 3. Arquitectura

### 3.1 Visión general

```
Flutter (app móvil)                      Browser (Jinja2 + Leaflet.js + JS vainilla)
      │  Bearer JWT (sin cookies)                │  form/JSON + CSRF token
      ▼                                          ▼
Flask app (backend/app.py — create_app())
├── Blueprint api   (backend/api/)   → /api/v1/*    JWT Bearer, envelope {success,data}
├── Blueprint auth  (backend/auth.py) → /register, /login, /profile, /select-mode…
├── Blueprint main  (backend/routes.py) → HTML + APIs JSON web (viajes, wallet, admin)
├── Blueprint company(backend/company.py) → portal empresas B2B
├── Services        (backend/services/) → fare.py (Decimal/comisión), identity.py (sesión)
├── Validators      (backend/validators.py) → reglas compartidas web/API
├── Migraciones     (backend/migration.py → alembic upgrade head; migrations/)
├── Extensions      (backend/extensions.py) → Limiter + Fernet
└── Models          (backend/models.py) → SQLAlchemy (esquema unificado)
        │
        ▼
PostgreSQL (prod, Alembic) / SQLite :memory: o archivo (tests, dev sin BD)
```

### 3.2 Capas y responsabilidades

| Componente | Archivo | Responsabilidad |
|------------|---------|-----------------|
| Factory | `backend/app.py` | Config, sesión segura, JWT config, headers de seguridad, template filters, error handlers 404/500/429 (JSON en `/api/*`), CSRF injection, `run_all()` de migraciones al arrancar. |
| API v1 | `backend/api/` | Blueprint `/api/v1`: `jwt.py` (JWT+refresh), `errors.py` (catálogo), `decorators.py` (`jwt_required`, `require_mode`), `pagination.py`, `serializers.py`, `auth.py` (endpoints de auth — implementados). `openapi.yaml` + Swagger UI en `/api/v1/docs`. |
| Auth web | `backend/auth.py` | Registro pasajero/conductor, login por rol, `/select-mode` y `/switch-mode` (usuario `both`), perfil, verificación email (web, sesiones). |
| Routes web | `backend/routes.py` | Ciclo de vida del viaje, geolocalización, conductores cercanos, favoritos, reviews, métodos de pago, wallet, admin, GDPR (export/delete). |
| Empresas | `backend/company.py` | Registro de empresa, planes (basic/advanced), pago MP/transferencia, login, dashboard, invitación de miembros, trips. |
| Servicios | `backend/services/fare.py` | Tarifas Decimal, `build_fare()`, comisión `PLATFORM_FEE_RATE`, haversine. `backend/services/identity.py` | Sesión unificada, `allowed_modes()`/`switch_mode()`, `driver_view()` (capa plana legacy para templates). |
| Validaciones | `backend/validators.py` | Reglas compartidas web/API (nombre, email, password, sanitize) — una sola fuente de verdad. |
| Migraciones | `backend/migration.py` | `run_all()`: PostgreSQL → `alembic upgrade head`; MySQL legacy → WARN + migración pymysql (incompatible con modelos unificados); SQLite → `db.create_all()`. |
| Tests | `tests/` | Pytest, app fresca por método, SQLite `:memory:` (ver §12). |
| Scripts raíz | `migrate.py`, `setup.py`, `reset_db.py`, `create_demo_users.py`, `ver_usuarios.py`, `eliminar_usuario.py` | Operaciones de DB sin servidor. |
| Deploy | `Dockerfile`, `start.sh`, `railway.json`, `Procfile`, `Caddyfile`, `.nixpacks`, `docker-compose.yml` | Build y run en producción; PostgreSQL local para dev. |

### 3.3 Modelo de datos (esquema unificado — 14 tablas)

- **users** — única identidad. `role` (passenger|driver|both|admin|company) con CHECK `chk_users_role`, index único `lower(email)`, balance, rating, foto, guidelines.
- **driver_profiles** — 1:1 con users (`user_id` UNIQUE, FK `ON DELETE CASCADE`). `status` (pending|approved|rejected) con CHECK `chk_driver_profile_status` = **única fuente de autorización**; `is_verified` legacy NO autoriza; `is_online`/`is_busy`/lat/lng/pagos aceptados/QR MP.
- **vehicles** — 1:N con driver_profiles (`type`: moto/auto, placa, marca, seguro, casco, `is_active`).
- **trips** — viajes: `passenger_id`/`driver_id` → `users.id`, `vehicle_id`, `company_id` opcional, coordenadas/direcciones, `total_fare`/`platform_fee`/`platform_fee_rate`/`driver_earnings`/`currency` (CHECK `chk_trip_money`: `total_fare = platform_fee + driver_earnings`), `status` (CHECK), `requested_at`/`started_at`/`completed_at`, `cancelled_by`, `payment_method`.
- **reviews** — calificación cruzada (1 vez por par viaje/emisor/receptor, UNIQUE `uq_review_once`), rating 1–5, `role` = rol del destinatario.
- **companies** — B2B: plan, status (trial/active/inactive/pending_payment), `max_employees`.
- **company_members** — empleados (rol admin/employee, invitación).
- **driver_payment_methods** — métodos de cobro del conductor (details cifrados Fernet, FK → driver_profiles).
- **passenger_payment_configs** — configs de pago del pasajero (cifrados).
- **favorite_addresses** — direcciones frecuentes con contador.
- **wallet_transactions** — ledger: `user_id` (dueño) + `counterparty_id`, `amount` con signo, `type`, `trip_id`, `status`.
- **topup_requests** — cargas: MercadoPago/CVU/voucher, `mp_payment_id` (dedup), aprobación admin.
- **refresh_tokens** — API v1: `token_hash` SHA-256 UNIQUE, `expires_at`, `revoked_at`, `replaced_by_id`, FK → users (CASCADE).
- **email_verifications** — códigos de verificación (hash, intentos, expiración).

> Histórico (ya no existe en el esquema unificado): tabla `drivers`, columnas `is_ocupado`, `user_type`, FKs duales de `reviews`/`wallet_transactions`. Todo esto fue consolidado por la migración `0002` (ver §6).

### 3.4 Flujo de datos del viaje (web legacy)

1. Pasajero solicita (`/passenger/request`): geocodifica origen/destino (Nominatim), distancia (haversine) y tarifa (`build_fare`).
2. Viaje `requested`; conductores online+libres+`approved` lo ven en `/api/trips/available`.
3. Conductor acepta (HTML `/driver/accept/<id>` o JSON `/api/driver/respond/<id>`).
4. `accepted` → `ongoing` (`/driver/start`) → `completed` (`/driver/complete`).
5. Cancelación (pasajero/conductor/`system` por timeout de 5 min en `cancel_stale_trips()`).
6. Rating posterior (`/api/trip/<id>/rate`) y pago (efectivo/MP/billetera).

### 3.5 Despliegue

- **Producción**: Railway (Dockerfile → `start.sh` → `migrate.py` → waitress). Healthcheck `/health`.
- **HTTPS**: automático en Railway; Caddy (dominio propio), Cloudflare Tunnel o cert autofirmado (local).
- **Local full-stack**: `docker-compose.yml` (PostgreSQL) o SQLite sin BD; `python backend/app.py` (corre migraciones + arranca :5000). `.env` en `backend/.env`.

---

## 4. Roadmap (orden aprobado)

| Fase | Alcance | Estado |
|------|---------|--------|
| **Fase 1** | **Backend para Flutter**: API REST `/api/v1`, JWT + refresh tokens, OpenAPI/Swagger, **web intacta** | 🔄 **EN CURSO** (Etapa 0 infraestructura+auth y Etapa 1 migración 0003 COMPLETAS; **Etapa 2 — Trips API NO implementada aún** y siguientes pendientes, ver §7/§9) |
| **Fase 2** | **App Flutter**: pasajero + conductor, publicar MVP en Google Play | ⏳ Pendiente |
| **Fase 3** | **Tiempo real**: Socket.IO + Redis, ubicación en vivo, matching | ⏳ Pendiente |
| **Fase 4** | **Monetización**: comisión por viaje (cobro real de `platform_fee`), suscripciones empresa, wallet, Mercado Pago | ⏳ Pendiente |
| **Fase 5** | **Infraestructura**: PostgreSQL + Alembic, Cloudflare R2, Celery | ✅ **PostgreSQL + Alembic YA ADOPTADOS**; R2/Celery pendientes |
| **Fase 6** | **Escalabilidad**: multi-ciudad, referidos, surge pricing, analíticas, IA | ⏳ Pendiente |

**Regla**: no saltar fases. La Fase 1 no se cierra hasta completar las 8 etapas del contrato (`docs/api-contract-v1.md` §16) con suite en verde.

---

## 5. Seguridad

- **Web (sesiones)**: CSRF en todas las rutas de mutación (`csrf_token` form, `X-CSRF-Token` header o `{csrf_token}` JSON). `window.CSRF_TOKEN` en templates.
- **API v1 (JWT)**: Bearer token, sin cookies ni CSRF. Access token 30 min stateless (`JWT_ACCESS_TTL_MINUTES`); refresh token opaco (`secrets.token_urlsafe(48)`) en tabla `refresh_tokens` (hash SHA-256), rotativo (TTL 30 días, `JWT_REFRESH_TTL_DAYS`), con detección de reuso (reuso → revoca TODOS los tokens del usuario). `JWT_SECRET_KEY` env (fallback `SECRET_KEY`).
- **JWT claims**: `sub` (user_id), `role`, `mode` (contexto, NUNCA autoriza), `jti`, `iat`, `exp`. La autorización SIEMPRE se valida contra la DB (`decorators.py::require_mode`).
- **Input sanitizado**: `sanitize_input()` elimina HTML tags y trunca a 500 chars (compartido web/API).
- **SECRET_KEY**: requerida en `backend/.env` o producción (la app no arranca sin ella).
- **Email verification**: exigida al login solo si SMTP está configurado en `.env`.
- **Datos de pago cifrados** con Fernet (`ENCRYPTION_KEY`).
- Headers: `X-Content-Type-Options`, `X-Frame-Options: DENY`, CSP, HSTS en prod.

---

## 6. Migraciones (Alembic)

`backend/migration.py::run_all()` corre `alembic upgrade head` al arrancar (PostgreSQL). Cadena de migraciones en `migrations/versions/`:

### 0001 — `7234ca128813_baseline_esquema_actual_pre_refactor.py`
- Baseline del esquema **legacy** (pre-refactor): `users` + `drivers` separados, `user_type` en tokens/verificaciones, `trips.fare` sin comisión, FKs duales en reviews/wallet. `down_revision = None`.
- Propósito: snapshot del esquema MySQL legacy para poder migrar datos a PG.

### 0002 — `0002_unified_users.py` (refactor identidad unificada, reversible)
- `users.role` + CHECK `chk_users_role` + index único `lower(email)`.
- Crea `driver_profiles` (1:1, FK CASCADE) y `vehicles` (1:N).
- `trips`: `fare` → `total_fare`; agrega `platform_fee`, `platform_fee_rate`, `driver_earnings`, `currency`, `vehicle_id`; CHECKs `chk_trip_money`, `chk_trip_status`, `chk_trip_vehicle_type`; FKs `driver_id` → `users.id`.
- `reviews`: elimina FKs duales, `role` no-null, UNIQUE `uq_review_once`.
- `wallet_transactions`: `driver_id` → `counterparty_id`, `user_id` no-null.
- `driver_payment_methods`: `driver_id` → `driver_profile_id`.
- `refresh_tokens`/`email_verifications`: elimina `user_type`, FK → users (CASCADE).
- **Merge defensivo de datos**: solo corre si existe la tabla legacy `drivers` con datos. Promueve pasajeros a `both` cuando el email coincide; emails que chocan entre conductores se resuelven en la migración (sufijo o más reciente, según 0002). Protegido con `is_offline_mode()` para `--sql` (no ejecuta datos offline).
- **Downgrade**: revierte columnas/FKs y elimina `driver_profiles`/`vehicles` (datos legacy consolidados no se restauran a `drivers`).

### 0003 — `0003_driver_profile_status.py` (verificación del conductor — contrato §7)
- **Upgrade**:
  - `ADD COLUMN driver_profiles.status VARCHAR(10) NOT NULL` con `server_default 'pending'` → **nuevos registros = `pending`**.
  - **Backfill**: TODOS los existentes → `'approved'` (compatibilidad total; nadie queda bloqueado).
  - `CREATE CHECK chk_driver_profile_status`: `status IN ('pending', 'approved', 'rejected')` (mismo nombre que en `models.py`).
  - Usa `batch_alter_table` (passthrough en PG; recrea la tabla en SQLite → testeable sin Docker).
  - Backfill protegido con `_online()` (`is_offline_mode()`): con `alembic upgrade --sql` solo se renderiza el DDL.
- **Downgrade**: elimina el CHECK y la columna `status` (reversible, sin pérdida de otros datos).
- **Modelo alineado**: `models.py::DriverProfile.status` con `default='pending'`, `server_default='pending'` y el mismo CHECK; constantes `DRIVER_STATUS_*`/`DRIVER_STATUSES`.
- `is_verified` se conserva INTACTO: es legacy/presentación, no autoriza.

> **Validación**: 0003 cubierta por `tests/test_migration_0003.py` (12 tests: upgrade, backfill, CHECK, downgrade, modo offline, alineación con modelo) sobre SQLite en archivo, y el SQL offline para PostgreSQL fue validado (`test_render_sql_no_ejecuta_backfill` renderiza el DDL sin el UPDATE). 0002/0001 se prueban en el flujo `alembic upgrade head` de la suite. **NO validada contra PostgreSQL real**: el entorno local actual usa MySQL legacy y Docker no está disponible. La migración NO fue ejecutada en ninguna base real y NO debe presentarse como aplicada en producción; queda pendiente ejecutar `alembic upgrade head` contra PostgreSQL local (`docker-compose.yml`) o de desarrollo.

---

## 7. API v1 — contrato y estado de implementación

- Contrato definitivo: `docs/api-contract-v1.md` (APROBADO 2026-08-10). Spec OpenAPI 3: `backend/api/openapi.yaml`, servido en `/api/v1/openapi.yaml`; Swagger UI en `/api/v1/docs`.
- Envelope: éxito `{"success": true, "data": ...}`; error `{"success": false, "error": {"code": "CODE", "message": "..."}}`. `code` estable (catálogo en `backend/api/errors.py`) — Flutter parsea SOLO `code`.
- Dinero como **string decimal** en JSON; fechas ISO 8601 UTC (`serializers.py`). Paginación `?page=&limit=` (default 20, máx 100, clamp server-side).
- Idempotencia por header `Idempotency-Key` (contrato §11; tabla `api_idempotency_keys` — pendiente de crear en etapa de trips).
- Flujo Flutter: login/register → guardar ambos tokens; `TOKEN_EXPIRED` → `POST /auth/refresh`; access como `Authorization: Bearer <token>`.

### Estado por etapa

> Numeración de implementación: **Etapa 1 = migración 0003**. Difiere de la numeración de `docs/api-contract-v1.md` §16 (que numera los módulos API como etapas 1–7); en el seguimiento actual Trips API = **Etapa 2**.

| Etapa | Contenido | Estado |
|-------|-----------|--------|
| 0 | Infraestructura: `errors.py` (catálogo), `decorators.py` (`jwt_required`, `require_mode`), `pagination.py`, `serializers.py`, `jwt.py`, endpoints auth, `openapi.yaml` | ✅ **Completada** (commit `1a2ab8ca`) |
| 1 | Migración 0003 — `driver_profiles.status` (contrato §7) + `tests/test_migration_0003.py` (12 tests) | ✅ **Completada** (sin commit) |
| 2 | **Trips API**: `POST /trips` (creación, fare estimate, ACTIVE_TRIP_EXISTS, company auto-asignado, idempotencia) | ⏳ **Pendiente — NO implementada** |
| 3 | GET/list/accept/reject/start/complete/cancel/rate/eta (`/trips*`) + máquina de estados | ⏳ Pendiente |
| 4 | Wallet: `/wallet`, transactions, topups, `POST /trips/{id}/pay` (ledger I1–I6) | ⏳ Pendiente |
| 5 | Ubicación: `/drivers/location`, `/drivers/online`, `/drivers/nearby`, `/geocode` | ⏳ Pendiente |
| 6 | Company: `/company`, members, trips | ⏳ Pendiente |
| 7 | Verificación y admin: `/drivers/verification` (GET/PUT), `/admin/drivers*` | ⏳ Pendiente |
| 8 | `test_trips_service.py` (unit services), regresión web completa | ⏳ Pendiente |

### Auth v1 — implementado (contrato Flutter)

| Método | Ruta | Propósito |
|--------|------|-----------|
| POST | `/api/v1/auth/register` | Registro pasajero → tokens + perfil |
| POST | `/api/v1/auth/register/driver` | Registro conductor (vehículo) → tokens + perfil (promueve a `both` si el email ya es pasajero) |
| POST | `/api/v1/auth/login` | `{email, password, mode?}` → tokens + perfil |
| POST | `/api/v1/auth/refresh` | `{refresh_token}` → par nuevo (rotación) |
| POST | `/api/v1/auth/logout` | `{refresh_token}` → revoca |
| GET | `/api/v1/auth/me` | Perfil del token |
| POST | `/api/v1/auth/switch-mode` | Cambia `mode` → access token nuevo (solo `both`) |
| POST | `/api/v1/auth/verify-email` | `{code}` con Bearer |

### Endpoints planificados (contrato §4 — NO implementados aún)

`POST/GET /trips`, `GET /trips?role=`, `GET /trips/available`, `POST /trips/{id}/accept|reject|start|complete|cancel|rate`, `GET /trips/{id}`, `GET /trips/{id}/eta`, `GET/POST /wallet*`, `POST /trips/{id}/pay`, `POST /drivers/location`, `POST /drivers/online`, `GET /drivers/nearby`, `GET /geocode`, `GET /company*`, `GET/PUT /drivers/verification`, `GET /admin/drivers*`, `POST /admin/drivers/{id}/verify`. Permisos y errores definidos en `docs/api-contract-v1.md` §§3–4.

---

## 8. Identidad unificada y modo dual (resumen operativo)

- `users.role` es la identidad permanente. **Nunca** se modifica por sesión ni token.
- `active_mode` (sesión web) / `mode` (JWT) es solo contexto: qué vista/token usar. Login `both` → elige modo (parámetro `mode` en login, `/select-mode` en web, `/auth/switch-mode` en v1).
- Promoción: registro de conductor con email de pasajero existente → `role='both'` + `driver_profile` nuevo (web y API).
- Autorización conductor (web y API): `role ∈ (driver, both)` + `driver_profile` existe + `status == 'approved'`.
- `driver_view()` (identity.py) es la capa de compatibilidad para templates legacy.
- **Pitfall SQLAlchemy**: no usar `user.driver_profile or DriverProfile(...)` tras asignar el profile (SQLAlchemy cachea `None`); asignar `user.driver_profile = DriverProfile(...)` y commitear de inmediato.

---

## 9. API JSON web legacy (sesión + CSRF)

Todas requieren `X-CSRF-Token` header (obtener de `window.CSRF_TOKEN`) salvo los webhooks. **No cambian de URL ni de formato** (contrato §15).

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
| GET | `/api/trip/<id>/status` · `/eta` · `/driver-eta` | Estado del viaje / ETA |
| GET | `/api/driver/payment-methods` · POST · DELETE `/api/driver/payment-methods/<id>` | CRUD métodos del conductor |
| GET | `/api/wallet/balance` · `/api/wallet/transactions` · `/api/driver/wallet/*` | Billetera |
| POST | `/api/wallet/topup` · `/api/wallet/topup/cvu` · `/api/wallet/topup/voucher` · `/api/wallet/topup/webhook` (sin CSRF) | Cargas de billetera |
| GET | `/api/wallet/cvu-info` · `/api/wallet/bank-info` | Datos para transferencia |
| POST | `/api/wallet/pay-driver` | Pago a conductor desde billetera |
| POST | `/api/account/export` · `/api/account/delete` | GDPR |
| POST | `/api/upload-photo`, `/api/accept-guidelines`, `/api/favorites` | Perfil y favoritos |
| GET/POST | `/api/driver/mercadopago-qr`, `/api/user/payment-methods` | Métodos de pago |
| POST | `/company/api/create_preference` · `/company/payment/webhook` (sin CSRF) | Checkout MP empresa |
| GET | `/company/api/members` · `/company/api/trips` · POST `/company/api/invite` · DELETE `/company/api/members/<id>/remove` | Portal empresa |
| POST | `/admin/topups/<id>/confirm\|reject` · `/admin/drivers/<id>/verify` | Admin |

### Rutas HTML (POST con CSRF)

`/register`, `/login`, `/select-mode`, `/switch-mode`, `/driver/register`, `/passenger/request`, `/driver/accept/<id>`, `/driver/start/<id>`, `/driver/complete/<id>`, `/forgot-password`, `/reset-password`, `/profile/edit`, `/account/settings`, `/admin/login`, `/admin/logout`, rutas `/company/*` y de pago.

### Tarifa (contrato de negocio — `backend/services/fare.py`)

```
fare = max(BASE + km * POR_KM + min * POR_MIN, MINIMA)
```

| Vehículo | BASE | POR_KM | POR_MIN | MINIMA |
|----------|------|--------|---------|--------|
| Moto | 3.0 | 1.5 | 0.25 | 5.0 |
| Auto | 4.5 | 2.0 | 0.30 | 7.0 |

Al completar el viaje se persiste `total_fare = platform_fee + driver_earnings` (comisión `PLATFORM_FEE_RATE` env, 5% default — calculada y guardada pero **NO cobrada aún**, Fase 4).

### Ciclo de vida del viaje

```
requested → accepted → ongoing → completed
        └──────────→ cancelled (pasajero | conductor | system: timeout 5 min)
```

Máquina de estados completa de la API v1 (transiciones, actores y errores): `docs/api-contract-v1.md` §6.

### Estados de empresa

`trial` → `active` | `pending_payment` | `inactive`

### Métodos de pago (claves)

`efectivo` · `mercadopago` · `transferencia` · `tarjeta` · `billetera`

---

## 10. Modelo de negocio

### 10.1 Segmentos

1. **Pasajeros (B2C)**: pagan la tarifa del viaje (efectivo, billetera con top-up, MercadoPago, tarjeta).
2. **Conductores (C2C oferta)**: registran vehículo (moto/auto), se ponen online, aceptan viajes y cobran. Deben estar `approved` (status) para operar.
3. **Empresas (B2B)**: plan mensual, gestionan viajes para empleados (miembros, `max_employees`).

### 10.2 Fuentes de ingreso de VAN

- **Suscripción B2B**: planes `basic` (default, max 15 empleados) y `advanced`; `trial` → pago MP o transferencia (confirmación admin).
- **Comisión por viaje (Fase 4)**: `platform_fee` ya se calcula y persiste (`PLATFORM_FEE_RATE`); el cobro real (movimiento contable de plataforma) entra con la cuenta interna y `COMMISSION_ACTIVE` en Fase 4.

### 10.3 Billetera (ledger I1–I6, contrato §8)

- Pasajero y conductor tienen `balance` (Numeric 12,2) unificado por user (el `both` no divide dinero).
- Carga: MercadoPago (webhook, dedup por `mp_payment_id`), CVU, voucher (aprobado por admin).
- Pagos: al completar con `billetera` y saldo → débito pasajero + crédito conductor pareados (mismo `payment_ref`); saldo insuficiente → débito `pending` sin crédito (pagable después con `pay`). Todo auditable en `wallet_transactions`.
- Invariantes: `total_fare = platform_fee + driver_earnings` (I1); nunca se debita de más (I2/I3); sin crédito sin débito pareado (I4); comisión reconocida pero no extraída (I5); una sola pareja de movimientos por acción (I6, locks + Idempotency-Key).

### 10.4 Verificación y confianza

- Conductores: `driver_profiles.status` (pending → admin approve → approved | rejected; rejected → resubida → pending). Backfill 0003: existentes → approved.
- Ratings recíprocos 1–5; guidelines (`accepted_guidelines`) requerido; GDPR: export/delete.

---

## 11. Workstreams

### Web legacy (completados)

| WS | Nombre | Estado |
|----|--------|--------|
| W0.1 | Fundación y ramp-up | ✅ Completado |
| W0.2 | Autenticación y perfiles | ✅ Completado |
| W0.3 | Solicitud y geolocalización | ✅ Completado |
| W0.4 | Ciclo de vida del viaje | ✅ Completado |
| W0.5 | Pagos y billetera | ✅ Completado |
| W0.6 | Empresas B2B | ✅ Completado |
| W0.7 | Admin y moderación | ✅ Completado (base) |
| W0.8 | Seguridad y hardening | ✅ Completado (base) |
| W0.9 | Producción y despliegue | ✅ Completado |
| W0.10 | Calidad y tests | ✅ Completado (base) |

### Fase 1 — Backend para Flutter (en curso)

| WS | Nombre | Estado |
|----|--------|--------|
| W1.0 | API v1 — infraestructura y auth (etapa 0: errors, decorators, pagination, serializers, jwt, auth, openapi) | ✅ Completado |
| W1.1 | Verificación del conductor — migración 0003 `driver_profiles.status` (etapa 1, contrato §7) + `tests/test_migration_0003.py` | ✅ Completado (sin commit) |
| W1.2 | API v1 — Trips API (etapa 2: `POST /trips` + idempotencia) | ⏳ Pendiente |
| W1.3 | API v1 — ciclo de vida de trips (etapa 3: list/get/accept/reject/start/complete/cancel/rate/eta) | ⏳ Pendiente |
| W1.4 | API v1 — wallet/ledger (etapa 4) | ⏳ Pendiente |
| W1.5 | API v1 — ubicación/geocode (etapa 5) | ⏳ Pendiente |
| W1.6 | API v1 — company (etapa 6) | ⏳ Pendiente |
| W1.7 | API v1 — verificación/admin (etapa 7) + servicios y regresión (etapa 8) | ⏳ Pendiente |

### Fases siguientes

| WS | Nombre | Fase | Estado |
|----|--------|------|--------|
| W2.x | App Flutter (pasajero + conductor, Google Play) | Fase 2 | ⏳ Pendiente |
| W3.x | Tiempo real (Socket.IO + Redis, ubicación, matching) | Fase 3 | ⏳ Pendiente |
| W4.x | Monetización (comisión, suscripciones, wallet, Mercado Pago) | Fase 4 | ⏳ Pendiente |
| W5.x | Infraestructura (R2, Celery — PostgreSQL+Alembic ya adoptados) | Fase 5 | ⏳ Parcial |
| W6.x | Escalabilidad (multi-ciudad, referidos, surge pricing, analíticas, IA) | Fase 6 | ⏳ Pendiente |

**Regla de workstreams**: todo PR/cambio debe declarar a qué workstream pertenece. Un workstream se cierra solo con tests verdes y spec actualizado.

---

## 12. Tests

Baseline actual: **149 tests, 0 fallos** (`python -m pytest -q`, SQLite `:memory:`, app fresca por método).

| Archivo | Cubre |
|---------|-------|
| `test_api_auth.py` | API v1 auth: register (pasajero/conductor/promoción a both), login (roles, mode), me, switch-mode, refresh (rotación, reuso), logout, verify-email, openapi/docs |
| `test_api_decorators.py` | `require_mode`: 401/403, MODE_NOT_ALLOWED, conductor sin profile, `status != approved` → NOT_VERIFIED, claim `mode` nunca autoriza |
| `test_api_errors.py` | Catálogo de errores, ApiError, envelope, serializers (money_str, iso_dt, public_user) |
| `test_api_pagination.py` | Paginación: defaults, clamp 100, página inválida, estructura `{items, pagination}` |
| `test_fare.py` | Tarifas Decimal, mínimas, invariante total_fare, comisión configurable (monkeypatch PLATFORM_FEE_RATE) |
| `test_migration_0003.py` | Migración 0003 (12 tests): upgrade/backfill/CHECK/downgrade/offline + alineación con modelo |
| `test_security.py` | CSRF web (form/JSON), admin sessions |
| `test_trip_lifecycle.py` | Ciclo de vida web: request/accept/start/complete/cancel |
| `test_wallet.py` | Billetera: pay-driver, cobro al completar, saldo insuficiente |
| `test_web_modes.py` | Modo dual web: select-mode, switch-mode, sesiones por rol |
| `conftest.py` | Fixture `app` (create_app fresca por método, SQLite `:memory:`) |

**Warnings conocidos (no bloquean)**: `Query.get()` legacy SQLAlchemy 2.0 (pendiente migrar a `db.session.get()`), `datetime.utcnow()` deprecado, flask-limiter en memoria en tests. Sin lint/CI configurados — responsabilidad del agente mantener calidad.

---

## 13. Reglas de desarrollo

1. **Fuente de verdad**: código > tests > migraciones > ADRs > `docs/api-contract-v1.md` > `AGENTS.md` > este spec. Si algo cambia, actualizar `AGENTS.md`, `README.md` y este spec.
2. **Tests sin BD real**: siempre `python -m pytest tests/ -v` (SQLite `:memory:`). No afirmar validación en PostgreSQL sin ejecutarla contra la BD real.
3. **Toda ruta de mutación web requiere CSRF**; la API v1 usa JWT Bearer (sin cookies, sin CSRF).
4. **Nunca renombrar columnas históricas** sin migración explícita y aprobación (`is_ocupado` es alias de presentación vía `driver_view()`).
5. **`.env` solo en `backend/.env`**; nunca commitear. `SECRET_KEY` obligatoria en producción; `JWT_SECRET_KEY` recomendada dedicada.
6. **Migraciones**: cadena Alembic; toda migración con upgrade/downgrade, backfill explícito, constraints con nombre, y pruebas (SQLite batch para verificar); datos protegidos con `is_offline_mode()`.
7. **No agregar dependencias** sin justificación y sin actualizar `requirements.txt` (pin exacto) y este spec (nueva decisión D#).
8. **No tocar la landing `/`**: sirve `demo/index.html` si existe, sino `templates/index.html`.
9. **Verificación**: después de cambios, correr tests. Sin lint/CI — responsabilidad del agente.
10. **Compatibilidad SQLite ↔ PostgreSQL**: no usar features específicas de un motor en código compartido (tests corren en SQLite).
11. **Errores**: nunca loggear secretos, tokens (especialmente refresh tokens — tabla guarda hash SHA-256, ADR-002) ni datos de pago. Dinero siempre Decimal.
12. **Timestamps**: `datetime.utcnow()` (convención actual; al eliminarse la deprecación migrar a `datetime.now(timezone.utc)` en bloque).
13. **Commit style**: mensajes concisos; no commitear sin pedido explícito.
14. **Pitfall SQLAlchemy**: asignar `user.driver_profile = DriverProfile(...)` y commitear de inmediato; no usar `or` sobre la relación tras asignar.

---

## 14. Estándares de código

### Python / Flask

- **PEP 8**: indentación 4 espacios, `snake_case` funciones/variables, `CamelCase` clases.
- Blueprints con `@<bp>.route()`; decoradores y validaciones compartidas en `validators.py` (web+API — no duplicar reglas).
- Dinero en `Decimal` (`services/fare.py`), nunca float en JSON ni en columnas de dinero.
- Respuestas web: `jsonify({'error': ...})` con códigos HTTP correctos (401/403/429, JSON en `/api/*`).
- Respuestas API v1: envelope `{success, data}` / `{success, error:{code,message}}` — `code` del catálogo, nunca inventar códigos.
- `db.session.commit()`/`rollback()` en `teardown_appcontext` (ya implementado en `app.py`).
- No añadir comentarios salvo que aporten contexto real (typos históricos, decisiones, quirks).

### Frontend / JS

- JS vainilla, sin transpilación ni bundlers. `window.CSRF_TOKEN` para `X-CSRF-Token`.
- Textos de UI en español. Mapas Leaflet + tiles OSM; sin API keys de mapas.

### SQL / Migraciones

- Migraciones Alembic con revisiones cortas y descriptivas; constraints con nombre (`chk_*`, `uq_*`, `ix_*`, `fk_*`).
- Nuevas tablas: modelo SQLAlchemy + migración Alembic (no depender de `create_all` en prod).
- Nombres `snake_case`, timestamps `DATETIME`/`DateTime`, dinero `Numeric(12,2)`, booleans booleanos.

---

## 15. Glosario y quirks

- `status` (driver_profiles): **única fuente de autorización** del conductor. `is_verified`: legacy, solo presentación (`driver_view()`).
- `is_ocupado`: typo histórico intencional → hoy es `is_busy`; `driver_view()` lo expone como alias para templates.
- `.env` en `backend/.env`; `.env.example` en la raíz. `DATABASE_URL` PostgreSQL objetivo; sin él → SQLite local.
- `FLASK_DEBUG=1` para debug local; `PORT` env para puerto (default 5000).
- Landing `/` = `demo/index.html` si existe.
- VSCode asocia templates como `django-html`.
- Refresh tokens: nunca loguear el valor; la tabla guarda hash SHA-256 (ADR-002).
- API v1: `JWT_SECRET_KEY` (fallback `SECRET_KEY`), `JWT_ACCESS_TTL_MINUTES=30`, `JWT_REFRESH_TTL_DAYS=30`, `PLATFORM_FEE_RATE` (comisión), `DEFAULT_CURRENCY=ARS`.
- El branch MySQL legacy de `migration.py` emite WARN: el esquema `drivers` ya no es compatible con los modelos unificados; los datos legacy se migran con Alembic 0002 sobre PostgreSQL.

---

## 16. Estado al cierre de la jornada (2026-08-10)

Estado reproducible tras la **Etapa 1 — migración 0003** (verificación del conductor, contrato §7). La **Etapa 2 — Trips API NO fue implementada**.

### Validado localmente
- Suite completa: **149 tests passed, 0 failures** (`python -m pytest -q`).
- Migración 0003: upgrade/downgrade/backfill/CHECK/offline sobre SQLite en archivo (`tests/test_migration_0003.py`, 12 tests).
- SQL offline para PostgreSQL: `alembic upgrade --sql` renderiza ADD COLUMN + CHECK sin ejecutar el UPDATE de backfill.
- `git diff --check` limpio.

### NO validado todavía
- Ejecución real de la migración sobre **PostgreSQL** (entorno local actual usa MySQL legacy; Docker no disponible). La cadena 0001→0002→0003 **no fue aplicada a ninguna base real**; no debe presentarse como aplicada en producción.

### Working tree (SIN commit — pendiente de commitear)
- Modificados: `AGENTS.md`, `VAN_MASTER_SPEC.md`
- Nuevos: `migrations/versions/0003_driver_profile_status.py`, `tests/test_migration_0003.py`

### Próximo incremento del roadmap
**Etapa 2 — Trips API** (`POST /trips`: creación, fare estimate con `PLATFORM_FEE_RATE`, `ACTIVE_TRIP_EXISTS`, `company_id` auto-asignado, idempotencia con header `Idempotency-Key` y tabla `api_idempotency_keys`). Referencia: `docs/api-contract-v1.md` §§4–5, 11 y 16. Requiere TDD (`tests/test_api_trips.py`) y, antes de cerrar, validación de la cadena de migraciones contra PostgreSQL real.
