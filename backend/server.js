const express = require('express');
const cors = require('cors');
const bodyParser = require('body-parser');
const { v4: uuidv4 } = require('uuid');
const bcrypt = require('bcryptjs');
const path = require('path');
const { Sequelize, DataTypes, Op } = require('sequelize');

const OWNER_EMAIL = process.env.OWNER_EMAIL || 'propietario@mototaxi.com';

const app = express();
const PORT = process.env.PORT || 3001;

// Trust proxy (required when behind Railway / proxies) so we can detect original protocol
app.set('trust proxy', true);

// Middleware
app.use(cors());
app.use(bodyParser.json());

// En entornos de producción, forzar redireccion a HTTPS si la petición llegó por HTTP
if (process.env.ENFORCE_HTTPS === 'true' || process.env.NODE_ENV === 'production') {
  app.use((req, res, next) => {
    const proto = req.headers['x-forwarded-proto'];
    if (proto && proto !== 'https') {
      return res.redirect(`https://${req.headers.host}${req.url}`);
    }
    next();
  });
}

// Conexión MySQL Railway
const sequelize = new Sequelize(
  process.env.MYSQL_DATABASE,
  process.env.MYSQL_USER,
  process.env.MYSQL_PASSWORD,
  {
    host: process.env.MYSQL_HOST,
    dialect: 'mysql',
    port: process.env.MYSQL_PORT || 3306,
    logging: false,
    pool: { max: 5, min: 0, acquire: 30000, idle: 10000 }
  }
);

// MODELOS
const Usuario = sequelize.define('Usuario', {
  id: { type: DataTypes.UUID, defaultValue: DataTypes.UUIDV4, primaryKey: true },
  name: DataTypes.STRING,
  email: { type: DataTypes.STRING, unique: true },
  password: DataTypes.STRING,
  userType: DataTypes.STRING,
  phone: DataTypes.STRING,
  rating: { type: DataTypes.FLOAT, defaultValue: 5.0 },
  createdAt: { type: DataTypes.DATE, defaultValue: DataTypes.NOW }
}, { tableName: 'usuarios', timestamps: false });

const Driver = sequelize.define('Driver', {
  id: { type: DataTypes.UUID, defaultValue: DataTypes.UUIDV4, primaryKey: true },
  userId: DataTypes.UUID,
  vehicleBrand: DataTypes.STRING,
  vehicleModel: DataTypes.STRING,
  vehicleColor: DataTypes.STRING,
  cc: DataTypes.STRING,
  plateNumber: DataTypes.STRING,
  hasHelmetDriver: DataTypes.BOOLEAN,
  hasHelmetPassenger: DataTypes.BOOLEAN,
  hasInsurance: DataTypes.BOOLEAN,
  insuranceType: DataTypes.STRING,
  drivingLicense: DataTypes.STRING,
  lastService: DataTypes.STRING,
  rating: { type: DataTypes.FLOAT, defaultValue: 5.0 },
  tripsCompleted: { type: DataTypes.INTEGER, defaultValue: 0 },
  isOnline: { type: DataTypes.BOOLEAN, defaultValue: false },
  isAvailable: { type: DataTypes.BOOLEAN, defaultValue: false },
  location: { type: DataTypes.JSON, defaultValue: { lat: 0, lng: 0 } },
  fareRate: { type: DataTypes.FLOAT, defaultValue: 200 },
  createdAt: { type: DataTypes.DATE, defaultValue: DataTypes.NOW }
}, { tableName: 'drivers', timestamps: false });

