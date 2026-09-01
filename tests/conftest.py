import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['SECRET_KEY'] = 'test-secret-key'
os.environ['JWT_SECRET_KEY'] = 'test-jwt-secret-key'
os.environ['FLASK_DEBUG'] = '0'
os.environ['RATELIMIT_ENABLED'] = '0'

# Hermeticidad: load_dotenv() en backend/app.py (override=False) puede
# filtrar el backend/.env real (MP_ENV=test, tokens MP) al proceso de tests.
# Precargamos sentinelas que dotenv respeta; cada test ajusta lo que necesita.
os.environ.setdefault('MP_ENV', 'production')
os.environ.setdefault('MERCADOPAGO_TEST_ACCESS_TOKEN', 'sentinel-test-token')
os.environ.setdefault('MERCADOPAGO_TEST_PUBLIC_KEY', 'sentinel-test-pubkey')
os.environ.setdefault('MERCADOPAGO_PUBLIC_KEY', 'sentinel-prod-pubkey')

@pytest.fixture
def app():
    from backend.app import create_app
    app = create_app()
    with app.app_context():
        from backend.models import db
        db.create_all()
        yield app

@pytest.fixture
def client(app):
    return app.test_client()
