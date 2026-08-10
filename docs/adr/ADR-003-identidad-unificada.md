# ADR-003: Identidad unificada (users + driver_profiles + vehicles)

- Estado: Aceptado
- Fecha: 2026-08-10

## Contexto

El esquema legacy (MySQL) tenía dos tablas de identidad: `users` (pasajeros)
y `drivers` (conductores) con campos duplicados (nombre, email, password,
saldo, rating) y dos FKs sueltas (`passenger_id` / `driver_id`). Consecuencias:

- Un conductor no podía ser pasajero sin una segunda cuenta con otro email.
- IDs ambiguos: `driver_id=7` y `user_id=7` no eran la misma persona.
- La billetera, el historial y la API v1 debían duplicar toda la lógica.
- La Fase 4 (comisión por viaje) requería una sola identidad con dinero.

Además, `driver_info` legacy tenía atributos de vehículo aplanados
(`moto_marca`, `placa`, `auto_año`), sin soporte de varios vehículos.

## Decisión

Esquema unificado sobre PostgreSQL (Fase 5, ya adoptado):

- **`users`** es la única tabla de identidad. Campo `role`:
  `passenger | driver | both | admin | company`.
- **`driver_profiles`** (1:1) con los datos de conductor: `is_online`,
  `is_busy`, `is_verified`, foto, rating, etc.
- **`vehicles`** (1:N) con los vehículos del conductor (`type`: moto/auto).
- `driver_profiles.user_id` tiene FK con `ON DELETE CASCADE`; el profile se
  crea junto con el user (mismo commit).
- Las FKs de viajes/apuestas apuntan a `users.id` siempre.

### Modo dual

- Un usuario `both` entra al sistema con un **modo activo**:
  `passenger` o `driver`. En la web: `active_mode` en la sesión
  (login → selector `/select-mode`, cambio en `/switch-mode`).
  En la API: claim `mode` en el JWT + parámetro `mode` en login/register.
- El claim `mode` del JWT **nunca autoriza por sí solo**: los permisos se
  derivan del `role` en la BD (el JWT expira a los 30 min; el role es
  fuente de verdad). El `mode` es solo contexto de presentación (qué vista
  mostrar).
- Promoción: si un conductor se registra con el email de un pasajero
  existente, el user se promueve a `role='both'` y se crea su
  `driver_profile` (web y API). Se evita el pitfall de SQLAlchemy de
  `user.driver_profile or DriverProfile(...)` cacheando `None`: se asigna
  `user.driver_profile = DriverProfile(...)` directamente y se hace commit
  inmediato.
- El portal admin (clave `ADMIN_SECRET_KEY`, flag `is_admin` en sesión) se
  conserva como está; es ortogonal a la identidad de usuarios.

### Dinero y comisión (preparación Fase 4)

- Dinero siempre en `Decimal` (`backend/services/fare.py`).
- `trips` ahora persiste el desglose al completarse:
  `total_fare = platform_fee + driver_earnings` (CHECK `chk_trip_money` en
  PostgreSQL). La comisión (`PLATFORM_FEE_RATE`, 5%) se calcula y guarda,
  pero **aún no se cobra** (no se descuenta del saldo del pasajero): el
  cobro real entra en la Fase 4 con billetera y Mercado Pago.

## Alternativas consideradas

- **Seguir con dos tablas + vista lógica**: rechazado — duplica la lógica de
  auth, billetera y API; imposible rol dual limpio.
- **Migrar usuarios a la tabla drivers (conductor primario)**: rechazado —
  el pasajero es el caso mayoritario en el MVP.
- **Tabla intermedia de identidades (`identities`)**: sobrediseño a la
  escala actual; un solo `users` con `role` es suficiente y la migración
  incremental es directa (legacy `drivers` → `users` + `driver_profiles`).

## Consecuencias

Positivas:
- Una sola fuente de verdad para auth, billetera, historial y API.
- Rol dual sin cuentas duplicadas; selector de modo en web y `mode` en API.
- Base directa para la Fase 4 (comisión) y Fase 6 (analítica por persona).
- Migración incremental: la migración `0002_unified_users` crea
  `driver_profiles` y `vehicles`, copia datos de `drivers`, promueve
  usuarios duplicados a `both`, y ajusta las FKs de `trips`; es reversible
  (`downgrade`).

Negativas:
- La migración de datos del legacy requiere cuidado con emails duplicados
  (se promueven a `both`; los que chocan entre conductores se resuelven
  sufijando el email o conservando solo al más reciente, según lo definido
  en la migración 0002).
- Los templates web legacy consumen campos planos: se mantiene
  `driver_view()` (SimpleNamespace) en `backend/services/identity.py` como
  capa de compatibilidad mientras migran los templates.

Supera a: ADR-001 (parcial — este define el modelo de identidad que la API
JWT consume) y al diseño legacy de dos tablas.
