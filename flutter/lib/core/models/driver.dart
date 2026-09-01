class DriverNearby {
  final int id;
  final String name;
  final String? phone;
  final String? profilePicture;
  final double? lat;
  final double? lng;
  final double? distanceKm;
  final double? ratingAvg;
  final int? ratingCount;
  final String? vehicleType;

  DriverNearby({
    required this.id,
    required this.name,
    this.phone,
    this.profilePicture,
    this.lat,
    this.lng,
    this.distanceKm,
    this.ratingAvg,
    this.ratingCount,
    this.vehicleType,
  });

  factory DriverNearby.fromJson(Map<String, dynamic> json) {
    return DriverNearby(
      id: json['id'] ?? 0,
      name: json['name'] ?? '',
      phone: json['phone'],
      profilePicture: json['profile_picture'],
      lat: _toDouble(json['lat']),
      lng: _toDouble(json['lng']),
      distanceKm: _toDouble(json['distance_km']),
      ratingAvg: _toDouble(json['rating_avg']),
      ratingCount: json['rating_count'],
      vehicleType: json['vehicle_type'],
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
