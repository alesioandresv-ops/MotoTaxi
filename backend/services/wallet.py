"""Billetera: transferencias atómicas pasajero↔conductor.

Única fuente de verdad para mover saldo (web y API — no duplicar reglas):

- Locks por fila con orden determinista por id (evita deadlocks en PG
  cuando dos transfers concurrentes tocan los mismos usuarios en orden
  inverso).
- NUNCA commitea: el caller dueño del caso de uso commitea junto con el
  resto de los cambios del mismo evento (ej: finalize_trip marca el viaje
  completed en la MISMA transacción que el débito). Un rollback del caller
  deshace todo el bloque.
- Dinero SIEMPRE Decimal; inputs numéricos hostil-proof (_parse_amount).
- Cada transfer genera DOS WalletTransaction espejadas (débito con signo
  negativo para el payer, crédito positivo para el receiver).
"""
from decimal import Decimal, InvalidOperation

from backend.models import User, WalletTransaction, db
from backend.services.fare import round_money


class WalletTransferError(Exception):
    """Rechazo de transferencia con código estable para la capa HTTP."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message

    def __repr__(self):
        return f'WalletTransferError({self.code!r})'


def _parse_amount(value):
    """Decimal o None si el valor no es un número finito (input HTTP hostil)."""
    if isinstance(value, Decimal):
        return value if value.is_finite() else None
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return d if d.is_finite() else None


def _locked_users(payer_id, receiver_id):
    """Carga ambos usuarios con FOR UPDATE en orden determinista por id."""
    first_id, second_id = sorted((payer_id, receiver_id))
    rows = {
        u.id: u
        for u in db.session.query(User)
        .filter(User.id.in_((first_id, second_id)))
        .with_for_update()
        .all()
    }
    return rows.get(payer_id), rows.get(receiver_id)


def wallet_transfer(
    payer_id,
    receiver_id,
    amount,
    *,
    credit_amount=None,
    tx_type='trip_payment',
    trip_id=None,
    description='',
    reference=None,
):
    """Debita `amount` a payer y acredita `credit_amount` a receiver.

    `credit_amount` permite transferencias asimétricas (ej: viaje con
    comisión — el pasajero paga el total, el conductor recibe sus
    earnings y la diferencia queda para la plataforma). None → simétrica.
    NO commitea: ver docstring del módulo.

    Devuelve (payer, receiver) actualizados. Lanza WalletTransferError:
    - INVALID_AMOUNT: monto ausente/no numérico/<= 0 (o crédito < 0).
    - USER_NOT_FOUND: alguna de las partes no existe.
    - INSUFFICIENT_BALANCE: el payer no tiene saldo suficiente.
    """
    amount = _parse_amount(amount)
    if amount is None or amount <= 0:
        raise WalletTransferError('INVALID_AMOUNT', 'Monto inválido')
    if payer_id == receiver_id:
        raise WalletTransferError('INVALID_AMOUNT', 'Payer y receiver no pueden ser el mismo')
    if credit_amount is None:
        credit_amount = amount
    else:
        credit_amount = _parse_amount(credit_amount)
        if credit_amount is None or credit_amount < 0:
            raise WalletTransferError('INVALID_AMOUNT', 'Crédito inválido')

    payer, receiver = _locked_users(payer_id, receiver_id)
    if payer is None or receiver is None:
        raise WalletTransferError('USER_NOT_FOUND', 'Usuario inexistente')

    current = _parse_amount(payer.balance) or Decimal('0')
    if current < amount:
        raise WalletTransferError(
            'INSUFFICIENT_BALANCE',
            f'Saldo insuficiente (${current} disponible, ${amount} requerido)',
        )

    payer.balance = round_money(current - amount)
    receiver.balance = round_money(
        (_parse_amount(receiver.balance) or Decimal('0')) + credit_amount
    )

    db.session.add(WalletTransaction(
        user_id=payer.id, counterparty_id=receiver.id,
        amount=-amount, type=tx_type, trip_id=trip_id,
        reference=reference, description=description,
    ))
    db.session.add(WalletTransaction(
        user_id=receiver.id, counterparty_id=payer.id,
        amount=credit_amount, type=tx_type, trip_id=trip_id,
        reference=reference, description=description,
    ))
    return payer, receiver
