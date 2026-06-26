from flask import Blueprint, render_template, session, request, redirect, url_for, flash, jsonify
from .models import db, User, Driver, Trip
import random

main_bp = Blueprint('main', __name__)


def calculate_fare(pickup, dropoff):
    base = 5.0
    distance = max(1, abs(len(pickup) - len(dropoff)))
    estimate = base + distance * 0.75
    return round(estimate, 2)


@main_bp.route('/')
def index():
    return render_template('index.html')


@main_bp.route('/dashboard')
def dashboard():
    if 'user_id' in session:
        user_name = session.get('user_name')
        passenger = User.query.get(session['user_id'])
        current_trip = Trip.query.filter(Trip.passenger_id == passenger.id, Trip.status.in_(['requested', 'accepted', 'ongoing'])).order_by(Trip.requested_at.desc()).first()
        history_trips = Trip.query.filter_by(passenger_id=passenger.id).order_by(Trip.requested_at.desc()).limit(10).all()
        driver_info = current_trip.driver if current_trip and current_trip.driver else None
        return render_template('dashboard.html', user_type='passenger', user_name=user_name, current_trip=current_trip, history_trips=history_trips, driver_info=driver_info)

    if 'driver_id' in session:
        user_name = session.get('driver_name')
        driver = Driver.query.get(session['driver_id'])
        available_trips = Trip.query.filter_by(status='requested').order_by(Trip.requested_at.asc()).all()
        active_trip = Trip.query.filter(Trip.driver_id == driver.id, Trip.status.in_(['accepted', 'ongoing'])).order_by(Trip.requested_at.desc()).first()
        completed_trips = Trip.query.filter_by(driver_id=driver.id, status='completed').order_by(Trip.requested_at.desc()).limit(10).all()
        return render_template('dashboard.html', user_type='driver', user_name=user_name, driver=driver, available_trips=available_trips, active_trip=active_trip, completed_trips=completed_trips)

    return redirect(url_for('auth.login'))


@main_bp.route('/passenger/request', methods=['POST'])
def passenger_request():
    if 'user_id' not in session:
        flash('Debes iniciar sesión como pasajero', 'danger')
        return redirect(url_for('auth.login'))

    pickup = request.form.get('pickup_address')
    dropoff = request.form.get('dropoff_address')
    if not pickup or not dropoff:
        flash('Completa el origen y destino', 'danger')
        return redirect(url_for('main.dashboard'))

    fare = calculate_fare(pickup, dropoff)
    trip = Trip(
        passenger_id=session['user_id'],
        pickup_address=pickup,
        dropoff_address=dropoff,
        fare=fare,
        status='requested'
    )
    db.session.add(trip)
    db.session.commit()
    flash(f'Viaje solicitado (${fare}). Esperando conductor.', 'success')
    return redirect(url_for('main.dashboard'))


@main_bp.route('/driver/accept/<int:trip_id>')
def driver_accept(trip_id):
    if 'driver_id' not in session:
        flash('Debes iniciar sesión como conductor', 'danger')
        return redirect(url_for('auth.login'))

    trip = Trip.query.get_or_404(trip_id)
    if trip.status != 'requested':
        flash('Este viaje ya no está disponible', 'warning')
        return redirect(url_for('main.dashboard'))

    trip.driver_id = session['driver_id']
    trip.status = 'accepted'
    db.session.commit()
    flash('Has aceptado el viaje. Datos del conductor disponibles para el pasajero.', 'success')
    return redirect(url_for('main.dashboard'))


@main_bp.route('/driver/complete/<int:trip_id>')
def driver_complete(trip_id):
    if 'driver_id' not in session:
        flash('Debes iniciar sesión como conductor', 'danger')
        return redirect(url_for('auth.login'))

    trip = Trip.query.get_or_404(trip_id)
    if trip.driver_id != session['driver_id']:
        flash('No puedes completar este viaje.', 'danger')
        return redirect(url_for('main.dashboard'))

    trip.status = 'completed'
    db.session.commit()
    flash('Viaje completado con éxito.', 'success')
    return redirect(url_for('main.dashboard'))


@main_bp.route('/api/trip/<int:trip_id>/status')
def api_trip_status(trip_id):
    trip = Trip.query.get(trip_id)
    if not trip:
        return jsonify({'error': 'Viaje no encontrado'}), 404

    driver_info = None
    if trip.driver:
        driver_info = {
            'name': trip.driver.name,
            'phone': trip.driver.phone,
            'placa': trip.driver.placa,
            'moto_marca': trip.driver.moto_marca,
            'moto_modelo': trip.driver.moto_modelo,
            'moto_color': trip.driver.moto_color,
            'moto_cilindrada': trip.driver.moto_cilindrada,
            'tiene_casco': trip.driver.tiene_casco,
            'seguro_moto': trip.driver.seguro_moto,
            'carnet_conducir': trip.driver.carnet_conducir,
        }

    return jsonify({
        'id': trip.id,
        'status': trip.status,
        'pickup_address': trip.pickup_address,
        'dropoff_address': trip.dropoff_address,
        'fare': trip.fare,
        'driver': driver_info,
    })


@main_bp.route('/api/trips/available')
def api_trips_available():
    trips = Trip.query.filter_by(status='requested').order_by(Trip.requested_at.asc()).all()
    return jsonify({
        'count': len(trips),
        'trips': [{
            'id': t.id,
            'pickup_address': t.pickup_address,
            'dropoff_address': t.dropoff_address,
            'fare': t.fare,
            'requested_at': t.requested_at.isoformat() if t.requested_at else None,
        } for t in trips],
    })
