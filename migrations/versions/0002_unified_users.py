"""refactor usuarios unificados + trips comision

Revision ID: 0002
Revises: 7234ca128813
Create Date: 2026-08-10

Transforma el esquema legacy (users+drivers separados) al unificado:
users(role) + driver_profiles + vehicles. Repara FKs de trips/reviews/
wallet/tokens. Prepara trips para comision (total_fare, platform_fee,
platform_fee_rate, driver_earnings, currency).

El merge de datos legacy es defensivo: solo corre si la tabla 'drivers'
existe y tiene filas (PG que haya tenido datos en Etapa 1). Los nombres de
FK siguen el patron PostgreSQL por defecto (<tabla>_<columna>_fkey).
"""
from alembic import op
import sqlalchemy as sa

revision = '0002'
down_revision = '7234ca128813'
branch_labels = None
depends_on = None


# ───────────────────────── helpers ─────────────────────────

def _fk_name(table, column):
    return f'{table}_{column}_fkey'


def _is_sqlite():
    return _bind().dialect.name == 'sqlite'


def _drop_fk(table, column):
    # En SQLite las FK no tienen nombre y no se pueden soltar por separado:
    # el batch_alter_table de _drop_column reconstruye la tabla sin ellas.
    if _is_sqlite():
        return
    op.drop_constraint(_fk_name(table, column), table, type_='foreignkey')


def _create_fk(name, table, referent, local_cols, remote_cols, ondelete=None):
    if _is_sqlite():
        with op.batch_alter_table(table) as batch:
            batch.create_foreign_key(name, referent, local_cols, remote_cols, ondelete=ondelete)
    else:
        op.create_foreign_key(name, table, referent, local_cols, remote_cols, ondelete=ondelete)


def _create_check(name, table, condition):
    if _is_sqlite():
        with op.batch_alter_table(table) as batch:
            batch.create_check_constraint(name, condition)
    else:
        op.create_check_constraint(name, table, condition)


def _create_unique(name, table, columns):
    if _is_sqlite():
        with op.batch_alter_table(table) as batch:
            batch.create_unique_constraint(name, columns)
    else:
        op.create_unique_constraint(name, table, columns)


def _set_nullable(table, column, existing_type, nullable):
    if _is_sqlite():
        with op.batch_alter_table(table) as batch:
            batch.alter_column(column, existing_type=existing_type, nullable=nullable)
    else:
        op.alter_column(table, column, existing_type=existing_type, nullable=nullable)


def _drop_column(table, column):
    # batch en SQLite: DROP COLUMN nativo falla si la columna participa en
    # FK o CHECK; la reconstrucción de tabla los elimina correctamente.
    if _is_sqlite():
        with op.batch_alter_table(table) as batch:
            batch.drop_column(column)
    else:
        op.drop_column(table, column)


def _drop_named(type_, name, table):
    # SQLite no almacena nombres de constraints: el drop se omite y la
    # recreación de tabla (_drop_column) los elimina implícitamente.
    if _is_sqlite():
        return
    op.drop_constraint(name, table, type_=type_)


def _bind():
    return op.get_bind()


def _online():
    from alembic import context
    return not context.is_offline_mode()


def _table_has(bind, table):
    insp = sa.inspect(bind)
    return table in insp.get_table_names()


def _column_has(bind, table, column):
    if not _table_has(bind, table):
        return False
    insp = sa.inspect(bind)
    return column in {c['name'] for c in insp.get_columns(table)}


