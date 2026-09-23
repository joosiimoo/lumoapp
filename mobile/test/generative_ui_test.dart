import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:lumo/api/lumo_api_client.dart';
import 'package:lumo/app/lumo_app.dart';
import 'package:lumo/core/env/app_config.dart';
import 'package:lumo/core/session/session_store.dart';
import 'package:lumo/features/inicio/inicio_page.dart';
import 'package:lumo/lumo/generative_ui/renderer.dart';
import 'package:lumo/lumo/widgets/lumo_card.dart';
import 'package:lumo/lumo/widgets/lumo_chips.dart';

Map<String, dynamic> _goldenContract({
  String lineTotal = '22.50',
  int sessionItemCount = 1,
  String sessionTotal = '22.50',
}) {
  return {
    'component': 'sale_item_added',
    'version': 1,
    'data': {
      'sale_session_id': 'sess',
      'sale_item_id': 'item',
      'product_name': 'Zanahoria',
      'quantity_input': '900',
      'unit_input': 'gram',
      'quantity_normalized': '0.900',
      'unit_normalized': 'kilogram',
      'unit_price': {'amount': '25.00', 'currency': 'MXN'},
      'line_total': {'amount': lineTotal, 'currency': 'MXN'},
      'session_item_count': sessionItemCount,
      'session_total': {'amount': sessionTotal, 'currency': 'MXN'},
    },
    'actions': [],
    'fallback_text': 'Agregué 0.900 kg de Zanahoria · \$$lineTotal',
  };
}

Map<String, dynamic> _confirmedContract({
  String total = '56.50',
  String method = 'card',
  int itemCount = 3,
}) {
  return {
    'component': 'sale_confirmed',
    'version': 1,
    'data': {
      'sale_session_id': 'sess',
      'payment_id': 'pay',
      'status': 'confirmed',
      'currency': 'MXN',
      'item_count': itemCount,
      'total': {'amount': total, 'currency': 'MXN'},
      'payment': {
        'method': method,
        'amount': {'amount': total, 'currency': 'MXN'},
        'status': 'recorded',
      },
      'items': [
        {
          'sale_item_id': 'i1',
          'product_name': 'Zanahoria',
          'quantity_normalized': '0.900',
          'unit_normalized': 'kilogram',
          'unit_price': {'amount': '25.00', 'currency': 'MXN'},
          'line_total': {'amount': '22.50', 'currency': 'MXN'},
        },
        {
          'sale_item_id': 'i2',
          'product_name': 'Tomate',
          'quantity_normalized': '0.500',
          'unit_normalized': 'kilogram',
          'unit_price': {'amount': '20.00', 'currency': 'MXN'},
          'line_total': {'amount': '10.00', 'currency': 'MXN'},
        },
        {
          'sale_item_id': 'i3',
          'product_name': 'Galleta A',
          'quantity_normalized': '2',
          'unit_normalized': 'unit',
          'unit_price': {'amount': '12.00', 'currency': 'MXN'},
          'line_total': {'amount': '24.00', 'currency': 'MXN'},
        },
      ],
    },
    'actions': [],
    'fallback_text': 'Venta registrada · $itemCount artículos · \$$total · Tarjeta',
  };
}

Map<String, dynamic> _summaryContract({
  String total = '32.50',
  String zanahoriaLine = '22.50',
  String tomateLine = '10.00',
}) {
  return {
    'component': 'sale_summary',
    'version': 1,
    'data': {
      'sale_session_id': 'sess',
      'status': 'ready_to_charge',
      'currency': 'MXN',
      'item_count': 2,
      'subtotal': {'amount': total, 'currency': 'MXN'},
      'total': {'amount': total, 'currency': 'MXN'},
      'items': [
        {
          'sale_item_id': 'i1',
          'product_name': 'Zanahoria',
          'quantity_normalized': '0.900',
          'unit_normalized': 'kilogram',
          'unit_price': {'amount': '25.00', 'currency': 'MXN'},
          'line_total': {'amount': zanahoriaLine, 'currency': 'MXN'},
        },
        {
          'sale_item_id': 'i2',
          'product_name': 'Tomate',
          'quantity_normalized': '0.500',
          'unit_normalized': 'kilogram',
          'unit_price': {'amount': '20.00', 'currency': 'MXN'},
          'line_total': {'amount': tomateLine, 'currency': 'MXN'},
        },
      ],
    },
    'actions': [],
    'fallback_text': 'Venta lista para cobrar · 2 artículos · \$$total',
  };
}

Map<String, dynamic> _preparationContract({
  String expected = '22.50',
  String counted = '20.00',
  String difference = '-2.50',
  String status = 'short',
  String word = 'Faltante',
}) {
  return {
    'component': 'daily_close_preparation',
    'version': 1,
    'data': {
      'operational_day_id': '01900000-0000-7000-8000-000000000099',
      'business_date': '2026-09-21',
      'day_status': 'open',
      'currency': 'MXN',
      'sale_count': 3,
      'expected_cash': {'amount': expected, 'currency': 'MXN'},
      'counted_cash': {'amount': counted, 'currency': 'MXN'},
      'cash_difference': {'amount': difference, 'currency': 'MXN'},
      'cash_status': status,
      'counted_at': '2026-09-21T23:10:00+00:00',
      'cash_count_id': '01900000-0000-7000-8000-0000000000aa',
    },
    'actions': [],
    'fallback_text':
        'Cierre 2026-09-21 · Efectivo esperado \$$expected · Contado \$$counted · Diferencia $difference · $word',
  };
}

http.Response _json(Map<String, dynamic> body) {
  return http.Response(jsonEncode(body), 200, headers: {'content-type': 'application/json'});
}

