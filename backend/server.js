const express = require('express');
const cors = require('cors');
const bodyParser = require('body-parser');
const { v4: uuidv4 } = require('uuid');
const bcrypt = require('bcryptjs');
const fs = require('fs');
const path = require('path');

const DATA_FILE = path.join(__dirname, 'data.json');

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

function estimateDistance(pickupAddress, dropoffAddress) {
  const base = Math.max(1, Math.round((pickupAddress.length + dropoffAddress.length) / 15));
  return base;
}

function formatCurrencyARS(amount) {
  return Number(amount.toFixed(2));
}

function calculateFare(distance, rate) {
  return formatCurrencyARS(Math.max(150, distance * rate));
}

function isDriverBusy(driverId) {
  return trips.some(t => t.driverId === driverId && ['accepted', 'ongoing'].includes(t.status));
}

// Cargar datos persistidos si existen
if (fs.existsSync(DATA_FILE)) {
  try {
    const raw = fs.readFileSync(DATA_FILE, 'utf8');
    const d = JSON.parse(raw || '{}');
    if (d.users) users.push(...d.users);
    if (d.drivers) drivers.push(...d.drivers);
    if (d.trips) trips.push(...d.trips);
    if (d.ratings) ratings.push(...d.ratings);
    console.log('Datos cargados desde', DATA_FILE);
  } catch (err) {
    console.error('Error cargando datos:', err.message);
  }
}

function saveData() {
  try {
    fs.writeFileSync(DATA_FILE, JSON.stringify({ users, drivers, trips, ratings }, null, 2));
  } catch (err) {
    console.error('Error guardando datos:', err.message);
  }
}

// Rutas de Autenticación
app.post('/api/auth/register', (req, res) => {
  const {
    name,
    email,
    password,
    userType,
    phone,
    // driver specific
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
  } = req.body;

  if (!name || !email || !password || !userType || !phone) {
    return res.status(400).json({ error: 'Faltan campos requeridos' });
  }

  if (users.find(u => u.email === email)) {
    return res.status(409).json({ error: 'El correo ya está registrado' });
  }

  const hashedPassword = bcrypt.hashSync(password, 10);

  const user = {
    id: uuidv4(),
    name,
    email,
    password: hashedPassword,
    userType, // 'passenger' o 'driver'
    createdAt: new Date(),
    phone,
    rating: 5.0
  };

  users.push(user);
  saveData();

  let userResponse = {
    id: user.id,
    name: user.name,
    email: user.email,
    userType: user.userType,
    rating: user.rating
  };

  if (userType === 'driver') {
    // Validaciones obligatorias para conductores
    if (!vehicleBrand || !vehicleModel || !vehicleColor || !cc || !plateNumber || !drivingLicense || !lastService) {
      return res.status(400).json({ error: 'Faltan datos del vehículo o documentación requerida para el conductor' });
    }

    // Validar formato de patente (alfanumérico)
    const plateOk = /^[A-Za-z0-9]+$/.test(String(plateNumber));
    if (!plateOk) {
      return res.status(400).json({ error: 'Formato de patente inválido. Debe contener letras y/o números.' });
    }

    const driver = {
      id: uuidv4(),
      userId: user.id,
      vehicleBrand,
      vehicleModel,
      vehicleColor,
      cc,
      plateNumber,
      hasHelmetDriver: Boolean(hasHelmetDriver),
      hasHelmetPassenger: Boolean(hasHelmetPassenger),
      hasInsurance: Boolean(hasInsurance),
      insuranceType: hasInsurance ? (insuranceType || '') : '',
      drivingLicense: drivingLicense || '',
      lastService: lastService || '',
      phone,
      rating: 5.0,
      tripsCompleted: 0,
      isOnline: false,
      isAvailable: false,
      location: { lat: 0, lng: 0 },
      fareRate: 200,
      createdAt: new Date()
    };

    drivers.push(driver);
    saveData();
    userResponse.driverProfile = {
      driverId: driver.id,
      vehicleBrand: driver.vehicleBrand,
      vehicleModel: driver.vehicleModel,
      vehicleColor: driver.vehicleColor,
      cc: driver.cc,
      phone: driver.phone,
      isOnline: driver.isOnline,
      isAvailable: driver.isAvailable,
      fareRate: driver.fareRate,
      // keep plateNumber in driver profile for driver UI only
      plateNumber: driver.plateNumber,
      drivingLicense: driver.drivingLicense,
      lastService: driver.lastService
    };
  }

  res.status(201).json({ message: 'Usuario registrado exitosamente', user: userResponse });
});

