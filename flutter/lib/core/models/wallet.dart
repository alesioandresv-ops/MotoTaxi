class Wallet {
  final double balance;
  final String currency;

  Wallet({required this.balance, required this.currency});

  factory Wallet.fromJson(Map<String, dynamic> json) {
    return Wallet(
      balance: (json['balance'] ?? 0).toDouble(),
      currency: json['currency'] ?? 'ARS',
    );
  }
}

class TopUpRequest {
  final int id;
  final double amount;
  final String status;
  final String? paymentMethod;
  final String? initPoint;
  final String? preferenceId;
  final DateTime? createdAt;

  TopUpRequest({
    required this.id,
    required this.amount,
    required this.status,
    this.paymentMethod,
    this.initPoint,
    this.preferenceId,
    this.createdAt,
  });

  factory TopUpRequest.fromJson(Map<String, dynamic> json) {
    return TopUpRequest(
      id: json['id'] ?? 0,
      amount: (json['amount'] ?? 0).toDouble(),
      status: json['status'] ?? 'pending',
      paymentMethod: json['payment_method'],
      initPoint: json['init_point'],
      preferenceId: json['preference_id'],
      createdAt: json['created_at'] != null
          ? DateTime.tryParse(json['created_at'])
          : null,
    );
  }
}

class WalletTransaction {
  final int id;
  final String type;
  final double amount;
  final double? balanceAfter;
  final String? description;
  final DateTime? createdAt;

  WalletTransaction({
    required this.id,
    required this.type,
    required this.amount,
    this.balanceAfter,
    this.description,
    this.createdAt,
  });

  factory WalletTransaction.fromJson(Map<String, dynamic> json) {
    return WalletTransaction(
      id: json['id'] ?? 0,
      type: json['type'] ?? '',
      amount: (json['amount'] ?? 0).toDouble(),
      balanceAfter: json['balance_after']?.toDouble(),
      description: json['description'],
      createdAt: json['created_at'] != null
          ? DateTime.tryParse(json['created_at'])
          : null,
    );
  }
}

class FavoriteAddress {
  final int id;
  final String label;
  final String address;
  final double? lat;
  final double? lng;
  final int usageCount;

  FavoriteAddress({
    required this.id,
    required this.label,
    required this.address,
    this.lat,
    this.lng,
    this.usageCount = 0,
  });

  factory FavoriteAddress.fromJson(Map<String, dynamic> json) {
    return FavoriteAddress(
      id: json['id'] ?? 0,
      label: json['label'] ?? '',
      address: json['address'] ?? '',
      lat: json['lat']?.toDouble(),
      lng: json['lng']?.toDouble(),
      usageCount: json['usage_count'] ?? 0,
    );
  }
}
