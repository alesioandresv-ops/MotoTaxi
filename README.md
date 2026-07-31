# VAN

Plataforma de solicitud de viajes (moto y auto). Flask + MySQL + Leaflet.js.

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
- `backend/migration.py` — migraciones vía pymysql (columnas + tablas) + `db.create_all()`.
- `backend/models.py` — SQLAlchemy: `User`, `Driver`, `Trip`, `Review`.
- `backend/auth.py` — Blueprint `auth`: registro, login, perfil, verificación email.
- `backend/routes.py` — Blueprint `main`: rutas HTML + JSON APIs (CSRF protegidas).
- `backend/templates/` — Jinja2 + Leaflet.js.
- `demo/index.html` — SPA JS vainilla con datos mock (landing page en `/`).
- `tests/` — Pytest con SQLite `:memory:`, app fresca por método.

## Seguridad

- **CSRF**: todas las rutas de mutación requieren `csrf_token` (form) o `X-CSRF-Token` (JSON) o `{csrf_token}` en JSON body. `window.CSRF_TOKEN` se inyecta en templates.
- **Auth**: `@login_required` + `@csrf_required` en rutas protegidas. GET routes solo requieren login.
- **Input sanitized**: `sanitize_input()` elimina HTML tags y trunca a 500 chars.
- **SECRET_KEY**: requerida en `backend/.env` o producción (app no arranca sin ella).
- **Email verification**: exigida al login solo si SMTP está configurado en `.env`.

## APIs JSON clave

Todas requieren `X-CSRF-Token` header (obtener de `window.CSRF_TOKEN`).

| Método | Ruta | Propósito |
|--------|------|-----------|
| POST | `/api/location/update` | Conductor envía `{lat, lng}` |
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
```

Moto: `BASE=3.0, POR_KM=1.5, POR_MIN=0.25, MINIMA=5.0`
Auto:  `BASE=4.5, POR_KM=2.0, POR_MIN=0.30, MINIMA=7.0`

## Despliegue y HTTPS

### Railway (producción actual)
HTTPS automático provisto por Railway. No requiere configuración adicional.

La app detecta `RAILWAY_ENVIRONMENT` y activa `SESSION_COOKIE_SECURE` y `Strict-Transport-Security` automáticamente.

### Cloudflare Tunnel (desarrollo/testing en LAN)
Obtén una URL HTTPS pública temporal para probar en celulares sin advertencias de certificado.

```bash
# 1. Instalar cloudflared
winget install cloudflare.cloudflared

# 2. Correr la app localmente
python backend/app.py    # corre en :5000

# 3. En otra terminal, exponer el puerto
cloudflared tunnel --url http://localhost:5000
```

Esto genera una URL tipo `https://xxxx.trycloudflare.com` que podés compartir. La cámara funciona sin advertencias.

### Caddy + Let's Encrypt (producción con dominio propio)
Si tenés un dominio apuntando al servidor, usá Caddy para HTTPS automático.

```bash
# 1. Instalar Caddy
winget install caddy

# 2. Editar Caddyfile (ya incluido en el proyecto)
#    Reemplazar van.midominio.com por tu dominio real

# 3. Ejecutar
caddy run
```

Caddy obtiene certificados Let's Encrypt automáticamente.

### Desarrollo local (HTTP — default)
La app arranca en HTTP por defecto. La cámara **no funciona en HTTP**, pero todo lo demás sí.

```bash
python backend/app.py
# → http://localhost:5000
```

Para probar la cámara localmente usá **Cloudflare Tunnel** (abajo).

### Certificado autofirmado (para HTTPS local)
Si necesitás HTTPS local sin depender de Tunnel:

```bash
# 1. Generar certificado (detecta IPs LAN automáticamente)
python backend/generate_cert.py

# 2. Descomentar SSL_ENABLED en backend/.env
SSL_ENABLED=true

# 3. Iniciar
python backend/app.py
# → https://localhost:5000  o  https://<tu-ip>:5000
```

El navegador mostrará advertencia por ser autofirmado, pero la cámara funcionará.

## Quirks

- `is_ocupado` es typo intencional en DB (no `ocupado`) — así está en models y migration.
- `.env` va en `backend/.env`, no en raíz. `.env.example` en raíz.
- `FLASK_DEBUG=1` en `.env` activa debug mode. `PORT` variable de entorno (default 5000).
- La landing page `/` sirve `demo/index.html` si existe, sino `templates/index.html`.
