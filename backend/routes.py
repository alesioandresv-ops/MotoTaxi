import os
import json
import uuid
import hmac
import math
import secrets
import urllib.request
import urllib.parse
from datetime import datetime, timedelta, timezone
from functools import wraps
from werkzeug.utils import secure_filename
from flask import Blueprint, render_template, session, request, redirect, url_for, flash, jsonify, current_app
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from .models import db, User, Driver, Trip, Review, DriverPaymentMethod, PassengerPaymentConfig, FavoriteAddress, WalletTransaction, TopUpRequest
from .extensions import encrypt_details, decrypt_details, limiter
from .validators import sanitize_input

main_bp = Blueprint('main', __name__)

def csrf_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = (
            request.form.get('csrf_token')
            or request.headers.get('X-CSRF-Token')
            or (request.is_json and request.get_json(silent=True) or {}).get('csrf_token')
        )
        if not token or not hmac.compare_digest(str(token), str(session.get('csrf_token', ''))):
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

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('is_admin'):
            if request.is_json:
                return jsonify({'error': 'No autorizado como admin'}), 401
            flash('Debes iniciar sesión como administrador', 'danger')
            return redirect(url_for('main.admin_login'))
        return f(*args, **kwargs)
    return decorated

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

PAYMENT_TYPES = {
    'efectivo': '💵 Efectivo',
    'mercadopago': '💙 MercadoPago',
    'transferencia': '🏦 Transferencia',
    'tarjeta': '💳 Tarjeta',
    'billetera': '💰 Billetera',
}

def get_payment_label(key):
    return PAYMENT_TYPES.get(key, key)

def parse_accepted_payments(raw):
    if not raw:
        return ['efectivo']
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [p for p in parsed if p in PAYMENT_TYPES]
    except (json.JSONDecodeError, TypeError):
        pass
    return ['efectivo']

def cancel_stale_trips():
    timeout = datetime.utcnow() - timedelta(minutes=5)
    stale = Trip.query.filter(
        Trip.status == 'requested',
        Trip.requested_at < timeout
    ).all()
    for t in stale:
        t.status = 'cancelled'
        t.cancelled_by = 'system'
    if stale:
        db.session.commit()

def get_driver_vehicle_info(driver):
    accepted = parse_accepted_payments(driver.accepted_payments)
    if driver.vehicle_type == 'auto':
        return {
            'vehicle_type': 'auto',
            'marca': driver.auto_marca or '',
            'modelo': driver.auto_modelo or '',
            'color': driver.auto_color or '',
            'placa': driver.placa_auto or '',
            'año': driver.auto_año or '',
            'accepted_payments': accepted,
            'mercadopago_qr': driver.mercadopago_qr,
        }
    return {
        'vehicle_type': 'moto',
        'marca': driver.moto_marca or '',
        'modelo': driver.moto_modelo or '',
        'color': driver.moto_color or '',
        'placa': driver.placa or '',
        'cilindrada': driver.moto_cilindrada or '',
        'tiene_casco': driver.tiene_casco,
        'accepted_payments': accepted,
        'mercadopago_qr': driver.mercadopago_qr,
    }

@main_bp.route('/health')
def health():
    try:
        db.session.execute(db.text('SELECT 1'))
        return jsonify({'status': 'ok', 'db': 'connected'}), 200
    except Exception as e:
        current_app.logger.error(f"Health check DB failure: {e}")
        return jsonify({'status': 'degraded', 'db': 'disconnected'}), 503

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
@login_required
def dashboard():
    cancel_stale_trips()
    if 'user_id' in session:
        user_name = session.get('user_name')
        passenger = User.query.get(session['user_id'])
        current_trip = Trip.query.filter(
            Trip.passenger_id == passenger.id,
            Trip.status.in_(['requested', 'accepted', 'ongoing'])
        ).order_by(Trip.requested_at.desc()).first()
        cutoff = datetime.now(timezone.utc) - timedelta(days=4)
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
        ).limit(50).all()

        prefill_pickup = request.args.get('pickup', '')
        prefill_dropoff = request.args.get('dropoff', '')
        prefill_vehicle = request.args.get('vehicle', '')

        return render_template(
            'dashboard.html',
            user_type='passenger',
            user_name=user_name,
            current_trip=current_trip,
            history_trips=history_trips,
            driver_info=driver_info,
            driver=passenger,
            nearby_drivers=nearby_drivers,
            prefill_pickup=prefill_pickup,
            prefill_dropoff=prefill_dropoff,
            prefill_vehicle=prefill_vehicle,
            vehicle_emoji=vehicle_emoji,
            vehicle_label=vehicle_label,
            MAPBOX_TOKEN=os.getenv('MAPBOX_TOKEN', ''),
            GOOGLE_MAPS_KEY=os.getenv('GOOGLE_MAPS_KEY', '')
        )

    if 'driver_id' in session:
        user_name = session.get('driver_name')
        driver = Driver.query.get(session['driver_id'])
        available_trips = Trip.query.filter_by(status='requested').order_by(Trip.requested_at.asc()).limit(50).all()
        active_trip = Trip.query.filter(
            Trip.driver_id == driver.id,
            Trip.status.in_(['accepted', 'ongoing'])
        ).order_by(Trip.requested_at.desc()).first()
        cutoff = datetime.now(timezone.utc) - timedelta(days=4)
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

@main_bp.route('/historial')
@login_required
def historial():
    if 'user_id' not in session:
        flash('Debes ser pasajero para ver tu historial', 'danger')
        return redirect(url_for('auth.login'))
    return render_template('historial.html', user_name=session.get('user_name'))