const Trip = sequelize.define('Trip', {
  id: { type: DataTypes.UUID, defaultValue: DataTypes.UUIDV4, primaryKey: true },
  userId: DataTypes.UUID,
  driverId: DataTypes.UUID,
  pickupLocation: DataTypes.JSON,
  dropoffLocation: DataTypes.JSON,
  pickupAddress: DataTypes.STRING,
  dropoffAddress: DataTypes.STRING,
  serviceType: DataTypes.STRING,
  routeType: DataTypes.STRING,
  status: DataTypes.STRING,
  distance: DataTypes.FLOAT,
  fare: DataTypes.FLOAT,
  paymentMethod: DataTypes.STRING,
  paymentStatus: DataTypes.STRING,
  currency: DataTypes.STRING,
  createdAt: { type: DataTypes.DATE, defaultValue: DataTypes.NOW },
  startTime: DataTypes.DATE,
  endTime: DataTypes.DATE,
  rated: { type: DataTypes.BOOLEAN, defaultValue: false },
  ratingValue: DataTypes.FLOAT,
  ratingComment: DataTypes.TEXT,
  driverLocation: DataTypes.JSON,
  driverSnapshot: DataTypes.JSON
}, { tableName: 'trips', timestamps: false });

const Rating = sequelize.define('Rating', {
  id: { type: DataTypes.UUID, defaultValue: DataTypes.UUIDV4, primaryKey: true },
  tripId: DataTypes.UUID,
  ratedUserId: DataTypes.UUID,
  rating: DataTypes.FLOAT,
  comment: DataTypes.TEXT,
  createdAt: { type: DataTypes.DATE, defaultValue: DataTypes.NOW }
}, { tableName: 'ratings', timestamps: false });

const FarePolicy = sequelize.define('FarePolicy', {
  id: { type: DataTypes.INTEGER, defaultValue: 1, primaryKey: true },
  baseFareRate: { type: DataTypes.FLOAT, defaultValue: 200 },
  adminModificationFee: { type: DataTypes.FLOAT, defaultValue: 150 },
  serviceMultipliers: { type: DataTypes.JSON, defaultValue: { mototaxi: 1, taxi: 1.2, remis: 1.3, local: 1.1, cortaDistancia: 1.5, largaDistancia: 3 } },
  modifications: { type: DataTypes.JSON, defaultValue: [] }
}, { tableName: 'fare_policies', timestamps: false });

Usuario.hasOne(Driver, { foreignKey: 'userId' });
Driver.belongsTo(Usuario, { foreignKey: 'userId' });

sequelize.sync().then(async () => {
  // Crear farePolicy inicial si no existe
  await FarePolicy.findOrCreate({ where: { id: 1 }, defaults: {} });
  console.log('DB sincronizada');
});

// Helpers
function formatCurrencyARS(amount) {
  return Number(amount.toFixed(2));
}

async function estimateDistance(pickupAddress, dropoffAddress, serviceType = 'mototaxi', routeType = 'local') {
  const policy = await FarePolicy.findByPk(1);
  const base = Math.max(1, Math.round((pickupAddress.length + dropoffAddress.length) / 15));
  const serviceFactor = policy.serviceMultipliers[serviceType] || 1;
  const routeFactor = policy.serviceMultipliers[routeType] || 1;
  return Math.max(1, Math.round(base * serviceFactor * routeFactor));
}

function calculateFare(distance, rate) {
  return formatCurrencyARS(Math.max(150, distance * rate));
}

async function isDriverBusy(driverId) {
  const trip = await Trip.findOne({ where: { driverId, status: { [Op.in]: ['accepted', 'ongoing'] } } });
  return!!trip;
}

async function getUserById(userId) {
  return await Usuario.findByPk(userId);
}

async function isFareOwner(user) {
  return user && user.email && user.email.toLowerCase() === OWNER_EMAIL.toLowerCase();
}

