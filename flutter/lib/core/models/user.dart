class User {
  final int id;
  final String name;
  final String email;
  final String? phone;
  final String role;
  final String activeMode;
  final String? profilePicture;
  final bool isVerified;
  final bool guidelinesAccepted;
  final DateTime? createdAt;

  User({
    required this.id,
    required this.name,
    required this.email,
    this.phone,
    required this.role,
    required this.activeMode,
    this.profilePicture,
    this.isVerified = false,
    this.guidelinesAccepted = false,
    this.createdAt,
  });

  factory User.fromJson(Map<String, dynamic> json) {
    return User(
      id: json['id'] ?? 0,
      name: json['name'] ?? '',
      email: json['email'] ?? '',
      phone: json['phone'],
      role: json['role'] ?? 'passenger',
      activeMode: json['active_mode'] ?? 'passenger',
      profilePicture: json['profile_picture'],
      isVerified: json['is_verified'] ?? false,
      guidelinesAccepted: json['guidelines_accepted'] ?? false,
      createdAt: json['created_at'] != null
          ? DateTime.tryParse(json['created_at'])
          : null,
    );
  }

  bool get isPassenger =>
      activeMode == 'passenger' || role == 'passenger';
  bool get isDriver => activeMode == 'driver' || role == 'driver';
  bool get isBoth => role == 'both';
}
