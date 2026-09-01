import 'package:dio/dio.dart';
import '../api/api_client.dart';
import '../api/api_error.dart';
import '../models/wallet.dart';

class WalletService {
  final _api = ApiClient.instance;

  Map<String, dynamic> _extractData(Response response) {
    final body = response.data;
    if (body['success'] == true) return body['data'];
    throw ApiError.fromResponse(body, statusCode: response.statusCode);
  }

  /// GET /api/v1/wallet
  Future<Wallet> getWallet() async {
    final response = await _api.dio.get('/api/v1/wallet');
    final data = _extractData(response);
    return Wallet.fromJson(data);
  }

  /// GET /api/v1/wallet/transactions
  Future<List<WalletTransaction>> getTransactions({
    String? type,
    int page = 1,
    int limit = 20,
  }) async {
    final response = await _api.dio.get(
      '/api/v1/wallet/transactions',
      queryParameters: {
        if (type != null) 'type': type,
        'page': page,
        'limit': limit,
      },
    );
    final data = _extractData(response);
    final items = data['items'] as List? ?? [];
    return items.map((j) => WalletTransaction.fromJson(j)).toList();
  }

  /// POST /api/v1/wallet/topups
  Future<TopUpRequest> createTopUp({
    required double amount,
    required String method,
  }) async {
    final response = await _api.dio.post('/api/v1/wallet/topups', data: {
      'amount': amount,
      'method': method,
    });
    final data = _extractData(response);
    return TopUpRequest.fromJson(data);
  }

  /// GET /api/v1/wallet/topups
  Future<List<TopUpRequest>> listTopUps({
    String? status,
    int page = 1,
    int limit = 20,
  }) async {
    final response = await _api.dio.get(
      '/api/v1/wallet/topups',
      queryParameters: {
        if (status != null) 'status': status,
        'page': page,
        'limit': limit,
      },
    );
    final data = _extractData(response);
    final items = data['items'] as List? ?? [];
    return items.map((j) => TopUpRequest.fromJson(j)).toList();
  }

  /// GET /api/v1/wallet/topups/{id}
  Future<TopUpRequest> getTopUp(int id) async {
    final response = await _api.dio.get('/api/v1/wallet/topups/$id');
    final data = _extractData(response);
    return TopUpRequest.fromJson(data);
  }

  /// GET /api/v1/favorites
  Future<List<FavoriteAddress>> getFavorites() async {
    final response = await _api.dio.get('/api/v1/favorites');
    final data = _extractData(response);
    final items = data['items'] as List? ?? data as List? ?? [];
    return items.map((j) => FavoriteAddress.fromJson(j)).toList();
  }
}
