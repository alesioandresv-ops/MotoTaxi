import os
import re
import uuid
import hmac
import secrets
import string
import smtplib
import base64
import io
import time
from email.mime.text import MIMEText

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
    jsonify,
)
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.exc import IntegrityError

from .models import (
    db,
    User,
    DriverProfile,
    Vehicle,
    Trip,
    Review,
    ROLE_DRIVER,
    ROLE_BOTH,
    MODE_DRIVER,
    MODE_PASSENGER,
)
from .routes import login_required, csrf_required, sanitize_input
from .validators import validate_name, validate_email, validate_password, first_error
from .extensions import limiter
from .services.identity import (
    current_user,
    current_driver_profile,
    set_session,
    switch_mode,
    allowed_modes,
    driver_view,
)

auth_bp = Blueprint('auth', __name__)

UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}
MAX_UPLOAD_BYTES = 2 * 1024 * 1024  # 2MB


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def validate_upload_size(file):
    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)
    return size <= 5 * 1024 * 1024


def validate_image_content(file):
    try:
        from PIL import Image

        file.seek(0)
        Image.open(file).verify()
        file.seek(0)
        return True
    except Exception:
        return False


def save_driver_photo(file_or_bytes):
    try:
        if isinstance(file_or_bytes, bytes):
            data = file_or_bytes
        else:
            file_or_bytes.seek(0)
            data = file_or_bytes.read()
            file_or_bytes.seek(0)

        if len(data) > MAX_UPLOAD_BYTES:
            return None, 'max_size'

        from PIL import Image

        img = Image.open(io.BytesIO(data))
        img = img.convert('RGB')
        img.thumbnail((800, 800), Image.LANCZOS)

        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        filename = f"driver_{uuid.uuid4().hex}_{int(time.time())}.webp"
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        img.save(filepath, 'WEBP', quality=85)
        return f'/static/uploads/{filename}', None
    except Exception:
        return None, 'invalid'


def save_base64_image(image_data):
    try:
        if ',' in image_data:
            image_data = image_data.split(',', 1)[1]
        raw = base64.b64decode(image_data)
        if len(raw) > MAX_UPLOAD_BYTES:
            return None
        return save_driver_photo(raw)[0]
    except Exception:
        return None


def send_verification_email(email, code):
    try:
        smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        smtp_port = int(os.getenv('SMTP_PORT', 587))
        smtp_user = os.getenv('SMTP_USER', '')
        smtp_pass = os.getenv('SMTP_PASS', '')

        if not smtp_user or not smtp_pass:
            return False

        msg = MIMEText(f'Tu código de verificación de VAN es: {code}\n\nEste código expira en 10 minutos.')
        msg['Subject'] = 'Verifica tu correo - VAN'
        msg['From'] = smtp_user
        msg['To'] = email

        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_user, [email], msg.as_string())
        server.quit()
        return True
    except Exception:
        return False


# ─── Registro ───

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        token = request.form.get('csrf_token') or request.headers.get('X-CSRF-Token')
        if not token or not hmac.compare_digest(str(token), str(session.get('csrf_token', ''))):
            flash('Token CSRF inválido', 'danger')
            return redirect(url_for('auth.register'))
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        phone = request.form.get('phone', '').strip()

        err = first_error(validate_name(name), validate_email(email), validate_password(password))
        if err:
            flash(err, 'danger')
            return redirect(url_for('auth.register'))

        if User.query.filter_by(email=email).first():
            flash('Correo electrónico ya registrado', 'warning')
            return redirect(url_for('auth.register'))
        user = User(name=name, email=email, password=generate_password_hash(password), phone=phone)
        db.session.add(user)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash('Correo electrónico ya registrado', 'warning')
            return redirect(url_for('auth.register'))

        code = ''.join(secrets.choice(string.digits) for _ in range(6))
        session['verify_code'] = code
        session['verify_user_id'] = user.id
        session['verify_email'] = email

        if send_verification_email(email, code):
            flash('Registro exitoso. Revisa tu correo para verificar tu cuenta.', 'success')
            return redirect(url_for('auth.verify_email'))
        else:
            flash('Registro exitoso. No se pudo enviar correo de verificación (configura SMTP en .env).', 'success')
            return redirect(url_for('auth.login'))
    return render_template('register.html')


