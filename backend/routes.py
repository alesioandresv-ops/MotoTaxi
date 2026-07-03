import os
import json
import math
import secrets
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from functools import wraps
from flask import Blueprint, render_template, session, request, redirect, url_for, flash, jsonify
from .models import db, User, Driver, Trip, Review

main_bp = Blueprint('main', __name__)

def csrf_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = (
            request.form.get('csrf_token')
            or request.headers.get('X-CSRF-Token')
            or (request.is_json and request.get_json(silent=True) or {}).get('csrf_token')
        )
        if not token or token != session.get('csrf_token'):
            return jsonify({'error': 'CSRF token inválido'}), 403
        return f(*args, **kwargs)
    return decorated

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session and 'driver_id' not in session:
            if request.is_json:
                return jsonify({'error': 'No autorizado'}), 401
            flash('Debes iniciar sesión', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated

def sanitize_input(value):
    if value is None:
        return None
    import re
    value = str(value).strip()
    value = re.sub(r'<[^>]*>', '', value)
    return value[:500]

# Tarifas — Moto
TARIFA_BASE_MOTO = 3.0
TARIFA_POR_KM_MOTO = 1.5
TARIFA_POR_MIN_MOTO = 0.25
TARIFA_MINIMA_MOTO = 5.0

# Tarifas — Auto
TARIFA_BASE_AUTO = 4.5
TARIFA_POR_KM_AUTO = 2.0
TARIFA_POR_MIN_AUTO = 0.30
TARIFA_MINIMA_AUTO = 7.0

def calcular_tarifa_real(distance_km, duration_min, vehicle_type='moto'):
    if vehicle_type == 'auto':
        fare = TARIFA_BASE_AUTO + (distance_km * TARIFA_POR_KM_AUTO) + (duration_min * TARIFA_POR_MIN_AUTO)
        return round(max(fare, TARIFA_MINIMA_AUTO), 2)
    fare = TARIFA_BASE_MOTO + (distance_km * TARIFA_POR_KM_MOTO) + (duration_min * TARIFA_POR_MIN_MOTO)
    return round(max(fare, TARIFA_MINIMA_MOTO), 2)

def calcular_distancia(lat1, lng1, lat2, lng2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return round(R * c, 2)

def vehicle_emoji(vtype):
    return '🚗' if vtype == 'auto' else '🛵'

def vehicle_label(vtype):
    return 'Auto' if vtype == 'auto' else 'Moto'

def get_driver_vehicle_info(driver):
    if driver.vehicle_type == 'auto':
        return {
            'vehicle_type': 'auto',
            'marca': driver.auto_marca or '',
            'modelo': driver.auto_modelo or '',
            'color': driver.auto_color or '',
            'placa': driver.placa_auto or '',
            'año': driver.auto_año or '',
        }
    return {
        'vehicle_type': 'moto',
        'marca': driver.moto_marca or '',
        'modelo': driver.moto_modelo or '',
        'color': driver.moto_color or '',
        'placa': driver.placa or '',
        'cilindrada': driver.moto_cilindrada or '',
        'tiene_casco': driver.tiene_casco,
    }

@main_bp.route('/')
def index():
    import os
    demo_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'demo', 'index.html')
    if os.path.exists(demo_path):
        with open(demo_path, 'r', encoding='utf-8') as f:
            return f.read()
    return render_template('index.html')

@main_bp.route('/app')
def app_index():
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
        cutoff = datetime.utcnow() - timedelta(days=4)
        history_trips = Trip.query.filter(
            Trip.passenger_id == passenger.id,
            Trip.status != 'cancelled',
            Trip.completed_at >= cutoff
        ).order_by(Trip.requested_at.desc()).limit(10).all()
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
            vehicle_emoji=vehicle_emoji,
            vehicle_label=vehicle_label,
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
        cutoff = datetime.utcnow() - timedelta(days=4)
        completed_trips = Trip.query.filter(
            Trip.driver_id == driver.id,
            Trip.status == 'completed',
            Trip.completed_at >= cutoff
        ).order_by(Trip.requested_at.desc()).limit(10).all()

        return render_template(
            'dashboard.html',
            user_type='driver',
            user_name=user_name,
            driver=driver,
            available_trips=available_trips,
            active_trip=active_trip,
            completed_trips=completed_trips,
            vehicle_emoji=vehicle_emoji,
            vehicle_label=vehicle_label,
            MAPBOX_TOKEN=os.getenv('MAPBOX_TOKEN', ''),
            GOOGLE_MAPS_KEY=os.getenv('GOOGLE_MAPS_KEY', '')
        )

    return redirect(url_for('auth.login'))

@main_bp.route('/passenger/request', methods=['POST'])
@csrf_required
@login_required
def passenger_request():
    if 'user_id' not in session:
        flash('Debes iniciar sesión como pasajero', 'danger')
        return redirect(url_for('auth.login'))

    pickup = sanitize_input(request.form.get('pickup_address'))
    dropoff = sanitize_input(request.form.get('dropoff_address'))
    pickup_lat = request.form.get('pickup_lat', type=float)
    pickup_lng = request.form.get('pickup_lng', type=float)
    dropoff_lat = request.form.get('dropoff_lat', type=float)
    dropoff_lng = request.form.get('dropoff_lng', type=float)
    distance_km = request.form.get('distance_km', type=float)
    vehicle_type = request.form.get('vehicle_type', 'moto')

    if vehicle_type not in ('moto', 'auto'):
        vehicle_type = 'moto'

    if not pickup or not dropoff:
        flash('Completa el origen y destino', 'danger')
        return redirect(url_for('main.dashboard'))

    active = Trip.query.filter(
        Trip.passenger_id == session['user_id'],
        Trip.status.in_(['requested', 'accepted', 'ongoing'])
    ).first()
    if active:
        flash('Ya tienes un viaje en curso', 'warning')
        return redirect(url_for('main.dashboard'))

    if distance_km and distance_km > 0:
        fare = calcular_tarifa_real(distance_km, 0, vehicle_type)
    else:
        base = TARIFA_MINIMA_AUTO if vehicle_type == 'auto' else TARIFA_MINIMA_MOTO
        dist = max(1, abs(len(pickup) - len(dropoff)))
        por_km = TARIFA_POR_KM_AUTO if vehicle_type == 'auto' else TARIFA_POR_KM_MOTO
        fare = round(base + dist * por_km, 2)

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
        vehicle_type=vehicle_type,
        status='requested'
    )
    db.session.add(trip)
    db.session.commit()

    emoji = vehicle_emoji(vehicle_type)
    flash(f'{emoji} Viaje solicitado (${fare:.2f}). Esperando conductor.', 'success')
    return redirect(url_for('main.dashboard'))