@main_bp.route('/request-ride')
@login_required
def request_ride():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    pickup = request.args.get('from', '')
    dropoff = request.args.get('to', '')
    vehicle = request.args.get('vehicle', 'moto')
    return redirect(url_for('main.dashboard', pickup=pickup, dropoff=dropoff, vehicle=vehicle))

@main_bp.route('/api/trips/history')
@login_required
def api_trips_history():
    if 'user_id' not in session:
        return jsonify({'error': 'Debes ser pasajero'}), 401

    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 20, type=int)
    limit = min(limit, 100)
    status_filter = request.args.get('status', '')
    search = request.args.get('q', '').strip()

    query = Trip.query.filter(Trip.passenger_id == session['user_id'])

    if status_filter == 'completed':
        query = query.filter(Trip.status == 'completed')
    elif status_filter == 'cancelled':
        query = query.filter(Trip.status == 'cancelled')
    else:
        query = query.filter(Trip.status.in_(['completed', 'cancelled']))

    if search:
        like = f'%{search}%'
        query = query.filter(
            db.or_(Trip.pickup_address.ilike(like), Trip.dropoff_address.ilike(like))
        )

    total = query.count()
    pages = max(1, (total + limit - 1) // limit)
    page = min(page, pages)

    trips = query.order_by(Trip.requested_at.desc()).offset((page - 1) * limit).limit(limit).all()

    result = []
    for t in trips:
        driver = Driver.query.get(t.driver_id) if t.driver_id else None
        my_review = Review.query.filter_by(trip_id=t.id, from_user_id=session['user_id']).first()
        result.append({
            'id': t.id,
            'pickup_address': t.pickup_address,
            'dropoff_address': t.dropoff_address,
            'fare': float(t.fare) if t.fare else 0,
            'status': t.status,
            'payment_method': t.payment_method,
            'vehicle_type': t.vehicle_type,
            'requested_at': t.requested_at.isoformat() if t.requested_at else None,
            'completed_at': t.completed_at.isoformat() if t.completed_at else None,
            'duration_min': t.duration_min,
            'distance_km': t.distance_km,
            'driver_name': driver.name if driver else None,
            'driver_phone': driver.phone if driver else None,
            'driver_vehicle': driver.vehicle_type if driver else None,
            'my_rating': my_review.rating if my_review else None,
            'my_comment': my_review.comment if my_review else None,
        })

    return jsonify({'trips': result, 'total': total, 'page': page, 'pages': pages})

@main_bp.route('/passenger/request', methods=['POST'])
@limiter.limit("10 per minute")
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
    payment_method = sanitize_input(request.form.get('payment_method'))

    if vehicle_type not in ('moto', 'auto'):
        vehicle_type = 'moto'

    if payment_method not in PAYMENT_TYPES:
        flash('Método de pago inválido', 'danger')
        return redirect(url_for('main.dashboard'))

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
        por_km = TARIFA_POR_KM_AUTO if vehicle_type == 'auto' else TARIFA_POR_KM_MOTO
        if pickup_lat and pickup_lng and dropoff_lat and dropoff_lng:
            dist = calcular_distancia(pickup_lat, pickup_lng, dropoff_lat, dropoff_lng)
            dist = max(1.0, dist)
        else:
            dist = 1.0
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
        payment_method=payment_method,
        status='requested'
    )
    db.session.add(trip)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash('Ya tienes un viaje en curso.', 'warning')
        return redirect(url_for('main.dashboard'))

    emoji = vehicle_emoji(vehicle_type)
    pm_label = get_payment_label(payment_method)
    flash(f'{emoji} Viaje solicitado (${fare:.2f}) — {pm_label}. Esperando conductor.', 'success')
    return redirect(url_for('main.dashboard'))

@main_bp.route('/driver/accept/<int:trip_id>', methods=['POST'])
@limiter.limit("20 per minute")
@login_required
@csrf_required
def driver_accept(trip_id):
    if 'driver_id' not in session:
        flash('Debes iniciar sesión como conductor', 'danger')
        return redirect(url_for('auth.login'))

    result = db.session.execute(
        update(Trip)
        .where(Trip.id == trip_id, Trip.status == 'requested')
        .values(driver_id=session['driver_id'], status='accepted')
    )
    if result.rowcount == 0:
        flash('Este viaje ya no está disponible', 'warning')
        return redirect(url_for('main.dashboard'))

    driver = db.session.query(Driver).filter_by(id=session['driver_id']).with_for_update().first()
    driver.is_ocupado = True
    db.session.commit()

    flash('Has aceptado el viaje.', 'success')
    return redirect(url_for('main.dashboard'))

@main_bp.route('/api/driver/respond/<int:trip_id>', methods=['POST'])
@limiter.limit("20 per minute")
@login_required
@csrf_required
def api_driver_respond(trip_id):
    if 'driver_id' not in session:
        return jsonify({'error': 'Debes ser conductor'}), 401

    data = request.get_json(silent=True) or {}
    action = data.get('action')

    if action == 'accept':
        result = db.session.execute(
            update(Trip)
            .where(Trip.id == trip_id, Trip.status == 'requested')
            .values(driver_id=session['driver_id'], status='accepted')
        )
        if result.rowcount == 0:
            return jsonify({'error': 'Viaje no disponible'}), 400

        driver = db.session.query(Driver).filter_by(id=session['driver_id']).with_for_update().first()
        driver.is_ocupado = True
        db.session.commit()
        return jsonify({'success': True, 'status': 'accepted', 'trip_id': trip_id})

    elif action == 'reject':
        return jsonify({'success': True, 'status': 'rejected'})

    return jsonify({'error': 'Acción inválida'}), 400

@main_bp.route('/driver/start/<int:trip_id>', methods=['POST'])
@limiter.limit("20 per minute")
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
    trip.started_at = datetime.now(timezone.utc)
    db.session.commit()
    flash('Viaje iniciado.', 'success')
    return redirect(url_for('main.dashboard'))

