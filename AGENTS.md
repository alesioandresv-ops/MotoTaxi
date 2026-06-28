## Modos de ejecución

- **Standalone (sin servidor):** abre `demo/index.html` en el navegador. Datos mock en memoria JS.
- **Full-stack (Flask + MySQL):** `python backend/app.py`. Requiere MySQL con DB `mototaxi` y credenciales en `backend/.env`.

## Setup inicial

```bash
# 1. Crear base de datos MySQL
mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS mototaxi"

# 2. Configurar backend/.env (ver .env.example)
#    DATABASE_URL=mysql+pymysql://root:pass@127.0.0.1:3306/mototaxi

# 3. Crear tablas (primera vez)
python setup.py

# 4. Si las tablas YA EXISTEN y se agregaron columnas nuevas:
python migrate.py    # ALTER TABLE sin perder datos

# 5. Usuarios demo
python create_demo_users.py   # pasajero@demo.com / 1234, conductor@demo.com / 1234

# 6. Iniciar servidor
python backend/app.py         # Puerto de env PORT o 5000
```

## Base de datos

- MySQL vía SQLAlchemy + pymysql. `DATABASE_URL` en `backend/.env`.
- `db.create_all()` en `app.py:45` — solo crea tablas nuevas, **no altera** existentes.
- Para migrar tablas existentes: `python migrate.py`.
- `backend/.env` contiene credenciales reales — **no versionar** (ya en `.gitignore`).

## Modelos (`backend/models.py`)

| Tabla | Propósito | Campos clave |
|-------|-----------|-------------|
| `users` | Pasajero | name, email, password(hashed), phone, profile_picture, email_verified, rating_avg, rating_count |
| `drivers` | Conductor | +is_online, is_ocupado, lat, lng, last_location_update, placa, moto_* |
| `trips` | Viaje | passenger_id, driver_id, pickup/dropoff_address + _lat/_lng, distance_km, fare, status |
| `reviews` | Reseña | trip_id, from_user/driver_id, to_user/driver_id, rating(1-5), comment, role('passenger'\|'driver') |
| `driver_sessions` | Ubicación conductor | driver_id, is_online, lat, lng |

## Ciclo de vida del viaje

`requested` → `accepted` → `ongoing` → `completed` | `cancelled`

Rutas HTML en `backend/routes.py`:
- `POST /passenger/request` — pasajero solicita
- `GET /driver/accept/<id>` — conductor acepta (marca `is_ocupado=True`)
- `GET /driver/start/<id>` — inicia viaje (→ `ongoing`)
- `GET /driver/complete/<id>` — completa (→ `completed`, `is_ocupado=False`)

## APIs JSON

| Método | Ruta | Propósito |
|--------|------|-----------|
| POST | `/api/location/update` | Conductor envía `{lat, lng}` cada 5s |
| POST | `/api/driver/toggle_online` | `{is_online: bool}` |
| POST | `/api/driver/respond/<id>` | `{action: "accept"\|"reject"}` |
| GET | `/api/drivers/nearby?lat=&lng=&radius=` | Conductores online+libres con distancia |
| GET | `/api/trip/<id>/status` | Estado + datos del conductor |
| GET | `/api/trip/<id>/eta` | ETA conductor→pickup |
| GET | `/api/trip/<id>/driver-eta` | ETA simplificada |
| POST | `/api/trip/<id>/cancel` | `{reason}` |
| POST | `/api/trip/<id>/rate` | `{rating: 1-5, comment}` |
| GET | `/api/driver/reviews/<id>` | Reseñas de conductor |
| GET | `/api/user/reviews/<id>` | Reseñas de pasajero |
| GET | `/api/trips/available` | Viajes solicitados (con distancia al conductor) |

## Tarifa

```python
TARIFA_BASE = 3.0
TARIFA_POR_KM = 1.5
TARIFA_POR_MIN = 0.25
TARIFA_MINIMA = 5.0
fare = max(TARIFA_BASE + km * TARIFA_POR_KM + min * TARIFA_POR_MIN, TARIFA_MINIMA)
```

Si faltan coordenadas, fallback a cálculo por longitud de string (legacy).

## Rutas de perfil (`backend/auth.py`)

| Ruta | Propósito |
|------|-----------|
| `/profile` | Ver perfil + reseñas + viajes |
| `/profile/edit` | Editar nombre, teléfono, foto, datos de moto, contraseña |

Fotos se guardan en `backend/static/uploads/` (creado automáticamente al iniciar).

## Verificación de email

- Al registrarse se genera código de 6 dígitos y (si SMTP está configurado en `.env`) se envía por correo.
- Rutas: `/verify-email` (pasajero), `/verify-email-driver` (conductor).
- Sin SMTP configurado: el registro omite verificación.

## Mapas

Los mapas usan **OpenStreetMap embeds** (no requiere API key). Si se configura `GOOGLE_MAPS_KEY` en `.env`, se puede cambiar a Google Maps en las templates.

## Comandos

| Acción | Comando |
|--------|---------|
| Servidor dev | `python backend/app.py` |
| Servidor producción | `waitress-serve --bind=0.0.0.0:$PORT backend.app:app` |
| Setup inicial | `python setup.py` |
| Migrar DB existente | `python migrate.py` |
| Usuarios demo | `python create_demo_users.py` |
| Docker | `docker build -t mototaxi . && docker run -p 5000:5000 mototaxi` |

## Detalles técnicos

- `backend/__init__.py` vacío — `app.py:7-9` muta `sys.path` para importar desde la raíz.
- No hay lint, typecheck ni tests configurados.
- Solo Dockerfile y Procfile reflejan el setup de producción.
- `.gitignore` excluye `.env`, `.venv/`, `__pycache__/`.
- Las sesiones son de servidor (Flask session cookies) — no JWT.
- El conductor debe estar `is_online=True` y `is_ocupado=False` para recibir viajes.
- La ubicación del conductor se actualiza vía polling cada 5s (`/api/location/update`).
