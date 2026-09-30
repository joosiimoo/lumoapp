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
import 'package:lumo/features/inicio/inicio_page.dart';
import 'package:lumo/lumo/generative_ui/renderer.dart';
import 'package:lumo/lumo/widgets/lumo_composer.dart';

void main() {
  test('sale count label uses singular only for one sale', () {
    expect(saleCountLabel(1), '1 venta');
    expect(saleCountLabel(2), '2 ventas');
    expect(saleCountLabel(0), '0 ventas');
  });

  test('cash status labels and amount display do not recompute money', () {
    expect(cashStatusLabel('not_counted'), 'Falta contar');
    expect(cashStatusLabel('balanced'), 'Caja cuadrada');
    expect(cashStatusLabel('short'), 'Faltante');
    expect(cashStatusLabel('over'), 'Sobrante');
    expect(formatStreamAmount('22.50'), r'$22.50');
    expect(formatStreamAmount('-2.50'), r'-$2.50');
    final stream = BusinessStream.fromJson(_body(state: 'cash_difference', cashStatus: 'short'));
    expect(stream.primaryAction!.actionId, isNull);
    expect(stream.primaryAction!.label, 'Preparar el cierre del día');
    expect(stream.primaryAction!.message, isNull);
    expect(stream.primaryAction!.kind, 'prepare_daily_close');
    expect(stream.primaryAction!.invocation, 'close_workspace');
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

  testWidgets('Inicio light header shows sentence and indicators without close CTAs', (tester) async {
    final client = _client([], (_) => _body(state: 'cash_count_required', cashStatus: 'not_counted'));
    await tester.pumpWidget(_app(client));
    await tester.pumpAndSettle();
    expect(find.text(r'Llevas $22.50 en ventas.'), findsOneWidget);
    expect(find.text('VENTAS HOY'), findsOneWidget);
    expect(find.text('CAJA'), findsOneWidget);
    expect(find.text('1 venta'), findsOneWidget);
    expect(find.text(r'$22.50'), findsWidgets);
    expect(find.text('Falta contar'), findsOneWidget);
    expect(find.text('Registrar conteo'), findsNothing);
    expect(find.text('Revisar cierre'), findsNothing);
    expect(find.text('Confirmar cierre'), findsNothing);
    expect(find.text('Efectivo \$22.50'), findsNothing);
  });


  testWidgets('Hoy opens prepare-close workspace without navigating to Inicio', (tester) async {
    await tester.binding.setSurfaceSize(const Size(420, 1400));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final requests = <http.Request>[];
    final client = _client(requests, (request) {
      if (request.method == 'POST' && request.url.path == '/api/v1/lumo/messages') {
        return _prepareCountResponse();
      }
      return _body(state: 'cash_count_required', cashStatus: 'not_counted');
    });
    await tester.pumpWidget(_app(client));
    await tester.pumpAndSettle();
    expect(find.text('Preparar el cierre del día'), findsNothing);
    await tester.tap(find.text('Hoy'));
    await tester.pumpAndSettle();
    expect(find.text('Preparar el cierre del día'), findsOneWidget);
    expect(find.text('Confirma efectivo y revisa pendientes'), findsOneWidget);
    expect(find.text('Registrar conteo'), findsNothing);
    expect(find.text('Revisar cierre'), findsNothing);
    await tester.ensureVisible(find.text('Preparar el cierre del día'));
    await tester.tap(find.text('Preparar el cierre del día'));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('close-workspace')), findsOneWidget);
    expect(find.text('Cierre del día'), findsOneWidget);
    expect(find.textContaining('deberías tener'), findsOneWidget);
    expect(find.text('¿Cuánto contaste?'), findsOneWidget);
    expect(find.text('Buenos días'), findsNothing);
    expect(find.byKey(const Key('close-count-input')), findsOneWidget);
    final preparePosts = requests.where((r) => r.method == 'POST' && r.url.path == '/api/v1/lumo/messages');
    expect(preparePosts, hasLength(1));
    expect(jsonDecode(preparePosts.single.body)['message'], 'preparar el cierre');
  });

  testWidgets('workspace submits structured cash count and shows balanced facts', (tester) async {
    await tester.binding.setSurfaceSize(const Size(420, 1400));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final requests = <http.Request>[];
    final client = _client(requests, (request) {
      if (request.method == 'POST' && request.url.path == '/api/v1/lumo/actions') {
        final body = jsonDecode(request.body) as Map<String, dynamic>;
        expect(body['action_id'], 'closing.submit_cash_count@1');
        expect(body['payload']['amount'], '22.50');
        return _countedPreparationResponse(status: 'balanced', counted: '22.50', difference: '0.00');
      }
      if (request.method == 'POST' && request.url.path == '/api/v1/lumo/messages') {
        return _prepareCountResponse();
      }
      return _body(state: 'cash_count_required', cashStatus: 'not_counted');
    });
    await tester.pumpWidget(_app(client));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Hoy'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Preparar el cierre del día'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('close-count-input')), '22.50');
    await tester.tap(find.text('Registrar conteo'));
    await tester.pumpAndSettle();
    expect(find.text('Caja cuadrada'), findsOneWidget);
    expect(find.textContaining(r'Esperado $22.50'), findsWidgets);
    expect(find.textContaining(r'Contado $22.50'), findsOneWidget);
    expect(find.textContaining(r'Diferencia $0.00'), findsOneWidget);
    expect(find.text('Cerrar el día'), findsOneWidget);
    expect(find.text('Agregar nota'), findsOneWidget);
    expect(find.text('Buenos días'), findsNothing);
    expect(requests.where((r) => r.url.path == '/api/v1/lumo/actions'), hasLength(1));
  });

  testWidgets('workspace shortage emphasizes optional note and closes with Listo', (tester) async {
    await tester.binding.setSurfaceSize(const Size(420, 1400));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    var closed = false;
    final requests = <http.Request>[];
    final client = _client(requests, (request) {
      if (request.method == 'POST' && request.url.path == '/api/v1/lumo/actions') {
        final body = jsonDecode(request.body) as Map<String, dynamic>;
        expect(body['action_id'], 'closing.confirm@1');
        expect(body['payload']['close_note'], 'Faltaron dos billetes');
        closed = true;
        return _confirmedCloseResponse(note: 'Faltaron dos billetes');
      }
      if (request.method == 'POST' && request.url.path == '/api/v1/lumo/messages') {
        final body = jsonDecode(request.body) as Map<String, dynamic>;
        if (body['message'] == 'cerrar el día') {
          return _reviewResponse(status: 'short', counted: '20.00', difference: '-2.50');
        }
      }
      if (closed) {
        return _body(state: 'closed', cashStatus: 'short', counted: '20.00', difference: '-2.50');
      }
      return _body(
        state: 'cash_difference',
        cashStatus: 'short',
        amount: '22.50',
        counted: '20.00',
        difference: '-2.50',
      );
    });
    await tester.pumpWidget(_app(client));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Hoy'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Preparar el cierre del día'));
    await tester.pumpAndSettle();
    expect(find.text('Faltante'), findsWidgets);
    expect(find.textContaining(r'-$2.50'), findsWidgets);
    expect(find.textContaining('nota opcional'), findsOneWidget);
    await tester.tap(find.text('Agregar nota'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('close-note-input')), 'Faltaron dos billetes');
    await tester.tap(find.text('Cerrar el día'));
    await tester.pumpAndSettle();
    expect(find.text('Día cerrado'), findsOneWidget);
    expect(find.text('Faltaron dos billetes'), findsOneWidget);
    await tester.tap(find.text('Listo'));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('close-workspace')), findsNothing);
    expect(find.text('Día cerrado'), findsOneWidget);
    expect(find.text('Preparar el cierre del día'), findsNothing);
    expect(find.text('Cerrar el día'), findsNothing);
  });

  testWidgets('Hoy shortage CTA is prepare-close and does not invent math', (tester) async {
    final client = _client(
      [],
      (_) => _body(
        state: 'cash_difference',
        cashStatus: 'short',
        amount: '22.50',
        counted: '20.00',
        difference: '-2.50',
      ),
    );
    await tester.pumpWidget(_app(client));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Hoy'));
    await tester.pumpAndSettle();
    expect(find.text('Faltante'), findsWidgets);
    expect(find.textContaining(r'-$2.50'), findsWidgets);
    expect(find.text('20.00 − 22.50'), findsNothing);
    expect(find.text('Preparar el cierre del día'), findsOneWidget);
    expect(find.text('Revisar cierre'), findsNothing);
    expect(find.text('Cerrar el día'), findsNothing);
  });

  testWidgets('a failed refresh drops the previous facts and retry restores them', (tester) async {
    var calls = 0;
    final client = _client([], (_) {
      calls += 1;
      if (calls == 1) {
        return _body(state: 'cash_count_required', cashStatus: 'not_counted', amount: '99.00');
      }
      if (calls == 2 || calls == 3) {
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
    expect(find.text('Falta contar'), findsOneWidget);
    expect(find.text('900gr zanahoria'), findsOneWidget);
    final posted = requests.where((request) => request.method == 'POST').single;
    expect(jsonDecode(posted.body)['message'], '900gr zanahoria');
  });

  testWidgets('hoy and memoria stay on their own reads', (tester) async {
    final requests = <http.Request>[];
    final client = _client(requests, (_) => _body());
    await tester.pumpWidget(_app(client));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Hoy'));
    await tester.pumpAndSettle();
    expect(find.text('Así va hoy'), findsOneWidget);
    expect(find.text('Descargar Excel'), findsOneWidget);
    expect(find.text('Descargar CSV'), findsOneWidget);
    expect(find.text('Cerrar el día'), findsNothing);
    expect(
      requests.where((request) => request.url.path == '/api/v1/operational-days/current/next-best-action'),
      isEmpty,
    );
    expect(requests.where((request) => request.url.path == '/api/v1/business-stream/today').length, greaterThan(1));
    await tester.tap(find.text('Memoria'));
    await tester.pumpAndSettle();
    expect(find.text('Aún no hay actividad registrada.'), findsOneWidget);
    expect(requests.where((request) => request.url.path == '/api/v1/memory/events'), isNotEmpty);
  });

  testWidgets('compact header stays visible while the transcript scrolls', (tester) async {
    await tester.binding.setSurfaceSize(const Size(420, 640));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: InicioPage(
          businessName: 'Carrota',
          stream: BusinessStream.fromJson(_body(state: 'cash_count_required', cashStatus: 'not_counted')),
          messages: [for (var index = 0; index < 30; index++) InicioTurn.user('venta $index')],
        ),
      ),
    ));
    expect(find.text('Buenos días'), findsOneWidget);
    expect(find.text(r'Llevas $22.50 en ventas.'), findsOneWidget);
    expect(find.text('VENTAS HOY'), findsOneWidget);
    expect(find.text('CAJA'), findsOneWidget);
    expect(find.text('Falta contar'), findsOneWidget);
    expect(find.text('1 venta'), findsOneWidget);
    expect(find.text('Registrar conteo'), findsNothing);
    expect(find.text('Revisar cierre'), findsNothing);
  });

  testWidgets('typed cerrar el día still keeps the conversational card', (tester) async {
    await tester.binding.setSurfaceSize(const Size(420, 900));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final client = _client([], (request) {
      if (request.method == 'POST') {
        return _reviewResponse();
      }
      return _twoTenderBody(state: 'ready_to_close', cashStatus: 'balanced');
    });
    await tester.pumpWidget(_app(client));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'cerrar el día');
    await tester.testTextInput.receiveAction(TextInputAction.send);
    await tester.pumpAndSettle();
    expect(find.text('cerrar el día'), findsOneWidget);
    expect(find.text('Confirmar cierre'), findsWidgets);
    expect(find.byKey(const Key('close-workspace')), findsNothing);
  });

  testWidgets('active tab selection styling remains visible', (tester) async {
    final client = _client([], (_) => _body());
    await tester.pumpWidget(_app(client));
    await tester.pumpAndSettle();
    expect(find.text('Inicio'), findsOneWidget);
    await tester.tap(find.text('Hoy'));
    await tester.pumpAndSettle();
    expect(find.text('Hoy'), findsOneWidget);
    expect(find.text('Así va hoy'), findsOneWidget);
    await tester.tap(find.text('Inicio'));
    await tester.pumpAndSettle();
    expect(find.text('Buenos días'), findsOneWidget);
  });

  testWidgets('closed day keeps sale transcript read-only without mutation controls', (tester) async {
    final summary = GenerativeUiContract.fromJson(_staleSaleSummary());
    final added = GenerativeUiContract.fromJson(_staleSaleItemAdded());
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: InicioPage(
            businessName: 'Carrota',
            stream: BusinessStream.fromJson(_body(state: 'closed', cashStatus: 'balanced')),
            messages: [
              InicioTurn.user('900gr zanahoria'),
              InicioTurn.assistant('Agregué Zanahoria', [added]),
              InicioTurn.user('totalizar'),
              InicioTurn.assistant('Venta lista para cobrar', [summary]),
            ],
          ),
        ),
      ),
    );
    expect(find.text('900gr zanahoria'), findsOneWidget);
    expect(find.text('Zanahoria'), findsWidgets);
    expect(find.textContaining(r'$22.50'), findsWidgets);
    expect(find.text('Quitar'), findsNothing);
    expect(find.text('Lista para cobrar'), findsNothing);
    expect(find.text('¿Cómo pagó?'), findsNothing);
    expect(find.text('Efectivo'), findsNothing);
    expect(find.text('Tarjeta'), findsNothing);
    expect(find.text('Transferencia'), findsNothing);
    expect(find.text('Anular'), findsNothing);
  });

  testWidgets('open day still shows sale mutation controls on summary cards', (tester) async {
    final summary = GenerativeUiContract.fromJson(_staleSaleSummary());
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: InicioPage(
            businessName: 'Carrota',
            stream: BusinessStream.fromJson(
              _body(state: 'cash_count_required', cashStatus: 'not_counted'),
            ),
            messages: [
              InicioTurn.assistant('Venta lista para cobrar', [summary]),
            ],
          ),
        ),
      ),
    );
    expect(find.text('Lista para cobrar'), findsOneWidget);
    expect(find.text('¿Cómo pagó?'), findsOneWidget);
    expect(find.text('Efectivo'), findsOneWidget);
    expect(find.text('Tarjeta'), findsOneWidget);
    expect(find.text('Transferencia'), findsOneWidget);
  });
}

