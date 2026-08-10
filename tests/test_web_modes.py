"""
Tests web de identidad unificada: login por roles, selector de modo para
usuarios duales (both), switch-mode sin nueva cuenta.
"""
import re


def _create_both_user(app):
    from backend.models import db, User, DriverProfile, Vehicle, ROLE_BOTH
    from werkzeug.security import generate_password_hash
    with app.app_context():
        u = User(
            name='Dual User', email='dual@test.com',
            password=generate_password_hash('Pass1234'), phone='3001112233',
            email_verified=True, role=ROLE_BOTH,
            driver_profile=DriverProfile(
                is_online=False, is_busy=False,
                vehicles=[Vehicle(
                    type='moto', placa='ABC123', marca='Yamaha', modelo='R3',
                    color='Azul', cilindrada='300cc', tipo_seguro='Todo riesgo',
                    carnet_conducir='A2', ultimo_servicio='2024-01-01', is_active=True,
                )],
            ),
        )
        db.session.add(u)
        db.session.commit()
        return u.id


def _create_passenger(app):
    from backend.models import db, User
    from werkzeug.security import generate_password_hash
    with app.app_context():
        u = User(name='Pass Only', email='pass@test.com',
                 password=generate_password_hash('Pass1234'),
                 phone='3001112233', email_verified=True)
        db.session.add(u)
        db.session.commit()
        return u.id


def _csrf_from(client, url='/login'):
    rv = client.get(url)
    match = re.search(rb'window\.CSRF_TOKEN\s*=\s*"([^"]+)"', rv.data)
    return match.group(1).decode() if match else ''


class TestDualModeWeb:
    def test_both_login_redirects_to_mode_selector(self, app, client):
        _create_both_user(app)
        csrf = _csrf_from(client)
        rv = client.post('/login', data={
            'email': 'dual@test.com', 'password': 'Pass1234', 'csrf_token': csrf
        }, follow_redirects=True)
        assert rv.status_code == 200
        assert b'select-mode' in rv.data or b'Elije' in rv.data or b'modo' in rv.data.lower()

    def test_mode_selection_sets_driver_mode(self, app, client):
        _create_both_user(app)
        csrf = _csrf_from(client)
        client.post('/login', data={
            'email': 'dual@test.com', 'password': 'Pass1234', 'csrf_token': csrf
        })
        csrf = _csrf_from(client, '/select-mode')
        rv = client.post('/select-mode', data={'mode': 'driver', 'csrf_token': csrf},
                         follow_redirects=True)
        assert rv.status_code == 200
        # dashboard en modo conductor muestra la vista de conductor
        assert b'online-toggle' in rv.data or b'Conectarse' in rv.data

    def test_mode_selection_sets_passenger_mode(self, app, client):
        _create_both_user(app)
        csrf = _csrf_from(client)
        client.post('/login', data={
            'email': 'dual@test.com', 'password': 'Pass1234', 'csrf_token': csrf
        })
        csrf = _csrf_from(client, '/select-mode')
        rv = client.post('/select-mode', data={'mode': 'passenger', 'csrf_token': csrf},
                         follow_redirects=True)
        assert rv.status_code == 200
        assert b'solicitar' in rv.data.lower() or b'viaje' in rv.data.lower()

    def test_switch_mode_api_requires_csrf(self, app, client):
        _create_both_user(app)
        csrf = _csrf_from(client)
        client.post('/login', data={
            'email': 'dual@test.com', 'password': 'Pass1234', 'csrf_token': csrf
        })
        csrf = _csrf_from(client, '/select-mode')
        client.post('/select-mode', data={'mode': 'passenger', 'csrf_token': csrf},
                    follow_redirects=True)
        rv = client.post('/switch-mode', data={'mode': 'driver'})
        assert rv.status_code == 403

    def test_switch_mode_api_ok_with_csrf(self, app, client):
        _create_both_user(app)
        csrf = _csrf_from(client)
        client.post('/login', data={
            'email': 'dual@test.com', 'password': 'Pass1234', 'csrf_token': csrf
        })
        csrf = _csrf_from(client, '/select-mode')
        client.post('/select-mode', data={'mode': 'passenger', 'csrf_token': csrf},
                    follow_redirects=True)
        csrf = _csrf_from(client, '/dashboard')
        rv = client.post('/switch-mode', data={'mode': 'driver', 'csrf_token': csrf},
                         follow_redirects=True)
        assert rv.status_code == 200
        assert b'Conectarse' in rv.data  # vista conductor

    def test_single_role_user_skips_selector(self, app, client):
        _create_passenger(app)
        csrf = _csrf_from(client)
        rv = client.post('/login', data={
            'email': 'pass@test.com', 'password': 'Pass1234', 'csrf_token': csrf
        }, follow_redirects=True)
        assert rv.status_code == 200
        assert b'select-mode' not in rv.data

    def test_driver_dashboard_uses_unified_identity(self, app, client):
        _create_both_user(app)
        csrf = _csrf_from(client)
        client.post('/login', data={
            'email': 'dual@test.com', 'password': 'Pass1234', 'csrf_token': csrf
        })
        csrf = _csrf_from(client, '/select-mode')
        rv = client.post('/select-mode', data={'mode': 'driver', 'csrf_token': csrf},
                         follow_redirects=True)
        assert rv.status_code == 200
        assert b'Dual User' in rv.data  # identidad unificada (users)
        assert b'Conectarse' in rv.data  # toggle online del perfil de conductor


class TestEditProfileCsrf:
    def test_edit_profile_get_renders_without_csrf_token(self, app, client):
        _create_both_user(app)
        csrf = _csrf_from(client)
        client.post('/login', data={
            'email': 'dual@test.com', 'password': 'Pass1234', 'csrf_token': csrf
        })
        rv = client.get('/profile/edit')
        assert rv.status_code == 200  # GET no debe exigir token CSRF
        assert b'Perfil' in rv.data or b'perfil' in rv.data.lower()

    def test_edit_profile_post_without_csrf_rejected(self, app, client):
        _create_both_user(app)
        csrf = _csrf_from(client)
        client.post('/login', data={
            'email': 'dual@test.com', 'password': 'Pass1234', 'csrf_token': csrf
        })
        rv = client.post('/profile/edit', data={'name': 'Hacker'}, follow_redirects=True)
        assert rv.status_code == 200
        assert b'Token CSRF invalido' in rv.data or b'Dual User' in rv.data

    def test_edit_profile_post_with_csrf_updates(self, app, client):
        _create_both_user(app)
        csrf = _csrf_from(client)
        client.post('/login', data={
            'email': 'dual@test.com', 'password': 'Pass1234', 'csrf_token': csrf
        })
        csrf = _csrf_from(client, '/profile/edit')
        rv = client.post('/profile/edit', data={
            'csrf_token': csrf, 'name': 'Dual Renombrado', 'phone': '3009998887'
        }, follow_redirects=True)
        assert rv.status_code == 200
        assert b'Dual Renombrado' in rv.data
