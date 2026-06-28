#!/usr/bin/env python
"""
Migración: agrega nuevas columnas a tablas existentes sin perder datos.
Uso directo:  python migrate.py
Importable:   from migrate import run_migration; run_migration(database_url)
"""
import os
import sys
from dotenv import load_dotenv


def run_migration(database_url):
    """Check each table and add any missing columns defined in models."""
    import pymysql

    parts = database_url.replace('mysql+pymysql://', '').replace('mysql://', '')
    user_pass, rest = parts.split('@', 1)
    db_user, db_pass = user_pass.split(':', 1)
    host_port, db_name = rest.split('/', 1)
    if ':' in host_port:
        db_host, db_port = host_port.split(':', 1)
    else:
        db_host = host_port
        db_port = 3306

    conn = pymysql.connect(
        host=db_host,
        port=int(db_port),
        user=db_user,
        password=db_pass,
        database=db_name
    )
    cursor = conn.cursor()

    cursor.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'users'", (db_name,))
    users_cols = {r[0] for r in cursor.fetchall()}

    cursor.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'drivers'", (db_name,))
    drivers_cols = {r[0] for r in cursor.fetchall()}

    cursor.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'trips'", (db_name,))
    trips_cols = {r[0] for r in cursor.fetchall()}

    # ─── users ───
    users_new = {
        'profile_picture': 'VARCHAR(255) NULL',
        'email_verified': 'TINYINT(1) DEFAULT 0',
        'rating_avg': 'FLOAT DEFAULT 5.0',
        'rating_count': 'INTEGER DEFAULT 0',
    }
    for col, col_type in users_new.items():
        if col not in users_cols:
            sql = f"ALTER TABLE users ADD COLUMN {col} {col_type}"
            cursor.execute(sql)
            print(f"  ✅ users.{col} agregada")

    # ─── drivers ───
    drivers_new = {
        'profile_picture': 'VARCHAR(255) NULL',
        'email_verified': 'TINYINT(1) DEFAULT 0',
        'is_online': 'TINYINT(1) DEFAULT 0',
        'is_ocupado': 'TINYINT(1) DEFAULT 0',
        'lat': 'FLOAT NULL',
        'lng': 'FLOAT NULL',
        'last_location_update': 'DATETIME NULL',
        'rating_avg': 'FLOAT DEFAULT 5.0',
        'rating_count': 'INTEGER DEFAULT 0',
    }
    for col, col_type in drivers_new.items():
        if col not in drivers_cols:
            sql = f"ALTER TABLE drivers ADD COLUMN {col} {col_type}"
            cursor.execute(sql)
            print(f"  ✅ drivers.{col} agregada")

    # ─── trips ───
    trips_new = {
        'pickup_lat': 'FLOAT NULL',
        'pickup_lng': 'FLOAT NULL',
        'dropoff_lat': 'FLOAT NULL',
        'dropoff_lng': 'FLOAT NULL',
        'distance_km': 'FLOAT NULL',
        'duration_min': 'INTEGER NULL',
        'started_at': 'DATETIME NULL',
        'completed_at': 'DATETIME NULL',
        'cancelled_by': 'VARCHAR(20) NULL',
    }
    for col, col_type in trips_new.items():
        if col not in trips_cols:
            sql = f"ALTER TABLE trips ADD COLUMN {col} {col_type}"
            cursor.execute(sql)
            print(f"  ✅ trips.{col} agregada")

    # ─── review ───
    cursor.execute("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'reviews'", (db_name,))
    if not cursor.fetchone():
        cursor.execute("""
            CREATE TABLE reviews (
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
        """)
        print("  ✅ Tabla 'reviews' creada")

    # ─── driver_sessions ───
    cursor.execute("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'driver_sessions'", (db_name,))
    if not cursor.fetchone():
        cursor.execute("""
            CREATE TABLE driver_sessions (
                id INTEGER PRIMARY KEY AUTO_INCREMENT,
                driver_id INTEGER NOT NULL,
                is_online TINYINT(1) DEFAULT 0,
                lat FLOAT NULL,
                lng FLOAT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (driver_id) REFERENCES drivers(id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        print("  ✅ Tabla 'driver_sessions' creada")

    conn.commit()
    cursor.close()
    conn.close()
    print("  ✅ Migración completada")


if __name__ == '__main__':
    load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), 'backend', '.env'))
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        print("ERROR: DATABASE_URL no definida en backend/.env")
        sys.exit(1)
    print(f"Migrando: {database_url}\n")
    try:
        run_migration(database_url)
        print("\n✅ Migración completada exitosamente")
        print("   Ahora puedes iniciar la app con: python backend/app.py")
    except Exception as e:
        print(f"\n❌ Error durante la migración: {e}")
        sys.exit(1)
