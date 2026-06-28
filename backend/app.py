import os
import sys
from flask import Flask
from dotenv import load_dotenv

# Permitir ejecución directa desde la raíz del proyecto
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.models import db
from backend.auth import auth_bp
from backend.routes import main_bp

# Cargar variables desde backend/.env (no existe en Railway, no pasa nada)
base_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(dotenv_path=os.path.join(base_dir, '.env'))


def _ensure_columns(engine):
    """
    Agrega columnas faltantes sin depender de inspect().
    Cada ALTER TABLE se ejecuta individualmente con try/except.
    """
    from sqlalchemy import text

    statements = [
        # users
        "ALTER TABLE users ADD COLUMN profile_picture VARCHAR(255) NULL",
        "ALTER TABLE users ADD COLUMN email_verified TINYINT(1) DEFAULT 0",
        "ALTER TABLE users ADD COLUMN rating_avg FLOAT DEFAULT 5.0",
        "ALTER TABLE users ADD COLUMN rating_count INTEGER DEFAULT 0",
        # drivers
        "ALTER TABLE drivers ADD COLUMN profile_picture VARCHAR(255) NULL",
        "ALTER TABLE drivers ADD COLUMN email_verified TINYINT(1) DEFAULT 0",
        "ALTER TABLE drivers ADD COLUMN is_online TINYINT(1) DEFAULT 0",
        "ALTER TABLE drivers ADD COLUMN is_ocupado TINYINT(1) DEFAULT 0",
        "ALTER TABLE drivers ADD COLUMN lat FLOAT NULL",
        "ALTER TABLE drivers ADD COLUMN lng FLOAT NULL",
        "ALTER TABLE drivers ADD COLUMN last_location_update DATETIME NULL",
        "ALTER TABLE drivers ADD COLUMN rating_avg FLOAT DEFAULT 5.0",
        "ALTER TABLE drivers ADD COLUMN rating_count INTEGER DEFAULT 0",
        # trips
        "ALTER TABLE trips ADD COLUMN pickup_lat FLOAT NULL",
        "ALTER TABLE trips ADD COLUMN pickup_lng FLOAT NULL",
        "ALTER TABLE trips ADD COLUMN dropoff_lat FLOAT NULL",
        "ALTER TABLE trips ADD COLUMN dropoff_lng FLOAT NULL",
        "ALTER TABLE trips ADD COLUMN distance_km FLOAT NULL",
        "ALTER TABLE trips ADD COLUMN duration_min INTEGER NULL",
        "ALTER TABLE trips ADD COLUMN started_at DATETIME NULL",
        "ALTER TABLE trips ADD COLUMN completed_at DATETIME NULL",
        "ALTER TABLE trips ADD COLUMN cancelled_by VARCHAR(20) NULL",
    ]

    with engine.connect() as conn:
        for sql in statements:
            try:
                conn.execute(text(sql))
                print(f"  ✅ {sql}")
            except Exception as e:
                err = str(e)
                ignore = ["Duplicate column", "Unknown database", "doesn't exist"]
                if not any(ig in err for ig in ignore):
                    print(f"  ℹ️  {err[:120]}")


def _ensure_tables(engine):
    """Crea las tablas que falten (reviews, driver_sessions)."""
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    pending = []

    try:
        inspector.get_columns("reviews")
    except Exception:
        pending.append("""
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTO_INCREMENT,
                trip_id INTEGER NOT NULL,
                from_user_id INTEGER NULL,
                from_driver_id INTEGER NULL,
                to_user_id INTEGER NULL,
                to_driver_id INTEGER NULL,
                rating INTEGER NOT NULL,
                comment TEXT NULL,
                role VARCHAR(10) NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (trip_id) REFERENCES trips(id),
                FOREIGN KEY (from_user_id) REFERENCES users(id),
                FOREIGN KEY (from_driver_id) REFERENCES drivers(id),
                FOREIGN KEY (to_user_id) REFERENCES users(id),
                FOREIGN KEY (to_driver_id) REFERENCES drivers(id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

    try:
        inspector.get_columns("driver_sessions")
    except Exception:
        pending.append("""
            CREATE TABLE IF NOT EXISTS driver_sessions (
                id INTEGER PRIMARY KEY AUTO_INCREMENT,
                driver_id INTEGER NOT NULL,
                is_online TINYINT(1) DEFAULT 0,
                lat FLOAT NULL,
                lng FLOAT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (driver_id) REFERENCES drivers(id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

    for ddl in pending:
        with engine.connect() as conn:
            conn.execute(text(ddl))
        print(f"  ✅ Tabla creada")


def create_app():
    app = Flask(__name__, template_folder='templates', static_folder='static')

    database_url = os.getenv('DATABASE_URL')

    if database_url and database_url.startswith('mysql://'):
        database_url = database_url.replace(
        'mysql://',
        'mysql+pymysql://',
        1
    )

    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret')

    print("DATABASE_URL =", database_url)

    db.init_app(app)

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)

    os.makedirs(os.path.join(base_dir, 'static', 'uploads'), exist_ok=True)

    @app.template_filter('status_label')
    def status_label_filter(status):
        labels = {
            'requested': 'Solicitado',
            'accepted': 'Aceptado',
            'ongoing': 'En curso',
            'completed': 'Completado',
            'cancelled': 'Cancelado',
        }
        return labels.get(status, status)

    with app.app_context():
        print("--- Iniciando migración de columnas ---")
        try:
            _ensure_columns(db.engine)
        except Exception as e:
            print(f"⚠️  Error en _ensure_columns: {e}")
        try:
            _ensure_tables(db.engine)
        except Exception as e:
            print(f"⚠️  Error en _ensure_tables: {e}")
        print("--- Migración finalizada ---")
        db.create_all()

    return app


app = create_app()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
