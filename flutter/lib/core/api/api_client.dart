import 'package:dio/dio.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class ApiClient {
  ApiClient._internal();
  static final ApiClient instance = ApiClient._internal();

  late final Dio dio;
  final _storage = const FlutterSecureStorage();

  String? _accessToken;
  String? _refreshToken;

  String? get accessToken => _accessToken;
  bool get isAuthenticated => _accessToken != null;

  void init({required String baseUrl}) {
    dio = Dio(BaseOptions(
      baseUrl: baseUrl,
      connectTimeout: const Duration(seconds: 15),
      receiveTimeout: const Duration(seconds: 15),
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      },
    ));

    dio.interceptors.add(InterceptorsWrapper(
      onRequest: (options, handler) {
        if (_accessToken != null) {
          options.headers['Authorization'] = 'Bearer $_accessToken';
        }
        return handler.next(options);
      },
      onError: (error, handler) async {
        if (error.response?.statusCode == 401 && _refreshToken != null) {
          final refreshed = await _tryRefreshToken();
          if (refreshed) {
            error.requestOptions.headers['Authorization'] =
                'Bearer $_accessToken';
            final response = await dio.fetch(error.requestOptions);
            return handler.resolve(response);
          }
        }
        return handler.next(error);
      },
    ));
  }

  Future<bool> _tryRefreshToken() async {
    try {
      final response = await dio.post(
        '/api/v1/auth/refresh',
        data: {'refresh_token': _refreshToken},
        options: Options(
          headers: {'Authorization': null},
        ),
      );

      if (response.statusCode == 200 && response.data['success'] == true) {
        final data = response.data['data'];
        _accessToken = data['access_token'];
        _refreshToken = data['refresh_token'];
        await _saveTokens();
        return true;
      }
    } catch (_) {
      await logout();
    }
    return false;
  }

  Future<void> saveAuth({
    required String accessToken,
    required String refreshToken,
  }) async {
    _accessToken = accessToken;
    _refreshToken = refreshToken;
    await _saveTokens();
  }

  Future<void> _saveTokens() async {
    if (_accessToken != null) {
      await _storage.write(key: 'access_token', value: _accessToken);
    }
    if (_refreshToken != null) {
      await _storage.write(key: 'refresh_token', value: _refreshToken);
    }
  }

  Future<void> loadTokens() async {
    _accessToken = await _storage.read(key: 'access_token');
    _refreshToken = await _storage.read(key: 'refresh_token');
  }

  Future<void> logout() async {
    if (_refreshToken != null) {
      try {
        await dio.post('/api/v1/auth/logout',
            data: {'refresh_token': _refreshToken});
      } catch (_) {}
    }
    _accessToken = null;
    _refreshToken = null;
    await _storage.deleteAll();
  }
}