// Rutas de Autenticación
app.post('/api/auth/register', async (req, res) => {
  try {
    const { name, email, password, userType, phone, vehicleBrand, vehicleModel, vehicleColor, cc, plateNumber, hasHelmetDriver, hasHelmetPassenger, hasInsurance, insuranceType, drivingLicense, lastService } = req.body;

    if (!name ||!email ||!password ||!userType ||!phone) {
      return res.status(400).json({ error: 'Faltan campos requeridos' });
    }

    const existe = await Usuario.findOne({ where: { email } });
    if (existe) {
      return res.status(409).json({ error: 'El correo ya está registrado' });
    }

    if (userType === 'driver') {
      if (!vehicleBrand ||!vehicleModel ||!vehicleColor ||!cc ||!plateNumber ||!drivingLicense ||!lastService) {
        return res.status(400).json({ error: 'Faltan datos del vehículo o documentación requerida' });
      }
      const plateOk = /^[A-Za-z0-9]+$/.test(String(plateNumber));
      if (!plateOk) {
        return res.status(400).json({ error: 'Formato de patente inválido' });
      }
    }

    const hashedPassword = bcrypt.hashSync(password, 10);
    const user = await Usuario.create({ name, email, password: hashedPassword, userType, phone });

    let userResponse = { id: user.id, name: user.name, email: user.email, userType: user.userType, rating: user.rating };

    if (userType === 'driver') {
      const driver = await Driver.create({
        userId: user.id, vehicleBrand, vehicleModel, vehicleColor, cc, plateNumber,
        hasHelmetDriver: Boolean(hasHelmetDriver), hasHelmetPassenger: Boolean(hasHelmetPassenger),
        hasInsurance: Boolean(hasInsurance), insuranceType: hasInsurance? (insuranceType || '') : '',
        drivingLicense: drivingLicense || '', lastService: lastService || '', phone, fareRate: 200
      });

      userResponse.driverProfile = {
        driverId: driver.id, vehicleBrand: driver.vehicleBrand, vehicleModel: driver.vehicleModel,
        vehicleColor: driver.vehicleColor, cc: driver.cc, phone: driver.phone,
        isOnline: driver.isOnline, isAvailable: driver.isAvailable, fareRate: driver.fareRate,
        plateNumber: driver.plateNumber, drivingLicense: driver.drivingLicense, lastService: driver.lastService
      };
    }

    res.status(201).json({ message: 'Usuario registrado exitosamente', user: userResponse });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Error en el servidor' });
  }
});

app.post('/api/auth/login', async (req, res) => {
  try {
    const { email, password } = req.body;
    const user = await Usuario.findOne({ where: { email } });

    if (!user ||!bcrypt.compareSync(password, user.password)) {
      return res.status(401).json({ error: 'Email o contraseña incorrectos' });
    }

    const userResponse = { id: user.id, name: user.name, email: user.email, userType: user.userType, rating: user.rating };

    if (user.userType === 'driver') {
      const driver = await Driver.findOne({ where: { userId: user.id } });
      if (driver) {
        userResponse.driverProfile = {
          driverId: driver.id, vehicleBrand: driver.vehicleBrand, vehicleModel: driver.vehicleModel,
          vehicleColor: driver.vehicleColor, cc: driver.cc, plateNumber: driver.plateNumber,
          phone: driver.phone, isOnline: driver.isOnline, isAvailable: driver.isAvailable,
          fareRate: driver.fareRate, insuranceType: driver.insuranceType,
          drivingLicense: driver.drivingLicense, lastService: driver.lastService
        };
      }
    }

    res.json({ message: 'Login exitoso', user: userResponse });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Error en el servidor' });
  }
});

// Rutas de Conductores
app.post('/api/drivers/register', async (req, res) => {
  const { userId, vehicleBrand, vehicleModel, licenseNumber, phone } = req.body;
  const driver = await Driver.create({ userId, vehicleBrand, vehicleModel, drivingLicense: licenseNumber, phone });
  res.status(201).json({ message: 'Conductor registrado', driver });
});

app.get('/api/drivers/available', async (req, res) => {
  const availableDrivers = await Driver.findAll({ where: { isAvailable: true } });
  res.json(availableDrivers);
});

