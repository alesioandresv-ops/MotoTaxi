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

cur.execute('SELECT id, name, email, created_at FROM users')
print('=== PASAJEROS ===')
for r in cur.fetchall():
    print(f'  [{r[0]}] {r[1]} - {r[2]} ({r[3]})')

cur.execute('SELECT id, name, email, created_at FROM drivers')
print('\n=== CONDUCTORES ===')
for r in cur.fetchall():
    print(f'  [{r[0]}] {r[1]} - {r[2]} ({r[3]})')

cur.execute('SELECT id, name, email, status, created_at FROM companies')
print('\n=== EMPRESAS ===')
for r in cur.fetchall():
    print(f'  [{r[0]}] {r[1]} - {r[2]} [{r[3]}] ({r[4]})')

conn.close()
