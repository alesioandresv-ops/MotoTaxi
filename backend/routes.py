import os
import math
from datetime import datetime
from flask import Blueprint, render_template, session, request, redirect, url_for, flash, jsonify
from .models import db, User, Driver, Trip, Review, DriverSession

main_bp = Blueprint('main', __name__)

TARIFA_BASE = 3.0
TARIFA_POR_KM = 1.5
TARIFA_POR_MIN = 0.25
TARIFA_MINIMA = 5.0

def calcular_tarifa_real(distance_km, duration_min):
    fare = TARIFA_BASE + (distance_km * TARIFA_POR_KM) + (duration_min * TARIFA_POR_MIN)
    return round(max(fare, TARIFA_MINIMA), 2)

def calcular_distancia(lat1, lng1, lat2, lng2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return round(R * c, 2)

@main_bp.route('/')
def index():
    return render_template('index.html')

@main_bp.route('/dashboard')
def dashboard():
    if 'user_id' in session:
        user_name = session.get('user_name')
        passenger = User.query.get(session['user_id'])
        current_trip = Trip.query.filter(
            Trip.passenger_id == passenger.id,
            Trip.status.in_(['requested', 'accepted', 'ongoing'])
        ).order_by(Trip.requested_at.desc()).first()
        history_trips = Trip.query.filter_by(passenger_id=passenger.id).order_by(Trip.requested_at.desc()).limit(10).all()
        driver_info = current_trip.driver if current_trip and current_trip.driver else None

        nearby_drivers = Driver.query.filter(
            Driver.is_online == True,
            Driver.is_ocupado == False,
            Driver.lat.isnot(None),
            Driver.lng.isnot(None)
        ).all()

        return render_template(
            'dashboard.html',
            user_type='passenger',
            user_name=user_name,
            current_trip=current_trip,
            history_trips=history_trips,
            driver_info=driver_info,
            driver=passenger,
            nearby_drivers=nearby_drivers,
            MAPBOX_TOKEN=os.getenv('MAPBOX_TOKEN', ''),
            GOOGLE_MAPS_KEY=os.getenv('GOOGLE_MAPS_KEY', '')
        )

    if 'driver_id' in session:
        user_name = session.get('driver_name')
        driver = Driver.query.get(session['driver_id'])
        available_trips = Trip.query.filter_by(status='requested').order_by(Trip.requested_at.asc()).all()
        active_trip = Trip.query.filter(
            Trip.driver_id == driver.id,
            Trip.status.in_(['accepted', 'ongoing'])
        ).order_by(Trip.requested_at.desc()).first()
        completed_trips = Trip.query.filter_by(driver_id=driver.id, status='completed').order_by(Trip.requested_at.desc()).limit(10).all()

        return render_template(
            'dashboard.html',
            user_type='driver',
            user_name=user_name,
            driver=driver,
            available_trips=available_trips,
            active_trip=active_trip,
            completed_trips=completed_trips,
            MAPBOX_TOKEN=os.getenv('MAPBOX_TOKEN', ''),
            GOOGLE_MAPS_KEY=os.getenv('GOOGLE_MAPS_KEY', '')
        )

    return redirect(url_for('auth.login'))

@main_bp.route('/passenger/request', methods=['POST'])
def passenger_request():
    if 'user_id' not in session:
        flash('Debes iniciar sesión como pasajero', 'danger')
        return redirect(url_for('auth.login'))

    pickup = request.form.get('pickup_address')
    dropoff = request.form.get('dropoff_address')
    pickup_lat = request.form.get('pickup_lat', type=float)
    pickup_lng = request.form.get('pickup_lng', type=float)
    dropoff_lat = request.form.get('dropoff_lat', type=float)
    dropoff_lng = request.form.get('dropoff_lng', type=float)
    distance_km = request.form.get('distance_km', type=float)

    if not pickup or not dropoff:
        flash('Completa el origen y destino', 'danger')
        return redirect(url_for('main.dashboard'))

    if distance_km and distance_km > 0:
        fare = calcular_tarifa_real(distance_km, 0)
    else:
        base = 5.0
        dist = max(1, abs(len(pickup) - len(dropoff)))
        fare = round(base + dist * 0.75, 2)

    trip = Trip(
        passenger_id=session['user_id'],
        pickup_address=pickup,
        dropoff_address=dropoff,
        pickup_lat=pickup_lat,
        pickup_lng=pickup_lng,
        dropoff_lat=dropoff_lat,
        dropoff_lng=dropoff_lng,
        distance_km=distance_km,
        fare=fare,
        status='requested'
    )
    db.session.add(trip)
    db.session.commit()

    flash(f'Viaje solicitado (${fare:.2f}). Esperando conductor.', 'success')
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
    driver = Driver.query.get(session['driver_id'])
    driver.is_ocupado = True
    db.session.commit()

    flash('Has aceptado el viaje.', 'success')
    return redirect(url_for('main.dashboard'))

@main_bp.route('/api/driver/respond/<int:trip_id>', methods=['POST'])
def api_driver_respond(trip_id):
    if 'driver_id' not in session:
        return jsonify({'error': 'No autorizado'}), 401

    data = request.get_json()
    action = data.get('action') if data else None

    trip = Trip.query.get(trip_id)
    if not trip or trip.status != 'requested':
        return jsonify({'error': 'Viaje no disponible'}), 400

    if action == 'accept':
        trip.driver_id = session['driver_id']
        trip.status = 'accepted'
        driver = Driver.query.get(session['driver_id'])
        driver.is_ocupado = True
        db.session.commit()
        return jsonify({'success': True, 'status': 'accepted', 'trip_id': trip.id})

    elif action == 'reject':
        return jsonify({'success': True, 'status': 'rejected'})

    return jsonify({'error': 'Acción inválida'}), 400

@main_bp.route('/driver/start/<int:trip_id>')
def driver_start(trip_id):
    if 'driver_id' not in session:
        flash('Debes iniciar sesión como conductor', 'danger')
        return redirect(url_for('auth.login'))

    trip = Trip.query.get_or_404(trip_id)
    if trip.driver_id != session['driver_id']:
        flash('No puedes modificar este viaje.', 'danger')
        return redirect(url_for('main.dashboard'))

    trip.status = 'ongoing'
    trip.started_at = datetime.utcnow()
    db.session.commit()
    flash('Viaje iniciado.', 'success')
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
    trip.completed_at = datetime.utcnow()
    driver = Driver.query.get(session['driver_id'])
    driver.is_ocupado = False
    db.session.commit()

    flash('Viaje completado con éxito. ¡Califica a tu pasajero!', 'success')
    return redirect(url_for('main.dashboard'))

@main_bp.route('/api/trip/<int:trip_id>/cancel', methods=['POST'])
def api_cancel_trip(trip_id):
    if 'user_id' not in session and 'driver_id' not in session:
        return jsonify({'error': 'No autorizado'}), 401

    data = request.get_json()
    reason = data.get('reason', '') if data else ''

    trip = Trip.query.get(trip_id)
    if not trip:
        return jsonify({'error': 'Viaje no encontrado'}), 404

    if trip.status in ['completed', 'cancelled']:
        return jsonify({'error': 'Viaje ya finalizado'}), 400

    if 'user_id' in session and trip.passenger_id == session['user_id']:
        trip.status = 'cancelled'
        trip.cancelled_by = 'passenger'
        if trip.driver:
            driver = Driver.query.get(trip.driver_id)
            if driver:
                driver.is_ocupado = False
        db.session.commit()
        return jsonify({'success': True})

    if 'driver_id' in session and trip.driver_id == session['driver_id']:
        trip.status = 'cancelled'
        trip.cancelled_by = 'driver'
        driver = Driver.query.get(session['driver_id'])
        driver.is_ocupado = False
        db.session.commit()
        return jsonify({'success': True})

    return jsonify({'error': 'No autorizado'}), 401

@main_bp.route('/api/location/update', methods=['POST'])
def api_location_update():
    if 'driver_id' not in session:
        return jsonify({'error': 'No autorizado'}), 401

    data = request.get_json()
    lat = data.get('lat')
    lng = data.get('lng')

    if lat is None or lng is None:
        return jsonify({'error': 'lat y lng requeridos'}), 400

    driver = Driver.query.get(session['driver_id'])
    driver.lat = lat
    driver.lng = lng
    driver.last_location_update = datetime.utcnow()
    db.session.commit()

    return jsonify({'success': True})

@main_bp.route('/api/driver/toggle_online', methods=['POST'])
def api_toggle_online():
    if 'driver_id' not in session:
        return jsonify({'error': 'No autorizado'}), 401

    data = request.get_json()
    is_online = data.get('is_online', False)

    driver = Driver.query.get(session['driver_id'])
    driver.is_online = is_online
    if not is_online:
        driver.is_ocupado = False
    db.session.commit()

    return jsonify({'success': True, 'is_online': driver.is_online})

@main_bp.route('/api/drivers/nearby')
def api_drivers_nearby():
    lat = request.args.get('lat', type=float)
    lng = request.args.get('lng', type=float)
    radius_km = request.args.get('radius', 10, type=float)

    if lat is None or lng is None:
        return jsonify({'error': 'lat y lng requeridos'}), 400

    drivers = Driver.query.filter(
        Driver.is_online == True,
        Driver.is_ocupado == False,
        Driver.lat.isnot(None),
        Driver.lng.isnot(None)
    ).all()

    nearby = []
    for d in drivers:
        dist = calcular_distancia(lat, lng, d.lat, d.lng)
        if dist <= radius_km:
            nearby.append({
                'id': d.id,
                'name': d.name,
                'rating_avg': d.rating_avg,
                'rating_count': d.rating_count,
                'moto_marca': d.moto_marca,
                'moto_modelo': d.moto_modelo,
                'moto_color': d.moto_color,
                'placa': d.placa,
                'lat': d.lat,
                'lng': d.lng,
                'distance_km': dist,
                'profile_picture': d.profile_picture,
            })

    nearby.sort(key=lambda x: x['distance_km'])

    return jsonify({
        'count': len(nearby),
        'drivers': nearby
    })

@main_bp.route('/api/trip/<int:trip_id>/status')
def api_trip_status(trip_id):
    trip = Trip.query.get(trip_id)
    if not trip:
        return jsonify({'error': 'Viaje no encontrado'}), 404

    driver_info = None
    if trip.driver:
        driver_info = {
            'id': trip.driver.id,
            'name': trip.driver.name,
            'phone': trip.driver.phone,
            'profile_picture': trip.driver.profile_picture,
            'rating_avg': trip.driver.rating_avg,
            'rating_count': trip.driver.rating_count,
            'placa': trip.driver.placa,
            'moto_marca': trip.driver.moto_marca,
            'moto_modelo': trip.driver.moto_modelo,
            'moto_color': trip.driver.moto_color,
            'moto_cilindrada': trip.driver.moto_cilindrada,
            'tiene_casco': trip.driver.tiene_casco,
            'seguro_moto': trip.driver.seguro_moto,
            'carnet_conducir': trip.driver.carnet_conducir,
            'lat': trip.driver.lat,
            'lng': trip.driver.lng,
        }

    return jsonify({
        'id': trip.id,
        'status': trip.status,
        'pickup_address': trip.pickup_address,
        'dropoff_address': trip.dropoff_address,
        'pickup_lat': trip.pickup_lat,
        'pickup_lng': trip.pickup_lng,
        'dropoff_lat': trip.dropoff_lat,
        'dropoff_lng': trip.dropoff_lng,
        'fare': trip.fare,
        'distance_km': trip.distance_km,
        'driver': driver_info,
    })

@main_bp.route('/api/trip/<int:trip_id>/eta')
def api_trip_eta(trip_id):
    trip = Trip.query.get(trip_id)
    if not trip:
        return jsonify({'error': 'Viaje no encontrado'}), 404

    if not trip.driver or not trip.driver.lat or not trip.driver.lng:
        return jsonify({'eta_min': None, 'distance_km': None})

    dist = calcular_distancia(trip.driver.lat, trip.driver.lng, trip.pickup_lat or 0, trip.pickup_lng or 0)
    avg_speed_kmh = 30
    eta_min = max(1, int((dist / avg_speed_kmh) * 60)) if avg_speed_kmh > 0 else None

    return jsonify({
        'eta_min': eta_min,
        'distance_km': dist,
        'driver_lat': trip.driver.lat,
        'driver_lng': trip.driver.lng,
    })

@main_bp.route('/api/trips/available')
def api_trips_available():
    if 'driver_id' in session:
        driver = Driver.query.get(session['driver_id'])
        trips = Trip.query.filter_by(status='requested').order_by(Trip.requested_at.asc()).all()
        trip_list = []
        for t in trips:
            dist = None
            if driver.lat and driver.lng and t.pickup_lat and t.pickup_lng:
                dist = calcular_distancia(driver.lat, driver.lng, t.pickup_lat, t.pickup_lng)
            trip_list.append({
                'id': t.id,
                'pickup_address': t.pickup_address,
                'dropoff_address': t.dropoff_address,
                'pickup_lat': t.pickup_lat,
                'pickup_lng': t.pickup_lng,
                'fare': t.fare,
                'distance_km': dist,
                'requested_at': t.requested_at.isoformat() if t.requested_at else None,
            })
        trip_list.sort(key=lambda x: x['distance_km'] if x['distance_km'] else 999)

        return jsonify({
            'count': len(trip_list),
            'trips': trip_list,
            'driver_lat': driver.lat,
            'driver_lng': driver.lng,
        })

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

@main_bp.route('/api/trip/<int:trip_id>/rate', methods=['POST'])
def api_rate_trip(trip_id):
    if 'user_id' not in session and 'driver_id' not in session:
        return jsonify({'error': 'No autorizado'}), 401

    trip = Trip.query.get(trip_id)
    if not trip or trip.status != 'completed':
        return jsonify({'error': 'Viaje no encontrado o no completado'}), 400

    data = request.get_json()
    rating = data.get('rating')
    comment = data.get('comment', '')

    if not rating or not (1 <= int(rating) <= 5):
        return jsonify({'error': 'Calificación debe ser entre 1 y 5'}), 400

    rating = int(rating)

    if 'user_id' in session and trip.passenger_id == session['user_id']:
        existing = Review.query.filter_by(trip_id=trip.id, from_user_id=session['user_id']).first()
        if existing:
            return jsonify({'error': 'Ya calificaste este viaje'}), 400

        review = Review(
            trip_id=trip.id,
            from_user_id=session['user_id'],
            to_driver_id=trip.driver_id,
            rating=rating,
            comment=comment,
            role='passenger'
        )
        db.session.add(review)
        _update_driver_rating(trip.driver_id)

    elif 'driver_id' in session and trip.driver_id == session['driver_id']:
        existing = Review.query.filter_by(trip_id=trip.id, from_driver_id=session['driver_id']).first()
        if existing:
            return jsonify({'error': 'Ya calificaste este viaje'}), 400

        review = Review(
            trip_id=trip.id,
            from_driver_id=session['driver_id'],
            to_user_id=trip.passenger_id,
            rating=rating,
            comment=comment,
            role='driver'
        )
        db.session.add(review)
        _update_user_rating(trip.passenger_id)

    else:
        return jsonify({'error': 'No autorizado'}), 401

    db.session.commit()
    return jsonify({'success': True})

def _update_driver_rating(driver_id):
    driver = Driver.query.get(driver_id)
    if driver:
        reviews = Review.query.filter_by(to_driver_id=driver_id).all()
        if reviews:
            driver.rating_avg = round(sum(r.rating for r in reviews) / len(reviews), 1)
            driver.rating_count = len(reviews)

def _update_user_rating(user_id):
    user = User.query.get(user_id)
    if user:
        reviews = Review.query.filter_by(to_user_id=user_id).all()
        if reviews:
            user.rating_avg = round(sum(r.rating for r in reviews) / len(reviews), 1)
            user.rating_count = len(reviews)

@main_bp.route('/api/driver/reviews/<int:driver_id>')
def api_driver_reviews(driver_id):
    reviews = Review.query.filter_by(to_driver_id=driver_id).order_by(Review.created_at.desc()).limit(20).all()
    return jsonify({
        'reviews': [{
            'id': r.id,
            'rating': r.rating,
            'comment': r.comment,
            'created_at': r.created_at.isoformat() if r.created_at else None,
            'from_user': User.query.get(r.from_user_id).name if r.from_user_id else None,
        } for r in reviews]
    })

@main_bp.route('/api/user/reviews/<int:user_id>')
def api_user_reviews(user_id):
    reviews = Review.query.filter_by(to_user_id=user_id).order_by(Review.created_at.desc()).limit(20).all()
    return jsonify({
        'reviews': [{
            'id': r.id,
            'rating': r.rating,
            'comment': r.comment,
            'created_at': r.created_at.isoformat() if r.created_at else None,
            'from_driver': Driver.query.get(r.from_driver_id).name if r.from_driver_id else None,
        } for r in reviews]
    })

@main_bp.route('/api/trip/<int:trip_id>/driver-eta')
def api_driver_eta(trip_id):
    trip = Trip.query.get(trip_id)
    if not trip or not trip.driver:
        return jsonify({'eta_min': None})

    driver = trip.driver
    if not driver.lat or not driver.lng:
        return jsonify({'eta_min': None})

    dist = calcular_distancia(driver.lat, driver.lng, trip.pickup_lat or 0, trip.pickup_lng or 0)
    avg_speed_kmh = 30
    eta_min = max(1, int((dist / avg_speed_kmh) * 60))
    return jsonify({'eta_min': eta_min, 'distance_km': dist, 'driver_lat': driver.lat, 'driver_lng': driver.lng})
