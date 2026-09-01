"""Etapa 4 — Wallet API v1 (contrato §§4.3, 5.3, 8, 12).

Cubre: balance, transacciones (paginado, filtro por tipo), topups (MP, cvu,
bank), validaciones min/max/método, detalle y listado de topups, aislamiento
entre usuarios.
"""
import json
import uuid
from decimal import Decimal
from unittest.mock import patch


REGISTER_PAX = {
    'name': 'Ana Pérez',
    'email': None,  # se genera por test
    'password': 'Pass1234',
    'phone': '3001112233',
}


def _api(client, method, path, token=None, data=None, headers=None):
    hdrs = dict(headers or {})
    if token:
        hdrs['Authorization'] = f'Bearer {token}'
    return client.open(
        path, method=method, headers=hdrs,
        data=json.dumps(data) if data is not None else None,
        content_type='application/json',
    )


def _uniq(prefix):
    return f'{prefix}-{uuid.uuid4().hex[:8]}@test.com'


def _register_pax(client):
    email = _uniq('ana')
    rv = _api(client, 'POST', '/api/v1/auth/register',
              data=dict(REGISTER_PAX, email=email))
    assert rv.status_code == 201, rv.get_json()
    return email, rv.get_json()['data']['tokens']['access_token']


def _fund(app, email, amount):
    from backend.models import db, User
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        user.balance = Decimal(str(amount))
        db.session.commit()


def _topup_cvu(client, token, amount=500):
    return _api(client, 'POST', '/api/v1/wallet/topups',
                token=token, data={'amount': amount, 'method': 'cvu'})


def _mock_mp_preference(init_point='https://checkout.mp/init/123', pref_id='pref-mock'):
    """Mock that creates the TopUpRequest like the real service, so the
    wallet endpoint's follow-up query works."""
    def _inner(user_id, amount, client='web'):
        from backend.models import TopUpRequest, db
        topup = TopUpRequest(
            user_id=user_id, amount=amount, method='mp_checkout',
            preference_id=pref_id, status='pending',
        )
        db.session.add(topup)
        db.session.commit()
        return init_point, topup.id
    return _inner


# ─── GET /wallet ────────────────────────────────────────────────────────


class TestGetBalance:
    def test_empty_balance(self, client):
        email, token = _register_pax(client)
        rv = _api(client, 'GET', '/api/v1/wallet', token=token)
        assert rv.status_code == 200
        body = rv.get_json()
        assert body['success'] is True
        assert body['data']['balance'] == '0'
        assert body['data']['currency'] == 'ARS'

    def test_funded_balance(self, client, app):
        email, token = _register_pax(client)
        _fund(app, email, 1234.50)
        rv = _api(client, 'GET', '/api/v1/wallet', token=token)
        assert rv.status_code == 200
        assert rv.get_json()['data']['balance'] == '1234.50'

    def test_no_token(self, client):
        rv = _api(client, 'GET', '/api/v1/wallet')
        assert rv.status_code == 401


# ─── GET /wallet/transactions ──────────────────────────────────────────


