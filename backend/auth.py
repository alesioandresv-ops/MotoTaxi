import os
import random
import string
import smtplib
from email.mime.text import MIMEText
from werkzeug.utils import secure_filename
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, current_app
from .models import db, User, Driver, Trip, Review
from werkzeug.security import generate_password_hash, check_password_hash

auth_bp = Blueprint('auth', __name__)

UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def send_verification_email(email, code):
    try:
        smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        smtp_port = int(os.getenv('SMTP_PORT', 587))
        smtp_user = os.getenv('SMTP_USER', '')
        smtp_pass = os.getenv('SMTP_PASS', '')

        if not smtp_user or not smtp_pass:
            return False

        msg = MIMEText(f'Tu código de verificación de MotoTaxi es: {code}\n\nEste código expira en 10 minutos.')
        msg['Subject'] = 'Verifica tu correo - MotoTaxi'
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
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        phone = request.form.get('phone')
        if User.query.filter_by(email=email).first():
            flash('Email ya registrado', 'warning')
            return redirect(url_for('auth.register'))
        user = User(name=name, email=email, password=generate_password_hash(password), phone=phone)
        db.session.add(user)
        db.session.commit()

        code = ''.join(random.choices(string.digits, k=6))
        session['verify_code'] = code
        session['verify_user_id'] = user.id
        session['verify_email'] = email

        if send_verification_email(email, code):
            flash('Registro exitoso. Revisa tu correo para verificar tu cuenta.', 'success')
            return redirect(url_for('auth.verify_email'))
        else:
            flash('Registro exitoso. No se pudo enviar email de verificación (configura SMTP en .env).', 'success')
            return redirect(url_for('auth.login'))
    return render_template('register.html')

@auth_bp.route('/verify-email', methods=['GET', 'POST'])
def verify_email():
    if 'verify_code' not in session:
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        code = request.form.get('code', '').strip()
        if code == session.get('verify_code'):
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
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        phone = request.form.get('phone')
        placa = request.form.get('placa')
        moto_marca = request.form.get('moto_marca')
        moto_modelo = request.form.get('moto_modelo')
        moto_color = request.form.get('moto_color')
        moto_cilindrada = request.form.get('moto_cilindrada')
        tiene_patente = request.form.get('tiene_patente') == 'yes'
        tiene_casco = request.form.get('tiene_casco') == 'yes'
        seguro_moto = request.form.get('seguro_moto') == 'yes'
        tipo_seguro = request.form.get('tipo_seguro')
        carnet_conducir = request.form.get('carnet_conducir')
        ultimo_servicio = request.form.get('ultimo_servicio')

        if Driver.query.filter_by(email=email).first():
            flash('Email de conductor ya registrado', 'warning')
            return redirect(url_for('auth.driver_register'))

        required_fields = [name, email, password, phone, placa, moto_marca, moto_modelo, moto_color, moto_cilindrada, tipo_seguro, carnet_conducir, ultimo_servicio]
        if not all(required_fields):
            flash('Por favor completa todos los campos obligatorios para conductores.', 'danger')
            return redirect(url_for('auth.driver_register'))

        driver = Driver(
            name=name,
            email=email,
            password=generate_password_hash(password),
            phone=phone,
            placa=placa,
            moto_marca=moto_marca,
            moto_modelo=moto_modelo,
            moto_color=moto_color,
            moto_cilindrada=moto_cilindrada,
            tiene_patente=tiene_patente,
            tiene_casco=tiene_casco,
            seguro_moto=seguro_moto,
            tipo_seguro=tipo_seguro,
            carnet_conducir=carnet_conducir,
            ultimo_servicio=ultimo_servicio
        )
        db.session.add(driver)
        db.session.commit()

        code = ''.join(random.choices(string.digits, k=6))
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
def verify_email_driver():
    if 'verify_code' not in session:
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        code = request.form.get('code', '').strip()
        if code == session.get('verify_code'):
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
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            session['user_name'] = user.name
            flash('Bienvenido ' + user.name, 'success')
            return redirect(url_for('main.dashboard'))
        driver = Driver.query.filter_by(email=email).first()
        if driver and check_password_hash(driver.password, password):
            session['driver_id'] = driver.id
            session['driver_name'] = driver.name
            flash('Bienvenido conductor ' + driver.name, 'success')
            return redirect(url_for('main.dashboard'))
        flash('Credenciales inválidas', 'danger')
    return render_template('login.html')

@auth_bp.route('/logout')
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
def edit_profile():
    if 'user_id' not in session and 'driver_id' not in session:
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        name = request.form.get('name')
        phone = request.form.get('phone')
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')

        if 'user_id' in session:
            user = User.query.get(session['user_id'])
            user.name = name
            user.phone = phone
            if current_password and new_password:
                if check_password_hash(user.password, current_password):
                    user.password = generate_password_hash(new_password)
                    flash('Contraseña actualizada.', 'success')
                else:
                    flash('Contraseña actual incorrecta.', 'danger')

            if 'profile_picture' in request.files:
                file = request.files['profile_picture']
                if file and allowed_file(file.filename):
                    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
                    ext = file.filename.rsplit('.', 1)[1].lower()
                    filename = f'user_{user.id}.{ext}'
                    file.save(os.path.join(UPLOAD_FOLDER, filename))
                    user.profile_picture = f'/static/uploads/{filename}'

            db.session.commit()
            session['user_name'] = user.name
            flash('Perfil actualizado.', 'success')

        elif 'driver_id' in session:
            driver = Driver.query.get(session['driver_id'])
            driver.name = name
            driver.phone = phone
            driver.placa = request.form.get('placa', driver.placa)
            driver.moto_marca = request.form.get('moto_marca', driver.moto_marca)
            driver.moto_modelo = request.form.get('moto_modelo', driver.moto_modelo)
            driver.moto_color = request.form.get('moto_color', driver.moto_color)
            driver.moto_cilindrada = request.form.get('moto_cilindrada', driver.moto_cilindrada)

            if current_password and new_password:
                if check_password_hash(driver.password, current_password):
                    driver.password = generate_password_hash(new_password)
                    flash('Contraseña actualizada.', 'success')
                else:
                    flash('Contraseña actual incorrecta.', 'danger')

            if 'profile_picture' in request.files:
                file = request.files['profile_picture']
                if file and allowed_file(file.filename):
                    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
                    ext = file.filename.rsplit('.', 1)[1].lower()
                    filename = f'driver_{driver.id}.{ext}'
                    file.save(os.path.join(UPLOAD_FOLDER, filename))
                    driver.profile_picture = f'/static/uploads/{filename}'

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
