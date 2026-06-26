## Inicio rápido

La app funciona en dos modos:

- **Standalone (sin servidor):** Abre `demo/index.html` en el navegador. Todos los datos son mock en memoria JS.
- **Full-stack (Flask + MySQL):** Ejecuta `python backend/app.py` (o `python setup.py` primero para crear tablas). Requiere MySQL con base de datos `mototaxi`.

## Base de datos

- **MySQL** vía SQLAlchemy + pymysql. Cadena de conexión desde variable `DATABASE_URL` (cargada de `backend/.env`).
- Las tablas se crean automáticamente al iniciar mediante `db.create_all()` en `app.py:43`.
- Credenciales demo: `pasajero@demo.com` / `1234` y `conductor@demo.com` / `1234` — se crean con `python create_demo_users.py`.

## Modelos

- `User` — pasajero (id, name, email, password, phone)
- `Driver` — conductor (id, name, email, password, phone, placa, moto_*, etc.)
- `Trip` — viaje (passenger_id, driver_id, pickup/dropoff_address, fare, status)

## Ciclo de vida del viaje

`solicitado` → `aceptado` → `en_curso` → `completado`

Las transiciones ocurren en `backend/routes.py`:
- Pasajero solicita: `POST /passenger/request`
- Conductor acepta: `GET /driver/accept/<id>`
- Conductor completa: `GET /driver/complete/<id>`

## Comandos

| Acción | Comando |
|--------|---------|
| Servidor dev | `python backend/app.py` (usa PORT env o 5000) |
| Servidor producción | `waitress-serve --bind=0.0.0.0:$PORT backend.app:app` |
| Setup / crear tablas | `python setup.py` |
| Crear usuarios demo | `python create_demo_users.py` |

## Despliegue

- **Docker:** `FROM python:3.12-slim`, ejecuta `python backend/app.py`
- **Railway/Heroku:** Procfile usa `waitress-serve`
- No existen comandos de lint, typecheck ni tests.
- `.gitignore` excluye `.env`, `.venv/`, `__pycache__/`.

## Detalles importantes

- `backend/__init__.py` está vacío — el paquete funciona porque `app.py:7-9` muta `sys.path` para insertar la raíz del proyecto.
- `backend/.env` contiene credenciales reales — tratar como sensible. Ya no está versionado en git.
- Solo el Dockerfile y Procfile reflejan el setup actual de despliegue.
