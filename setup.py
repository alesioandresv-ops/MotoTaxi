#!/usr/bin/env python
"""
Setup inicial de VAN: verifica conexión y migra DB.
PostgreSQL (Alembic) es el objetivo; MySQL legacy sigue soportado.
Uso: python setup.py
"""
import os
import sys

from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), 'backend', '.env'))

db_url = os.environ.get('DATABASE_URL')
if not db_url:
    print("ERROR: Edita backend/.env y configura DATABASE_URL (PostgreSQL).")
    sys.exit(1)

sys.path.insert(0, os.path.dirname(__file__))

print("=== Setup VAN ===\n")
print("Verificando conexión a la base de datos...")

try:
    if db_url.startswith('postgres'):
        import psycopg
        conn = psycopg.connect(db_url.replace('postgresql+psycopg', 'postgresql'))
        conn.close()
        print("PostgreSQL OK")
    elif db_url.startswith('mysql'):
        import pymysql
        host, port, user, pw, db = _parse_mysql(db_url)
        conn = pymysql.connect(host=host, port=port, user=user, password=pw, database=db)
        conn.close()
        print("MySQL (legacy) OK")
    else:
        print("AVISO: DATABASE_URL no es PostgreSQL ni MySQL, se intenta igual.")

    from backend.migration import run_all
    run_all()
    print("\nSetup completado. Inicia con: python backend/app.py")
except Exception as e:
    print(f"\nError: {e}")
    print("\nVerifica:")
    print("1. La base de datos está corriendo")
    print("2. DATABASE_URL en backend/.env es correcta")
    print("3. PostgreSQL: la base de datos existe (docker compose up -d)")
    sys.exit(1)


def _parse_mysql(url):
    u = url.replace('mysql+pymysql://', '').replace('mysql://', '')
    user_pass, rest = u.split('@', 1)
    user, pw = user_pass.split(':', 1)
    host_part = rest.split('/', 1)[0]
    db = rest.split('/', 1)[1].split('?')[0]
    if ':' in host_part:
        host, port = host_part.split(':', 1)
        return host, int(port), user, pw, db
    return host_part, 3306, user, pw, db