http.Response _sessionOk() {
  return _json({
    'actor': {'id': 'u', 'name': 'Owner'},
    'business': {
      'id': 'b',
      'name': 'Carrota',
      'currency': 'MXN',
      'timezone': 'America/Mexico_City',
      'locale': 'es-MX',
    },
  });
}

LumoApiClient _client(MockClient httpClient) {
  return LumoApiClient(
    config: const AppConfig(env: 'test', apiBaseUrl: 'http://lumo.test'),
    session: SessionStore()..accessToken = 'test-token',
    httpClient: httpClient,
  );
}

void main() {
  test('unknown component shows fallback and cannot run actions', () {
    const renderer = GenerativeUIRenderer();
    final contract = GenerativeUiContract.fromJson({
      'component': 'sale_confirmed_card',
      'version': 1,
      'data': {},
      'actions': [
        {
          'action_id': 'sale.confirm',
          'context_token': 'tok',
          'idempotency_key': 'k',
        }
      ],
      'fallback_text': 'Venta registrada',
    });
    final result = renderer.render(contract);
    expect(result.text, 'Venta registrada');
    expect(result.handled, isFalse);
    expect(renderer.canRunActions(contract), isFalse);
  });

  test('unknown version of sale_item_added falls back', () {
    const renderer = GenerativeUIRenderer();
    final contract = GenerativeUiContract.fromJson({
      ..._goldenContract(),
      'version': 2,
      'fallback_text': 'Agregué zanahoria',
    });
    expect(renderer.render(contract).handled, isFalse);
    expect(renderer.canRunActions(contract), isFalse);
    expect(renderer.render(contract).text, 'Agregué zanahoria');
  });

  test('display units map canonical values without math', () {
    expect(SaleItemAddedView.displayUnit('kilogram'), 'kg');
    expect(SaleItemAddedView.displayUnit('gram'), 'g');
    expect(SaleItemAddedView.displayUnit('unit'), 'unidad');
    expect(SaleItemAddedView.displayUnit('package'), 'paquete');
  });

  testWidgets('golden card shows server fields without multiplying', (tester) async {
    const renderer = GenerativeUIRenderer();
    final contract = GenerativeUiContract.fromJson(_goldenContract());
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: renderer.build(contract))));
    expect(find.text('Zanahoria'), findsOneWidget);
    expect(find.text('0.900 kg · \$25.00/kg'), findsOneWidget);
    expect(find.textContaining('\$22.50'), findsWidgets);
    expect(find.textContaining('1 artículo'), findsOneWidget);
    expect(find.textContaining('kilogram'), findsNothing);
    expect(find.byType(LumoCard), findsOneWidget);
  });

  testWidgets('free concept cards keep the server snapshot', (tester) async {
    const renderer = GenerativeUIRenderer();
    for (final name in ['bolsas de hielo', 'Café Orgánico', 'Café Molido']) {
      final contract = GenerativeUiContract.fromJson({
        ..._goldenContract(),
        'data': {
          ..._goldenContract()['data'] as Map<String, dynamic>,
          'product_name': name,
          'unit_normalized': name == 'Café Molido' ? 'kilogram' : 'package',
          'line_total': {'amount': '36.00', 'currency': 'MXN'},
        },
        'fallback_text': 'Agregué $name',
      });
      await tester.pumpWidget(MaterialApp(home: Scaffold(body: renderer.build(contract))));
      expect(find.text(name), findsOneWidget);
      expect(find.text('cafe organico'), findsNothing);
      expect(find.text('cafe molido'), findsNothing);
      expect(find.textContaining('Concepto libre'), findsNothing);
      expect(find.textContaining('Guardar'), findsNothing);
    }
  });

  testWidgets('add-item card shows server session totals without summing lines', (tester) async {
    const renderer = GenerativeUIRenderer();
    final contract = GenerativeUiContract.fromJson(
      _goldenContract(lineTotal: '22.50', sessionItemCount: 2, sessionTotal: '99.00'),
    );
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: renderer.build(contract))));
    expect(find.textContaining('2 artículos'), findsOneWidget);
    expect(find.textContaining('\$99.00'), findsWidgets);
    expect(find.textContaining('\$32.50'), findsNothing);
  });

  testWidgets('sale_summary renders payload totals without adding line totals', (tester) async {
    const renderer = GenerativeUIRenderer();
    final contract = GenerativeUiContract.fromJson(_summaryContract(total: '99.00'));
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: renderer.build(contract))));
    expect(find.text('Zanahoria'), findsOneWidget);
    expect(find.text('Tomate'), findsOneWidget);
    expect(find.textContaining('\$22.50'), findsWidgets);
    expect(find.textContaining('\$10.00'), findsWidgets);
    expect(find.textContaining('\$99.00'), findsWidgets);
    expect(find.textContaining('\$32.50'), findsNothing);
    expect(find.text('Lista para cobrar'), findsOneWidget);
    expect(find.textContaining('2 artículos'), findsWidgets);
    expect(find.byType(LumoStatusChip), findsOneWidget);
    expect(find.text('Registrar'), findsNothing);
    expect(find.text('Corregir'), findsNothing);
  });

  test('unknown version of sale_summary falls back', () {
    const renderer = GenerativeUIRenderer();
    final contract = GenerativeUiContract.fromJson({
      ..._summaryContract(),
      'version': 2,
      'fallback_text': 'Resumen no disponible',
    });
    expect(renderer.render(contract).handled, isFalse);
    expect(renderer.canRunActions(contract), isFalse);
    expect(renderer.render(contract).text, 'Resumen no disponible');
  });

  testWidgets('renderer displays payload line total even when it is not 0.900 × 25', (tester) async {
    const renderer = GenerativeUIRenderer();
    final contract = GenerativeUiContract.fromJson(_goldenContract(lineTotal: '99.00', sessionTotal: '99.00'));
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: renderer.build(contract))));
    expect(find.textContaining('\$99.00'), findsWidgets);
    expect(find.textContaining('\$22.50'), findsNothing);
  });

  testWidgets('Inicio send posts through the typed client', (tester) async {
    final requests = <http.Request>[];
    final httpClient = MockClient((request) async {
      requests.add(request);
      if (request.method == 'GET') {
        return _sessionOk();
      }
      return _json({
        'message_id': 'm1',
        'status': 'completed',
        'text': 'Agregué 0.900 kg de Zanahoria · \$22.50',
        'ui': [_goldenContract()],
        'correlation_id': 'c1',
      });
    });
    await tester.pumpWidget(LumoApp(
      config: const AppConfig(env: 'test', apiBaseUrl: 'http://lumo.test'),
      apiClient: _client(httpClient),
    ));
    await tester.pumpAndSettle();
    expect(find.text('LUMO · CARROTA'), findsOneWidget);
    expect(find.text('Buenos días'), findsOneWidget);
    await tester.enterText(find.byType(TextField), '900gr zanahoria');
    await tester.pump();
    await tester.tap(find.byIcon(Icons.arrow_upward));
    await tester.pumpAndSettle();
    final posted = requests.where((request) => request.method == 'POST').toList();
    expect(posted, isNotEmpty);
    expect(posted.first.url.path, '/api/v1/lumo/messages');
    expect(posted.first.headers['authorization'], 'Bearer test-token');
    expect(posted.first.headers['idempotency-key'], isNotEmpty);
    expect(jsonDecode(posted.first.body)['message'], '900gr zanahoria');
    expect(jsonDecode(posted.first.body)['conversation_id'], isNotEmpty);
    expect(find.text('900gr zanahoria'), findsOneWidget);
    expect(find.text('Zanahoria'), findsOneWidget);
    expect(find.text('0.900 kg · \$25.00/kg'), findsOneWidget);
  });

  testWidgets('Enter submits the same composer path', (tester) async {
    final posted = <String>[];
    final httpClient = MockClient((request) async {
      if (request.method == 'GET') {
        return _sessionOk();
      }
      posted.add(jsonDecode(request.body)['message'] as String);
      return _json({
        'message_id': 'm1',
        'status': 'completed',
        'text': 'Agregué 0.900 kg de Zanahoria · \$22.50',
        'ui': [_goldenContract()],
        'correlation_id': 'c1',
      });
    });
    await tester.pumpWidget(LumoApp(
      config: const AppConfig(env: 'test', apiBaseUrl: 'http://lumo.test'),
      apiClient: _client(httpClient),
    ));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), '900gr zanahoria');
    await tester.testTextInput.receiveAction(TextInputAction.send);
    await tester.pumpAndSettle();
    expect(posted, ['900gr zanahoria']);
    expect(find.text('Zanahoria'), findsOneWidget);
  });

  testWidgets('clarification follow-up reuses the same conversation_id', (tester) async {
    final conversationIds = <String>[];
    final httpClient = MockClient((request) async {
      if (request.method == 'GET') {
        return _sessionOk();
      }
      conversationIds.add(jsonDecode(request.body)['conversation_id'] as String);
      final message = jsonDecode(request.body)['message'] as String;
      if (message == '900 zanahoria') {
        return _json({
          'message_id': 'm1',
          'status': 'completed',
          'text': '¿En qué unidad? gramos o kilogramos.',
          'ui': [],
          'correlation_id': 'c1',
        });
      }
      return _json({
        'message_id': 'm2',
        'status': 'completed',
        'text': 'Agregué 0.900 kg de Zanahoria · \$22.50',
        'ui': [_goldenContract()],
        'correlation_id': 'c2',
      });
    });
    await tester.pumpWidget(LumoApp(
      config: const AppConfig(env: 'test', apiBaseUrl: 'http://lumo.test'),
      apiClient: _client(httpClient),
    ));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), '900 zanahoria');
    await tester.testTextInput.receiveAction(TextInputAction.send);
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'gr');
    await tester.testTextInput.receiveAction(TextInputAction.send);
    await tester.pumpAndSettle();
    expect(conversationIds, hasLength(2));
    expect(conversationIds[0], isNotEmpty);
    expect(conversationIds[1], conversationIds[0]);
    expect(find.text('Zanahoria'), findsOneWidget);
  });

  testWidgets('totalizar posts the same conversation_id and renders summary', (tester) async {
    final conversationIds = <String>[];
    final httpClient = MockClient((request) async {
      if (request.method == 'GET') {
        return _sessionOk();
      }
      conversationIds.add(jsonDecode(request.body)['conversation_id'] as String);
      final message = jsonDecode(request.body)['message'] as String;
      if (message == 'totalizar') {
        return _json({
          'message_id': 'm2',
          'status': 'completed',
          'text': 'Venta lista para cobrar · 2 artículos · \$32.50',
          'ui': [_summaryContract()],
          'correlation_id': 'c2',
        });
      }
      return _json({
        'message_id': 'm1',
        'status': 'completed',
        'text': 'Agregué 0.900 kg de Zanahoria · \$22.50',
        'ui': [_goldenContract()],
        'correlation_id': 'c1',
      });
    });
    await tester.pumpWidget(LumoApp(
      config: const AppConfig(env: 'test', apiBaseUrl: 'http://lumo.test'),
      apiClient: _client(httpClient),
    ));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), '900gr zanahoria');
    await tester.testTextInput.receiveAction(TextInputAction.send);
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'totalizar');
    await tester.testTextInput.receiveAction(TextInputAction.send);
    await tester.pumpAndSettle();
    expect(conversationIds, hasLength(2));
    expect(conversationIds[1], conversationIds[0]);
    expect(find.text('totalizar'), findsOneWidget);
    expect(find.text('Lista para cobrar'), findsOneWidget);
    expect(find.textContaining('\$32.50'), findsWidgets);
  });

  testWidgets('sale_confirmed renders payload totals without summing or change', (tester) async {
    const renderer = GenerativeUIRenderer();
    final contract = GenerativeUiContract.fromJson(_confirmedContract(total: '99.00', method: 'card'));
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: renderer.build(contract))));
    expect(find.text('Venta registrada'), findsOneWidget);
    expect(find.textContaining('3 artículos'), findsWidgets);
    expect(find.textContaining('\$99.00'), findsWidgets);
    expect(find.textContaining('Tarjeta'), findsWidgets);
    expect(find.textContaining('\$56.50'), findsNothing);
    expect(find.textContaining('\$32.50'), findsNothing);
    expect(find.text('Registrar'), findsNothing);
    expect(find.text('Corregir'), findsNothing);
    expect(find.text('Deshacer'), findsNothing);
    expect(find.text('Efectivo'), findsNothing);
    expect(find.text('Transferencia'), findsNothing);
    expect(find.textContaining('cambio'), findsNothing);
    expect(find.byType(LumoCard), findsOneWidget);
    expect(find.byType(LumoStatusChip), findsOneWidget);
  });

  test('unknown version of sale_confirmed falls back', () {
    const renderer = GenerativeUIRenderer();
    final contract = GenerativeUiContract.fromJson({
      ..._confirmedContract(),
      'version': 2,
      'fallback_text': 'Confirmación no disponible',
    });
    expect(renderer.render(contract).handled, isFalse);
    expect(renderer.canRunActions(contract), isFalse);
    expect(renderer.render(contract).text, 'Confirmación no disponible');
  });

  test('display methods map canonical values without math', () {
    expect(SaleConfirmedView.displayMethod('cash'), 'Efectivo');
    expect(SaleConfirmedView.displayMethod('card'), 'Tarjeta');
    expect(SaleConfirmedView.displayMethod('transfer'), 'Transferencia');
  });

  testWidgets('efectivo and next item reuse the same conversation_id', (tester) async {
    final conversationIds = <String>[];
    final httpClient = MockClient((request) async {
      if (request.method == 'GET') {
        return _sessionOk();
      }
      conversationIds.add(jsonDecode(request.body)['conversation_id'] as String);
      final message = jsonDecode(request.body)['message'] as String;
      if (message == 'efectivo') {
        return _json({
          'message_id': 'm3',
          'status': 'completed',
          'text': 'Venta registrada · 3 artículos · \$56.50 · Efectivo',
          'ui': [_confirmedContract(method: 'cash')],
          'correlation_id': 'c3',
        });
      }
      if (message == '900gr zanahoria' && conversationIds.length > 2) {
        return _json({
          'message_id': 'm4',
          'status': 'completed',
          'text': 'Agregué 0.900 kg de Zanahoria · \$22.50',
          'ui': [_goldenContract()],
          'correlation_id': 'c4',
        });
      }
      if (message == 'totalizar') {
        return _json({
          'message_id': 'm2',
          'status': 'completed',
          'text': 'Venta lista para cobrar · 2 artículos · \$32.50',
          'ui': [_summaryContract()],
          'correlation_id': 'c2',
        });
      }
      return _json({
        'message_id': 'm1',
        'status': 'completed',
        'text': 'Agregué 0.900 kg de Zanahoria · \$22.50',
        'ui': [_goldenContract()],
        'correlation_id': 'c1',
      });
    });
    await tester.pumpWidget(LumoApp(
      config: const AppConfig(env: 'test', apiBaseUrl: 'http://lumo.test'),
      apiClient: _client(httpClient),
    ));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), '900gr zanahoria');
    await tester.testTextInput.receiveAction(TextInputAction.send);
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'totalizar');
    await tester.testTextInput.receiveAction(TextInputAction.send);
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'efectivo');
    await tester.testTextInput.receiveAction(TextInputAction.send);
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), '900gr zanahoria');
    await tester.testTextInput.receiveAction(TextInputAction.send);
    await tester.pumpAndSettle();
    expect(conversationIds, hasLength(4));
    expect(conversationIds.toSet(), hasLength(1));
    expect(conversationIds.first, isNotEmpty);
  });

  testWidgets('whitespace Enter does not send', (tester) async {
    var posts = 0;
    final httpClient = MockClient((request) async {
      if (request.method == 'GET') {
        return _sessionOk();
      }
      posts += 1;
      return _json({'message_id': 'm', 'status': 'completed', 'text': 'x', 'ui': [], 'correlation_id': 'c'});
    });
    await tester.pumpWidget(LumoApp(
      config: const AppConfig(env: 'test', apiBaseUrl: 'http://lumo.test'),
      apiClient: _client(httpClient),
    ));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), '   ');
    await tester.testTextInput.receiveAction(TextInputAction.send);
    await tester.pumpAndSettle();
    expect(posts, 0);
  });

  test('business date is the payload calendar day', () {
    expect(OperationalDaySummaryView.displayBusinessDate('2026-09-22'), '2026-09-22');
    expect(OperationalDaySummaryView.displayBusinessDate('2026-09-21'), '2026-09-21');
  });

  testWidgets('operational day summary renders backend values without summing', (tester) async {
    const renderer = GenerativeUIRenderer();
    final contract = GenerativeUiContract.fromJson({
      'component': 'operational_day_summary',
      'version': 1,
      'fallback_text': 'Hoy 2026-09-21 · 2 ventas · \$80.00 · Efectivo \$56.50 · Tarjeta \$23.50 · Transferencia \$0.00',
      'actions': [],
      'data': {
        'operational_day_id': '01900000-0000-7000-8000-000000000099',
        'business_date': '2026-09-21',
        'status': 'open',
        'currency': 'MXN',
        'sale_count': 2,
        'gross_sales_total': '80.00',
        'cash_total': '56.50',
        'card_total': '23.50',
        'transfer_total': '0.00',
      },
    });
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: renderer.build(contract))));
    expect(find.text('2026-09-21'), findsOneWidget);
    expect(find.textContaining('2 ventas'), findsWidgets);
    expect(find.textContaining('\$80.00'), findsWidgets);
    expect(find.textContaining('Efectivo \$56.50'), findsWidgets);
    expect(find.textContaining('Tarjeta \$23.50'), findsWidgets);
    expect(find.textContaining('Transferencia \$0.00'), findsWidgets);
    expect(find.textContaining('\$80.00'), findsWidgets);
    expect(find.text('Cerrar'), findsNothing);
    expect(find.textContaining('diferencia'), findsNothing);
    expect(find.textContaining('esperado'), findsNothing);
    expect(find.byType(LumoCard), findsOneWidget);
  });

  testWidgets('como vamos hoy reuses the same conversation_id', (tester) async {
    final conversationIds = <String>[];
    final httpClient = MockClient((request) async {
      if (request.method == 'GET') {
        return _sessionOk();
      }
      conversationIds.add(jsonDecode(request.body)['conversation_id'] as String);
      return _json({
        'message_id': 'm-day',
        'status': 'completed',
        'text': 'Hoy 2026-09-21 · 0 ventas · \$0.00 · Efectivo \$0.00 · Tarjeta \$0.00 · Transferencia \$0.00',
        'ui': [
          {
            'component': 'operational_day_summary',
            'version': 1,
            'fallback_text': 'Hoy 2026-09-21 · 0 ventas · \$0.00 · Efectivo \$0.00 · Tarjeta \$0.00 · Transferencia \$0.00',
            'actions': [],
            'data': {
              'operational_day_id': null,
              'business_date': '2026-09-21',
              'status': null,
              'currency': 'MXN',
              'sale_count': 0,
              'gross_sales_total': '0.00',
              'cash_total': '0.00',
              'card_total': '0.00',
              'transfer_total': '0.00',
            },
          },
        ],
        'correlation_id': 'c-day',
      });
    });
    await tester.pumpWidget(LumoApp(
      config: const AppConfig(env: 'test', apiBaseUrl: 'http://lumo.test'),
      apiClient: _client(httpClient),
    ));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'como vamos hoy');
    await tester.testTextInput.receiveAction(TextInputAction.send);
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'ventas de hoy');
    await tester.testTextInput.receiveAction(TextInputAction.send);
    await tester.pumpAndSettle();
    expect(conversationIds, hasLength(2));
    expect(conversationIds[1], conversationIds[0]);
    expect(conversationIds.first, isNotEmpty);
    expect(find.text('2026-09-21'), findsWidgets);
    expect(find.text('Cerrar'), findsNothing);
  });

  test('cash status labels map canonical values without deriving them', () {
    expect(DailyClosePreparationView.statusLabel('not_counted'), 'Sin contar');
    expect(DailyClosePreparationView.statusLabel('balanced'), 'Caja cuadrada');
    expect(DailyClosePreparationView.statusLabel('over'), 'Sobrante');
    expect(DailyClosePreparationView.statusLabel('short'), 'Faltante');
  });

  testWidgets('daily close preparation renders server amounts without subtracting', (tester) async {
    const renderer = GenerativeUIRenderer();
    final contract = GenerativeUiContract.fromJson(_preparationContract());
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: renderer.build(contract))));
    expect(find.text('Cierre 2026-09-21'), findsOneWidget);
    expect(find.text('EFECTIVO ESPERADO'), findsOneWidget);
    expect(find.text('CONTADO'), findsOneWidget);
    expect(find.text('DIFERENCIA'), findsOneWidget);
    expect(find.text('\$22.50'), findsOneWidget);
    expect(find.text('\$20.00'), findsOneWidget);
    expect(find.text('-\$2.50'), findsOneWidget);
    expect(find.text('Faltante'), findsOneWidget);
    expect(find.text('Falta contar efectivo'), findsNothing);
    expect(find.text('Cerrar el día'), findsNothing);
    expect(find.text('Confirmar cierre'), findsNothing);
    expect(find.text('Reabrir'), findsNothing);
    expect(find.byType(LumoCard), findsOneWidget);
    expect(find.byType(LumoStatusChip), findsOneWidget);
  });

  testWidgets('daily close preparation shows a server overage as given', (tester) async {
    const renderer = GenerativeUIRenderer();
    final contract = GenerativeUiContract.fromJson(
      _preparationContract(counted: '25.00', difference: '2.50', status: 'over', word: 'Sobrante'),
    );
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: renderer.build(contract))));
    expect(find.text('+\$2.50'), findsOneWidget);
    expect(find.text('-\$2.50'), findsNothing);
    expect(find.text('Sobrante'), findsOneWidget);
  });

  testWidgets('not counted state shows no counted amount and no difference', (tester) async {
    const renderer = GenerativeUIRenderer();
    final contract = GenerativeUiContract.fromJson({
      'component': 'daily_close_preparation',
      'version': 1,
      'fallback_text': 'Cierre 2026-09-21 · Efectivo esperado \$22.50 · Falta contar efectivo',
      'actions': [],
      'data': {
        'operational_day_id': '01900000-0000-7000-8000-000000000099',
        'business_date': '2026-09-21',
        'day_status': 'open',
        'currency': 'MXN',
        'sale_count': 1,
        'expected_cash': {'amount': '22.50', 'currency': 'MXN'},
        'counted_cash': null,
        'cash_difference': null,
        'cash_status': 'not_counted',
        'counted_at': null,
        'cash_count_id': null,
      },
    });
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: renderer.build(contract))));
    expect(find.text('Sin contar'), findsOneWidget);
    expect(find.text('Falta contar efectivo'), findsOneWidget);
    expect(find.text('\$22.50'), findsOneWidget);
    expect(find.text('CONTADO'), findsNothing);
    expect(find.text('DIFERENCIA'), findsNothing);
    expect(find.text('\$0.00'), findsNothing);
  });

  test('unknown version of daily_close_preparation falls back', () {
    const renderer = GenerativeUIRenderer();
    final contract = GenerativeUiContract.fromJson({
      ..._preparationContract(),
      'version': 2,
      'fallback_text': 'Cierre no disponible',
    });
    expect(renderer.render(contract).handled, isFalse);
    expect(renderer.canRunActions(contract), isFalse);
    expect(renderer.render(contract).text, 'Cierre no disponible');
  });

  testWidgets('cash count and preparation reuse the Inicio conversation_id', (tester) async {
    final conversationIds = <String>[];
    final httpClient = MockClient((request) async {
      if (request.method == 'GET') {
        return _sessionOk();
      }
      conversationIds.add(jsonDecode(request.body)['conversation_id'] as String);
      final message = jsonDecode(request.body)['message'] as String;
      if (message == 'tengo 20 en caja') {
        return _json({
          'message_id': 'm-count',
          'status': 'completed',
          'text': _preparationContract()['fallback_text'],
          'ui': [_preparationContract()],
          'correlation_id': 'c-count',
        });
      }
      return _json({
        'message_id': 'm-prep',
        'status': 'completed',
        'text': _preparationContract()['fallback_text'],
        'ui': [_preparationContract()],
        'correlation_id': 'c-prep',
      });
    });
    await tester.pumpWidget(LumoApp(
      config: const AppConfig(env: 'test', apiBaseUrl: 'http://lumo.test'),
      apiClient: _client(httpClient),
    ));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'tengo 20 en caja');
    await tester.testTextInput.receiveAction(TextInputAction.send);
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'preparar el cierre');
    await tester.testTextInput.receiveAction(TextInputAction.send);
    await tester.pumpAndSettle();
    expect(conversationIds, hasLength(2));
    expect(conversationIds[1], conversationIds[0]);
    expect(conversationIds.first, isNotEmpty);
    expect(find.text('tengo 20 en caja'), findsOneWidget);
    expect(find.text('EFECTIVO ESPERADO'), findsWidgets);
    expect(find.text('Confirmar cierre'), findsNothing);
  });

  testWidgets('confirmed close renders server amounts and no client math', (tester) async {
    const renderer = GenerativeUIRenderer();
    final contract = GenerativeUiContract.fromJson({
      'component': 'daily_close_confirmed',
      'version': 1,
      'fallback_text': 'Cierre confirmado · 2026-09-22 · 1 venta · \$22.50 · Sobrante',
      'actions': [],
      'data': {
        'operational_day_id': '01900000-0000-7000-8000-000000000099',
        'business_date': '2026-09-22',
        'currency': 'MXN',
        'sale_count': 1,
        'gross_sales_total': {'amount': '22.50', 'currency': 'MXN'},
        'expected_cash': {'amount': '22.50', 'currency': 'MXN'},
        'counted_cash': {'amount': '25.00', 'currency': 'MXN'},
        'cash_difference': {'amount': '9.99', 'currency': 'MXN'},
        'cash_status': 'over',
        'closed_at': '2026-09-22T18:00:00+00:00',
        'confirmation_token': 'must-not-appear',
      },
    });
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: renderer.build(contract))));
    expect(find.text('Cierre confirmado'), findsOneWidget);
    expect(find.text('\$9.99'), findsOneWidget);
    expect(find.text('\$2.50'), findsNothing);
    expect(find.text('Sobrante'), findsOneWidget);
    expect(find.text('must-not-appear'), findsNothing);
    expect(find.text('Confirmar cierre'), findsNothing);
    expect(find.text('Reabrir'), findsNothing);
  });

  testWidgets('closed summary shows the server Cerrado label', (tester) async {
    const renderer = GenerativeUIRenderer();
    final contract = GenerativeUiContract.fromJson({
      'component': 'operational_day_summary',
      'version': 1,
      'fallback_text': 'Hoy 2026-09-22 · 1 venta · \$22.50',
      'actions': [],
      'data': {
        'operational_day_id': '01900000-0000-7000-8000-000000000099',
        'business_date': '2026-09-22',
        'status': 'closed',
        'currency': 'MXN',
        'sale_count': 1,
        'gross_sales_total': '22.50',
        'cash_total': '22.50',
        'card_total': '0.00',
        'transfer_total': '0.00',
      },
    });
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: renderer.build(contract))));
    expect(find.text('Cerrado'), findsOneWidget);
  });

  test('confirmation token is kept, echoed only in memory, and cleared', () {
    const token = 'header.payload.sig';
    GenerativeUiContract card(String component, Map<String, dynamic> data) {
      return GenerativeUiContract.fromJson({
        'component': component,
        'version': 1,
        'fallback_text': 'Cierre',
        'actions': [],
        'data': data,
      });
    }

    final kept = nextConfirmationToken([
      card('daily_close_preparation', {'confirmation_token': token}),
    ], null);
    expect(kept, token);
    final clearedByNull = nextConfirmationToken([
      card('daily_close_preparation', {'confirmation_token': null}),
    ], token);
    expect(clearedByNull, isNull);
    final clearedByClose = nextConfirmationToken([
      card('daily_close_confirmed', {}),
    ], token);
    expect(clearedByClose, isNull);
  });

  test('mismatched confirm token is not echoed', () {
    final contract = GenerativeUiContract.fromJson({
      'component': 'daily_close_preparation',
      'version': 1,
      'fallback_text': 'El cierre está preparado',
      'actions': [
        {
          'action_id': 'closing.confirm@1',
          'option_id': null,
          'context_token': 'button-token',
          'idempotency_key': 'k-confirm',
        },
      ],
      'data': {'confirmation_token': 'other-token'},
    });
    expect(nextConfirmationToken([contract], 'previous'), isNull);
  });

  test('duplicate prose is hidden only for the approved cards', () {
    final summary = GenerativeUiContract.fromJson(_summaryContract());
    expect(hideAssistantProse(summary.fallbackText, summary), isTrue);
    final prepared = GenerativeUiContract.fromJson({
      ..._preparationContract(),
      'fallback_text': 'El cierre está preparado: 1 venta · \$22.50.',
    });
    expect(hideAssistantProse(prepared.fallbackText, prepared), isFalse);
    final standard = GenerativeUiContract.fromJson(_preparationContract());
    expect(hideAssistantProse(standard.fallbackText, standard), isTrue);
  });

  testWidgets('payment buttons come only from known server actions', (tester) async {
    const renderer = GenerativeUIRenderer();
    final contract = GenerativeUiContract.fromJson({
      ..._summaryContract(),
      'actions': [
        {
          'action_id': 'sale.pay.cash@1',
          'option_id': null,
          'context_token': 'cash-token',
          'idempotency_key': 'cash-key',
        },
        {
          'action_id': 'sale.pay.crypto@1',
          'option_id': null,
          'context_token': 'crypto-token',
          'idempotency_key': 'crypto-key',
        },
      ],
    });
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: renderer.build(contract, chrome: const UiActionChrome(onAction: _ignoreAction)))));
    expect(find.text('¿Cómo pagó?'), findsOneWidget);
    expect(find.text('Efectivo'), findsOneWidget);
    expect(find.text('Tarjeta'), findsNothing);
    expect(find.text('Transferencia'), findsNothing);
    expect(find.text('sale.pay.crypto@1'), findsNothing);
  });

  testWidgets('sale confirmed renders every server line and one payment label', (tester) async {
    const renderer = GenerativeUIRenderer();
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: renderer.build(GenerativeUiContract.fromJson(_confirmedContract())))));
    expect(find.text('Zanahoria'), findsOneWidget);
    expect(find.text('Tomate'), findsOneWidget);
    expect(find.text('Galleta A'), findsOneWidget);
    expect(find.text('Pago Tarjeta'), findsOneWidget);
    expect(find.text('Deshacer'), findsNothing);
  });

  test('over difference adds a display prefix and short keeps the server sign', () {
    expect(
      DailyClosePreparationView.displayDifference('over', {'amount': '2.50', 'currency': 'MXN'}),
      '+\$2.50',
    );
    expect(
      DailyClosePreparationView.displayDifference('short', {'amount': '-2.50', 'currency': 'MXN'}),
      '-\$2.50',
    );
  });

  testWidgets('a tap posts the server action without a user bubble or sale id', (tester) async {
    final bodies = <Map<String, dynamic>>[];
    final httpClient = MockClient((request) async {
      if (request.method == 'GET') {
        return _sessionOk();
      }
      final body = jsonDecode(request.body) as Map<String, dynamic>;
      bodies.add(body);
      if (request.url.path.endsWith('/actions')) {
        return _json({
          'message_id': 'm-paid',
          'status': 'completed',
          'text': 'Venta registrada · 2 artículos · \$32.50 · Efectivo',
          'ui': [_confirmedContract(total: '32.50', method: 'cash', itemCount: 2)],
          'correlation_id': 'c-paid',
        });
      }
      return _json({
        'message_id': 'm-ready',
        'status': 'completed',
        'text': _summaryContract()['fallback_text'],
        'ui': [
          {
            ..._summaryContract(),
            'actions': [
              {
                'action_id': 'sale.pay.cash@1',
                'option_id': null,
                'context_token': 'cash-token',
                'idempotency_key': 'server-key',
              },
            ],
          },
        ],
        'correlation_id': 'c-ready',
      });
    });
    await tester.pumpWidget(LumoApp(
      config: const AppConfig(env: 'test', apiBaseUrl: 'http://lumo.test'),
      apiClient: _client(httpClient),
    ));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'totalizar');
    await tester.testTextInput.receiveAction(TextInputAction.send);
    await tester.pumpAndSettle();
    expect(find.text('totalizar'), findsOneWidget);
    await tester.ensureVisible(find.text('Efectivo'));
    await tester.tap(find.text('Efectivo'));
    await tester.pumpAndSettle();
    expect(find.text('totalizar'), findsOneWidget);
    expect(find.text('Efectivo'), findsOneWidget);
    expect(find.text('Venta registrada'), findsOneWidget);
    final action = bodies.last;
    expect(action.containsKey('sale_session_id'), isFalse);
    expect(action['idempotency_key'], 'server-key');
    expect(action['option_id'], isNull);
    expect(bodies.where((body) => body['message'] == 'Efectivo'), isEmpty);
  });

  testWidgets('failure keeps the card and retries the same server key', (tester) async {
    var attempts = 0;
    final keys = <String>[];
    final httpClient = MockClient((request) async {
      if (request.method == 'GET') {
        return _sessionOk();
      }
      if (request.url.path.endsWith('/actions')) {
        attempts += 1;
        keys.add(jsonDecode(request.body)['idempotency_key'] as String);
        return http.Response('{"error":{"code":"INTERNAL_ERROR","message":"no"}}', 500);
      }
      return _json({
        'message_id': 'm-ready',
        'status': 'completed',
        'text': _summaryContract()['fallback_text'],
        'ui': [
          {
            ..._summaryContract(),
            'actions': [
              {
                'action_id': 'sale.pay.cash@1',
                'option_id': null,
                'context_token': 'cash-token',
                'idempotency_key': 'server-key',
              },
            ],
          },
        ],
        'correlation_id': 'c-ready',
      });
    });
    await tester.pumpWidget(LumoApp(
      config: const AppConfig(env: 'test', apiBaseUrl: 'http://lumo.test'),
      apiClient: _client(httpClient),
    ));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'totalizar');
    await tester.testTextInput.receiveAction(TextInputAction.send);
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Efectivo'));
    await tester.tap(find.text('Efectivo'));
    await tester.pump();
    expect(find.text('No pude registrar eso. Intenta de nuevo.'), findsOneWidget);
    expect(find.text('Efectivo'), findsOneWidget);
    await tester.ensureVisible(find.text('Efectivo'));
    await tester.tap(find.text('Efectivo'));
    await tester.pump();
    expect(attempts, 2);
    expect(keys, ['server-key', 'server-key']);
    await tester.pump(const Duration(seconds: 3));
  });

  testWidgets('stale action shows clarification and no confirmed card', (tester) async {
    final httpClient = MockClient((request) async {
      if (request.method == 'GET') {
        return _sessionOk();
      }
      if (request.url.path.endsWith('/actions')) {
        return _json({
          'message_id': 'm-stale',
          'status': 'completed',
          'text': 'Esta acción ya no aplica a la venta en curso.',
          'ui': [],
          'correlation_id': 'c-stale',
        });
      }
      return _json({
        'message_id': 'm-ready',
        'status': 'completed',
        'text': _summaryContract()['fallback_text'],
        'ui': [
          {
            ..._summaryContract(),
            'actions': [
              {
                'action_id': 'sale.pay.cash@1',
                'option_id': null,
                'context_token': 'cash-token',
                'idempotency_key': 'server-key',
              },
            ],
          },
        ],
        'correlation_id': 'c-ready',
      });
    });
    await tester.pumpWidget(LumoApp(
      config: const AppConfig(env: 'test', apiBaseUrl: 'http://lumo.test'),
      apiClient: _client(httpClient),
    ));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'totalizar');
    await tester.testTextInput.receiveAction(TextInputAction.send);
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Efectivo'));
    await tester.tap(find.text('Efectivo'));
    await tester.pumpAndSettle();
    expect(find.text('Esta acción ya no aplica a la venta en curso.'), findsOneWidget);
    expect(find.text('Venta registrada'), findsNothing);
    expect(find.text('Lista para cobrar'), findsOneWidget);
    expect(find.text('totalizar'), findsOneWidget);
  });

  testWidgets('request-close prose stays visible beside the card', (tester) async {
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: InicioPage(
          messages: [
            InicioTurn.assistant(
              'El cierre está preparado: 1 venta · \$22.50.',
              [
                GenerativeUiContract.fromJson({
                  ..._preparationContract(),
                  'fallback_text': 'Cierre 2026-09-21 · Efectivo esperado \$22.50',
                }),
              ],
            ),
          ],
        ),
      ),
    ));
    expect(find.text('El cierre está preparado: 1 venta · \$22.50.'), findsOneWidget);
    expect(find.text('Cierre 2026-09-21'), findsOneWidget);
  });

  testWidgets('a second tap while the action is in flight sends nothing', (tester) async {
    var posts = 0;
    final release = Completer<http.Response>();
    final httpClient = MockClient((request) async {
      if (request.method == 'GET') {
        return _sessionOk();
      }
      if (request.url.path.endsWith('/actions')) {
        posts += 1;
        return release.future;
      }
      return _json({
        'message_id': 'm-ready',
        'status': 'completed',
        'text': _summaryContract()['fallback_text'],
        'ui': [
          {
            ..._summaryContract(),
            'actions': [
              {
                'action_id': 'sale.pay.cash@1',
                'option_id': null,
                'context_token': 'cash-token',
                'idempotency_key': 'server-key',
              },
            ],
          },
        ],
        'correlation_id': 'c-ready',
      });
    });
    await tester.pumpWidget(LumoApp(
      config: const AppConfig(env: 'test', apiBaseUrl: 'http://lumo.test'),
      apiClient: _client(httpClient),
    ));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'totalizar');
    await tester.testTextInput.receiveAction(TextInputAction.send);
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Efectivo'));
    await tester.tap(find.text('Efectivo'));
    await tester.pump();
    await tester.tap(find.text('Efectivo'));
    await tester.pump();
    expect(posts, 1);
    release.complete(_json({
      'message_id': 'm-paid',
      'status': 'completed',
      'text': 'Venta registrada',
      'ui': [],
      'correlation_id': 'c-paid',
    }));
    await tester.pumpAndSettle();
  });
}

void _ignoreAction(GenerativeUiAction action) {}
