"""Integración MercadoPago post-auditoría (2026-08-24).

Bajo prueba:
- services.mercadopago.validate_webhook_signature: manifest ts/v1 del SDK
  oficial; fail-closed cuando MP_WEBHOOK_SECRET está configurado.
- Selección de credenciales por entorno (MP_ENV test|production).
- create_topup_preference: persiste TopUpRequest pending con preference_id;
  notification_url/auto_return solo con BASE_URL público.
- Webhooks (wallet y empresa): 403 ante firma inválida con secret; dedup de
  activación de empresa por payment_reference.

El SDK se reemplaza con un fake vía sys.modules['mercadopago'] (el servicio
importa mercadopago tardío, así el fake entra limpio).
"""
import hashlib
import hmac
import sys
import time
import types

import pytest

from backend.models import Company, TopUpRequest, User, db
from backend.services import mercadopago as mps

SECRET = 'test-webhook-secret'


def _sign(data_id, request_id='req-1', secret=SECRET, ts=None):
    """Firma manifest oficial: v1 = HMAC-SHA256('id:...;request-id:...;ts:...;')."""
    ts = str(ts if ts is not None else int(time.time()))
    manifest = f'id:{data_id};request-id:{request_id};ts:{ts};'
    v1 = hmac.new(secret.encode(), manifest.encode(), hashlib.sha256).hexdigest()
    return f'ts={ts},v1={v1}'


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


class _FakePreferenceAPI:
    def __init__(self, holder):
        self._holder = holder

    def create(self, data):
        self._holder['payload'] = data
        return self._holder['preference_result']


class _FakePaymentsAPI:
    def __init__(self, holder):
        self._holder = holder

    def get(self, payment_id):
        return {'status': 200,
                'response': dict(self._holder['payment_response'], id=payment_id)}


def _install_fake_sdk(monkeypatch, payment_response=None, preference_result=None):
    holder = {
        'payment_response': payment_response or {},
        'preference_result': preference_result or {'status': 201, 'response': {}},
        'payload': None,
        'token': None,
    }

    class _FakeSDK:
        def __init__(self, token):
            holder['token'] = token

        def payment(self):
            return _FakePaymentsAPI(holder)

        def preference(self):
            return _FakePreferenceAPI(holder)

    monkeypatch.setitem(sys.modules, 'mercadopago', types.SimpleNamespace(SDK=_FakeSDK))
    return holder


@pytest.fixture
def mp_test_env(monkeypatch):
    """Entorno MP de prueba sin secret de webhook."""
    monkeypatch.setenv('MP_ENV', 'test')
    monkeypatch.setenv('MERCADOPAGO_TEST_ACCESS_TOKEN', 'test-mp-token')
    monkeypatch.delenv('MP_WEBHOOK_SECRET', raising=False)


APPROVED_PAYMENT = {
    'status': 'approved',
    'external_reference': None,  # se completa por test
    'transaction_amount': 500,
}
PREFERENCE_OK = {'status': 201, 'response': {
    'id': 'PREF-1', 'init_point': 'https://www.mercadopago.com.ar/checkout/v1/redirect?pref_id=PREF-1',
}}


class TestSignatureValidation:
    """Manifest ts/v1 — vectores generados localmente contra el SDK real."""

    def test_firma_valida_aceptada(self, monkeypatch):
        monkeypatch.setenv('MP_WEBHOOK_SECRET', SECRET)
        assert mps.validate_webhook_signature(_sign(123), 'req-1', '123') is True

    def test_secret_distinto_rechazado(self, monkeypatch):
        monkeypatch.setenv('MP_WEBHOOK_SECRET', SECRET)
        assert mps.validate_webhook_signature(_sign(123, secret='otro'), 'req-1', '123') is False

    def test_data_id_alterado_rechazado(self, monkeypatch):
        monkeypatch.setenv('MP_WEBHOOK_SECRET', SECRET)
        assert mps.validate_webhook_signature(_sign(123), 'req-1', '999') is False

    def test_request_id_alterado_rechazado(self, monkeypatch):
        monkeypatch.setenv('MP_WEBHOOK_SECRET', SECRET)
        assert mps.validate_webhook_signature(_sign(123), 'req-distinto', '123') is False

    def test_sin_header_fail_closed(self, monkeypatch):
        monkeypatch.setenv('MP_WEBHOOK_SECRET', SECRET)
        assert mps.validate_webhook_signature(None, 'req-1', '123') is False

    def test_sin_secret_dev_acepta(self, monkeypatch):
        monkeypatch.delenv('MP_WEBHOOK_SECRET', raising=False)
        assert mps.validate_webhook_signature(None, None, None) is True


