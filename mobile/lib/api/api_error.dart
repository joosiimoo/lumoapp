class ApiError {
  const ApiError({
    required this.code,
    required this.message,
    required this.retryable,
    required this.correlationId,
  });

  final String code;
  final String message;
  final bool retryable;
  final String correlationId;

  factory ApiError.fromEnvelope(Map<String, dynamic> json) {
    final error = json['error'] as Map<String, dynamic>;
    return ApiError(
      code: error['code'] as String,
      message: error['message'] as String,
      retryable: error['retryable'] as bool? ?? false,
      correlationId: error['correlation_id'] as String? ?? '',
    );
  }
}
