import os
import sys
import secrets
from datetime import timedelta
from flask import Flask, session, redirect, request
from dotenv import load_dotenv

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.models import db
from backend.extensions import limiter
from backend.auth import auth_bp
from backend.routes import main_bp
from backend.company import company_bp

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

    if not database_url:
        database_url = 'sqlite:///:memory:'
        print("DATABASE_URL no definida, usando SQLite en memoria")
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
    if not app.config['SECRET_KEY']:
        raise RuntimeError("SECRET_KEY debe estar definida en .env para produccion")

    # Session security config
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=4)
    if os.getenv('RAILWAY_ENVIRONMENT'):
        app.config['SESSION_COOKIE_SECURE'] = True

    if database_url:
        safe_url = database_url.replace(database_url.split('@')[0].split(':')[0] + ':' + database_url.split('@')[0].split(':')[1], '***:***')
        print("DB conectada:", safe_url.split('@')[1] if '@' in safe_url else 'ok')

    db.init_app(app)
    limiter.init_app(app)

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(company_bp)

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

    @app.template_filter('company_status_label')
    def company_status_label_filter(status):
        labels = {
            'trial': 'Prueba',
            'active': 'Activo',
            'inactive': 'Inactivo',
            'pending_payment': 'Pendiente de pago',
        }
        return labels.get(status, status)

    @app.template_filter('plan_label')
    def plan_label_filter(plan):
        labels = {
            'basic': 'Básico',
            'advanced': 'Avanzado',
        }
        return labels.get(plan, plan)

    @app.context_processor
    def inject_csrf():
        if 'csrf_token' not in session:
            session['csrf_token'] = secrets.token_hex(32)
        return {'csrf_token': session['csrf_token']}

    @app.after_request
    def add_security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' 'unsafe-inline' https://unpkg.com https://js.mercadopago.com; style-src 'self' 'unsafe-inline' https://unpkg.com; img-src 'self' data:; connect-src 'self' https://nominatim.openstreetmap.org; font-src 'self'"
        if request.is_secure or os.getenv('RAILWAY_ENVIRONMENT'):
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        return response

    with app.app_context():
        from backend.migration import run_all as run_migrations
        run_migrations(app)

    return app


app = create_app()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=os.getenv('FLASK_DEBUG', '0') == '1', use_reloader=False, threaded=True)
