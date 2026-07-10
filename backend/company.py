import os
import json
import hmac
from functools import wraps
from datetime import datetime
from flask import Blueprint, render_template, session, request, redirect, url_for, flash, jsonify
from .models import db, User, Driver, Trip, Company, CompanyMember
from werkzeug.security import generate_password_hash, check_password_hash
from .routes import csrf_required

company_bp = Blueprint('company', __name__, url_prefix='/company')

PLAN_PRICES = {
    'basic': (60000, 'Básico'),
    'advanced': (90000, 'Avanzado'),
}


def company_login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'company_id' not in session:
            flash('Debes iniciar sesión como empresa', 'danger')
            return redirect(url_for('company.login'))
        company = Company.query.get(session['company_id'])
        if company and company.status != 'active':
            if company.status == 'pending_payment':
                return redirect(url_for('company.payment'))
            flash('Tu suscripción está inactiva. Contacta al administrador.', 'danger')
            return redirect(url_for('company.logout'))
        return f(*args, **kwargs)
    return decorated


def get_mp_sdk():
    token = os.getenv('MERCADOPAGO_ACCESS_TOKEN')
    if not token:
        return None
    import mercadopago
    return mercadopago.SDK(token)


def get_base_url():
    return os.getenv('BASE_URL', 'http://127.0.0.1:5000')


@company_bp.route('/')
def landing():
    return render_template('company/landing.html')


@company_bp.route('/register', methods=['GET'])
def register_get():
    return render_template('company/register.html')


@company_bp.route('/register', methods=['POST'])
@csrf_required
def register_post():
    name = request.form.get('name')
    email = request.form.get('email')
    password = request.form.get('password')
    phone = request.form.get('phone')
    plan = request.form.get('plan', 'basic')

    if Company.query.filter_by(email=email).first():
        flash('Correo electrónico ya registrado', 'warning')
        return redirect(url_for('company.register_get'))

    max_emp = 15 if plan == 'basic' else 9999
    comp = Company(
        name=name, email=email,
        password=generate_password_hash(password),
        phone=phone, plan=plan,
        status='pending_payment',
        max_employees=max_emp,
    )
    db.session.add(comp)
    db.session.commit()

    session['company_id'] = comp.id
    session['company_name'] = comp.name
    flash('Registro exitoso. Ahora elige tu método de pago.', 'success')
    return redirect(url_for('company.payment'))


@company_bp.route('/payment')
def payment():
    if 'company_id' not in session:
        return redirect(url_for('company.login'))
    company = Company.query.get(session['company_id'])
    if not company:
        return redirect(url_for('company.logout'))
    if company.status == 'active':
        return redirect(url_for('company.dashboard'))
    if company.payment_method == 'transfer':
        return redirect(url_for('company.payment_pending_review'))
    price, label = PLAN_PRICES.get(company.plan, (60000, 'Básico'))
    return render_template('company/payment.html',
                           company=company,
                           price=price,
                           plan_label=label,
                           bank_name=os.getenv('BANK_NAME', 'Banco Nación'),
                           bank_account_type=os.getenv('BANK_ACCOUNT_TYPE', 'Caja de Ahorro'),
                           bank_account_number=os.getenv('BANK_ACCOUNT_NUMBER', ''),
                           bank_holder=os.getenv('BANK_ACCOUNT_HOLDER', 'VAN SRL'),
                           bank_cuit=os.getenv('BANK_CUIT', ''),
                           bank_alias=os.getenv('BANK_ALIAS', ''),
                           mp_public_key=os.getenv('MERCADOPAGO_PUBLIC_KEY', ''))


@company_bp.route('/api/create_preference', methods=['POST'])
@csrf_required
def create_preference():
    if 'company_id' not in session:
        return jsonify({'error': 'No autorizado'}), 401
    company = Company.query.get(session['company_id'])
    if not company:
        return jsonify({'error': 'Empresa no encontrada'}), 404

    price, label = PLAN_PRICES.get(company.plan, (60000, 'Básico'))
    sdk = get_mp_sdk()
    if not sdk:
        return jsonify({'error': 'Mercado Pago no configurado. Contacta al administrador.'}), 500

    preference_data = {
        'items': [{
            'title': f'Plan {label} — VAN para Empresas',
            'quantity': 1,
            'currency_id': 'ARS',
            'unit_price': float(price),
        }],
        'back_urls': {
            'success': f'{get_base_url()}/company/payment/success',
            'failure': f'{get_base_url()}/company/payment/failure',
            'pending': f'{get_base_url()}/company/payment/pending',
        },
        # 'auto_return': 'approved',  # comentado para desarrollo local
        'external_reference': str(company.id),
        # 'notification_url': f'{get_base_url()}/company/payment/webhook',  # comentado para desarrollo local
    }

    try:
        preference = sdk.preference().create(preference_data)
        if preference.get('status') == 201:
            return jsonify({
                'id': preference['response']['id'],
                'init_point': preference['response']['init_point'],
            })
        else:
            err = preference.get('response', {})
            msg = err.get('message', 'Error desconocido de Mercado Pago')
            return jsonify({'error': f'Mercado Pago: {msg}'}), 500
    except Exception as e:
        return jsonify({'error': f'Error al crear preferencia: {str(e)}'}), 500