@auth_bp.route('/verify-email', methods=['GET', 'POST'])
@limiter.limit("5 per minute", methods=["POST"])
def verify_email():
    if 'verify_code' not in session:
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        token = request.form.get('csrf_token') or request.headers.get('X-CSRF-Token')
        if not token or not hmac.compare_digest(str(token), str(session.get('csrf_token', ''))):
            flash('Token CSRF inválido', 'danger')
            return redirect(url_for('auth.verify_email'))
        code = request.form.get('code', '').strip()
        if hmac.compare_digest(str(code), str(session.get('verify_code', ''))):
            user = User.query.get(session['verify_user_id'])
            if user:
                user.email_verified = True
                db.session.commit()
            session.pop('verify_code', None)
            session.pop('verify_user_id', None)
            session.pop('verify_email', None)
            flash('Correo verificado exitosamente. Ahora puedes iniciar sesión.', 'success')
            return redirect(url_for('auth.login'))
        else:
            flash('Código incorrecto. Intenta de nuevo.', 'danger')

    return render_template('verify_email.html', email=session.get('verify_email'))


def _build_vehicle(vehicle_type, form):
    """Crea Vehicle desde el form del registro web (moto o auto)."""
    if vehicle_type == 'moto':
        return Vehicle(
            type='moto',
            placa=sanitize_input(form.get('placa')),
            marca=sanitize_input(form.get('moto_marca')),
            modelo=sanitize_input(form.get('moto_modelo')),
            color=sanitize_input(form.get('moto_color')),
            cilindrada=sanitize_input(form.get('moto_cilindrada')),
            has_patente=form.get('tiene_patente') == 'yes',
            has_casco=form.get('tiene_casco') == 'yes',
            has_seguro=form.get('seguro_moto') == 'yes',
            tipo_seguro=sanitize_input(form.get('tipo_seguro')),
            carnet_conducir=sanitize_input(form.get('carnet_conducir')),
            ultimo_servicio=sanitize_input(form.get('ultimo_servicio')),
            is_active=True,
        )
    return Vehicle(
        type='auto',
        placa=sanitize_input(form.get('placa_auto')),
        marca=sanitize_input(form.get('auto_marca')),
        modelo=sanitize_input(form.get('auto_modelo')),
        color=sanitize_input(form.get('auto_color')),
        anio=sanitize_input(form.get('auto_año')),
        has_patente=form.get('tiene_patente_auto') == 'yes',
        has_seguro=form.get('seguro_auto') == 'yes',
        tipo_seguro=sanitize_input(form.get('tipo_seguro_auto')),
        carnet_conducir=sanitize_input(
            form.get('carnet_conducir_auto') or form.get('carnet_conducir')
        ),
        ultimo_servicio=sanitize_input(form.get('ultimo_servicio_auto')),
        is_active=True,
    )


@auth_bp.route('/driver/register', methods=['GET', 'POST'])
def driver_register():
    if request.method == 'POST':
        token = request.form.get('csrf_token') or request.headers.get('X-CSRF-Token')
        if not token or not hmac.compare_digest(str(token), str(session.get('csrf_token', ''))):
            flash('Token CSRF inválido', 'danger')
            return redirect(url_for('auth.driver_register'))
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        phone = request.form.get('phone', '').strip()
        vehicle_type = request.form.get('vehicle_type', 'moto')

        err = first_error(validate_name(name), validate_email(email), validate_password(password))
        if err:
            flash(err, 'danger')
            return redirect(url_for('auth.driver_register'))

        profile_picture = None
        err = 'missing'
        if 'profile_picture' in request.files:
            f = request.files['profile_picture']
            if f and f.filename:
                ext = f.filename.rsplit('.', 1)[1].lower() if '.' in f.filename else ''
                if ext not in ALLOWED_EXTENSIONS:
                    flash('Solo se permiten imágenes JPG, PNG o WEBP', 'danger')
                    return redirect(url_for('auth.driver_register'))
                profile_picture, err = save_driver_photo(f)
            else:
                err = 'missing'
        else:
            err = 'missing'

        if err == 'max_size':
            flash('La imagen debe pesar menos de 2MB', 'danger')
            return redirect(url_for('auth.driver_register'))
        elif err == 'invalid':
            flash('El archivo no es una imagen válida.', 'danger')
            return redirect(url_for('auth.driver_register'))
        elif err == 'missing' or not profile_picture:
            flash('La foto de perfil es obligatoria para conductores.', 'danger')
            return redirect(url_for('auth.driver_register'))

        vehicle = _build_vehicle(vehicle_type, request.form)
        required_fields = [name, email, password, phone, vehicle.placa, vehicle.marca,
                           vehicle.modelo, vehicle.color, vehicle.tipo_seguro,
                           vehicle.carnet_conducir, vehicle.ultimo_servicio]
        if vehicle_type == 'auto':
            required_fields.append(vehicle.anio)
        if not all(required_fields):
            flash('Por favor completa todos los campos obligatorios.', 'danger')
            return redirect(url_for('auth.driver_register'))

        # Identidad única: mismo email = misma cuenta. Pasajero existente → 'both'.
        existing = User.query.filter_by(email=email).first()
        if existing:
            if existing.role != 'passenger':
                flash('El correo electrónico ya está registrado', 'warning')
                return redirect(url_for('auth.driver_register'))
            user = existing
            user.role = ROLE_BOTH
            user.phone = user.phone or phone
            if not user.profile_picture:
                user.profile_picture = profile_picture
            if user.driver_profile is None:
                user.driver_profile = DriverProfile(user_id=user.id, vehicles=[vehicle])
            else:
                user.driver_profile.vehicles.append(vehicle)
            db.session.add(user)
        else:
            user = User(
                name=name, email=email, password=generate_password_hash(password),
                phone=phone, profile_picture=profile_picture, role=ROLE_DRIVER,
            )
            profile = DriverProfile(user_id=user.id, vehicles=[vehicle])
            user.driver_profile = profile
            db.session.add(user)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash('Correo electrónico ya registrado', 'warning')
            return redirect(url_for('auth.driver_register'))

        code = ''.join(secrets.choice(string.digits) for _ in range(6))
        session['verify_code'] = code
        session['verify_user_id'] = user.id
        session['verify_email'] = email

        if send_verification_email(email, code):
            flash('Registro exitoso. Revisa tu correo para verificar tu cuenta.', 'success')
            return redirect(url_for('auth.verify_email'))
        else:
            flash('Registro exitoso.', 'success')
            return redirect(url_for('auth.login'))
    return render_template('driver_register.html')


