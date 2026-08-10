import os
import json
import re
import uuid
import hmac
import secrets
import string
import smtplib
import base64
from email.mime.text import MIMEText
from werkzeug.utils import secure_filename
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, current_app
from .models import db, User, Driver, Trip, Review
from werkzeug.security import generate_password_hash, check_password_hash
from .routes import login_required, csrf_required, sanitize_input
from .validators import validate_name, validate_email, validate_password, first_error
from .extensions import limiter
from sqlalchemy.exc import IntegrityError

auth_bp = Blueprint('auth', __name__)

UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}
MAX_UPLOAD_BYTES = 2 * 1024 * 1024  # 2MB

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_driver_photo(file_or_bytes):
    try:
        from PIL import Image
        import io
        import time

        if isinstance(file_or_bytes, bytes):
            data = file_or_bytes
        else:
            file_or_bytes.seek(0)
            data = file_or_bytes.read()
            file_or_bytes.seek(0)

        if len(data) > MAX_UPLOAD_BYTES:
            return None, 'max_size'

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

        if Driver.query.filter_by(email=email).first():
            flash('Correo electrónico de conductor ya registrado', 'warning')
            return redirect(url_for('auth.driver_register'))

        # Common fields
        carnet_conducir = sanitize_input(request.form.get('carnet_conducir'))
        profile_picture = None

        # Handle profile picture (required) — from file input or camera
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

        if vehicle_type == 'moto':
            placa = sanitize_input(request.form.get('placa'))
            moto_marca = sanitize_input(request.form.get('moto_marca'))
            moto_modelo = sanitize_input(request.form.get('moto_modelo'))
            moto_color = sanitize_input(request.form.get('moto_color'))
            moto_cilindrada = sanitize_input(request.form.get('moto_cilindrada'))
            tiene_patente = request.form.get('tiene_patente') == 'yes'
            tiene_casco = request.form.get('tiene_casco') == 'yes'
            seguro_moto = request.form.get('seguro_moto') == 'yes'
            tipo_seguro = sanitize_input(request.form.get('tipo_seguro'))
            ultimo_servicio = sanitize_input(request.form.get('ultimo_servicio'))

            required_fields = [name, email, password, phone, placa, moto_marca, moto_modelo, moto_color, moto_cilindrada, tipo_seguro, carnet_conducir, ultimo_servicio]
            if not all(required_fields):
                flash('Por favor completa todos los campos obligatorios para moto.', 'danger')
                return redirect(url_for('auth.driver_register'))

            driver = Driver(
                name=name, email=email, password=generate_password_hash(password),
                phone=phone, profile_picture=profile_picture, vehicle_type='moto',
                placa=placa, moto_marca=moto_marca, moto_modelo=moto_modelo,
                moto_color=moto_color, moto_cilindrada=moto_cilindrada,
                tiene_patente=tiene_patente, tiene_casco=tiene_casco,
                seguro_moto=seguro_moto, tipo_seguro=tipo_seguro,
                carnet_conducir=carnet_conducir, ultimo_servicio=ultimo_servicio
            )
        else:
            placa_auto = sanitize_input(request.form.get('placa_auto'))
            auto_marca = sanitize_input(request.form.get('auto_marca'))
            auto_modelo = sanitize_input(request.form.get('auto_modelo'))
            auto_color = sanitize_input(request.form.get('auto_color'))
            auto_año = sanitize_input(request.form.get('auto_año'))
            tiene_patente_auto = request.form.get('tiene_patente_auto') == 'yes'
            seguro_auto = request.form.get('seguro_auto') == 'yes'
            tipo_seguro_auto = sanitize_input(request.form.get('tipo_seguro_auto'))
            carnet_conducir_auto = request.form.get('carnet_conducir_auto', carnet_conducir)
            ultimo_servicio_auto = sanitize_input(request.form.get('ultimo_servicio_auto'))

            required_fields = [name, email, password, phone, placa_auto, auto_marca, auto_modelo, auto_color, auto_año, tipo_seguro_auto, carnet_conducir_auto]
            if not all(required_fields):
                flash('Por favor completa todos los campos obligatorios para auto.', 'danger')
                return redirect(url_for('auth.driver_register'))

            driver = Driver(
                name=name, email=email, password=generate_password_hash(password),
                phone=phone, profile_picture=profile_picture, vehicle_type='auto',
                placa='', moto_marca='', moto_modelo='', moto_color='',
                moto_cilindrada='', tiene_patente=False, tiene_casco=False,
                seguro_moto=False, tipo_seguro='', carnet_conducir=carnet_conducir,
                ultimo_servicio='',
                placa_auto=placa_auto, auto_marca=auto_marca, auto_modelo=auto_modelo,
                auto_color=auto_color, auto_año=auto_año,
                tiene_patente_auto=tiene_patente_auto, seguro_auto=seguro_auto,
                tipo_seguro_auto=tipo_seguro_auto, carnet_conducir_auto=carnet_conducir_auto,
                ultimo_servicio_auto=ultimo_servicio_auto
            )

        db.session.add(driver)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash('Correo electrónico de conductor ya registrado', 'warning')
            return redirect(url_for('auth.driver_register'))

        code = ''.join(secrets.choice(string.digits) for _ in range(6))
        session['verify_code'] = code
        session['verify_driver_id'] = driver.id
        session['verify_email'] = email

        if send_verification_email(email, code):
            flash('Registro exitoso. Revisa tu correo para verificar tu cuenta.', 'success')
            return redirect(url_for('auth.verify_email_driver'))
        else:
            flash('Registro exitoso.', 'success')
            return redirect(url_for('auth.login'))
    return render_template('driver_register.html')

