# Contrato API v1 — VAN (definitivo, backend-first para Flutter)

- Estado: **APROBADO** (2026-08-10) — contrato definitivo. Implementado:
  Etapa 0 (infraestructura API: errores, decorators, serializers, auth,
  openapi) y migración 0003 (`driver_profiles.status`). Pendiente: Trips API
  y módulos siguientes (numeración de implementación en VAN_MASTER_SPEC.md §7).
- Fecha: 2026-08-10
- Alcance: viajes, wallet/pagos, company, verificación de conductores,
  errores/paginación. **Ubicación en tiempo real (Socket.IO): fuera de esta
  fase** — los endpoints de polling son el contrato REST que Fase 3
  reemplazará/complementará (mapping en §4.4).
- Comisión: valor configurable `PLATFORM_FEE_RATE` (env) vía
  `backend/services/fare.py::commission_rate()`. **Prohibido hardcodear**
  porcentajes en la API.

## 1. Principios y reglas del contrato

1. **Cliente delgado**: Flutter NO calcula tarifas, comisión, distancias,
   saldo, matching, permisos, transiciones ni asignación. Todo el negocio
   vive en `backend/services/`, compartido por web y API.
2. **Identidad unificada (obligatoria)**: solo
   `users → driver_profiles → vehicles`. No existe `drivers`; la
   verificación usa EXCLUSIVAMENTE `driver_profiles.status`. El columna
   legacy `is_verified` no se usa para autorizar (solo como alias de
   presentación en `driver_view()` para templates).
3. **Envelope**: éxito `{"success": true, "data": {...}}`; error
   `{"success": false, "error": {"code": "CODE", "message": "..."}}`.
   `code` es estable (§12); Flutter nunca parsea `message`.
4. **Dinero**: todo dinero viaja como **string decimal** en JSON
   (ej. `"14.80"`), nunca float, nunca `0.5` sin ceros. El backend opera
   siempre en `Decimal` (`services/fare.py`).
5. **Invariante contable**: `total_fare = platform_fee + driver_earnings`
   (verificado por CHECK `chk_trip_money` en PostgreSQL). El desglose se
   persiste SIEMPRE en el viaje (§8).
6. **Idempotencia**: operaciones mutables aceptan el header estándar
   `Idempotency-Key` (§11). El campo JSON `idempotency_key` es **deprecated**
   (aceptado temporalmente; el header manda si ambos vienen).
7. **Web intacta**: los endpoints JSON web (sesión+CSRF) y las rutas HTML
   siguen funcionando sin cambios de URL ni de respuesta (§15).

## 2. Headers requeridos

| Header | Uso |
|--------|-----|
| `Authorization: Bearer <access_token>` | obligatorio en endpoints autenticados (excepto auth/refresh/register) |
| `Content-Type: application/json` | obligatorio en POST/PUT |
| `Accept: application/json` | recomendado |
| `Idempotency-Key: <UUID>` | obligatorio en `POST /trips`; opcional en `accept/start/complete/cancel/pay/topups` |
| `Retry-After: <segundos>` | respuesta de `RATE_LIMITED` (429) |

Si `Idempotency-Key` y el body `idempotency_key` vienen juntos, **el header
es la fuente oficial** (se ignora el body y se loguea un warning).

## 3. Autenticación y permisos

- **JWT access 30 min** (claims `sub`, `role`, `mode`, `jti`, `iat`, `exp`) +
  **refresh opaco rotativo** (ADR-002).
- `role` se valida SIEMPRE contra la DB en cada operación. `mode` del JWT es
  solo contexto de presentación y nunca autoriza.
- Permiso de modo conductor ⇒ `role ∈ (driver, both)` + `driver_profile`
  existe + `status == 'approved'` (ver §7).
- Permiso de modo pasajero ⇒ `role ∈ (passenger, both)`.
- Admin ⇒ `ADMIN_SECRET_KEY` (web) / JWT con `role='admin'` (v1).
- Empresa ⇒ miembro activo de `company_members` (v1) / sesión del portal
  (web, no cambia).

| Endpoint (v1) | Auth | Role·mode requerido |
|---|---|---|
| `/auth/register*`, `/auth/login`, `/auth/refresh` | público | – |
| `/auth/logout`, `/auth/me`, `/auth/switch-mode`, `/auth/verify-email` | JWT | cualquier usuario |
| `/trips` POST, `/trips/{id}` GET, `/trips` GET (`role=passenger`) | JWT | pasajero |
| `/trips/available`, `/drivers/location`, `/drivers/online` | JWT | conductor aprobado |
| `/trips/{id}/accept|reject|start|complete` | JWT | conductor aprobado (assignee para start/complete) |
| `/trips/{id}/cancel` | JWT | pasajero dueño o conductor asignado |
| `/trips/{id}/rate` | JWT | participante (pasajero y conductor, 1 vez c/u) |
| `/trips/{id}/eta` | JWT | participante |
| `/wallet*`, `/trips/{id}/pay` | JWT | cualquier usuario (pay: pasajero dueño) |
| `/drivers/nearby`, `/geocode` | JWT | pasajero |
| `/company*` | JWT | miembro (admin de empresa para gestión) |
| `/drivers/verification` | JWT | conductor (cualquier status) |
| `/admin/drivers*` | JWT | `role='admin'` |

