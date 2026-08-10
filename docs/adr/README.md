# Architecture Decision Records (ADR)

Documento vivo de decisiones de arquitectura de VAN. Cada decisión importante
se registra con contexto, alternativa consideradas y consecuencias.

Convención de nombres: `ADR-NNN-slug.md`. Estados: Propuesto / Aceptado /
Superado.

## Índice

| ADR | Decisión | Estado |
|-----|----------|--------|
| [ADR-001](ADR-001-api-jwt.md) | API REST versionada `/api/v1` + JWT (Access + Refresh) como mecanismo de auth para la app móvil | Aceptado |
| [ADR-002](ADR-002-refresh-tokens-bd.md) | Refresh tokens opacos almacenados en base de datos (no Redis) | Aceptado |
| [ADR-003](ADR-003-identidad-unificada.md) | Identidad unificada: `users.role` + `driver_profiles` (1:1) + `vehicles` (1:N), modo dual y comisión Decimal | Aceptado |

## Plantilla

```markdown
# ADR-NNN: Título

- Estado: Propuesto | Aceptado | Superado
- Fecha: YYYY-MM-DD

## Contexto
## Decisión
## Alternativas consideradas
## Consecuencias
```