@main_bp.route('/driver/accept/<int:trip_id>', methods=['POST'])
@login_required
@csrf_required
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
@login_required
@csrf_required
def api_driver_respond(trip_id):
    if 'driver_id' not in session:
        return jsonify({'error': 'Debes ser conductor'}), 401

    data = request.get_json(silent=True) or {}
    action = data.get('action')

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

@main_bp.route('/driver/start/<int:trip_id>', methods=['POST'])
@login_required
@csrf_required
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

@main_bp.route('/driver/complete/<int:trip_id>', methods=['POST'])
@login_required
@csrf_required
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
@login_required
@csrf_required
def api_cancel_trip(trip_id):
    data = request.get_json(silent=True) or {}
    reason = sanitize_input(data.get('reason', ''))

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
@login_required
@csrf_required
def api_location_update():
    if 'driver_id' not in session:
        return jsonify({'error': 'Debes ser conductor'}), 401

    driver = Driver.query.get(session['driver_id'])
    if not driver or not driver.is_online:
        return jsonify({'error': 'Conductor no está en línea'}), 403

    data = request.get_json()
    lat = data.get('lat')
    lng = data.get('lng')

    if lat is None or lng is None:
        return jsonify({'error': 'lat y lng requeridos'}), 400

    driver.lat = lat
    driver.lng = lng
    driver.last_location_update = datetime.utcnow()
    db.session.commit()

    return jsonify({'success': True})

@main_bp.route('/api/driver/toggle_online', methods=['POST'])
@login_required
@csrf_required
def api_toggle_online():
    if 'driver_id' not in session:
        return jsonify({'error': 'Debes ser conductor'}), 401

    data = request.get_json(silent=True) or {}
    is_online = data.get('is_online', False)

    driver = Driver.query.get(session['driver_id'])
    driver.is_online = is_online
    if not is_online:
        driver.is_ocupado = False
    db.session.commit()

    return jsonify({'success': True, 'is_online': driver.is_online})

