class ApiError {
  final String code;
  final String message;
  final int? statusCode;

  ApiError({required this.code, required this.message, this.statusCode});

  factory ApiError.fromResponse(Map<String, dynamic> body, {int? statusCode}) {
    final error = body['error'] ?? {};
    return ApiError(
      code: error['code'] ?? 'UNKNOWN_ERROR',
      message: error['message'] ?? 'Ocurrió un error inesperado',
      statusCode: statusCode,
    );
  }

  bool get isTokenExpired => code == 'TOKEN_EXPIRED';
  bool get isNotVerified => code == 'NOT_VERIFIED';
  bool get isForbidden => code == 'FORBIDDEN';
  bool get isNotFound => code == 'NOT_FOUND';
  bool get isInsufficientBalance => code == 'INSUFFICIENT_BALANCE';
  bool get isDuplicateTrip => code == 'DUPLICATE_TRIP';
  bool get isActiveTripExists => code == 'ACTIVE_TRIP_EXISTS';
  bool get isTripNotAvailable => code == 'TRIP_NOT_AVAILABLE';
  bool get isInvalidTransition => code == 'INVALID_TRANSITION';
  bool get isLocationRequired => code == 'LOCATION_REQUIRED';
}