@auth_bp.route('/verify-email-driver', methods=['GET', 'POST'])
@limiter.limit("5 per minute", methods=["POST"])
def verify_email_driver():
    # ruta legacy: ahora la verificación es idéntica para todos los roles
    return verify_email()


# ─── Login / logout / modos ───

@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute", methods=["POST"])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        smtp_configured = bool(os.getenv('SMTP_SERVER') and os.getenv('SMTP_USER') and os.getenv('SMTP_PASS'))

        user = User.query.filter_by(email=email).first()
        if not user or not check_password_hash(user.password, password):
            flash('Credenciales inválidas', 'danger')
            return render_template('login.html')

        if smtp_configured and not user.email_verified:
            flash('Debes verificar tu correo antes de iniciar sesión. Revisa tu bandeja de entrada.', 'warning')
            return redirect(url_for('auth.login'))

        if user.role == ROLE_BOTH:
            # identidad dual → el usuario elige el modo antes de entrar
            set_session(user, mode=None)
            return redirect(url_for('auth.select_mode'))

        mode = MODE_DRIVER if user.role == ROLE_DRIVER else MODE_PASSENGER
        set_session(user, mode=mode)
        flash('Bienvenido ' + user.name, 'success')
        return redirect(url_for('main.dashboard'))

    return render_template('login.html')


@auth_bp.route('/select-mode', methods=['GET', 'POST'])
@login_required
def select_mode():
    user = current_user()
    if not user or user.role != ROLE_BOTH:
        return redirect(url_for('auth.login'))
    modes = allowed_modes(user)
    if len(modes) < 2:
        # rol both pero sin perfil completo: no debería pasar, modo por defecto
        set_session(user, mode=modes[0] if modes else MODE_PASSENGER)
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        token = request.form.get('csrf_token') or request.headers.get('X-CSRF-Token')
        if not token or not hmac.compare_digest(str(token), str(session.get('csrf_token', ''))):
            flash('Token CSRF inválido', 'danger')
            return redirect(url_for('auth.select_mode'))
        target = request.form.get('mode', '')
        if target not in (MODE_PASSENGER, MODE_DRIVER):
            flash('Modo inválido', 'danger')
            return redirect(url_for('auth.select_mode'))
        switch_mode(target)
        flash('Modo activo: ' + ('Conductor' if target == MODE_DRIVER else 'Pasajero'), 'info')
        return redirect(url_for('main.dashboard'))

    return render_template('select_mode.html', user=user, modes=modes)


@auth_bp.route('/switch-mode', methods=['POST'])
@login_required
@csrf_required
def switch_mode_route():
    target = request.form.get('mode', '') or (request.get_json(silent=True) or {}).get('mode', '')
    if target not in (MODE_PASSENGER, MODE_DRIVER) or not switch_mode(target):
        if request.is_json:
            return jsonify({'success': False, 'error': 'Modo no permitido'}), 400
        flash('Modo no permitido', 'danger')
        return redirect(request.referrer or url_for('main.dashboard'))
    if request.is_json:
        return jsonify({'success': True, 'mode': target})
    flash('Modo activo: ' + ('Conductor' if target == MODE_DRIVER else 'Pasajero'), 'info')
    return redirect(request.referrer or url_for('main.dashboard'))


