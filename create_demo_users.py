#!/usr/bin/env python
"""Script para crear usuarios de demostración en la base de datos"""
import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from backend.models import db, User, Driver
from backend.app import app
from werkzeug.security import generate_password_hash

def create_demo_users():
    with app.app_context():
        passenger_exists = User.query.filter_by(email="pasajero@demo.com").first()
        driver_exists = Driver.query.filter_by(email="conductor@demo.com").first()

        if not passenger_exists:
            passenger = User(
                name="Juan Pérez",
                email="pasajero@demo.com",
                password=generate_password_hash("1234"),
                phone="3001234567",
                email_verified=True,
                rating_avg=4.8,
                rating_count=12
            )
            db.session.add(passenger)
            print("✅ Pasajero de demostración creado: pasajero@demo.com / 1234")
        else:
            print("ℹ️ El pasajero de demostración ya existe")

        if not driver_exists:
            driver = Driver(
                name="Carlos López",
                email="conductor@demo.com",
                password=generate_password_hash("1234"),
                phone="3009876543",
                placa="ABC123",
                moto_marca="Honda",
                moto_modelo="CB 150",
                moto_color="Roja",
                moto_cilindrada="150cc",
                tiene_patente=True,
                tiene_casco=True,
                seguro_moto=True,
                tipo_seguro="Responsabilidad Civil",
                carnet_conducir="ABC123456",
                ultimo_servicio="2024-01-15",
                email_verified=True,
                is_online=False,
                is_ocupado=False,
                rating_avg=4.9,
                rating_count=25
            )
            db.session.add(driver)
            print("✅ Conductor de demostración creado: conductor@demo.com / 1234")
        else:
            print("ℹ️ El conductor de demostración ya existe")

        try:
            db.session.commit()
            print("\n✅ Usuarios de demostración configurados correctamente")
            print("\n📱 PASAJERO DEMO:")
            print("   Email: pasajero@demo.com")
            print("   Contraseña: 1234")
            print("\n🏍️  CONDUCTOR DEMO:")
            print("   Email: conductor@demo.com")
            print("   Contraseña: 1234")
        except Exception as e:
            db.session.rollback()
            print(f"❌ Error al crear usuarios: {e}")

if __name__ == "__main__":
    create_demo_users()
