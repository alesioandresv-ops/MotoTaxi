# VAN — MASTER SPEC

> Documento maestro del proyecto. Define visión, decisiones técnicas aprobadas, arquitectura, roadmap, reglas de desarrollo, estándares de código, convenciones de API, modelo de negocio y workstreams.
>
> Última actualización: 2026-08-24 · Estado: **Activo** · Fuente de verdad técnica: código en `backend/`, `tests/`, `migrations/`, ADRs en `docs/adr/`, `docs/api-contract-v1.md` y `AGENTS.md` (en ese orden de autoridad).

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
| D15 | **Tests: pytest + pytest-flask con SQLite `:memory:`** | ✅ Aprobada | App fresca por método. Suite actual: **179 tests** (ver §12). |
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

### 3.3 Modelo de datos (esquema unificado — 15 tablas)

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
- **topup_requests** — cargas: MercadoPago/CVU/voucher, `mp_payment_id` (dedup, UNIQUE parcial), `preference_id` (trazabilidad de preferencia Checkout Pro, nullable — migración 0007), aprobación admin.
- **refresh_tokens** — API v1: `token_hash` SHA-256 UNIQUE, `expires_at`, `revoked_at`, `replaced_by_id`, FK → users (CASCADE).
- **email_verifications** — códigos de verificación (hash, intentos, expiración).
- **api_idempotency_keys** — respuestas guardadas para replays idempotentes API v1: UNIQUE `(user_id, key, method)`, `response_body` JSON, TTL 24 h con limpieza perezosa (migración 0004).

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
| **Fase 1** | **Backend para Flutter**: API REST `/api/v1`, JWT + refresh tokens, OpenAPI/Swagger, **web intacta** | 🔄 **EN CURSO** (Etapas 0, 1 y 2 COMPLETAS; **Etapa 3 — ciclo de vida de trips** y siguientes pendientes, ver §7/§9) |
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

> **Validación**: 0003 cubierta por `tests/test_migration_0003.py` (12 tests: upgrade, backfill, CHECK, downgrade, modo offline, alineación con modelo) sobre SQLite en archivo. La cadena 0001→0002→0003 **fue validada contra PostgreSQL real** (commit `ef5e6ee0`, 2026-08-20).

### 0004 — `0004_idempotency_keys.py` (idempotencia API v1 — contrato §8.3/§11)
- **Upgrade**:
  - Crea `api_idempotency_keys`: `user_id` (FK CASCADE), `key`, `method`, `path`, `status_code`, `response_body` (JSON Text), `created_at`; UNIQUE `uq_idempotency_user_key_method` (la clave es por usuario: un cliente no puede clonar claves de otro); índices por `user_id` y `created_at` (limpieza perezosa TTL 24 h).
  - `trips.idempotency_key VARCHAR(255)` nullable + UNIQUE `uq_trips_passenger_idempotency` (trazabilidad; mecanismo principal = header).
  - Sin backfill de datos → no requiere `_online()`.
- Nota: el contrato ubicaba estas columnas en la "migración 0003"; ese número ya estaba tomado → es 0004.
- **Downgrade**: elimina constraint/columna y la tabla (reversible).
- Usa `batch_alter_table` para ser testeable en SQLite.
- > **Validación**: cubierta por `tests/test_migration_0004.py` (6 tests) sobre SQLite en archivo + SQL offline renderizado (`0003:0004 --sql`). **NO ejecutada aún contra PostgreSQL real**.

### 0005 — `0005_trip_payment_tracking.py` (cobro al finalizar)
- **Upgrade** (`batch_alter_table`, testeable en SQLite):
  - `trips.payment_status VARCHAR(20) NOT NULL` con `server_default 'pending'`; CHECK `chk_trip_payment_status` (`pending|paid`); constantes `TRIP_PAYMENT_PENDING/PAID/STATUSES` en `models.py`.
  - `trips.paid_at DATETIME NULL` y `trips.payment_method_collected VARCHAR(50) NULL`.
  - **Backfill selectivo** protegido con `_online()` (`is_offline_mode()`): SOLO viajes `completed` → `'paid'` (ya cobrados por definición); requested/accepted/ongoing/cancelled quedan `pending`.