@auth_bp.route('/logout', methods=['POST'])
@csrf_required
def logout():
    profile = current_driver_profile()
    if profile:
        profile.is_online = False
        profile.is_busy = False
        db.session.commit()
    session.clear()
    flash('Sesión cerrada', 'info')
    return redirect(url_for('main.index'))


# ─── Perfil ───

@auth_bp.route('/profile')
@login_required
def profile():
    user = current_user()
    if not user:
        return redirect(url_for('auth.login'))
    trips = Trip.query.filter_by(passenger_id=user.id).order_by(Trip.requested_at.desc()).limit(20).all()
    reviews = Review.query.filter_by(to_user_id=user.id).order_by(Review.created_at.desc()).limit(10).all()
    is_driver = user.is_driver and session.get('active_mode') == MODE_DRIVER
    if is_driver:
        trips = Trip.query.filter_by(driver_id=user.id).order_by(Trip.requested_at.desc()).limit(20).all()
        reviews = Review.query.filter_by(to_user_id=user.id).order_by(Review.created_at.desc()).limit(10).all()
        return render_template('profile.html', user=driver_view(user), trips=trips, reviews=reviews, user_type='driver')
    return render_template('profile.html', user=user, trips=trips, reviews=reviews, user_type='passenger')


@auth_bp.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def edit_profile():
    user = current_user()
    if not user:
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        token = request.form.get('csrf_token') or request.headers.get('X-CSRF-Token')
        if not token or not hmac.compare_digest(str(token), str(session.get('csrf_token', ''))):
            flash('Token CSRF inválido', 'danger')
            return redirect(url_for('auth.edit_profile'))
        name = request.form.get('name', '').strip()
        phone = request.form.get('phone', '').strip()
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')

        if not name or len(name) < 2:
            flash('El nombre debe tener al menos 2 caracteres', 'danger')
            return redirect(url_for('auth.edit_profile'))
        if new_password and len(new_password) < 8:
            flash('La nueva contraseña debe tener al menos 8 caracteres', 'danger')
            return redirect(url_for('auth.edit_profile'))
        if new_password and (not re.search(r'[A-Z]', new_password) or not re.search(r'[0-9]', new_password)):
            flash('La nueva contraseña debe contener al menos una mayúscula y un número', 'danger')
            return redirect(url_for('auth.edit_profile'))

        if current_password and new_password:
            if check_password_hash(user.password, current_password):
                user.password = generate_password_hash(new_password)
                flash('Contraseña actualizada.', 'success')
            else:
                flash('Contraseña actual incorrecta.', 'danger')
                return redirect(url_for('auth.edit_profile'))

        user.name = name
        user.phone = phone

        if 'profile_picture' in request.files:
            file = request.files['profile_picture']
            if file and allowed_file(file.filename):
                if not validate_upload_size(file):
                    flash('La imagen es demasiado grande (máx. 5MB).', 'danger')
                    return redirect(url_for('auth.edit_profile'))
                if not validate_image_content(file):
                    flash('El archivo no es una imagen válida.', 'danger')
                    return redirect(url_for('auth.edit_profile'))
                old_pic = user.profile_picture
                os.makedirs(UPLOAD_FOLDER, exist_ok=True)
                ext = file.filename.rsplit('.', 1)[1].lower()
                filename = f'user_{uuid.uuid4().hex}.{ext}'
                file.save(os.path.join(UPLOAD_FOLDER, filename))
                user.profile_picture = f'/static/uploads/{filename}'
                if old_pic and old_pic.startswith('/static/uploads/'):
                    old_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), old_pic.lstrip('/'))
                    if os.path.exists(old_path):
                        try:
                            os.remove(old_path)
                        except OSError:
                            pass

        profile = user.driver_profile
        vehicle = profile.active_vehicle if profile else None
        if vehicle:
            if vehicle.type == 'moto':
                vehicle.placa = sanitize_input(request.form.get('placa')) or vehicle.placa
                vehicle.marca = sanitize_input(request.form.get('moto_marca')) or vehicle.marca
                vehicle.modelo = sanitize_input(request.form.get('moto_modelo')) or vehicle.modelo
                vehicle.color = sanitize_input(request.form.get('moto_color')) or vehicle.color
                vehicle.cilindrada = sanitize_input(request.form.get('moto_cilindrada')) or vehicle.cilindrada
            else:
                vehicle.placa = sanitize_input(request.form.get('placa_auto')) or vehicle.placa
                vehicle.marca = sanitize_input(request.form.get('auto_marca')) or vehicle.marca
                vehicle.modelo = sanitize_input(request.form.get('auto_modelo')) or vehicle.modelo
                vehicle.color = sanitize_input(request.form.get('auto_color')) or vehicle.color
                vehicle.anio = sanitize_input(request.form.get('auto_año')) or vehicle.anio

        db.session.commit()
        session['user_name'] = user.name
        flash('Perfil actualizado.', 'success')
        return redirect(url_for('auth.profile'))

    is_driver = user.is_driver
    if is_driver:
        return render_template('edit_profile.html', user=driver_view(user), user_type='driver')
    return render_template('edit_profile.html', user=user, user_type='passenger')