## 4. Esquema final de endpoints

### 4.1 Auth (ya implementado, sin cambios)

`/auth/register`, `/auth/register/driver`, `/auth/login`, `/auth/refresh`,
`/auth/logout`, `/auth/me`, `/auth/switch-mode`, `/auth/verify-email`
(ver doc actual `openapi.yaml`; `/auth/switch-mode` devuelve access token
nuevo con `mode` actualizado y el refresh sigue válido).

### 4.2 Trips

| Método | Ruta | Request (JSON) | Response `data` | Errores |
|---|---|---|---|---|
| POST | `/trips` | ver §5.2.1 | trip | VALIDATION_ERROR, ACTIVE_TRIP_EXISTS, INVALID_VEHICLE_TYPE, INVALID_PAYMENT_METHOD |
| GET | `/trips/{id}` | – | trip | NOT_FOUND, FORBIDDEN |
| GET | `/trips?role=passenger\|driver&status=&page=&limit=` | – | {items: [trip], pagination} | – |
| GET | `/trips/available?lat&lng&radius=&vehicle_type=&page=` | – | {items: [available_trip], pagination} | LOCATION_REQUIRED |
| POST | `/trips/{id}/accept` | `{}` | trip | TRIP_NOT_AVAILABLE, NOT_ONLINE, NOT_VERIFIED |
| POST | `/trips/{id}/reject` | `{}` | ok | NOT_FOUND |
| POST | `/trips/{id}/start` | `{}` | trip | INVALID_TRANSITION, FORBIDDEN |
| POST | `/trips/{id}/complete` | `{}` | trip (fare final + wallet) | INVALID_TRANSITION, FORBIDDEN |
| POST | `/trips/{id}/cancel` | `{reason?}` | trip | TRIP_FINALIZED, FORBIDDEN |
| POST | `/trips/{id}/rate` | `{rating: 1-5, comment?}` | ok | TRIP_NOT_COMPLETED, ALREADY_RATED, INVALID_RATING |
| GET | `/trips/{id}/eta` | – | {eta_min, distance_km, driver_lat, driver_lng} | NOT_FOUND |

### 4.3 Wallet

| Método | Ruta | Request | Response `data` | Errores |
|---|---|---|---|---|
| GET | `/wallet` | – | {balance, currency} | – |
| GET | `/wallet/transactions?type=&page=&limit=` | – | {items: [txn], pagination} | – |
| POST | `/wallet/topups` | {amount, method: mercadopago\|cvu\|bank, voucher_base64?} | topup {id, status, init_point?} | TOPUP_MIN, TOPUP_MAX, INVALID_AMOUNT, MP_NOT_CONFIGURED |
| GET | `/wallet/topups/{id}` | – | topup {status, admin_note} | NOT_FOUND |
| GET | `/wallet/topups?status=&page=&limit=` | – | {items, pagination} | – |
| POST | `/trips/{id}/pay` | `{amount?}` | {paid_amount, outstanding, passenger_txn_id, driver_txn_id} | TRIP_NOT_COMPLETED, TRIP_ALREADY_PAID, INSUFFICIENT_BALANCE, FORBIDDEN, VALIDATION_ERROR |
| GET | `/wallet/withdrawals` | – | {items: [], pagination} (Fase 4) | – |

### 4.4 Ubicación (polling; contrato REST para Fase 3)

| Método | Ruta | Request | Response | Errores |
|---|---|---|---|---|
| POST | `/drivers/location` | {lat, lng} | ok | NOT_ONLINE, NOT_VERIFIED, INVALID_COORDINATES |
| POST | `/drivers/online` | {is_online: bool} | {is_online} | NOT_VERIFIED |
| GET | `/drivers/nearby?lat&lng&radius=&vehicle_type=` | – | {items: [driver], count} | INVALID_COORDINATES |
| GET | `/geocode?q=` | – | {address, lat, lng} | NOT_FOUND |

Mapping Socket.IO futuro (no implementar): `driver:location` ↔ POST
`/drivers/location`; `trip:update` ↔ respuestas de accept/start/complete y
poll de `/trips/available`; `trip:assigned` ↔ push al pasajero del estado
accept (hoy poll a `GET /trips/{id}`). El matching sigue 100% backend.

