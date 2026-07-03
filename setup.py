#!/usr/bin/env python
"""
Setup inicial de MotoTaxi: verifica conexión y migra DB.
Uso: python setup.py
"""
import os
import sys
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), 'backend', '.env'))

db_url = os.environ.get('DATABASE_URL')
if not db_url or 'root:contraseña' in db_url:
    print("ERROR: Edita backend/.env y configura DATABASE_URL con tus datos de MySQL.")
    sys.exit(1)

sys.path.insert(0, os.path.dirname(__file__))

print("=== Setup MotoTaxi ===\n")

try:
    from backend.migration import run_migration
    run_migration(db_url)
    print("\n✅ Setup completado. Inicia con: python backend/app.py")
except Exception as e:
    print(f"\n❌ Error: {e}")
    print("\nVerifica:")
    print("1. MySQL está corriendo")
    print("2. DATABASE_URL en .env es correcta")
    print("3. Base de datos 'mototaxi' existe")
    sys.exit(1)