- **Downgrade**: elimina CHECK y las 3 columnas (reversible, sin pérdida de otros datos).
- > **Validación**: `tests/test_migration_0005.py` (12 tests). **Ejecutada contra PostgreSQL real** (upgrade automático `0004 -> 0005` al arrancar la app, 2026-08-24).

### 0006 — `0006_trip_payment_dedup.py` (índice único parcial recargas MP)
- **Upgrade**: UNIQUE parcial `uq_topup_requests_mp_payment_id` sobre `topup_requests.mp_payment_id WHERE mp_payment_id IS NOT NULL` (`sqlite_where`/`postgresql_where`). Blinda a nivel BD la idempotencia del webhook de MercadoPago: el pre-check SELECT-then-INSERT de `_credit_mp_payment()` deja una ventana de carrera ante retries concurrentes; un INSERT duplicado ahora revienta con IntegrityError y se revierte.
- Parcial porque las recargas manuales (transferencia/voucher sin MP) tienen `mp_payment_id NULL` y deben permitirse múltiples.
- **Downgrade**: elimina el índice (reversible).
- > **Validación**: `tests/test_migration_0006.py` (6 tests sobre SQLite en archivo). Ejecutada contra PostgreSQL real (`alembic upgrade head`, 2026-08-24).

### 0007 — `0007_topup_preference_id.py` (trazabilidad de preferencias MP)
- **Upgrade**: columna nullable `topup_requests.preference_id` (String(100)). Al crear una preferencia Checkout Pro de recarga, `services/mercadopago.create_topup_preference()` persiste `TopUpRequest(status='pending', preference_id=...)` ANTES de redirigir al usuario — si el webhook nunca llega (localhost, caída de MP), queda evidencia para reconciliación manual contra `/v1/payments/search`.
- Nullable sin backfill: recargas manuales (transferencia/voucher) no tienen preferencia.
- **Downgrade**: elimina la columna (reversible; `batch_alter_table` para ser testeable en SQLite).
- > **Validación**: `tests/test_migration_0007.py` (6 tests). **Ejecutada contra PostgreSQL real** (`python migrate.py`, 2026-08-24).

---

## 7. API v1 — contrato y estado de implementación

- Contrato definitivo: `docs/api-contract-v1.md` (APROBADO 2026-08-10). Spec OpenAPI 3: `backend/api/openapi.yaml`, servido en `/api/v1/openapi.yaml`; Swagger UI en `/api/v1/docs`.
- Envelope: éxito `{"success": true, "data": ...}`; error `{"success": false, "error": {"code": "CODE", "message": "..."}}`. `code` estable (catálogo en `backend/api/errors.py`) — Flutter parsea SOLO `code`.
- Dinero como **string decimal** en JSON; fechas ISO 8601 UTC (`serializers.py`). Paginación `?page=&limit=` (default 20, máx 100, clamp server-side).
- Idempotencia por header `Idempotency-Key` (contrato §11; tabla `api_idempotency_keys` creada por migración 0004; implementada para `POST /trips` en Etapa 2, se extenderá a accept/start/complete/cancel/pay/topups en etapas siguientes).
- Flujo Flutter: login/register → guardar ambos tokens; `TOKEN_EXPIRED` → `POST /auth/refresh`; access como `Authorization: Bearer <token>`.

### Estado por etapa

> Numeración de implementación: **Etapa 1 = migración 0003**. Difiere de la numeración de `docs/api-contract-v1.md` §16 (que numera los módulos API como etapas 1–7); en el seguimiento actual Trips API = **Etapa 2**.