# ─── Camera upload endpoint ───
@auth_bp.route('/api/upload-photo', methods=['POST'])
@login_required
@csrf_required
def api_upload_photo():
    data = request.get_json(silent=True) or {}
    image_data = data.get('image')

    if not image_data:
        return jsonify({'error': 'No image data'}), 400

    url = save_base64_image(image_data)
    if url:
        return jsonify({'success': True, 'url': url})
    return jsonify({'error': 'Failed to save image'}), 500


# ─── Password Reset ───
@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
@limiter.limit("5 per minute", methods=["POST"])
def forgot_password():
    if request.method == 'POST':
        token = request.form.get('csrf_token') or request.headers.get('X-CSRF-Token')
        if not token or not hmac.compare_digest(str(token), str(session.get('csrf_token', ''))):
            flash('Token CSRF inválido', 'danger')
            return redirect(url_for('auth.forgot_password'))

        email = request.form.get('email', '').strip().lower()
        if not email:
            flash('Ingresa tu correo electrónico', 'danger')
            return redirect(url_for('auth.forgot_password'))

        code = ''.join(secrets.choice(string.digits) for _ in range(6))
        session['reset_code'] = code
        session['reset_email'] = email
        session['reset_attempts'] = 0

        user = User.query.filter_by(email=email).first()

        if user and send_verification_email(email, code):
            flash('Se envió un código de recuperación a tu correo.', 'success')
        else:
            flash('Si el correo está registrado, recibirás un código.', 'info')

        return redirect(url_for('auth.reset_password'))
    return render_template('forgot_password.html')


@auth_bp.route('/reset-password', methods=['GET', 'POST'])
@limiter.limit("10 per minute", methods=["POST"])
def reset_password():
    if 'reset_code' not in session:
        return redirect(url_for('auth.forgot_password'))

    if request.method == 'POST':
        token = request.form.get('csrf_token') or request.headers.get('X-CSRF-Token')
        if not token or not hmac.compare_digest(str(token), str(session.get('csrf_token', ''))):
            flash('Token CSRF inválido', 'danger')
            return redirect(url_for('auth.reset_password'))

        code = request.form.get('code', '').strip()
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')

        attempts = session.get('reset_attempts', 0)
        if attempts >= 5:
            session.pop('reset_code', None)
            session.pop('reset_email', None)
            session.pop('reset_attempts', None)
            flash('Demasiados intentos. Solicita un nuevo código.', 'danger')
            return redirect(url_for('auth.forgot_password'))

        if not hmac.compare_digest(str(code), str(session.get('reset_code', ''))):
            session['reset_attempts'] = attempts + 1
            flash(f'Código incorrecto. Intentos restantes: {4 - attempts}', 'danger')
            return redirect(url_for('auth.reset_password'))

        if len(new_password) < 8:
            flash('La contraseña debe tener al menos 8 caracteres', 'danger')
            return redirect(url_for('auth.reset_password'))
        if not re.search(r'[A-Z]', new_password) or not re.search(r'[0-9]', new_password):
            flash('La contraseña debe contener al menos una mayúscula y un número', 'danger')
            return redirect(url_for('auth.reset_password'))
        if new_password != confirm_password:
            flash('Las contraseñas no coinciden', 'danger')
            return redirect(url_for('auth.reset_password'))

        email = session.get('reset_email', '')
        user = User.query.filter_by(email=email).first()
        if user:
            user.password = generate_password_hash(new_password)

        db.session.commit()
        session.pop('reset_code', None)
        session.pop('reset_email', None)
        session.pop('reset_attempts', None)

        flash('Contraseña restablecida exitosamente. Ahora puedes iniciar sesión.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('reset_password.html')