@company_bp.route('/payment/success')
def payment_success():
    if 'company_id' not in session:
        return redirect(url_for('company.login'))
    payment_id = request.args.get('payment_id')
    comp = Company.query.get(session['company_id'])
    if comp and comp.status == 'pending_payment':
        comp.status = 'active'
        comp.subscription_start = datetime.utcnow()
        comp.payment_method = 'mercadopago'
        comp.payment_reference = payment_id
        db.session.commit()
        flash('¡Pago exitoso! Tu plan ya está activo.', 'success')
    return redirect(url_for('company.dashboard'))


@company_bp.route('/payment/failure')
def payment_failure():
    flash('El pago no se completó. Podés intentar de nuevo.', 'danger')
    return redirect(url_for('company.payment'))


@company_bp.route('/payment/pending')
def payment_pending():
    flash('El pago está pendiente. Te avisaremos cuando se confirme.', 'info')
    return redirect(url_for('company.payment'))


@company_bp.route('/payment/webhook', methods=['POST'])
def payment_webhook():
    data = request.get_json(silent=True) or {}
    action = data.get('action') or request.form.get('topic') or request.args.get('topic')
    mp_id = data.get('data', {}).get('id') or request.form.get('id')

    if not mp_id:
        return jsonify({'status': 'ok'})

    if action == 'payment.created' or (not action and mp_id):
        try:
            sdk = get_mp_sdk()
            if sdk:
                payment_info = sdk.payment().get(mp_id)
                resp = payment_info.get('response', {})
                if resp.get('status') == 'approved':
                    company_id = int(resp.get('external_reference', 0))
                    if company_id:
                        comp = Company.query.get(company_id)
                        if comp and comp.status == 'pending_payment':
                            comp.status = 'active'
                            comp.subscription_start = datetime.utcnow()
                            comp.payment_method = 'mercadopago'
                            comp.payment_reference = mp_id
                            db.session.commit()
        except Exception as e:
            current_app.logger.error(f"Webhook error: {e}")
    return jsonify({'status': 'ok'})


@company_bp.route('/payment/confirm_transfer', methods=['POST'])
@csrf_required
def confirm_transfer():
    if 'company_id' not in session:
        return jsonify({'error': 'No autorizado'}), 401
    company = Company.query.get(session['company_id'])
    if not company or company.status != 'pending_payment':
        return jsonify({'error': 'No válido'}), 400

    company.payment_method = 'transfer'
    company.payment_reference = f'transfer_{datetime.utcnow().timestamp()}'
    db.session.commit()
    flash('Solicitud enviada. Te confirmaremos por correo cuando recibamos la transferencia.', 'success')
    return redirect(url_for('company.payment_pending_review'))


@company_bp.route('/payment/pending_review')
def payment_pending_review():
    if 'company_id' not in session:
        return redirect(url_for('company.login'))
    return render_template('company/pending_review.html')


@company_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        company = Company.query.filter_by(email=email).first()
        if company and check_password_hash(company.password, password):
            if company.status == 'inactive':
                flash('Tu suscripción está inactiva. Contacta al administrador.', 'danger')
                return redirect(url_for('company.login'))
            session['company_id'] = company.id
            session['company_name'] = company.name
            if company.status == 'pending_payment':
                return redirect(url_for('company.payment'))
            flash(f'Bienvenido {company.name}', 'success')
            return redirect(url_for('company.dashboard'))

        flash('Credenciales inválidas', 'danger')
    return render_template('company/login.html')


@company_bp.route('/logout')
def logout():
    session.pop('company_id', None)
    session.pop('company_name', None)
    flash('Sesión cerrada', 'info')
    return redirect(url_for('company.landing'))