class TestCredencialesPorEntorno:
    def test_mp_env_test_usa_token_de_prueba(self, mp_test_env):
        assert mps.mp_environment() == 'test'
        assert mps.mp_access_token() == 'test-mp-token'

    def test_mp_env_test_sin_credencial_lanza_config_error(self, monkeypatch):
        monkeypatch.setenv('MP_ENV', 'test')
        monkeypatch.delenv('MERCADOPAGO_TEST_ACCESS_TOKEN', raising=False)
        with pytest.raises(mps.MercadoPagoConfigError):
            mps.mp_access_token()

    def test_default_produccion_usa_access_token(self, monkeypatch):
        monkeypatch.delenv('MP_ENV', raising=False)
        monkeypatch.delenv('MERCADOPAGO_TEST_ACCESS_TOKEN', raising=False)
        monkeypatch.setenv('MERCADOPAGO_ACCESS_TOKEN', 'prod-token')
        assert mps.mp_access_token() == 'prod-token'

    def test_get_sdk_pasa_el_token_del_entorno(self, mp_test_env, monkeypatch):
        holder = _install_fake_sdk(monkeypatch)
        mps.get_sdk()
        assert holder['token'] == 'test-mp-token'

    def test_public_key_por_entorno(self, monkeypatch):
        monkeypatch.setenv('MP_ENV', 'test')
        monkeypatch.setenv('MERCADOPAGO_TEST_PUBLIC_KEY', 'TEST-PUB')
        monkeypatch.setenv('MERCADOPAGO_PUBLIC_KEY', 'PROD-PUB')
        assert mps.mp_public_key() == 'TEST-PUB'

    def test_sin_credencial_en_produccion_lanza_config_error(self, app, monkeypatch):
        monkeypatch.delenv('MP_ENV', raising=False)
        monkeypatch.delenv('MERCADOPAGO_ACCESS_TOKEN', raising=False)
        _install_fake_sdk(monkeypatch)
        with pytest.raises(mps.MercadoPagoConfigError):
            mps.get_sdk()


class TestCreateTopupPreference:
    def test_crea_y_persiste_pending_con_preference_id(self, app, mp_test_env, monkeypatch):
        uid = _mkuser(app)
        holder = _install_fake_sdk(monkeypatch, preference_result=PREFERENCE_OK)
        with app.app_context():
            init_point, topup_id = mps.create_topup_preference(uid, 500)
            assert init_point == PREFERENCE_OK['response']['init_point']
            t = db.session.get(TopUpRequest, topup_id)
            assert t.status == 'pending'
            assert t.preference_id == 'PREF-1'
            assert t.method == 'mp_checkout'
            assert float(t.amount) == 500.0
            payload = holder['payload']
            assert payload['external_reference'] == str(uid)
            assert payload['items'][0]['unit_price'] == 500.0
            # auto_return SIEMPRE presente (fix bug congrats MP 2026-08-24)
            assert payload['auto_return'] == 'approved'
            assert payload['back_urls']['success'].endswith('/wallet/topup/success')

    def test_localhost_con_auto_return_sin_notification_url(self, app, mp_test_env, monkeypatch):
        """En localhost el webhook es inalcanzable, pero auto_return va igual
        para que MP devuelva al usuario a la página de validación."""
        uid = _mkuser(app)
        monkeypatch.setenv('BASE_URL', 'http://127.0.0.1:5000')
        holder = _install_fake_sdk(monkeypatch, preference_result=PREFERENCE_OK)
        with app.app_context():
            mps.create_topup_preference(uid, 500)
        payload = holder['payload']
        assert 'notification_url' not in payload
        assert payload['auto_return'] == 'approved'

    def test_base_url_publico_incluye_webhook_y_auto_return(self, app, mp_test_env, monkeypatch):
        uid = _mkuser(app)
        monkeypatch.setenv('BASE_URL', 'https://van.com.ar')
        holder = _install_fake_sdk(monkeypatch, preference_result=PREFERENCE_OK)
        with app.app_context():
            mps.create_topup_preference(uid, 500)
        payload = holder['payload']
        assert payload['auto_return'] == 'approved'
        assert payload['notification_url'].startswith('https://van.com.ar/api/wallet/topup/webhook')
        assert payload['notification_url'].endswith('?source_news=webhooks')

    def test_cliente_mobile_usa_deep_links_app_scheme(self, app, mp_test_env, monkeypatch):
        """Header X-Client-Type: mobile → back_urls con APP_SCHEME (van://)."""
        uid = _mkuser(app)
        monkeypatch.setenv('APP_SCHEME', 'van://')
        holder = _install_fake_sdk(monkeypatch, preference_result=PREFERENCE_OK)
        with app.app_context():
            mps.create_topup_preference(uid, 500, client='mobile')
        back = holder['payload']['back_urls']
        assert back['success'] == 'van://wallet/topup/success'
        assert back['failure'] == 'van://wallet/topup/failure'
        assert back['pending'] == 'van://wallet/topup/pending'

    def test_cliente_web_default_usa_base_url(self, app, mp_test_env, monkeypatch):
        uid = _mkuser(app)
        monkeypatch.setenv('BASE_URL', 'https://van.com.ar')
        holder = _install_fake_sdk(monkeypatch, preference_result=PREFERENCE_OK)
        with app.app_context():
            mps.create_topup_preference(uid, 300, client='web')
        assert holder['payload']['back_urls']['success'] == 'https://van.com.ar/wallet/topup/success'

    def test_error_de_mp_no_persiste_fila(self, app, mp_test_env, monkeypatch):
        uid = _mkuser(app)
        _install_fake_sdk(
            monkeypatch,
            preference_result={'status': 400, 'response': {'message': 'invalid item'}},
        )
        with app.app_context():
            with pytest.raises(mps.MercadoPagoAPIError):
                mps.create_topup_preference(uid, 500)
            assert TopUpRequest.query.count() == 0

    def test_marcar_expirada_es_best_effort(self, app, mp_test_env, monkeypatch):
        uid = _mkuser(app)
        _install_fake_sdk(monkeypatch, preference_result=PREFERENCE_OK)
        with app.app_context():
            _, topup_id = mps.create_topup_preference(uid, 300)
            mps.mark_topup_preference_expired(topup_id)
            assert db.session.get(TopUpRequest, topup_id).status == 'expired'
            # No lanza aunque la fila no exista.
            mps.mark_topup_preference_expired(999999)