### 4.5 Company

| Método | Ruta | Request | Response | Errores |
|---|---|---|---|---|
| GET | `/company` | – | {company: {id, name, plan, status, max_employees}, member: {role, user_id}} | FORBIDDEN |
| GET | `/company/members?page=&limit=` | – | {items, pagination} | FORBIDDEN |
| POST | `/company/members` | {email, role: admin\|employee} | member | MEMBER_EXISTS, PLAN_LIMIT_REACHED, VALIDATION_ERROR |
| DELETE | `/company/members/{member_id}` | – | ok | NOT_FOUND, FORBIDDEN |
| GET | `/company/trips?status=&page=&limit=` | – | {items: [trip], pagination} | FORBIDDEN |

### 4.6 Verificación y admin

| Método | Ruta | Request | Response | Errores |
|---|---|---|---|---|
| GET | `/drivers/verification` | – | {status, vehicles, documents} | – |
| PUT | `/drivers/verification` | {vehicles[], profile fields, document urls} | {status: pending} | VALIDATION_ERROR |
| GET | `/admin/drivers?status=&page=&limit=` | – | {items: [driver+profile+vehicles], pagination} | FORBIDDEN |
| POST | `/admin/drivers/{id}/verify` | {decision: approve\|reject, note?} | {status} | NOT_FOUND, FORBIDDEN |

## 5. Request/response detallados

### 5.1 `trip` (payload canónico)

```json
{
  "id": 12,
  "status": "accepted",
  "vehicle_type": "moto",
  "pickup_address": "Av. Siempre Viva 742",
  "dropoff_address": "Plaza Mayor",
  "pickup_lat": -34.6, "pickup_lng": -58.4,
  "dropoff_lat": -34.61, "dropoff_lng": -58.41,
  "distance_km": 4.8,
  "duration_min": null,
  "payment_method": "billetera",
  "company_id": null,
  "requested_at": "2026-08-10T14:00:00Z",
  "started_at": null,
  "completed_at": null,
  "cancelled_by": null,
  "fare": {
    "estimate": {"total_fare": "11.25", "platform_fee": "0.56",
                 "platform_fee_rate": "0.05", "driver_earnings": "10.69",
                 "currency": "ARS"},
    "final": null
  },
  "wallet": {"charged": false, "passenger_txn_id": null, "driver_txn_id": null},
  "passenger": {"id": 3, "name": "Ana", "rating_avg": 4.9, "rating_count": 21},
  "driver": {"id": 7, "name": "Carlos", "phone": "...", "profile_picture": null,
             "rating_avg": 5.0, "rating_count": 3,
             "vehicle_type": "moto",
             "vehicle_info": {"placa": "ABC123", "marca": "Yamaha", "modelo": "R3"},
             "lat": -34.59, "lng": -58.41}
}
```

- `fare.estimate` = snapshot al crear (duration=0). `fare.final` = al
  completar (duración real) — sobreescribe los campos del trip en DB.
- Moneda y desglose: siempre los 5 campos (`total_fare`, `platform_fee`,
  `platform_fee_rate`, `driver_earnings`, `currency`). `platform_fee_rate`
  puede ser `null` (comisión desactivada).
- `wallet.charged` = true solo si se movió saldo en ese `complete`.

### 5.2 Trips

#### 5.2.1 POST /trips
```json
// Request
{"pickup_address": "Av. Siempre Viva 742", "dropoff_address": "Plaza Mayor",
 "pickup_lat": -34.6, "pickup_lng": -58.4,
 "dropoff_lat": -34.61, "dropoff_lng": -58.41,
 "vehicle_type": "moto", "payment_method": "billetera"}
// Headers: Authorization + Idempotency-Key (obligatorio)
// 201 → data: {"trip": {...}, "duplicate": false}
// Replay con la misma Idempotency-Key → 200 con el MISMO trip y "duplicate": true
```

Reglas: `vehicle_type ∈ {moto, auto}`; `payment_method ∈ {billetera,
efectivo}` (mismo set `PAYMENT_TYPES` que la web); distancia calculada por
el backend (coords o geocode de la dirección si faltan); fallback 1.0 km;
si el pasajero ya tiene un viaje `requested|accepted|ongoing` →
`ACTIVE_TRIP_EXISTS`. Si el pasajero pertenece a empresa activa →
`company_id` asignado por el backend (§10). `company_id` enviado por el
cliente se IGNORA.

#### 5.2.2 GET /trips/{id} → data: {trip} (el payload §5.1)

