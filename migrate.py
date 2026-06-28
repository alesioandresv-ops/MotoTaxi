#!/usr/bin/env python
"""
Migración: agrega nuevas columnas a tablas existentes sin perder datos.
Uso directo:  python migrate.py
Importable:   from migrate import run_migration_sa; run_migration_sa(db)
"""
import os
import sys
from dotenv import load_dotenv


NEW_COLUMNS = {
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

MISSING_TABLES = {
    'reviews': """
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
    """,
    'driver_sessions': """
        CREATE TABLE driver_sessions (
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


def run_migration_sa(db):
    """
    Check each table and add any missing columns/tables using the
    app's existing SQLAlchemy engine (no URL parsing needed).
    """
    from sqlalchemy import inspect, text

    inspector = inspect(db.engine)

    for table_name, columns in NEW_COLUMNS.items():
        try:
            existing = {c['name'] for c in inspector.get_columns(table_name)}
        except Exception:
            print(f"  ⚠️  No se pudo inspeccionar {table_name}, quizá no existe")
            existing = set()

        for col, col_type in columns.items():
            if col not in existing:
                stmt = text(f"ALTER TABLE {table_name} ADD COLUMN {col} {col_type}")
                with db.engine.connect() as conn:
                    conn.execute(stmt)
                    conn.commit()
                print(f"  ✅ {table_name}.{col} agregada")

    for table_name, ddl in MISSING_TABLES.items():
        try:
            inspector.get_columns(table_name)
        except Exception:
            with db.engine.connect() as conn:
                conn.execute(text(ddl))
                conn.commit()
            print(f"  ✅ Tabla '{table_name}' creada")

    print("  ✅ Migración completada")


def run_migration(database_url):
    """
    Legacy version using raw pymysql (for CLI usage).
    Prefer run_migration_sa() when running inside the app.
    """
    import pymysql

    parts = database_url.replace('mysql+pymysql://', '').replace('mysql://', '')
    user_pass, rest = parts.split('@', 1)
    db_user, db_pass = user_pass.split(':', 1)
    query_parts = rest.split('/', 1)
    if len(query_parts) != 2:
        print("  ⚠️  URL no válida, no se puede migrar")
        return
    host_port, db_name = query_parts
    db_name = db_name.split('?')[0]  # quitar query params (ssl, etc.)
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

    for table_name, columns in NEW_COLUMNS.items():
        cursor.execute(
            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s",
            (db_name, table_name)
        )
        existing = {r[0] for r in cursor.fetchall()}
        for col, col_type in columns.items():
            if col not in existing:
                cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {col} {col_type}")
                print(f"  ✅ {table_name}.{col} agregada")

    for table_name, ddl in MISSING_TABLES.items():
        cursor.execute(
            "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s",
            (db_name, table_name)
        )
        if not cursor.fetchone():
            cursor.execute(ddl)
            print(f"  ✅ Tabla '{table_name}' creada")

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
