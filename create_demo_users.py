#!/usr/bin/env python
"""Script para crear usuarios de demostración en la base de datos.

Esquema unificado: users (role) + driver_profiles + vehicles.
Funciona con PostgreSQL o SQLite (DATABASE_URL del .env o entorno).
"""
import sys
import os
import secrets

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from backend.models import (
    db, User, DriverProfile, Vehicle,
    ROLE_PASSENGER, ROLE_DRIVER, MODE_PASSENGER, MODE_DRIVER,
)
from backend.app import app
from werkzeug.security import generate_password_hash


def create_demo_users():
    with app.app_context():
        passenger_exists = User.query.filter_by(email="pasajero@demo.com").first()
        driver_exists = User.query.filter_by(email="conductor@demo.com").first()

        passenger_password = secrets.token_urlsafe(12)
        driver_password = secrets.token_urlsafe(12)

        if not passenger_exists:
            passenger = User(
                name="Juan Pérez",
                email="pasajero@demo.com",
                password=generate_password_hash(passenger_password),
                phone="3001234567",
                email_verified=True,
                role=ROLE_PASSENGER,
                rating_avg=4.8,
                rating_count=12
            )
            db.session.add(passenger)
        else:
            passenger_password = '(ya existente)'

        if not driver_exists:
            driver = User(
                name="Carlos López",
                email="conductor@demo.com",
                password=generate_password_hash(driver_password),
                phone="3009876543",
                profile_picture="",
                email_verified=True,
                role=ROLE_DRIVER,
                rating_avg=4.9,
                rating_count=25,
                driver_profile=DriverProfile(
                    is_online=False,
                    is_busy=False,
                    vehicles=[Vehicle(
                        type="moto",
                        placa="ABC123",
                        marca="Honda",
                        modelo="CB 150",
                        color="Roja",
                        cilindrada="150cc",
                        has_patente=True,
                        has_casco=True,
                        has_seguro=True,
                        tipo_seguro="Responsabilidad Civil",
                        carnet_conducir="ABC123456",
                        ultimo_servicio="2024-01-15",
                        is_active=True,
                    )],
                ),
            )
            db.session.add(driver)
        else:
            driver_password = '(ya existente)'

        try:
            db.session.commit()
            print("\n✅ Usuarios de demostración configurados correctamente")
            print("\n📱 PASAJERO DEMO:")
            print("   Email: pasajero@demo.com")
            print(f"   Contraseña: {passenger_password}")
            print("\n🏍️  CONDUCTOR DEMO:")
            print("   Email: conductor@demo.com")
            print(f"   Contraseña: {driver_password}")
            print("\n💡 Roles duales: registra al conductor como pasajero en")
            print("   /driver/register o edita el rol a 'both' para probar modos.")
        except Exception as e:
            db.session.rollback()
            print(f"❌ Error al crear usuarios: {e}")


if __name__ == "__main__":
    create_demo_users()
