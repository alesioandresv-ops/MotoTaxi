import os
import json
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from cryptography.fernet import Fernet

limiter = Limiter(key_func=get_remote_address)

def get_fernet():
    key = os.getenv('ENCRYPTION_KEY')
    if not key:
        return None
    return Fernet(key.encode())

def encrypt_details(details_dict):
    f = get_fernet()
    if not f:
        raise RuntimeError("ENCRYPTION_KEY debe estar definida en .env para guardar datos de pago")
    encrypted = f.encrypt(json.dumps(details_dict, ensure_ascii=False).encode())
    return 'enc:' + encrypted.decode()

def decrypt_details(encrypted_str):
    if not encrypted_str:
        return {}
    if encrypted_str.startswith('enc:'):
        f = get_fernet()
        if f:
            try:
                return json.loads(f.decrypt(encrypted_str[4:].encode()).decode())
            except Exception:
                return {}
        return {}
    try:
        return json.loads(encrypted_str)
    except Exception:
        return {}
