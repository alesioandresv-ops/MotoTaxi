class Review {
  final int id;
  final int tripId;
  final int raterId;
  final String? raterName;
  final int rateeId;
  final String? rateeName;
  final int rating;
  final String? comment;
  final String role;
  final DateTime? createdAt;

  Review({
    required this.id,
    required this.tripId,
    required this.raterId,
    this.raterName,
    required this.rateeId,
    this.rateeName,
    required this.rating,
    this.comment,
    required this.role,
    this.createdAt,
  });

  factory Review.fromJson(Map<String, dynamic> json) {
    return Review(
      id: json['id'] ?? 0,
      tripId: json['trip_id'] ?? 0,
      raterId: json['rater_id'] ?? 0,
      raterName: json['rater_name'],
      rateeId: json['ratee_id'] ?? 0,
      rateeName: json['ratee_name'],
      rating: json['rating'] ?? 0,
      comment: json['comment'],
      role: json['role'] ?? '',
      createdAt: json['created_at'] != null
          ? DateTime.tryParse(json['created_at'])
          : null,
    );
  }
}

class DriverPaymentMethod {
  final int id;
  final String type;
  final Map<String, dynamic>? details;
  final DateTime? createdAt;

  DriverPaymentMethod({
    required this.id,
    required this.type,
    this.details,
    this.createdAt,
  });

  factory DriverPaymentMethod.fromJson(Map<String, dynamic> json) {
    return DriverPaymentMethod(
      id: json['id'] ?? 0,
      type: json['type'] ?? '',
      details: json['details'],
      createdAt: json['created_at'] != null
          ? DateTime.tryParse(json['created_at'])
          : null,
    );
  }
}
