import pymysql
import sys
from dotenv import load_dotenv
import os

load_dotenv('backend/.env')

database = os.getenv('MYSQL_DB', 'van')
host = os.getenv('MYSQL_HOST', '127.0.0.1')

if 'prod' in database.lower() or 'production' in database.lower():
    print(f'ABORT: refusing to reset database "{database}" (looks like production)')
    sys.exit(1)

if not os.getenv('FORCE_RESET'):
    confirm = input(f'¿Borrar TODOS los datos de "{database}" en {host}? (escribe "SI" para confirmar): ')
    if confirm != 'SI':
        print('Cancelado.')
        sys.exit(0)

conn = pymysql.connect(
    host=host,
    user=os.getenv('MYSQL_USER', 'root'),
    password=os.getenv('MYSQL_PASSWORD', ''),
    database=database
)
cur = conn.cursor()

cur.execute('SET FOREIGN_KEY_CHECKS = 0')

tablas = [
    'wallet_transactions',
    'topup_requests',
    'reviews',
    'trips',
    'driver_payment_methods',
    'passenger_payment_configs',
    'company_members',
    'companies',
    'users',
    'drivers',
]

for t in tablas:
    cur.execute(f'DELETE FROM {t}')
    cur.execute(f'ALTER TABLE {t} AUTO_INCREMENT = 1')
    print(f'  OK {t} vacia')

cur.execute('SET FOREIGN_KEY_CHECKS = 1')
conn.commit()
conn.close()
print(f'\nBase de datos "{database}" limpia.')