@main_bp.route('/driver/complete/<int:trip_id>', methods=['POST'])
@limiter.limit("20 per minute")
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
    trip.completed_at = datetime.now(timezone.utc)
    if trip.started_at:
        started = trip.started_at.replace(tzinfo=None) if trip.started_at.tzinfo else trip.started_at
        completed = trip.completed_at.replace(tzinfo=None) if trip.completed_at.tzinfo else trip.completed_at
        delta = completed - started
        trip.duration_min = max(1, int(delta.total_seconds() / 60))
        recalc_fare = calcular_tarifa_real(float(trip.distance_km or 0), trip.duration_min, trip.vehicle_type)
        trip.fare = recalc_fare
    trip_driver = db.session.query(Driver).filter_by(id=session['driver_id']).with_for_update().first()
    trip_driver.is_ocupado = False

    if trip.payment_method == 'billetera' and trip.fare:
        passenger = db.session.query(User).filter_by(id=trip.passenger_id).with_for_update().first()
        if passenger and float(passenger.balance) >= float(trip.fare):
            passenger.balance = round(float(passenger.balance) - float(trip.fare), 2)
            trip_driver.balance = round(float(trip_driver.balance) + float(trip.fare), 2)
            db.session.add(WalletTransaction(
                user_id=passenger.id, amount=-trip.fare, type='trip_payment',
                trip_id=trip.id, description=f'Viaje #{trip.id}'
            ))
            db.session.add(WalletTransaction(
                driver_id=trip_driver.id, amount=trip.fare, type='trip_payment',
                trip_id=trip.id, description=f'Viaje #{trip.id}'
            ))
        elif passenger:
            db.session.add(WalletTransaction(
                user_id=passenger.id, amount=-trip.fare, type='trip_payment',
                trip_id=trip.id, status='pending',
                description=f'Viaje #{trip.id} — pago pendiente (saldo insuficiente)'
            ))
            flash('Saldo insuficiente del pasajero. Se registra como pendiente.', 'warning')

    db.session.commit()

    try:
        fav = FavoriteAddress.query.filter_by(
            user_id=trip.passenger_id,
            pickup_address=trip.pickup_address,
            dropoff_address=trip.dropoff_address
        ).first()
        if fav:
            fav.count += 1
        else:
            existing_count = FavoriteAddress.query.filter_by(user_id=trip.passenger_id).count()
            fav = FavoriteAddress(
                user_id=trip.passenger_id,
                name=f'Ruta Frecuente {existing_count + 1}',
                pickup_address=trip.pickup_address,
                dropoff_address=trip.dropoff_address,
                count=1
            )
            db.session.add(fav)
        db.session.commit()
    except Exception:
        db.session.rollback()

    flash('Viaje completado con éxito. ¡Califica a tu pasajero!', 'success')
    return redirect(url_for('main.dashboard'))

@main_bp.route('/api/trip/<int:trip_id>/cancel', methods=['POST'])
@limiter.limit("10 per minute")
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
@limiter.limit("60 per minute")
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

    if not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)):
        return jsonify({'error': 'lat/lng deben ser numéricos'}), 400
    if math.isnan(lat) or math.isnan(lng):
        return jsonify({'error': 'Coordenadas inválidas'}), 400
    if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
        return jsonify({'error': 'Coordenadas fuera de rango'}), 400

    driver.lat = lat
    driver.lng = lng
    driver.last_location_update = datetime.now(timezone.utc)
    db.session.commit()

    return jsonify({'success': True})

@main_bp.route('/api/driver/toggle_online', methods=['POST'])
@limiter.limit("30 per minute")
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

    drivers = query.limit(100).all()

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
                'accepted_payments': parse_accepted_payments(d.accepted_payments),
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
        'payment_method': trip.payment_method,
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
@login_required
def api_trips_available():
    cancel_stale_trips()
    if 'driver_id' in session:
        driver = Driver.query.get(session['driver_id'])
        trips = Trip.query.filter_by(status='requested').order_by(Trip.requested_at.asc()).limit(50).all()
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
                'payment_method': t.payment_method,
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

    if 'user_id' in session:
        trips = Trip.query.filter_by(
            passenger_id=session['user_id'], status='requested'
        ).order_by(Trip.requested_at.asc()).limit(50).all()
        return jsonify({
            'count': len(trips),
            'trips': [{
                'id': t.id,
                'pickup_address': t.pickup_address,
                'dropoff_address': t.dropoff_address,
                'fare': t.fare,
                'vehicle_type': t.vehicle_type,
                'payment_method': t.payment_method,
                'requested_at': t.requested_at.isoformat() if t.requested_at else None,
            } for t in trips],
        })

    return jsonify({'error': 'Debes ser conductor o pasajero'}), 403

@main_bp.route('/api/favorites')
@login_required
def api_favorites():
    if 'user_id' not in session:
        return jsonify({'error': 'Debes ser pasajero'}), 401
    favs = FavoriteAddress.query.filter_by(
        user_id=session['user_id']
    ).filter(FavoriteAddress.count >= 3
    ).order_by(FavoriteAddress.count.desc()).limit(3).all()
    return jsonify({'favorites': [{
        'id': f.id,
        'name': f.name,
        'pickup_address': f.pickup_address,
        'dropoff_address': f.dropoff_address,
        'count': f.count
    } for f in favs]})

