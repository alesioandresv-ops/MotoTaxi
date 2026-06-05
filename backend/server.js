const express = require('express');
const cors = require('cors');
const bodyParser = require('body-parser');
const { v4: uuidv4 } = require('uuid');
const bcrypt = require('bcryptjs');
const fs = require('fs');
const path = require('path');
const os = require('os');

const DATA_FILE = path.join(__dirname, 'data.json');
const OWNER_EMAIL = process.env.OWNER_EMAIL || 'propietario@mototaxi.com';
const HOST = process.env.HOST || '0.0.0.0';

const app = express();
const PORT = process.env.PORT || 3001;

// Middleware
app.use(cors());
app.use(bodyParser.json());

// Base de datos en memoria
const users = [];
const drivers = [];
const trips = [];
const ratings = [];
const farePolicy = {
  baseFareRate: 200,
  adminModificationFee: 150,
  serviceMultipliers: {
    mototaxi: 1,
    taxi: 1.2,
    remis: 1.3,
    local: 1.1,
    cortaDistancia: 1.5,
    largaDistancia: 3
  },
  modifications: []
};

function estimateDistance(pickupAddress, dropoffAddress, serviceType = 'mototaxi', routeType = 'local') {
  const base = Math.max(1, Math.round((pickupAddress.length + dropoffAddress.length) / 15));
  const serviceFactor = farePolicy.serviceMultipliers[serviceType] || 1;
  const routeFactor = farePolicy.serviceMultipliers[routeType] || 1;
  return Math.max(1, Math.round(base * serviceFactor * routeFactor));
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

function getUserById(userId) {
  return users.find(u => u.id === userId);
}

function isFareOwner(user) {
  return user && user.email && user.email.toLowerCase() === OWNER_EMAIL.toLowerCase();
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
    if (d.farePolicy) {
      Object.assign(farePolicy, d.farePolicy);
    }
    console.log('Datos cargados desde', DATA_FILE);
  } catch (err) {
    console.error('Error cargando datos:', err.message);
  }
}

function saveData() {
  try {
    fs.writeFileSync(DATA_FILE, JSON.stringify({ users, drivers, trips, ratings, farePolicy }, null, 2));
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

  if (userType === 'driver') {
    if (!vehicleBrand || !vehicleModel || !vehicleColor || !cc || !plateNumber || !drivingLicense || !lastService) {
      return res.status(400).json({ error: 'Faltan datos del vehículo o documentación requerida para el conductor' });
    }

    const plateOk = /^[A-Za-z0-9]+$/.test(String(plateNumber));
    if (!plateOk) {
      return res.status(400).json({ error: 'Formato de patente inválido. Debe contener letras y/o números.' });
    }
  }

  const hashedPassword = bcrypt.hashSync(password, 10);

  const user = {
    id: uuidv4(),
    name,
    email,
    password: hashedPassword,
    userType, // 'passenger', 'driver' o 'admin'
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
      plateNumber: driver.plateNumber,
      drivingLicense: driver.drivingLicense,
      lastService: driver.lastService
    };
  }

  saveData();
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
        vehicleBrand: driver.vehicleBrand,
        vehicleModel: driver.vehicleModel,
        vehicleColor: driver.vehicleColor,
        cc: driver.cc,
        plateNumber: driver.plateNumber,
        phone: driver.phone,
        isOnline: driver.isOnline,
        isAvailable: driver.isAvailable,
        fareRate: driver.fareRate,
        insuranceType: driver.insuranceType,
        drivingLicense: driver.drivingLicense,
        lastService: driver.lastService
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
  const { fareRate, userId } = req.body;
  const requestor = getUserById(userId);
  const driver = drivers.find(d => d.id === driverId);

  if (!driver) {
    return res.status(404).json({ error: 'Conductor no encontrado' });
  }

  if (!requestor || !isFareOwner(requestor)) {
    return res.status(403).json({ error: 'Solo el propietario puede modificar la tarifa de conductor.' });
  }

  driver.fareRate = Number(fareRate) || driver.fareRate;
  saveData();
  res.json({ message: 'Tarifa actualizada por propietario', driver });
});