def _driver_user_map(bind):
    """drivers.id → users.id (crea users/profiles/vehicles si hace falta)."""
    map_ = {}
    if not _table_has(bind, 'drivers') or not _column_has(bind, 'drivers', 'email'):
        return map_
    rows = bind.execute(
        sa.text(
            'SELECT id, name, email, password, phone, profile_picture, '
            'email_verified, rating_avg, rating_count, accepted_guidelines, '
            'balance, created_at, is_online, is_ocupado, lat, lng, '
            'last_location_update, is_verified, accepted_payments, '
            'mercadopago_qr, vehicle_type, placa, moto_marca, moto_modelo, '
            'moto_color, moto_cilindrada, tiene_patente, tiene_casco, '
            'seguro_moto, tipo_seguro, carnet_conducir, ultimo_servicio, '
            'placa_auto, auto_marca, auto_modelo, auto_color, "auto_año", '
            'tiene_patente_auto, seguro_auto, tipo_seguro_auto, '
            'carnet_conducir_auto, ultimo_servicio_auto '
            'FROM drivers'
        )
    ).fetchall()
    for r in rows:
        (did, name, email, password, phone, profile_picture, email_verified,
         rating_avg, rating_count, accepted_guidelines, balance, created_at,
         is_online, is_ocupado, lat, lng, last_location_update, is_verified,
         accepted_payments, mercadopago_qr, vehicle_type, placa,
         moto_marca, moto_modelo, moto_color, moto_cilindrada, tiene_patente,
         tiene_casco, seguro_moto, tipo_seguro, carnet_conducir,
         ultimo_servicio, placa_auto, auto_marca, auto_modelo, auto_color,
         auto_anio, tiene_patente_auto, seguro_auto, tipo_seguro_auto,
         carnet_conducir_auto, ultimo_servicio_auto) = r

        existing = bind.execute(
            sa.text('SELECT id, role FROM users WHERE email = :e'),
            {'e': email},
        ).fetchone()
        if existing:
            uid, urole = existing
            if urole in ('passenger', 'both', 'driver'):
                new_role = urole
            else:
                new_role = urole
            if urole == 'passenger':
                bind.execute(
                    sa.text('UPDATE users SET role = :r WHERE id = :i'),
                    {'r': 'both', 'i': uid},
                )
            elif urole == 'driver':
                pass
            else:
                bind.execute(
                    sa.text('UPDATE users SET role = :r WHERE id = :i'),
                    {'r': 'both', 'i': uid},
                )
        else:
            res = bind.execute(
                sa.text(
                    'INSERT INTO users (name, email, password, phone, '
                    'profile_picture, email_verified, rating_avg, '
                    'rating_count, accepted_guidelines, balance, created_at, '
                    'role) VALUES (:n, :e, :p, :ph, :pp, :ev, :ra, :rc, '
                    ':ag, :bal, :ca, :r) RETURNING id'
                ),
                {
                    'n': name, 'e': email, 'p': password, 'ph': phone,
                    'pp': profile_picture or '', 'ev': bool(email_verified),
                    'ra': rating_avg or 5.0, 'rc': rating_count or 0,
                    'ag': bool(accepted_guidelines), 'bal': balance or 0,
                    'ca': created_at, 'r': 'driver',
                },
            )
            uid = res.fetchone()[0]

        prof = bind.execute(
            sa.text(
                'SELECT id FROM driver_profiles WHERE user_id = :u'
            ),
            {'u': uid},
        ).fetchone()
        if prof:
            pid = prof[0]
        else:
            res = bind.execute(
                sa.text(
                    'INSERT INTO driver_profiles (user_id, is_online, '
                    'is_busy, lat, lng, last_location_update, is_verified, '
                    'accepted_payments, mercadopago_qr, carnet_conducir, '
                    'tipo_seguro, ultimo_servicio) VALUES (:u, :on, :busy, '
                    ':lat, :lng, :llu, :ver, :ap, :qr, :cc, :ts, :us) '
                    'RETURNING id'
                ),
                {
                    'u': uid, 'on': bool(is_online), 'busy': bool(is_ocupado),
                    'lat': lat, 'lng': lng, 'llu': last_location_update,
                    'ver': bool(is_verified), 'ap': accepted_payments or '["efectivo"]',
                    'qr': mercadopago_qr, 'cc': carnet_conducir,
                    'ts': tipo_seguro, 'us': ultimo_servicio,
                },
            )
            pid = res.fetchone()[0]

        if vehicle_type == 'moto':
            vcols = {
                'type': 'moto', 'placa': placa, 'marca': moto_marca,
                'modelo': moto_modelo, 'color': moto_color,
                'cilindrada': moto_cilindrada, 'anio': None,
                'has_patente': bool(tiene_patente), 'has_casco': bool(tiene_casco),
                'has_seguro': bool(seguro_moto), 'tipo_seguro': tipo_seguro,
                'carnet_conducir': carnet_conducir,
                'ultimo_servicio': ultimo_servicio,
            }
        else:
            vcols = {
                'type': 'auto', 'placa': placa_auto, 'marca': auto_marca,
                'modelo': auto_modelo, 'color': auto_color, 'anio': auto_anio,
                'has_patente': bool(tiene_patente_auto), 'has_casco': False,
                'has_seguro': bool(seguro_auto), 'tipo_seguro': tipo_seguro_auto,
                'carnet_conducir': carnet_conducir_auto,
                'ultimo_servicio': ultimo_servicio_auto,
            }
        bind.execute(
            sa.text(
                'INSERT INTO vehicles (driver_profile_id, type, placa, marca, '
                'modelo, color, cilindrada, anio, has_patente, has_casco, '
                'has_seguro, tipo_seguro, carnet_conducir, ultimo_servicio, '
                'is_active) VALUES (:pid, :t, :pl, :ma, :mo, :co, :ci, :an, '
                ':hp, :hc, :hs, :ts, :cc, :us, true)'
            ),
            {
                'pid': pid, 't': vcols['type'], 'pl': vcols['placa'],
                'ma': vcols['marca'], 'mo': vcols['modelo'], 'co': vcols['color'],
                'ci': vcols['cilindrada'], 'an': vcols['anio'],
                'hp': vcols['has_patente'], 'hc': vcols['has_casco'],
                'hs': vcols['has_seguro'], 'ts': vcols['tipo_seguro'],
                'cc': vcols['carnet_conducir'], 'us': vcols['ultimo_servicio'],
            },
        )
        map_[did] = uid
    return map_


