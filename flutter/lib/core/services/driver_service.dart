import 'package:dio/dio.dart';
import '../api/api_client.dart';
import '../api/api_error.dart';
import '../models/driver.dart';
import '../models/review.dart';

class DriverService {
  final _api = ApiClient.instance;

  Map<String, dynamic> _extractData(Response response) {
    final body = response.data;
    if (body['success'] == true) return body['data'];
    throw ApiError.fromResponse(body, statusCode: response.statusCode);
  }

  /// POST /api/v1/drivers/location
  Future<void> updateLocation({required double lat, required double lng}) async {
    await _api.dio.post('/api/v1/drivers/location', data: {
      'lat': lat,
      'lng': lng,
    });
  }

  /// POST /api/v1/drivers/online
  Future<bool> setOnline({required bool isOnline}) async {
    final response = await _api.dio.post('/api/v1/drivers/online', data: {
      'is_online': isOnline,
    });
    final data = _extractData(response);
    return data['is_online'] ?? false;
  }

  /// GET /api/v1/drivers/nearby
  Future<List<DriverNearby>> getNearbyDrivers({
    required double lat,
    required double lng,
    double radius = 10,
    String? vehicleType,
  }) async {
    final response = await _api.dio.get(
      '/api/v1/drivers/nearby',
      queryParameters: {
        'lat': lat,
        'lng': lng,
        'radius': radius,
        if (vehicleType != null) 'vehicle_type': vehicleType,
      },
    );
    final data = _extractData(response);
    final items = data['items'] as List? ?? [];
    return items.map((j) => DriverNearby.fromJson(j)).toList();
  }

  /// GET /api/v1/driver/accepted-payments
  Future<List<String>> getAcceptedPayments() async {
    final response = await _api.dio.get('/api/v1/driver/accepted-payments');
    final data = _extractData(response);
    return (data['accepted_payments'] as List?)
            ?.map((e) => e.toString())
            .toList() ??
        [];
  }

  /// PUT /api/v1/driver/accepted-payments
  Future<void> updateAcceptedPayments(List<String> payments) async {
    await _api.dio.put('/api/v1/driver/accepted-payments', data: {
      'accepted_payments': payments,
    });
  }

  /// POST /api/v1/driver/qr
  Future<void> uploadQr({required String base64Image}) async {
    await _api.dio.post('/api/v1/driver/qr', data: {'image': base64Image});
  }

  /// GET /api/v1/driver/payment-methods
  Future<List<DriverPaymentMethod>> getPaymentMethods() async {
    final response = await _api.dio.get('/api/v1/driver/payment-methods');
    final data = _extractData(response);
    final items = data['items'] as List? ?? [];
    return items.map((j) => DriverPaymentMethod.fromJson(j)).toList();
  }

  /// POST /api/v1/driver/payment-methods
  Future<DriverPaymentMethod> addPaymentMethod({
    required String type,
    Map<String, dynamic>? details,
  }) async {
    final response = await _api.dio.post('/api/v1/driver/payment-methods', data: {
      'type': type,
      if (details != null) 'details': details,
    });
    final data = _extractData(response);
    return DriverPaymentMethod.fromJson(data);
  }

  /// DELETE /api/v1/driver/payment-methods/{id}
  Future<void> deletePaymentMethod(int id) async {
    await _api.dio.delete('/api/v1/driver/payment-methods/$id');
  }

  /// GET /api/v1/geo/geocode
  Future<Map<String, dynamic>> geocode(String query) async {
    final response = await _api.dio.get(
      '/api/v1/geo/geocode',
      queryParameters: {'q': query},
    );
    final data = _extractData(response);
    return data;
  }

  /// GET /api/v1/users/{userId}/reviews
  Future<List<Review>> getUserReviews(int userId, {String? role}) async {
    final response = await _api.dio.get(
      '/api/v1/users/$userId/reviews',
      queryParameters: {if (role != null) 'role': role},
    );
    final data = _extractData(response);
    final items = data['items'] as List? ?? [];
    return items.map((j) => Review.fromJson(j)).toList();
  }
}