@main_bp.route('/api/drivers/nearby')
@login_required
def api_drivers_nearby():
    lat = request.args.get('lat', type=float)
    lng = request.args.get('lng', type=float)
    radius_km = request.args.get('radius', 10, type=float)
    vehicle_type = request.args.get('vehicle_type', '')

    if lat is None or lng is None:
        return jsonify({'error': 'lat y lng requeridos'}), 400

    query = Driver.query.filter(
        Driver.is_online == True,
        Driver.is_ocupado == False,
        Driver.lat.isnot(None),
        Driver.lng.isnot(None)
    )
    if vehicle_type in ('moto', 'auto'):
        query = query.filter(Driver.vehicle_type == vehicle_type)

    drivers = query.all()

    nearby = []
    for d in drivers:
        dist = calcular_distancia(lat, lng, d.lat, d.lng)
        if dist <= radius_km:
            vinfo = get_driver_vehicle_info(d)
            nearby.append({
                'id': d.id,
                'name': d.name,
                'rating_avg': d.rating_avg,
                'rating_count': d.rating_count,
                'vehicle_type': d.vehicle_type,
                'vehicle_info': vinfo,
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
    if 'user_id' not in session and 'driver_id' not in session:
        return jsonify({'error': 'No autorizado'}), 401

    trip = Trip.query.get(trip_id)
    if not trip:
        return jsonify({'error': 'Viaje no encontrado'}), 404

    if 'user_id' in session and trip.passenger_id != session['user_id']:
        return jsonify({'error': 'No autorizado'}), 401
    if 'driver_id' in session and trip.driver_id != session['driver_id']:
        return jsonify({'error': 'No autorizado'}), 401

    driver_info = None
    if trip.driver:
        vinfo = get_driver_vehicle_info(trip.driver)
        driver_info = {
            'id': trip.driver.id,
            'name': trip.driver.name,
            'phone': trip.driver.phone,
            'profile_picture': trip.driver.profile_picture,
            'rating_avg': trip.driver.rating_avg,
            'rating_count': trip.driver.rating_count,
            'vehicle_type': trip.driver.vehicle_type,
            'vehicle_info': vinfo,
            'lat': trip.driver.lat,
            'lng': trip.driver.lng,
        }

    return jsonify({
        'id': trip.id,
        'status': trip.status,
        'vehicle_type': trip.vehicle_type,
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
    if 'user_id' not in session and 'driver_id' not in session:
        return jsonify({'error': 'No autorizado'}), 401

    trip = Trip.query.get(trip_id)
    if not trip:
        return jsonify({'error': 'Viaje no encontrado'}), 404

    if 'user_id' in session and trip.passenger_id != session['user_id']:
        return jsonify({'error': 'No autorizado'}), 401
    if 'driver_id' in session and trip.driver_id != session['driver_id']:
        return jsonify({'error': 'No autorizado'}), 401

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
                'vehicle_type': t.vehicle_type,
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
            'vehicle_type': t.vehicle_type,
            'requested_at': t.requested_at.isoformat() if t.requested_at else None,
        } for t in trips],
    })

@main_bp.route('/api/trip/<int:trip_id>/rate', methods=['POST'])
@login_required
@csrf_required
def api_rate_trip(trip_id):
    trip = Trip.query.get(trip_id)
    if not trip or trip.status != 'completed':
        return jsonify({'error': 'Viaje no encontrado o no completado'}), 400

    data = request.get_json(silent=True) or {}
    rating = data.get('rating')
    comment = sanitize_input(data.get('comment', ''))

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
    if 'user_id' not in session and 'driver_id' not in session:
        return jsonify({'error': 'No autorizado'}), 401

    trip = Trip.query.get(trip_id)
    if not trip or not trip.driver:
        return jsonify({'eta_min': None})

    if 'user_id' in session and trip.passenger_id != session['user_id']:
        return jsonify({'error': 'No autorizado'}), 401
    if 'driver_id' in session and trip.driver_id != session['driver_id']:
        return jsonify({'error': 'No autorizado'}), 401

    driver = trip.driver
    if not driver.lat or not driver.lng:
        return jsonify({'eta_min': None})

    dist = calcular_distancia(driver.lat, driver.lng, trip.pickup_lat or 0, trip.pickup_lng or 0)
    avg_speed_kmh = 30
    eta_min = max(1, int((dist / avg_speed_kmh) * 60))
    return jsonify({'eta_min': eta_min, 'distance_km': dist, 'driver_lat': driver.lat, 'driver_lng': driver.lng})