#### 5.2.3 GET /trips
```json
// ?role=passenger&status=completed&page=1&limit=20
// → data: {"items": [trip...], "pagination": {"page": 1, "limit": 20, "total": 34, "pages": 2}}
// role=passenger: trips.passenger_id == sub ; role=driver: trips.driver_id == sub
// status filtra; sin status → todos (completed + cancelled como la web)
```

#### 5.2.4 GET /trips/available (conductor)
```json
// ?lat=-34.59&lng=-58.41&radius=10&vehicle_type=moto&page=1&limit=20
// → data: {"items": [{"id": 12, "pickup_address": "...", "dropoff_address": "...",
//   "pickup_lat": ..., "pickup_lng": ..., "vehicle_type": "moto",
//   "fare": {"estimate": {...}}, "distance_km": 3.2, "requested_at": "..."}],
//   "pagination": {...}}
```
Solo viajes `requested`; `distance_km` calculado contra la posición
persistida del conductor; sin posición → `LOCATION_REQUIRED`. Matching
íntegramente backend (misma query `nearby_drivers_query`/filtro web).

#### 5.2.5 accept / reject / start / complete / cancel / rate / eta
```json
// POST /trips/12/accept {} → 200 data: {trip}   (exige: online + libre + approved)
// POST /trips/12/reject {} → 200 data: {ok: true}   (sin efecto sobre el viaje)
// POST /trips/12/start {} → 200 data: {trip (status: ongoing, started_at)}
// POST /trips/12/complete {} → 200 data: {trip (fare.final + wallet.charged)}
// POST /trips/12/cancel {"reason": "cambio de planes"} → 200 data: {trip (cancelled)}
// POST /trips/12/rate {"rating": 5, "comment": "todo bien"} → 200 data: {ok: true}
// GET /trips/12/eta → 200 data: {"eta_min": 6, "distance_km": 2.4,
//                                 "driver_lat": -34.58, "driver_lng": -58.40}
```

### 5.3 Wallet

```json
// GET /wallet → 200 data: {"balance": "120.50", "currency": "ARS"}

// GET /wallet/transactions?page=1&limit=20
// → data: {"items": [{"id": 55, "amount": "-14.80", "type": "trip_payment",
//   "status": "completed", "trip_id": 12, "reference": null,
//   "description": "Viaje #12", "created_at": "..."}], "pagination": {...}}

// POST /wallet/topups {"amount": "5000", "method": "mercadopago"}
// → 201 data: {"topup": {"id": 9, "status": "pending", "init_point": "https://..."}}
// method=cvu|bank → "init_point": null (el pasajero sube voucher → admin confirma)

// GET /wallet/topups/9 → data: {"topup": {"id": 9, "amount": "5000.00",
//   "method": "mercadopago", "status": "confirmed", "admin_note": null}}

// POST /trips/12/pay {"amount": "14.80"}  (o sin amount → paga todo lo adeudado)
// → 200 data: {"paid_amount": "14.80", "outstanding": "0.00",
//   "passenger_txn_id": 70, "driver_txn_id": 71}
// Replay con misma Idempotency-Key → mismo body, sin nuevos movimientos.
// Reglas: trip completed; pasajero dueño; amount ≤ outstanding
// (outstanding = total_fare − pagado_acumulado del pasajero);
// saldo suficiente → INSUFFICIENT_BALANCE. Ver ledger §8.
```

### 5.4 Ubicación
```json
// POST /drivers/location {"lat": -34.59, "lng": -58.41} → 200 data: {ok: true}
// POST /drivers/online {"is_online": true} → 200 data: {"is_online": true}
//   (status != approved → 403 NOT_VERIFIED; offline ⇒ is_busy=false)
// GET /drivers/nearby → data: {"items": [{"id": 7, "name": "Carlos",
//   "rating_avg": 5.0, "rating_count": 3, "vehicle_type": "moto",
//   "vehicle_info": {...}, "lat": ..., "lng": ..., "distance_km": 1.2,
//   "profile_picture": null, "accepted_payments": ["efectivo", "billetera"]}],
//   "count": 3}
// GET /geocode?q=Plaza%20Mayor → data: {"address": "Plaza Mayor, ...",
//   "lat": -34.6083, "lng": -58.3712}
```

### 5.5 Company
```json
// GET /company → data: {"company": {"id": 1, "name": "ACME SA", "plan": "basic",
//   "status": "active", "max_employees": 15}, "member": {"role": "admin", "user_id": 9}}
// POST /company/members {"email": "nuevo@acme.com", "role": "employee"}
//   → 201 data: {"member": {"id": 5, "company_id": 1, "user_id": 22,
//     "role": "employee", "joined_at": null}}
//   (el miembro existe como user; si el email no tiene cuenta user → VALIDATION_ERROR)
// GET /company/trips?status=completed → data: {"items": [trip], "pagination": {...}}
```