@main_bp.route('/api/trip/<int:trip_id>/rate', methods=['POST'])
@limiter.limit("5 per minute")
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
@login_required
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
@login_required
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
@login_required
@limiter.limit("30 per minute")
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
        current_app.logger.error(f"Geocode error: {e}")
        return jsonify({'error': 'Error de geocodificación'}), 500

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
                'details': decrypt_details(m.details),
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
        details=encrypt_details(details),
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
@login_required
def api_driver_public_payment_methods(driver_id):
    if 'driver_id' not in session or session['driver_id'] != driver_id:
        return jsonify({'error': 'No autorizado'}), 403
    driver = Driver.query.get(driver_id)
    if not driver:
        return jsonify({'error': 'Conductor no encontrado'}), 404
    methods = DriverPaymentMethod.query.filter_by(driver_id=driver_id, is_active=True).all()
    return jsonify({
        'methods': [{'type': m.type, 'id': m.id} for m in methods]
    })

# ─── Driver Accepted Payments API ───
@main_bp.route('/api/driver/accepted-payments', methods=['GET', 'POST'])
@login_required
@csrf_required
def api_driver_accepted_payments():
    if 'driver_id' not in session:
        return jsonify({'error': 'Debes ser conductor'}), 401

    driver = Driver.query.get(session['driver_id'])
    if not driver:
        return jsonify({'error': 'Conductor no encontrado'}), 404

    if request.method == 'GET':
        accepted = parse_accepted_payments(driver.accepted_payments)
        return jsonify({'accepted_payments': accepted})

    data = request.get_json(silent=True) or {}
    payments = data.get('accepted_payments', [])
    if not isinstance(payments, list):
        return jsonify({'error': 'Formato inválido'}), 400

    valid = [p for p in payments if p in PAYMENT_TYPES]
    if not valid:
        valid = ['efectivo']

    driver.accepted_payments = json.dumps(valid)
    db.session.commit()
    return jsonify({'success': True, 'accepted_payments': valid})

# ─── Driver MercadoPago QR Upload ───
_DRIVER_UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads')

@main_bp.route('/api/driver/mercadopago-qr', methods=['POST'])
@login_required
@csrf_required
def api_upload_mercadopago_qr():
    if 'driver_id' not in session:
        return jsonify({'error': 'Debes ser conductor'}), 401

    driver = Driver.query.get(session['driver_id'])
    if not driver:
        return jsonify({'error': 'Conductor no encontrado'}), 404

    ALLOWED_EXT = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

    if 'qr_image' in request.files:
        file = request.files['qr_image']
        if file and file.filename:
            ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
            if ext not in ALLOWED_EXT:
                return jsonify({'error': 'Formato no permitido'}), 400
            file.seek(0, 2)
            file_size = file.tell()
            file.seek(0)
            if file_size > 5 * 1024 * 1024:
                return jsonify({'error': 'Imagen demasiado grande (máx. 5MB)'}), 400
            try:
                from PIL import Image
                import io
                img_data = file.read()
                file.seek(0)
                img = Image.open(io.BytesIO(img_data))
                img.verify()
            except Exception:
                return jsonify({'error': 'El archivo no es una imagen válida'}), 400
            os.makedirs(_DRIVER_UPLOAD_FOLDER, exist_ok=True)
            filename = f'mp_qr_{uuid.uuid4().hex}.{ext}'
            filepath = os.path.join(_DRIVER_UPLOAD_FOLDER, filename)
            file.save(filepath)
            driver.mercadopago_qr = f'/static/uploads/{filename}'
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
                try:
                    os.remove(filepath)
                except OSError:
                    pass
                raise
            return jsonify({'success': True, 'url': driver.mercadopago_qr})

    data = request.get_json(silent=True) or {}
    image_data = data.get('image')
    if image_data:
        try:
            header, encoded = image_data.split(',', 1)
            import base64
            data_bytes = base64.b64decode(encoded)
            if len(data_bytes) > 5 * 1024 * 1024:
                return jsonify({'error': 'Imagen demasiado grande (máx. 5MB)'}), 400
            ext = 'png' if 'png' in header else 'jpg'
            os.makedirs(_DRIVER_UPLOAD_FOLDER, exist_ok=True)
            filename = f'mp_qr_{uuid.uuid4().hex}.{ext}'
            filepath = os.path.join(_DRIVER_UPLOAD_FOLDER, filename)
            with open(filepath, 'wb') as f:
                f.write(data_bytes)
            driver.mercadopago_qr = f'/static/uploads/{filename}'
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
                try:
                    os.remove(filepath)
                except OSError:
                    pass
                raise
            return jsonify({'success': True, 'url': driver.mercadopago_qr})
        except Exception:
            db.session.rollback()
            return jsonify({'error': 'Error procesando imagen'}), 400

    return jsonify({'error': 'No se proporcionó imagen'}), 400

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
                'details': decrypt_details(c.details),
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
        details=encrypt_details(details),
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


# ═══════════════════════════════════════════════
# ─── ACCOUNT: Settings, Export & Delete (LGPD) ───
# ═══════════════════════════════════════════════

@main_bp.route('/account/settings')
@login_required
def account_settings():
    return render_template('account_settings.html')

