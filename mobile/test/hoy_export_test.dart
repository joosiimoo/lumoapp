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
import 'package:lumo/features/inicio/business_stream.dart';
import 'package:share_plus/share_plus.dart';

void main() {
  testWidgets('Hoy downloads current export bytes and the server filename', (tester) async {
    final requests = <http.Request>[];
    SalesExportFile? shared;
    final httpClient = MockClient((request) async {
      requests.add(request);
      if (request.url.path.endsWith('next-best-action')) {
        return http.Response(
          jsonEncode({
            'operational_day_id': null,
            'day_status': null,
            'pending_count': 0,
            'next_best_action': null,
          }),
          200,
          headers: {'content-type': 'application/json'},
        );
      }
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

    expect(find.text('Anular'), findsNothing);
    expect(find.text('Venta registrada'), findsNothing);
    await tester.tap(find.text('Descargar CSV'));
    await tester.pumpAndSettle();

    final exports = requests.where((request) => request.url.path.endsWith('sales-export')).toList();
    expect(exports, hasLength(1));
    expect(exports.single.method, 'GET');
    expect(exports.single.url.path, '/api/v1/operational-days/current/sales-export');
    expect(exports.single.url.queryParameters['format'], 'csv');
    expect(exports.single.headers['authorization'], 'Bearer tok');
    expect(exports.single.headers['x-correlation-id'], isNotEmpty);
    expect(exports.single.headers.containsKey('idempotency-key'), isFalse);
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

  testWidgets('Hoy keeps exports under the daily summary and does not call next-best-action', (tester) async {
    await tester.binding.setSurfaceSize(const Size(420, 1400));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final requests = <http.Request>[];
    final httpClient = MockClient((request) async {
      requests.add(request);
      return http.Response('{}', 200, headers: {'content-type': 'application/json'});
    });
    await tester.pumpWidget(
      MaterialApp(
        home: HoyPage(
          apiClient: _client(httpClient),
          businessName: 'Carrota',
          shareExport: (_) async {},
          stream: BusinessStream.fromJson({
            'business_date': '2026-09-26',
            'operator_state': 'closed',
            'close_progress': 'completed',
            'responsibility': 'Cierre completado',
            'detail': null,
            'factual_summary': {
              'basis': 'closing_snapshot',
              'sale_count': 2,
              'gross_sales_total': {'amount': '52.50', 'currency': 'MXN'},
              'cash_total': {'amount': '22.50', 'currency': 'MXN'},
              'card_total': {'amount': '30.00', 'currency': 'MXN'},
              'transfer_total': {'amount': '0.00', 'currency': 'MXN'},
              'expected_cash': {'amount': '22.50', 'currency': 'MXN'},
              'counted_cash': {'amount': '22.50', 'currency': 'MXN'},
              'cash_difference': {'amount': '0.00', 'currency': 'MXN'},
              'cash_status': 'balanced',
              'closed_at': '2026-09-26T18:00:00Z',
            },
            'attention': null,
            'primary_action': null,
            'coverage': {
              'sentence': 'Este cierre considera las operaciones registradas en Lumo.',
              'limitation_code': 'only_lumo_registered_operations',
            },
            'as_of': '2026-09-26T18:00:00Z',
          }),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(
      find.text(
        'Incluye las ventas confirmadas y anuladas de hoy, con estado explícito en el archivo. Los totales de arriba excluyen ventas anuladas.',
      ),
      findsOneWidget,
    );
    expect(find.text('Así va Carrota hoy'), findsOneWidget);
    expect(find.text('2 ventas'), findsOneWidget);
    expect(find.text(r'$52.50'), findsOneWidget);
    expect(find.text('Día cerrado'), findsOneWidget);
    expect(find.text('Este cierre considera las operaciones registradas en Lumo.'), findsOneWidget);
    expect(find.text('Cerrar el día'), findsNothing);
    expect(find.text('Revisar cierre'), findsNothing);
    expect(find.text('Confirmar cierre'), findsNothing);
    expect(find.text('Registrar conteo'), findsNothing);
    expect(find.text('Preparar el cierre del día'), findsNothing);
    final summary = tester.getTopLeft(find.text('Así va Carrota hoy'));
    final excel = tester.getTopLeft(find.text('Descargar Excel'));
    expect(excel.dy, greaterThan(summary.dy));
    expect(requests.where((request) => request.url.path.contains('next-best-action')), isEmpty);
  });
}

LumoApiClient _client(http.Client httpClient) {
  return LumoApiClient(
    config: const AppConfig(env: 'test', apiBaseUrl: 'http://lumo.test'),
    session: SessionStore()..accessToken = 'tok',
    httpClient: httpClient,
  );
}
