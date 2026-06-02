const express = require('express');
const cors = require('cors');
const bodyParser = require('body-parser');
const { v4: uuidv4 } = require('uuid');

const app = express();
const PORT = 3001;

// Middleware
app.use(cors());
app.use(bodyParser.json());

// Base de datos en memoria
const users = [];
const drivers = [];
const trips = [];
const ratings = [];

// Rutas de Autenticación
app.post('/api/auth/register', (req, res) => {
  const { name, email, password, userType, phone, vehicle, licenseNumber } = req.body;
  
  if (!name || !email || !password || !userType || !phone) {
    return res.status(400).json({ error: 'Faltan campos requeridos' });
  }

  if (users.find(u => u.email === email)) {
    return res.status(409).json({ error: 'El correo ya está registrado' });
  }

  const user = {
    id: uuidv4(),
    name,
    email,
    password,
    userType, // 'passenger' o 'driver'
    createdAt: new Date(),
    phone,
    rating: 5.0
  };

  users.push(user);

  let userResponse = {
    id: user.id,
    name: user.name,
    email: user.email,
    userType: user.userType,
    rating: user.rating
  };

  if (userType === 'driver') {
    const driver = {
      id: uuidv4(),
      userId: user.id,
      vehicle: vehicle || 'Moto estándar',
      licenseNumber: licenseNumber || '',
      phone,
      rating: 5.0,
      tripsCompleted: 0,
      isAvailable: true,
      location: { lat: 0, lng: 0 },
      createdAt: new Date()
    };

    drivers.push(driver);
    userResponse.driverProfile = {
      driverId: driver.id,
      vehicle: driver.vehicle,
      licenseNumber: driver.licenseNumber,
      phone: driver.phone
    };
  }

  res.status(201).json({ message: 'Usuario registrado exitosamente', user: userResponse });
});

app.post('/api/auth/login', (req, res) => {
  const { email, password } = req.body;
  
  const user = users.find(u => u.email === email && u.password === password);
  
  if (!user) {
    return res.status(401).json({ error: 'Email o contraseña incorrectos' });
  }

  const userResponse = {
    id: user.id,
    name: user.name,
    email: user.email,
    userType: user.userType,
    rating: user.rating
  };

  if (user.userType === 'driver') {
    const driver = drivers.find((d) => d.userId === user.id);
    if (driver) {
      userResponse.driverProfile = {
        driverId: driver.id,
        vehicle: driver.vehicle,
        licenseNumber: driver.licenseNumber,
        phone: driver.phone,
        isAvailable: driver.isAvailable
      };
    }
  }

  res.json({ 
    message: 'Login exitoso', 
    user: userResponse
  });
});

// Rutas de Conductores
app.post('/api/drivers/register', (req, res) => {
  const { userId, vehicle, licenseNumber, phone } = req.body;
  
  const driver = {
    id: uuidv4(),
    userId,
    vehicle,
    licenseNumber,
    phone,
    rating: 5.0,
    tripsCompleted: 0,
    isAvailable: true,
    location: { lat: 0, lng: 0 },
    createdAt: new Date()
  };

  drivers.push(driver);
  res.status(201).json({ message: 'Conductor registrado', driver });
});

app.get('/api/drivers/available', (req, res) => {
  const availableDrivers = drivers.filter(d => d.isAvailable);
  res.json(availableDrivers);
});

app.put('/api/drivers/:driverId/status', (req, res) => {
  const { driverId } = req.params;
  const { isAvailable } = req.body;
  
  const driver = drivers.find(d => d.id === driverId);
  if (driver) {
    driver.isAvailable = isAvailable;
    res.json({ message: 'Estado actualizado', driver });
  } else {
    res.status(404).json({ error: 'Conductor no encontrado' });
  }
});