app.post('/api/auth/login', (req, res) => {
  const { email, password } = req.body;

  const user = users.find(u => u.email === email);

  if (!user || !bcrypt.compareSync(password, user.password)) {
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
        isOnline: driver.isOnline,
        isAvailable: driver.isAvailable,
        fareRate: driver.fareRate
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
  saveData();
  res.status(201).json({ message: 'Conductor registrado', driver });
});

app.get('/api/drivers/available', (req, res) => {
  const availableDrivers = drivers.filter(d => d.isAvailable);
  res.json(availableDrivers);
});

app.put('/api/drivers/:driverId/status', (req, res) => {
  const { driverId } = req.params;
  const { isOnline } = req.body;
  
  const driver = drivers.find(d => d.id === driverId);
  if (driver) {
    driver.isOnline = Boolean(isOnline);
    driver.isAvailable = driver.isOnline && !isDriverBusy(driverId);
    saveData();
    res.json({ message: 'Estado actualizado', driver });
  } else {
    res.status(404).json({ error: 'Conductor no encontrado' });
  }
});

app.put('/api/drivers/:driverId/tarifa', (req, res) => {
  const { driverId } = req.params;
  const { fareRate } = req.body;
  
  const driver = drivers.find(d => d.id === driverId);
  if (driver) {
    driver.fareRate = Number(fareRate) || driver.fareRate;
    saveData();
    res.json({ message: 'Tarifa actualizada', driver });
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
    saveData();
    res.json({ message: 'Ubicación actualizada', driver });
  } else {
    res.status(404).json({ error: 'Conductor no encontrado' });
  }
});

app.get('/api/drivers/:driverId/requests', (req, res) => {
  const { driverId } = req.params;
  const driver = drivers.find(d => d.id === driverId);

  if (!driver) {
    return res.status(404).json({ error: 'Conductor no encontrado' });
  }

  if (!driver.isOnline) {
    return res.json([]);
  }

  const availableTrips = trips.filter(t => t.status === 'requested');
  res.json(availableTrips);
});

app.get('/api/drivers/:driverId/trips', (req, res) => {
  const { driverId } = req.params;
  const driverTrips = trips.filter(t => t.driverId === driverId);
  res.json(driverTrips);
});

app.get('/api/drivers/:driverId', (req, res) => {
  const { driverId } = req.params;
  const driver = drivers.find(d => d.id === driverId);
  if (driver) {
    res.json(driver);
  } else {
    res.status(404).json({ error: 'Conductor no encontrado' });
  }
});

app.get('/api/trips/:tripId', (req, res) => {
  const { tripId } = req.params;
  const trip = trips.find(t => t.id === tripId);
  if (trip) {
    res.json(trip);
  } else {
    res.status(404).json({ error: 'Viaje no encontrado' });
  }
});

// Rutas de Viajes
app.post('/api/trips/request', (req, res) => {
  const { userId, pickupLocation, dropoffLocation, pickupAddress, dropoffAddress } = req.body;
  const passenger = users.find(u => u.id === userId);

  if (!passenger) {
    return res.status(404).json({ error: 'Pasajero no encontrado' });
  }

  const distance = estimateDistance(pickupAddress, dropoffAddress);
  const defaultRate = 200;
  const fare = calculateFare(distance, defaultRate);

  const trip = {
    id: uuidv4(),
    userId,
    driverId: null,
    pickupLocation,
    dropoffLocation,
    pickupAddress,
    dropoffAddress,
    status: 'requested', // requested, accepted, ongoing, completed, cancelled
    distance,
    fare,
    currency: 'ARS',
    createdAt: new Date(),
    startTime: null,
    endTime: null
  };

  trips.push(trip);
  saveData();
  res.status(201).json({ message: 'Viaje solicitado', trip });
});

app.put('/api/trips/:tripId/accept', (req, res) => {
  const { tripId } = req.params;
  const { driverId } = req.body;

  const trip = trips.find(t => t.id === tripId);
  const driver = drivers.find(d => d.id === driverId);

  if (!trip) {
    return res.status(404).json({ error: 'Viaje no encontrado' });
  }

  if (!driver) {
    return res.status(404).json({ error: 'Conductor no encontrado' });
  }

  if (!driver.isOnline) {
    return res.status(400).json({ error: 'El conductor no está en línea' });
  }

  if (trip.status !== 'requested') {
    return res.status(400).json({ error: 'El viaje ya fue aceptado o no está disponible' });
  }

  trip.driverId = driverId;
  trip.status = 'accepted';
  trip.fare = calculateFare(trip.distance || 1, driver.fareRate || 200);
  // Attach a public snapshot of driver data for the passenger (hide exact plate number)
  const userOfDriver = users.find(u => u.id === driver.userId);
  trip.driverSnapshot = {
    name: userOfDriver ? userOfDriver.name : 'Conductor',
    vehicleBrand: driver.vehicleBrand,
    vehicleModel: driver.vehicleModel,
    vehicleColor: driver.vehicleColor,
    cc: driver.cc,
    hasPlate: Boolean(driver.plateNumber),
    hasHelmetDriver: driver.hasHelmetDriver,
    hasHelmetPassenger: driver.hasHelmetPassenger,
    hasInsurance: driver.hasInsurance,
    insuranceType: driver.hasInsurance ? driver.insuranceType : '',
    drivingLicense: driver.drivingLicense,
    lastService: driver.lastService
  };
  driver.isAvailable = false;
  saveData();

  res.json({ message: 'Viaje aceptado', trip });
});

app.put('/api/trips/:tripId/start', (req, res) => {
  const { tripId } = req.params;
  
  const trip = trips.find(t => t.id === tripId);
  if (trip) {
    trip.status = 'ongoing';
    trip.startTime = new Date();
    const driver = drivers.find(d => d.id === trip.driverId);
    if (driver) {
      driver.isAvailable = false;
    }
    saveData();
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
    const driver = drivers.find(d => d.id === trip.driverId);
    if (driver) {
      driver.tripsCompleted = (driver.tripsCompleted || 0) + 1;
      driver.isAvailable = driver.isOnline && !isDriverBusy(driver.id);
    }
    saveData();
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
  saveData();
  
  // Actualizar rating del usuario
  const user = users.find(u => u.id === ratedUserId);
  if (user) {
    const userRatings = ratings.filter(r => r.ratedUserId === ratedUserId);
    user.rating = (userRatings.reduce((sum, r) => sum + r.rating, 0) / userRatings.length).toFixed(1);
    saveData();
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
