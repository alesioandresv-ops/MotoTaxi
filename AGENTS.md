# MotoTaxi

Flask + MySQL app de solicitud de mototaxis. Dos modos de frontend.

## Modos de ejecución

- **Standalone (sin servidor):** abre `demo/index.html` en navegador. Datos mock en memoria JS.
- **Full-stack (Flask + MySQL):** `python backend/app.py`. Requiere MySQL y `backend/.env`.
- **O Directamente **.\.venv\Scripts\python backend\app.py**.

## Setup inicial

```bash
mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS mototaxi"
# Copiar y editar backend/.env (ver .env.example)
python backend/app.py           # Crea tablas + migra columnas al arrancar
python create_demo_users.py     # pasajero@demo.com / 1234, conductor@demo.com / 1234
```

Para crear tablas sin arrancar el servidor: `python setup.py`.

Para migrar columnas en DB existente sin reiniciar: `python migrate.py`.

## Arquitectura

- `backend/app.py` — `create_app()` factory. Al arrancar ejecuta `_ensure_columns()` + `_ensure_tables()` (pymysql directo, autocommit) y luego `db.create_all()`.
- `backend/models.py` — SQLAlchemy: `User`, `Driver`, `Trip`, `Review`, `DriverSession`.
- `backend/routes.py` — Blueprint `main`: rutas HTML + JSON APIs.
- `backend/auth.py` — Blueprint `auth`: registro, login, perfil, verificación email.
- `backend/__init__.py` — solo comentario. `app.py:7-9` muta `sys.path` para imports desde raíz.
- `backend/templates/` — Jinja2 (Inter font, dark theme CSS).
- `demo/index.html` — app SPA en JS vainilla con datos mock (independiente del backend).

## Frontend: dos implementaciones

| Capa | Ruta | Tecnología |
|------|------|------------|
| Server-rendered | `backend/templates/*.html` | Jinja2 + `style.css` (dark) |
| Standalone demo | `demo/index.html` | Vanilla JS, datos mock en memoria |

## Base de datos

- MySQL vía SQLAlchemy + pymysql. `DATABASE_URL` en `backend/.env`.
- `mysql://` se reescribe a `mysql+pymysql://` automáticamente en `app.py:125-130`.
- Migración automática al arrancar (`_ensure_columns` + `_ensure_tables` + `db.create_all()`).
- Para migración manual: `python migrate.py` (ALTER TABLE sin perder datos).

## APIs JSON clave

| Método | Ruta | Propósito |
|--------|------|-----------|
| POST | `/api/location/update` | Conductor envía `{lat, lng}` (cada 5s polling) |
| POST | `/api/driver/toggle_online` | `{is_online: bool}` |
| POST | `/api/driver/respond/<id>` | `{action: "accept"\|"reject"}` |
| GET | `/api/drivers/nearby?lat=&lng=&radius=` | Conductores online+libres c/distancia |
| POST | `/api/trip/<id>/cancel` | `{reason}` |
| POST | `/api/trip/<id>/rate` | `{rating: 1-5, comment}` |
| GET | `/api/trips/available` | Viajes solicitados (con distancia al conductor) |

Ver `backend/routes.py` para firmas completas.

## Ciclo de vida del viaje

`requested` → `accepted` → `ongoing` → `completed` | `cancelled`

Rutas HTML (redirect con flash):
- `POST /passenger/request` — pasajero solicita
- `GET /driver/accept/<id>` — conductor acepta (marca `is_ocupado=True`)
- `GET /driver/start/<id>` → `ongoing`
- `GET /driver/complete/<id>` → `completed`, `is_ocupado=False`

## Tarifa (`backend/routes.py:9-16`)

```
fare = max(BASE + km * POR_KM + min * POR_MIN, MINIMA)
```
[BASE=3.0, POR_KM=1.5, POR_MIN=0.25, MINIMA=5.0]

Fallback a cálculo por longitud de string si faltan coordenadas.

## Sesiones

Flask session cookies (servidor, no JWT). Claves de sesión: `user_id`/`driver_id`.

## Conductores

- `is_online=True` + `is_ocupado=False` para recibir viajes.
- Ubicación por polling cada 5s a `POST /api/location/update`.
- Al hacer logout: `is_online=False`, `is_ocupado=False`.

## Mapas

OpenStreetMap embeds por defecto. Opcional: `GOOGLE_MAPS_KEY` en `.env`. También se referencia `MAPBOX_TOKEN` en templates.

## Verificación de email

Código de 6 dígitos. Si SMTP no está configurado en `.env`, se omite.

## Producción

- `start.sh` → ejecuta `migrate.py` → `waitress-serve --listen=0.0.0.0:$PORT backend.app:app`
- Docker: `docker build -t mototaxi . && docker run -p 5000:5000 mototaxi`
- `.nixpacks` reflect del comando de producción.

## Notas

- No hay tests, lint, ni typecheck configurados.
- Solamente `Dockerfile`, `Procfile`, y `.nixpacks` reflejan producción.
- `.gitignore`: `.env`, `.venv/`, `__pycache__/`, `*.pyc`, `*.pyo`.
- Fotos de perfil: `backend/static/uploads/` (creado al arrancar).
- Pillow está en requirements.txt pero no se usa activamente.
