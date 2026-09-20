import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:lumo/api/api_error.dart';
import 'package:lumo/api/idempotency_store.dart';
import 'package:lumo/core/env/app_config.dart';
import 'package:lumo/core/session/session_store.dart';
import 'package:uuid/uuid.dart';

class LumoApiClient {
  LumoApiClient({
    required this.config,
    required this.session,
    http.Client? httpClient,
    IdempotencyStore? idempotencyStore,
  })  : _http = httpClient ?? http.Client(),
        idempotency = idempotencyStore ?? IdempotencyStore();

  final AppConfig config;
  final SessionStore session;
  final IdempotencyStore idempotency;
  final http.Client _http;
  final _uuid = const Uuid();

  Uri _uri(String path) => Uri.parse('${config.apiBaseUrl}$path');

  Future<Map<String, dynamic>> get(String path) {
    return _send('GET', path);
  }

  Future<Map<String, dynamic>> post(
    String path, {
    Map<String, dynamic>? body,
    required String operation,
  }) {
    return _send('POST', path, body: body, operation: operation);
  }

  Future<Map<String, dynamic>> _send(
    String method,
    String path, {
    Map<String, dynamic>? body,
    String? operation,
  }) async {
    final headers = <String, String>{
      'Accept': 'application/json',
      'Content-Type': 'application/json',
      'X-Correlation-ID': _uuid.v4(),
    };
    final token = session.accessToken;
    if (token != null) {
      headers['Authorization'] = 'Bearer $token';
    }
    if (method != 'GET') {
      final op = operation ?? path;
      headers['Idempotency-Key'] = idempotency.keyFor(op);
    }
    final uri = _uri(path);
    late http.Response response;
    if (method == 'GET') {
      response = await _http.get(uri, headers: headers);
    } else {
      response = await _http.post(uri, headers: headers, body: jsonEncode(body ?? {}));
    }
    final decoded = response.body.isEmpty ? <String, dynamic>{} : jsonDecode(response.body);
    if (decoded is Map<String, dynamic> && decoded['error'] != null) {
      throw ApiError.fromEnvelope(decoded);
    }
    if (response.statusCode >= 400) {
      throw ApiError(
        code: 'INTERNAL_ERROR',
        message: 'Request failed',
        retryable: response.statusCode >= 500,
        correlationId: headers['X-Correlation-ID']!,
      );
    }
    return decoded as Map<String, dynamic>;
  }
}
