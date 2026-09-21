import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:lumo/api/lumo_api_client.dart';
import 'package:lumo/app/lumo_app.dart';
import 'package:lumo/core/env/app_config.dart';
import 'package:lumo/core/session/session_store.dart';
import 'package:lumo/lumo/generative_ui/renderer.dart';
import 'package:lumo/lumo/widgets/lumo_card.dart';

Map<String, dynamic> _goldenContract({String lineTotal = '22.50'}) {
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
      'session_item_count': 1,
      'session_total': {'amount': lineTotal, 'currency': 'MXN'},
    },
    'actions': [],
    'fallback_text': 'Agregué 0.900 kg de Zanahoria · \$$lineTotal',
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
    expect(find.textContaining('kilogram'), findsNothing);
    expect(find.byType(LumoCard), findsOneWidget);
  });

  testWidgets('renderer displays payload line total even when it is not 0.900 × 25', (tester) async {
    const renderer = GenerativeUIRenderer();
    final contract = GenerativeUiContract.fromJson(_goldenContract(lineTotal: '99.00'));
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
}
