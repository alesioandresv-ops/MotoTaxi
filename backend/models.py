"""Modelos de datos de VAN — esquema unificado (PostgreSQL objetivo).

Identidad única: `users` (role: passenger | driver | both | admin | company).
Conductores: `driver_profiles` (1:1) + `vehicles` (1:N).
Money: siempre Numeric/Decimal, nunca float (ver services/fare.py).
"""
from datetime import datetime

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import CheckConstraint, Index, UniqueConstraint, func
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.sql import column

db = SQLAlchemy()

ROLE_PASSENGER = 'passenger'
ROLE_DRIVER = 'driver'
ROLE_BOTH = 'both'
ROLE_ADMIN = 'admin'
ROLE_COMPANY = 'company'

ROLES = (ROLE_PASSENGER, ROLE_DRIVER, ROLE_BOTH, ROLE_ADMIN, ROLE_COMPANY)

MODE_PASSENGER = 'passenger'
MODE_DRIVER = 'driver'

TRIP_STATUSES = ('requested', 'accepted', 'ongoing', 'completed', 'cancelled')
VEHICLE_TYPES = ('moto', 'auto')

DRIVER_STATUS_PENDING = 'pending'
DRIVER_STATUS_APPROVED = 'approved'
DRIVER_STATUS_REJECTED = 'rejected'
DRIVER_STATUSES = (DRIVER_STATUS_PENDING, DRIVER_STATUS_APPROVED, DRIVER_STATUS_REJECTED)


def _now():
    return datetime.utcnow()


class User(db.Model):
    """Identidad única: pasajero, conductor, ambos, admin o empresa."""
    __tablename__ = 'users'
    __table_args__ = (
        Index('ix_users_email_lower', func.lower(column('email')), unique=True),
        CheckConstraint(f"role IN {ROLES}", name='chk_users_role'),
    )
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    password = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(30))
    profile_picture = db.Column(db.String(255), nullable=True)
    email_verified = db.Column(db.Boolean, default=False)
    role = db.Column(db.String(10), nullable=False, default=ROLE_PASSENGER)
    balance = db.Column(db.Numeric(12, 2), default=0.0)
    rating_avg = db.Column(db.Float, default=5.0)
    rating_count = db.Column(db.Integer, default=0)
    accepted_guidelines = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=_now)

    driver_profile = db.relationship(
        'DriverProfile', backref='user', uselist=False,
        cascade='all, delete-orphan', lazy='joined',
    )
    trips_as_passenger = db.relationship(
        'Trip', foreign_keys='Trip.passenger_id', backref='passenger', lazy=True,
    )
    trips_as_driver = db.relationship(
        'Trip', foreign_keys='Trip.driver_id', backref='driver', lazy=True,
    )
    wallet_transactions = db.relationship(
        'WalletTransaction', foreign_keys='WalletTransaction.user_id',
        backref='user', lazy=True,
    )
    topup_requests = db.relationship('TopUpRequest', backref='user', lazy=True)
    payment_configs = db.relationship('PassengerPaymentConfig', backref='user', lazy=True)
    favorite_addresses = db.relationship('FavoriteAddress', backref='user', lazy=True)
    company_memberships = db.relationship('CompanyMember', backref='user', lazy=True)

    @property
    def is_driver(self):
        return self.role in (ROLE_DRIVER, ROLE_BOTH) and self.driver_profile is not None


class DriverProfile(db.Model):
    """Estado y verificación del conductor. 1:1 con users.

    status es la ÚNICA fuente de autorización del conductor
    (pending | approved | rejected). `is_verified` (legacy) queda solo como
    alias de presentación para templates vía driver_view(); no autoriza.
    El DDL de esta columna para PostgreSQL llega con la migración 0003
    (backfill: existentes → approved; nuevos → pending).
    """
    __tablename__ = 'driver_profiles'
    __table_args__ = (
        Index('ix_driver_profiles_online_free', 'is_online', 'is_busy'),
        CheckConstraint(f"status IN {DRIVER_STATUSES}", name='chk_driver_profile_status'),
    )
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False, unique=True,
    )
    status = db.Column(
        db.String(10), nullable=False, default=DRIVER_STATUS_PENDING,
        server_default=DRIVER_STATUS_PENDING,
    )
    is_online = db.Column(db.Boolean, default=False)
    is_busy = db.Column(db.Boolean, default=False)
    lat = db.Column(db.Float, nullable=True)
    lng = db.Column(db.Float, nullable=True)
    last_location_update = db.Column(db.DateTime, nullable=True)
    is_verified = db.Column(db.Boolean, default=False)
    accepted_payments = db.Column(db.String(500), nullable=True, default='["efectivo"]')
    mercadopago_qr = db.Column(db.String(500), nullable=True)
    carnet_conducir = db.Column(db.String(120), nullable=True)
    tipo_seguro = db.Column(db.String(120), nullable=True)
    ultimo_servicio = db.Column(db.String(120), nullable=True)

    vehicles = db.relationship(
        'Vehicle', backref='profile', lazy=True, cascade='all, delete-orphan',
    )
    payment_methods = db.relationship(
        'DriverPaymentMethod', backref='driver_profile', lazy=True,
        cascade='all, delete-orphan',
    )

    @property
    def active_vehicle(self):
        for v in self.vehicles:
            if v.is_active:
                return v
        return self.vehicles[0] if self.vehicles else None


