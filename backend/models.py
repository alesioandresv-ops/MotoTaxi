from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(30))
    profile_picture = db.Column(db.String(255), nullable=True)
    email_verified = db.Column(db.Boolean, default=False)
    balance = db.Column(db.Numeric(12, 2), default=0.0)
    rating_avg = db.Column(db.Float, default=5.0)
    rating_count = db.Column(db.Integer, default=0)
    accepted_guidelines = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Driver(db.Model):
    __tablename__ = 'drivers'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(30), nullable=False)
    profile_picture = db.Column(db.String(255), nullable=False)
    email_verified = db.Column(db.Boolean, default=False)
    is_online = db.Column(db.Boolean, default=False)
    is_ocupado = db.Column(db.Boolean, default=False)
    lat = db.Column(db.Float, nullable=True)
    lng = db.Column(db.Float, nullable=True)
    last_location_update = db.Column(db.DateTime, nullable=True)
    rating_avg = db.Column(db.Float, default=5.0)
    rating_count = db.Column(db.Integer, default=0)
    accepted_guidelines = db.Column(db.Boolean, default=False)
    is_verified = db.Column(db.Boolean, default=False)
    vehicle_type = db.Column(db.String(10), nullable=False, default='moto')
    # Moto fields
    placa = db.Column(db.String(50), nullable=False)
    moto_marca = db.Column(db.String(120), nullable=False)
    moto_modelo = db.Column(db.String(120), nullable=False)
    moto_color = db.Column(db.String(80), nullable=False)
    moto_cilindrada = db.Column(db.String(50), nullable=False)
    tiene_patente = db.Column(db.Boolean, nullable=False, default=False)
    tiene_casco = db.Column(db.Boolean, nullable=False, default=False)
    seguro_moto = db.Column(db.Boolean, nullable=False, default=False)
    tipo_seguro = db.Column(db.String(120), nullable=False)
    carnet_conducir = db.Column(db.String(120), nullable=False)
    ultimo_servicio = db.Column(db.String(120), nullable=False)
    # Auto fields
    placa_auto = db.Column(db.String(50), nullable=True)
    auto_marca = db.Column(db.String(120), nullable=True)
    auto_modelo = db.Column(db.String(120), nullable=True)
    auto_color = db.Column(db.String(80), nullable=True)
    auto_año = db.Column(db.String(10), nullable=True)
    tiene_patente_auto = db.Column(db.Boolean, default=False)
    seguro_auto = db.Column(db.Boolean, default=False)
    tipo_seguro_auto = db.Column(db.String(120), nullable=True)
    carnet_conducir_auto = db.Column(db.String(120), nullable=True)
    ultimo_servicio_auto = db.Column(db.String(120), nullable=True)
    accepted_payments = db.Column(db.String(500), nullable=True, default='["efectivo"]')
    mercadopago_qr = db.Column(db.String(500), nullable=True)
    balance = db.Column(db.Numeric(12, 2), default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Trip(db.Model):
    __tablename__ = 'trips'
    id = db.Column(db.Integer, primary_key=True)
    passenger_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    driver_id = db.Column(db.Integer, db.ForeignKey('drivers.id'), nullable=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True)
    vehicle_type = db.Column(db.String(10), nullable=False, default='moto')
    pickup_address = db.Column(db.String(255), nullable=False)
    dropoff_address = db.Column(db.String(255), nullable=False)
    pickup_lat = db.Column(db.Float, nullable=True)
    pickup_lng = db.Column(db.Float, nullable=True)
    dropoff_lat = db.Column(db.Float, nullable=True)
    dropoff_lng = db.Column(db.Float, nullable=True)
    distance_km = db.Column(db.Float, nullable=True)
    duration_min = db.Column(db.Integer, nullable=True)
    fare = db.Column(db.Numeric(12, 2), nullable=False)
    status = db.Column(db.String(50), nullable=False, default='requested', index=True)
    requested_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    cancelled_by = db.Column(db.String(20), nullable=True)
    payment_method = db.Column(db.String(50), nullable=True)

    passenger = db.relationship('User', backref='trips')
    driver = db.relationship('Driver', backref='assigned_trips')
    company = db.relationship('Company', backref='trips')
    reviews = db.relationship('Review', backref='trip', lazy=True)

class Review(db.Model):
    __tablename__ = 'reviews'
    id = db.Column(db.Integer, primary_key=True)
    trip_id = db.Column(db.Integer, db.ForeignKey('trips.id'), nullable=False)
    from_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    from_driver_id = db.Column(db.Integer, db.ForeignKey('drivers.id'), nullable=True)
    to_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    to_driver_id = db.Column(db.Integer, db.ForeignKey('drivers.id'), nullable=True)
    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text, nullable=True)
    role = db.Column(db.String(10), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Company(db.Model):
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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    members = db.relationship('CompanyMember', backref='company', lazy=True)

class CompanyMember(db.Model):
    __tablename__ = 'company_members'
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='employee')
    invited_at = db.Column(db.DateTime, default=datetime.utcnow)
    joined_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship('User', backref='company_memberships')

class DriverPaymentMethod(db.Model):
    __tablename__ = 'driver_payment_methods'
    id = db.Column(db.Integer, primary_key=True)
    driver_id = db.Column(db.Integer, db.ForeignKey('drivers.id'), nullable=False)
    type = db.Column(db.String(30), nullable=False)
    details = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=True)

    driver = db.relationship('Driver', backref='payment_methods')

class PassengerPaymentConfig(db.Model):
    __tablename__ = 'passenger_payment_configs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    type = db.Column(db.String(30), nullable=False)
    details = db.Column(db.Text, nullable=True)
    is_default = db.Column(db.Boolean, default=False)

    user = db.relationship('User', backref='payment_configs')

class FavoriteAddress(db.Model):
    __tablename__ = 'favorite_addresses'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    pickup_address = db.Column(db.String(255), nullable=False)
    dropoff_address = db.Column(db.String(255), nullable=False)
    count = db.Column(db.Integer, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='favorite_addresses')

class WalletTransaction(db.Model):
    __tablename__ = 'wallet_transactions'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    driver_id = db.Column(db.Integer, db.ForeignKey('drivers.id'), nullable=True, index=True)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    type = db.Column(db.String(30), nullable=False)
    trip_id = db.Column(db.Integer, db.ForeignKey('trips.id'), nullable=True)
    reference = db.Column(db.String(200), nullable=True)
    status = db.Column(db.String(20), default='completed')
    description = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='wallet_transactions')
    driver = db.relationship('Driver', backref='wallet_transactions')
    trip = db.relationship('Trip', backref='wallet_transactions')

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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    confirmed_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship('User', backref='topup_requests')
