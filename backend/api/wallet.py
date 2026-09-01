"""API v1 — Wallet endpoints (Etapa 4 §4.3, §5.3).

Endpoints:
    GET  /wallet                    → saldo + currency
    GET  /wallet/transactions       → movimientos paginados
    POST /wallet/topups             → crear recarga (MP preference o manual)
    GET  /wallet/topups             → listar propias
    GET  /wallet/topups/{id}        → detalle propia
"""

from backend.services.mercadopago import (
    MercadoPagoAPIError,
    MercadoPagoConfigError,
    create_topup_preference,
)
from backend.api.pagination import paginate
from backend.models import db, User, TopUpRequest, WalletTransaction
from backend.api.errors import raise_api_error
from backend.api import api_bp
from backend.api.jwt import jwt_required, current_user as get_jwt_user
from flask import current_app, request, jsonify

_TOPUP_METHODS = {'mercadopago', 'cvu', 'bank'}
_TOPUP_MIN = 100
_TOPUP_MAX = 500_000
_CURRENCY = 'ARS'


# ─── Serializers ────────────────────────────────────────────────────────

def _serialize_balance(user: User) -> dict:
    return {
        'balance': str(user.balance or 0),
        'currency': _CURRENCY,
    }


def _serialize_topup(t: TopUpRequest) -> dict:
    return {
        'id': t.id,
        'amount': str(t.amount),
        'method': t.method,
        'status': t.status,
        'admin_note': t.admin_note,
        'created_at': t.created_at.isoformat() if t.created_at else None,
    }


def _serialize_wallet_txn(t: WalletTransaction) -> dict:
    return {
        'id': t.id,
        'amount': str(t.amount),
        'type': t.type,
        'status': t.status,
        'trip_id': t.trip_id,
        'reference': t.reference,
        'description': t.description or '',
        'created_at': t.created_at.isoformat() if t.created_at else None,
    }


# ─── GET /wallet ────────────────────────────────────────────────────────

@api_bp.get('/wallet')
@jwt_required
def get_balance():
    user = get_jwt_user()
    return jsonify({'success': True, 'data': _serialize_balance(user)})


# ─── GET /wallet/transactions ──────────────────────────────────────────

@api_bp.get('/wallet/transactions')
@jwt_required
def list_transactions():
    user = get_jwt_user()
    tx_type = request.args.get('type')
    q = WalletTransaction.query.filter_by(user_id=user.id)
    if tx_type:
        q = q.filter_by(type=tx_type)
    q = q.order_by(WalletTransaction.created_at.desc())
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 20, type=int)
    result = paginate(q, page=page, limit=limit)
    return jsonify({
        'success': True,
        'data': {
            'items': [_serialize_wallet_txn(t) for t in result['items']],
            'pagination': result['pagination'],
        },
    })


# ─── POST /wallet/topups ───────────────────────────────────────────────

@api_bp.post('/wallet/topups')
@jwt_required
def create_topup():
    user = get_jwt_user()
    data = request.get_json(silent=True) or {}

    amount = data.get('amount')
    method = (data.get('method') or '').strip().lower()

    # ── Validations ──────────────────────────────────────────────────
    try:
        amount_f = float(amount)
    except (TypeError, ValueError):
        raise_api_error('VALIDATION_ERROR', 'Monto requerido y numérico')

    if amount_f < _TOPUP_MIN:
        raise_api_error('TOPUP_MIN')
    if amount_f > _TOPUP_MAX:
        raise_api_error('TOPUP_MAX')
    if method not in _TOPUP_METHODS:
        raise_api_error('VALIDATION_ERROR', f'Métodos válidos: {", ".join(sorted(_TOPUP_METHODS))}')

    # ── Mercado Pago ─────────────────────────────────────────────────
    if method == 'mercadopago':
        client = 'mobile' if (request.headers.get('X-Client-Type') or '').strip().lower() == 'mobile' else 'web'
        try:
            init_point, _pref_topup_id = create_topup_preference(user.id, amount_f, client=client)
        except MercadoPagoConfigError as e:
            raise_api_error('MERCADOPAGO_CONFIG', str(e), status=500)
        except MercadoPagoAPIError as e:
            current_app.logger.error(f'Topup MP error: {e}')
            raise_api_error('MERCADOPAGO_API', str(e), status=502)
        except Exception as e:
            current_app.logger.error(f'Topup MP error inesperado: {e}')
            raise_api_error('MERCADOPAGO_API', 'Error creando preferencia', status=500)

        # create_topup_preference already persists TopUpRequest with
        # method='mp_checkout' and preference_id — returned id is the DB pk.
        topup = TopUpRequest.query.get(_pref_topup_id)
        return jsonify({
            'success': True,
            'data': {
                'topup': {**_serialize_topup(topup), 'init_point': init_point},
            },
        }), 201

    # ── CVU / Bank transfer (manual approval by admin) ───────────────
    topup = TopUpRequest(
        user_id=user.id,
        amount=amount_f,
        method=method,
        status='pending',
    )
    db.session.add(topup)
    db.session.commit()
    return jsonify({
        'success': True,
        'data': {'topup': {**_serialize_topup(topup), 'init_point': None}},
    }), 201


