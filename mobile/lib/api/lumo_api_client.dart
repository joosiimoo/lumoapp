import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;
import 'package:lumo/api/api_error.dart';
import 'package:lumo/api/idempotency_store.dart';
import 'package:lumo/core/env/app_config.dart';
import 'package:lumo/core/session/session_store.dart';
import 'package:lumo/lumo/generative_ui/renderer.dart';
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
    String? idempotencyKey,
  }) {
    return _send('POST', path, body: body, operation: operation, idempotencyKey: idempotencyKey);
  }

  Future<Map<String, dynamic>> _send(
    String method,
    String path, {
    Map<String, dynamic>? body,
    String? operation,
    String? idempotencyKey,
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
      headers['Idempotency-Key'] = idempotencyKey ?? idempotency.keyFor(op);
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

  Future<LumoMessageResponse> postMessage(
    String message, {
    required String operation,
    required String conversationId,
    String? confirmationToken,
  }) async {
    final body = <String, dynamic>{
      'message': message,
      'conversation_id': conversationId,
    };
    if (confirmationToken != null) {
      body['client_context'] = {'confirmation_token': confirmationToken};
    }
    final decoded = await post(
      '/api/v1/lumo/messages',
      body: body,
      operation: operation,
    );
    return LumoMessageResponse.fromJson(decoded);
  }

  Future<LumoMessageResponse> postAction({
    required String actionId,
    String? optionId,
    required String contextToken,
    required String conversationId,
    required String idempotencyKey,
  }) async {
    final decoded = await post(
      '/api/v1/lumo/actions',
      operation: 'lumo.action.$idempotencyKey',
      idempotencyKey: idempotencyKey,
      body: {
        'action_id': actionId,
        'option_id': optionId,
        'context_token': contextToken,
        'conversation_id': conversationId,
        'idempotency_key': idempotencyKey,
      },
    );
    return LumoMessageResponse.fromJson(decoded);
  }

  Future<Map<String, dynamic>> getSession() {
    return get('/api/v1/session');
  }

  Future<Map<String, dynamic>> getCurrentNextBestAction() {
    return get('/api/v1/operational-days/current/next-best-action');
  }

  Future<SalesExportFile> downloadCurrentSalesExport(String format) {
    return downloadFile('/api/v1/operational-days/current/sales-export?format=$format');
  }

  Future<SalesExportFile> downloadFile(String path) async {
    final headers = <String, String>{
      'Accept': '*/*',
      'X-Correlation-ID': _uuid.v4(),
    };
    final token = session.accessToken;
    if (token != null) {
      headers['Authorization'] = 'Bearer $token';
    }
    final response = await _http.get(_uri(path), headers: headers);
    if (response.statusCode >= 400) {
      final decoded = response.body.isEmpty ? <String, dynamic>{} : jsonDecode(response.body);
      if (decoded is Map<String, dynamic> && decoded['error'] != null) {
        throw ApiError.fromEnvelope(decoded);
      }
      throw ApiError(
        code: 'INTERNAL_ERROR',
        message: 'Request failed',
        retryable: response.statusCode >= 500,
        correlationId: headers['X-Correlation-ID']!,
      );
    }
    final filename = _attachmentFilename(response.headers['content-disposition']);
    if (filename == null || filename.isEmpty) {
      throw ApiError(
        code: 'INTERNAL_ERROR',
        message: 'Export filename is missing',
        retryable: false,
        correlationId: headers['X-Correlation-ID']!,
      );
    }
    return SalesExportFile(
      bytes: response.bodyBytes,
      filename: filename,
      mimeType: response.headers['content-type'] ?? 'application/octet-stream',
    );
  }
}

class SalesExportFile {
  const SalesExportFile({
    required this.bytes,
    required this.filename,
    required this.mimeType,
  });

  final Uint8List bytes;
  final String filename;
  final String mimeType;
}

String? _attachmentFilename(String? disposition) {
  if (disposition == null) {
    return null;
  }
  final match = RegExp('filename="([^"]+)"').firstMatch(disposition);
  return match?.group(1);
}

class LumoMessageResponse {
  const LumoMessageResponse({
    required this.messageId,
    required this.status,
    required this.text,
    required this.ui,
    required this.correlationId,
  });

  final String messageId;
  final String status;
  final String text;
  final List<GenerativeUiContract> ui;
  final String correlationId;

  factory LumoMessageResponse.fromJson(Map<String, dynamic> json) {
    return LumoMessageResponse(
      messageId: '${json['message_id'] ?? ''}',
      status: '${json['status'] ?? ''}',
      text: '${json['text'] ?? ''}',
      ui: [
        for (final item in (json['ui'] as List? ?? []))
          GenerativeUiContract.fromJson(Map<String, dynamic>.from(item as Map)),
      ],
      correlationId: '${json['correlation_id'] ?? ''}',
    );
  }
}