@main_bp.route('/api/geocode')
def api_geocode():
    q = request.args.get('q')
    if not q:
        return jsonify({'error': 'q requerido'}), 400
    try:
        url = 'https://nominatim.openstreetmap.org/search?' + urllib.parse.urlencode({
            'q': q, 'format': 'json', 'limit': 1, 'addressdetails': 0
        })
        req = urllib.request.Request(url, headers={'User-Agent': 'VAN/1.0'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            if data:
                return jsonify({'lat': float(data[0]['lat']), 'lng': float(data[0]['lon']), 'display_name': data[0].get('display_name', '')})
        return jsonify({'error': 'No encontrado'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ─── Driver Payment Methods API ───
@main_bp.route('/api/driver/payment-methods', methods=['GET', 'POST'])
@login_required
@csrf_required
def api_driver_payment_methods():
    if 'driver_id' not in session:
        return jsonify({'error': 'Debes ser conductor'}), 401

    if request.method == 'GET':
        methods = DriverPaymentMethod.query.filter_by(driver_id=session['driver_id']).all()
        return jsonify({
            'methods': [{
                'id': m.id, 'type': m.type,
                'details': json.loads(m.details) if m.details else {},
                'is_active': m.is_active
            } for m in methods]
        })

    data = request.get_json(silent=True) or {}
    pm_type = data.get('type')
    details = data.get('details', {})

    if pm_type not in ('card', 'mercadopago', 'transfer'):
        return jsonify({'error': 'Tipo inválido'}), 400

    method = DriverPaymentMethod(
        driver_id=session['driver_id'],
        type=pm_type,
        details=json.dumps(details, ensure_ascii=False),
        is_active=True
    )
    db.session.add(method)
    db.session.commit()
    return jsonify({'success': True, 'id': method.id})

@main_bp.route('/api/driver/payment-methods/<int:method_id>', methods=['DELETE'])
@login_required
@csrf_required
def api_delete_payment_method(method_id):
    if 'driver_id' not in session:
        return jsonify({'error': 'Debes ser conductor'}), 401
    method = DriverPaymentMethod.query.get(method_id)
    if not method or method.driver_id != session['driver_id']:
        return jsonify({'error': 'No encontrado'}), 404
    db.session.delete(method)
    db.session.commit()
    return jsonify({'success': True})

@main_bp.route('/api/driver/<int:driver_id>/payment-methods')
def api_driver_public_payment_methods(driver_id):
    driver = Driver.query.get(driver_id)
    if not driver:
        return jsonify({'error': 'Conductor no encontrado'}), 404
    methods = DriverPaymentMethod.query.filter_by(driver_id=driver_id, is_active=True).all()
    return jsonify({
        'methods': [{'type': m.type, 'details': json.loads(m.details) if m.details else {}} for m in methods]
    })

# ─── Passenger Payment Configs API ───
@main_bp.route('/api/user/payment-methods', methods=['GET', 'POST'])
@login_required
@csrf_required
def api_user_payment_methods():
    if 'user_id' not in session:
        return jsonify({'error': 'Debes ser pasajero'}), 401

    if request.method == 'GET':
        configs = PassengerPaymentConfig.query.filter_by(user_id=session['user_id']).all()
        return jsonify({
            'methods': [{
                'id': c.id, 'type': c.type,
                'details': json.loads(c.details) if c.details else {},
                'is_default': c.is_default
            } for c in configs]
        })

    data = request.get_json(silent=True) or {}
    pm_type = data.get('type')
    details = data.get('details', {})

    if pm_type not in ('card', 'mercadopago', 'transfer'):
        return jsonify({'error': 'Tipo inválido'}), 400

    config = PassengerPaymentConfig(
        user_id=session['user_id'],
        type=pm_type,
        details=json.dumps(details, ensure_ascii=False),
        is_default=not PassengerPaymentConfig.query.filter_by(user_id=session['user_id']).first()
    )
    db.session.add(config)
    db.session.commit()
    return jsonify({'success': True, 'id': config.id})

@main_bp.route('/api/user/payment-methods/<int:config_id>', methods=['DELETE'])
@login_required
@csrf_required
def api_delete_user_payment_method(config_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Debes ser pasajero'}), 401
    config = PassengerPaymentConfig.query.get(config_id)
    if not config or config.user_id != session['user_id']:
        return jsonify({'error': 'No encontrado'}), 404
    db.session.delete(config)
    db.session.commit()
    return jsonify({'success': True})

# ─── Guidelines API ───
@main_bp.route('/api/accept-guidelines', methods=['POST'])
@login_required
@csrf_required
def api_accept_guidelines():
    if 'user_id' in session:
        user = User.query.get(session['user_id'])
        if user:
            user.accepted_guidelines = True
            db.session.commit()
            return jsonify({'success': True})
    if 'driver_id' in session:
        driver = Driver.query.get(session['driver_id'])
        if driver:
            driver.accepted_guidelines = True
            db.session.commit()
            return jsonify({'success': True})
    return jsonify({'error': 'No autorizado'}), 401

@main_bp.route('/api/guidelines-status')
@login_required
def api_guidelines_status():
    if 'user_id' in session:
        user = User.query.get(session['user_id'])
        return jsonify({'accepted': user.accepted_guidelines if user else False})
    if 'driver_id' in session:
        driver = Driver.query.get(session['driver_id'])
        return jsonify({'accepted': driver.accepted_guidelines if driver else False})
    return jsonify({'accepted': False})
