#!/usr/bin/env python
"""Elimina un usuario (o empresa) con sus datos relacionados. Esquema unificado.

Usa SQLAlchemy (DATABASE_URL de backend/.env) y respeta los FKs del modelo.
Advertencia: operación destructiva, pide confirmación.
"""
import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
from backend.models import (
    db, User, Company, Trip, Review, WalletTransaction, TopUpRequest,
    PassengerPaymentConfig, FavoriteAddress, CompanyMember,
)
from backend.app import app

load_dotenv(os.path.join(PROJECT_ROOT, 'backend', '.env'))

database = (os.getenv('DATABASE_URL') or '').split('?')[0]
if 'prod' in database.lower() or 'production' in database.lower():
    print(f'ABORT: refusing to modify database "{database}" (looks like production)')
    sys.exit(1)


def list_records():
    users = User.query.order_by(User.id).all()
    print('=== USUARIOS ===')
    for u in users:
        role = u.role or '?'
        extra = ''
        if u.driver_profile is not None:
            veh = u.driver_profile.active_vehicle
            extra = f" | CONDUCTOR {veh.type if veh else '?'} {veh.placa if veh else ''}"
        print(f'  [{u.id}] {u.name} - {u.email} [{role}]{extra} ({u.created_at})')
    companies = Company.query.order_by(Company.id).all()
    print('\n=== EMPRESAS ===')
    for c in companies:
        print(f'  [{c.id}] {c.name} - {c.email} [{c.status}] ({c.created_at})')


def delete_user(user_id):
    user = User.query.get(user_id)
    if not user:
        print(f'Usuario ID {user_id} no encontrado.')
        return False

    profile = user.driver_profile
    veh_type = f" {profile.active_vehicle.type} {profile.active_vehicle.placa}" if profile and profile.active_vehicle else ''
    print(f'\n{"="*40}')
    print(f'Usuario: {user.name} <{user.email}> [{user.role}]{veh_type}')
    print(f'{"="*40}')
    confirm = input(f'\n¿Eliminar usuario ID {user_id} y TODOS sus datos relacionados? (s/n): ').strip().lower()
    if confirm != 's':
        print('Cancelado.')
        return False

    # relaciones (FKs)
    WalletTransaction.query.filter(
        db.or_(WalletTransaction.user_id == user.id, WalletTransaction.counterparty_id == user.id)
    ).delete(synchronize_session=False)
    TopUpRequest.query.filter_by(user_id=user.id).delete(synchronize_session=False)
    PassengerPaymentConfig.query.filter_by(user_id=user.id).delete(synchronize_session=False)
    FavoriteAddress.query.filter_by(user_id=user.id).delete(synchronize_session=False)
    CompanyMember.query.filter_by(user_id=user.id).delete(synchronize_session=False)
    Review.query.filter(
        db.or_(Review.from_user_id == user.id, Review.to_user_id == user.id)
    ).delete(synchronize_session=False)
    Trip.query.filter_by(passenger_id=user.id).delete(synchronize_session=False)
    Trip.query.filter(Trip.driver_id == user.id).update({'driver_id': None}, synchronize_session=False)
    if profile:
        db.session.delete(profile)  # cascade: vehicles, payment_methods
    db.session.delete(user)
    db.session.commit()
    print(f'\nUsuario ID {user_id} eliminado.')
    return True


def delete_company(company_id):
    company = Company.query.get(company_id)
    if not company:
        print(f'Empresa ID {company_id} no encontrada.')
        return False
    print(f'\n{"="*40}')
    print(f'Empresa: {company.name} <{company.email}> [{company.status}]')
    print(f'{"="*40}')
    confirm = input(f'\n¿Eliminar empresa ID {company_id} y sus relaciones? (s/n): ').strip().lower()
    if confirm != 's':
        print('Cancelado.')
        return False
    CompanyMember.query.filter_by(company_id=company.id).delete(synchronize_session=False)
    Trip.query.filter(Trip.company_id == company.id).update({'company_id': None}, synchronize_session=False)
    db.session.delete(company)
    db.session.commit()
    print(f'\nEmpresa ID {company_id} eliminada.')
    return True


if __name__ == '__main__':
    with app.app_context():
        list_records()
        tipo = input('\n¿Qué quieres eliminar? [U]suario / [E]mpresa: ').strip().lower()
        if tipo in ('u', 'usuario'):
            id_str = input('\nID del usuario a eliminar: ').strip()
            if not id_str.isdigit():
                print('ID inválido.')
                sys.exit(1)
            delete_user(int(id_str))
        elif tipo in ('e', 'empresa'):
            id_str = input('\nID de la empresa a eliminar: ').strip()
            if not id_str.isdigit():
                print('ID inválido.')
                sys.exit(1)
            delete_company(int(id_str))
        else:
            print('Opción inválida.')
            sys.exit(1)
