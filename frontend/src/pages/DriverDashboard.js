import React, { useState, useEffect } from 'react';
import './DriverDashboard.css';

const API_URL = 'http://localhost:3001';

const DriverDashboard = ({ user, onLogout }) => {
  const driverId = user?.driverProfile?.driverId;
  const [isOnline, setIsOnline] = useState(user?.driverProfile?.isOnline || false);
  const [fareRate, setFareRate] = useState(user?.driverProfile?.fareRate || 200);
  const [requests, setRequests] = useState([]);
  const [currentTrip, setCurrentTrip] = useState(null);
  const [completedTrips, setCompletedTrips] = useState([]);
  const [earnings, setEarnings] = useState(0);
  const [statusMessage, setStatusMessage] = useState('');

  const loadDriverData = async () => {
    if (!driverId) return;
    try {
      const profileResponse = await fetch(`${API_URL}/api/drivers/${driverId}`);
      let online = isOnline;
      if (profileResponse.ok) {
        const driverProfile = await profileResponse.json();
        online = driverProfile.isOnline;
        setIsOnline(online);
        setFareRate(driverProfile.fareRate || 200);
      }

      const response = await fetch(`${API_URL}/api/drivers/${driverId}/trips`);
      if (response.ok) {
        const driverTrips = await response.json();
        const activeTrip = driverTrips.find(t => ['accepted', 'ongoing'].includes(t.status));
        const finished = driverTrips.filter(t => t.status === 'completed');
        const total = finished.reduce((sum, trip) => sum + (trip.fare || 0), 0);

        setCurrentTrip(activeTrip || null);
        setCompletedTrips(finished);
        setEarnings(total);
      }

      if (online) {
        const reqResponse = await fetch(`${API_URL}/api/drivers/${driverId}/requests`);
        if (reqResponse.ok) {
          const available = await reqResponse.json();
          setRequests(available);
        }
      } else {
        setRequests([]);
      }
    } catch (err) {
      console.error('Error cargando datos del conductor', err);
    }
  };

  useEffect(() => {
    loadDriverData();
  }, [driverId, isOnline]);

  useEffect(() => {
    const interval = setInterval(() => {
      loadDriverData();
    }, 5000);
    return () => clearInterval(interval);
  }, [driverId, isOnline]);

  const updateStatus = async (online) => {
    if (!driverId) return;
    try {
      const response = await fetch(`${API_URL}/api/drivers/${driverId}/status`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ isOnline: online })
      });
      if (response.ok) {
        setIsOnline(online);
        setStatusMessage(online ? 'Estás en línea y recibirás nuevos pedidos' : 'Has salido de línea');
      }
    } catch (err) {
      console.error('Error actualizando estado', err);
    }
  };

  const saveFareRate = async () => {
    if (!driverId) return;
    try {
      const response = await fetch(`${API_URL}/api/drivers/${driverId}/tarifa`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ fareRate })
      });
      if (response.ok) {
        setStatusMessage('Tarifa actualizada a ARS ' + fareRate);
      }
    } catch (err) {
      console.error('Error actualizando tarifa', err);
    }
  };

  const acceptTrip = async (tripId) => {
    if (!driverId) return;
    try {
      const response = await fetch(`${API_URL}/api/trips/${tripId}/accept`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ driverId })
      });
      if (response.ok) {
        await loadDriverData();
      }
    } catch (err) {
      console.error('Error aceptando viaje', err);
    }
  };

  const startTrip = async () => {
    if (!currentTrip) return;
    try {
      const response = await fetch(`${API_URL}/api/trips/${currentTrip.id}/start`, {
        method: 'PUT'
      });
      if (response.ok) {
        await loadDriverData();
      }
    } catch (err) {
      console.error('Error iniciando viaje', err);
    }
  };

  const completeTrip = async () => {
    if (!currentTrip) return;
    try {
      const response = await fetch(`${API_URL}/api/trips/${currentTrip.id}/complete`, {
        method: 'PUT'
      });
      if (response.ok) {
        await loadDriverData();
      }
    } catch (err) {
      console.error('Error completando viaje', err);
    }
  };

  return (
    <div className="driver-dashboard">
      <header className="driver-header">
        <div className="header-left">
          <h1>🏍️ MotoTaxi Conductor</h1>
        </div>
        <div className="header-center">
          <span className="user-info">👤 {user.name}</span>
          <span className="rating">⭐ {user.rating}</span>
        </div>
        <div className="header-right">
          <button
            className={`online-btn ${isOnline ? 'active' : ''}`}
            onClick={() => updateStatus(!isOnline)}
          >
            {isOnline ? '🟢 En Línea' : '⚫ Fuera de Línea'}
          </button>
          <button className="logout-btn" onClick={onLogout}>
            Salir
          </button>
        </div>
      </header>

      <div className="driver-content">
        <div className="main-section">
          <div className="status-card">
            <h2>Estado Actual</h2>
            <div className="status-info">
              <p><strong>Estado:</strong> {isOnline ? '🟢 En Línea' : '⚫ Fuera de Línea'}</p>
              <p><strong>Viajes Completados:</strong> {completedTrips.length}</p>
              <p><strong>Ganancias:</strong> ARS {earnings.toFixed(2)}</p>
              <p><strong>Calificación:</strong> ⭐ {user.rating}</p>
            </div>
          </div>

          <div className="fare-card">
            <h2>Tarifa del conductor</h2>
            <div className="fare-control">
              <label>Tarifa por km (ARS)</label>
              <input
                type="number"
                min="50"
                step="10"
                value={fareRate}
                onChange={(e) => setFareRate(Number(e.target.value))}
              />
              <button className="save-fare-btn" onClick={saveFareRate}>
                Guardar Tarifa
              </button>
            </div>
            <p className="fare-note">Tus viajes se calculan en pesos argentinos.</p>
          </div>

          {currentTrip ? (
            <div className="active-trip-card">
              <h2>Viaje Activo</h2>
              <div className="trip-details">
                <p><strong>Origen:</strong> {currentTrip.pickupAddress}</p>
                <p><strong>Destino:</strong> {currentTrip.dropoffAddress}</p>
                <p><strong>Distancia estimada:</strong> {currentTrip.distance} km</p>
                <p><strong>Tarifa:</strong> ARS {currentTrip.fare.toFixed(2)}</p>
                <p><strong>Estado:</strong> <span className="trip-status">{currentTrip.status}</span></p>
              </div>
              <div className="trip-actions">
                {currentTrip.status === 'accepted' && (
                  <button className="start-btn" onClick={startTrip}>
                    🚀 Iniciar Viaje
                  </button>
                )}
                {currentTrip.status === 'ongoing' && (
                  <button className="complete-btn" onClick={completeTrip}>
                    ✅ Completar Viaje
                  </button>
                )}
              </div>
            </div>
          ) : (
            <div className="pending-trips-card">
              <h2>Viajes Nuevos</h2>
              {isOnline ? (
                requests.length === 0 ? (
                  <p className="no-trips">No hay viajes nuevos por el momento.</p>
                ) : (
                  <div className="trips-list">
                    {requests.map((trip) => (
                      <div key={trip.id} className="trip-item">
                        <div className="trip-info">
                          <p><strong>📍 Origen:</strong> {trip.pickupAddress}</p>
                          <p><strong>🎯 Destino:</strong> {trip.dropoffAddress}</p>
                          <p><strong>Distancia:</strong> {trip.distance} km</p>
                          <p><strong>Tarifa estimada:</strong> ARS {trip.fare.toFixed(2)}</p>
                        </div>
                        <button className="accept-btn" onClick={() => acceptTrip(trip.id)}>
                          Aceptar Viaje
                        </button>
                      </div>
                    ))}
                  </div>
                )
              ) : (
                <p className="offline-message">Activa tu estado en línea para recibir solicitudes.</p>
              )}
            </div>
          )}
        </div>

        <div className="sidebar">
          <div className="stats-card">
            <h3>Estadísticas</h3>
            <div className="stat">
              <span className="label">Viajes Completados:</span>
              <span className="value">{completedTrips.length}</span>
            </div>
            <div className="stat">
              <span className="label">Ganancias:</span>
              <span className="value">ARS {earnings.toFixed(2)}</span>
            </div>
            <div className="stat">
              <span className="label">Tarifa actual:</span>
              <span className="value">ARS {fareRate} / km</span>
            </div>
          </div>

          <div className="history-card">
            <h3>Últimos Viajes</h3>
            {completedTrips.length === 0 ? (
              <p className="no-history">Todavía no has completado viajes</p>
            ) : (
              <div className="completed-trips">
                {completedTrips.slice(0, 5).map((trip) => (
                  <div key={trip.id} className="completed-trip">
                    <p>{trip.pickupAddress}</p>
                    <p className="destination">→ {trip.dropoffAddress}</p>
                    <p className="fare">ARS {trip.fare.toFixed(2)}</p>
                  </div>
                ))}
              </div>
            )}
          </div>

          {statusMessage && <div className="status-notice">{statusMessage}</div>}
        </div>
      </div>
    </div>
  );
};

export default DriverDashboard;
