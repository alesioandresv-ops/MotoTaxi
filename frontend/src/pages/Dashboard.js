import React, { useState, useEffect } from 'react';
import './Dashboard.css';

const API_URL = 'http://localhost:3001';

const Dashboard = ({ user, onLogout }) => {
  const [pickupAddress, setPickupAddress] = useState('');
  const [dropoffAddress, setDropoffAddress] = useState('');
  const [activeTrip, setActiveTrip] = useState(null);
  const [trips, setTrips] = useState([]);
  const [showHistory, setShowHistory] = useState(false);
  const [statusMessage, setStatusMessage] = useState('');

  const loadTrips = async () => {
    try {
      const response = await fetch(`${API_URL}/api/trips/user/${user.id}`);
      if (response.ok) {
        const userTrips = await response.json();
        setTrips(userTrips.sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt)));
        const active = userTrips.find((trip) => ['requested', 'accepted', 'ongoing'].includes(trip.status));
        setActiveTrip(active || null);
      }
    } catch (err) {
      console.error('Error cargando viajes del pasajero', err);
    }
  };

  const loadActiveTrip = async (tripId) => {
    try {
      const response = await fetch(`${API_URL}/api/trips/${tripId}`);
      if (response.ok) {
        const trip = await response.json();
        setActiveTrip(trip);
      }
    } catch (err) {
      console.error('Error actualizando viaje activo', err);
    }
  };

  useEffect(() => {
    loadTrips();
  }, [user.id]);

  useEffect(() => {
    if (!activeTrip) return;
    const interval = setInterval(() => {
      loadActiveTrip(activeTrip.id);
      loadTrips();
    }, 5000);
    return () => clearInterval(interval);
  }, [activeTrip]);

  const requestTrip = async () => {
    if (!pickupAddress || !dropoffAddress) {
      setStatusMessage('Por favor completa los campos');
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
        const data = await response.json();
        setActiveTrip(data.trip);
        setTrips([data.trip, ...trips]);
        setPickupAddress('');
        setDropoffAddress('');
        setStatusMessage('Viaje solicitado correctamente. Esperando aceptación de conductor.');
      } else {
        const errorData = await response.json();
        setStatusMessage(errorData.error || 'Error al solicitar viaje');
      }
    } catch (err) {
      setStatusMessage('Error de conexión al solicitar viaje');
    }
  };

  const cancelTrip = () => {
    setActiveTrip(null);
    setStatusMessage('Viaje cancelado localmente. Refresca para ver cambios en el servidor.');
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
              {statusMessage && <div className="status-message">{statusMessage}</div>}
              {activeTrip ? (
                <div className="trip-status">
                  <h3>Estado del Viaje: <span className={`status-${activeTrip.status}`}>{activeTrip.status}</span></h3>
                  <div className="trip-info">
                    <p><strong>Origen:</strong> {activeTrip.pickupAddress}</p>
                    <p><strong>Destino:</strong> {activeTrip.dropoffAddress}</p>
                    <p><strong>Tarifa:</strong> ARS {activeTrip.fare?.toFixed(2)}</p>
                    {activeTrip.distance != null && <p><strong>Distancia estimada:</strong> {activeTrip.distance} km</p>}
                  </div>
                  {activeTrip.driverSnapshot && (
                    <div className="driver-info">
                      <h4>Datos del conductor</h4>
                      <p><strong>Nombre:</strong> {activeTrip.driverSnapshot.name}</p>
                      <p><strong>Moto:</strong> {activeTrip.driverSnapshot.vehicleBrand} {activeTrip.driverSnapshot.vehicleModel} - {activeTrip.driverSnapshot.vehicleColor} ({activeTrip.driverSnapshot.cc} cc)</p>
                      <p><strong>Patente:</strong> {activeTrip.driverSnapshot.hasPlate ? 'SI' : 'NO'}</p>
                      <p><strong>Casco conductor:</strong> {activeTrip.driverSnapshot.hasHelmetDriver ? 'SI' : 'NO'}</p>
                      <p><strong>Casco acompañante:</strong> {activeTrip.driverSnapshot.hasHelmetPassenger ? 'SI' : 'NO'}</p>
                      <p><strong>Seguro:</strong> {activeTrip.driverSnapshot.hasInsurance ? `SI (${activeTrip.driverSnapshot.insuranceType || 'Tipo no especificado'})` : 'NO'}</p>
                      <p><strong>Carnet de conducir:</strong> {activeTrip.driverSnapshot.drivingLicense}</p>
                      <p><strong>Último servicio:</strong> {activeTrip.driverSnapshot.lastService}</p>
                    </div>
                  )}
                  {activeTrip.status === 'requested' && (
                    <div className="trip-actions">
                      <p>⏳ Esperando que un conductor acepte tu pedido...</p>
                    </div>
                  )}
                  {activeTrip.status === 'accepted' && (
                    <div className="trip-actions">
                      <p>✅ Conductor asignado. Prepárate para el viaje.</p>
                    </div>
                  )}
                  {activeTrip.status === 'ongoing' && (
                    <div className="trip-actions">
                      <p>🚗 Tu viaje ya comenzó.</p>
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
                <li>✅ Precios en pesos argentinos</li>
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
                      <span className="fare">ARS {trip.fare?.toFixed(2)}</span>
                    </div>
                    <p><strong>De:</strong> {trip.pickupAddress}</p>
                    <p><strong>A:</strong> {trip.dropoffAddress}</p>
                    {trip.distance != null && <p><small>{trip.distance} km</small></p>}
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
