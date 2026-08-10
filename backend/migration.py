import os
import pymysql
from dotenv import load_dotenv


COLUMNAS = {
    'users': {
        'profile_picture': 'VARCHAR(255) NULL',
        'email_verified': 'TINYINT(1) DEFAULT 0',
        'balance': 'DECIMAL(12,2) DEFAULT 0.0',
        'rating_avg': 'FLOAT DEFAULT 5.0',
        'rating_count': 'INTEGER DEFAULT 0',
        'accepted_guidelines': 'TINYINT(1) DEFAULT 0',
    },
    'drivers': {
        'profile_picture': 'VARCHAR(255) NOT NULL DEFAULT ""',
        'email_verified': 'TINYINT(1) DEFAULT 0',
        'is_online': 'TINYINT(1) DEFAULT 0',
        'is_ocupado': 'TINYINT(1) DEFAULT 0',
        'lat': 'FLOAT NULL',
        'lng': 'FLOAT NULL',
        'last_location_update': 'DATETIME NULL',
        'rating_avg': 'FLOAT DEFAULT 5.0',
        'rating_count': 'INTEGER DEFAULT 0',
        'accepted_guidelines': 'TINYINT(1) DEFAULT 0',
        'is_verified': 'TINYINT(1) DEFAULT 0',
        'vehicle_type': 'VARCHAR(10) DEFAULT "moto"',
        'placa_auto': 'VARCHAR(50) NULL',
        'auto_marca': 'VARCHAR(120) NULL',
        'auto_modelo': 'VARCHAR(120) NULL',
        'auto_color': 'VARCHAR(80) NULL',
        'auto_año': 'VARCHAR(10) NULL',
        'tiene_patente_auto': 'TINYINT(1) DEFAULT 0',
        'seguro_auto': 'TINYINT(1) DEFAULT 0',
        'tipo_seguro_auto': 'VARCHAR(120) NULL',
        'carnet_conducir_auto': 'VARCHAR(120) NULL',
        'ultimo_servicio_auto': 'VARCHAR(120) NULL',
        'accepted_payments': 'VARCHAR(500) DEFAULT \'["efectivo"]\'',
        'mercadopago_qr': 'VARCHAR(500) NULL',
        'balance': 'DECIMAL(12,2) DEFAULT 0.0',
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
        'vehicle_type': 'VARCHAR(10) DEFAULT "moto"',
        'company_id': 'INTEGER NULL',
        'payment_method': 'VARCHAR(50) NULL',
        'fare': 'DECIMAL(12,2) NOT NULL DEFAULT 0.0',
    },
    'wallet_transactions': {
        'amount': 'DECIMAL(12,2) NOT NULL DEFAULT 0.0',
    },
    'topup_requests': {
        'amount': 'DECIMAL(12,2) NOT NULL DEFAULT 0.0',
    },
}

