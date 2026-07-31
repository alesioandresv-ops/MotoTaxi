import pymysql
import sys
from dotenv import load_dotenv
import os

load_dotenv('backend/.env')

database = os.getenv('MYSQL_DB', 'van')
host = os.getenv('MYSQL_HOST', '127.0.0.1')

if 'prod' in database.lower() or 'production' in database.lower():
    print(f'ABORT: refusing to modify database "{database}" (looks like production)')
    sys.exit(1)

conn = pymysql.connect(
    host=host,
    user=os.getenv('MYSQL_USER', 'root'),
    password=os.getenv('MYSQL_PASSWORD', ''),
    database=database
)
cur = conn.cursor()

# ─── Listar usuarios ───
cur.execute('SELECT id, name, email, created_at FROM users')
pasajeros = cur.fetchall()
print('=== PASAJEROS ===')
for r in pasajeros:
    print(f'  [{r[0]}] {r[1]} - {r[2]} ({r[3]})')

cur.execute('SELECT id, name, email, created_at FROM drivers')
conductores = cur.fetchall()
print('\n=== CONDUCTORES ===')
for r in conductores:
    print(f'  [{r[0]}] {r[1]} - {r[2]} ({r[3]})')

cur.execute('SELECT id, name, email, status, created_at FROM companies')
empresas = cur.fetchall()
print('\n=== EMPRESAS ===')
for r in empresas:
    print(f'  [{r[0]}] {r[1]} - {r[2]} [{r[3]}] ({r[4]})')

if not pasajeros and not conductores and not empresas:
    print('\nNo hay registros para eliminar.')
    conn.close()
    sys.exit(0)

# ─── Seleccionar tipo ───
print('\n¿Qué quieres eliminar?')
print('  [P] Pasajero')
print('  [C] Conductor')
print('  [E] Empresa')
tipo = input('Tipo: ').strip().lower()

if tipo == 'p':
    table = 'users'
    label = 'pasajero'
elif tipo == 'c':
    table = 'drivers'
    label = 'conductor'
elif tipo == 'e':
    table = 'companies'
    label = 'empresa'
else:
    print('Opción inválida.')
    conn.close()
    sys.exit(1)

# ─── Seleccionar ID ───
id_str = input(f'\nID del {label} a eliminar: ').strip()
if not id_str.isdigit():
    print('ID inválido.')
    conn.close()
    sys.exit(1)

record_id = int(id_str)

cur.execute(f'SELECT * FROM {table} WHERE id = %s', (record_id,))
row = cur.fetchone()
if not row:
    print(f'{label.capitalize()} con ID {record_id} no encontrado.')
    conn.close()
    sys.exit(1)

# Obtener nombres de columnas
cur.execute(f'SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s', (database, table))
columns = [r[0] for r in cur.fetchall()]

print(f'\n{"="*40}')
print(f'Registro encontrado ({label}):')
for col, val in zip(columns, row):
    if col == 'password':
        print(f'  {col}: ****')
    elif val is not None:
        print(f'  {col}: {val}')
print(f'{"="*40}')

confirm = input(f'\n¿Eliminar {label} ID {record_id} y TODOS sus datos relacionados? (s/n): ').strip().lower()
if confirm != 's':
    print('Cancelado.')
    conn.close()
    sys.exit(0)

# ─── Eliminar registros relacionados ───
cur.execute('SET FOREIGN_KEY_CHECKS = 0')

deleted = []

if table == 'users':
    cur.execute('DELETE FROM wallet_transactions WHERE user_id = %s', (record_id,))
    deleted.append(('wallet_transactions', cur.rowcount))
    cur.execute('DELETE FROM topup_requests WHERE user_id = %s', (record_id,))
    deleted.append(('topup_requests', cur.rowcount))
    cur.execute('DELETE FROM passenger_payment_configs WHERE user_id = %s', (record_id,))
    deleted.append(('passenger_payment_configs', cur.rowcount))
    cur.execute('DELETE FROM company_members WHERE user_id = %s', (record_id,))
    deleted.append(('company_members', cur.rowcount))
    cur.execute('DELETE FROM reviews WHERE from_user_id = %s OR to_user_id = %s', (record_id, record_id))
    deleted.append(('reviews', cur.rowcount))
    cur.execute('DELETE FROM trips WHERE passenger_id = %s', (record_id,))
    deleted.append(('trips', cur.rowcount))

elif table == 'drivers':
    cur.execute('DELETE FROM wallet_transactions WHERE driver_id = %s', (record_id,))
    deleted.append(('wallet_transactions', cur.rowcount))
    cur.execute('DELETE FROM driver_payment_methods WHERE driver_id = %s', (record_id,))
    deleted.append(('driver_payment_methods', cur.rowcount))
    cur.execute('DELETE FROM reviews WHERE from_driver_id = %s OR to_driver_id = %s', (record_id, record_id))
    deleted.append(('reviews', cur.rowcount))
    cur.execute('UPDATE trips SET driver_id = NULL WHERE driver_id = %s', (record_id,))
    deleted.append(('trips (driver_id = NULL)', cur.rowcount))

elif table == 'companies':
    cur.execute('DELETE FROM company_members WHERE company_id = %s', (record_id,))
    deleted.append(('company_members', cur.rowcount))
    cur.execute('UPDATE trips SET company_id = NULL WHERE company_id = %s', (record_id,))
    deleted.append(('trips (company_id = NULL)', cur.rowcount))

cur.execute(f'DELETE FROM {table} WHERE id = %s', (record_id,))
deleted.append((table, cur.rowcount))

cur.execute('SET FOREIGN_KEY_CHECKS = 1')
conn.commit()
conn.close()

print(f'\n{label.capitalize()} ID {record_id} eliminado.')
print('Registros eliminados:')
for t, count in deleted:
    print(f'  {t}: {count}')
