from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from .models import db, User, Driver, Trip
from werkzeug.security import generate_password_hash, check_password_hash

auth_bp = Blueprint('auth', __name__)


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
        flash('Registro exitoso. Por favor inicia sesión.', 'success')
        return redirect(url_for('auth.login'))
    return render_template('register.html')


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
        flash('Registro de conductor exitoso. Inicia sesión.', 'success')
        return redirect(url_for('auth.login'))
    return render_template('driver_register.html')


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
    session.clear()
    flash('Sesión cerrada', 'info')
    return redirect(url_for('main.index'))
