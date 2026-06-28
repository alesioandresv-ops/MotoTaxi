#!/usr/bin/env python
"""
Migración CLI: agrega nuevas columnas a tablas existentes sin perder datos.
Uso: python migrate.py
(No se importa desde app.py — la migración es inline en backend/app.py)
"""
import os
import sys
from dotenv import load_dotenv


COLUMNAS = {
    'users': {
        'profile_picture': 'VARCHAR(255) NULL',
        'email_verified': 'TINYINT(1) DEFAULT 0',
        'rating_avg': 'FLOAT DEFAULT 5.0',
        'rating_count': 'INTEGER DEFAULT 0',
    },
    'drivers': {
        'profile_picture': 'VARCHAR(255) NULL',
        'email_verified': 'TINYINT(1) DEFAULT 0',
        'is_online': 'TINYINT(1) DEFAULT 0',
        'is_ocupado': 'TINYINT(1) DEFAULT 0',
        'lat': 'FLOAT NULL',
        'lng': 'FLOAT NULL',
        'last_location_update': 'DATETIME NULL',
        'rating_avg': 'FLOAT DEFAULT 5.0',
        'rating_count': 'INTEGER DEFAULT 0',
    },
    'trips': {
        'pickup_lat': 'FLOAT NULL',
        'pickup_lng': 'FLOAT NULL',
        'dropoff_lat': 'FLOAT NULL',
        'dropoff_lng': 'FLOAT NULL',
        'distance_km': 'FLOAT NULL',
        'duration_min': 'INTEGER NULL',
        'started_at': 'DATETIME NULL',
        'completed_at': 'DATETIME NULL',
        'cancelled_by': 'VARCHAR(20) NULL',
    },
}

TABLAS = {
    'reviews': """
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTO_INCREMENT,
            trip_id INTEGER NOT NULL,
            from_user_id INTEGER NULL,
            from_driver_id INTEGER NULL,
            to_user_id INTEGER NULL,
            to_driver_id INTEGER NULL,
            rating INTEGER NOT NULL,
            comment TEXT NULL,
            role VARCHAR(10) NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (trip_id) REFERENCES trips(id),
            FOREIGN KEY (from_user_id) REFERENCES users(id),
            FOREIGN KEY (from_driver_id) REFERENCES drivers(id),
            FOREIGN KEY (to_user_id) REFERENCES users(id),
            FOREIGN KEY (to_driver_id) REFERENCES drivers(id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    'driver_sessions': """
        CREATE TABLE IF NOT EXISTS driver_sessions (
            id INTEGER PRIMARY KEY AUTO_INCREMENT,
            driver_id INTEGER NOT NULL,
            is_online TINYINT(1) DEFAULT 0,
            lat FLOAT NULL,
            lng FLOAT NULL,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (driver_id) REFERENCES drivers(id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
}


def run_migration(database_url):
    """Ejecuta migración usando pymysql directo."""
    import pymysql

    url = database_url.replace('mysql+pymysql://', '').replace('mysql://', '')
    user_pass, rest = url.split('@', 1)
    db_user, db_pass = user_pass.split(':', 1)
    host_part = rest.split('/', 1)[0]
    db_name = rest.split('/', 1)[1].split('?')[0]

    if ':' in host_part:
        db_host, db_port = host_part.split(':', 1)
    else:
        db_host, db_port = host_part, 3306

    conn = pymysql.connect(host=db_host, port=int(db_port), user=db_user, password=db_pass, database=db_name)
    cursor = conn.cursor()

    for table, cols in COLUMNAS.items():
        cursor.execute(
            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s",
            (db_name, table)
        )
        existing = {r[0] for r in cursor.fetchall()}
        for col, typ in cols.items():
            if col not in existing:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")
                print(f"  ✅ {table}.{col}")

    for table, ddl in TABLAS.items():
        cursor.execute(
            "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s",
            (db_name, table)
        )
        if not cursor.fetchone():
            cursor.execute(ddl)
            print(f"  ✅ Tabla '{table}' creada")

    conn.commit()
    cursor.close()
    conn.close()
    print("  ✅ Migración CLI completada")


if __name__ == '__main__':
    load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), 'backend', '.env'))
    url = os.environ.get('DATABASE_URL')
    if not url:
        print("ERROR: DATABASE_URL no definida en backend/.env")
        sys.exit(1)
    print(f"Migrando: {url}\n")
    try:
        run_migration(url)
        print("\n✅ Listo, inicia con: python backend/app.py")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)
