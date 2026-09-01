import 'package:dio/dio.dart';
import '../api/api_client.dart';
import '../api/api_error.dart';
import '../models/user.dart';

class AuthService {
  final _api = ApiClient.instance;

  Map<String, dynamic> _extractData(Response response) {
    if (response.statusCode == 200 || response.statusCode == 201) {
      final body = response.data;
      if (body['success'] == true) return body['data'];
      throw ApiError.fromResponse(body, statusCode: response.statusCode);
    }
    throw ApiError(
      code: 'HTTP_${response.statusCode}',
      message: 'Error inesperado',
      statusCode: response.statusCode,
    );
  }

  /// POST /api/v1/auth/register
  Future<AuthResult> register({
    required String name,
    required String email,
    required String password,
    String? phone,
  }) async {
    final response = await _api.dio.post('/api/v1/auth/register', data: {
      'name': name,
      'email': email,
      'password': password,
      if (phone != null) 'phone': phone,
    });
    final data = _extractData(response);
    return AuthResult.fromMap(data);
  }

  /// POST /api/v1/auth/register/driver
  Future<AuthResult> registerDriver({
    required String name,
    required String email,
    required String password,
    required String phone,
    required String placa,
    required String motoMarca,
    required String motoModelo,
    String? motoColor,
    String? motoCilindrada,
    String? tipoSeguro,
    String? carnetConducir,
  }) async {
    final response =
        await _api.dio.post('/api/v1/auth/register/driver', data: {
      'name': name,
      'email': email,
      'password': password,
      'phone': phone,
      'placa': placa,
      'moto_marca': motoMarca,
      'moto_modelo': motoModelo,
      if (motoColor != null) 'moto_color': motoColor,
      if (motoCilindrada != null) 'moto_cilindrada': motoCilindrada,
      if (tipoSeguro != null) 'tipo_seguro': tipoSeguro,
      if (carnetConducir != null) 'carnet_conducir': carnetConducir,
    });
    final data = _extractData(response);
    return AuthResult.fromMap(data);
  }

  /// POST /api/v1/auth/login
  Future<AuthResult> login({
    required String email,
    required String password,
    String? mode,
  }) async {
    final response = await _api.dio.post('/api/v1/auth/login', data: {
      'email': email,
      'password': password,
      if (mode != null) 'mode': mode,
    });
    final data = _extractData(response);
    return AuthResult.fromMap(data);
  }

  /// POST /api/v1/auth/refresh
  Future<AuthResult> refresh({required String refreshToken}) async {
    final response = await _api.dio.post(
      '/api/v1/auth/refresh',
      data: {'refresh_token': refreshToken},
    );
    final data = _extractData(response);
    return AuthResult.fromMap(data);
  }

  /// POST /api/v1/auth/logout
  Future<void> logout({required String refreshToken}) async {
    try {
      await _api.dio.post(
        '/api/v1/auth/logout',
        data: {'refresh_token': refreshToken},
      );
    } catch (_) {}
  }

  /// GET /api/v1/auth/me
  Future<User> getMe() async {
    final response = await _api.dio.get('/api/v1/auth/me');
    final data = _extractData(response);
    return User.fromJson(data);
  }

  /// POST /api/v1/auth/verify-email
  Future<void> verifyEmail({required String code}) async {
    await _api.dio.post('/api/v1/auth/verify-email', data: {'code': code});
  }

  /// POST /api/v1/auth/switch-mode
  Future<AuthResult> switchMode({required String mode}) async {
    final response =
        await _api.dio.post('/api/v1/auth/switch-mode', data: {'mode': mode});
    final data = _extractData(response);
    return AuthResult.fromMap(data);
  }

  /// PUT /api/v1/auth/profile
  Future<User> updateProfile({String? name, String? phone}) async {
    final response = await _api.dio.put('/api/v1/auth/profile', data: {
      if (name != null) 'name': name,
      if (phone != null) 'phone': phone,
    });
    final data = _extractData(response);
    return User.fromJson(data);
  }

  /// POST /api/v1/auth/password
  Future<void> changePassword({
    required String currentPassword,
    required String newPassword,
  }) async {
    await _api.dio.post('/api/v1/auth/password', data: {
      'current_password': currentPassword,
      'new_password': newPassword,
    });
  }

  /// POST /api/v1/auth/profile/photo
  Future<String> uploadProfilePhoto({required String base64Image}) async {
    final response = await _api.dio.post(
      '/api/v1/auth/profile/photo',
      data: {'image': base64Image},
    );
    final data = _extractData(response);
    return data['profile_picture'] ?? '';
  }
}

class AuthResult {
  final String accessToken;
  final String refreshToken;
  final User user;

  AuthResult({
    required this.accessToken,
    required this.refreshToken,
    required this.user,
  });

  factory AuthResult.fromMap(Map<String, dynamic> data) {
    return AuthResult(
      accessToken: data['access_token'] ?? '',
      refreshToken: data['refresh_token'] ?? '',
      user: User.fromJson(data['user'] ?? {}),
    );
  }
}
