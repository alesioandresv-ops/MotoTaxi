# ADR-002: Refresh tokens opacos en base de datos (no Redis)

- Estado: Aceptado
- Fecha: 2026-08-05

## Contexto

La API v1 necesita refresh tokens revocables con rotación y detección de
reuso. La arquitectura objetivo contempla Redis, pero está en la Fase 5 del
roadmap (infraestructura). Se necesita una solución que funcione hoy sobre
MySQL/SQLite sin bloquear la Fase 1 ni el MVP Flutter.

## Decisión

Los refresh tokens son **opacos** (`secrets.token_urlsafe(48)`), se guardan
**hasheados (SHA-256)** en la tabla `refresh_tokens` con `expires_at`,
`revoked_at` y `replaced_by_id` (para auditoría de la cadena de rotación).

Comportamiento:
- **Rotación**: cada uso de un refresh emite uno nuevo y revoca el anterior.
- **Detección de reuso**: si aparece un token ya revocado, se revocan TODOS
  los tokens del usuario (respuesta estándar OAuth2 ante sesión comprometida).
- **Logout** revoca el refresh presentado.
- Nunca se almacena el token en claro (hash SHA-256; mitigación ante fuga de
  la tabla).

## Alternativas consideradas

- **Redis con TTL**: preferible a escala, pero agrega infraestructura hoy
  (Fase 5). La BD ya existe y los volúmenes actuales son triviales.
- **Refresh JWT firmado sin estado**: rechazado — sin revocación real;
  un token robado vale hasta 30 días.

## Consecuencias

Positivas:
- Cero dependencias nuevas de infraestructura; funciona en MySQL y SQLite.
- Revocación total por usuario (seguridad ante compromiso).
- El cambio futuro a Redis es localizado: solo cambia el storage de
  `issue_tokens` / `rotate_refresh_token`, la API no se entera.

Negativas:
- Una escritura en BD por login/refresh (despreciable a la escala actual;
  Redis lo resuelve en Fase 5 si hace falta).
- `user_id` sin FK dual (referencia `users.id` o `drivers.id` según
  `user_type`) — documentado en el modelo.

Supera a: ninguna — decisión nueva.