### 5.6 Verificación
```json
// GET /drivers/verification → data: {"status": "pending",
//   "vehicles": [{"id": 2, "type": "moto", "placa": "ABC123", "marca": "Yamaha",
//                 "modelo": "R3", "is_active": true}],
//   "profile": {"carnet_conducir": "A2", "tipo_seguro": "Todo riesgo"},
//   "documents": {"carnet_url": null, "seguro_url": null, "foto_url": null}}
// PUT /drivers/verification {...} → 200 data: {"status": "pending"}
//   (desde rejected vuelve a pending)
// POST /admin/drivers/7/verify {"decision": "approve"} → data: {"status": "approved"}
// POST /admin/drivers/7/verify {"decision": "reject", "note": "seguro vencido"}
//   → data: {"status": "rejected"}
```

## 6. Máquina de estados de Trip

```
requested ──accept(driver online+libre+approved)──► accepted ──start(driver)──► ongoing
   │  ▲                                                │                         │
   │  └────reject (sin efecto)─────────────────────────┘                         │
   │                                                                             │
   ├──cancel(pasajero)──────────────────────► cancelled ◄──cancel(pasajero)──────┤
   └──cancel(sistema, 5 min: stale)─────────► cancelled ◄──cancel(conductor)─────┘

ongoing ──complete(driver)──► completed ──rate(pasajero y conductor, 1 vez c/u)──► completed
```

| De | Acción | Quién | Efecto | Inválida → |
|----|--------|-------|--------|-----------|
| requested | accept | conductor online+libre+`approved` | accepted; `is_busy=true`; `driver_id` asignado | TRIP_NOT_AVAILABLE / NOT_ONLINE / NOT_VERIFIED |
| requested | reject | conductor | sin efecto | – |
| requested | cancel | pasajero dueño | cancelled; `cancelled_by=passenger` | TRIP_FINALIZED / FORBIDDEN |
| requested | cancel | sistema (timeout 5 min) | cancelled; `cancelled_by=system` | – |
| accepted | start | conductor asignado | ongoing; `started_at` | INVALID_TRANSITION / FORBIDDEN |
| accepted/ongoing | cancel | pasajero dueño o conductor asignado | cancelled; libera `is_busy` (sin penalización, D8) | TRIP_FINALIZED / FORBIDDEN |
| ongoing | complete | conductor asignado | completed; `completed_at`, duración, `fare.final`; cobro billetera (§8); libera `is_busy` | INVALID_TRANSITION / FORBIDDEN |
| completed | rate | ambos (1 c/u) | review; actualiza rating | TRIP_NOT_COMPLETED / ALREADY_RATED / INVALID_RATING |
| completed/cancelled | cualquier mutación | – | rechazado | TRIP_FINALIZED |

Arquitectura preparada para política de cancelación futura (D8): `cancelled_by`
persiste el actor; agregar sanciones será solo lógica nueva, sin migración.

## 7. Máquina de estados de verificación del conductor

Modelo ÚNICO: `users → driver_profiles.status ∈ {pending, approved,
rejected}`. (Sin `drivers`, sin `is_verified` como autorizador.)

```
registro (nuevo conductor) ──► pending
pending ──admin approve──► approved
pending ──admin reject──► rejected
rejected ──PUT /drivers/verification (resubir docs)──► pending
approved ──admin revoke──► pending   (el web "desverificar" → pending)
```

| Operación | pending | approved | rejected |
|---|---|---|---|
| Ver su estado / editar perfil | ✅ | ✅ | ✅ |
| Resubir documentación | ✅ (ya está) | – | ✅ (→ pending) |
| `POST /drivers/online` | ❌ NOT_VERIFIED | ✅ | ❌ NOT_VERIFIED |
| `POST /drivers/location` | ❌ NOT_VERIFIED | ✅ | ❌ NOT_VERIFIED |
| `POST /trips/{id}/accept` | ❌ NOT_VERIFIED | ✅ | ❌ NOT_VERIFIED |
| Viajes asignados (start/complete/cancel) | ✅ (si es assignee) | ✅ | ✅ |

Backfill (migración 0003): conductores existentes → `status='approved'`
(compatibilidad total; nadie queda bloqueado). Nuevos registros → `pending`.
El alias `is_verified` (bool) queda solo como derivado de presentación en
`driver_view()`; la lógica de autorización usa `status`.

## 8. Flujo completo de dinero / ledger (requisito B)

Modelo contable (sin dinero de la nada, sin movimientos duplicados, balances
siempre consistentes):

### 8.1 Reglas invariantes
- **I1**: `total_fare = platform_fee + driver_earnings` — CHECK
  `chk_trip_money` en PG; se mantiene en TODOS los viajes.
