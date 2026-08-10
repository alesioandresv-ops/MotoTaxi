# VAN — MASTER SPEC

> Documento maestro del proyecto. Define visión, decisiones técnicas aprobadas, arquitectura, roadmap, reglas de desarrollo, estándares de código, convenciones de API, modelo de negocio y workstreams.
>
> Última actualización: 2026-08-05 · Estado: **Activo** · Fuente de verdad técnica: código en `backend/`, `tests/` y `AGENTS.md`.

---

## 1. Visión del proyecto

**VAN** es una plataforma de solicitud de viajes urbano en moto y auto (estilo ride-hailing) pensada para el mercado hispanohablante, con foco en:

1. **Conectar pasajeros con conductores** en tiempo real: solicitud → aceptación → viaje → pago → calificación.
2. **Monetizar de dos formas**: tarifas por viaje (pasajero → conductor) y **suscripción B2B** (empresas que contratan viajes para empleados).
3. **Pagos flexibles**: efectivo, MercadoPago, transferencia, tarjeta y billetera interna con top-up (MercadoPago, CVU, voucher bancario).
4. **Cero dependencias de mapas propietarios**: mapas con Leaflet.js + OpenStreetMap y geocodificación con Nominatim.
5. **Lanzamiento rápido y de bajo costo**: stack Python monolítico que corre en un solo servidor (Railway/Docker) con MySQL.

La visión a mediano plazo: convertirse en la alternativa local y accesible a las apps internacionales de viajes, diferenciándose por **pago en billetera con carga manual, soporte de empresas y conductores verificados**, con tarifas transparentes.

---

## 2. Decisiones técnicas aprobadas