@company_bp.route('/dashboard')
@company_login_required
def dashboard():
    company = Company.query.get(session['company_id'])
    members = CompanyMember.query.filter_by(company_id=company.id).all()
    member_ids = [m.user_id for m in members]
    company_trips = Trip.query.filter(Trip.company_id == company.id).order_by(Trip.requested_at.desc()).limit(50).all()
    employee_users = User.query.filter(User.id.in_(member_ids)).all() if member_ids else []

    total_trips = len(company_trips)
    total_spent = sum(t.fare for t in company_trips if t.status == 'completed')
    active_members = sum(1 for m in members if m.joined_at is not None)

    return render_template(
        'company/dashboard.html',
        company=company,
        members=members,
        employee_users=employee_users,
        company_trips=company_trips,
        total_trips=total_trips,
        total_spent=total_spent,
        active_members=active_members
    )


@company_bp.route('/api/members', methods=['GET'])
@company_login_required
def api_members():
    company = Company.query.get(session['company_id'])
    members = CompanyMember.query.filter_by(company_id=company.id).all()
    result = []
    for m in members:
        user = User.query.get(m.user_id)
        if user:
            result.append({
                'id': m.id,
                'user_id': user.id,
                'name': user.name,
                'email': user.email,
                'role': m.role,
                'joined': m.joined_at.isoformat() if m.joined_at else None,
                'invited': m.invited_at.isoformat() if m.invited_at else None,
            })
    return jsonify({'members': result})


@company_bp.route('/api/invite', methods=['POST'])
@csrf_required
@company_login_required
def api_invite():
    company = Company.query.get(session['company_id'])
    data = request.get_json(silent=True) or {}
    email = data.get('email', '').strip().lower()

    if not email:
        return jsonify({'error': 'Correo electrónico requerido'}), 400

    current_count = CompanyMember.query.filter_by(company_id=company.id).count()
    if current_count >= company.max_employees:
        return jsonify({'error': f'Límite de {company.max_employees} empleados alcanzado'}), 400

    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({'error': 'El usuario debe registrarse primero en VAN'}), 404

    existing = CompanyMember.query.filter_by(company_id=company.id, user_id=user.id).first()
    if existing:
        return jsonify({'error': 'El usuario ya es miembro'}), 400

    member = CompanyMember(company_id=company.id, user_id=user.id, role='employee')
    db.session.add(member)
    db.session.commit()

    return jsonify({'success': True, 'name': user.name, 'email': user.email})


@company_bp.route('/api/members/<int:member_id>/remove', methods=['POST'])
@csrf_required
@company_login_required
def api_remove_member(member_id):
    company = Company.query.get(session['company_id'])
    member = CompanyMember.query.get(member_id)
    if not member or member.company_id != company.id:
        return jsonify({'error': 'Miembro no encontrado'}), 404

    db.session.delete(member)
    db.session.commit()
    return jsonify({'success': True})


@company_bp.route('/api/trips')
@company_login_required
def api_trips():
    company = Company.query.get(session['company_id'])
    days = request.args.get('days', 30, type=int)
    from datetime import timedelta
    cutoff = datetime.utcnow() - timedelta(days=days)

    trips = Trip.query.filter(
        Trip.company_id == company.id,
        Trip.requested_at >= cutoff
    ).order_by(Trip.requested_at.desc()).all()

    result = []
    for t in trips:
        driver = Driver.query.get(t.driver_id) if t.driver_id else None
        result.append({
            'id': t.id,
            'pickup': t.pickup_address,
            'dropoff': t.dropoff_address,
            'fare': t.fare,
            'status': t.status,
            'vehicle_type': t.vehicle_type,
            'driver_name': driver.name if driver else None,
            'requested_at': t.requested_at.isoformat() if t.requested_at else None,
        })
    return jsonify({'trips': result, 'total': sum(t.fare for t in trips if t.status == 'completed')})


# ─── Admin: activar empresa por transferencia ───
@company_bp.route('/api/admin/activate/<int:company_id>', methods=['POST'])
def admin_activate(company_id):
    auth = request.headers.get('Authorization', '')
    admin_key = os.getenv('ADMIN_SECRET_KEY', '')
    if not admin_key or not hmac.compare_digest(auth, f'Bearer {admin_key}'):
        return jsonify({'error': 'No autorizado'}), 401
    comp = Company.query.get(company_id)
    if not comp:
        return jsonify({'error': 'Empresa no encontrada'}), 404
    comp.status = 'active'
    comp.subscription_start = datetime.utcnow()
    db.session.commit()
    return jsonify({'success': True, 'name': comp.name})