@auth_bp.route('/verify-email-driver', methods=['GET', 'POST'])
@limiter.limit("5 per minute", methods=["POST"])
def verify_email_driver():
    if 'verify_code' not in session:
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        token = request.form.get('csrf_token') or request.headers.get('X-CSRF-Token')
        if not token or not hmac.compare_digest(str(token), str(session.get('csrf_token', ''))):
            flash('Token CSRF inválido', 'danger')
            return redirect(url_for('auth.verify_email_driver'))
        code = request.form.get('code', '').strip()
        if hmac.compare_digest(str(code), str(session.get('verify_code', ''))):
            driver = Driver.query.get(session['verify_driver_id'])
            if driver:
                driver.email_verified = True
                db.session.commit()
            session.pop('verify_code', None)
            session.pop('verify_driver_id', None)
            session.pop('verify_email', None)
            flash('Correo verificado exitosamente. Ahora puedes iniciar sesión.', 'success')
            return redirect(url_for('auth.login'))
        else:
            flash('Código incorrecto. Intenta de nuevo.', 'danger')

    return render_template('verify_email.html', email=session.get('verify_email'))

@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute", methods=["POST"])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        smtp_configured = bool(os.getenv('SMTP_SERVER') and os.getenv('SMTP_USER') and os.getenv('SMTP_PASS'))

        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            if smtp_configured and not user.email_verified:
                flash('Debes verificar tu correo antes de iniciar sesión. Revisa tu bandeja de entrada.', 'warning')
                return redirect(url_for('auth.login'))
            user_data = {'user_id': user.id, 'user_name': user.name}
            session.clear()
            session.update(user_data)
            session['csrf_token'] = secrets.token_hex(32)
            session.permanent = True
            flash('Bienvenido ' + user.name, 'success')
            return redirect(url_for('main.dashboard'))
        driver = Driver.query.filter_by(email=email).first()
        if driver and check_password_hash(driver.password, password):
            if smtp_configured and not driver.email_verified:
                flash('Debes verificar tu correo antes de iniciar sesión. Revisa tu bandeja de entrada.', 'warning')
                return redirect(url_for('auth.login'))
            driver_data = {'driver_id': driver.id, 'driver_name': driver.name}
            session.clear()
            session.update(driver_data)
            session['csrf_token'] = secrets.token_hex(32)
            session.permanent = True
            flash('Bienvenido conductor ' + driver.name, 'success')
            return redirect(url_for('main.dashboard'))
        flash('Credenciales inválidas', 'danger')
    return render_template('login.html')

@auth_bp.route('/logout', methods=['POST'])
@csrf_required
def logout():
    driver_id = session.get('driver_id')
    if driver_id:
        driver = Driver.query.get(driver_id)
        if driver:
            driver.is_online = False
            driver.is_ocupado = False
            db.session.commit()
    session.clear()
    flash('Sesión cerrada', 'info')
    return redirect(url_for('main.index'))

@auth_bp.route('/profile')
@login_required
def profile():
    if 'user_id' in session:
        user = User.query.get(session['user_id'])
        trips = Trip.query.filter_by(passenger_id=user.id).order_by(Trip.requested_at.desc()).limit(20).all()
        reviews = Review.query.filter_by(to_user_id=user.id).order_by(Review.created_at.desc()).limit(10).all()
        return render_template('profile.html', user=user, trips=trips, reviews=reviews, user_type='passenger')

    if 'driver_id' in session:
        driver = Driver.query.get(session['driver_id'])
        trips = Trip.query.filter_by(driver_id=driver.id).order_by(Trip.requested_at.desc()).limit(20).all()
        reviews = Review.query.filter_by(to_driver_id=driver.id).order_by(Review.created_at.desc()).limit(10).all()
        return render_template('profile.html', user=driver, trips=trips, reviews=reviews, user_type='driver')

    return redirect(url_for('auth.login'))