| Etapa | Contenido | Estado |
|-------|-----------|--------|
| 0 | Infraestructura: `errors.py` (catálogo), `decorators.py` (`jwt_required`, `require_mode`), `pagination.py`, `serializers.py`, `jwt.py`, endpoints auth, `openapi.yaml` | ✅ **Completada** (commit `1a2ab8ca`) |
| 1 | Migración 0003 — `driver_profiles.status` (contrato §7) + `tests/test_migration_0003.py` (12 tests) | ✅ **Completada** (commit `5f243faf`) |
| 2 | **Trips API (creación)**: `POST /trips` con idempotencia obligatoria (`Idempotency-Key` + tabla `api_idempotency_keys`, migración 0004), fare estimate, `ACTIVE_TRIP_EXISTS`, company auto-asignado (D9); lógica en `backend/services/trips.py` + endpoint en `backend/api/trips.py`; tests `test_api_trips.py` (24) y `test_migration_0004.py` (6) | ✅ **Completada** (sin commit) |
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

### Trips v1 — implementado (Etapa 2)

| Método | Ruta | Propósito |
|--------|------|-----------|
| POST | `/api/v1/trips` | Crea viaje. Header `Idempotency-Key` obligatorio; replay → 200 con el mismo trip y `duplicate:true`. Errores: VALIDATION_ERROR, INVALID_VEHICLE_TYPE, INVALID_PAYMENT_METHOD, ACTIVE_TRIP_EXISTS. Lógica en `backend/services/trips.py`; serializer canónico `serialize_trip` (contrato §5.1) |

### Endpoints planificados (contrato §4 — NO implementados aún)

`GET /trips`, `GET /trips?role=`, `GET /trips/available`, `POST /trips/{id}/accept|reject|start|complete|cancel|rate`, `GET /trips/{id}`, `GET /trips/{id}/eta`, `GET/POST /wallet*`, `POST /trips/{id}/pay`, `POST /drivers/location`, `POST /drivers/online`, `GET /drivers/nearby`, `GET /geocode`, `GET /company*`, `GET/PUT /drivers/verification`, `GET /admin/drivers*`, `POST /admin/drivers/{id}/verify`. Permisos y errores definidos en `docs/api-contract-v1.md` §§3–4. (`POST /trips` ya está implementado — Etapa 2.)

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
| POST | `/api/trip/<id>/collect-payment` | `{method}` — conductor cobra y finaliza (ver Ciclo de vida). Errores: FORBIDDEN 403, INVALID_STATUS 409, INVALID_METHOD 400/409, PAYMENT_INSUFFICIENT_BALANCE 409. Éxito: `{trip_id, status:'completed', payment_status:'paid', payment_method_collected, fare}` |
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

`/register`, `/login`, `/select-mode`, `/switch-mode`, `/driver/register`, `/passenger/request`, `/driver/accept/<id>`, `/driver/start/<id>`, `/forgot-password`, `/reset-password`, `/profile/edit`, `/account/settings`, `/admin/login`, `/admin/logout`, rutas `/company/*` y de pago.

> `/driver/complete/<id>` fue **eliminado**: finalizar el viaje ahora pasa por `POST /api/trip/<id>/collect-payment` (cobro obligatorio antes de completar).

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
requested → accepted → ongoing → collect-payment (cobro) → completed
        └──────────→ cancelled (pasajero | conductor | system: timeout 5 min)