class Vehicle(db.Model):
    """Vehículo de un conductor (moto o auto). Un conductor puede tener varios."""
    __tablename__ = 'vehicles'
    id = db.Column(db.Integer, primary_key=True)
    driver_profile_id = db.Column(
        db.Integer, db.ForeignKey('driver_profiles.id', ondelete='CASCADE'),
        nullable=False, index=True,
    )
    type = db.Column(db.String(10), nullable=False, default='moto')
    placa = db.Column(db.String(50), nullable=True)
    marca = db.Column(db.String(120), nullable=True)
    modelo = db.Column(db.String(120), nullable=True)
    color = db.Column(db.String(80), nullable=True)
    cilindrada = db.Column(db.String(50), nullable=True)
    anio = db.Column(db.String(10), nullable=True)
    has_patente = db.Column(db.Boolean, default=False)
    has_casco = db.Column(db.Boolean, default=False)
    has_seguro = db.Column(db.Boolean, default=False)
    tipo_seguro = db.Column(db.String(120), nullable=True)
    carnet_conducir = db.Column(db.String(120), nullable=True)
    ultimo_servicio = db.Column(db.String(120), nullable=True)
    is_active = db.Column(db.Boolean, default=True)


class Trip(db.Model):
    """Viaje. Money: total_fare = platform_fee + driver_earnings (CHECK en PG).
    platform_fee_rate es snapshot del porcentaje aplicado; NULL = sin comisión.
    currency es snapshot ISO 4217 (DEFAULT_CURRENCY env al crear)."""
    __tablename__ = 'trips'
    __table_args__ = (
        CheckConstraint(
            'total_fare >= 0 AND platform_fee >= 0 AND driver_earnings >= 0 '
            'AND total_fare = platform_fee + driver_earnings '
            'AND (platform_fee_rate IS NULL OR platform_fee_rate >= 0)',
            name='chk_trip_money',
        ),
        CheckConstraint(f"status IN {TRIP_STATUSES}", name='chk_trip_status'),
        CheckConstraint(f"vehicle_type IN {VEHICLE_TYPES}", name='chk_trip_vehicle_type'),
        Index('ix_trips_status_requested', 'status', 'requested_at'),
        Index('ix_trips_passenger_recent', 'passenger_id', 'requested_at'),
        Index('ix_trips_driver_recent', 'driver_id', 'requested_at'),
    )
    id = db.Column(db.Integer, primary_key=True)
    passenger_id = db.Column(
        db.Integer, db.ForeignKey('users.id'), nullable=False,
    )
    driver_id = db.Column(
        db.Integer, db.ForeignKey('users.id'), nullable=True,
    )
    vehicle_id = db.Column(
        db.Integer, db.ForeignKey('vehicles.id'), nullable=True,
    )
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True)
    vehicle_type = db.Column(db.String(10), nullable=False, default='moto')
    pickup_address = db.Column(db.String(255), nullable=False)
    dropoff_address = db.Column(db.String(255), nullable=False)
    pickup_lat = db.Column(db.Float, nullable=True)
    pickup_lng = db.Column(db.Float, nullable=True)
    dropoff_lat = db.Column(db.Float, nullable=True)
    dropoff_lng = db.Column(db.Float, nullable=True)
    distance_km = db.Column(db.Numeric(8, 2), nullable=True)
    duration_min = db.Column(db.Integer, nullable=True)
    total_fare = db.Column(db.Numeric(12, 2), nullable=False)
    platform_fee = db.Column(db.Numeric(12, 2), nullable=False, default=0.0)
    platform_fee_rate = db.Column(db.Numeric(5, 4), nullable=True)
    driver_earnings = db.Column(db.Numeric(12, 2), nullable=False)
    currency = db.Column(db.String(3), nullable=False, default='ARS')
    status = db.Column(db.String(20), nullable=False, default='requested')
    requested_at = db.Column(db.DateTime, default=_now)
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    cancelled_by = db.Column(db.String(20), nullable=True)
    payment_method = db.Column(db.String(50), nullable=True)

    vehicle = db.relationship('Vehicle', backref='trips')
    company = db.relationship('Company', backref='trips')
    reviews = db.relationship('Review', backref='trip', lazy=True)

    @hybrid_property
    def fare(self):
        """Compat web: trip.fare == total_fare."""
        return self.total_fare

    @fare.setter
    def fare(self, value):
        self.total_fare = value