class TestWebhookWalletConFirma:
    def _post(self, client, data_id, headers=None):
        return client.post(
            '/api/wallet/topup/webhook',
            query_string={'data.id': str(data_id)},
            headers=headers or {},
            json={'action': 'payment.updated', 'data': {'id': data_id}},
        )

    def test_firma_invalida_403_no_acredita(self, app, client, mp_test_env, monkeypatch):
        monkeypatch.setenv('MP_WEBHOOK_SECRET', SECRET)
        uid = _mkuser(app)
        _install_fake_sdk(
            monkeypatch,
            payment_response=dict(APPROVED_PAYMENT, external_reference=str(uid)),
        )
        rv = self._post(client, 4242, headers={'x-signature': 'ts=1,v1=deadbeef'})
        assert rv.status_code == 403
        with app.app_context():
            assert db.session.get(User, uid).balance == 0.0
            assert TopUpRequest.query.filter_by(mp_payment_id='4242').count() == 0

    def test_firma_ausente_fail_closed_403(self, app, client, mp_test_env, monkeypatch):
        monkeypatch.setenv('MP_WEBHOOK_SECRET', SECRET)
        uid = _mkuser(app)
        _install_fake_sdk(
            monkeypatch,
            payment_response=dict(APPROVED_PAYMENT, external_reference=str(uid)),
        )
        rv = self._post(client, 4243)
        assert rv.status_code == 403
        with app.app_context():
            assert db.session.get(User, uid).balance == 0.0

    def test_firma_valida_acredita(self, app, client, mp_test_env, monkeypatch):
        monkeypatch.setenv('MP_WEBHOOK_SECRET', SECRET)
        uid = _mkuser(app)
        _install_fake_sdk(
            monkeypatch,
            payment_response=dict(APPROVED_PAYMENT, external_reference=str(uid)),
        )
        headers = {'x-signature': _sign(4242), 'x-request-id': 'req-1'}
        rv = self._post(client, 4242, headers=headers)
        assert rv.status_code == 200
        assert rv.get_json() == {'status': 'ok'}
        with app.app_context():
            assert float(db.session.get(User, uid).balance) == 500.0