@main_bp.route('/api/account/export', methods=['POST'])
@login_required
@csrf_required
def api_account_export():
    if 'user_id' in session:
        user = User.query.get(session['user_id'])
        if not user:
            return jsonify({'error': 'No encontrado'}), 404
        trips = Trip.query.filter_by(passenger_id=user.id).order_by(Trip.requested_at.desc()).limit(1000).all()
        reviews = Review.query.filter_by(to_user_id=user.id).order_by(Review.created_at.desc()).limit(500).all()
        txns = WalletTransaction.query.filter_by(user_id=user.id).order_by(WalletTransaction.created_at.desc()).limit(500).all()
        data = {
            'user': {'name': user.name, 'email': user.email, 'phone': user.phone, 'created_at': str(user.created_at)},
            'trips': [{'id': t.id, 'pickup': t.pickup_address, 'dropoff': t.dropoff_address, 'fare': float(t.fare), 'status': t.status, 'requested_at': str(t.requested_at)} for t in trips],
            'reviews': [{'rating': r.rating, 'comment': r.comment, 'created_at': str(r.created_at)} for r in reviews],
            'wallet_transactions': [{'amount': float(t.amount), 'type': t.type, 'description': t.description, 'created_at': str(t.created_at)} for t in txns],
        }
        return jsonify(data)

    if 'driver_id' in session:
        driver = Driver.query.get(session['driver_id'])
        if not driver:
            return jsonify({'error': 'No encontrado'}), 404
        trips = Trip.query.filter_by(driver_id=driver.id).order_by(Trip.requested_at.desc()).limit(1000).all()
        reviews = Review.query.filter_by(to_driver_id=driver.id).order_by(Review.created_at.desc()).limit(500).all()
        txns = WalletTransaction.query.filter_by(driver_id=driver.id).order_by(WalletTransaction.created_at.desc()).limit(500).all()
        data = {
            'driver': {'name': driver.name, 'email': driver.email, 'phone': driver.phone, 'vehicle_type': driver.vehicle_type, 'created_at': str(driver.created_at)},
            'trips': [{'id': t.id, 'pickup': t.pickup_address, 'dropoff': t.dropoff_address, 'fare': float(t.fare), 'status': t.status, 'requested_at': str(t.requested_at)} for t in trips],
            'reviews': [{'rating': r.rating, 'comment': r.comment, 'created_at': str(r.created_at)} for r in reviews],
            'wallet_transactions': [{'amount': float(t.amount), 'type': t.type, 'description': t.description, 'created_at': str(t.created_at)} for t in txns],
        }
        return jsonify(data)

    return jsonify({'error': 'No autorizado'}), 401

@main_bp.route('/api/account/delete', methods=['POST'])
@login_required
@csrf_required
def api_account_delete():
    if 'user_id' in session:
        user = User.query.get(session['user_id'])
        if user:
            if float(user.balance) > 0:
                db.session.add(WalletTransaction(
                    user_id=user.id, amount=-user.balance, type='account_deletion',
                    description=f'Eliminación de cuenta — saldo {float(user.balance):.2f} removido'
                ))
            user.name = 'Usuario eliminado'
            user.email = f'deleted_{user.id}@van.deleted'
            user.phone = ''
            user.password = 'DELETED'
            user.profile_picture = None
            user.balance = 0
            user.email_verified = False
            db.session.commit()
        session.clear()
        flash('Tu cuenta ha sido eliminada.', 'info')
        return jsonify({'success': True})

    if 'driver_id' in session:
        driver = Driver.query.get(session['driver_id'])
        if driver:
            if float(driver.balance) > 0:
                db.session.add(WalletTransaction(
                    driver_id=driver.id, amount=-driver.balance, type='account_deletion',
                    description=f'Eliminación de cuenta — saldo {float(driver.balance):.2f} removido'
                ))
            driver.is_online = False
            driver.is_ocupado = False
            driver.name = 'Conductor eliminado'
            driver.email = f'deleted_{driver.id}@van.deleted'
            driver.phone = ''
            driver.password = 'DELETED'
            driver.profile_picture = ''
            driver.balance = 0
            driver.email_verified = False
            db.session.commit()
        session.clear()
        flash('Tu cuenta ha sido eliminada.', 'info')
        return jsonify({'success': True})

    return jsonify({'error': 'No autorizado'}), 401


# ═══════════════════════════════════════════════
# ─── WALLET: Balance & Transactions ───
# ═══════════════════════════════════════════════

@main_bp.route('/api/wallet/balance')
@login_required
def api_wallet_balance():
    if 'user_id' not in session:
        return jsonify({'error': 'Debes ser pasajero'}), 401
    user = User.query.get(session['user_id'])
    return jsonify({'balance': float(user.balance) if user else 0.0})

@main_bp.route('/api/wallet/transactions')
@login_required
def api_wallet_transactions():
    if 'user_id' not in session:
        return jsonify({'error': 'Debes ser pasajero'}), 401
    txns = WalletTransaction.query.filter_by(user_id=session['user_id']).order_by(
        WalletTransaction.created_at.desc()
    ).limit(50).all()
    return jsonify({'transactions': [{
        'id': t.id, 'amount': t.amount, 'type': t.type,
        'description': t.description or '', 'reference': t.reference or '',
        'status': t.status, 'created_at': t.created_at.isoformat() if t.created_at else None
    } for t in txns]})

@main_bp.route('/api/driver/wallet/balance')
@login_required
def api_driver_wallet_balance():
    if 'driver_id' not in session:
        return jsonify({'error': 'Debes ser conductor'}), 401
    driver = Driver.query.get(session['driver_id'])
    return jsonify({'balance': float(driver.balance) if driver else 0.0})

@main_bp.route('/api/driver/wallet/transactions')
@login_required
def api_driver_wallet_transactions():
    if 'driver_id' not in session:
        return jsonify({'error': 'Debes ser conductor'}), 401
    txns = WalletTransaction.query.filter_by(driver_id=session['driver_id']).order_by(
        WalletTransaction.created_at.desc()
    ).limit(50).all()
    return jsonify({'transactions': [{
        'id': t.id, 'amount': t.amount, 'type': t.type,
        'description': t.description or '', 'reference': t.reference or '',
        'status': t.status, 'created_at': t.created_at.isoformat() if t.created_at else None
    } for t in txns]})


# ═══════════════════════════════════════════════
# ─── WALLET: Carga por MP Checkout ───
# ═══════════════════════════════════════════════

