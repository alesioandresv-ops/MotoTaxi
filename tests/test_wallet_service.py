"""Unit tests de backend.services.wallet.wallet_transfer.

Reglas bajo prueba:
- Débito/crédito correctos y montos asimétricos (comisión de plataforma).
- Dos WalletTransaction espejadas por transfer.
- Errores con código estable: INVALID_AMOUNT / USER_NOT_FOUND /
  INSUFFICIENT_BALANCE — y NADA escrito cuando rechaza.
- No commitea: un rollback del caller deshace todo el bloque.
"""
import pytest

from backend.models import User, WalletTransaction, db
from backend.services.wallet import WalletTransferError, wallet_transfer


def _mkuser(app, email, balance=0.0):
    from werkzeug.security import generate_password_hash

    with app.app_context():
        u = User(
            name=email.split('@')[0], email=email,
            password=generate_password_hash('x'), phone='3000000000',
            email_verified=True, balance=balance,
        )
        db.session.add(u)
        db.session.commit()
        return u.id


class TestWalletTransferOk:
    def test_transferencia_simetrica(self, app):
        payer = _mkuser(app, 'p@t.com', balance=100)
        payee = _mkuser(app, 'd@t.com')
        with app.app_context():
            wallet_transfer(payer, payee, 40)
            db.session.commit()
            assert float(db.session.get(User, payer).balance) == 60.0
            assert float(db.session.get(User, payee).balance) == 40.0

    def test_montos_asimetricos_comision_plataforma(self, app):
        """Pasajero paga el total, conductor recibe earnings; la diferencia
        (comisión VAN) queda retenida."""
        payer = _mkuser(app, 'p2@t.com', balance=100)
        payee = _mkuser(app, 'd2@t.com')
        with app.app_context():
            wallet_transfer(payer, payee, 50, credit_amount=47.5)
            db.session.commit()
            assert float(db.session.get(User, payer).balance) == 50.0
            assert float(db.session.get(User, payee).balance) == 47.5

    def test_genera_dos_transacciones_espejadas(self, app):
        payer = _mkuser(app, 'p3@t.com', balance=80)
        payee = _mkuser(app, 'd3@t.com')
        with app.app_context():
            wallet_transfer(
                payer, payee, 30,
                tx_type='trip_payment', trip_id=7,
                description='Viaje #7', reference='ref-1',
            )
            db.session.commit()
            txs = WalletTransaction.query.filter_by(trip_id=7).all()
            assert len(txs) == 2
            by_user = {tx.user_id: tx for tx in txs}
            assert float(by_user[payer].amount) == -30.0
            assert float(by_user[payee].amount) == 30.0
            assert all(tx.counterparty_id in (payer, payee) for tx in txs)

    def test_rollback_del_caller_deshace_todo(self, app):
        """wallet_transfer NO commitea: el caller controla la atomicidad."""
        payer = _mkuser(app, 'p4@t.com', balance=100)
        payee = _mkuser(app, 'd4@t.com')
        with app.app_context():
            wallet_transfer(payer, payee, 40)
            db.session.rollback()
            assert float(db.session.get(User, payer).balance) == 100.0
            assert float(db.session.get(User, payee).balance) == 0.0
            assert WalletTransaction.query.count() == 0


class TestWalletTransferErrores:
    def test_monto_cero_o_negativo(self, app):
        payer = _mkuser(app, 'e1p@t.com', balance=100)
        payee = _mkuser(app, 'e1d@t.com')
        with app.app_context():
            for bad in (0, -5, 'abc'):
                with pytest.raises(WalletTransferError) as exc:
                    wallet_transfer(payer, payee, bad)
                assert exc.value.code == 'INVALID_AMOUNT'
            assert WalletTransaction.query.count() == 0

    def test_payer_y_receiver_iguales(self, app):
        uid = _mkuser(app, 'e2@t.com', balance=100)
        with app.app_context():
            with pytest.raises(WalletTransferError) as exc:
                wallet_transfer(uid, uid, 10)
            assert exc.value.code == 'INVALID_AMOUNT'

    def test_usuario_inexistente(self, app):
        uid = _mkuser(app, 'e3@t.com', balance=100)
        with app.app_context():
            with pytest.raises(WalletTransferError) as exc:
                wallet_transfer(uid, 999999, 10)
            assert exc.value.code == 'USER_NOT_FOUND'

    def test_saldo_insuficiente_no_escribe_nada(self, app):
        payer = _mkuser(app, 'e4p@t.com', balance=10)
        payee = _mkuser(app, 'e4d@t.com')
        with app.app_context():
            with pytest.raises(WalletTransferError) as exc:
                wallet_transfer(payer, payee, 50)
            assert exc.value.code == 'INSUFFICIENT_BALANCE'
            assert float(db.session.get(User, payer).balance) == 10.0
            assert float(db.session.get(User, payee).balance) == 0.0
            assert WalletTransaction.query.count() == 0

    def test_credito_negativo_rechazado(self, app):
        payer = _mkuser(app, 'e5p@t.com', balance=100)
        payee = _mkuser(app, 'e5d@t.com')
        with app.app_context():
            with pytest.raises(WalletTransferError) as exc:
                wallet_transfer(payer, payee, 50, credit_amount=-1)
            assert exc.value.code == 'INVALID_AMOUNT'