class TestWebhookEmpresa:
    PLAN_BASIC_PRICE = 60000

    def _mkcompany(self, app):
        with app.app_context():
            c = Company(
                name='ACME', email='acme@t.com', password='x',
                plan='basic', status='pending_payment', max_employees=15,
            )
            db.session.add(c)
            db.session.commit()
            return c.id

    def _approved_payment_for_company(self, cid):
        return dict(APPROVED_PAYMENT,
                    external_reference=str(cid),
                    transaction_amount=self.PLAN_BASIC_PRICE)

    def _post(self, client, data_id, signature=None):
        headers = {}
        if signature is not None:
            headers['x-signature'] = _sign(data_id, request_id='r9') if signature is True \
                else signature
            headers['x-request-id'] = 'r9'
        return client.post(
            '/company/payment/webhook',
            query_string={'data.id': str(data_id)},
            headers=headers,
            json={'action': 'payment.created', 'data': {'id': data_id}},
        )

    def test_firma_invalida_403_no_activa(self, app, client, mp_test_env, monkeypatch):
        monkeypatch.setenv('MP_WEBHOOK_SECRET', SECRET)
        cid = self._mkcompany(app)
        _install_fake_sdk(monkeypatch, payment_response=self._approved_payment_for_company(cid))
        rv = self._post(client, 777, signature='ts=1,v1=forjada')
        assert rv.status_code == 403
        with app.app_context():
            assert db.session.get(Company, cid).status == 'pending_payment'

    def test_firma_valida_activa_empresa(self, app, client, mp_test_env, monkeypatch):
        monkeypatch.setenv('MP_WEBHOOK_SECRET', SECRET)
        cid = self._mkcompany(app)
        _install_fake_sdk(monkeypatch, payment_response=self._approved_payment_for_company(cid))
        rv = self._post(client, 777, signature=True)
        assert rv.status_code == 200
        with app.app_context():
            comp = db.session.get(Company, cid)
            assert comp.status == 'active'
            assert comp.payment_method == 'mercadopago'
            assert comp.payment_reference == '777'
            assert comp.subscription_start is not None

    def test_monto_menor_al_plan_no_activa(self, app, client, mp_test_env, monkeypatch):
        cid = self._mkcompany(app)
        pago = dict(APPROVED_PAYMENT, external_reference=str(cid), transaction_amount=100)
        _install_fake_sdk(monkeypatch, payment_response=pago)
        rv = self._post(client, 778)
        assert rv.status_code == 200
        with app.app_context():
            assert db.session.get(Company, cid).status == 'pending_payment'

    def test_dedup_retry_no_reactiva(self, app, client, mp_test_env, monkeypatch):
        """Retry del webhook no pisa subscription_start ni re-procesa."""
        monkeypatch.setenv('MP_WEBHOOK_SECRET', SECRET)
        cid = self._mkcompany(app)
        _install_fake_sdk(monkeypatch, payment_response=self._approved_payment_for_company(cid))
        self._post(client, 779, signature=True)
        with app.app_context():
            comp = db.session.get(Company, cid)
            primera_act = comp.subscription_start
            comp.status = 'pending_payment'  # admin la revierte p.ej. por re-bill
            db.session.commit()
        self._post(client, 779, signature=True)
        with app.app_context():
            comp = db.session.get(Company, cid)
            assert comp.status == 'pending_payment'
            assert comp.subscription_start == primera_act


# ─── Fix auto_return + página de validación (bug congrats MP 2026-08-24) ───

import re

PAX_EMAIL = 'paxv@t.com'


def _mkpax(app, email=PAX_EMAIL, balance=0.0):
    from werkzeug.security import generate_password_hash
    with app.app_context():
        u = User(
            name='PaxV', email=email, password=generate_password_hash('Pass1234'),
            phone='3005556666', email_verified=True, balance=balance,
        )
        db.session.add(u)
        db.session.commit()
        return u.id


def _login_pax(client, email=PAX_EMAIL):
    """Login y devuelve el CSRF VIGENTE (el login regenera session.csrf_token)."""
    rv = client.get('/login')
    m = re.search(rb'window\.CSRF_TOKEN\s*=\s*"([^"]+)"', rv.data)
    client.post(
        '/login',
        data={'email': email, 'password': 'Pass1234',
              'csrf_token': m.group(1).decode() if m else ''},
        follow_redirects=True,
    )
    rv2 = client.get('/login')
    m2 = re.search(rb'window\.CSRF_TOKEN\s*=\s*"([^"]+)"', rv2.data)
    return m2.group(1).decode() if m2 else ''