@main_bp.route('/api/wallet/topup', methods=['POST'])
@limiter.limit("5 per minute")
@login_required
@csrf_required
def api_wallet_topup():
    if 'user_id' not in session:
        return jsonify({'error': 'Debes ser pasajero'}), 401

    data = request.get_json(silent=True) or {}
    amount = data.get('amount', 0)
    method = data.get('method', 'mp_checkout')

    if not isinstance(amount, (int, float)) or amount < 100:
        return jsonify({'error': 'Monto mínimo $100'}), 400
    if amount > 500000:
        return jsonify({'error': 'Monto máximo $500.000'}), 400

    if method in ('mp_checkout', 'mercadopago'):
        token = os.getenv('MERCADOPAGO_ACCESS_TOKEN')
        if not token:
            return jsonify({'error': 'MercadoPago no configurado'}), 500

        import mercadopago
        sdk = mercadopago.SDK(token)
        base_url = os.getenv('BASE_URL', 'http://127.0.0.1:5000')

        preference_data = {
            "items": [{
                "id": "topup",
                "title": f"Recarga VAN - ${amount:.2f}",
                "quantity": 1,
                "unit_price": float(amount),
                "currency_id": "ARS"
            }],
            "external_reference": str(session['user_id']),
            "back_urls": {
                "success": base_url + "/wallet/topup/success",
                "failure": base_url + "/wallet/topup/failure",
                "pending": base_url + "/wallet/topup/pending"
            },
            "statement_descriptor": "VAN RECARGA",
            "expires": True,
            "expiration_date_from": (datetime.now(timezone.utc)).isoformat(),
            "expiration_date_to": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        }

        if '127.0.0.1' not in base_url and 'localhost' not in base_url:
            preference_data["auto_return"] = "approved"

        try:
            result = sdk.preference().create(preference_data)
            if result.get("status") in (200, 201):
                init_point = result["response"].get("init_point")
                return jsonify({"init_point": init_point})
            else:
                msg = result.get("response", {}).get("message", "Error desconocido")
                return jsonify({"error": f"MP: {msg}"}), 500
        except Exception as e:
            current_app.logger.error(f"Topup MP error: {e}")
            return jsonify({"error": "Error creando preferencia"}), 500

    return jsonify({"error": "Método no soportado"}), 400


@main_bp.route('/api/wallet/topup/webhook', methods=['GET', 'POST'])
def api_wallet_topup_webhook():
    if request.method == 'GET':
        challenge = request.args.get('challenge')
        if challenge:
            return challenge
        return 'ok'

    data = request.get_json(silent=True) or {}
    action = data.get('action')
    mp_id = data.get('data', {}).get('id')

    if not mp_id:
        return jsonify({'status': 'ok'})

    try:
        mp_id = int(mp_id)
    except (ValueError, TypeError):
        return jsonify({'status': 'ok'})

    if action not in ('payment.created', 'payment.updated'):
        return jsonify({'status': 'ok'})

    token = os.getenv('MERCADOPAGO_ACCESS_TOKEN')
    if not token:
        return jsonify({'status': 'ok'})

    try:
        import mercadopago
        sdk = mercadopago.SDK(token)
        payment_info = sdk.payment().get(mp_id)
        resp = payment_info.get('response', {})

        if resp.get('status') == 'approved' and resp.get('external_reference'):
            user_id = int(resp['external_reference'])
            amount = float(resp.get('transaction_amount', 0))

            user = db.session.query(User).filter_by(id=user_id).with_for_update().first()
            if user and amount > 0:
                existing = TopUpRequest.query.filter_by(
                    mp_payment_id=str(mp_id), status='confirmed'
                ).first()
                if existing:
                    return jsonify({'status': 'ok'})

                user.balance = round(float(user.balance) + amount, 2)
                req = TopUpRequest(
                    user_id=user_id, amount=amount, method='mp_checkout',
                    mp_payment_id=str(mp_id), status='confirmed',
                    confirmed_at=datetime.now(timezone.utc)
                )
                db.session.add(req)
                db.session.add(WalletTransaction(
                    user_id=user_id, amount=amount, type='deposit_mp',
                    reference=str(mp_id), description=f'Recarga MP ${amount:.2f}'
                ))
                db.session.commit()
                current_app.logger.info(f"Topup MP acreditado: user={user_id} ${amount}")
    except IntegrityError:
        db.session.rollback()
        current_app.logger.info(f"Topup MP duplicado ignorado: mp_id={mp_id}")
    except Exception as e:
        current_app.logger.error(f"Webhook topup error: {e}")
        db.session.rollback()

    return jsonify({'status': 'ok'})


@main_bp.route('/wallet/topup/success')
@login_required
def wallet_topup_success():
    flash('Recarga aprobada. Tu saldo se acreditó.', 'success')
    return redirect(url_for('main.dashboard'))


@main_bp.route('/wallet/topup/failure')
@login_required
def wallet_topup_failure():
    flash('La recarga no se completó. Intentá de nuevo.', 'danger')
    return redirect(url_for('main.dashboard'))


@main_bp.route('/wallet/topup/pending')
@login_required
def wallet_topup_pending():
    flash('Recarga pendiente. Se acreditará cuando se confirme.', 'info')
    return redirect(url_for('main.dashboard'))


# ═══════════════════════════════════════════════
# ─── WALLET: Carga por CVU MP ───
# ═══════════════════════════════════════════════

@main_bp.route('/api/wallet/cvu-info')
@login_required
def api_wallet_cvu_info():
    if 'user_id' not in session:
        return jsonify({'error': 'Debes ser pasajero'}), 401
    return jsonify({
        'cvu': os.getenv('MP_CVU', ''),
        'alias': os.getenv('MP_ALIAS', ''),
        'holder': 'VAN SRL',
    })


