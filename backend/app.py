import os
import sys
from flask import Flask, send_from_directory, send_file
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
    
    # Get database credentials from environment variables
    db_user = os.getenv('MYSQL_USER') or os.getenv('DB_USER')
    db_password = os.getenv('MYSQL_PASSWORD') or os.getenv('DB_PASSWORD')
    db_host = os.getenv('MYSQL_HOST') or os.getenv('DB_HOST')
    db_port = os.getenv('MYSQL_PORT') or os.getenv('DB_PORT', '3306')
    db_name = os.getenv('MYSQL_DATABASE') or os.getenv('DB_NAME') or os.getenv('MYSQLDATABASE')
    
    # Validate database configuration
    if not all([db_user, db_password, db_host, db_name]):
        print("ERROR: Missing database configuration!")
        print(f"DB_USER = {db_user}")
        print(f"DB_PASSWORD = {'***' if db_password else None}")
        print(f"DB_HOST = {db_host}")
        print(f"DB_PORT = {db_port}")
        print(f"DB_NAME = {db_name}")
        raise ValueError("Database configuration is incomplete. Check environment variables.")
    
    # Build database URI
    database_uri = (
        f"mysql+pymysql://{db_user}:"
        f"{db_password}@"
        f"{db_host}:"
        f"{db_port}/"
        f"{db_name}"
    )
    
    app.config['SQLALCHEMY_DATABASE_URI'] = database_uri
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret')

    print("=" * 60)
    print("DATABASE CONFIGURATION")
    print("=" * 60)
    print(f"DB_USER = {db_user}")
    print(f"DB_HOST = {db_host}")
    print(f"DB_PORT = {db_port}")
    print(f"DB_NAME = {db_name}")
    print(f"DATABASE_URI = {database_uri.replace(db_password, '***')}")
    print("=" * 60)

    db.init_app(app)

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)

    with app.app_context():
        db.create_all()

    # Serve static files and frontend
    @app.route('/')
    def serve_index():
        return send_file(os.path.join(PROJECT_ROOT, 'index.html'))
    
    @app.route('/<path:path>')
    def serve_static(path):
        # Try to serve from static folder first
        static_path = os.path.join(base_dir, 'static', path)
        if os.path.exists(static_path):
            return send_from_directory(os.path.join(base_dir, 'static'), path)
        
        # If not found and it's not an API route, serve index.html (SPA fallback)
        if not path.startswith('api/'):
            return send_file(os.path.join(PROJECT_ROOT, 'index.html'))
        
        # API route not found
        return {'error': 'Not found'}, 404

    return app

app = create_app()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