- **I2**: pagado por pasajero (por viaje) = `SUM(WalletTransaction.amount
  WHERE user_id=passenger AND trip_id=T AND type='trip_payment' AND
  status='completed')` ≤ `total_fare`. Nunca se debita de más.
- **I3**: cobrado por conductor (por viaje) = `SUM(... user_id=driver ...)` ≤
  `driver_earnings`. El conductor NUNCA recibe más de sus ganancias.
- **I4**: todo crédito al conductor tiene su débito pareado al pasajero
  (misma cantidad, mismo viaje, `payment_ref` compartido). No se acredita
  sin debitar.
- **I5**: `platform_fee` queda **registrada contablemente** en el viaje
  (snapshot `platform_fee`, `platform_fee_rate`) pero **no se extrae**: no
  hay movimiento de wallet de plataforma hasta la Fase 4 (cuenta interna +
  `COMMISSION_ACTIVE`). "Reconocida, no extraída".
- **I6**: una sola pareja de movimientos por acción de pago (autocharge o
  pay manual) — protegido por transacción con locks
  (`SELECT ... FOR UPDATE` sobre pasajero y conductor) + Idempotency-Key.

### 8.2 Flujo por evento

**1. Crear viaje** (POST /trips)
- `build_fare(distancia, 0, tipo)` → `{total_fare, platform_fee,
  platform_fee_rate, driver_earnings, currency}` (comisión = rate de
  `PLATFORM_FEE_RATE`, ver `commission_rate()`).
- Se persisten los 5 campos (estimate). Sin movimientos de wallet.

**2. Completar viaje** (POST /trips/{id}/complete)
- `build_fare(distancia, duración_real, tipo)` → desglose FINAL; se
  sobreescriben los 5 campos en el trip.
- Si `payment_method == 'billetera'` y `company_id IS NULL`:
  - saldo suficiente: débito `-total_fare` (pasajero, `trip_payment`,
    `payment_ref=PK`, `status=completed`) + crédito `+driver_earnings`
    (conductor, mismo `payment_ref`). Una sola pareja. (`wallet.charged=true`)
  - saldo insuficiente: débito `-total_fare` con `status='pending'` en el
    pasajero, SIN crédito al conductor (I4). El viaje queda pagable vía
    `POST /trips/{id}/pay` (§8.3).
- `efectivo`: sin movimiento automático. Pago posterior por `/trips/{id}/pay`.
- Viaje corporativo (`company_id != null`): sin cargo a la billetera del
  pasajero; la facturación a la empresa es Fase 4 (el trip queda con
  `payment_status='company'` derivado).

**3. Pago manual** (POST /trips/{id}/pay)
- `outstanding_pasajero = total_fare − SUM(debita pasajero, completed)`.
- `por_cobrar_conductor = driver_earnings − SUM(acredita conductor,
  completed)`.
- `amount` (default = outstanding) debe cumplir: `0 < amount ≤ outstanding`
  y `amount ≤ por_cobrar_conductor` (implica que nunca se paga de más).
- Débito pasajero + crédito conductor, mismos `amount` y `payment_ref`,
  `status='completed'`, en una transacción con locks.
- `TRIP_ALREADY_PAID` cuando `outstanding == 0`.

**4. Depositar** (topups)
- MP webhook: acredita `users.balance` + `WalletTransaction
  type='deposit_mp'` + `TopUpRequest` — dedup por `mp_payment_id` (ya
  implementado). CVU/bank: admin confirma → mismo patrón.
- El saldo solo aumenta por depósitos o por créditos de viaje pareados (I4).

### 8.3 Columnas nuevas (migración 0003)
- `wallet_transactions.payment_ref` (string, nullable) — agrupa la pareja
  débito/crédito.
- `trips.idempotency_key` (nullable, único por pasajero) — trazabilidad
  (mecanismo principal = header, §11).
- Tabla `api_idempotency_keys` — almacén de respuestas para replays.

## 9. role='both' y active_mode

- **`role`**: identidad permanente en `users` (passenger | driver | both |
  admin | company). Nunca se modifica por sesión ni por token.
- **`active_mode`**: contexto de sesión/token (passenger | driver). La
  sesión web guarda `active_mode`; el JWT lleva `mode`.
- Login: `passenger`→pasajero directo; `driver`→conductor directo; `both`→
  el cliente elige (`mode` en login o `/auth/switch-mode`).
- `mode` NUNCA autoriza: cada endpoint valida `role` + `driver_profile` +
  `status` en DB (decorators `require_mode`).
- Modo conductor requiere `driver_profile != NULL` y `status='approved'`
  para operar (ver §7). Modo pasajero no requiere nada extra.
