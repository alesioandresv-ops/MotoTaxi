class Trip {
  final int id;
  final String status;
  final String vehicleType;
  final String? pickupAddress;
  final String? dropoffAddress;
  final double? pickupLat;
  final double? pickupLng;
  final double? dropoffLat;
  final double? dropoffLng;
  final double? fare;
  final double? distanceKm;
  final String? paymentMethod;
  final String? paymentStatus;
  final String? paymentMethodCollected;
  final DateTime? createdAt;
  final DateTime? completedAt;

  Trip({
    required this.id,
    required this.status,
    required this.vehicleType,
    this.pickupAddress,
    this.dropoffAddress,
    this.pickupLat,
    this.pickupLng,
    this.dropoffLat,
    this.dropoffLng,
    this.fare,
    this.distanceKm,
    this.paymentMethod,
    this.paymentStatus,
    this.paymentMethodCollected,
    this.createdAt,
    this.completedAt,
  });

  factory Trip.fromJson(Map<String, dynamic> json) {
    return Trip(
      id: json['id'] ?? 0,
      status: json['status'] ?? '',
      vehicleType: json['vehicle_type'] ?? 'moto',
      pickupAddress: json['pickup_address'],
      dropoffAddress: json['dropoff_address'],
      pickupLat: _toDouble(json['pickup_lat']),
      pickupLng: _toDouble(json['pickup_lng']),
      dropoffLat: _toDouble(json['dropoff_lat']),
      dropoffLng: _toDouble(json['dropoff_lng']),
      fare: _toDouble(json['fare']),
      distanceKm: _toDouble(json['distance_km']),
      paymentMethod: json['payment_method'],
      paymentStatus: json['payment_status'],
      paymentMethodCollected: json['payment_method_collected'],
      createdAt: json['created_at'] != null
          ? DateTime.tryParse(json['created_at'])
          : null,
      completedAt: json['completed_at'] != null
          ? DateTime.tryParse(json['completed_at'])
          : null,
    );
  }

  static double? _toDouble(dynamic v) {
    if (v == null) return null;
    if (v is double) return v;
    if (v is int) return v.toDouble();
    if (v is String) return double.tryParse(v);
    return null;
  }

  bool get isActive =>
      status == 'requested' || status == 'accepted' || status == 'ongoing';
  bool get isCompleted => status == 'completed';
  bool get isCancelled => status == 'cancelled';
  bool get canBeCancelled => status != 'completed' && status != 'cancelled';
}

class TripStatusUpdate {
  final int id;
  final String status;
  final double? driverLat;
  final double? driverLng;
  final double? fare;
  final String? paymentStatus;
  final String? paymentMethodCollected;
  final DriverInfo? driver;

  TripStatusUpdate({
    required this.id,
    required this.status,
    this.driverLat,
    this.driverLng,
    this.fare,
    this.paymentStatus,
    this.paymentMethodCollected,
    this.driver,
  });

  factory TripStatusUpdate.fromJson(Map<String, dynamic> json) {
    return TripStatusUpdate(
      id: json['id'] ?? 0,
      status: json['status'] ?? '',
      driverLat: _toDouble(json['driver']?['lat']),
      driverLng: _toDouble(json['driver']?['lng']),
      fare: _toDouble(json['fare']),
      paymentStatus: json['payment_status'],
      paymentMethodCollected: json['payment_method_collected'],
      driver: json['driver'] != null ? DriverInfo.fromJson(json['driver']) : null,
    );
  }

  static double? _toDouble(dynamic v) {
    if (v == null) return null;
    if (v is double) return v;
    if (v is int) return v.toDouble();
    if (v is String) return double.tryParse(v);
    return null;
  }
}

class DriverInfo {
  final int id;
  final String name;
  final String? phone;
  final String? profilePicture;
  final double ratingAvg;
  final int ratingCount;
  final double? lat;
  final double? lng;
  final VehicleInfo? vehicleInfo;

  DriverInfo({
    required this.id,
    required this.name,
    this.phone,
    this.profilePicture,
    this.ratingAvg = 0,
    this.ratingCount = 0,
    this.lat,
    this.lng,
    this.vehicleInfo,
  });

  factory DriverInfo.fromJson(Map<String, dynamic> json) {
    return DriverInfo(
      id: json['id'] ?? 0,
      name: json['name'] ?? '',
      phone: json['phone'],
      profilePicture: json['profile_picture'],
      ratingAvg: (json['rating_avg'] ?? 0).toDouble(),
      ratingCount: json['rating_count'] ?? 0,
      lat: _toDouble(json['lat']),
      lng: _toDouble(json['lng']),
      vehicleInfo: json['vehicle_info'] != null
          ? VehicleInfo.fromJson(json['vehicle_info'])
          : null,
    );
  }

  static double? _toDouble(dynamic v) {
    if (v == null) return null;
    if (v is double) return v;
    if (v is int) return v.toDouble();
    if (v is String) return double.tryParse(v);
    return null;
  }
}

class VehicleInfo {
  final String? type;
  final String? placa;
  final String? marca;
  final String? modelo;

  VehicleInfo({this.type, this.placa, this.marca, this.modelo});

  factory VehicleInfo.fromJson(Map<String, dynamic> json) {
    return VehicleInfo(
      type: json['type'],
      placa: json['placa'],
      marca: json['marca'],
      modelo: json['modelo'],
    );
  }
}