app.put('/api/drivers/:driverId/location', (req, res) => {
  const { driverId } = req.params;
  const { lat, lng } = req.body;
  
  const driver = drivers.find(d => d.id === driverId);
  if (driver) {
    driver.location = { lat, lng };
    res.json({ message: 'Ubicación actualizada', driver });
  } else {
    res.status(404).json({ error: 'Conductor no encontrado' });
  }
});

// Rutas de Viajes
app.post('/api/trips/request', (req, res) => {
  const { userId, pickupLocation, dropoffLocation, pickupAddress, dropoffAddress } = req.body;
  
  const nearestDriver = drivers.find(d => d.isAvailable);
  
  if (!nearestDriver) {
    return res.status(404).json({ error: 'No hay conductores disponibles' });
  }

  const trip = {
    id: uuidv4(),
    userId,
    driverId: nearestDriver.id,
    pickupLocation,
    dropoffLocation,
    pickupAddress,
    dropoffAddress,
    status: 'requested', // requested, accepted, ongoing, completed, cancelled
    fare: Math.random() * 50 + 5,
    createdAt: new Date(),
    startTime: null,
    endTime: null
  };

  trips.push(trip);
  res.status(201).json({ message: 'Viaje solicitado', trip });
});

app.put('/api/trips/:tripId/accept', (req, res) => {
  const { tripId } = req.params;
  
  const trip = trips.find(t => t.id === tripId);
  if (trip) {
    trip.status = 'accepted';
    res.json({ message: 'Viaje aceptado', trip });
  } else {
    res.status(404).json({ error: 'Viaje no encontrado' });
  }
});

app.put('/api/trips/:tripId/start', (req, res) => {
  const { tripId } = req.params;
  
  const trip = trips.find(t => t.id === tripId);
  if (trip) {
    trip.status = 'ongoing';
    trip.startTime = new Date();
    res.json({ message: 'Viaje iniciado', trip });
  } else {
    res.status(404).json({ error: 'Viaje no encontrado' });
  }
});

app.put('/api/trips/:tripId/complete', (req, res) => {
  const { tripId } = req.params;
  
  const trip = trips.find(t => t.id === tripId);
  if (trip) {
    trip.status = 'completed';
    trip.endTime = new Date();
    res.json({ message: 'Viaje completado', trip });
  } else {
    res.status(404).json({ error: 'Viaje no encontrado' });
  }
});

app.get('/api/trips/user/:userId', (req, res) => {
  const { userId } = req.params;
  const userTrips = trips.filter(t => t.userId === userId);
  res.json(userTrips);
});

// Rutas de Calificaciones
app.post('/api/ratings', (req, res) => {
  const { tripId, ratedUserId, rating, comment } = req.body;
  
  const ratingObj = {
    id: uuidv4(),
    tripId,
    ratedUserId,
    rating,
    comment,
    createdAt: new Date()
  };

  ratings.push(ratingObj);
  
  // Actualizar rating del usuario
  const user = users.find(u => u.id === ratedUserId);
  if (user) {
    const userRatings = ratings.filter(r => r.ratedUserId === ratedUserId);
    user.rating = (userRatings.reduce((sum, r) => sum + r.rating, 0) / userRatings.length).toFixed(1);
  }

  res.status(201).json({ message: 'Calificación registrada', rating: ratingObj });
});

app.get('/api/ratings/:userId', (req, res) => {
  const { userId } = req.params;
  const userRatings = ratings.filter(r => r.ratedUserId === userId);
  res.json(userRatings);
});

// Ruta de prueba
app.get('/api/health', (req, res) => {
  res.json({ 
    status: 'OK', 
    message: 'Servidor de MotoTaxi funcionando',
    users: users.length,
    drivers: drivers.length,
    trips: trips.length
  });
});

app.listen(PORT, () => {
  console.log(`🏍️  Servidor de MotoTaxi ejecutándose en http://localhost:${PORT}`);
  console.log(`📊 Estado: http://localhost:${PORT}/api/health`);
});