- Wallet y rating son ÚNICOS por user (el `both` no divide dinero).
- Historial: `GET /trips?role=` filtra por pasajero o conductor sin cambiar
  de identidad.
- Sin cuentas ni sesiones duplicadas: mismo `sub`, mismo refresh token.

## 10. Viajes corporativos (D9)

- `POST /trips`: si `sub` tiene una membership con empresa activa
  (`companies.status ∈ {trial, active}`), el backend asigna
  `company_id` automáticamente.
- Flutter NO envía `company_id`; si lo manda, se ignora (no se confía en el
  cliente).
- Efectos en MVP: viaje normal en tarifa; **sin cargo automático a la
  billetera del pasajero** (la facturación a la empresa llega en Fase 4).
- Permisos v1: `GET /company` cualquier miembro; members/trips solo
  `role='admin'` de la empresa. Portal web sin cambios.
- Límite de miembros: `max_employees` → `PLAN_LIMIT_REACHED`.

## 11. Idempotencia y reintentos (requisito A)

- Header `Idempotency-Key: <UUID>` — fuente oficial. Body
  `idempotency_key` deprecated (temporal, documentado en openapi como
  deprecated; header gana).
- Mecanismo: tabla `api_idempotency_keys (id, user_id, key, method, path,
  status_code, response_body JSON, created_at)` con
  `UNIQUE (user_id, key, method)`.
  - Primer request: se ejecuta la operación y se almacena la respuesta
    (status + body) en el MISMO commit.
  - Replay (misma user+key+method): se devuelve la respuesta almacenada
    (mismo status y body), sin re-ejecutar. `duplicate:true` en POST /trips.
  - TTL 24 h con limpieza perezosa; la clave es por usuario (un cliente no
    puede clonar claves de otro).
- Operaciones:
  - `POST /trips`: **obligatoria** (replay devuelve el MISMO trip).
  - `accept/start/complete/cancel/pay/topups`: opcional (recomendada).
  - Protección extra por naturaleza: accept usa UPDATE atómico
    (`WHERE status='requested'`); complete solo transiciona
    `ongoing → completed` una vez; rate usa `uq_review_once`; pay usa locks
    + I2/I3; topup webhook dedup por `mp_payment_id`.
- **Reintentos Flutter**: si la conexión corta, reenviar con la MISMA
  `Idempotency-Key`; el servidor responde el resultado original.

## 12. Códigos de error estables

`TOKEN_EXPIRED, TOKEN_INVALID, TOKEN_REVOKED, INVALID_CREDENTIALS,
EMAIL_NOT_VERIFIED, EMAIL_TAKEN, VALIDATION_ERROR, NOT_FOUND, FORBIDDEN,
METHOD_NOT_ALLOWED, MODE_NOT_ALLOWED, ACTIVE_TRIP_EXISTS, TRIP_NOT_AVAILABLE,
INVALID_TRANSITION, TRIP_FINALIZED, TRIP_NOT_COMPLETED, ALREADY_RATED,
INVALID_RATING, INSUFFICIENT_BALANCE, TRIP_ALREADY_PAID, TOPUP_MIN, TOPUP_MAX,
INVALID_AMOUNT, MP_NOT_CONFIGURED, NOT_ONLINE, NOT_VERIFIED,
INVALID_COORDINATES, LOCATION_REQUIRED, MEMBER_EXISTS, PLAN_LIMIT_REACHED,
COMPANY_INACTIVE, RATE_LIMITED, INTERNAL_ERROR`

Reglas: HTTP status coherente (400 validación/negocio, 401 auth, 403
permisos, 404, 409 estado conflictivo, 422 validación de forma, 429, 500);
`code` estable en el tiempo; `message` solo legible por humanos.

## 13. Paginación

- `?page=1&limit=20` (default 20, máx 100, clamp server-side).
- Respuesta: `{"items": [...], "pagination": {"page": 1, "limit": 20,
  "total": 34, "pages": 2}}`.
- Orden estable: `created_at DESC, id DESC` (compatible cursor futuro).
- Aplica a: `/trips`, `/trips/available`, `/wallet/transactions`,
  `/wallet/topups`, `/company/members`, `/company/trips`,
  `/admin/drivers`, `/wallet/withdrawals`.

## 14. Rate limits

| Tier | Endpoints | Límite |
|------|-----------|--------|
| auth | `/auth/login`, `/auth/register*` | 10/min |
| crítico | `/trips/{id}/accept`, `/start`, `/complete`, `/cancel`, `/rate`, `/pay` | 20/min |
| topup | `/wallet/topups` | 5/min |
| ubicación | `/drivers/location` | 60/min |
| consulta | `/trips`, `/wallet`, `/drivers/nearby`, `/geocode`, `/company*`, `/drivers/verification` | 30–60/min |

