"""Integración MercadoPago — punto único para SDK, credenciales y webhooks.

Auditoría MP (2026-08-24):
- Credenciales por entorno vía MP_ENV: 'test' usa MERCADOPAGO_TEST_ACCESS_TOKEN,
  'production' (default) usa MERCADOPAGO_ACCESS_TOKEN.
- Firma de webhooks con el manifest oficial ts/v1 vía WebhookSignatureValidator
  del SDK oficial (>=3.4). Política fail-closed: si MP_WEBHOOK_SECRET está
  configurado, una notificación sin firma válida se rechaza (403 en las rutas).
- Las preferencias de recarga persisten TopUpRequest 'pending' con
  preference_id antes de redirigir (reconciliación y trazabilidad).

El SDK se importa tardío dentro de cada función: los tests reemplazan
sys.modules['mercadopago'] con fakes y así no queda binding de módulo.
"""
import os

from datetime import datetime, timezone


class MercadoPagoConfigError(Exception):
    """Falta la credencial del entorno activo (MP_ENV)."""


class MercadoPagoAPIError(Exception):
    """La API de MercadoPago rechazó o falló al crear una preferencia."""


def mp_environment():
    """'test' | 'production' (default production)."""
    return (os.getenv('MP_ENV') or 'production').strip().lower()


def mp_access_token():
    if mp_environment() == 'test':
        token = os.getenv('MERCADOPAGO_TEST_ACCESS_TOKEN')
        if not token:
            raise MercadoPagoConfigError(
                'MP_ENV=test pero falta MERCADOPAGO_TEST_ACCESS_TOKEN en backend/.env')
        return token
    token = os.getenv('MERCADOPAGO_ACCESS_TOKEN')
    if not token:
        raise MercadoPagoConfigError(
            'MP_ENV=production pero falta MERCADOPAGO_ACCESS_TOKEN en backend/.env')
    return token


def get_sdk():
    import mercadopago
    return mercadopago.SDK(mp_access_token())


def mp_public_key():
    """Public key del entorno activo (se inyecta en templates con JS de MP)."""
    if mp_environment() == 'test':
        return os.getenv('MERCADOPAGO_TEST_PUBLIC_KEY') or os.getenv('MERCADOPAGO_PUBLIC_KEY', '')
    return os.getenv('MERCADOPAGO_PUBLIC_KEY', '')


def webhook_secret():
    """Secret de firma configurado en el panel (Tus integraciones → Webhooks).

    Vacío = modo dev sin validación de firma (la verificación server-side del
    pago contra la API sigue siendo obligatoria antes de acreditar).
    """
    return (os.getenv('MP_WEBHOOK_SECRET') or '').strip()


def validate_webhook_signature(x_signature, x_request_id, data_id):
    """True si la notificación webhook es legítima.

    - Sin MP_WEBHOOK_SECRET → True (dev; solo se confía tras verificar el
      pago contra la API de MP).
    - Con secret → fail-closed: exige header x-signature con manifest
      id/request-id/ts válido. QR notifications NO vienen firmadas; no pasar
      esas notificaciones por acá.
    """
    secret = webhook_secret()
    if not secret:
        return True
    from mercadopago.webhook import InvalidWebhookSignatureError, WebhookSignatureValidator
    try:
        WebhookSignatureValidator.validate(x_signature, x_request_id, data_id, secret)
        return True
    except InvalidWebhookSignatureError as e:
        # Loguear e.reason + x-request-id para correlacionar contra el panel MP.
        import logging
        logging.getLogger(__name__).warning(
            "Webhook MP rechazado (%s) request-id=%s", e.reason.value, x_request_id)
        return False


def base_url():
    return (os.getenv('BASE_URL') or 'http://127.0.0.1:5000').rstrip('/')


def app_scheme():
    """Deep link scheme normalizado de la app Flutter. Siempre devuelve
    '<scheme>://' (ej. 'van://'); tolera 'van', 'van:', o 'van://' en .env."""
    base = (os.getenv('APP_SCHEME') or 'van://').strip().rstrip('/:')
    return f'{base}://' if base else 'van://'


def is_public_base_url(url=None):
    u = url or base_url()
    return '127.0.0.1' not in u and 'localhost' not in u


def back_urls_for(client, web_base_path):
    """back_urls según cliente. Mismas rutas para web y app: un solo contrato.

    - client='web' → {BASE_URL}/wallet/topup/{success|failure|pending}
    - client='mobile' → van://wallet/topup/... (deep links con APP_SCHEME)
    """
    clean = web_base_path.strip('/')
    base = app_scheme() + clean if client == 'mobile' else f'{base_url()}/{clean}'
    return {
        state: f'{base}/{state}'
        for state in ('success', 'failure', 'pending')
    }


def create_topup_preference(user_id, amount, client='web'):
    """Preferencia Checkout Pro para recargar billetera.

    Persiste TopUpRequest(status='pending', preference_id=...) ANTES de
    devolver el init_point — si MP nunca llama al webhook, la fila queda
    como evidencia para reconciliación manual.

    auto_return SIEMPRE activo: sin él MP muestra su pantalla "¡Listo!" y
    no vuelve a VAN (bug 2026-08-24). notification_url solo con BASE_URL
    público (MP no alcanza webhooks locales).

    client: 'web' (default) o 'mobile' → back_urls con APP_SCHEME deep links.
    Devuelve (init_point, topup.id). Lanza MercadoPagoConfigError /
    MercadoPagoAPIError. Commitea su propia transacción (creación aislada,
    sin dinero en juego todavía).
    """
    from backend.models import TopUpRequest, db

    sdk = get_sdk()
    preference_data = {
        'items': [{
            'id': 'topup',
            'title': f'Recarga VAN - ${float(amount):.2f}',
            'quantity': 1,
            'unit_price': float(amount),
            'currency_id': 'ARS',
        }],
        'external_reference': str(user_id),
        'back_urls': back_urls_for(client, '/wallet/topup'),
        # CLAVE del redirect automático post-pago (~5 s) a back_urls.success.
        'auto_return': 'approved',
        'statement_descriptor': 'VAN RECARGA',
    }
    if is_public_base_url():
        preference_data['notification_url'] = base_url() + '/api/wallet/topup/webhook?source_news=webhooks'

    result = sdk.preference().create(preference_data)
    status = result.get('status')
    response = result.get('response') or {}
    if status not in (200, 201) or not response.get('init_point'):
        msg = response.get('message', f'status {status}')
        raise MercadoPagoAPIError(f'No se pudo crear la preferencia ({msg})')

    topup = TopUpRequest(
        user_id=user_id,
        amount=float(amount),
        method='mp_checkout',
        preference_id=str(response.get('id')),
        status='pending',
    )
    db.session.add(topup)
    db.session.commit()
    return response['init_point'], topup.id


def mark_topup_preference_expired(topup_id):
    """Marca pendiente→expired cuando el usuario vuelve por back_urls sin
    haber pagado (best-effort: nunca lanza ni interrumpe el flujo web)."""
    from backend.models import TopUpRequest, db
    try:
        topup = db.session.get(TopUpRequest, topup_id)
        if topup and topup.status == 'pending':
            topup.status = 'expired'
            topup.confirmed_at = datetime.now(timezone.utc)
            db.session.commit()
    except Exception:
        db.session.rollback()