class TestListTransactions:
    def test_empty(self, client):
        _, token = _register_pax(client)
        rv = _api(client, 'GET', '/api/v1/wallet/transactions', token=token)
        assert rv.status_code == 200
        body = rv.get_json()
        assert body['data']['items'] == []
        assert body['data']['pagination']['total'] == 0

    def test_with_transactions(self, client, app):
        email, token = _register_pax(client)
        # Seed a wallet transaction directly
        from backend.models import db, WalletTransaction, User
        with app.app_context():
            user = User.query.filter_by(email=email).first()
            db.session.add(WalletTransaction(
                user_id=user.id, amount=Decimal('500.00'), type='topup',
                status='completed', description='Recarga',
            ))
            db.session.commit()
        rv = _api(client, 'GET', '/api/v1/wallet/transactions', token=token)
        body = rv.get_json()
        assert len(body['data']['items']) == 1
        assert body['data']['items'][0]['type'] == 'topup'
        assert body['data']['items'][0]['amount'] == '500.00'

    def test_filter_by_type(self, client, app):
        email, token = _register_pax(client)
        from backend.models import db, WalletTransaction, User
        with app.app_context():
            user = User.query.filter_by(email=email).first()
            db.session.add(WalletTransaction(
                user_id=user.id, amount=Decimal('100'), type='topup', status='completed',
            ))
            db.session.add(WalletTransaction(
                user_id=user.id, amount=Decimal('-25.50'), type='trip_payment',
                status='completed', trip_id=1,
            ))
            db.session.commit()
        rv = _api(client, 'GET', '/api/v1/wallet/transactions?type=trip_payment', token=token)
        items = rv.get_json()['data']['items']
        assert len(items) == 1
        assert items[0]['type'] == 'trip_payment'

    def test_pagination(self, client, app):
        email, token = _register_pax(client)
        from backend.models import db, WalletTransaction, User
        with app.app_context():
            user = User.query.filter_by(email=email).first()
            for i in range(5):
                db.session.add(WalletTransaction(
                    user_id=user.id, amount=Decimal('10'), type='topup',
                    status='completed',
                ))
            db.session.commit()
        rv = _api(client, 'GET', '/api/v1/wallet/transactions?limit=2&page=1', token=token)
        body = rv.get_json()
        assert len(body['data']['items']) == 2
        assert body['data']['pagination']['total'] == 5
        assert body['data']['pagination']['pages'] == 3

    def test_another_user_isolation(self, client, app):
        email1, token1 = _register_pax(client)
        email2, token2 = _register_pax(client)
        from backend.models import db, WalletTransaction, User
        with app.app_context():
            user = User.query.filter_by(email=email1).first()
            db.session.add(WalletTransaction(
                user_id=user.id, amount=Decimal('100'), type='topup', status='completed',
            ))
            db.session.commit()
        rv = _api(client, 'GET', '/api/v1/wallet/transactions', token=token2)
        assert rv.get_json()['data']['items'] == []


# ─── POST /wallet/topups ───────────────────────────────────────────────


class TestCreateTopup:
    def test_cvu_topup(self, client):
        _, token = _register_pax(client)
        rv = _topup_cvu(client, token, 500)
        assert rv.status_code == 201
        body = rv.get_json()['data']['topup']
        assert body['method'] == 'cvu'
        assert body['status'] == 'pending'
        assert body['init_point'] is None
        assert float(body['amount']) == 500.0

    def test_bank_topup(self, client):
        _, token = _register_pax(client)
        rv = _api(client, 'POST', '/api/v1/wallet/topups', token=token,
                  data={'amount': 200, 'method': 'bank'})
        assert rv.status_code == 201
        body = rv.get_json()['data']['topup']
        assert body['method'] == 'bank'
        assert body['init_point'] is None

    @patch('backend.api.wallet.create_topup_preference',
           side_effect=_mock_mp_preference('https://checkout.mp/init/123', 'pref-abc'))
    def test_mercadopago_topup(self, mock_pref, client):
        _, token = _register_pax(client)
        rv = _api(client, 'POST', '/api/v1/wallet/topups', token=token,
                  data={'amount': 1000, 'method': 'mercadopago'})
        assert rv.status_code == 201
        body = rv.get_json()['data']['topup']
        assert body['init_point'] == 'https://checkout.mp/init/123'
        assert body['method'] == 'mp_checkout'
        assert body['status'] == 'pending'
        mock_pref.assert_called_once()

    @patch('backend.api.wallet.create_topup_preference',
           side_effect=_mock_mp_preference('van://wallet/topup/success', 'pref-mob'))
    def test_mercadopago_mobile_deep_link(self, mock_pref, client):
        _, token = _register_pax(client)
        rv = _api(client, 'POST', '/api/v1/wallet/topups', token=token,
                  data={'amount': 500, 'method': 'mercadopago'},
                  headers={'X-Client-Type': 'mobile'})
        assert rv.status_code == 201
        body = rv.get_json()['data']['topup']
        assert body['init_point'] == 'van://wallet/topup/success'
        call_args = mock_pref.call_args
        assert call_args[0][0]  # user_id present
        assert call_args[0][1] == 500  # amount
        assert call_args[1]['client'] == 'mobile'

    def test_amount_below_min(self, client):
        _, token = _register_pax(client)
        rv = _topup_cvu(client, token, 50)
        assert rv.status_code == 400
        assert rv.get_json()['error']['code'] == 'TOPUP_MIN'

    def test_amount_above_max(self, client):
        _, token = _register_pax(client)
        rv = _topup_cvu(client, token, 600_000)
        assert rv.status_code == 400
        assert rv.get_json()['error']['code'] == 'TOPUP_MAX'

    def test_invalid_method(self, client):
        _, token = _register_pax(client)
        rv = _api(client, 'POST', '/api/v1/wallet/topups', token=token,
                  data={'amount': 500, 'method': 'crypto'})
        assert rv.status_code == 400
        assert rv.get_json()['error']['code'] == 'VALIDATION_ERROR'

    def test_missing_amount(self, client):
        _, token = _register_pax(client)
        rv = _api(client, 'POST', '/api/v1/wallet/topups', token=token,
                  data={'method': 'cvu'})
        assert rv.status_code == 400

    def test_no_token(self, client):
        rv = _api(client, 'POST', '/api/v1/wallet/topups',
                  data={'amount': 500, 'method': 'cvu'})
        assert rv.status_code == 401


