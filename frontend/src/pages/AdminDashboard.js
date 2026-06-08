import React, { useEffect, useState } from 'react';
import './AdminDashboard.css';
import { API_URL } from '../config';

const AdminDashboard = ({ user, onLogout }) => {
  const [stats, setStats] = useState(null);
  const [users, setUsers] = useState([]);
  const [drivers, setDrivers] = useState([]);
  const [farePolicy, setFarePolicy] = useState(null);
  const [newFare, setNewFare] = useState(0);
  const [newFee, setNewFee] = useState(0);
  const [adminPaidFee, setAdminPaidFee] = useState(false);
  const [error, setError] = useState('');

  const loadData = async () => {
    try {
      const [statsRes, usersRes, driversRes] = await Promise.all([
        fetch(`${API_URL}/api/admin/stats`),
        fetch(`${API_URL}/api/admin/users`),
        fetch(`${API_URL}/api/admin/drivers`)
      ]);

      if (!statsRes.ok || !usersRes.ok || !driversRes.ok) {
        setError('No se pudieron cargar los datos administrativos');
        return;
      }

      const statsData = await statsRes.json();
      setStats(statsData);
      setFarePolicy(statsData.farePolicy || null);
      setNewFare(statsData?.farePolicy?.baseFareRate || 0);
      setNewFee(statsData?.farePolicy?.adminModificationFee || 0);
      setUsers(await usersRes.json());
      setDrivers(await driversRes.json());
    } catch (err) {
      console.error(err);
      setError('Error de conexión con el servidor');
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  return (
    <div className="admin-dashboard">
      <header className="admin-header">
        <div>
          <h1>🛠️ Panel Administrativo</h1>
          <p>Administrador: {user.name}</p>
        </div>
        <button className="logout-btn" onClick={onLogout}>Salir</button>
      </header>

      {error && <div className="admin-error">{error}</div>}

      {stats ? (
        <>
          <div className="stats-grid">
            <div className="stat-card">
              <h3>Pasajeros</h3>
              <p>{stats.totalPassengers}</p>
            </div>
            <div className="stat-card">
              <h3>Conductores</h3>
              <p>{stats.totalDrivers}</p>
            </div>
            <div className="stat-card">
              <h3>Admins</h3>
              <p>{stats.totalAdmins}</p>
            </div>
            <div className="stat-card">
              <h3>Viajes Totales</h3>
              <p>{stats.totalTrips}</p>
            </div>
            <div className="stat-card">
              <h3>Viajes completados</h3>
              <p>{stats.completedTrips}</p>
            </div>
            <div className="stat-card">
              <h3>Ingresos</h3>
              <p>ARS {stats.totalRevenue.toFixed(2)}</p>
            </div>
            <div className="stat-card">
              <h3>Rating conductor promedio</h3>
              <p>{stats.averageDriverRating}</p>
            </div>
            <div className="stat-card">
              <h3>Rating pasajero promedio</h3>
              <p>{stats.averagePassengerRating}</p>
            </div>
          </div>
          {farePolicy && (
            <div className="fare-summary">
              <div className="stat-card">
                <h3>Tarifa base</h3>
                <p>ARS {farePolicy.baseFareRate}</p>
              </div>
              <div className="stat-card">
                <h3>Cargo admin</h3>
                <p>ARS {farePolicy.adminModificationFee}</p>
              </div>
            </div>
          )}
        </>
      ) : (
        <p className="admin-loading">Cargando estadísticas...</p>
      )}

      <section className="admin-section">
        <h2>Usuarios</h2>
        <div className="admin-table">
          <div className="table-row header">
            <span>Nombre</span>
            <span>Email</span>
            <span>Tipo</span>
            <span>Rating</span>
          </div>
          {users.map((item) => (
            <div key={item.id} className="table-row">
              <span>{item.name}</span>
              <span>{item.email}</span>
              <span>{item.userType}</span>
              <span>{item.rating}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="admin-section">
        <h2>Conductores</h2>
        <div className="admin-table">
          <div className="table-row header">
            <span>Vehículo</span>
            <span>Estado</span>
            <span>Tarifa</span>
            <span>Viajes</span>
          </div>
          {drivers.map((item) => (
            <div key={item.id} className="table-row">
              <span>{item.vehicleBrand} {item.vehicleModel}</span>
              <span>{item.isOnline ? 'En línea' : 'Offline'}</span>
              <span>ARS {item.fareRate}</span>
              <span>{item.tripsCompleted}</span>
            </div>
          ))}
        </div>
      </section>

      {farePolicy && (
        <section className="admin-section">
          <h2>Tarifa del servicio</h2>
          <div className="fare-policy-card">
            <p><strong>Base actual:</strong> ARS {farePolicy.baseFareRate}</p>
            <p><strong>Costo por modificación de admin:</strong> ARS {farePolicy.adminModificationFee}</p>
            <div className="input-group">
              <label>Nueva tarifa base</label>
              <input
                type="number"
                min="1"
                value={newFare}
                onChange={(e) => setNewFare(Number(e.target.value))}
              />
            </div>
            <div className="input-group">
              <label>Costo de modificación para admin</label>
              <input
                type="number"
                min="0"
                value={newFee}
                onChange={(e) => setNewFee(Number(e.target.value))}
              />
            </div>
            <div className="input-group checkbox-group">
              <label>
                <input
                  type="checkbox"
                  checked={adminPaidFee}
                  onChange={(e) => setAdminPaidFee(e.target.checked)}
                /> El administrador paga el adicional para modificar la tarifa
              </label>
            </div>
            <button className="save-fare-btn" onClick={async () => {
              try {
                const response = await fetch(`${API_URL}/api/fare-policy`, {
                  method: 'PUT',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({
                    userId: user.id,
                    baseFareRate: newFare,
                    adminPaidFee,
                    adminModificationFee: newFee
                  })
                });
                if (response.ok) {
                  const updated = await response.json();
                  setFarePolicy(updated.farePolicy || updated);
                  setError('Tarifa actualizada correctamente');
                } else {
                  const payload = await response.json();
                  setError(payload.error || 'Error actualizando tarifa');
                }
              } catch (err) {
                setError('Error de conexión al actualizar tarifa');
              }
            }}>
              Actualizar tarifa
            </button>
          </div>
        </section>
      )}
      <section className="admin-section">
        <h2>Viajes recientes</h2>
        {stats && stats.recentTrips.length > 0 ? (
          <div className="recent-trips">
            {stats.recentTrips.map((trip) => (
              <div key={trip.id} className="recent-trip-card">
                <p><strong>{trip.pickupAddress}</strong> → <strong>{trip.dropoffAddress}</strong></p>
                <p>Estado: {trip.status} | Pago: {trip.paymentMethod || 'efectivo'}</p>
                <p>ARS {trip.fare.toFixed(2)} | {new Date(trip.createdAt).toLocaleString('es-ES')}</p>
              </div>
            ))}
          </div>
        ) : (
          <p className="admin-loading">No hay viajes recientes.</p>
        )}
      </section>
    </div>
  );
};

export default AdminDashboard;
