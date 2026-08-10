"""
Validaciones compartidas entre la web (sesiones) y la API (/api/v1).
Una sola fuente de verdad para reglas de negocio de entrada de usuario.
"""
import re
import bleach

EMAIL_RE = re.compile(r'^[^@]+@[^@]+\.[^@]+$')
PASSWORD_MIN_LEN = 8
MAX_INPUT_LEN = 500


def sanitize_input(value):
    if value is None:
        return None
    value = str(value).strip()
    value = bleach.clean(value, tags=[], strip=True)
    return value[:MAX_INPUT_LEN]


def normalize_email(value):
    return (value or '').strip().lower()


def validate_name(name):
    if not name or len(name) < 2:
        return 'El nombre debe tener al menos 2 caracteres'
    return None


def validate_email(email):
    if not re.match(EMAIL_RE, email):
        return 'Correo electrónico inválido'
    return None


def validate_password(password):
    if not password or len(password) < PASSWORD_MIN_LEN:
        return 'La contraseña debe tener al menos 8 caracteres'
    if not re.search(r'[A-Z]', password) or not re.search(r'[0-9]', password):
        return 'La contraseña debe contener al menos una mayúscula y un número'
    return None


def first_error(*errors):
    for err in errors:
        if err:
            return err
    return None
