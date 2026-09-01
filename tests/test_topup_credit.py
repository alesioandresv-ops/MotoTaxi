"""Tests de backend.routes._credit_mp_payment — acreditación de recargas MP.

El helper verifica contra la API de MercadoPago (SDK mockeado) antes de
acreditar. Bajo prueba:
- Solo acredita pagos 'approved' con external_reference válida.
- Dedup idempotente: segundo llamado con el mismo payment_id no duplica.
- expected_user_id: rechaza pagos de otro usuario (ruta web success).
- Rechaza montos <= 0, falta de token y SDK roto — sin lanzar.
"""
import sys
import types

import pytest

from backend.models import TopUpRequest, User, WalletTransaction, db
from backend.routes import _credit_mp_payment


class _FakePaymentsAPI:
    def __init__(self, response):
        self._response = response

    def get(self, payment_id):
        return {'status': 200, 'response': dict(self._response, id=payment_id)}


def _install_fake_sdk(monkeypatch, response):
    """Reemplaza mercadopago.SDK por un fake que devuelve `response`."""
    holder = {'response': response}

    class _FakeSDK:
        def __init__(self, token):
            assert token == 'test-mp-token'

        def payment(self):
            return _FakePaymentsAPI(holder['response'])

    monkeypatch.setitem(sys.modules, 'mercadopago', types.SimpleNamespace(SDK=_FakeSDK))
    return holder


@pytest.fixture
def mp_env(monkeypatch):
    monkeypatch.setenv('MERCADOPAGO_ACCESS_TOKEN', 'test-mp-token')


def _mkuser(app, email='pax@t.com', balance=0.0):
    from werkzeug.security import generate_password_hash

    with app.app_context():
        u = User(
            name='Pax', email=email, password=generate_password_hash('x'),
            phone='3001111111', email_verified=True, balance=balance,
        )
        db.session.add(u)
        db.session.commit()
        return u.id


APPROVED = {
    'status': 'approved',
    'external_reference': None,  # se completa por test
    'transaction_amount': 500,
}


class TestCreditMpPayment:
    def test_acredita_pago_aprobado(self, app, mp_env, monkeypatch):
        uid = _mkuser(app)
        _install_fake_sdk(monkeypatch, dict(APPROVED, external_reference=str(uid)))
        with app.app_context():
            assert _credit_mp_payment(12345) is True
            u = db.session.get(User, uid)
            assert float(u.balance) == 500.0
            topup = TopUpRequest.query.filter_by(mp_payment_id='12345').one()
            assert topup.status == 'confirmed'
            assert float(topup.amount) == 500.0
            tx = WalletTransaction.query.filter_by(user_id=uid).one()
            assert tx.type == 'deposit_mp'
            assert float(tx.amount) == 500.0

    def test_dedup_segunda_llamada_no_duplica(self, app, mp_env, monkeypatch):
        uid = _mkuser(app)
        _install_fake_sdk(monkeypatch, dict(APPROVED, external_reference=str(uid)))
        with app.app_context():
            assert _credit_mp_payment(999) is True
            assert _credit_mp_payment(999) is True  # retry del webhook
            assert float(db.session.get(User, uid).balance) == 500.0
            assert TopUpRequest.query.count() == 1
            assert WalletTransaction.query.count() == 1

    def test_rechaza_usuario_de_sesion_distinto(self, app, mp_env, monkeypatch):
        """Ruta web success: el pago debe pertenecer al usuario logueado."""
        uid = _mkuser(app)
        otro = uid + 1000
        _install_fake_sdk(monkeypatch, dict(APPROVED, external_reference=str(otro)))
        with app.app_context():
            assert _credit_mp_payment(555, expected_user_id=uid) is False
            assert db.session.get(User, uid).balance == 0.0
            assert TopUpRequest.query.count() == 0

    def test_acepta_dueño_legitimo_con_expected_user(self, app, mp_env, monkeypatch):
        uid = _mkuser(app)
        _install_fake_sdk(monkeypatch, dict(APPROVED, external_reference=str(uid)))
        with app.app_context():
            assert _credit_mp_payment(556, expected_user_id=uid) is True

    def test_no_aprobado_no_acredita(self, app, mp_env, monkeypatch):
        uid = _mkuser(app)
        _install_fake_sdk(monkeypatch, dict(APPROVED, external_reference=str(uid), status='pending'))
        with app.app_context():
            assert _credit_mp_payment(777) is False
            assert db.session.get(User, uid).balance == 0.0

    def test_sin_external_reference_no_acredita(self, app, mp_env, monkeypatch):
        _mkuser(app)
        _install_fake_sdk(monkeypatch, dict(APPROVED, external_reference=None))
        with app.app_context():
            assert _credit_mp_payment(778) is False

    def test_monto_cero_o_negativo_no_acredita(self, app, mp_env, monkeypatch):
        uid = _mkuser(app)
        for bad_amount in (0, -50):
            _install_fake_sdk(monkeypatch, dict(
                APPROVED, external_reference=str(uid), transaction_amount=bad_amount,
            ))
            with app.app_context():
                assert _credit_mp_payment(779) is False
                assert db.session.get(User, uid).balance == 0.0

    def test_sin_token_no_acredita_ni_lanza(self, app, monkeypatch):
        monkeypatch.delenv('MERCADOPAGO_ACCESS_TOKEN', raising=False)
        _install_fake_sdk(monkeypatch, {})
        with app.app_context():
            assert _credit_mp_payment(880) is False

    def test_sdk_roto_devuelve_false_sin_lanzar(self, app, mp_env, monkeypatch):
        class _BrokenSDK:
            def __init__(self, token):
                raise RuntimeError('network down')

        monkeypatch.setitem(sys.modules, 'mercadopago', types.SimpleNamespace(SDK=_BrokenSDK))
        _mkuser(app)
        with app.app_context():
            assert _credit_mp_payment(881) is False

    def test_mp_id_invalido(self, app, mp_env, monkeypatch):
        _install_fake_sdk(monkeypatch, {})
        with app.app_context():
            assert _credit_mp_payment(None) is False
            assert _credit_mp_payment('') is False
            assert _credit_mp_payment('no-es-numero') is False


class TestWebhookEndpoint:
    def test_webhook_acredita_y_ackuea(self, app, client, mp_env, monkeypatch):
        uid = _mkuser(app)
        _install_fake_sdk(monkeypatch, dict(APPROVED, external_reference=str(uid)))
        rv = client.post('/api/wallet/topup/webhook', json={
            'action': 'payment.updated', 'data': {'id': 4242},
        })
        assert rv.status_code == 200
        assert rv.get_json() == {'status': 'ok'}
        with app.app_context():
            assert float(db.session.get(User, uid).balance) == 500.0

    def test_webhook_ignora_acciones_irrelevantes(self, app, client, mp_env, monkeypatch):
        uid = _mkuser(app)
        _install_fake_sdk(monkeypatch, dict(APPROVED, external_reference=str(uid)))
        rv = client.post('/api/wallet/topup/webhook', json={
            'action': 'refund.created', 'data': {'id': 1},
        })
        assert rv.status_code == 200
        rv = client.post('/api/wallet/topup/webhook', json={'foo': 'bar'})
        assert rv.status_code == 200
        with app.app_context():
            assert db.session.get(User, uid).balance == 0.0

    def test_webhook_get_challenge(self, app, client):
        rv = client.get('/api/wallet/topup/webhook?challenge=abc123')
        assert rv.status_code == 200
        assert b'abc123' in rv.data
