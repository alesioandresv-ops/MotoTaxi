import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['SECRET_KEY'] = 'test-secret-key'
os.environ['JWT_SECRET_KEY'] = 'test-jwt-secret-key'
os.environ['FLASK_DEBUG'] = '0'
os.environ['RATELIMIT_ENABLED'] = '0'

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