@main_bp.route('/api/wallet/topup/cvu', methods=['POST'])
@login_required
@csrf_required
def api_wallet_topup_cvu():
    if 'user_id' not in session:
        return jsonify({'error': 'Debes ser pasajero'}), 401

    data = request.get_json(silent=True) or {}
    amount = data.get('amount', 0)
    if not isinstance(amount, (int, float)) or amount < 100 or amount > 500000:
        return jsonify({'error': 'Monto debe ser entre $100 y $500.000'}), 400

    req = TopUpRequest(
        user_id=session['user_id'], amount=amount, method='mp_cvu',
        status='pending'
    )
    db.session.add(req)
    db.session.commit()

    return jsonify({'success': True, 'message': 'Esperando transferencia al CVU de VAN'})


# ═══════════════════════════════════════════════
# ─── WALLET: Carga por transferencia + comprobante ───
# ═══════════════════════════════════════════════

@main_bp.route('/api/wallet/bank-info')
@login_required
def api_wallet_bank_info():
    if 'user_id' not in session:
        return jsonify({'error': 'Debes ser pasajero'}), 401
    return jsonify({
        'bank_name': os.getenv('BANK_NAME', ''),
        'account_type': os.getenv('BANK_ACCOUNT_TYPE', ''),
        'account_number': os.getenv('BANK_ACCOUNT_NUMBER', ''),
        'holder': os.getenv('BANK_ACCOUNT_HOLDER', ''),
        'cuit': os.getenv('BANK_CUIT', ''),
        'alias': os.getenv('BANK_ALIAS', ''),
    })


@main_bp.route('/api/wallet/topup/voucher', methods=['POST'])
@login_required
@csrf_required
def api_wallet_topup_voucher():
    if 'user_id' not in session:
        return jsonify({'error': 'Debes ser pasajero'}), 401

    amount = request.form.get('amount', type=float)
    if not amount or amount < 100:
        return jsonify({'error': 'Monto mínimo $100'}), 400

    voucher_url = None
    voucher_file = request.files.get('voucher')
    if voucher_file and voucher_file.filename:
        ext = secure_filename(voucher_file.filename).rsplit('.', 1)[-1].lower()
        if ext not in ('png', 'jpg', 'jpeg', 'gif', 'webp', 'pdf'):
            return jsonify({'error': 'Formato no válido'}), 400
        voucher_file.seek(0, 2)
        if voucher_file.tell() > 5 * 1024 * 1024:
            return jsonify({'error': 'Archivo muy grande (máx 5MB)'}), 400
        voucher_file.seek(0)
        folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads', 'vouchers')
        os.makedirs(folder, exist_ok=True)
        filename = f'voucher_{uuid.uuid4().hex}.{ext}'
        filepath = os.path.join(folder, filename)
        voucher_file.save(filepath)
        voucher_url = f'/static/uploads/vouchers/{filename}'

    req = TopUpRequest(
        user_id=session['user_id'], amount=amount, method='bank_transfer',
        voucher_url=voucher_url, status='pending'
    )
    db.session.add(req)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        if voucher_url:
            try:
                os.remove(filepath)
            except (OSError, UnboundLocalError):
                pass
        raise

    flash('Comprobante enviado. Se confirmará en 24-48hs hábiles.', 'info')
    return jsonify({'success': True})


# ═══════════════════════════════════════════════
# ─── WALLET: Pago por QR del conductor ───
# ═══════════════════════════════════════════════

@main_bp.route('/api/wallet/pay-driver', methods=['POST'])
@limiter.limit("10 per minute")
@login_required
@csrf_required
def api_wallet_pay_driver():
    if 'user_id' not in session:
        return jsonify({'error': 'Debes ser pasajero'}), 401

    data = request.get_json(silent=True) or {}
    driver_id = data.get('driver_id')
    amount = data.get('amount', 0)
    trip_id = data.get('trip_id')

    if not driver_id or not isinstance(amount, (int, float)) or amount <= 0:
        return jsonify({'error': 'Datos inválidos'}), 400

    passenger = db.session.query(User).filter_by(id=session['user_id']).with_for_update().first()
    driver = db.session.query(Driver).filter_by(id=driver_id).with_for_update().first()
    if not driver:
        return jsonify({'error': 'Conductor no encontrado'}), 404
    if float(passenger.balance) < amount:
        return jsonify({'error': 'Saldo insuficiente'}), 400

    passenger.balance = round(float(passenger.balance) - amount, 2)
    driver.balance = round(float(driver.balance) + amount, 2)

    desc = f'Pago al conductor {driver.name}'
    if trip_id:
        desc += f' (viaje #{trip_id})'

    db.session.add(WalletTransaction(
        user_id=passenger.id, driver_id=driver.id, amount=-amount,
        type='trip_payment', trip_id=trip_id, description=desc
    ))
    db.session.add(WalletTransaction(
        driver_id=driver.id, user_id=passenger.id, amount=amount,
        type='trip_payment', trip_id=trip_id, description=desc
    ))
    db.session.commit()

    return jsonify({'success': True, 'message': f'Pago de ${amount:.2f} realizado'})


# ═══════════════════════════════════════════════
# ─── ADMIN: Panel de comprobantes ───
# ═══════════════════════════════════════════════