| # | Decisión | Estado | Detalle |
|---|----------|--------|---------|
| D1 | **Stack backend: Flask 3.1 (Python 3.12)** | ✅ Aprobada | Monolito simple, una sola app `create_app()` en `backend/app.py`. |
| D2 | **ORM: Flask-SQLAlchemy 3.1** | ✅ Aprobada | `db = SQLAlchemy()` en `backend/models.py`. Modelos: `User`, `Driver`, `Trip`, `Review`, `Company`, `CompanyMember`, `DriverPaymentMethod`, `PassengerPaymentConfig`, `FavoriteAddress`, `WalletTransaction`, `TopUpRequest`. |
| D3 | **Base de datos: MySQL (PyMySQL)** | ✅ Aprobada | `mysql+pymysql://` vía `DATABASE_URL`. Fallback a SQLite `:memory:` solo para tests/dev sin DB. |
| D4 | **Migraciones propias (sin Alembic)** | ✅ Aprobada | `backend/migration.py`: dicts `COLUMNAS`/`COLUMN_MODIFY` + `ALTER TABLE` inline vía pymysql, más `db.create_all()` para tablas nuevas. Idempotente; corre al arrancar la app, en `migrate.py` y en `start.sh`. |
| D5 | **Frontend: Jinja2 server-side + Leaflet.js** | ✅ Aprobada | Templates en `backend/templates/`, mapas con OSM. `demo/index.html` es la landing SPA con datos mock servida en `/` si existe. |
| D6 | **JS vainilla, sin framework** | ✅ Aprobada | No hay React/Vue. `window.CSRF_TOKEN` inyectado desde template. |
| D7 | **Autenticación por sesión (cookies), no JWT** | ✅ Aprobada | Session Flask, cookie `HttpOnly`, `SameSite=Lax`, `Secure` en producción (`RAILWAY_ENVIRONMENT`/`SSL_ENABLED`), lifetime 4 h. |
| D8 | **CSRF manual por sesión** | ✅ Aprobada | Token en `session['csrf_token']`, comparado con `hmac.compare_digest` en decorador `@csrf_required`. Acepta form, header `X-CSRF-Token` o campo JSON `csrf_token`. |
| D9 | **Rate limiting: Flask-Limiter** | ✅ Aprobada | Límites por IP en login y rutas sensibles. Handler 429 global. |
| D10 | **Sanitización: bleach** | ✅ Aprobada | `sanitize_input()`: strip HTML (tags vacíos) + truncado a 500 chars. |
| D11 | **Cifrado de datos de pago: Fernet** | ✅ Aprobada | `backend/extensions.py`: `encrypt_details()`/`decrypt_details()` con `ENCRYPTION_KEY` (cryptography). Prefijo `enc:`. |
| D12 | **Pagos: SDK mercadopago + webhooks** | ✅ Aprobada | Checkout para empresas y top-ups de billetera; webhook en `/api/wallet/topup/webhook` y `/company/payment/webhook`. |
| D13 | **Geocodificación: Nominatim (OSM)** | ✅ Aprobada | `/api/geocode`. Fallback a longitud de dirección si falla. |
| D14 | **Cálculo de distancia: haversine propio** | ✅ Aprobada | `calcular_distancia()` en `routes.py` (radio 6371 km), sin API externa. |
| D15 | **Tests: pytest + pytest-flask con SQLite `:memory:`** | ✅ Aprobada | App fresca por método. Sin MySQL requerido. `tests/`: `test_security.py`, `test_trip_lifecycle.py`, `test_wallet.py`. |
| D16 | **Servidor prod: Waitress** | ✅ Aprobada | `waitress-serve --listen=0.0.0.0:$PORT backend.app:app` en `start.sh`. |
| D17 | **Deploy: Railway + Docker** | ✅ Aprobada | `Dockerfile` (python:3.12-slim, usuario no-root) + `railway.json` (healthcheck `/health`). Detección de entorno vía `RAILWAY_ENVIRONMENT`. |
| D18 | **HTTPS**: Railway automático / Caddy+Let's Encrypt / Cloudflare Tunnel / cert autofirmado (`generate_cert.py`) | ✅ Aprobada | Cámara requiere HTTPS; documentado en README. |
| D19 | **Email de verificación SMTP** | ✅ Aprobada (opcional) | Solo se exige si `SMTP_USER`/`SMTP_PASS` están configurados. |
| D20 | **Multi-vehículo: moto y auto** | ✅ Aprobada | `vehicle_type` en `Driver` y `Trip`, campos separados `moto_*` / `auto_*`, tarifas diferenciadas. |
| D21 | **`is_ocupado` (typo intencional)** | ✅ Aprobada | Nombre de columna histórico en DB; NO renombrar (está en models y migration). |
| D22 | **Datos de pago del pasajero cifrados** | ✅ Aprobada | `PassengerPaymentConfig.details` y `DriverPaymentMethod.details` se guardan con Fernet. |

### Decisiones explícitamente rechazadas / descartadas

- **Alembic** para migraciones (se usa sistema propio idempotente).
- **JWT** para auth (se usa sesión server-side).
- **Google Maps / Mapbox** (descartado: Leaflet + OSM). `MAPBOX_TOKEN` ya no se usa.
- **Framework JS frontend** (React/Vue/etc.).
- **Celery / tareas asíncronas** (no hay colas; todo es síncrono o webhooks).

---

## 3. Arquitectura

### 3.1 Visión general

```
Browser (Jinja2 templates + Leaflet.js + JS vainilla)
        │  form/JSON + CSRF token
        ▼
Flask app (backend/app.py — create_app())
├── Blueprint auth   (backend/auth.py)     → /register, /login, /profile, /forgot-password…
├── Blueprint main   (backend/routes.py)   → HTML + APIs JSON (viajes, conductores, wallet, admin)
├── Blueprint company(backend/company.py)  → portal empresas B2B
├── migrations       (backend/migration.py)→ pymysql ALTER TABLE + db.create_all()
├── extensions       (backend/extensions.py)→ Limiter + Fernet
└── models           (backend/models.py)   → SQLAlchemy ORM
        │
        ▼
MySQL (prod) / SQLite :memory: (tests)
```

### 3.2 Capas y responsabilidades