@auth_bp.route('/profile/edit', methods=['GET', 'POST'])
@csrf_required
def edit_profile():
    if 'user_id' not in session and 'driver_id' not in session:
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
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

        if 'user_id' in session:
            user = User.query.get(session['user_id'])
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

            db.session.commit()
            session['user_name'] = user.name
            flash('Perfil actualizado.', 'success')

        elif 'driver_id' in session:
            driver = Driver.query.get(session['driver_id'])
            if current_password and new_password:
                if check_password_hash(driver.password, current_password):
                    driver.password = generate_password_hash(new_password)
                    flash('Contraseña actualizada.', 'success')
                else:
                    flash('Contraseña actual incorrecta.', 'danger')
                    return redirect(url_for('auth.edit_profile'))
            driver.name = name
            driver.phone = phone

            if driver.vehicle_type == 'moto':
                driver.placa = sanitize_input(request.form.get('placa')) or driver.placa
                driver.moto_marca = sanitize_input(request.form.get('moto_marca')) or driver.moto_marca
                driver.moto_modelo = sanitize_input(request.form.get('moto_modelo')) or driver.moto_modelo
                driver.moto_color = sanitize_input(request.form.get('moto_color')) or driver.moto_color
                driver.moto_cilindrada = sanitize_input(request.form.get('moto_cilindrada')) or driver.moto_cilindrada
            else:
                driver.placa_auto = sanitize_input(request.form.get('placa_auto')) or driver.placa_auto
                driver.auto_marca = sanitize_input(request.form.get('auto_marca')) or driver.auto_marca
                driver.auto_modelo = sanitize_input(request.form.get('auto_modelo')) or driver.auto_modelo
                driver.auto_color = sanitize_input(request.form.get('auto_color')) or driver.auto_color
                driver.auto_año = sanitize_input(request.form.get('auto_año')) or driver.auto_año

            if 'profile_picture' in request.files:
                file = request.files['profile_picture']
                if file and allowed_file(file.filename):
                    if not validate_upload_size(file):
                        flash('La imagen es demasiado grande (máx. 5MB).', 'danger')
                        return redirect(url_for('auth.edit_profile'))
                    if not validate_image_content(file):
                        flash('El archivo no es una imagen válida.', 'danger')
                        return redirect(url_for('auth.edit_profile'))
                    old_pic = driver.profile_picture
                    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
                    ext = file.filename.rsplit('.', 1)[1].lower()
                    filename = f'driver_{uuid.uuid4().hex}.{ext}'
                    file.save(os.path.join(UPLOAD_FOLDER, filename))
                    driver.profile_picture = f'/static/uploads/{filename}'
                    if old_pic and old_pic.startswith('/static/uploads/'):
                        old_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), old_pic.lstrip('/'))
                        if os.path.exists(old_path):
                            try:
                                os.remove(old_path)
                            except OSError:
                                pass

            db.session.commit()
            session['driver_name'] = driver.name
            flash('Perfil actualizado.', 'success')

        return redirect(url_for('auth.profile'))

    if 'user_id' in session:
        user = User.query.get(session['user_id'])
        return render_template('edit_profile.html', user=user, user_type='passenger')
    if 'driver_id' in session:
        driver = Driver.query.get(session['driver_id'])
        return render_template('edit_profile.html', user=driver, user_type='driver')

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
        driver = Driver.query.filter_by(email=email).first()

        if user and driver:
            session['reset_target'] = 'user'
        elif user:
            session['reset_target'] = 'user'
        elif driver:
            session['reset_target'] = 'driver'
        else:
            session['reset_target'] = None

        target = user or driver

        if target and send_verification_email(email, code):
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
            session.pop('reset_target', None)
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
        target_type = session.get('reset_target')

        if target_type == 'driver':
            driver = Driver.query.filter_by(email=email).first()
            if driver:
                driver.password = generate_password_hash(new_password)
        else:
            user = User.query.filter_by(email=email).first()
            if user:
                user.password = generate_password_hash(new_password)

        db.session.commit()
        session.pop('reset_code', None)
        session.pop('reset_email', None)
        session.pop('reset_attempts', None)
        session.pop('reset_target', None)

        flash('Contraseña restablecida exitosamente. Ahora puedes iniciar sesión.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('reset_password.html')