class Review(db.Model):
    """Calificación cruzada. role = el rol del destinatario (driver|passenger)."""
    __tablename__ = 'reviews'
    __table_args__ = (
        UniqueConstraint('trip_id', 'from_user_id', 'to_user_id', name='uq_review_once'),
        CheckConstraint('rating >= 1 AND rating <= 5', name='chk_review_rating'),
        CheckConstraint("role IN ('driver', 'passenger')", name='chk_review_role'),
    )
    id = db.Column(db.Integer, primary_key=True)
    trip_id = db.Column(db.Integer, db.ForeignKey('trips.id'), nullable=False)
    from_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    to_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text, nullable=True)
    role = db.Column(db.String(10), nullable=False)
    created_at = db.Column(db.DateTime, default=_now)

    from_user = db.relationship('User', foreign_keys=[from_user_id])
    to_user = db.relationship('User', foreign_keys=[to_user_id])


class Company(db.Model):
    """Empresa B2B (suscripción). Auth separada (web portal)."""
    __tablename__ = 'companies'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(30))
    plan = db.Column(db.String(20), nullable=False, default='basic')
    status = db.Column(db.String(20), nullable=False, default='trial')
    subscription_start = db.Column(db.DateTime, nullable=True)
    subscription_end = db.Column(db.DateTime, nullable=True)
    payment_method = db.Column(db.String(50), nullable=True)
    payment_reference = db.Column(db.String(255), nullable=True)
    max_employees = db.Column(db.Integer, default=15)
    created_at = db.Column(db.DateTime, default=_now)

    members = db.relationship('CompanyMember', backref='company', lazy=True)


class CompanyMember(db.Model):
    __tablename__ = 'company_members'
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(
        db.Integer, db.ForeignKey('companies.id'), nullable=False,
    )
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='employee')
    invited_at = db.Column(db.DateTime, default=_now)
    joined_at = db.Column(db.DateTime, nullable=True)


class DriverPaymentMethod(db.Model):
    """Método de cobro del conductor (details cifrados con Fernet)."""
    __tablename__ = 'driver_payment_methods'
    id = db.Column(db.Integer, primary_key=True)
    driver_profile_id = db.Column(
        db.Integer, db.ForeignKey('driver_profiles.id', ondelete='CASCADE'),
        nullable=False, index=True,
    )
    type = db.Column(db.String(30), nullable=False)
    details = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=True)


class PassengerPaymentConfig(db.Model):
    __tablename__ = 'passenger_payment_configs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    type = db.Column(db.String(30), nullable=False)
    details = db.Column(db.Text, nullable=True)
    is_default = db.Column(db.Boolean, default=False)


class FavoriteAddress(db.Model):
    __tablename__ = 'favorite_addresses'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    pickup_address = db.Column(db.String(255), nullable=False)
    dropoff_address = db.Column(db.String(255), nullable=False)
    count = db.Column(db.Integer, default=1)
    created_at = db.Column(db.DateTime, default=_now)


class WalletTransaction(db.Model):
    """Movimiento de billetera. user_id = dueño; counterparty_id = contraparte.
    amount es con signo (negativo = debita, positivo = acredita)."""
    __tablename__ = 'wallet_transactions'
    __table_args__ = (
        Index('ix_wallet_user_recent', 'user_id', 'created_at'),
    )
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    counterparty_id = db.Column(
        db.Integer, db.ForeignKey('users.id'), nullable=True,
    )
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    type = db.Column(db.String(30), nullable=False)
    trip_id = db.Column(db.Integer, db.ForeignKey('trips.id'), nullable=True)
    reference = db.Column(db.String(200), nullable=True)
    status = db.Column(db.String(20), default='completed')
    description = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=_now)

    trip = db.relationship('Trip', backref='wallet_transactions')
    counterparty = db.relationship('User', foreign_keys=[counterparty_id])


class TopUpRequest(db.Model):
    __tablename__ = 'topup_requests'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    method = db.Column(db.String(30), nullable=False)
    voucher_url = db.Column(db.String(500), nullable=True)
    mp_payment_id = db.Column(db.String(100), nullable=True)
    status = db.Column(db.String(20), default='pending')
    admin_note = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=_now)
    confirmed_at = db.Column(db.DateTime, nullable=True)


class RefreshToken(db.Model):
    """Refresh tokens de /api/v1. user_id → users (cualquier role)."""
    __tablename__ = 'refresh_tokens'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False, index=True,
    )
    token_hash = db.Column(db.String(64), unique=True, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=_now)
    revoked_at = db.Column(db.DateTime, nullable=True)
    replaced_by_id = db.Column(db.Integer, nullable=True)
    user_agent = db.Column(db.String(255), nullable=True)


class EmailVerification(db.Model):
    __tablename__ = 'email_verifications'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False, index=True,
    )
    email = db.Column(db.String(120), nullable=False)
    code_hash = db.Column(db.String(64), nullable=False)
    attempts = db.Column(db.Integer, default=0)
    expires_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=_now)
    verified_at = db.Column(db.DateTime, nullable=True)