# ───────────────────────── upgrade ─────────────────────────

def upgrade():
    bind = _bind()

    # ── users.role ──
    op.add_column(
        'users',
        sa.Column('role', sa.String(length=10), nullable=False,
                  server_default='passenger'),
    )
    op.create_index('ix_users_email_lower', 'users', [sa.text('lower(email)')], unique=True)
    _create_check(
        'chk_users_role',
        'users',
        "role IN ('passenger', 'driver', 'both', 'admin', 'company')",
    )

    # ── driver_profiles ──
    op.create_table(
        'driver_profiles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('is_online', sa.Boolean(), nullable=True),
        sa.Column('is_busy', sa.Boolean(), nullable=True),
        sa.Column('lat', sa.Float(), nullable=True),
        sa.Column('lng', sa.Float(), nullable=True),
        sa.Column('last_location_update', sa.DateTime(), nullable=True),
        sa.Column('is_verified', sa.Boolean(), nullable=True),
        sa.Column('accepted_payments', sa.String(length=500), nullable=True,
                  server_default='["efectivo"]'),
        sa.Column('mercadopago_qr', sa.String(length=500), nullable=True),
        sa.Column('carnet_conducir', sa.String(length=120), nullable=True),
        sa.Column('tipo_seguro', sa.String(length=120), nullable=True),
        sa.Column('ultimo_servicio', sa.String(length=120), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id'),
    )
    op.create_index('ix_driver_profiles_online_free', 'driver_profiles', ['is_online', 'is_busy'])

    # ── vehicles ──
    op.create_table(
        'vehicles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('driver_profile_id', sa.Integer(), nullable=False),
        sa.Column('type', sa.String(length=10), nullable=False),
        sa.Column('placa', sa.String(length=50), nullable=True),
        sa.Column('marca', sa.String(length=120), nullable=True),
        sa.Column('modelo', sa.String(length=120), nullable=True),
        sa.Column('color', sa.String(length=80), nullable=True),
        sa.Column('cilindrada', sa.String(length=50), nullable=True),
        sa.Column('anio', sa.String(length=10), nullable=True),
        sa.Column('has_patente', sa.Boolean(), nullable=True),
        sa.Column('has_casco', sa.Boolean(), nullable=True),
        sa.Column('has_seguro', sa.Boolean(), nullable=True),
        sa.Column('tipo_seguro', sa.String(length=120), nullable=True),
        sa.Column('carnet_conducir', sa.String(length=120), nullable=True),
        sa.Column('ultimo_servicio', sa.String(length=120), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(['driver_profile_id'], ['driver_profiles.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_vehicles_driver_profile_id', 'vehicles', ['driver_profile_id'])

    # ── merge defensivo de drivers legacy ──
    driver_map = _driver_user_map(bind) if _online() else {}

    # ── trips: comision + FK driver→users ──
    op.alter_column('trips', 'fare', new_column_name='total_fare')
    op.add_column(
        'trips',
        sa.Column('platform_fee', sa.Numeric(12, 2), nullable=False, server_default='0'),
    )
    op.add_column('trips', sa.Column('platform_fee_rate', sa.Numeric(5, 4), nullable=True))
    op.add_column('trips', sa.Column('driver_earnings', sa.Numeric(12, 2), nullable=True))
    op.add_column(
        'trips',
        sa.Column('currency', sa.String(length=3), nullable=False, server_default='ARS'),
    )
    op.add_column('trips', sa.Column('vehicle_id', sa.Integer(), nullable=True))
    if _online():
        bind.execute(
            sa.text('UPDATE trips SET driver_earnings = total_fare WHERE driver_earnings IS NULL')
        )
    _set_nullable('trips', 'driver_earnings', sa.Numeric(12, 2), False)
    _create_fk(
        'fk_trips_vehicle_id_vehicles', 'trips', 'vehicles', ['vehicle_id'], ['id'],
    )

    if driver_map:
        for old_did, new_uid in driver_map.items():
            bind.execute(
                sa.text('UPDATE trips SET driver_id = :u WHERE driver_id = :d'),
                {'u': new_uid, 'd': old_did},
            )
    _drop_fk('trips', 'driver_id')
    _create_fk('fk_trips_driver_id_users', 'trips', 'users', ['driver_id'], ['id'])

    _create_check(
        'chk_trip_money', 'trips',
        'total_fare >= 0 AND platform_fee >= 0 AND driver_earnings >= 0 '
        'AND total_fare = platform_fee + driver_earnings '
        'AND (platform_fee_rate IS NULL OR platform_fee_rate >= 0)',
    )
    _create_check(
        'chk_trip_status', 'trips',
        "status IN ('requested', 'accepted', 'ongoing', 'completed', 'cancelled')",
    )
    _create_check(
        'chk_trip_vehicle_type', 'trips', "vehicle_type IN ('moto', 'auto')",
    )
    op.drop_index('ix_trips_status', table_name='trips')
    op.drop_index('ix_trips_requested_at', table_name='trips')
    op.create_index('ix_trips_status_requested', 'trips', ['status', 'requested_at'])
    op.create_index('ix_trips_passenger_recent', 'trips', ['passenger_id', 'requested_at'])
    op.create_index('ix_trips_driver_recent', 'trips', ['driver_id', 'requested_at'])

    # ── reviews: 2 FKs + role ──
    if driver_map:
        for old_did, new_uid in driver_map.items():
            bind.execute(
                sa.text('UPDATE reviews SET from_user_id = :u WHERE from_driver_id = :d'),
                {'u': new_uid, 'd': old_did},
            )
            bind.execute(
                sa.text('UPDATE reviews SET to_user_id = :u WHERE to_driver_id = :d'),
                {'u': new_uid, 'd': old_did},
            )
    if _online():
        bind.execute(
            sa.text(
                "UPDATE reviews SET role = 'driver' WHERE role IS NULL OR role = ''"
            )
        )
    _set_nullable('reviews', 'role', sa.String(10), False)
    _set_nullable('reviews', 'from_user_id', sa.Integer(), False)
    _set_nullable('reviews', 'to_user_id', sa.Integer(), False)
    _drop_fk('reviews', 'from_driver_id')
    _drop_fk('reviews', 'to_driver_id')
    _drop_column('reviews', 'from_driver_id')
    _drop_column('reviews', 'to_driver_id')
    _create_check('chk_review_rating', 'reviews', 'rating >= 1 AND rating <= 5')
    _create_check(
        'chk_review_role', 'reviews', "role IN ('driver', 'passenger')",
    )
    _create_unique(
        'uq_review_once', 'reviews', ['trip_id', 'from_user_id', 'to_user_id'],
    )

    # ── wallet_transactions: user_id obligatorio + counterparty ──
    # driver_id se reemplaza por counterparty_id: se agrega la columna nueva,
    # se backfillea el mapeo legacy y luego se elimina driver_id. Un RENAME
    # colisionaria con la columna ya creada en PostgreSQL (chk: DuplicateColumn).
    op.add_column(
        'wallet_transactions',
        sa.Column('counterparty_id', sa.Integer(), nullable=True),
    )
    if driver_map:
        for old_did, new_uid in driver_map.items():
            bind.execute(
                sa.text(
                    'UPDATE wallet_transactions SET user_id = :u '
                    'WHERE driver_id = :d AND user_id IS NULL'
                ),
                {'u': new_uid, 'd': old_did},
            )
            bind.execute(
                sa.text(
                    'UPDATE wallet_transactions SET counterparty_id = :u '
                    'WHERE driver_id = :d AND user_id IS NOT NULL'
                ),
                {'u': new_uid, 'd': old_did},
            )
    _drop_fk('wallet_transactions', 'driver_id')
    op.drop_index('ix_wallet_transactions_driver_id', table_name='wallet_transactions')
    _drop_column('wallet_transactions', 'driver_id')
    if _online():
        bind.execute(
            sa.text(
                'UPDATE wallet_transactions SET user_id = counterparty_id '
                'WHERE user_id IS NULL AND counterparty_id IS NOT NULL'
            )
        )
    _set_nullable('wallet_transactions', 'user_id', sa.Integer(), False)
    _create_fk(
        'fk_wallet_transactions_counterparty_id_users',
        'wallet_transactions', 'users', ['counterparty_id'], ['id'],
    )
    op.create_index('ix_wallet_user_recent', 'wallet_transactions', ['user_id', 'created_at'])

    # ── driver_payment_methods → driver_profile_id ──
    # Mismo patrón que wallet: ADD + backfill + DROP (el RENAME colisiona en PG).
    op.add_column(
        'driver_payment_methods',
        sa.Column('driver_profile_id', sa.Integer(), nullable=True),
    )
    if driver_map:
        pid_by_did = {}
        for old_did, new_uid in driver_map.items():
            row = bind.execute(
                sa.text('SELECT id FROM driver_profiles WHERE user_id = :u'),
                {'u': new_uid},
            ).fetchone()
            if row:
                pid_by_did[old_did] = row[0]
        for old_did, pid in pid_by_did.items():
            bind.execute(
                sa.text(
                    'UPDATE driver_payment_methods SET driver_profile_id = :p '
                    'WHERE driver_id = :d'
                ),
                {'p': pid, 'd': old_did},
            )
    _drop_fk('driver_payment_methods', 'driver_id')
    _drop_column('driver_payment_methods', 'driver_id')
    if _online():
        # columnas sin perfil valido se descartan (solo afecta datos legacy invalidos)
        bind.execute(
            sa.text(
                'DELETE FROM driver_payment_methods WHERE driver_profile_id NOT IN '
                '(SELECT id FROM driver_profiles)'
            )
        )
    _set_nullable(
        'driver_payment_methods', 'driver_profile_id', sa.Integer(), False,
    )
    _create_fk(
        'fk_driver_payment_methods_driver_profile_id_driver_profiles',
        'driver_payment_methods', 'driver_profiles', ['driver_profile_id'], ['id'],
    )
    op.create_index(
        'ix_driver_payment_methods_driver_profile_id',
        'driver_payment_methods', ['driver_profile_id'],
    )

    # ── refresh_tokens / email_verifications: FK users, sin user_type ──
    if driver_map:
        for old_did, new_uid in driver_map.items():
            bind.execute(
                sa.text(
                    'UPDATE refresh_tokens SET user_id = :u '
                    "WHERE user_type = 'driver' AND user_id = :d"
                ),
                {'u': new_uid, 'd': old_did},
            )
            bind.execute(
                sa.text(
                    'UPDATE email_verifications SET user_id = :u '
                    "WHERE user_type = 'driver' AND user_id = :d"
                ),
                {'u': new_uid, 'd': old_did},
            )
    op.drop_column('refresh_tokens', 'user_type')
    op.drop_column('email_verifications', 'user_type')
    _create_fk(
        'fk_refresh_tokens_user_id_users', 'refresh_tokens', 'users',
        ['user_id'], ['id'], ondelete='CASCADE',
    )
    _create_fk(
        'fk_email_verifications_user_id_users', 'email_verifications',
        'users', ['user_id'], ['id'], ondelete='CASCADE',
    )

    # la tabla legacy 'drivers' ya no forma parte del esquema unificado:
    # se elimina si existe (el merge defensivo ya consolido sus datos y
    # ninguna FK la referencia). El downgrade NO la recrea con datos.
    if _online():
        if _table_has(bind, 'drivers'):
            op.drop_table('drivers')
    else:
        op.execute('DROP TABLE IF EXISTS drivers')


# ───────────────────────── downgrade ─────────────────────────

def downgrade():
    bind = _bind()
    driver_map = {}

    # trips
    _drop_named('check', 'chk_trip_money', 'trips')
    _drop_named('check', 'chk_trip_status', 'trips')
    _drop_named('check', 'chk_trip_vehicle_type', 'trips')
    op.drop_index('ix_trips_status_requested', table_name='trips')
    op.drop_index('ix_trips_passenger_recent', table_name='trips')
    op.drop_index('ix_trips_driver_recent', table_name='trips')
    op.create_index('ix_trips_status', 'trips', ['status'], unique=False)
    op.create_index('ix_trips_requested_at', 'trips', ['requested_at'], unique=False)
    _drop_named('foreignkey', 'fk_trips_vehicle_id_vehicles', 'trips')
    _drop_named('foreignkey', 'fk_trips_driver_id_users', 'trips')
    op.drop_column('trips', 'vehicle_id')
    op.drop_column('trips', 'currency')
    op.drop_column('trips', 'driver_earnings')
    op.drop_column('trips', 'platform_fee_rate')
    op.drop_column('trips', 'platform_fee')
    op.alter_column('trips', 'total_fare', new_column_name='fare')

    # reviews
    _drop_named('unique', 'uq_review_once', 'reviews')
    _drop_named('check', 'chk_review_rating', 'reviews')
    _drop_named('check', 'chk_review_role', 'reviews')
    _set_nullable('reviews', 'from_user_id', sa.Integer(), True)
    _set_nullable('reviews', 'to_user_id', sa.Integer(), True)
    op.add_column('reviews', sa.Column('from_driver_id', sa.Integer(), nullable=True))
    op.add_column('reviews', sa.Column('to_driver_id', sa.Integer(), nullable=True))

    # wallet: se restaura driver_id como columna propia (espejo del upgrade:
    # ADD + copia best-effort de counterparty + DROP de counterparty_id)
    op.drop_index('ix_wallet_user_recent', table_name='wallet_transactions')
    _drop_named(
        'foreignkey', 'fk_wallet_transactions_counterparty_id_users',
        'wallet_transactions',
    )
    _set_nullable('wallet_transactions', 'user_id', sa.Integer(), True)
    op.add_column('wallet_transactions', sa.Column('driver_id', sa.Integer(), nullable=True))
    if _online():
        bind.execute(
            sa.text(
                'UPDATE wallet_transactions SET driver_id = counterparty_id '
                'WHERE counterparty_id IS NOT NULL'
            )
        )
    op.create_index('ix_wallet_transactions_driver_id', 'wallet_transactions', ['driver_id'])
    _drop_column('wallet_transactions', 'counterparty_id')

    # driver_payment_methods
    op.drop_index('ix_driver_payment_methods_driver_profile_id', table_name='driver_payment_methods')
    _drop_named(
        'foreignkey', 'fk_driver_payment_methods_driver_profile_id_driver_profiles',
        'driver_payment_methods',
    )
    op.alter_column(
        'driver_payment_methods', 'driver_profile_id', new_column_name='driver_id',
    )
    if _table_has(_bind(), 'drivers'):
        op.create_foreign_key('driver_payment_methods_driver_id_fkey', 'driver_payment_methods', 'drivers', ['driver_id'], ['id'])

    # tokens
    _drop_named('foreignkey', 'fk_refresh_tokens_user_id_users', 'refresh_tokens')
    _drop_named('foreignkey', 'fk_email_verifications_user_id_users', 'email_verifications')
    op.add_column('refresh_tokens', sa.Column('user_type', sa.String(length=10), nullable=False, server_default='user'))
    op.add_column('email_verifications', sa.Column('user_type', sa.String(length=10), nullable=False, server_default='user'))

    # users
    op.drop_index('ix_users_email_lower', table_name='users')
    _drop_named('check', 'chk_users_role', 'users')
    op.drop_column('users', 'role')

    # tablas nuevas
    op.drop_table('vehicles')
    op.drop_table('driver_profiles')

    bind = _bind()  # reconectar por si acaso
    del bind
