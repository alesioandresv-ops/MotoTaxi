import 'package:dio/dio.dart';
import '../api/api_client.dart';
import '../api/api_error.dart';
import '../models/trip.dart';

class TripService {
  final _api = ApiClient.instance;

  Map<String, dynamic> _extractData(Response response) {
    final body = response.data;
    if (body['success'] == true) return body['data'];
    throw ApiError.fromResponse(body, statusCode: response.statusCode);
  }

  /// POST /api/v1/trips
  Future<Map<String, dynamic>> createTrip({
    required String pickupAddress,
    required String dropoffAddress,
    required String vehicleType,
    required String paymentMethod,
    required String idempotencyKey,
    double? pickupLat,
    double? pickupLng,
    double? dropoffLat,
    double? dropoffLng,
    String? companyCode,
  }) async {
    final response = await _api.dio.post(
      '/api/v1/trips',
      data: {
        'pickup_address': pickupAddress,
        'dropoff_address': dropoffAddress,
        'vehicle_type': vehicleType,
        'payment_method': paymentMethod,
        'pickup_lat': pickupLat,
        'pickup_lng': pickupLng,
        'dropoff_lat': dropoffLat,
        'dropoff_lng': dropoffLng,
        if (companyCode != null) 'company_code': companyCode,
      },
      options: Options(
        headers: {'Idempotency-Key': idempotencyKey},
      ),
    );
    return _extractData(response);
  }

  /// GET /api/v1/trips/{id}
  Future<Trip> getTrip(int tripId) async {
    final response = await _api.dio.get('/api/v1/trips/$tripId');
    final data = _extractData(response);
    return Trip.fromJson(data);
  }

  /// GET /api/v1/trips?role=&status=&page=&limit=
  Future<List<Trip>> listTrips({
    String? role,
    String? status,
    int page = 1,
    int limit = 20,
  }) async {
    final response = await _api.dio.get('/api/v1/trips', queryParameters: {
      if (role != null) 'role': role,
      if (status != null) 'status': status,
      'page': page,
      'limit': limit,
    });
    final data = _extractData(response);
    final items = data['items'] as List? ?? [];
    return items.map((j) => Trip.fromJson(j)).toList();
  }

  /// GET /api/v1/trips/{id}/status (polling)
  Future<TripStatusUpdate> getTripStatus(int tripId) async {
    final response = await _api.dio.get('/api/v1/trips/$tripId/status');
    final data = _extractData(response);
    return TripStatusUpdate.fromJson(data);
  }

  /// GET /api/v1/trips/available
  Future<List<Trip>> getAvailableTrips({
    required double lat,
    required double lng,
    double radius = 10,
    String? vehicleType,
  }) async {
    final response = await _api.dio.get(
      '/api/v1/trips/available',
      queryParameters: {
        'lat': lat,
        'lng': lng,
        'radius': radius,
        if (vehicleType != null) 'vehicle_type': vehicleType,
      },
    );
    final data = _extractData(response);
    final items = data['items'] as List? ?? [];
    return items.map((j) => Trip.fromJson(j)).toList();
  }

  /// POST /api/v1/trips/{id}/accept
  Future<void> acceptTrip(int tripId) async {
    await _api.dio.post('/api/v1/trips/$tripId/accept');
  }

  /// POST /api/v1/trips/{id}/start
  Future<void> startTrip(int tripId) async {
    await _api.dio.post('/api/v1/trips/$tripId/start');
  }

  /// POST /api/v1/trips/{id}/complete
  Future<void> completeTrip(int tripId, {String? paymentMethod}) async {
    await _api.dio.post('/api/v1/trips/$tripId/complete', data: {
      if (paymentMethod != null) 'method': paymentMethod,
    });
  }

  /// POST /api/v1/trips/{id}/cancel
  Future<void> cancelTrip(int tripId, {String? reason}) async {
    await _api.dio.post('/api/v1/trips/$tripId/cancel', data: {
      if (reason != null) 'reason': reason,
    });
  }

  /// POST /api/v1/trips/{id}/rate
  Future<void> rateTrip(int tripId, {required int rating, String? comment}) async {
    await _api.dio.post('/api/v1/trips/$tripId/rate', data: {
      'rating': rating,
      if (comment != null) 'comment': comment,
    });
  }

  /// GET /api/v1/trips/{id}/eta
  Future<Map<String, dynamic>?> getTripEta(int tripId) async {
    final response = await _api.dio.get('/api/v1/trips/$tripId/eta');
    final data = _extractData(response);
    if (data['eta_minutes'] == null) return null;
    return data;
  }
}
