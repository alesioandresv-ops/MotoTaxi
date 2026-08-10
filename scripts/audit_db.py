#!/usr/bin/env python
"""
Gate de datos pre-migración: determina si la base de datos actual tiene
datos reales (creados por humanos) o solo datos de demo/test.

Uso: python scripts/audit_db.py
Funciona contra MySQL (legacy) y PostgreSQL.

Criterio: si hay filas con email fuera de los patrones demo/test,
se considera "datos reales" y NO se debe descartar la DB sin aprobación.
"""
import os
import sys

from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', 'backend', '.env'))

URL = os.environ.get('DATABASE_URL', '')

TABLES = [
    'users', 'drivers', 'trips', 'reviews', 'companies', 'company_members',
    'wallet_transactions', 'topup_requests', 'refresh_tokens', 'email_verifications',
    'driver_payment_methods', 'passenger_payment_configs', 'favorite_addresses',
]

DEMO_PATTERNS = ('@demo.com', '@test.com', 'demo@', 'test@')


def _is_demo(email):
    return email is None or any(p in email.lower() for p in DEMO_PATTERNS)


def _audit_mysql(conn):
    cur = conn.cursor()
    total = 0
    real = 0
    print('=== CONTEOS POR TABLA ===')
    for t in TABLES:
        try:
            cur.execute(f'SELECT COUNT(*) FROM {t}')
            n = cur.fetchone()[0]
        except Exception:
            continue
        total += n
        print(f'  {t}: {n}')
    try:
        cur.execute('SELECT email, created_at FROM users UNION ALL SELECT email, created_at FROM drivers')
        rows = cur.fetchall()
        real = [r for r in rows if not _is_demo(r[0])]
        if real:
            print('\n=== EMAILS FUERA DE DEMO/TEST ===')
            for email, created in real[:20]:
                print(f'  {email} ({created})')
    except Exception as e:
        print(f'  [warn] no se pudo leer emails: {e}')
    cur.close()
    return total, len(real)


def _audit_pg(conn):
    cur = conn.cursor()
    total = 0
    real = 0
    print('=== CONTEOS POR TABLA ===')
    for t in TABLES:
        try:
            cur.execute(f'SELECT COUNT(*) FROM {t}')
            n = cur.fetchone()[0]
        except Exception:
            continue
        total += n
        print(f'  {t}: {n}')
    try:
        cur.execute(
            'SELECT email, created_at FROM users '
            'UNION ALL SELECT email, created_at FROM drivers'
        )
        rows = cur.fetchall()
        real = [r for r in rows if not _is_demo(r[0])]
        if real:
            print('\n=== EMAILS FUERA DE DEMO/TEST ===')
            for email, created in real[:20]:
                print(f'  {email} ({created})')
    except Exception as e:
        print(f'  [warn] no se pudo leer emails: {e}')
    cur.close()
    return total, len(real)


def main():
    if not URL:
        print('ERROR: DATABASE_URL no definida en backend/.env')
        sys.exit(1)
    if URL.startswith('mysql'):
        import pymysql
        host, port, user, pw, db = _parse_mysql(URL)
        conn = pymysql.connect(host=host, port=port, user=user, password=pw, database=db)
        total, real = _audit_mysql(conn)
        conn.close()
    elif URL.startswith('postgres'):
        import psycopg
        conn = psycopg.connect(URL.replace('postgresql+psycopg', 'postgresql'))
        total, real = _audit_pg(conn)
        conn.close()
    else:
        print('ERROR: solo MySQL o PostgreSQL (no SQLite)')
        sys.exit(1)

    print(f'\n=== RESULTADO ===')
    print(f'  Filas totales: {total}')
    print(f'  Emails fuera de demo/test: {real}')
    if real == 0:
        print('  VEREDICTO: datos demo/test — se puede migrar con baseline limpio.')
    else:
        print('  VEREDICTO: EXISTEN DATOS REALES — se requiere ETL con backup y aprobación.')
    return 0 if real == 0 else 2


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


if __name__ == '__main__':
    sys.exit(main())
