import React, { useEffect, useState } from 'react';
import './App.css';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import DriverDashboard from './pages/DriverDashboard';
import AdminDashboard from './pages/AdminDashboard';

function App() {
  const [user, setUser] = useState(() => {
    try {
      const stored = window.localStorage.getItem('mototaxiUser');
      return stored ? JSON.parse(stored) : null;
    } catch {
      return null;
    }
  });
  const [showRegister, setShowRegister] = useState(false);

  useEffect(() => {
    if (user) {
      window.localStorage.setItem('mototaxiUser', JSON.stringify(user));
    } else {
      window.localStorage.removeItem('mototaxiUser');
    }
  }, [user]);

  return (
    <div className="App">
      {!user ? (
        <Login 
          onLogin={setUser} 
          showRegister={showRegister}
          setShowRegister={setShowRegister}
        />
      ) : user.userType === 'passenger' ? (
        <Dashboard user={user} onLogout={() => setUser(null)} />
      ) : user.userType === 'admin' ? (
        <AdminDashboard user={user} onLogout={() => setUser(null)} />
      ) : (
        <DriverDashboard user={user} onLogout={() => { setUser(null); setShowRegister(false); }} />
      )}
    </div>
  );
}

export default App;
