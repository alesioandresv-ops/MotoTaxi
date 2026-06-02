import React, { useState } from 'react';
import './Dashboard.css';

const Dashboard = ({ user, onLogout }) => {
  const [pickupAddress, setPickupAddress] = useState('');
  const [dropoffAddress, setDropoffAddress] = useState('');
  const [activeTrip, setActiveTrip] = useState(null);
  const [trips, setTrips] = useState([]);
  const [showHistory, setShowHistory] = useState(false);
  const [estimatedFare, setEstimatedFare] = useState(null);

  const API_URL = 'http://localhost:3001';

  const requestTrip = async () => {
    if (!pickupAddress || !dropoffAddress) {
      alert('Por favor completa los campos');
      return;
    }

    try {
      const response = await fetch(`${API_URL}/api/trips/request`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          userId: user.id,
          pickupAddress,
          dropoffAddress,
          pickupLocation: { lat: 0, lng: 0 },
          dropoffLocation: { lat: 0, lng: 0 }
        })
      });

      if (response.ok) {
        const trip = await response.json();
        setActiveTrip(trip.trip);
        setEstimatedFare(trip.trip.fare);
        setTrips([trip.trip, ...trips]);
        setPickupAddress('');
        setDropoffAddress('');
      }
    } catch (err) {
      alert('Error al solicitar viaje');
    }
  };

  const cancelTrip = () => {
    setActiveTrip(null);
    setEstimatedFare(null);
  };

  const simulateAcceptance = () => {
    if (activeTrip) {
      setActiveTrip({ ...activeTrip, status: 'accepted' });
      setTimeout(() => {
        setActiveTrip({ ...activeTrip, status: 'ongoing' });
      }, 2000);
    }
  };

  return (
    <div className="dashboard">
      <header className="dashboard-header">
        <div className="header-left">
          <h1>🏍️ MotoTaxi</h1>
        </div>
        <div className="header-center">
          <span className="user-info">👤 {user.name}</span>
          <span className="rating">⭐ {user.rating}</span>
        </div>
        <div className="header-right">
          <button className="history-btn" onClick={() => setShowHistory(!showHistory)}>
            📋 Historial
          </button>
          <button className="logout-btn" onClick={onLogout}>
            Salir
          </button>
        </div>
      </header>

      <div className="dashboard-content">
        {!showHistory ? (
          <div className="ride-request-section">
            <div className="map-placeholder">
              <div className="map-icon">📍</div>
              <p>Mapa en tiempo real</p>
            </div>

            <div className="request-form">
              <h2>Solicitar Viaje</h2>
              
              {activeTrip ? (
                <div className="trip-status">
                  <h3>Estado del Viaje: <span className={`status-${activeTrip.status}`}>{activeTrip.status}</span></h3>
                  
                  <div className="trip-info">
                    <p><strong>Origen:</strong> {activeTrip.pickupAddress}</p>
                    <p><strong>Destino:</strong> {activeTrip.dropoffAddress}</p>
                    <p><strong>Tarifa estimada:</strong> ${estimatedFare?.toFixed(2)}</p>
                  </div>

                  {activeTrip.status === 'requested' && (
                    <div className="trip-actions">
                      <div className="waiting">
                        <p>⏳ Esperando conductor...</p>
                        <button onClick={simulateAcceptance} className="simulate-btn">
                          Simular Aceptación
                        </button>
                      </div>
                    </div>
                  )}

                  {activeTrip.status === 'accepted' && (
                    <div className="trip-actions">
                      <p>✅ ¡Conductor en camino!</p>
                      <p>Tiempo estimado: 5 minutos</p>
                    </div>
                  )}

                  {activeTrip.status === 'ongoing' && (
                    <div className="trip-actions">
                      <p>🚗 ¡Viaje en progreso!</p>
                      <p>Conductor: Carlos Rodriguez</p>
                      <p>Vehículo: Yamaha YZF 150</p>
                    </div>
                  )}

                  <button onClick={cancelTrip} className="cancel-btn">
                    Cancelar Viaje
                  </button>
                </div>
              ) : (
                <>
                  <div className="input-group">
                    <label>📍 Ubicación de Recogida</label>
                    <input
                      type="text"
                      placeholder="Ej: Calle Principal 123"
                      value={pickupAddress}
                      onChange={(e) => setPickupAddress(e.target.value)}
                    />
                  </div>

                  <div className="input-group">
                    <label>🎯 Ubicación de Destino</label>
                    <input
                      type="text"
                      placeholder="Ej: Avenida Central 456"
                      value={dropoffAddress}
                      onChange={(e) => setDropoffAddress(e.target.value)}
                    />
                  </div>

                  <button onClick={requestTrip} className="request-btn">
                    Solicitar Viaje
                  </button>
                </>
              )}
            </div>

            <div className="info-section">
              <h3>¿Por qué elegir MotoTaxi?</h3>
              <ul>
                <li>✅ Rápido y eficiente</li>
                <li>✅ Conductores certificados</li>
                <li>✅ Precios justos y transparentes</li>
                <li>✅ Seguridad garantizada</li>
                <li>✅ Soporte 24/7</li>
              </ul>
            </div>
          </div>
        ) : (
          <div className="history-section">
            <h2>Historial de Viajes</h2>
            {trips.length === 0 ? (
              <p className="no-trips">No hay viajes registrados</p>
            ) : (
              <div className="trips-list">
                {trips.map((trip) => (
                  <div key={trip.id} className="trip-card">
                    <div className="trip-card-header">
                      <span className={`badge ${trip.status}`}>{trip.status}</span>
                      <span className="fare">${trip.fare?.toFixed(2)}</span>
                    </div>
                    <p><strong>De:</strong> {trip.pickupAddress}</p>
                    <p><strong>A:</strong> {trip.dropoffAddress}</p>
                    <p><small>{new Date(trip.createdAt).toLocaleDateString('es-ES')}</small></p>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default Dashboard;