| Componente | Archivo | Responsabilidad |
|------------|---------|-----------------|
| Factory | `backend/app.py` | Config, seguridad de sesión, headers, template filters, error handlers (404/500/429 con respuestas JSON en `/api/*`), inyección de CSRF, arranque de migraciones. |
| Auth | `backend/auth.py` | Registro pasajero/conductor, login, logout, verificación de email, perfil, foto de perfil, reset de password. |
| Routes | `backend/routes.py` | Ciclo de vida del viaje, geolocalización, conductores cercanos, favoritos, reviews, métodos de pago, guidelines, wallet (balance, top-ups, CVU, voucher, pay-driver), admin (topups, verificación de conductores), export/delete de cuenta. |
| Empresas | `backend/company.py` | Registro de empresa, planes (basic/advanced), pago con MercadoPago/transferencia, login, dashboard, invitación de miembros, trips. |
| Modelos | `backend/models.py` | 11 tablas ORM (ver §3.3). |
| Migraciones | `backend/migration.py` | `COLUMNAS` + `COLUMN_MODIFY` + `_ensure_columns` (ALTER idempotente) + `create_all`. |
| Seguridad | `backend/extensions.py` | `limiter` (Flask-Limiter), `encrypt_details`/`decrypt_details` (Fernet). |
| Tests | `tests/` | Pytest, app fresca por método, SQLite `:memory:`. |
| Scripts raíz | `migrate.py`, `setup.py`, `reset_db.py`, `create_demo_users.py`, `ver_usuarios.py`, `eliminar_usuario.py` | Operaciones de DB sin servidor. |
| Deploy | `Dockerfile`, `start.sh`, `railway.json`, `Procfile`, `Caddyfile`, `.nixpacks` | Build y run en producción. |

### 3.3 Modelo de datos (11 tablas)

- **users** — pasajeros: credenciales, balance (billetera), rating, verificación, foto.
- **drivers** — conductores: online/ocupado (`is_ocupado`), lat/lng, verificación, vehículo (moto o auto), métodos de pago aceptados, QR MercadoPago, balance.
- **trips** — viajes: pasajero + driver + company opcional, direcciones y coordenadas, distancia/duración, tarifa, estado, medio de pago, timestamps.
- **reviews** — calificaciones cruzadas (pasajero↔conductor), rol, rating 1–5.
- **companies** — empresas B2B: plan, estado (trial/active/inactive/pending_payment), suscripción, medio de pago.
- **company_members** — empleados de la empresa (rol, invitación).
- **driver_payment_methods** — cuentas del conductor (details cifrados con Fernet).
- **passenger_payment_configs** — configs de pago del pasajero (cifrados).
- **favorite_addresses** — direcciones frecuentes con contador.
- **wallet_transactions** — movimientos de billetera (user/driver/trip/amount/type/status).
- **topup_requests** — solicitudes de carga: MercadoPago, CVU, voucher; aprobadas por admin.

### 3.4 Flujo de datos del viaje

1. Pasajero solicita (`/passenger/request`): geocodifica origen/destino (Nominatim), calcula distancia (haversine) y tarifa.
2. Viaje queda `requested`; los conductores online+libres lo ven en `/api/trips/available`.
3. Conductor acepta (HTML `/driver/accept/<id>` o JSON `/api/driver/respond/<id>`).
4. `accepted` → `ongoing` (`/driver/start`) → `completed` (`/driver/complete`).
5. Cancelación posible (pasajero/conductor/`system` por timeout de 5 min en `cancel_stale_trips()`).
6. Rating posterior (`/api/trip/<id>/rate`) y pago (efectivo/MP/billetera).

### 3.5 Despliegue

- **Producción**: Railway (Dockerfile → `start.sh` → `migrate.py` → waitress). Healthcheck `/health`.
- **HTTPS**: automático en Railway; Caddy (dominio propio), Cloudflare Tunnel (testing en LAN) o cert autofirmado (local).
- **Local**: `python backend/app.py` (HTTP :5000), MySQL local `van`, `.env` en `backend/.env`.