# ─── GET /wallet/topups ────────────────────────────────────────────────


class TestListTopups:
    def test_empty(self, client):
        _, token = _register_pax(client)
        rv = _api(client, 'GET', '/api/v1/wallet/topups', token=token)
        assert rv.status_code == 200
        assert rv.get_json()['data']['items'] == []

    def test_own_topups(self, client):
        _, token = _register_pax(client)
        _topup_cvu(client, token, 500)
        _topup_cvu(client, token, 1000)
        rv = _api(client, 'GET', '/api/v1/wallet/topups', token=token)
        assert len(rv.get_json()['data']['items']) == 2

    def test_filter_status(self, client):
        _, token = _register_pax(client)
        _topup_cvu(client, token, 500)
        rv = _api(client, 'GET', '/api/v1/wallet/topups?status=pending', token=token)
        assert len(rv.get_json()['data']['items']) == 1
        rv = _api(client, 'GET', '/api/v1/wallet/topups?status=confirmed', token=token)
        assert len(rv.get_json()['data']['items']) == 0

    def test_isolation(self, client):
        _, token1 = _register_pax(client)
        _, token2 = _register_pax(client)
        _topup_cvu(client, token1, 500)
        rv = _api(client, 'GET', '/api/v1/wallet/topups', token=token2)
        assert rv.get_json()['data']['items'] == []


# ─── GET /wallet/topups/{id} ──────────────────────────────────────────


class TestGetTopup:
    def test_own_topup(self, client):
        _, token = _register_pax(client)
        rv = _topup_cvu(client, token, 500)
        topup_id = rv.get_json()['data']['topup']['id']
        rv2 = _api(client, 'GET', f'/api/v1/wallet/topups/{topup_id}', token=token)
        assert rv2.status_code == 200
        assert rv2.get_json()['data']['topup']['id'] == topup_id

    def test_not_found(self, client):
        _, token = _register_pax(client)
        rv = _api(client, 'GET', '/api/v1/wallet/topups/99999', token=token)
        assert rv.status_code == 404

    def test_another_users_topup(self, client):
        _, token1 = _register_pax(client)
        _, token2 = _register_pax(client)
        rv = _topup_cvu(client, token1, 500)
        topup_id = rv.get_json()['data']['topup']['id']
        rv2 = _api(client, 'GET', f'/api/v1/wallet/topups/{topup_id}', token=token2)
        assert rv2.status_code == 404
