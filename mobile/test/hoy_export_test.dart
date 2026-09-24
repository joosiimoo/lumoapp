import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:lumo/api/lumo_api_client.dart';
import 'package:lumo/core/env/app_config.dart';
import 'package:lumo/core/session/session_store.dart';
import 'package:lumo/features/hoy/hoy_page.dart';
import 'package:share_plus/share_plus.dart';

void main() {
  testWidgets('Hoy downloads current export bytes and the server filename', (tester) async {
    final requests = <http.Request>[];
    SalesExportFile? shared;
    final httpClient = MockClient((request) async {
      requests.add(request);
      final format = request.url.queryParameters['format'];
      return http.Response.bytes(
        utf8.encode(format == 'csv' ? 'business_date\r\n' : 'xlsx-bytes'),
        200,
        headers: {
          'content-type': format == 'csv'
              ? 'text/csv; charset=utf-8'
              : 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
          'content-disposition': 'attachment; filename="lumo-nandu-hijos-ventas-2026-09-23.$format"',
        },
      );
    });
    await tester.pumpWidget(
      MaterialApp(
        home: HoyPage(
          apiClient: _client(httpClient),
          shareExport: (file) async {
            shared = file;
          },
        ),
      ),
    );

    await tester.tap(find.text('Descargar CSV'));
    await tester.pumpAndSettle();

    expect(requests, hasLength(1));
    expect(requests.single.method, 'GET');
    expect(requests.single.url.path, '/api/v1/operational-days/current/sales-export');
    expect(requests.single.url.queryParameters['format'], 'csv');
    expect(requests.single.headers['authorization'], 'Bearer tok');
    expect(requests.single.headers['x-correlation-id'], isNotEmpty);
    expect(requests.single.headers.containsKey('idempotency-key'), isFalse);
    expect(shared!.filename, 'lumo-nandu-hijos-ventas-2026-09-23.csv');
    expect(utf8.decode(shared!.bytes), 'business_date\r\n');
    expect(find.text('Todavía no hay actividad de hoy para exportar.'), findsNothing);

    await tester.tap(find.text('Descargar Excel'));
    await tester.pumpAndSettle();
    expect(requests.last.url.queryParameters['format'], 'xlsx');
    expect(shared!.filename, 'lumo-nandu-hijos-ventas-2026-09-23.xlsx');
    expect(utf8.decode(shared!.bytes), 'xlsx-bytes');
  });

  testWidgets('Hoy shows the empty-current copy only for the tenant 404', (tester) async {
    final httpClient = MockClient((request) async {
      return http.Response(
        jsonEncode({
          'error': {
            'code': 'TENANT_SCOPE_VIOLATION',
            'message': 'operational day not found',
            'retryable': false,
            'correlation_id': 'c1',
          },
        }),
        404,
        headers: {'content-type': 'application/json'},
      );
    });
    await tester.pumpWidget(
      MaterialApp(
        home: HoyPage(
          apiClient: _client(httpClient),
          shareExport: (_) async {},
        ),
      ),
    );
    await tester.tap(find.text('Descargar Excel'));
    await tester.pumpAndSettle();
    expect(find.text('Todavía no hay actividad de hoy para exportar.'), findsOneWidget);
    expect(find.text('operational day not found'), findsNothing);
  });

  testWidgets('Hoy shows the server message for other export errors', (tester) async {
    final httpClient = MockClient((request) async {
      return http.Response(
        jsonEncode({
          'error': {
            'code': 'INTERNAL_ERROR',
            'message': 'confirmed sales export is inconsistent',
            'retryable': true,
            'correlation_id': 'c1',
          },
        }),
        500,
        headers: {'content-type': 'application/json'},
      );
    });
    await tester.pumpWidget(
      MaterialApp(
        home: HoyPage(
          apiClient: _client(httpClient),
          shareExport: (_) async {},
        ),
      ),
    );
    await tester.tap(find.text('Descargar CSV'));
    await tester.pumpAndSettle();
    expect(find.text('confirmed sales export is inconsistent'), findsOneWidget);
  });

  test('in-memory XFile drops the server filename on this platform', () {
    final staged = XFile.fromData(
      Uint8List.fromList(const [1, 2, 3]),
      name: 'lumo-carrota-ventas-2026-09-23.csv',
      mimeType: 'text/csv; charset=utf-8',
    );
    expect(staged.name.endsWith('.csv'), isFalse);
  });

  test('CSV and XLSX shares keep the server filename, bytes, and media type', () async {
    final directory = await Directory.systemTemp.createTemp('lumo-export');
    try {
      final csvBytes = Uint8List.fromList(const [0xEF, 0xBB, 0xBF, 0x61]);
      final csv = await salesExportShareFile(
        SalesExportFile(
          bytes: csvBytes,
          filename: 'lumo-carrota-ventas-2026-09-23.csv',
          mimeType: 'text/csv; charset=utf-8',
        ),
        directory: directory,
      );
      expect(csv.name, 'lumo-carrota-ventas-2026-09-23.csv');
      expect(csv.path.endsWith('.csv'), isTrue);
      expect(csv.mimeType, 'text/csv');
      expect(await csv.readAsBytes(), csvBytes);

      final xlsxBytes = Uint8List.fromList(const [0x50, 0x4B, 0x03, 0x04]);
      final xlsx = await salesExportShareFile(
        SalesExportFile(
          bytes: xlsxBytes,
          filename: 'lumo-carrota-ventas-2026-09-23.xlsx',
          mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        ),
        directory: directory,
      );
      expect(xlsx.name, 'lumo-carrota-ventas-2026-09-23.xlsx');
      expect(xlsx.path.endsWith('.xlsx'), isTrue);
      expect(xlsx.mimeType, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');
      expect(await xlsx.readAsBytes(), xlsxBytes);

      final replaced = Uint8List.fromList(const [0xEF, 0xBB, 0xBF, 0x62]);
      final again = await salesExportShareFile(
        SalesExportFile(
          bytes: replaced,
          filename: 'lumo-carrota-ventas-2026-09-23.csv',
          mimeType: 'text/csv; charset=utf-8',
        ),
        directory: directory,
      );
      expect(again.path, csv.path);
      expect(await again.readAsBytes(), replaced);
    } finally {
      await directory.delete(recursive: true);
    }
  });
}

LumoApiClient _client(http.Client httpClient) {
  return LumoApiClient(
    config: const AppConfig(env: 'test', apiBaseUrl: 'http://lumo.test'),
    session: SessionStore()..accessToken = 'tok',
    httpClient: httpClient,
  );
}
