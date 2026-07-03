#!/usr/bin/env python
"""
Migración CLI: usa backend/migration.py (fuente única).
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

# Necesitamos que los imports desde backend/ funcionen
sys.path.insert(0, os.path.dirname(__file__))

print(f"Migrando base de datos...\n")
from backend.migration import run_migration
try:
    run_migration(url)
    print("\n✅ Migración completada. Inicia con: python backend/app.py")
except Exception as e:
    print(f"\n❌ Error: {e}")
    sys.exit(1)
