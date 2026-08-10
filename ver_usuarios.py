#!/usr/bin/env python
"""Lista usuarios, conductores y empresas (esquema unificado).

Lee DATABASE_URL de backend/.env (PostgreSQL objetivo o SQLite de test).
"""
import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
from backend.models import db, User, Company
from backend.app import app

load_dotenv(os.path.join(PROJECT_ROOT, 'backend', '.env'))

with app.app_context():
    users = User.query.order_by(User.id).all()
    print('=== USUARIOS ===')
    for u in users:
        role = u.role or '?'
        profile = u.driver_profile
        online = ''
        if profile is not None:
            online = f" | online={profile.is_online} busy={profile.is_busy}"
            veh = profile.active_vehicle
            if veh:
                online += f" | {veh.type} {veh.placa or ''}"
        print(f'  [{u.id}] {u.name} - {u.email} [{role}]{online} ({u.created_at})')

    companies = Company.query.order_by(Company.id).all()
    print('\n=== EMPRESAS ===')
    for c in companies:
        print(f'  [{c.id}] {c.name} - {c.email} [{c.status}] ({c.created_at})')
