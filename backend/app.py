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

# Cargar variables desde backend/.env siempre que exista
base_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(dotenv_path=os.path.join(base_dir, '.env'))

def create_app():
    app = Flask(__name__, template_folder='templates', static_folder='static')
    app.config['SQLALCHEMY_DATABASE_URI'] = (
    f"mysql+pymysql://{os.getenv('DB_USER')}:"
    f"{os.getenv('DB_PASSWORD')}@"
    f"{os.getenv('DB_HOST')}:"
    f"{os.getenv('DB_PORT')}/"
    f"{os.getenv('DB_NAME')}"
)

    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret')

    print("DB_HOST =", os.getenv("DB_HOST"))
    print("DB_PORT =", os.getenv("DB_PORT"))
    print("DB_USER =", os.getenv("DB_USER"))
    print("DB_NAME =", os.getenv("DB_NAME"))

    db.init_app(app)

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)

    with app.app_context():
        db.create_all()

    return app

app = create_app()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
