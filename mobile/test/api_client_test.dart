import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:lumo/api/api_error.dart';
import 'package:lumo/api/idempotency_store.dart';
import 'package:lumo/api/lumo_api_client.dart';
import 'package:lumo/core/env/app_config.dart';
import 'package:lumo/core/session/session_store.dart';

void main() {
  test('error envelope is decoded', () {
    final error = ApiError.fromEnvelope({
      'error': {
        'code': 'VALIDATION_ERROR',
        'message': 'bad',
        'retryable': false,
        'correlation_id': 'abc',
      },
    });
    expect(error.code, 'VALIDATION_ERROR');
    expect(error.message, 'bad');
    expect(error.retryable, isFalse);
    expect(error.correlationId, 'abc');
  });

  test('mutation retry reuses the same idempotency key', () {
    final store = IdempotencyStore();
    final first = store.keyFor('platform.note.create');
    final retry = store.keyFor('platform.note.create');
    expect(retry, first);
  });

  test('postMessage always sends conversation_id', () async {
    String? body;
    final httpClient = MockClient((request) async {
      body = request.body;
      return http.Response(
        jsonEncode({
          'message_id': 'm1',
          'status': 'completed',
          'text': 'ok',
          'ui': [],
          'correlation_id': 'c1',
        }),
        200,
        headers: {'content-type': 'application/json'},
      );
    });
    final client = LumoApiClient(
      config: const AppConfig(env: 'test', apiBaseUrl: 'http://lumo.test'),
      session: SessionStore()..accessToken = 'tok',
      httpClient: httpClient,
    );
    await client.postMessage(
      '900gr zanahoria',
      operation: 'lumo.message.send.cid',
      conversationId: 'conv-required',
    );
    expect(jsonDecode(body!)['conversation_id'], 'conv-required');
    expect(jsonDecode(body!)['message'], '900gr zanahoria');
  });

  test('postMessage uses typed path and reuses idempotency key on retry', () async {
    final keys = <String?>[];
    final httpClient = MockClient((request) async {
      keys.add(request.headers['idempotency-key']);
      return http.Response(
        jsonEncode({
          'message_id': 'm1',
          'status': 'completed',
          'text': 'ok',
          'ui': [],
          'correlation_id': 'c1',
        }),
        200,
        headers: {'content-type': 'application/json'},
      );
    });
    final client = LumoApiClient(
      config: const AppConfig(env: 'test', apiBaseUrl: 'http://lumo.test'),
      session: SessionStore()..accessToken = 'tok',
      httpClient: httpClient,
    );
    final first = await client.postMessage(
      '900gr zanahoria',
      operation: 'lumo.message.send.1',
      conversationId: 'conv-client-1',
    );
    final replay = await client.postMessage(
      '900gr zanahoria',
      operation: 'lumo.message.send.1',
      conversationId: 'conv-client-1',
    );
    expect(first.text, 'ok');
    expect(replay.text, 'ok');
    expect(keys, hasLength(2));
    expect(keys[0], isNotEmpty);
    expect(keys[1], keys[0]);
  });

  test('postMessage echoes a confirmation token and never puts it in the message', () async {
    String? body;
    final httpClient = MockClient((request) async {
      body = request.body;
      return http.Response(
        jsonEncode({
          'message_id': 'm-close',
          'status': 'completed',
          'text': 'ok',
          'ui': [],
          'correlation_id': 'c-close',
        }),
        200,
        headers: {'content-type': 'application/json'},
      );
    });
    final client = LumoApiClient(
      config: const AppConfig(env: 'test', apiBaseUrl: 'http://lumo.test'),
      session: SessionStore()..accessToken = 'tok',
      httpClient: httpClient,
    );
    await client.postMessage(
      'confirmar cierre',
      operation: 'lumo.message.send.1',
      conversationId: 'conv-close',
      confirmationToken: 'header.payload.sig',
    );
    final decoded = jsonDecode(body!) as Map<String, dynamic>;
    expect(decoded['message'], 'confirmar cierre');
    expect(decoded['client_context'], {'confirmation_token': 'header.payload.sig'});
    expect(decoded['message'].toString().contains('header.payload.sig'), isFalse);
  });

  test('download returns server bytes and filename without an idempotency key', () async {
    final httpClient = MockClient((request) async {
      expect(request.method, 'GET');
      expect(request.headers['authorization'], 'Bearer tok');
      expect(request.headers['x-correlation-id'], isNotEmpty);
      expect(request.headers.containsKey('idempotency-key'), isFalse);
      return http.Response.bytes(
        [0xEF, 0xBB, 0xBF, 0x61],
        200,
        headers: {
          'content-type': 'text/csv; charset=utf-8',
          'content-disposition': 'attachment; filename="lumo-carrota-ventas-2026-09-23.csv"',
        },
      );
    });
    final client = LumoApiClient(
      config: const AppConfig(env: 'test', apiBaseUrl: 'http://lumo.test'),
      session: SessionStore()..accessToken = 'tok',
      httpClient: httpClient,
    );
    final file = await client.downloadCurrentSalesExport('csv');
    expect(file.filename, 'lumo-carrota-ventas-2026-09-23.csv');
    expect(file.mimeType, 'text/csv; charset=utf-8');
    expect(file.bytes, [0xEF, 0xBB, 0xBF, 0x61]);
  });

  test('xlsx download keeps the server filename and spreadsheet MIME type', () async {
    final httpClient = MockClient((request) async {
      return http.Response.bytes(
        [0x50, 0x4B],
        200,
        headers: {
          'content-type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
          'content-disposition': 'attachment; filename="lumo-carrota-ventas-2026-09-23.xlsx"',
        },
      );
    });
    final client = LumoApiClient(
      config: const AppConfig(env: 'test', apiBaseUrl: 'http://lumo.test'),
      session: SessionStore()..accessToken = 'tok',
      httpClient: httpClient,
    );
    final file = await client.downloadCurrentSalesExport('xlsx');
    expect(file.filename, 'lumo-carrota-ventas-2026-09-23.xlsx');
    expect(file.mimeType, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');
    expect(file.bytes, [0x50, 0x4B]);
  });
}
