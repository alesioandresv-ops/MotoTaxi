import pymysql
from dotenv import load_dotenv
import os

load_dotenv('backend/.env')

conn = pymysql.connect(
    host=os.getenv('MYSQL_HOST', '127.0.0.1'),
    user=os.getenv('MYSQL_USER', 'root'),
    password=os.getenv('MYSQL_PASSWORD', ''),
    database=os.getenv('MYSQL_DB', 'mototaxi')
)
cur = conn.cursor()

tablas = [
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
    print(f'  OK {t} vacia (auto_increment reset)')

conn.commit()
conn.close()
print('\nBase de datos limpia y auto_increment reseteado. Lista para empezar de cero.')