# ─── GET /wallet/topups ────────────────────────────────────────────────

@api_bp.get('/wallet/topups')
@jwt_required
def list_topups():
    user = get_jwt_user()
    status = request.args.get('status')
    q = TopUpRequest.query.filter_by(user_id=user.id)
    if status:
        q = q.filter_by(status=status)
    q = q.order_by(TopUpRequest.created_at.desc())
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 20, type=int)
    result = paginate(q, page=page, limit=limit)
    return jsonify({
        'success': True,
        'data': {
            'items': [_serialize_topup(t) for t in result['items']],
            'pagination': result['pagination'],
        },
    })


# ─── GET /wallet/topups/{id} ──────────────────────────────────────────

@api_bp.get('/wallet/topups/<int:topup_id>')
@jwt_required
def get_topup(topup_id: int):
    user = get_jwt_user()
    topup = TopUpRequest.query.filter_by(id=topup_id, user_id=user.id).first()
    if not topup:
        raise_api_error('NOT_FOUND', status=404)
    return jsonify({'success': True, 'data': {'topup': _serialize_topup(topup)}})


# ───────────────── Passenger extras: favorites + voucher ─────────────────


@api_bp.route('/favorites', methods=['GET'])
@jwt_required
def api_favorites():
    """GET /favorites — rutas frecuentes del pasajero (≥3 usos)."""
    from backend.models import FavoriteAddress

    user = get_jwt_user()
    favs = FavoriteAddress.query.filter_by(
        user_id=user.id
    ).filter(
        FavoriteAddress.count >= 3
    ).order_by(FavoriteAddress.count.desc()).limit(3).all()

    return jsonify({
        'success': True,
        'data': {'favorites': [{
            'id': f.id,
            'name': f.name,
            'pickup_address': f.pickup_address,
            'dropoff_address': f.dropoff_address,
            'count': f.count,
        } for f in favs]},
    })


@api_bp.route('/wallet/topups/<int:topup_id>/voucher', methods=['POST'])
@jwt_required
def api_upload_voucher(topup_id):
    """POST /wallet/topups/{id}/voucher — subir comprobante de transferencia (base64)."""
    import base64
    import os
    import uuid as _uuid

    from backend.api import ok as api_ok
    from backend.api.errors import ApiError

    user = get_jwt_user()
    topup = TopUpRequest.query.filter_by(id=topup_id, user_id=user.id).first()
    if not topup:
        raise ApiError('NOT_FOUND', status=404)

    data = request.get_json(silent=True) or {}
    image_data = data.get('image')
    if not image_data:
        raise ApiError('VALIDATION_ERROR', 'image requerido (base64)')

    try:
        header = ''
        encoded = image_data
        if ',' in image_data:
            header, encoded = image_data.split(',', 1)
        raw = base64.b64decode(encoded)
        if len(raw) > 5 * 1024 * 1024:
            raise ApiError('VALIDATION_ERROR', 'Archivo demasiado grande (máx 5MB)')
        ext = 'png' if 'png' in header else 'jpg'
        folder = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              'static', 'uploads', 'vouchers')
        os.makedirs(folder, exist_ok=True)
        filename = f'voucher_{_uuid.uuid4().hex}.{ext}'
        filepath = os.path.join(folder, filename)
        with open(filepath, 'wb') as f:
            f.write(raw)
        topup.voucher_url = f'/static/uploads/vouchers/{filename}'
        db.session.commit()
    except ApiError:
        raise
    except Exception:
        db.session.rollback()
        raise ApiError('VALIDATION_ERROR', 'Imagen base64 inválida')

    return api_ok({'voucher_url': topup.voucher_url})
