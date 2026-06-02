import React, { useState } from 'react';
import './App.css';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import DriverDashboard from './pages/DriverDashboard';

function App() {
  const [user, setUser] = useState(null);
  const [showRegister, setShowRegister] = useState(false);

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
      ) : (
        <DriverDashboard user={user} onLogout={() => setUser(null)} />
      )}
    </div>
  );
}

export default App;
