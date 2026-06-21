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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Driver(db.Model):
    __tablename__ = 'drivers'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(30), nullable=False)
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
    fare = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(50), nullable=False, default='requested')
    requested_at = db.Column(db.DateTime, default=datetime.utcnow)

    passenger = db.relationship('User', backref='trips')
    driver = db.relationship('Driver', backref='assigned_trips')