app.put('/api/drivers/:driverId/status', async (req, res) => {
  const { driverId } = req.params;
  const { isOnline } = req.body;
  const driver = await Driver.findByPk(driverId);
  if (driver) {
    const busy = await isDriverBusy(driverId);
    await driver.update({ isOnline: Boolean(isOnline), isAvailable: Boolean(isOnline) &&!busy });
    res.json({ message: 'Estado actualizado', driver });
  } else {
    res.status(404).json({ error: 'Conductor no encontrado' });
  }
});

app.put('/api/drivers/:driverId/tarifa', async (req, res) => {
  const { driverId } = req.params;
  const { fareRate, userId } = req.body;
  const requestor = await getUserById(userId);
  const driver = await Driver.findByPk(driverId);

  if (!driver) return res.status(404).json({ error: 'Conductor no encontrado' });
  if (!requestor ||!await isFareOwner(requestor)) {
    return res.status(403).json({ error: 'Solo el propietario puede modificar la tarifa' });
  }

  await driver.update({ fareRate: Number(fareRate) || driver.fareRate });
  res.json({ message: 'Tarifa actualizada', driver });
});

app.put('/api/drivers/:driverId/location', async (req, res) => {
  const { driverId } = req.params;
  const { lat, lng } = req.body;
  const driver = await Driver.findByPk(driverId);
  if (driver) {
    await driver.update({ location: { lat, lng } });
    await Trip.update({ driverLocation: { lat, lng } }, { where: { driverId, status: { [Op.in]: ['accepted', 'ongoing'] } } });
    res.json({ message: 'Ubicación actualizada', driver });
  } else {
    res.status(404).json({ error: 'Conductor no encontrado' });
  }
});

app.get('/api/drivers/:driverId/requests', async (req, res) => {
  const { driverId } = req.params;
  const driver = await Driver.findByPk(driverId);
  if (!driver) return res.status(404).json({ error: 'Conductor no encontrado' });
  if (!driver.isOnline) return res.json([]);
  const availableTrips = await Trip.findAll({ where: { status: 'requested' } });
  res.json(availableTrips);
});

app.get('/api/drivers/:driverId/trips', async (req, res) => {
  const { driverId } = req.params;
  const driverTrips = await Trip.findAll({ where: { driverId } });
  res.json(driverTrips);
});

app.get('/api/drivers/:driverId', async (req, res) => {
  const driver = await Driver.findByPk(req.params.driverId);
  driver? res.json(driver) : res.status(404).json({ error: 'Conductor no encontrado' });
});

app.get('/api/trips/:tripId', async (req, res) => {
  const trip = await Trip.findByPk(req.params.tripId);
  trip? res.json(trip) : res.status(404).json({ error: 'Viaje no encontrado' });
});

// Rutas de Viajes
app.post('/api/trips/request', async (req, res) => {
  const { userId, pickupLocation, dropoffLocation, pickupAddress, dropoffAddress, paymentMethod, serviceType, routeType } = req.body;
  const passenger = await getUserById(userId);
  if (!passenger) return res.status(404).json({ error: 'Pasajero no encontrado' });

  const policy = await FarePolicy.findByPk(1);
  const service = serviceType || 'mototaxi';
  const route = routeType || 'local';
  const distance = await estimateDistance(pickupAddress, dropoffAddress, service, route);
  const fare = calculateFare(distance, policy.baseFareRate);

  const trip = await Trip.create({
    userId, pickupLocation, dropoffLocation, pickupAddress, dropoffAddress,
    serviceType: service, routeType: route, status: 'requested', distance, fare,
    paymentMethod: paymentMethod || 'efectivo', paymentStatus: 'pending', currency: 'ARS'
  });

  res.status(201).json({ message: 'Viaje solicitado', trip });
});

