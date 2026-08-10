"""
Blueprint API versionada /api/v1 — consumida por la app Flutter.
Convención de respuestas:
  Éxito:  {"success": true,  "data": {...}}
  Error:  {"success": false, "error": {"code": "CODE", "message": "..."}}
La API usa JWT Bearer (Authorization: Bearer <token>). No usa cookies ni CSRF.
"""
import os
from flask import Blueprint, jsonify, request, current_app, send_from_directory

api_bp = Blueprint('api', __name__, url_prefix='/api/v1')


from backend.api.errors import ApiError, ERROR_CATALOG, api_error, raise_api_error  # noqa: E402


def ok(data=None):
    return jsonify({'success': True, 'data': data})


def fail(code, message, status=400):
    return jsonify({'success': False, 'error': {'code': code, 'message': message}}), status


@api_bp.errorhandler(ApiError)
def handle_api_error(e):
    return fail(e.code, e.message, e.status)


@api_bp.errorhandler(404)
def api_not_found(e):
    return fail('NOT_FOUND', 'Recurso no encontrado', 404)


@api_bp.errorhandler(405)
def api_method_not_allowed(e):
    return fail('METHOD_NOT_ALLOWED', 'Método no permitido', 405)


@api_bp.errorhandler(500)
def api_server_error(e):
    current_app.logger.error(f'API 500: {e}')
    return fail('INTERNAL_ERROR', 'Error interno del servidor', 500)


@api_bp.route('/openapi.yaml')
def api_openapi():
    folder = os.path.dirname(os.path.abspath(__file__))
    return send_from_directory(folder, 'openapi.yaml', mimetype='text/yaml')


@api_bp.route('/docs')
def api_docs():
    return (
        '<!DOCTYPE html><html><head><title>VAN API v1</title>'
        '<link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css">'
        '</head><body>'
        '<div id="swagger-ui"></div>'
        '<script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>'
        '<script>SwaggerUIBundle({url: "/api/v1/openapi.yaml", dom_id: "#swagger-ui"});</script>'
        '</body></html>'
    )


from backend.api import auth  # noqa: E402  (registra rutas del módulo)