```

- **`completed` SOLO se alcanza vía `finalize_trip()`** (`backend/services/trips.py`), invocada por `POST /api/trip/<id>/collect-payment`: el conductor confirma el método de pago real (puede cambiar el que eligió el pasajero) y el viaje se completa EN LA MISMA transacción que el cobro.
- `billetera` con saldo insuficiente → **bloquea la finalización** (`PAYMENT_INSUFFICIENT_BALANCE` 409); NO se crea deuda pendiente (mecanismo legacy eliminado) y el conductor elige otro método.
- Retry idempotente: `completed+paid` devuelve el resumen sin re-cobrar.
- `/driver/start` valida estado `accepted` (rechaza repetidos/otros estados).
- Polling web del conductor corre durante `accepted` Y `ongoing` (detecta cancelaciones tardías).
- Máquina de estados completa de la API v1 (transiciones, actores y errores): `docs/api-contract-v1.md` §6.

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
- Carga por MercadoPago Checkout Pro: `services/mercadopago.create_topup_preference()` crea la preferencia y persiste `TopUpRequest(status='pending', preference_id=…)` ANTES de redirigir (reconciliación si el webhook no llega). Acreditación ÚNICA vía `_credit_mp_payment()` (routes.py), que verifica el pago contra la API de MP antes de acreditar; dedup por registro confirmado + UNIQUE parcial 0006. Entradas: webhook `/api/wallet/topup/webhook` (firma manifest ts/v1 fail-closed si hay `MP_WEBHOOK_SECRET`; sin secret solo verificación server-side) + fallback `/wallet/topup/success` con `expected_user_id`. Otras cargas: CVU, voucher (aprobado por admin).
- Pagos: al finalizar con `billetera`, `wallet_transfer()` (`backend/services/wallet.py`) debita el TOTAL al pasajero y acredita `driver_earnings` al conductor (diferencia = comisión VAN retenida, aún no extraída — Fase 4), en la MISMA transacción que marca el viaje `completed`. **Saldo insuficiente → no se completa el viaje** (`PAYMENT_INSUFFICIENT_BALANCE`): sin débitos parciales ni deuda pendiente. Todo auditable en `wallet_transactions`.
- Invariantes: `total_fare = platform_fee + driver_earnings` (I1); nunca se debita de más (I2/I3); sin crédito sin débito pareado (I4); comisión reconocida pero no extraída (I5); una sola pareja de movimientos por acción (I6, locks por fila en orden determinista por id).
- `wallet_transfer()` NUNCA commitea: el caller dueño del caso de uso commitea todo-o-nada.

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
| W1.1 | Verificación del conductor — migración 0003 `driver_profiles.status` (etapa 1, contrato §7) + `tests/test_migration_0003.py` | ✅ Completado |
| W1.2 | API v1 — Trips API (etapa 2: `POST /trips` + idempotencia con migración 0004) + tests `test_api_trips.py`/`test_migration_0004.py` | ✅ Completado (sin commit) |
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

Baseline actual: **347 tests, 0 fallos** (`python -m pytest -q`, SQLite `:memory:`, app fresca por método).

| Archivo | Cubre |
|---------|-------|
| `test_api_auth.py` | API v1 auth: register (pasajero/conductor/promoción a both), login (roles, mode), me, switch-mode, refresh (rotación, reuso), logout, verify-email, openapi/docs |
| `test_api_decorators.py` | `require_mode`: 401/403, MODE_NOT_ALLOWED, conductor sin profile, `status != approved` → NOT_VERIFIED, claim `mode` nunca autoriza |
| `test_api_errors.py` | Catálogo de errores, ApiError, envelope, serializers (money_str, iso_dt, public_user) |
| `test_api_pagination.py` | Paginación: defaults, clamp 100, página inválida, estructura `{items, pagination}` |
| `test_api_trips.py` | Etapa 2 `POST /trips` (24 tests): auth/modo, validaciones (addresses, vehicle_type, payment_method, Idempotency-Key obligatoria/larga/body deprecated), ACTIVE_TRIP_EXISTS, fare estimate (rate 0.05, desactivada → rate null, snapshot = build_fare), company auto-asignado (D9: trial/active asigna, cliente ignorado, inactive/no membership → null), idempotencia (replay header 200 + mismo trip, claves aisladas por usuario, TTL 24 h re-ejecuta) |
| `test_fare.py` | Tarifas Decimal, mínimas, invariante total_fare, comisión configurable (monkeypatch PLATFORM_FEE_RATE) |
| `test_migration_0003.py` | Migración 0003 (12 tests): upgrade/backfill/CHECK/downgrade/offline + alineación con modelo |
| `test_migration_0004.py` | Migración 0004 (6 tests): tabla `api_idempotency_keys` + UNIQUE, `trips.idempotency_key` preservando filas, downgrade, offline solo DDL, alineación con modelo. Target fijo `'0004'` (no `head`) |
| `test_migration_0005.py` | Migración 0005 (12 tests): columnas de cobro, backfill selectivo completed→paid, CHECK, downgrade, offline sin UPDATE de datos |
| `test_migration_0006.py` | Migración 0006 (6 tests): índice único parcial `mp_payment_id`, duplicados rechazados, NULLs múltiples permitidos, downgrade |
| `test_migration_0007.py` | Migración 0007 (6 tests): columna `topup_requests.preference_id`, filas con/sin valor, índice 0006 sobrevive, downgrade |
| `test_mp_integration.py` | Integración MP post-auditoría (24 tests): firma manifest ts/v1 contra el SDK real (válida/secret distinto/data-id y request-id alterados/ausente fail-closed/sin secret dev), credenciales por entorno (`MP_ENV`, config errors), `create_topup_preference()` (persiste pending + preference_id, notification_url/auto_return solo con BASE_URL público, error no persiste, expiración best-effort), webhook wallet fail-closed (403 inválida/ausente, acredita válida), webhook empresa (firma, activación, monto mínimo, dedup retry) |
| `test_security.py` | CSRF web (form/JSON), admin sessions |
| `test_topup_credit.py` | `_credit_mp_payment()` con SDK de MP mockeado: acredita aprobados, dedup idempotente, rechaza usuario distinto (`expected_user_id`)/no aprobados/monto ≤0/sin token/SDK roto; webhook MP sin secret (ack, challenge GET, acciones irrelevantes) |
| `test_trip_finalize.py` | Unit `finalize_trip()`: billetera cobra y completa, efectivo no toca saldos, libera conductor, retry idempotente sin re-cobro, FORBIDDEN/INVALID_STATUS/INVALID_METHOD/PAYMENT_INSUFFICIENT_BALANCE sin mutar nada; `upsert_favorite_route()` crea/incrementa |
| `test_trip_lifecycle.py` | Ciclo de vida web: request/accept/start/cancel + complete vía `collect-payment` (paid + método) |
| `test_wallet.py` | Billetera: pay-driver, cobro al finalizar vía `collect-payment`, saldo insuficiente bloquea y permite cambiar método, no-cobrable por otro conductor, método inválido |
| `test_wallet_service.py` | Unit `wallet_transfer()`: simétrica/asimétrica (comisión), transacciones espejadas, rollback del caller deshace todo, INVALID_AMOUNT/USER_NOT_FOUND/INSUFFICIENT_BALANCE sin escrituras parciales |
| `test_web_modes.py` | Modo dual web: select-mode, switch-mode, sesiones por rol |
| `conftest.py` | Fixture `app` (create_app fresca por método, SQLite `:memory:`); sentinelas `MP_ENV`/tokens MP para hermeticidad ante dotenv |

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
- Idempotencia API v1: replay devuelve la respuesta guardada con el MISMO trip y `duplicate:true`; UNIQUE `(user_id, key, method)` en `api_idempotency_keys`; TTL 24 h con limpieza perezosa.
- Alembic `env.py` resuelve la URL desde `DATABASE_URL` del entorno (ignora `sqlalchemy.url` del ini en modo online): los tests de migración deben hacer `monkeypatch.setenv('DATABASE_URL', ...)` (patrón de `test_migration_0003/0004.py`). En modo offline sin estado de BD, `upgrade --sql` renderiza desde la base: usar rango (`0003:0004`) para aislar una revisión.
- **Import circular `services.trips ↔ backend.api`**: `backend/api/__init__` importa `api.trips`, que importa `backend.services.trips`; si este a su vez importara `backend.api.errors` a nivel de módulo, un import directo de `backend.services.trips` rompe la app (parcialmente inicializado). Regla: los servicios NUNCA importan `backend.api.*` en el tope — `ApiError` se importa tardío dentro de `create_trip()`. Mismo patrón en `routes.py` para `services.trips`/`services.wallet`.
- `wallet_transfer()` y `finalize_trip()` NO commitean: el caller commitea todo-o-nada (cobro + estado del viaje) y hace rollback si llega una excepción de negocio (`WalletTransferError`/`TripFinalizeError`).
- IDs de revisión Alembic cortos (`'0005'`, `'0006'`) — no confundir con el nombre del archivo. Los tests de migración fijan target explícito (`'0005'`, `'0006'`, `'0004'`): nunca `'head'`, porque el fixture mínimo no crea tablas que migraciones futuras puedan tocar.
- **MercadoPago (auditoría 2026-08-24)**: TODO pasa por `backend/services/mercadopago.py` — credenciales por entorno vía `MP_ENV` (`test` → `MERCADOPAGO_TEST_ACCESS_TOKEN`, `production` → `MERCADOPAGO_ACCESS_TOKEN`; default production), firma de webhooks manifest ts/v1 con el validador del SDK oficial (≥3.4), y `create_topup_preference()`. Nada debe leer tokens MP directo de `os.getenv`.
- Webhooks MP **fail-closed**: si `MP_WEBHOOK_SECRET` está configurado, notificación sin firma válida → 403 (wallet `routes.py` + empresa `company.py`). Sin secret (dev) se acepta, pero la acreditación/activación SIEMPRE exige verificación server-side del pago contra la API de MP antes de tocar dinero.
- El token en `.env` es de PRUEBA (usuario TESTUSER…): solo paga logueado como usuario comprador de prueba con tarjetas de prueba; pagar con cuenta real procesa DINERO REAL (`live_mode:true`).
- Tests herméticos ante dotenv: `tests/conftest.py` precarga sentinelas `MP_ENV`/tokens MP porque `load_dotenv()` en `backend/app.py` filtra el `backend/.env` real al proceso de pytest (dotenv no pisa variables ya existentes). Cada test ajusta su entorno con monkeypatch.
- El branch MySQL legacy de `migration.py` emite WARN: el esquema `drivers` ya no es compatible con los modelos unificados; los datos legacy se migran con Alembic 0002 sobre PostgreSQL.

---

## 16. Estado al cierre de la jornada (2026-08-25)

Estado reproducible tras completar la **Fase A — API v1 completa** (A1–A6) y **inicio de Fase B — App Flutter**.

### Validado localmente
- Suite completa: **441 tests passed, 0 failures** (`python -m pytest -q`; baseline previo 347 → 441).
- 6 grupos de tests nuevos: A1 Driver Location/Online/Nearby (34), A2 Trip Status Polling (8), A3 Profile Edit/Photo/Password/Guidelines (24), A4 Driver Config (14), A5 Passenger Extras (14), total +94 tests.

### API v1 completa — 24 endpoints (esta sesión)

#### A1 — Driver Location + Online + Nearby (3 endpoints)
- `POST /drivers/location` — conductor envía su ubicación (lat, lng). Solo si online. Error `NOT_ONLINE` si offline.
- `POST /drivers/online` — toggle online/offline. Invalida cache. Guarda posición si la tiene.
- `GET /drivers/nearby` — conductores online + libres ordenados por distancia. Opcional `vehicle_type`. No incluye al propio conductor.
- 34 tests: `tests/test_api_driver.py` TestDriverLocation (14) + TestDriverOnline (7) + TestDriversNearby (13).

#### A2 — Trip Status Polling (1 endpoint)
- `GET /trips/{id}/status` — payload ligero optimizado para polling cada 5s. Solo participantes. Incluye ubicación del conductor (`lat`, `lng`) para tracking en vivo.
- 8 tests: `tests/test_api_trips_lifecycle.py` TestTripStatus.

#### A3 — Profile Edit + Photo + Password + Guidelines (5 endpoints)
- `PUT /auth/profile` — editar nombre y teléfono. Valida name ≥2 chars.
- `POST /auth/profile/photo` — subir foto de perfil (base64 o data URL). Acepta cualquier imagen. Guarda como data URL en `profile_picture`.
- `POST /auth/password` — cambiar contraseña (requiere `current_password` + `new_password` ≥8 chars).
- `GET /auth/guidelines` — retorna `{accepted: bool}`. Si es true, el frontend no muestra el banner.
- `POST /auth/guidelines` — acepta las guidelines. Flag `guidelines_accepted` = True.
- 24 tests: `tests/test_api_profile.py`.

#### A4 — Driver Config (6 endpoints)
- `GET /driver/accepted-payments` — lista de métodos de pago aceptados (array de strings).
- `PUT /driver/accepted-payments` — actualizar lista. Reemplaza completa. Incluye `efectivo`, `mercadopago`, `transferencia`, `tarjeta`, `billetera`.
- `POST /driver/qr` — subir imagen QR de MercadoPago (base64). Guarda como data URL en `DriverProfile.qr_image`.
- `GET /driver/payment-methods` — listar métodos de cobro del conductor (cards, billeteras, etc).
- `POST /driver/payment-methods` — agregar método (type + details). Ej: `{type: "card", details: {last_four: "1234", brand: "visa"}}`.
- `DELETE /driver/payment-methods/{id}` — eliminar método propio. 404 si no existe.
- 14 tests: `tests/test_api_driver.py` TestAcceptedPayments (5) + TestDriverQR (3) + TestPaymentMethods (6).

#### A5 — Passenger Extras (4 endpoints)
- `GET /geo/geocode` — proxy a Nominatim (query param `q`). Retorna `{lat, lng, display_name}`. 404 si no encuentra. Fallback del backend.
- `GET /users/{user_id}/reviews` — reseñas recibidas por un usuario. Opcional `?role=driver` para ver reviews donde fue driver.
- `GET /favorites` — rutas frecuentes del pasajero (≥3 usos). Retorna `{items: [...]}`.
- `POST /wallet/topups/{id}/voucher` — subir comprobante de transferencia (base64). Solo transacciones propias, status `pending`.
- 14 tests: `tests/test_api_passenger_extras.py`.

#### A6 — OpenAPI actualizado
- `backend/api/openapi.yaml` actualizado con los ~19 endpoints nuevos de A1–A5. YAML válido verificado.

### Fix mapa Leaflet + production hardening (sesión anterior)
- **Bug mapa gris**: CSP `img-src` solo permitía `'self'` y `data:` — bloqueaba tiles de OpenStreetMap (`https://{s}.tile.openstreetmap.org/...`). Fix: agregar `https://*.tile.openstreetmap.org` al directive. Leaflet + OSM funciona correctamente, no era problema de la librería.
- **Requirements reorganizados**: `requirements.txt` = solo producción (sin pytest/pytest-flask, sin PyMySQL legacy). Nuevo `requirements-dev.txt` incluye dependencias de test.
- **Pillow pinnado exacto** (`==11.1.0`, antes `>=10.0.0` — riesgo de supply chain). PyMySQL eliminado (legacy MySQL ya no soportado).
- **Sentry**: `sentry-sdk[flask]==2.22.0` — init automático si `SENTRY_DSN` está definido en env. Traces al 10% en prod.
- **Log level configurable**: `LOG_LEVEL` env var (default `INFO`).
- **Cache busting**: `SEND_FILE_MAX_AGE_DEFAULT=31536000` (1 año) en prod, `0` en dev.
- **HTTP→HTTPS redirect**: `before_request` handler — 301 a HTTPS cuando `RAILWAY_ENVIRONMENT` o `SSL_ENABLED` están definidos.
- **`migration.py`**: `import pymysql` movido adentro de `_get_conn()` (condicional, solo se carga si se detecta MySQL legacy).
- **`.env.example` actualizado**: nuevas vars documentadas (`LOG_LEVEL`, `SENTRY_DSN`), referencia MySQL legacy eliminada.