---

## 4. Roadmap

### Estado actual (ya implementado)

- [x] Registro y login de pasajero y conductor (con vehículo moto y auto).
- [x] Solicitud de viaje, conductores cercanos, geocodificación OSM, Leaflet.
- [x] Ciclo completo del viaje + reviews + cancelación con timeout.
- [x] Billetera: balance, transacciones, top-ups (MercadoPago, CVU, voucher), pago a conductor, aprobación admin.
- [x] Métodos de pago cifrados (Fernet) y payments aceptados por conductor.
- [x] Empresas B2B: registro, planes, suscripción (MP/transferencia), miembros, trips.
- [x] Admin: login, top-ups, verificación de conductores.
- [x] Seguridad: CSRF, rate-limit, headers, sanitización, cifrado.
- [x] Tests de seguridad, ciclo de viaje y wallet.
- [x] Deploy Railway + Docker + HTTPS.

### Siguiente (plan)

| Fase | Alcance | Prioridad |
|------|---------|-----------|
| F1 | Notificaciones (email/push) y recordatorios | Alta |
| F2 | Matching automático / asignación por proximidad y rating | Alta |
| F3 | Panel analítico conductor y pasajero (viajes, ganancias, rating) | Media |
| F4 | Promociones y códigos de descuento | Media |
| F5 | Multi-idioma (ES/EN) | Baja |
| F6 | App móvil (PWA primero, luego nativa) | Baja |

---

## 5. Reglas de desarrollo

