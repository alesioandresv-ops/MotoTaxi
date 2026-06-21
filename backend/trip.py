from backend.models import db
from datetime import datetime

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
