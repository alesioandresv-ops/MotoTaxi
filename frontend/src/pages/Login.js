import React, { useState, useEffect } from 'react';
import './Login.css';

const Login = ({ onLogin, showRegister, setShowRegister }) => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [userType, setUserType] = useState('passenger');
  const [phone, setPhone] = useState('');
  const [vehicle, setVehicle] = useState('');
  const [licenseNumber, setLicenseNumber] = useState('');
  const [error, setError] = useState('');
  const [isRegister, setIsRegister] = useState(showRegister);

  useEffect(() => {
    setIsRegister(showRegister);
  }, [showRegister]);

  const API_URL = 'http://localhost:3001';

  const handleRegister = async (e) => {
    e.preventDefault();
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
          vehicle,
          licenseNumber
        })
      });
      
      if (response.ok) {
        const data = await response.json();
        alert('Registro exitoso. Por favor, inicia sesión.');
        setIsRegister(false);
        setShowRegister(false);
        setEmail('');
        setPassword('');
        setName('');
        setPhone('');
        setVehicle('');
        setLicenseNumber('');
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
            </select>
            {userType === 'driver' && (
              <>
                <input
                  type="text"
                  placeholder="Vehículo (Ej. Yamaha YZF 150)"
                  value={vehicle}
                  onChange={(e) => setVehicle(e.target.value)}
                  required
                />
                <input
                  type="text"
                  placeholder="Número de licencia"
                  value={licenseNumber}
                  onChange={(e) => setLicenseNumber(e.target.value)}
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