COLUMN_MODIFY = {
    'users': {
        'balance': 'DECIMAL(12,2) DEFAULT 0.0',
    },
    'drivers': {
        'balance': 'DECIMAL(12,2) DEFAULT 0.0',
    },
    'trips': {
        'fare': 'DECIMAL(12,2) NOT NULL DEFAULT 0.0',
    },
    'wallet_transactions': {
        'amount': 'DECIMAL(12,2) NOT NULL DEFAULT 0.0',
    },
    'topup_requests': {
        'amount': 'DECIMAL(12,2) NOT NULL DEFAULT 0.0',
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
    'companies': """
        CREATE TABLE IF NOT EXISTS companies (
            id INTEGER PRIMARY KEY AUTO_INCREMENT,
            name VARCHAR(200) NOT NULL,
            email VARCHAR(120) NOT NULL UNIQUE,
            password VARCHAR(255) NOT NULL,
            phone VARCHAR(30) NULL,
            plan VARCHAR(20) NOT NULL DEFAULT 'basic',
            status VARCHAR(20) NOT NULL DEFAULT 'trial',
            subscription_start DATETIME NULL,
            subscription_end DATETIME NULL,
            payment_method VARCHAR(50) NULL,
            payment_reference VARCHAR(255) NULL,
            max_employees INTEGER DEFAULT 15,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    'company_members': """
        CREATE TABLE IF NOT EXISTS company_members (
            id INTEGER PRIMARY KEY AUTO_INCREMENT,
            company_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            role VARCHAR(20) NOT NULL DEFAULT 'employee',
            invited_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            joined_at DATETIME NULL,
            FOREIGN KEY (company_id) REFERENCES companies(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    'driver_payment_methods': """
        CREATE TABLE IF NOT EXISTS driver_payment_methods (
            id INTEGER PRIMARY KEY AUTO_INCREMENT,
            driver_id INTEGER NOT NULL,
            type VARCHAR(30) NOT NULL,
            details TEXT NULL,
            is_active TINYINT(1) DEFAULT 1,
            FOREIGN KEY (driver_id) REFERENCES drivers(id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    'passenger_payment_configs': """
        CREATE TABLE IF NOT EXISTS passenger_payment_configs (
            id INTEGER PRIMARY KEY AUTO_INCREMENT,
            user_id INTEGER NOT NULL,
            type VARCHAR(30) NOT NULL,
            details TEXT NULL,
            is_default TINYINT(1) DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    'wallet_transactions': """
        CREATE TABLE IF NOT EXISTS wallet_transactions (
            id INTEGER PRIMARY KEY AUTO_INCREMENT,
            user_id INTEGER NULL,
            driver_id INTEGER NULL,
            amount DECIMAL(12,2) NOT NULL DEFAULT 0.0,
            type VARCHAR(30) NOT NULL,
            trip_id INTEGER NULL,
            reference VARCHAR(200) NULL,
            status VARCHAR(20) DEFAULT 'completed',
            description VARCHAR(200) NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (driver_id) REFERENCES drivers(id),
            FOREIGN KEY (trip_id) REFERENCES trips(id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    'topup_requests': """
        CREATE TABLE IF NOT EXISTS topup_requests (
            id INTEGER PRIMARY KEY AUTO_INCREMENT,
            user_id INTEGER NOT NULL,
            amount DECIMAL(12,2) NOT NULL DEFAULT 0.0,
            method VARCHAR(30) NOT NULL,
            voucher_url VARCHAR(500) NULL,
            mp_payment_id VARCHAR(100) NULL,
            status VARCHAR(20) DEFAULT 'pending',
            admin_note VARCHAR(200) NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            confirmed_at DATETIME NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    'refresh_tokens': """
        CREATE TABLE IF NOT EXISTS refresh_tokens (
            id INTEGER PRIMARY KEY AUTO_INCREMENT,
            user_type VARCHAR(10) NOT NULL,
            user_id INTEGER NOT NULL,
            token_hash VARCHAR(64) NOT NULL UNIQUE,
            expires_at DATETIME NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            revoked_at DATETIME NULL,
            replaced_by_id INTEGER NULL,
            user_agent VARCHAR(255) NULL,
            INDEX idx_refresh_user (user_type, user_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    'email_verifications': """
        CREATE TABLE IF NOT EXISTS email_verifications (
            id INTEGER PRIMARY KEY AUTO_INCREMENT,
            user_type VARCHAR(10) NOT NULL,
            user_id INTEGER NOT NULL,
            email VARCHAR(120) NOT NULL,
            code_hash VARCHAR(64) NOT NULL,
            attempts INTEGER DEFAULT 0,
            expires_at DATETIME NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            verified_at DATETIME NULL,
            INDEX idx_email_verif_user (user_type, user_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
}


def _is_mysql(url):
    return url and ('mysql://' in url or 'mysql+pymysql://' in url)


def _parse_url(url):
    u = url.replace('mysql+pymysql://', '').replace('mysql://', '')
    if '@' not in u:
        return None, None, None, None, None
    user_pass, rest = u.split('@', 1)
    db_user, db_pass = user_pass.split(':', 1)
    host_part = rest.split('/', 1)[0]
    db_name = rest.split('/', 1)[1].split('?')[0]
    if ':' in host_part:
        db_host, db_port = host_part.split(':', 1)
    else:
        db_host, db_port = host_part, '3306'
    return db_host, int(db_port), db_user, db_pass, db_name


def _get_conn(url):
    host, port, user, password, database = _parse_url(url)
    if not host:
        return None
    return pymysql.connect(host=host, port=port, user=user, password=password, database=database, autocommit=True)


def run_migration(url):
    if not _is_mysql(url):
        print("  [-] No es MySQL, saltando migracion pymysql", flush=True)
        return

    conn = _get_conn(url)
    if not conn:
        print("  [-] No se pudo conectar a MySQL, saltando", flush=True)
        return
    cursor = conn.cursor()
    _, _, _, _, db_name = _parse_url(url)

    for table, cols in COLUMNAS.items():
        cursor.execute(
            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s",
            (db_name, table)
        )
        existing = {r[0] for r in cursor.fetchall()}
        for col, typ in cols.items():
            if col not in existing:
                try:
                    cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")
                    print(f"  [+] {table}.{col}")
                except Exception as col_err:
                    print(f"  [WARN] {table}.{col}: {col_err}")

    for table, cols in COLUMN_MODIFY.items():
        cursor.execute(
            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s",
            (db_name, table)
        )
        existing = {r[0] for r in cursor.fetchall()}
        for col, typ in cols.items():
            if col in existing:
                try:
                    cursor.execute(f"ALTER TABLE {table} MODIFY COLUMN {col} {typ}")
                    print(f"  [~] {table}.{col} -> {typ}")
                except Exception as col_err:
                    print(f"  [WARN] {table}.{col} modify: {col_err}")

    for table, ddl in TABLAS.items():
        cursor.execute(
            "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s",
            (db_name, table)
        )
        if not cursor.fetchone():
            cursor.execute(ddl)
            print(f"  [+] Tabla '{table}' creada")

    cursor.close()
    conn.close()


def run_all(app):
    url = os.environ.get('DATABASE_URL', '')
    if url:
        print("[Migracion] Verificando columnas/tablas...", flush=True)
        try:
            run_migration(url)
        except Exception as e:
            print(f"  [WARN] Migration error: {e}", flush=True)

    print("[Migracion] db.create_all()...", flush=True)
    from backend.models import db
    db.create_all()
    print("[Migracion] OK", flush=True)


if __name__ == '__main__':
    load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '.env'))
    url = os.environ.get('DATABASE_URL')
    if not url:
        print("ERROR: DATABASE_URL no definida en backend/.env")
        import sys; sys.exit(1)
    print("Migrando base de datos...\n")
    run_migration(url)
    print("\nMigracion completada. Inicia con: python backend/app.py")