class TestTopupVerifyEndpoint:
    def test_acredita_y_devuelve_monto(self, app, client, mp_test_env, monkeypatch):
        uid = _mkpax(app, balance=0.0)
        _install_fake_sdk(
            monkeypatch,
            payment_response=dict(APPROVED_PAYMENT, external_reference=str(uid)),
        )
        csrf = _login_pax(client)
        rv = client.post('/api/wallet/topup/verify',
                         headers={'X-CSRF-Token': csrf},
                         json={'payment_id': 5100})
        assert rv.status_code == 200
        j = rv.get_json()
        assert j['credited'] is True
        assert j['amount'] == 500.0
        with app.app_context():
            assert float(db.session.get(User, uid).balance) == 500.0

    def test_retry_idempotente_no_duplica(self, app, client, mp_test_env, monkeypatch):
        uid = _mkpax(app)
        _install_fake_sdk(
            monkeypatch,
            payment_response=dict(APPROVED_PAYMENT, external_reference=str(uid)),
        )
        csrf = _login_pax(client)
        for _ in range(2):  # el loader puede reintentar
            rv = client.post('/api/wallet/topup/verify',
                             headers={'X-CSRF-Token': csrf},
                             json={'payment_id': 5101})
            assert rv.status_code == 200
            assert rv.get_json()['credited'] is True
        with app.app_context():
            assert float(db.session.get(User, uid).balance) == 500.0
            assert TopUpRequest.query.filter_by(mp_payment_id='5101').count() == 1

    def test_pago_ajeno_rechazado(self, app, client, mp_test_env, monkeypatch):
        """El pago debe pertenecer al usuario de sesión (expected_user_id)."""
        _mkpax(app)
        otro_uid = _mkpax(app, email='otro@t.com')
        _install_fake_sdk(
            monkeypatch,
            payment_response=dict(APPROVED_PAYMENT, external_reference=str(otro_uid)),
        )
        csrf = _login_pax(client)
        rv = client.post('/api/wallet/topup/verify',
                         headers={'X-CSRF-Token': csrf},
                         json={'payment_id': 5102})
        assert rv.status_code == 200
        assert rv.get_json() == {'credited': False, 'amount': None}

    def test_sin_payment_id_400(self, app, client, mp_test_env, monkeypatch):
        _mkpax(app)
        _install_fake_sdk(monkeypatch)
        csrf = _login_pax(client)
        rv = client.post('/api/wallet/topup/verify',
                         headers={'X-CSRF-Token': csrf}, json={})
        assert rv.status_code == 400

    def test_requiere_login(self, app, client, mp_test_env, monkeypatch):
        _install_fake_sdk(monkeypatch)
        rv = client.post('/api/wallet/topup/verify', json={'payment_id': 1})
        assert rv.status_code in (302, 401)


class TestTopupSuccessPage:
    def test_renderiza_loader_con_payment_id(self, app, client):
        _mkpax(app)
        _login_pax(client)
        rv = client.get('/wallet/topup/success?payment_id=4242&status=approved')
        assert rv.status_code == 200
        html = rv.data.decode()
        assert 'Validando pago' in html
        assert '4242' in html
        assert '/api/wallet/topup/verify' in html
        # TODO(mobile): deep link documentado en la plantilla.
        assert 'van://pago/exitoso' in html

    def test_requiere_login(self, app, client):
        rv = client.get('/wallet/topup/success?payment_id=4242')
        assert rv.status_code == 302


class TestClientTypeHeader:
    def test_topup_con_header_mobile_genera_deep_links(self, app, client, mp_test_env, monkeypatch):
        """POST /api/wallet/topup con X-Client-Type: mobile → back_urls van://."""
        _mkpax(app)
        monkeypatch.setenv('APP_SCHEME', 'van://')
        holder = _install_fake_sdk(monkeypatch, preference_result=PREFERENCE_OK)
        csrf = _login_pax(client)
        rv = client.post('/api/wallet/topup',
                         headers={'X-CSRF-Token': csrf, 'X-Client-Type': 'mobile'},
                         json={'amount': 500, 'method': 'mp_checkout'})
        assert rv.status_code == 200
        assert holder['payload']['back_urls']['success'] == 'van://wallet/topup/success'

    def test_topup_sin_header_mantiene_urls_web(self, app, client, mp_test_env, monkeypatch):
        _mkpax(app)
        monkeypatch.setenv('BASE_URL', 'https://van.com.ar')
        holder = _install_fake_sdk(monkeypatch, preference_result=PREFERENCE_OK)
        csrf = _login_pax(client)
        rv = client.post('/api/wallet/topup',
                         headers={'X-CSRF-Token': csrf},
                         json={'amount': 500, 'method': 'mp_checkout'})
        assert rv.status_code == 200
        assert holder['payload']['back_urls']['success'].startswith('https://van.com.ar/')
