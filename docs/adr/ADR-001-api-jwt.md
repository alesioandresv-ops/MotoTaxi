# ADR-001: API REST versionada + JWT para la app móvil

- Estado: Aceptado
- Fecha: 2026-08-05

## Contexto

VAN es una plataforma con backend Flask y frontend web (Jinja2) que usa
sesiones de cookies + CSRF. El objetivo es publicar una app Flutter en
Google Play. Las cookies no son un mecanismo viable ni seguro para una app
móvil, y los endpoints JSON actuales (`/api/*`) están acoplados a la sesión
web y sin versionado.

Roadmap aprobado: la API móvil es la Fase 1 (antes que PostgreSQL, tiempo
real y monetización) para priorizar el time-to-market del MVP.

## Decisión

1. **Blueprint nuevo `/api/v1`** (paquete `backend/api/`) — aditivo, no
   toca el flujo web. Envelope de respuestas consistente:
   `{"success": true, "data": ...}` / `{"success": false, "error": {"code", "message"}}`.
2. **Autenticación JWT Bearer** (PyJWT, HS256):
   - Access token: corto (30 min), stateless, claims `sub`, `utype`
     (`user`|`driver`), `jti`, `iat`, `exp`.
   - Refresh token: opaco, rotativo, revocable (ver ADR-002).
   - Decoradores `@jwt_required` / `@roles_required` en `backend/api/jwt.py`.
3. **Contrato documentado** con OpenAPI 3 (`backend/api/openapi.yaml`),
   servido en `/api/v1/openapi.yaml` y Swagger UI en `/api/v1/docs`.
4. **Validación compartida** (`backend/validators.py`): la web y la API usan
   las mismas reglas de nombre/email/password — una sola fuente de verdad.
5. La lógica de negocio sigue en el servidor; la app es un cliente delgado.

## Alternativas consideradas

- **Sesiones por cookie para la app**: rechazada — inseguro en móvil y no
  scale con el modelo de "lógica en el servidor".
- **Flask-JWT-Extended**: rechazada — PyJWT + decoradores propios (~60
  líneas) da control total sin dependencias opinadas.
- **API sin versionar (`/api/v2` ad-hoc)**: rechazada — una vez publicada la
  app, romper el contrato rompe instalaciones; el versionado es obligatorio
  desde el día uno.

## Consecuencias

Positivas:
- Flutter consume un contrato estable y documentado, probado por tests.
- La web convive sin cambios; migración incremental a v1 por endpoint.
- Rotación de refresh + detección de reuso = defensa ante robo de tokens.

Negativas:
- Dos mecanismos de auth conviven (sesiones web + JWT) hasta migrar la web.
- `JWT_SECRET_KEY` nueva variable de entorno (con fallback a `SECRET_KEY`
  durante la transición).

Supera a: ninguna decisión previa (la web nunca tuvo API para móvil).