@main_bp.route('/admin/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute", methods=["POST"])
def admin_login():
    admin_key = os.getenv('ADMIN_SECRET_KEY', '')
    if not admin_key:
        return 'ADMIN_SECRET_KEY no configurado', 500
    if request.method == 'POST':
        token = request.form.get('csrf_token') or request.headers.get('X-CSRF-Token')
        if not token or not hmac.compare_digest(str(token), str(session.get('csrf_token', ''))):
            flash('Token CSRF inválido', 'danger')
            return redirect(url_for('main.admin_login'))
        key = request.form.get('key', '')
        if key and hmac.compare_digest(str(key), str(admin_key)):
            session.clear()
            session['csrf_token'] = secrets.token_hex(32)
            session['is_admin'] = True
            flash('Sesión admin activa', 'success')
            return redirect(url_for('main.admin_topups'))
        flash('Clave incorrecta', 'danger')
    return render_template('admin/login.html')

@main_bp.route('/admin/logout', methods=['POST'])
@csrf_required
def admin_logout():
    session.pop('is_admin', None)
    flash('Sesión admin cerrada', 'info')
    return redirect(url_for('main.admin_login'))

@main_bp.route('/admin/topups')
@admin_required
def admin_topups():
    status_filter = request.args.get('status', 'pending')
    query = TopUpRequest.query
    if status_filter and status_filter != 'all':
        query = query.filter_by(status=status_filter)
    requests_list = query.order_by(TopUpRequest.created_at.desc()).limit(100).all()

    is_api = request.headers.get('Accept') == 'application/json'

    rows = []
    for r in requests_list:
        user = User.query.get(r.user_id) if r.user_id else None
        rows.append({
            'id': r.id, 'amount': r.amount, 'method': r.method,
            'status': r.status, 'voucher_url': r.voucher_url,
            'mp_payment_id': r.mp_payment_id, 'admin_note': r.admin_note,
            'user_name': user.name if user else '?', 'user_email': user.email if user else '?',
            'user_id': r.user_id,
            'created_at': r.created_at.strftime('%d/%m %H:%M') if r.created_at else '',
        })

    if is_api:
        return jsonify({'requests': rows, 'status_filter': status_filter})

    return render_template('admin/topups.html', requests=rows, status_filter=status_filter)


@main_bp.route('/admin/topups/<int:req_id>/confirm', methods=['POST'])
@admin_required
@csrf_required
def admin_topup_confirm(req_id):
    req = TopUpRequest.query.get(req_id)
    if not req:
        return jsonify({'error': 'No encontrado'}), 404
    if req.status != 'pending':
        return jsonify({'error': 'Ya procesado'}), 400

    user = db.session.query(User).filter_by(id=req.user_id).with_for_update().first()
    if user:
        user.balance = round(float(user.balance) + float(req.amount), 2)
        db.session.add(WalletTransaction(
            user_id=user.id, amount=req.amount, type=f'deposit_{req.method}',
            reference=str(req.id), description=f'Recarga {req.method} ${req.amount:.2f}'
        ))

    req.status = 'confirmed'
    req.confirmed_at = datetime.now(timezone.utc)
    db.session.commit()

    is_api = request.headers.get('Accept') == 'application/json'
    if is_api:
        return jsonify({'success': True, 'message': f'Saldo ${req.amount:.2f} acreditado a {user.name if user else "?"}'})

    flash(f'Saldo ${req.amount:.2f} acreditado a {user.name if user else "?"}', 'success')
    return redirect(url_for('main.admin_topups', status=request.args.get('status', 'pending')))


@main_bp.route('/admin/topups/<int:req_id>/reject', methods=['POST'])
@admin_required
@csrf_required
def admin_topup_reject(req_id):
    req = TopUpRequest.query.get(req_id)
    if not req:
        return jsonify({'error': 'No encontrado'}), 404
    if req.status != 'pending':
        return jsonify({'error': 'Ya procesado'}), 400

    data = request.get_json(silent=True) or {}
    req.status = 'rejected'
    req.admin_note = data.get('note', request.form.get('note', ''))
    db.session.commit()

    is_api = request.headers.get('Accept') == 'application/json'
    if is_api:
        return jsonify({'success': True})

    flash('Solicitud rechazada', 'info')
    return redirect(url_for('main.admin_topups', status=request.args.get('status', 'pending')))


# ═══════════════════════════════════════════════
# ─── ADMIN: Driver Verification ───
# ═══════════════════════════════════════════════

@main_bp.route('/admin/drivers')
@admin_required
def admin_drivers():
    status_filter = request.args.get('status', 'pending')
    if status_filter == 'verified':
        drivers = Driver.query.filter_by(is_verified=True).order_by(Driver.created_at.desc()).limit(100).all()
    elif status_filter == 'pending':
        drivers = Driver.query.filter_by(is_verified=False).order_by(Driver.created_at.desc()).limit(100).all()
    else:
        drivers = Driver.query.order_by(Driver.created_at.desc()).limit(100).all()

    is_api = request.headers.get('Accept') == 'application/json'
    rows = [{
        'id': d.id, 'name': d.name, 'email': d.email, 'phone': d.phone,
        'vehicle_type': d.vehicle_type, 'is_verified': d.is_verified,
        'carnet_conducir': d.carnet_conducir,
        'placa': d.placa or d.placa_auto or '',
        'profile_picture': d.profile_picture,
        'created_at': d.created_at.strftime('%d/%m/%Y') if d.created_at else '',
    } for d in drivers]

    if is_api:
        return jsonify({'drivers': rows, 'status_filter': status_filter})

    return render_template('admin/drivers.html', drivers=rows, status_filter=status_filter)


@main_bp.route('/admin/drivers/<int:driver_id>/verify', methods=['POST'])
@admin_required
@csrf_required
def admin_verify_driver(driver_id):
    driver = Driver.query.get(driver_id)
    if not driver:
        return jsonify({'error': 'No encontrado'}), 404

    action = request.form.get('action') or (request.get_json(silent=True) or {}).get('action', 'verify')
    driver.is_verified = (action == 'verify')
    db.session.commit()

    is_api = request.headers.get('Accept') == 'application/json'
    if is_api:
        return jsonify({'success': True, 'is_verified': driver.is_verified})

    flash(f'Conductor {driver.name} {"verificado" if driver.is_verified else "desverificado"}', 'success')
    return redirect(url_for('main.admin_drivers', status=request.args.get('status', 'pending')))