### Runbook dev E2E recargas MP
1. Túnel público: `cloudflared tunnel --url localhost:5000` → `BASE_URL=https://…` en `backend/.env`.
2. Panel MP → Tus integraciones → Webhooks: URL `https://…/api/wallet/topup/webhook` (eventos "Pagos") → copiar la clave secreta a `MP_WEBHOOK_SECRET`.
3. Crear usuario comprador DE PRUEBA (devpanel) y pagar logueado como él con tarjetas de prueba (Mastercard `5474 9254 3267 0366`, CVV 123, vto 11/30; titular APRO aprueba / FUND sin fondos / CONT pendiente).
4. Sin túnel: localhost funciona igual vía back_urls + auto_return (success acredita server-side); solo no llegan webhooks.
5. Producción (van.com.ar): `BASE_URL=https://van.com.ar` + webhook del panel apuntando a `https://van.com.ar/api/wallet/topup/webhook`.

### Fase B — App Flutter (27 archivos creados)

#### Estructura core
- `pubspec.yaml`: dependencias (dio 5.4, flutter_secure_storage 9.0, go_router 14.0, google_maps_flutter 2.5, geolocator 11.0, geocoding 3.0, permission_handler 11.0, cached_network_image 3.3, qr_flutter 4.1, url_launcher 6.2, image_picker 1.0).
- `lib/main.dart`: entry point con `MaterialApp.router`.
- `lib/app/router.dart`: GoRouter con 11 rutas (`/login`, `/register`, `/home`, `/passenger/request`, `/trip/active`, `/trip/rate/:tripId`, `/driver`, `/driver/trip/:tripId`, `/wallet`, `/profile`, `/history`).
- `lib/app/theme.dart`: tema VAN (colores primary/accent/surface, botones, inputs, cards).
- `lib/core/api/api_client.dart`: cliente Dio con JWT interceptor + refresh automático + persistencia en FlutterSecureStorage.
- `lib/core/api/api_error.dart`: error model con helpers (`isTokenExpired`, `isInsufficientBalance`, etc).
- `lib/core/models/`: User, Trip, TripStatusUpdate, DriverInfo, VehicleInfo, Wallet, TopUpRequest, WalletTransaction, FavoriteAddress, Review, DriverPaymentMethod, DriverNearby.

