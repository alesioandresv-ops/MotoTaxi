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
    rating_avg = db.Column(db.Float, default=5.0)
    rating_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Driver(db.Model):
    __tablename__ = 'drivers'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(30), nullable=False)
    profile_picture = db.Column(db.String(255), nullable=True)
    email_verified = db.Column(db.Boolean, default=False)
    is_online = db.Column(db.Boolean, default=False)
    is_ocupado = db.Column(db.Boolean, default=False)
    lat = db.Column(db.Float, nullable=True)
    lng = db.Column(db.Float, nullable=True)
    last_location_update = db.Column(db.DateTime, nullable=True)
    rating_avg = db.Column(db.Float, default=5.0)
    rating_count = db.Column(db.Integer, default=0)
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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Trip(db.Model):
    __tablename__ = 'trips'
    id = db.Column(db.Integer, primary_key=True)
    passenger_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    driver_id = db.Column(db.Integer, db.ForeignKey('drivers.id'), nullable=True)
    pickup_address = db.Column(db.String(255), nullable=False)
    dropoff_address = db.Column(db.String(255), nullable=False)
    pickup_lat = db.Column(db.Float, nullable=True)
    pickup_lng = db.Column(db.Float, nullable=True)
    dropoff_lat = db.Column(db.Float, nullable=True)
    dropoff_lng = db.Column(db.Float, nullable=True)
    distance_km = db.Column(db.Float, nullable=True)
    duration_min = db.Column(db.Integer, nullable=True)
    fare = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(50), nullable=False, default='requested')
    requested_at = db.Column(db.DateTime, default=datetime.utcnow)
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    cancelled_by = db.Column(db.String(20), nullable=True)

    passenger = db.relationship('User', backref='trips')
    driver = db.relationship('Driver', backref='assigned_trips')
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

class DriverSession(db.Model):
    __tablename__ = 'driver_sessions'
    id = db.Column(db.Integer, primary_key=True)
    driver_id = db.Column(db.Integer, db.ForeignKey('drivers.id'), nullable=False)
    is_online = db.Column(db.Boolean, default=False)
    lat = db.Column(db.Float, nullable=True)
    lng = db.Column(db.Float, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)