app.put('/api/drivers/:driverId/location', (req, res) => {
  const { driverId } = req.params;
  const { lat, lng } = req.body;
  
  const driver = drivers.find(d => d.id === driverId);
  if (driver) {
    driver.location = { lat, lng };
    trips.forEach((t) => {
      if (t.driverId === driverId && ['accepted', 'ongoing'].includes(t.status)) {
        t.driverLocation = driver.location;
      }
    });
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
  const {
    userId,
    pickupLocation,
    dropoffLocation,
    pickupAddress,
    dropoffAddress,
    paymentMethod,
    serviceType,
    routeType
  } = req.body;
  const passenger = users.find(u => u.id === userId);

  if (!passenger) {
    return res.status(404).json({ error: 'Pasajero no encontrado' });
  }

  const service = serviceType || 'mototaxi';
  const route = routeType || 'local';
  const distance = estimateDistance(pickupAddress, dropoffAddress, service, route);
  const fare = calculateFare(distance, farePolicy.baseFareRate);

  const trip = {
    id: uuidv4(),
    userId,
    driverId: null,
    pickupLocation,
    dropoffLocation,
    pickupAddress,
    dropoffAddress,
    serviceType: service,
    routeType: route,
    status: 'requested', // requested, accepted, ongoing, completed, cancelled
    distance,
    fare,
    paymentMethod: paymentMethod || 'efectivo',
    paymentStatus: 'pending',
    currency: 'ARS',
    createdAt: new Date(),
    startTime: null,
    endTime: null,
    rated: false
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
  trip.fare = calculateFare(trip.distance || 1, farePolicy.baseFareRate);
  trip.driverUserId = driver.userId;
  trip.driverLocation = driver.location;
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
      trip.driverLocation = driver.location;
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
  
  const trip = trips.find(t => t.id === tripId);
  if (!trip) {
    return res.status(404).json({ error: 'Viaje no encontrado para calificar' });
  }

  const ratingObj = {
    id: uuidv4(),
    tripId,
    ratedUserId,
    rating,
    comment,
    createdAt: new Date()
  };

  ratings.push(ratingObj);
  if (trip) {
    trip.rated = true;
    trip.ratingValue = rating;
    trip.ratingComment = comment;
  }

  saveData();
  
  const user = users.find(u => u.id === ratedUserId);
  if (user) {
    const userRatings = ratings.filter(r => r.ratedUserId === ratedUserId);
    user.rating = Number((userRatings.reduce((sum, r) => sum + r.rating, 0) / userRatings.length).toFixed(1));
    saveData();
  }

  res.status(201).json({ message: 'Calificación registrada', rating: ratingObj });
});

app.get('/api/ratings/:userId', (req, res) => {
  const { userId } = req.params;
  const userRatings = ratings.filter(r => r.ratedUserId === userId);
  res.json(userRatings);
});

app.get('/api/admin/stats', (req, res) => {
  const totalPassengers = users.filter(u => u.userType === 'passenger').length;
  const totalDrivers = drivers.length;
  const totalAdmins = users.filter(u => u.userType === 'admin').length;
  const totalTrips = trips.length;
  const completedTrips = trips.filter(t => t.status === 'completed').length;
  const totalRevenue = trips.filter(t => t.status === 'completed').reduce((sum, t) => sum + (t.fare || 0), 0);
  const averageDriverRating = drivers.length ? Number((drivers.reduce((sum, d) => sum + (d.rating || 0), 0) / drivers.length).toFixed(1)) : 0;
  const averagePassengerRating = users.filter(u => u.userType === 'passenger').length ? Number((users.filter(u => u.userType === 'passenger').reduce((sum, u) => sum + (u.rating || 0), 0) / users.filter(u => u.userType === 'passenger').length).toFixed(1)) : 0;

  res.json({
    totalPassengers,
    totalDrivers,
    totalAdmins,
    totalTrips,
    completedTrips,
    totalRevenue,
    averageDriverRating,
    averagePassengerRating,
    farePolicy,
    recentTrips: trips.slice(-6).reverse()
  });
});

app.get('/api/fare-policy', (req, res) => {
  res.json(farePolicy);
});

app.put('/api/fare-policy', (req, res) => {
  const { userId, baseFareRate, adminPaidFee } = req.body;
  const requestor = getUserById(userId);

  if (!requestor) {
    return res.status(404).json({ error: 'Usuario no encontrado' });
  }

  if (isFareOwner(requestor)) {
    if (typeof baseFareRate === 'number') {
      farePolicy.baseFareRate = baseFareRate;
    }
    if (typeof req.body.adminModificationFee === 'number') {
      farePolicy.adminModificationFee = req.body.adminModificationFee;
    }
    saveData();
    return res.json({ message: 'Tarifa actualizada por propietario', farePolicy });
  }

  if (requestor.userType === 'admin') {
    if (!adminPaidFee) {
      return res.status(403).json({ error: 'Los administradores deben pagar un adicional para modificar la tarifa.' });
    }

    const oldRate = farePolicy.baseFareRate;
    if (typeof baseFareRate === 'number') {
      farePolicy.baseFareRate = baseFareRate;
    }
    farePolicy.modifications.push({
      id: uuidv4(),
      adminId: requestor.id,
      adminEmail: requestor.email,
      oldRate,
      newRate: farePolicy.baseFareRate,
      feeCharged: farePolicy.adminModificationFee,
      createdAt: new Date()
    });
    saveData();
    return res.json({ message: 'Tarifa modificada por administrador con cargo adicional', farePolicy });
  }

  res.status(403).json({ error: 'No tienes permiso para modificar la tarifa.' });
});

app.get('/api/admin/fare-modifications', (req, res) => {
  res.json(farePolicy.modifications);
});

app.get('/api/admin/users', (req, res) => {
  const summary = users.map(u => ({
    id: u.id,
    name: u.name,
    email: u.email,
    userType: u.userType,
    rating: u.rating,
    createdAt: u.createdAt
  }));
  res.json(summary);
});

app.get('/api/admin/drivers', (req, res) => {
  const summary = drivers.map(d => ({
    id: d.id,
    userId: d.userId,
    vehicleBrand: d.vehicleBrand,
    vehicleModel: d.vehicleModel,
    isOnline: d.isOnline,
    fareRate: d.fareRate,
    tripsCompleted: d.tripsCompleted,
    rating: d.rating
  }));
  res.json(summary);
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

// Servir archivos estáticos (React)
app.use(express.static(path.join(__dirname, '../frontend/build')));

// Ruta para servir el archivo index.html
app.get('*', (req, res) => {
  res.sendFile(path.join(__dirname, '../frontend/build/index.html'));
});

function getLocalIp() {
  const interfaces = os.networkInterfaces();
  for (const name of Object.keys(interfaces)) {
    for (const iface of interfaces[name]) {
      if (iface.family === 'IPv4' && !iface.internal) {
        return iface.address;
      }
    }
  }
  return 'localhost';
}

app.listen(PORT, HOST, () => {
  const localIp = getLocalIp();
  console.log(`🏍️  Servidor de MotoTaxi ejecutándose en http://localhost:${PORT}`);
  console.log(`📶  Si estás en la misma red, usa http://${localIp}:${PORT}`);
  console.log(`📊 Estado: http://localhost:${PORT}/api/health`);
});
