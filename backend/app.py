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
from migrate import run_migration_sa

# Cargar variables desde backend/.env siempre que exista
base_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(dotenv_path=os.path.join(base_dir, '.env'))

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
        try:
            run_migration_sa(db)
        except Exception as e:
            print(f"⚠️  Error en migración: {e}")
        db.create_all()

    return app

app = create_app()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
