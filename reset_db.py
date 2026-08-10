#!/usr/bin/env python
"""Limpia TODOS los datos (dev only). Esquema unificado.

Usa SQLAlchemy (DATABASE_URL de backend/.env). Nunca corre contra
bases que parezcan producción. Requiere confirmación (o FORCE_RESET=1).
"""
import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
from backend.models import (
    db, User, Company, Trip, Review, WalletTransaction, TopUpRequest,
    PassengerPaymentConfig, FavoriteAddress, CompanyMember,
    DriverPaymentMethod, RefreshToken, EmailVerification, Vehicle, DriverProfile,
)
from backend.app import app

load_dotenv(os.path.join(PROJECT_ROOT, 'backend', '.env'))

database = (os.getenv('DATABASE_URL') or '').split('?')[0]
if 'prod' in database.lower() or 'production' in database.lower():
    print(f'ABORT: refusing to reset database "{database}" (looks like production)')
    sys.exit(1)

if not os.getenv('FORCE_RESET'):
    confirm = input(f'¿Borrar TODOS los datos de "{database}"? (escribe "SI" para confirmar): ')
    if confirm != 'SI':
        print('Cancelado.')
        sys.exit(0)

tablas = [
    WalletTransaction,
    TopUpRequest,
    Review,
    Trip,
    DriverPaymentMethod,
    PassengerPaymentConfig,
    FavoriteAddress,
    CompanyMember,
    RefreshToken,
    EmailVerification,
    Vehicle,
    DriverProfile,
    Company,
    User,
]

with app.app_context():
    for m in tablas:
        m.query.delete(synchronize_session=False)
        print(f'  OK {m.__tablename__} vacia')
    db.session.commit()
    print(f'\nBase de datos "{database}" limpia.')