app.put('/api/trips/:tripId/accept', async (req, res) => {
  const { tripId } = req.params;
  const { driverId } = req.body;

  const trip = await Trip.findByPk(tripId);
  const driver = await Driver.findByPk(driverId);

  if (!trip) return res.status(404).json({ error: 'Viaje no encontrado' });
  if (!driver) return res.status(404).json({ error: 'Conductor no encontrado' });
  if (!driver.isOnline) return res.status(400).json({ error: 'Conductor offline' });
  if (trip.status!== 'requested') return res.status(400).json({ error: 'Viaje no disponible' });

  const policy = await FarePolicy.findByPk(1);
  const userOfDriver = await Usuario.findByPk(driver.userId);

  await trip.update({
    driverId, status: 'accepted',
    fare: calculateFare(trip.distance || 1, policy.baseFareRate),
    driverLocation: driver.location,
    driverSnapshot: {
      name: userOfDriver? userOfDriver.name : 'Conductor',
      vehicleBrand: driver.vehicleBrand,
      vehicleModel: driver.vehicleModel,
      vehicleColor: driver.vehicleColor,
      cc: driver.cc,
      hasPlate: Boolean(driver.plateNumber),
      hasHelmetDriver: driver.hasHelmetDriver,
      hasHelmetPassenger: driver.hasHelmetPassenger,
      hasInsurance: driver.hasInsurance,
      insuranceType: driver.hasInsurance? driver.insuranceType : '',
      drivingLicense: driver.drivingLicense,
      lastService: driver.lastService
    }
  });

  await driver.update({ isAvailable: false });
  res.json({ message: 'Viaje aceptado', trip });
});

app.put('/api/trips/:tripId/start', async (req, res) => {
  const trip = await Trip.findByPk(req.params.tripId);
  if (trip) {
    await trip.update({ status: 'ongoing', startTime: new Date() });
    const driver = await Driver.findByPk(trip.driverId);
    if (driver) {
      await driver.update({ isAvailable: false });
      await trip.update({ driverLocation: driver.location });
    }
    res.json({ message: 'Viaje iniciado', trip });
  } else {
    res.status(404).json({ error: 'Viaje no encontrado' });
  }
});

app.put('/api/trips/:tripId/complete', async (req, res) => {
  const trip = await Trip.findByPk(req.params.tripId);
  if (trip) {
    await trip.update({ status: 'completed', endTime: new Date() });
    const driver = await Driver.findByPk(trip.driverId);
    if (driver) {
      await driver.update({
        tripsCompleted: driver.tripsCompleted + 1,
        isAvailable: driver.isOnline &&!(await isDriverBusy(driver.id))
      });
    }
    res.json({ message: 'Viaje completado', trip });
  } else {
    res.status(404).json({ error: 'Viaje no encontrado' });
  }
});

app.get('/api/trips/user/:userId', async (req, res) => {
  const userTrips = await Trip.findAll({ where: { userId: req.params.userId } });
  res.json(userTrips);
});

// Rutas de Calificaciones
app.post('/api/ratings', async (req, res) => {
  const { tripId, ratedUserId, rating, comment } = req.body;
  const trip = await Trip.findByPk(tripId);
  if (!trip) return res.status(404).json({ error: 'Viaje no encontrado' });

  const ratingObj = await Rating.create({ tripId, ratedUserId, rating, comment });
  await trip.update({ rated: true, ratingValue: rating, ratingComment: comment });

  const userRatings = await Rating.findAll({ where: { ratedUserId } });
  const avg = userRatings.reduce((sum, r) => sum + r.rating, 0) / userRatings.length;
  await Usuario.update({ rating: Number(avg.toFixed(1)) }, { where: { id: ratedUserId } });

  res.status(201).json({ message: 'Calificación registrada', rating: ratingObj });
});

app.get('/api/ratings/:userId', async (req, res) => {
  const userRatings = await Rating.findAll({ where: { ratedUserId: req.params.userId } });
  res.json(userRatings);
});