Map<String, dynamic> _staleSaleItemAdded() {
  return {
    'component': 'sale_item_added',
    'version': 1,
    'data': {
      'sale_session_id': 'sess-1',
      'sale_item_id': 'item-1',
      'product_name': 'Zanahoria',
      'quantity_input': '900gr',
      'unit_input': 'gr',
      'quantity_normalized': '0.900',
      'unit_normalized': 'kilogram',
      'unit_price': {'amount': '25.00', 'currency': 'MXN'},
      'line_total': {'amount': '22.50', 'currency': 'MXN'},
      'session_item_count': 1,
      'session_total': {'amount': '22.50', 'currency': 'MXN'},
    },
    'actions': [
      {
        'action_id': 'sale.remove_item@1',
        'option_id': null,
        'context_token': 'tok-remove',
        'idempotency_key': 'idem-remove',
      },
    ],
    'fallback_text': 'Agregué Zanahoria',
  };
}

Map<String, dynamic> _staleSaleSummary() {
  return {
    'component': 'sale_summary',
    'version': 1,
    'data': {
      'sale_session_id': 'sess-1',
      'status': 'ready_to_charge',
      'currency': 'MXN',
      'item_count': 1,
      'subtotal': {'amount': '22.50', 'currency': 'MXN'},
      'total': {'amount': '22.50', 'currency': 'MXN'},
      'items': [
        {
          'sale_item_id': 'item-1',
          'product_name': 'Zanahoria',
          'quantity_normalized': '0.900',
          'unit_normalized': 'kilogram',
          'unit_price': {'amount': '25.00', 'currency': 'MXN'},
          'line_total': {'amount': '22.50', 'currency': 'MXN'},
        },
      ],
    },
    'actions': [
      {
        'action_id': 'sale.pay.cash@1',
        'option_id': null,
        'context_token': 'tok-cash',
        'idempotency_key': 'idem-cash',
      },
      {
        'action_id': 'sale.pay.card@1',
        'option_id': null,
        'context_token': 'tok-card',
        'idempotency_key': 'idem-card',
      },
      {
        'action_id': 'sale.pay.transfer@1',
        'option_id': null,
        'context_token': 'tok-xfer',
        'idempotency_key': 'idem-xfer',
      },
    ],
    'fallback_text': r'Venta lista para cobrar · 1 artículo · $22.50',
  };
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

Map<String, dynamic> _twoTenderBody({
  String state = 'ready_to_close',
  String cashStatus = 'balanced',
  String counted = '22.50',
  String? difference = '0.00',
}) {
  return _body(
    state: state,
    cashStatus: cashStatus,
    amount: '22.50',
    saleCount: 2,
    gross: '52.50',
    cash: '22.50',
    card: '30.00',
    transfer: '0.00',
    counted: counted,
    difference: difference,
  );
}

Map<String, dynamic> _prepareCountResponse() {
  return {
    'message_id': 'm-prepare-count',
    'status': 'completed',
    'text': 'Falta contar efectivo',
    'ui': [
      {
        'component': 'daily_close_preparation',
        'version': 1,
        'fallback_text': 'Falta contar efectivo',
        'data': {
          'operational_day_id': 'day-1',
          'business_date': '2026-09-26',
          'day_status': 'open',
          'currency': 'MXN',
          'sale_count': 1,
          'expected_cash': {'amount': '22.50', 'currency': 'MXN'},
          'counted_cash': null,
          'cash_difference': null,
          'cash_status': 'not_counted',
          'confirmation_token': null,
        },
        'actions': [
          {
            'action_id': 'closing.submit_cash_count@1',
            'option_id': null,
            'context_token': 'token-count',
            'idempotency_key': 'idem-count',
          },
        ],
      },
    ],
    'correlation_id': 'c-prepare-count',
  };
}

Map<String, dynamic> _countedPreparationResponse({
  required String status,
  required String counted,
  required String difference,
}) {
  return {
    'message_id': 'm-counted',
    'status': 'completed',
    'text': 'Conteo registrado',
    'ui': [
      {
        'component': 'daily_close_preparation',
        'version': 1,
        'fallback_text': 'Conteo registrado',
        'data': {
          'operational_day_id': 'day-1',
          'business_date': '2026-09-26',
          'day_status': 'open',
          'currency': 'MXN',
          'sale_count': 1,
          'expected_cash': {'amount': '22.50', 'currency': 'MXN'},
          'counted_cash': {'amount': counted, 'currency': 'MXN'},
          'cash_difference': {'amount': difference, 'currency': 'MXN'},
          'cash_status': status,
          'confirmation_token': null,
        },
        'actions': [
          {
            'action_id': 'closing.request@1',
            'option_id': null,
            'context_token': 'token-request',
            'idempotency_key': 'idem-request',
          },
        ],
      },
    ],
    'correlation_id': 'c-counted',
  };
}

Map<String, dynamic> _confirmedCloseResponse({String? note}) {
  return {
    'message_id': 'm-confirmed',
    'status': 'completed',
    'text': 'Cierre confirmado',
    'ui': [
      {
        'component': 'daily_close_confirmed',
        'version': 1,
        'fallback_text': 'Cierre confirmado',
        'data': {
          'operational_day_id': 'day-1',
          'closing_snapshot_id': 'snap-1',
          'business_date': '2026-09-26',
          'day_status': 'closed',
          'closed_at': '2026-09-26T18:00:00Z',
          'currency': 'MXN',
          'sale_count': 1,
          'gross_sales_total': {'amount': '22.50', 'currency': 'MXN'},
          'expected_cash': {'amount': '22.50', 'currency': 'MXN'},
          'counted_cash': {'amount': '20.00', 'currency': 'MXN'},
          'cash_difference': {'amount': '-2.50', 'currency': 'MXN'},
          'cash_status': 'short',
          if (note != null) 'close_note': note,
        },
        'actions': [],
      },
    ],
    'correlation_id': 'c-confirmed',
  };
}

Map<String, dynamic> _reviewResponse({
  String status = 'balanced',
  String expected = '22.50',
  String counted = '22.50',
  String difference = '0.00',
  int saleCount = 2,
  String? prose,
}) {
  final noun = saleCount == 1 ? 'venta' : 'ventas';
  final text = prose ??
      'El cierre está preparado: $saleCount $noun · \$$expected. '
          'Efectivo esperado \$$expected. Contado \$$counted. Diferencia \$$difference. '
          '¿Confirmas el cierre?';
  return {
    'message_id': 'm-review',
    'status': 'completed',
    'text': text,
    'ui': [
      {
        'component': 'daily_close_preparation',
        'version': 1,
        'fallback_text': text,
        'data': {
          'operational_day_id': 'day-1',
          'business_date': '2026-09-26',
          'day_status': 'open',
          'currency': 'MXN',
          'sale_count': saleCount,
          'expected_cash': {'amount': expected, 'currency': 'MXN'},
          'counted_cash': {'amount': counted, 'currency': 'MXN'},
          'cash_difference': {'amount': difference, 'currency': 'MXN'},
          'cash_status': status,
          'confirmation_token': 'token-review',
        },
        'actions': [
          {
            'action_id': 'closing.confirm@1',
            'option_id': null,
            'context_token': 'token-review',
            'idempotency_key': 'idem-confirm',
          },
        ],
      },
    ],
    'correlation_id': 'c-review',
  };
}

Map<String, dynamic> _body({
  String state = 'no_active_day',
  String cashStatus = 'not_counted',
  String amount = '22.50',
  int saleCount = 1,
  String? gross,
  String? cash,
  String? card,
  String? transfer,
  String? counted,
  String? difference,
}) {
  final idle = state == 'no_active_day';
  final countedAmount = counted ?? amount;
  final differenceAmount = difference ?? (cashStatus == 'short' ? '-2.50' : null);
  return {
    'business_date': '2026-09-26',
    'operator_state': state,
    'close_progress': state == 'closed'
        ? 'completed'
        : idle
            ? 'none'
            : 'waiting',
    'responsibility': switch (state) {
      'cash_count_required' => 'Necesito que registres el efectivo contado',
      'ready_to_close' => 'Cierre listo para confirmar',
      'cash_difference' => 'Esperando tu revisión',
      'closed' => 'Cierre completado',
      _ => 'Cuando empiece la actividad, organizo el día.',
    },
    'detail': state == 'cash_count_required' ? 'Espero \$$amount en caja.' : null,
    'factual_summary': idle
        ? null
        : {
            'basis': state == 'closed' ? 'closing_snapshot' : 'registered_sales',
            'sale_count': saleCount,
            'gross_sales_total': {'amount': gross ?? amount, 'currency': 'MXN'},
            'cash_total': {'amount': cash ?? amount, 'currency': 'MXN'},
            'card_total': {'amount': card ?? '0.00', 'currency': 'MXN'},
            'transfer_total': {'amount': transfer ?? '0.00', 'currency': 'MXN'},
            'expected_cash': {'amount': amount, 'currency': 'MXN'},
            'counted_cash': cashStatus == 'not_counted' ? null : {'amount': countedAmount, 'currency': 'MXN'},
            'cash_difference': differenceAmount == null ? null : {'amount': differenceAmount, 'currency': 'MXN'},
            'cash_status': cashStatus,
            'closed_at': state == 'closed' ? '2026-09-26T18:00:00Z' : null,
          },
    'attention': null,
    'primary_action': switch (state) {
      'cash_count_required' || 'ready_to_close' || 'cash_difference' => {
          'kind': 'prepare_daily_close',
          'label': 'Preparar el cierre del día',
          'invocation': 'close_workspace',
          'message': null,
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