#### Services
- `auth_service.dart`: register, login, refresh, logout, getMe, verifyEmail, switchMode, updateProfile, changePassword, uploadProfilePhoto.
- `trip_service.dart`: create, get, list, status (polling), available, accept, start, complete, cancel, rate, eta.
- `wallet_service.dart`: getWallet, getTransactions, createTopUp, listTopUps, getTopUp, getFavorites.
- `driver_service.dart`: updateLocation, setOnline, getNearbyDrivers, getAcceptedPayments, updateAcceptedPayments, uploadQr, getPaymentMethods, addPaymentMethod, deletePaymentMethod, geocode, getUserReviews.
- `location_service.dart`: Geolocator wrapper (getCurrentPosition, getPositionStream, distanceBetween).

#### Pantallas
- **Auth**: login_screen.dart (formulario email+password), register_screen.dart (nombre+email+teléfono+password).
- **Passenger**: passenger_home.dart (Google Maps + wallet card + botón solicitar), request_trip_screen.dart (origen+destino+vehículo+pago+busca conductores).
- **Trip**: active_trip_screen.dart (polling cada 5s + mapa con markers conductor/origen/destino + panel info), rate_trip_screen.dart (5 estrellas + comentario).
- **Driver**: driver_home_screen.dart (online toggle + mapa + viajes disponibles), driver_trip_screen.dart (iniciar/finalizar viaje).
- **Wallet**: wallet_screen.dart (saldo card + topup MP/transferencia + transacciones).
- **Profile**: profile_screen.dart (info + pagos conductor + links editar).
- **History**: history_screen.dart (viajes completados + cancelados).

### Pendiente o próximo a realizar
1. Instalar Flutter SDK + `flutter pub get` + configurar Google Maps API key.
2. `flutter run` y probar flujo completo E2E (registro → login → solicitar viaje → conductor acepta → viaje → calificación).
3. Build APK release para Google Play.
4. Configurar env vars en producción: `BASE_URL=https://van.com.ar`, `MP_ENV=production` + credenciales prod, `MP_WEBHOOK_SECRET`.
5. Opcional: `SENTRY_DSN` para error tracking.

### Próximo incremento del roadmap
**Fase B — App Flutter feature-complete**: construir todas las pantallas sobre la API v1 ya completa. Producción backend lista; pendiente configuración env vars: `BASE_URL=https://van.com.ar`, `MP_ENV=production` + credenciales prod, `MP_WEBHOOK_SECRET` en panel MP.