`RATE_LIMITED` (429) + `Retry-After`. La web conserva sus límites actuales.

## 15. Impacto sobre la web existente

| Área | Impacto |
|------|---------|
| Rutas HTML y JSON web (URLs, responses) | **Ninguno**: no cambian de ruta ni de formato |
| Refactor a `services/` | Interno: `routes.py` y API v1 comparten `services/trips.py`, `services/identity.py`, `services/fare.py` — comportamiento idéntico, cubierto por los 96 tests existentes |
| `pay-driver` web | Se mantiene; v1 usa `POST /trips/{id}/pay` (no se elimina nada) |
| Webhook MP topup | Se mantiene igual |
| Portal admin web | Se mantiene; agrega `status` a la vista (mapea `approved`/`pending`/`rejected`); `is_verified` pasa a ser derivado |
| Verificación (enforcement) | Cambio visible SOLO para conductores nuevos/`pending` (no pueden online); existentes quedan `approved` por backfill |
| Portal company | Sin cambios |
| Sesiones/CSRF | Sin cambios |

## 16. Tests requeridos antes de cerrar Fase 1

Todos con SQLite `:memory:` + app fresca (patrón actual). Suite completa
existente (96) debe seguir en verde en cada etapa.

**test_api_decorators.py**: 401/403 por token; `MODE_NOT_ALLOWED`; modo
conductor sin profile; paginación (clamp, default).

**test_api_trips.py**
- create: validación (addresses, vehicle_type, payment_method);
  `ACTIVE_TRIP_EXISTS`; fare estimate con comisión configurable
  (`monkeypatch PLATFORM_FEE_RATE` → 0.05 y desactivada → rate null);
  `company_id` auto-asignado (D9) e ignorado si lo manda el cliente.
- idempotencia: misma `Idempotency-Key` → mismo trip + `duplicate:true`;
  clave distinta → viaje nuevo; replay tras respuesta perdida.
- accept: éxito setea `is_busy`; offline → `NOT_ONLINE`; `pending` →
  `NOT_VERIFIED`; race (dos conductores, uno gana → `TRIP_NOT_AVAILABLE`);
  replay idempotente.
- start/complete: `INVALID_TRANSITION` fuera de estado; complete calcula
  `fare.final` y `total_fare = platform_fee + driver_earnings` (I1);
  billetera con saldo → pareja de movimientos (I4, I6) y saldos correctos
  (I2, I3); saldo insuficiente → débito `pending` sin crédito al conductor;
  efectivo → sin movimientos; replay de complete → sin doble cargo.
- cancel: permisos (pasajero dueño / conductor asignado / tercero →
  FORBIDDEN); `TRIP_FINALIZED`; libera `is_busy`.
- rate: solo `completed`; 1 vez por usuario; rating fuera de 1–5.
- get/list: paginación; filtro `role`; acceso solo participantes.

**test_api_wallet.py**: balance unificado para `both` (mismo user en ambos
modos); transactions paginadas; topups (min 100, max 500000, método
inválido, ownership del topup ajeno → NOT_FOUND); pay (cap por outstanding,
`TRIP_ALREADY_PAID`, `INSUFFICIENT_BALANCE`, pagos parciales respetan I2/I3,
replay idempotente); withdrawals vacío.

**test_api_location.py**: location solo online+approved; coords fuera de
rango/NaN; online toggle bloqueado si `pending`/`rejected`; nearby (solo
online+libres, filtro vehicle_type, paginación).

**test_api_company.py**: GET /company sin membership → FORBIDDEN;
members CRUD (invite, duplicado → MEMBER_EXISTS, límite →
PLAN_LIMIT_REACHED, solo admin); trips de empresa con `company_id`.

**test_api_verification.py**: máquina de estados (pending→approved,
pending→rejected, rejected→pending por resubida, approved→pending por
revoke); enforcement (online/location/accept bloqueados salvo approved);
backfill (existentes → approved; nuevos → pending); `driver_view` expone
`is_verified` derivado de `status` para templates.

**test_trips_service.py** (unit services): transiciones legales/ilegales
de la máquina §6; invarianzas I1–I6 con dinero Decimal.

**test_web_regression.py** (o suite existente): los 149 tests siguen
pasando + smoke web (login dual, select-mode, dashboard, admin, pay-driver
web intacto).

---

Estado actual: la **Etapa 0** (infraestructura API: errores, decorators,
serializers, auth, openapi) y la **migración 0003** están completadas. El
seguimiento de implementación usa Etapa 1 = migración 0003 y **Etapa 2 =
Trips API** (numeración en VAN_MASTER_SPEC.md §7); los módulos 1–7 de este
contrato se implementan en commits pequeños, reversibles y con la suite en
verde al final de cada uno.
