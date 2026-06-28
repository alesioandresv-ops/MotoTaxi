#!/usr/bin/env python
"""
Script de setup para MotoTaxi
Verifica conexión MySQL y crea tablas
"""
import os
import sys
from dotenv import load_dotenv

# Cargar variables desde backend/.env para que el script funcione desde la raíz
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), 'backend', '.env'))


def setup():
    print("=== Setup MotoTaxi ===\n")
    
    db_url = os.environ.get('DATABASE_URL')
    if not db_url or db_url == 'mysql+pymysql://root:contraseña@127.0.0.1:3306/mototaxi':
        print("ERROR: Tu archivo backend/.env aún contiene credenciales de ejemplo.")
        print("Edita backend/.env y reemplaza DATABASE_URL con tus datos de MySQL.")
        print("Ejemplo:")
        print("  DATABASE_URL=mysql+pymysql://root:tu_contraseña@127.0.0.1:3306/mototaxi")
        sys.exit(1)
    if not db_url:
        print("ERROR: DATABASE_URL no definida en .env")
        sys.exit(1)
    
    print(f"📌 Usando DATABASE_URL: {db_url}\n")
    
    try:
        from backend.app import app
        
        with app.app_context():
            from backend.models import db
            print("✅ Conectado a MySQL")
            print("📚 Creando tablas...")
            db.create_all()
            print("✅ Tablas creadas correctamente")
            print("\n✅ Setup completado. Inicia la app con: python backend/app.py")
    
    except Exception as e:
        print(f"❌ Error: {e}")
        print("\nVerifica:")
        print("1. MySQL está corriendo (XAMPP/Workbench)")
        print("2. DATABASE_URL en .env es correcta")
        print("3. Base de datos 'mototaxi' existe")
        sys.exit(1)

if __name__ == '__main__':
    setup()
