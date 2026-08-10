import os
import sys
import logging
import secrets
from datetime import timedelta
from flask import Flask, session, redirect, request, jsonify
from dotenv import load_dotenv

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.models import db
from backend.extensions import limiter
from backend.auth import auth_bp
from backend.routes import main_bp
from backend.company import company_bp
from backend.api import api_bp

base_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(dotenv_path=os.path.join(base_dir, '.env'))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
)
logger = logging.getLogger('van')


def create_app():
    app = Flask(__name__, template_folder='templates', static_folder='static')
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

    database_url = os.getenv('DATABASE_URL')

    if database_url and database_url.startswith('mysql://'):
        database_url = database_url.replace(
        'mysql://',
        'mysql+pymysql://',
        1
    )

    if not database_url:
        database_url = 'sqlite:///:memory:'
        logger.info("DATABASE_URL no definida, usando SQLite en memoria")
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
    if not app.config['SECRET_KEY']:
        raise RuntimeError("SECRET_KEY debe estar definida en .env para produccion")

    # JWT para la API /api/v1 (app móvil). Si JWT_SECRET_KEY no está
    # definida, usa SECRET_KEY (migración incremental; en producción
    # conviene una clave dedicada y rotable).
    app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY') or os.getenv('SECRET_KEY')
    app.config['JWT_ACCESS_TTL_MINUTES'] = int(os.getenv('JWT_ACCESS_TTL_MINUTES', '30'))
    app.config['JWT_REFRESH_TTL_DAYS'] = int(os.getenv('JWT_REFRESH_TTL_DAYS', '30'))

    # Validate SMTP config if any SMTP env var is set
    smtp_user = os.getenv('SMTP_USER')
    smtp_pass = os.getenv('SMTP_PASS')
    if smtp_user or smtp_pass:
        if not (smtp_user and smtp_pass):
            logger.warning("SMTP_USER or SMTP_PASS set without the other - email will not work")

    # Session security config
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['SESSION_COOKIE_SECURE'] = bool(os.getenv('RAILWAY_ENVIRONMENT') or os.getenv('SSL_ENABLED'))
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=4)

    if database_url:
        try:
            host = database_url.split('@')[1].split('/')[0]
            logger.info(f"DB conectada a: {host}")
        except Exception:
            logger.info("DB conectada")

    db.init_app(app)
    limiter.init_app(app)

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(company_bp)
    app.register_blueprint(api_bp)

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

    @app.template_filter('payment_label')
    def payment_label_filter(key):
        labels = {
            'efectivo': '💵 Efectivo',
            'mercadopago': '💙 MercadoPago',
            'transferencia': '🏦 Transferencia',
            'tarjeta': '💳 Tarjeta',
            'billetera': '💰 Billetera',
        }
        return labels.get(key, key)

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
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' 'unsafe-inline' https://unpkg.com https://cdn.jsdelivr.com https://js.mercadopago.com; style-src 'self' 'unsafe-inline' https://unpkg.com; img-src 'self' data:; connect-src 'self' https://nominatim.openstreetmap.org; font-src 'self'"
        if request.is_secure or os.getenv('RAILWAY_ENVIRONMENT'):
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        return response

    @app.teardown_appcontext
    def shutdown_session(exception=None):
        if exception:
            logger.error(f"App context teardown with exception: {exception}")
            db.session.rollback()
        db.session.remove()

    @app.errorhandler(404)
    def not_found(e):
        if request.path.startswith('/api/'):
            return jsonify({'error': 'Recurso no encontrado'}), 404
        return 'Página no encontrada', 404

    @app.errorhandler(500)
    def server_error(e):
        logger.error(f"500 error: {e}")
        if request.path.startswith('/api/'):
            return jsonify({'error': 'Error interno del servidor'}), 500
        return 'Error interno del servidor', 500

    @app.errorhandler(429)
    def rate_limited(e):
        if request.path.startswith('/api/'):
            return jsonify({'error': 'Demasiadas peticiones, intenta más tarde'}), 429
        return 'Demasiadas peticiones, intenta más tarde', 429

    with app.app_context():
        from backend.migration import run_all as run_migrations
        run_migrations(app)

    return app


app = create_app()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    is_dev = os.getenv('RAILWAY_ENVIRONMENT') is None
    is_debug = is_dev and os.getenv('FLASK_DEBUG', '0') == '1'
    ssl_enabled = os.getenv('SSL_ENABLED', '').lower() in ('true', '1', 'yes')
    ssl_ctx = None
    if ssl_enabled:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        cert = os.path.join(base_dir, 'cert.pem')
        key = os.path.join(base_dir, 'key.pem')
        if os.path.exists(cert) and os.path.exists(key):
            ssl_ctx = (cert, key)
            logger.info("SSL habilitado - https://0.0.0.0:%d", port)
        else:
            logger.warning("SSL_ENABLED=true pero no se encontraron cert.pem / key.pem. Ejecutá: python backend/generate_cert.py")
    app.run(host='0.0.0.0', port=port, debug=is_debug, use_reloader=False, threaded=True, ssl_context=ssl_ctx)
