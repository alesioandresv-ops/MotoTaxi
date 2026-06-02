import React, { useState } from 'react';
import './DriverDashboard.css';

const DriverDashboard = ({ user, onLogout }) => {
  const [isOnline, setIsOnline] = useState(false);
  const [activeTrip, setActiveTrip] = useState(null);
  const [pendingTrips, setPendingTrips] = useState([
    {
      id: '1',
      pickupAddress: 'Calle Principal 123',
      dropoffAddress: 'Centro Comercial XYZ',
      fare: 25.50,
      status: 'requested'
    },
    {
      id: '2',
      pickupAddress: 'Hospital General',
      dropoffAddress: 'Terminal de Autobuses',
      fare: 18.75,
      status: 'requested'
    }
  ]);
  const [completedTrips, setCompletedTrips] = useState([]);
  const [earnings, setEarnings] = useState(0);

  const toggleOnline = () => {
    setIsOnline(!isOnline);
  };

  const acceptTrip = (trip) => {
    setActiveTrip(trip);
    setPendingTrips(pendingTrips.filter(t => t.id !== trip.id));
  };

  const startTrip = () => {
    if (activeTrip) {
      setActiveTrip({ ...activeTrip, status: 'ongoing' });
    }
  };

  const completeTrip = () => {
    if (activeTrip) {
      const completedTrip = { ...activeTrip, status: 'completed' };
      setCompletedTrips([completedTrip, ...completedTrips]);
      setEarnings(earnings + activeTrip.fare);
      setActiveTrip(null);
    }
  };

  const cancelTrip = () => {
    if (activeTrip) {
      setPendingTrips([activeTrip, ...pendingTrips]);
      setActiveTrip(null);
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
            onClick={toggleOnline}
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
              <p><strong>Ganancias del Día:</strong> ${earnings.toFixed(2)}</p>
              <p><strong>Calificación:</strong> ⭐ {user.rating}</p>
            </div>
          </div>

          {activeTrip ? (
            <div className="active-trip-card">
              <h2>Viaje Activo</h2>
              <div className="trip-details">
                <p><strong>Origen:</strong> {activeTrip.pickupAddress}</p>
                <p><strong>Destino:</strong> {activeTrip.dropoffAddress}</p>
                <p><strong>Tarifa:</strong> ${activeTrip.fare.toFixed(2)}</p>
                <p><strong>Estado:</strong> <span className="trip-status">{activeTrip.status}</span></p>
              </div>

              <div className="trip-actions">
                {activeTrip.status === 'requested' && (
                  <>
                    <button className="start-btn" onClick={startTrip}>
                      🚀 Iniciar Viaje
                    </button>
                  </>
                )}
                {activeTrip.status === 'ongoing' && (
                  <>
                    <button className="complete-btn" onClick={completeTrip}>
                      ✅ Completar Viaje
                    </button>
                  </>
                )}
                <button className="cancel-btn" onClick={cancelTrip}>
                  ❌ Cancelar
                </button>
              </div>
            </div>
          ) : (
            <div className="pending-trips-card">
              <h2>Viajes Disponibles ({pendingTrips.length})</h2>
              {pendingTrips.length === 0 ? (
                <p className="no-trips">No hay viajes disponibles en este momento</p>
              ) : (
                <div className="trips-list">
                  {pendingTrips.map((trip) => (
                    <div key={trip.id} className="trip-item">
                      <div className="trip-info">
                        <p><strong>📍 Origen:</strong> {trip.pickupAddress}</p>
                        <p><strong>🎯 Destino:</strong> {trip.dropoffAddress}</p>
                        <p><strong>💰 Tarifa:</strong> ${trip.fare.toFixed(2)}</p>
                      </div>
                      <button
                        className="accept-btn"
                        onClick={() => acceptTrip(trip)}
                      >
                        Aceptar
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        <div className="sidebar">
          <div className="stats-card">
            <h3>Estadísticas</h3>
            <div className="stat">
              <span className="label">Viajes Hoy:</span>
              <span className="value">{completedTrips.length}</span>
            </div>
            <div className="stat">
              <span className="label">Ganancias:</span>
              <span className="value">${earnings.toFixed(2)}</span>
            </div>
            <div className="stat">
              <span className="label">Promedio por Viaje:</span>
              <span className="value">${completedTrips.length > 0 ? (earnings / completedTrips.length).toFixed(2) : '0.00'}</span>
            </div>
          </div>

          <div className="history-card">
            <h3>Últimos Viajes ({completedTrips.length})</h3>
            {completedTrips.length === 0 ? (
              <p className="no-history">Sin viajes completados</p>
            ) : (
              <div className="completed-trips">
                {completedTrips.slice(0, 5).map((trip) => (
                  <div key={trip.id} className="completed-trip">
                    <p>{trip.pickupAddress}</p>
                    <p className="destination">→ {trip.dropoffAddress}</p>
                    <p className="fare">${trip.fare.toFixed(2)}</p>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="info-card">
            <h3>💡 Consejos</h3>
            <ul>
              <li>Sé puntual siempre</li>
              <li>Ofrece un viaje seguro</li>
              <li>Mantén tu vehículo limpio</li>
              <li>Sé amable con los pasajeros</li>
              <li>Respeta los límites de velocidad</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
};

export default DriverDashboard;
