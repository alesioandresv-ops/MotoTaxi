import React, { useState, useEffect } from 'react';
import './Login.css';

const Login = ({ onLogin, showRegister, setShowRegister }) => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [userType, setUserType] = useState('passenger');
  const [phone, setPhone] = useState('');
  const [vehicleBrand, setVehicleBrand] = useState('');
  const [vehicleModel, setVehicleModel] = useState('');
  const [vehicleColor, setVehicleColor] = useState('');
  const [cc, setCc] = useState('');
  const [plateNumber, setPlateNumber] = useState('');
  const [hasHelmetDriver, setHasHelmetDriver] = useState(true);
  const [hasHelmetPassenger, setHasHelmetPassenger] = useState(true);
  const [hasInsurance, setHasInsurance] = useState(false);
  const [insuranceType, setInsuranceType] = useState('');
  const [drivingLicense, setDrivingLicense] = useState('');
  const [lastService, setLastService] = useState('');
  const [error, setError] = useState('');
  const [isRegister, setIsRegister] = useState(showRegister);

  useEffect(() => {
    setIsRegister(showRegister);
  }, [showRegister]);

  const API_URL = 'http://localhost:3001';

  const handleRegister = async (e) => {
    e.preventDefault();

    // Validación mínima de campos
    if (password.length < 6) {
      setError('La contraseña debe tener al menos 6 caracteres');
      return;
    }
    try {
      const response = await fetch(`${API_URL}/api/auth/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            name,
            email,
            password,
            userType,
            phone,
            vehicleBrand,
            vehicleModel,
            vehicleColor,
            cc,
            plateNumber,
            hasHelmetDriver,
            hasHelmetPassenger,
            hasInsurance,
            insuranceType,
            drivingLicense,
            lastService
          })
      });
      
      if (response.ok) {
        const data = await response.json();
        // Auto-login después de registrarse
        if (data && data.user) {
          onLogin(data.user);
          return;
        }
        alert('Registro exitoso. Por favor, inicia sesión.');
        setIsRegister(false);
        setShowRegister(false);
        setEmail('');
        setPassword('');
        setName('');
        setPhone('');
        setVehicleBrand('');
        setVehicleModel('');
        setVehicleColor('');
        setCc('');
        setPlateNumber('');
        setHasHelmetDriver(true);
        setHasHelmetPassenger(true);
        setHasInsurance(false);
        setInsuranceType('');
        setDrivingLicense('');
        setLastService('');
        setUserType('passenger');
      } else {
        const errorData = await response.json();
        setError(errorData.error || 'Error en el registro');
      }
    } catch (err) {
      setError('Error de conexión');
    }
  };

  const handleLogin = async (e) => {
    e.preventDefault();
    try {
      const response = await fetch(`${API_URL}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password })
      });
      
      if (response.ok) {
        const data = await response.json();
        onLogin(data.user);
      } else {
        setError('Email o contraseña incorrectos');
      }
    } catch (err) {
      setError('Error de conexión con el servidor');
    }
  };

  const handleDemoLogin = (type) => {
    if (type === 'passenger') {
      onLogin({
        id: '1',
        name: 'Juan Pasajero',
        email: 'pasajero@demo.com',
        userType: 'passenger',
        rating: 4.8
      });
    } else {
      onLogin({
        id: '2',
        name: 'Carlos Conductor',
        email: 'conductor@demo.com',
        userType: 'driver',
        rating: 4.9
      });
    }
  };

  return (
    <div className="login-container">
      <div className="login-box">
        <div className="logo">
          <h1>🏍️ MotoTaxi</h1>
          <p>Tu app de mototaxi de confianza</p>
        </div>

        {error && <div className="error-message">{error}</div>}

        {!isRegister ? (
          <form onSubmit={handleLogin} className="form">
            <h2>Inicia Sesión</h2>
            <input
              type="email"
              placeholder="Correo electrónico"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
            <input
              type="password"
              placeholder="Contraseña"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
            <button type="submit">Inicia Sesión</button>

            <div className="demo-buttons">
              <p>O prueba con demo:</p>
              <button
                type="button"
                className="demo-btn passenger"
                onClick={() => handleDemoLogin('passenger')}
              >
                Demo Pasajero
              </button>
              <button
                type="button"
                className="demo-btn driver"
                onClick={() => handleDemoLogin('driver')}
              >
                Demo Conductor
              </button>
            </div>

            <button
              type="button"
              className="toggle-btn"
              onClick={() => {
                setIsRegister(true);
                setShowRegister(true);
                setError('');
              }}
            >
              ¿No tienes cuenta? Regístrate
            </button>
          </form>
        ) : (
          <form onSubmit={handleRegister} className="form">
            <h2>Regístrate</h2>
            <input
              type="text"
              placeholder="Nombre completo"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
            />
            <input
              type="email"
              placeholder="Correo electrónico"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
            <input
              type="password"
              placeholder="Contraseña"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
            <input
              type="tel"
              placeholder="Teléfono"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              required
            />
            <select value={userType} onChange={(e) => setUserType(e.target.value)}>
              <option value="passenger">Pasajero</option>
              <option value="driver">Conductor</option>
              <option value="admin">Administrador</option>
            </select>
            {userType === 'driver' && (
              <>
                <input
                  type="text"
                  placeholder="Marca de la moto (Ej. Yamaha)"
                  value={vehicleBrand}
                  onChange={(e) => setVehicleBrand(e.target.value)}
                  required
                />
                <input
                  type="text"
                  placeholder="Modelo de la moto (Ej. YZF 150)"
                  value={vehicleModel}
                  onChange={(e) => setVehicleModel(e.target.value)}
                  required
                />
                <input
                  type="text"
                  placeholder="Color de la moto"
                  value={vehicleColor}
                  onChange={(e) => setVehicleColor(e.target.value)}
                  required
                />
                <input
                  type="number"
                  placeholder="Cilindradas (cc)"
                  value={cc}
                  onChange={(e) => setCc(e.target.value)}
                  required
                />
                <input
                  type="text"
                  placeholder="Patente (ej. ABC123)"
                  value={plateNumber}
                  onChange={(e) => setPlateNumber(e.target.value)}
                  required
                />
                <label>
                  <input type="checkbox" checked={hasHelmetDriver} onChange={(e) => setHasHelmetDriver(e.target.checked)} /> Casco conductor
                </label>
                <label>
                  <input type="checkbox" checked={hasHelmetPassenger} onChange={(e) => setHasHelmetPassenger(e.target.checked)} /> Casco acompañante
                </label>
                <label>
                  <input type="checkbox" checked={hasInsurance} onChange={(e) => setHasInsurance(e.target.checked)} /> Tiene seguro
                </label>
                {hasInsurance && (
                  <input
                    type="text"
                    placeholder="Tipo de seguro"
                    value={insuranceType}
                    onChange={(e) => setInsuranceType(e.target.value)}
                    required
                  />
                )}
                <input
                  type="text"
                  placeholder="Carnet de conducir (nº)"
                  value={drivingLicense}
                  onChange={(e) => setDrivingLicense(e.target.value)}
                  required
                />
                <input
                  type="text"
                  placeholder="Último servicio realizado"
                  value={lastService}
                  onChange={(e) => setLastService(e.target.value)}
                  required
                />
              </>
            )}
            <button type="submit">Regístrate</button>
            <button
              type="button"
              className="toggle-btn"
              onClick={() => {
                setIsRegister(false);
                setShowRegister(false);
              }}
            >
              ¿Ya tienes cuenta? Inicia Sesión
            </button>
          </form>
        )}
      </div>
    </div>
  );
};

export default Login;