1. **Fuente de verdad**: el código y este documento. Si algo cambia, actualizar `AGENTS.md`, `README.md` y este spec.
2. **Sin servidor MySQL para correr tests**: siempre `python -m pytest tests/ -v` (SQLite `:memory:`).
3. **Toda ruta de mutación requiere CSRF**: form `csrf_token`, header `X-CSRF-Token` o campo JSON `csrf_token`. Nunca exponer rutas mutables sin `@csrf_required` + `@login_required`.
4. **Nunca renombrar columnas históricas** sin migración explícita y aprobación (ej.: `is_ocupado`).
5. **`.env` solo en `backend/.env`**; nunca commitear. `SECRET_KEY` es obligatoria en producción (la app no arranca sin ella).
6. **Migraciones**: agregar columnas nuevas a `COLUMNAS`/`COLUMN_MODIFY` en `backend/migration.py` y al modelo SQLAlchemy; la migración debe ser **idempotente** (no romper en DB fresca ni en DB vieja).
7. **No agregar dependencias** sin justificación y sin actualizar `requirements.txt` (pin exacto) y este spec (nueva decisión D#).
8. **No tocar la landing `/`**: sirve `demo/index.html` si existe, sino `templates/index.html`.
9. **Verificación**: después de cambios, correr tests. Sin lint/CI configurados — es responsabilidad del agente mantener calidad.
10. **Compatibilidad SQLite ↔ MySQL**: no usar features específicas de un motor en código compartido (tests corren en SQLite).
11. **Errores**: nunca loggear secretos, tokens o datos de pago (ni en texto plano). Datos de pago van cifrados con Fernet.
12. **Timestamps**: `datetime.utcnow` para `created_at`/`*_at` (convención existente; no mezclar con `datetime.now`).
13. **Commit style**: mensajes concisos, en la rama de trabajo; no commitear sin pedido explícito.

---

## 6. Estándares de código

### Python / Flask

- Estilo **PEP 8** con indentación de 4 espacios, nombres `snake_case` para funciones/variables, `CamelCase` para clases.
- Blueprints con decoradores `@<bp>.route()`; helpers y decoradores compartidos (`login_required`, `csrf_required`, `admin_required`, `sanitize_input`) viven en `routes.py`.
- Constantes de tarifa en mayúsculas (`TARIFA_BASE_MOTO`, etc.) al tope de `routes.py`.
- Respuestas JSON: `jsonify({'error': ...})` con códigos HTTP correctos; 401 no autorizado, 403 CSRF, 429 rate-limit, 404/500 JSON si la ruta empieza con `/api/`.
- `db.session.commit()`/`rollback()` en `teardown_appcontext` (ya implementado en `app.py`).
- No añadir comentarios salvo que aporten contexto real (typos históricos, decisiones quirks).

### Frontend / JS

- JS vainilla, sin transpilación ni bundlers.
- Token CSRF: usar `window.CSRF_TOKEN` para header `X-CSRF-Token` en fetch.
- Textos de UI en español.
- Mapas con Leaflet + tiles OSM; no introducir API keys de mapas.

### SQL / Migraciones

- `COLUMNAS` y `COLUMN_MODIFY` en orden alfabético por tabla, una entrada por columna, con tipo SQL explícito (MySQL).
- Nuevas tablas: agregar modelo SQLAlchemy + `db.create_all()` cubre la creación (ver `_ensure_columns`).
- Nombres en `snake_case`, timestamps `DATETIME`, dinero `DECIMAL(12,2)`, booleanos `TINYINT(1)`.

### Tests

- Un archivo por área (`test_security.py`, `test_trip_lifecycle.py`, `test_wallet.py`).
- App fresca por método (fixture en `tests/conftest.py`), SQLite `:memory:`.
- Cada test debe verificar tanto el caso feliz como el fallo (CSRF faltante, no autorizado, etc.).

---

## 7. Convenciones de API

### Autenticación y CSRF

- Sesión por cookie (HttpOnly, SameSite=Lax, Secure en prod).
- **Todas** las rutas POST/PUT/DELETE requieren CSRF: header `X-CSRF-Token` (recomendado para JSON) o `csrf_token` en form/body JSON.
- Respuesta 401 `{"error": "No autorizado"}` sin sesión; 403 `{"error": "CSRF token inválido"}`.

### Formato de respuesta

```json
{ "error": "mensaje" }            // error (código 4xx/5xx)
{ "data": ..., "ok": true }       // éxito
```

- Errores en español, mensajes accionables.
- Códigos: `400` validación, `401` no auth, `403` CSRF/permiso, `404` recurso, `429` rate-limit, `500` interno.

### Endpoints JSON principales (todos con `X-CSRF-Token` salvo nota)

| Método | Ruta | Propósito |
|--------|------|-----------|
| GET | `/health` | Healthcheck (sin auth) |
| GET | `/api/trips/history` | Historial del pasajero |
| GET | `/api/trips/available` | Viajes solicitados (conductores) |
| GET | `/api/trip/<id>/status` | Estado del viaje |
| GET | `/api/trip/<id>/eta` | ETA para pasajero |
| GET | `/api/trip/<id>/driver-eta` | ETA conductor→pasajero |
| GET | `/api/drivers/nearby?lat=&lng=&radius=` | Conductores online+libres c/distance_km |
| GET | `/api/geocode?q=` | Nominatim (OSM) |
| GET | `/api/driver/reviews/<driver_id>` / `/api/user/reviews/<user_id>` | Reviews públicas |
| GET | `/api/favorites` | Direcciones favoritas |
| GET | `/api/guidelines-status` | Estado de aceptación de normas |
| GET | `/api/wallet/balance` · `/api/wallet/transactions` | Billetera pasajero |
| GET | `/api/driver/wallet/balance` · `/api/driver/wallet/transactions` | Billetera conductor |
| GET | `/api/wallet/cvu-info` · `/api/wallet/bank-info` | Datos para transferencia |
| GET | `/api/driver/payment-methods` · `/api/driver/accepted-payments` | Métodos de pago del conductor |
| POST | `/api/location/update` | `{lat, lng}` (solo online) |
| POST | `/api/driver/toggle_online` | `{is_online: bool}` |
| POST | `/api/driver/respond/<id>` | `{action: "accept"\|"reject"}` |
| POST | `/api/trip/<id>/cancel` | `{reason}` |
| POST | `/api/trip/<id>/rate` | `{rating: 1-5, comment}` |
| POST | `/api/driver/payment-methods` / DELETE `/api/driver/payment-methods/<id>` | CRUD métodos conductor |
| POST | `/api/driver/mercadopago-qr` | QR MP del conductor |
| POST | `/api/user/payment-methods` / DELETE `/api/user/payment-methods/<id>` | CRUD config pasajero |
| POST | `/api/accept-guidelines` | Aceptar normas |
| POST | `/api/account/export` · `/api/account/delete` | GDPR: exportar/eliminar cuenta |
| POST | `/api/wallet/topup` | Cargar billetera (MP) |
| POST | `/api/wallet/topup/webhook` | Webhook MercadoPago (GET+POST, sin CSRF) |
| POST | `/api/wallet/topup/cvu` | Cargar por CVU |
| POST | `/api/wallet/topup/voucher` | Comprobante bancario |
| POST | `/api/wallet/pay-driver` | Pagar al conductor desde billetera |
| POST | `/api/upload-photo` | Foto de perfil |
| POST | `/company/api/create_preference` | Checkout MP empresa |
| POST | `/company/payment/webhook` | Webhook MP empresa |
| GET | `/company/api/members` · `/company/api/trips` | Portal empresa |
| POST | `/company/api/invite` · DELETE `/company/api/members/<id>/remove` | Miembros |
| POST | `/admin/topups/<id>/confirm\|reject` · `/admin/drivers/<id>/verify` | Admin |

### Rutas HTML (POST con CSRF)

`/register`, `/login`, `/driver/register`, `/passenger/request`, `/driver/accept/<id>`, `/driver/start/<id>`, `/driver/complete/<id>`, `/forgot-password`, `/reset-password`, `/profile/edit`, `/account/settings`, `/admin/login`, `/admin/logout`, rutas `/company/*` y de pago.

### Tarifa (contrato de negocio)

```
fare = max(BASE + km * POR_KM + min * POR_MIN, MINIMA)
```

| Vehículo | BASE | POR_KM | POR_MIN | MINIMA |
|----------|------|--------|---------|--------|
| Moto | 3.0 | 1.5 | 0.25 | 5.0 |
| Auto | 4.5 | 2.0 | 0.30 | 7.0 |

### Ciclo de vida del viaje

```
requested → accepted → ongoing → completed
        └──────────→ cancelled (pasajero | conductor | system: timeout 5 min)
```

### Estados de empresa

`trial` → `active` | `pending_payment` | `inactive`

### Métodos de pago (claves)

`efectivo` · `mercadopago` · `transferencia` · `tarjeta` · `billetera`

---

## 8. Modelo de negocio

### 8.1 Segmentos

1. **Pasajeros (B2C)**: pagan la tarifa del viaje. Pagan en efectivo o por plataforma (billetera con top-up, MercadoPago, tarjeta).
2. **Conductores (C2C oferta)**: registran vehículo (moto/auto), se ponen online, aceptan viajes y cobran. Reciben pagos desde la billetera del pasajero (`/api/wallet/pay-driver`).
3. **Empresas (B2B)**: contratan un plan mensual y gestionan viajes para sus empleados (miembros invitados, límite `max_employees`).

### 8.2 Fuentes de ingreso de VAN

- **Suscripción B2B**: planes `basic` (default, max 15 empleados) y `advanced`; período de prueba (`trial`), pago con MercadoPago o transferencia bancaria (confirmación manual/admin).
- **Futuro**: comisión por viaje y/o tarifas dinámicas (ver Roadmap F4/F5).

### 8.3 Billetera

- Pasajero y conductor tienen `balance` (DECIMAL 12,2).
- Carga: MercadoPago (webhook), transferencia CVU (info bancaria en `.env`: `BANK_*`), voucher manual (aprobado por admin en `/admin/topups`).
- Pagos: `pay-driver` mueve dinero de billetera pasajero → conductor; todo queda en `wallet_transactions` (auditable).
- Los detalles de métodos de pago se cifran con Fernet (`ENCRYPTION_KEY`).

### 8.4 Verificación y confianza

- Conductores: `is_verified` (admin aprueba), datos de vehículo y seguro obligatorios en registro.
- Ratings recíprocos (rating 1–5, `rating_avg`/`rating_count`).
- Lineamientos/guidelines: `accepted_guidelines` requerido para operar.
- GDPR: exportación y borrado de cuenta (`/api/account/export`, `/api/account/delete`).

---

## 9. Workstreams

Fases de trabajo (W) con su estado. Marco: **W0.x = fundación y features core**, los siguientes workstreams profundizan.

| WS | Nombre | Alcance | Estado |
|----|--------|---------|--------|
| W0.1 | Fundación y ramp-up | Factory `create_app()`, modelos base, migraciones, scripts (migrate/setup/reset/demo), infraestructura de tests | ✅ Completado |
| W0.2 | Autenticación y perfiles | Registro/login/logout pasajero y conductor, verificación email, reset password, perfiles con vehículo moto/auto, foto | ✅ Completado |
| W0.3 | Solicitud y geolocalización | `/passenger/request`, geocode Nominatim, haversine, tarifas, drivers/nearby, Leaflet, favoritos, guidelines | ✅ Completado |
| W0.4 | Ciclo de vida del viaje | accept/start/complete/cancel (timeout 5 min), status/ETA, trips/available, reviews recíprocas | ✅ Completado |
| W0.5 | Pagos y billetera | Métodos de pago cifrados, payments aceptados, QR MP, billetera, top-ups (MP/CVU/voucher), webhooks, pay-driver | ✅ Completado |
| W0.6 | Empresas B2B | Registro, planes basic/advanced, pago suscripción (MP/transferencia), dashboard, invitación de miembros, trips | ✅ Completado |
| W0.7 | Admin y moderación | Login admin, aprobación de top-ups, verificación de conductores | ✅ Completado (base) |
| W0.8 | Seguridad y hardening | CSRF, rate-limit, headers, sanitización, cifrado Fernet, sesiones seguras, GDPR (export/delete) | ✅ Completado (base) |
| W0.9 | Producción y despliegue | Railway/Docker/start.sh, HTTPS (Railway/Caddy/Tunnel/cert), healthcheck | ✅ Completado |
| W0.10 | Calidad y tests | pytest SQLite in-memory, cobertura de seguridad/ciclo/wallet | ✅ Completado (base) |
| W1.1 | Notificaciones | Email transaccionales (viaje aceptado, completado, top-up), push (futuro) | ⏳ Pendiente |
| W1.2 | Matching inteligente | Asignación automática por cercanía + rating + carga de trabajo | ⏳ Pendiente |
| W1.3 | Analytics | Panel pasajero/conductor: viajes, ganancias, rating, métricas de empresa | ⏳ Pendiente |
| W1.4 | Promociones | Códigos de descuento, referidos, tarifas dinámicas | ⏳ Pendiente |
| W1.5 | Internacionalización | i18n ES/EN en templates y mensajes de error | ⏳ Pendiente |
| W1.6 | Móvil | PWA (offline + push) → app nativa | ⏳ Pendiente |
| W1.7 | Operación | Monitoreo, logs estructurados, backup de MySQL, SLA | ⏳ Pendiente |

**Regla de workstreams**: todo PR/cambio debe declarar a qué workstream pertenece. Un workstream se cierra solo con tests verdes y spec actualizado.

---

## 10. Glosario y quirks

- `is_ocupado`: typo histórico intencional de la columna (no renombrar).
- `COLUMNAS`/`COLUMN_MODIFY`: dicts de migración manual — agregar columnas aquí y en el modelo.
- `.env` en `backend/.env`; `.env.example` en la raíz.
- Landing `/` = `demo/index.html` si existe.
- `FLASK_DEBUG=1` para debug local; `PORT` env para puerto (default 5000).
- VSCode asocia templates como `django-html`.