// Admin
app.get('/api/admin/stats', async (req, res) => {
  const totalPassengers = await Usuario.count({ where: { userType: 'passenger' } });
  const totalDrivers = await Driver.count();
  const totalAdmins = await Usuario.count({ where: { userType: 'admin' } });
  const totalTrips = await Trip.count();
  const completedTrips = await Trip.count({ where: { status: 'completed' } });
  const completed = await Trip.findAll({ where: { status: 'completed' } });
  const totalRevenue = completed.reduce((sum, t) => sum + (t.fare || 0), 0);
  const drivers = await Driver.findAll();
  const averageDriverRating = drivers.length? Number((drivers.reduce((sum, d) => sum + (d.rating || 0), 0) / drivers.length).toFixed(1)) : 0;
  const passengers = await Usuario.findAll({ where: { userType: 'passenger' } });
  const averagePassengerRating = passengers.length? Number((passengers.reduce((sum, u) => sum + (u.rating || 0), 0) / passengers.length).toFixed(1)) : 0;
  const policy = await FarePolicy.findByPk(1);
  const recentTrips = await Trip.findAll({ order: [['createdAt', 'DESC']], limit: 6 });

  res.json({ totalPassengers, totalDrivers, totalAdmins, totalTrips, completedTrips, totalRevenue, averageDriverRating, averagePassengerRating, farePolicy: policy, recentTrips });
});

app.get('/api/fare-policy', async (req, res) => {
  const policy = await FarePolicy.findByPk(1);
  res.json(policy);
});

app.put('/api/fare-policy', async (req, res) => {
  const { userId, baseFareRate, adminPaidFee } = req.body;
  const requestor = await getUserById(userId);
  const policy = await FarePolicy.findByPk(1);

  if (!requestor) return res.status(404).json({ error: 'Usuario no encontrado' });

  if (await isFareOwner(requestor)) {
    await policy.update({
      baseFareRate: typeof baseFareRate === 'number'? baseFareRate : policy.baseFareRate,
      adminModificationFee: typeof req.body.adminModificationFee === 'number'? req.body.adminModificationFee : policy.adminModificationFee
    });
    return res.json({ message: 'Tarifa actualizada por propietario', farePolicy: policy });
  }

  if (requestor.userType === 'admin') {
    if (!adminPaidFee) {
      return res.status(403).json({ error: 'Admins deben pagar adicional' });
    }
    const oldRate = policy.baseFareRate;
    await policy.update({ baseFareRate: typeof baseFareRate === 'number'? baseFareRate : policy.baseFareRate });
    const mods = [...policy.modifications, {
      id: uuidv4(), adminId: requestor.id, adminEmail: requestor.email,
      oldRate, newRate: policy.baseFareRate, feeCharged: policy.adminModificationFee, createdAt: new Date()
    }];
    await policy.update({ modifications: mods });
    return res.json({ message: 'Tarifa modificada por admin', farePolicy: policy });
  }

  res.status(403).json({ error: 'Sin permiso' });
});

app.get('/api/admin/fare-modifications', async (req, res) => {
  const policy = await FarePolicy.findByPk(1);
  res.json(policy.modifications);
});

app.get('/api/admin/users', async (req, res) => {
  const summary = await Usuario.findAll({ attributes: ['id', 'name', 'email', 'userType', 'rating', 'createdAt'] });
  res.json(summary);
});

app.get('/api/admin/drivers', async (req, res) => {
  const summary = await Driver.findAll({ attributes: ['id', 'userId', 'vehicleBrand', 'vehicleModel', 'isOnline', 'fareRate', 'tripsCompleted', 'rating'] });
  res.json(summary);
});

// Health
app.get('/api/health', async (req, res) => {
  const users = await Usuario.count();
  const drivers = await Driver.count();
  const trips = await Trip.count();
  res.json({ status: 'OK', message: 'Servidor MotoTaxi funcionando', users, drivers, trips });
});

// Servir React
app.use(express.static(path.join(__dirname, '../frontend/build')));
app.get('*', (req, res) => {
  res.sendFile(path.join(__dirname, '../frontend/build/index.html'));
});

app.listen(PORT, '0.0.0.0', () => {
  console.log(`🏍️ Servidor MotoTaxi en puerto ${PORT}`);
});