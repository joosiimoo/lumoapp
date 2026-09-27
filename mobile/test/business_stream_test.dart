import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:lumo/api/lumo_api_client.dart';
import 'package:lumo/app/lumo_app.dart';
import 'package:lumo/core/env/app_config.dart';
import 'package:lumo/core/session/session_store.dart';
import 'package:lumo/features/inicio/business_stream.dart';
import 'package:lumo/lumo/widgets/lumo_composer.dart';

void main() {
  test('sale count label uses singular only for one sale', () {
    expect(saleCountLabel(1), '1 venta');
    expect(saleCountLabel(2), '2 ventas');
    expect(saleCountLabel(0), '0 ventas');
  });

  test('cash status labels and amount display do not recompute money', () {
    expect(cashStatusLabel('not_counted'), 'Falta contar efectivo');
    expect(cashStatusLabel('balanced'), 'Caja cuadrada');
    expect(cashStatusLabel('short'), 'Faltante');
    expect(cashStatusLabel('over'), 'Sobrante');
    expect(formatStreamAmount('22.50'), r'$22.50');
    expect(formatStreamAmount('-2.50'), r'-$2.50');
    final stream = BusinessStream.fromJson(_body(state: 'cash_difference', cashStatus: 'short'));
    expect(stream.primaryAction!.actionId, isNull);
    expect(stream.primaryAction!.label, 'Revisar cierre');
    expect(stream.primaryAction!.message, 'cerrar el día');
    expect(stream.coverageSentence, 'Este cierre considera las operaciones registradas en Lumo.');
  });

  testWidgets('panel sits below the greeting and page load does not post', (tester) async {
    final requests = <http.Request>[];
    final client = _client(requests, (_) => _body());
    await tester.pumpWidget(_app(client));
    await tester.pumpAndSettle();
    expect(find.text('Buenos días'), findsOneWidget);
    expect(find.text('Cuando empiece la actividad, organizo el día.'), findsOneWidget);
    expect(find.byType(LumoComposer), findsOneWidget);
    expect(find.text('Inicio'), findsOneWidget);
    expect(find.text('Hoy'), findsOneWidget);
    expect(find.text('Memoria'), findsOneWidget);
    expect(find.text('Negocio'), findsOneWidget);
    final greeting = tester.getTopLeft(find.text('Buenos días'));
    final panel = tester.getTopLeft(find.text('Cuando empiece la actividad, organizo el día.'));
    expect(panel.dy, greaterThan(greeting.dy));
    expect(requests.where((request) => request.method == 'POST'), isEmpty);
    expect(requests.where((request) => request.url.path == '/api/v1/business-stream/today'), isNotEmpty);
  });

  testWidgets('registrar conteo focuses the composer without inserting text', (tester) async {
    await tester.binding.setSurfaceSize(const Size(420, 1400));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final client = _client([], (_) => _body(state: 'cash_count_required', cashStatus: 'not_counted'));
    await tester.pumpWidget(_app(client));
    await tester.pumpAndSettle();
    expect(find.text('Falta contar efectivo'), findsOneWidget);
    expect(find.text('Registrar conteo'), findsOneWidget);
    await tester.ensureVisible(find.text('Registrar conteo'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Registrar conteo'));
    await tester.pump();
    final field = tester.widget<TextField>(find.byType(TextField));
    expect(field.focusNode!.hasFocus, isTrue);
    expect(field.controller!.text, isEmpty);
    expect(find.text('cerrar el día'), findsNothing);
  });

  testWidgets('revisar cierre posts the phrase on the existing conversation', (tester) async {
    await tester.binding.setSurfaceSize(const Size(420, 1400));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final requests = <http.Request>[];
    final client = _client(requests, (_) => _body(state: 'ready_to_close', cashStatus: 'balanced'));
    await tester.pumpWidget(_app(client));
    await tester.pumpAndSettle();
    expect(find.text('Caja cuadrada'), findsOneWidget);
    expect(find.text('Revisar cierre'), findsOneWidget);
    expect(find.text('Confirmar cierre'), findsNothing);
    await tester.ensureVisible(find.text('Revisar cierre'));
    await tester.pumpAndSettle();
    final before = requests.length;
    await tester.tap(find.text('Revisar cierre'));
    await tester.pumpAndSettle();
    final posts = requests.skip(before).where((request) => request.method == 'POST').toList();
    expect(posts, hasLength(1));
    expect(posts.single.url.path, '/api/v1/lumo/messages');
    final body = jsonDecode(posts.single.body) as Map<String, dynamic>;
    expect(body['message'], 'cerrar el día');
    expect(body['conversation_id'], isNotEmpty);
    expect(requests.where((request) => request.url.path.contains('/lumo/actions')), isEmpty);
    expect(find.byType(TextField).evaluate().single, isNotNull);
    expect(tester.widget<TextField>(find.byType(TextField)).controller!.text, isEmpty);
  });

  testWidgets('a failed refresh drops the previous facts and retry restores them', (tester) async {
    var calls = 0;
    final client = _client([], (_) {
      calls += 1;
      if (calls == 1) {
        return _body(state: 'cash_count_required', cashStatus: 'not_counted', amount: '99.00');
      }
      if (calls == 2) {
        throw StateError('unavailable');
      }
      return _body(state: 'cash_count_required', cashStatus: 'not_counted', amount: '22.50');
    });
    await tester.pumpWidget(_app(client));
    await tester.pumpAndSettle();
    expect(find.textContaining('99.00'), findsWidgets);
    await tester.tap(find.text('Hoy'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Inicio'));
    await tester.pumpAndSettle();
    expect(find.text('No pude consultar el estado de hoy.'), findsOneWidget);
    expect(find.textContaining('99.00'), findsNothing);
    expect(find.text('Reintentar'), findsOneWidget);
    await tester.tap(find.text('Reintentar'));
    await tester.pumpAndSettle();
    expect(find.textContaining('22.50'), findsWidgets);
    expect(find.text('No pude consultar el estado de hoy.'), findsNothing);
  });

  testWidgets('a successful message refreshes the stream', (tester) async {
    var streamGets = 0;
    final requests = <http.Request>[];
    final client = _client(requests, (request) {
      if (request.url.path == '/api/v1/business-stream/today') {
        streamGets += 1;
        return _body(state: streamGets == 1 ? 'no_active_day' : 'cash_count_required', cashStatus: 'not_counted');
      }
      return {
        'message_id': 'm1',
        'status': 'completed',
        'text': 'Listo',
        'ui': [],
        'correlation_id': 'c1',
      };
    });
    await tester.pumpWidget(_app(client));
    await tester.pumpAndSettle();
    expect(streamGets, 1);
    await tester.enterText(find.byType(TextField), '900gr zanahoria');
    await tester.testTextInput.receiveAction(TextInputAction.send);
    await tester.pumpAndSettle();
    expect(streamGets, 2);
    expect(find.text('Necesito que registres el efectivo contado'), findsOneWidget);
  });

  testWidgets('hoy and memoria stay on their own reads', (tester) async {
    final requests = <http.Request>[];
    final client = _client(requests, (_) => _body());
    await tester.pumpWidget(_app(client));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Hoy'));
    await tester.pumpAndSettle();
    expect(find.text('Jornada'), findsOneWidget);
    expect(find.text('Cerrar el día'), findsNothing);
    await tester.tap(find.text('Memoria'));
    await tester.pumpAndSettle();
    expect(find.text('Todavía no hay actividad registrada'), findsOneWidget);
    expect(
      requests.where((request) => request.url.path == '/api/v1/operational-days/current/next-best-action'),
      isNotEmpty,
    );
    expect(requests.where((request) => request.url.path == '/api/v1/memory/events'), isNotEmpty);
  });
}

LumoApp _app(LumoApiClient client) {
  return LumoApp(
    config: const AppConfig(env: 'local', apiBaseUrl: 'http://127.0.0.1:8000'),
    apiClient: client,
  );
}

LumoApiClient _client(List<http.Request> requests, Map<String, dynamic> Function(http.Request request) bodyFor) {
  final httpClient = MockClient((request) async {
    requests.add(request);
    if (request.url.path == '/api/v1/memory/events') {
      return http.Response(
        jsonEncode({'events': [], 'next_cursor': null, 'business_today': '', 'business_yesterday': ''}),
        200,
      );
    }
    if (request.url.path == '/api/v1/operational-days/current/next-best-action') {
      return http.Response(jsonEncode({}), 200);
    }
    try {
      return http.Response(jsonEncode(bodyFor(request)), 200);
    } catch (_) {
      return http.Response('no', 500);
    }
  });
  return LumoApiClient(
    config: const AppConfig(env: 'local', apiBaseUrl: 'http://127.0.0.1:8000'),
    session: SessionStore(),
    httpClient: httpClient,
  );
}

Map<String, dynamic> _body({
  String state = 'no_active_day',
  String cashStatus = 'not_counted',
  String amount = '22.50',
}) {
  final idle = state == 'no_active_day';
  return {
    'business_date': '2026-09-26',
    'operator_state': state,
    'close_progress': idle ? 'none' : 'waiting',
    'responsibility': switch (state) {
      'cash_count_required' => 'Necesito que registres el efectivo contado',
      'ready_to_close' => 'Cierre listo para confirmar',
      'cash_difference' => 'Esperando tu revisión',
      _ => 'Cuando empiece la actividad, organizo el día.',
    },
    'detail': state == 'cash_count_required' ? 'Espero \$$amount en caja.' : null,
    'factual_summary': idle
        ? null
        : {
            'basis': 'registered_sales',
            'sale_count': 1,
            'gross_sales_total': {'amount': amount, 'currency': 'MXN'},
            'cash_total': {'amount': amount, 'currency': 'MXN'},
            'card_total': {'amount': '0.00', 'currency': 'MXN'},
            'transfer_total': {'amount': '0.00', 'currency': 'MXN'},
            'expected_cash': {'amount': amount, 'currency': 'MXN'},
            'counted_cash': cashStatus == 'not_counted' ? null : {'amount': amount, 'currency': 'MXN'},
            'cash_difference': cashStatus == 'short' ? {'amount': '-2.50', 'currency': 'MXN'} : null,
            'cash_status': cashStatus,
            'closed_at': null,
          },
    'attention': null,
    'primary_action': switch (state) {
      'cash_count_required' => {
          'kind': 'record_cash_count',
          'label': 'Registrar conteo',
          'invocation': 'composer',
          'message': null,
          'action_id': null,
          'work_item_id': null,
          'outcome_run_id': null,
        },
      'ready_to_close' || 'cash_difference' => {
          'kind': 'request_close',
          'label': 'Revisar cierre',
          'invocation': 'message',
          'message': 'cerrar el día',
          'action_id': null,
          'work_item_id': null,
          'outcome_run_id': null,
        },
      _ => null,
    },
    'coverage': idle
        ? null
        : {
            'sentence': 'Este cierre considera las operaciones registradas en Lumo.',
            'limitation_code': 'only_lumo_registered_operations',
          },
    'as_of': '2026-09-26T12:00:00-06:00',
  };
}
