#!/usr/bin/env python
"""
Migración CLI (fuente única: backend/migration.run_all).
PostgreSQL → Alembic. MySQL (legacy) → migración pymysql.
Uso: python migrate.py
"""
import os
import sys

from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), 'backend', '.env'))

url = os.environ.get('DATABASE_URL')
if not url:
    print("ERROR: DATABASE_URL no definida en backend/.env")
    sys.exit(1)

sys.path.insert(0, os.path.dirname(__file__))

print("Migrando base de datos...\n")
from backend.migration import run_all
try:
    run_all()
    print("\nMigración completada. Inicia con: python backend/app.py")
except Exception as e:
    print(f"\nError: {e}")
    sys.exit(1)
