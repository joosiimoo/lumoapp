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
import 'package:lumo/lumo/widgets/lumo_buttons.dart';
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
    final button = find.text('Registrar conteo');
    expect(button, findsOneWidget);
    await tester.ensureVisible(button);
    await tester.pumpAndSettle();
    await tester.tap(button);
    await tester.pumpAndSettle();
    final field = tester.widget<TextField>(find.byType(TextField));
    expect(field.focusNode!.hasFocus, isTrue);
    expect(field.controller!.text, isEmpty);
    expect(tester.widget<LumoComposer>(find.byType(LumoComposer)).emphasized, isTrue);
    expect(find.text('cerrar el día'), findsNothing);
  });

  testWidgets('cash count CTA stays enabled and one tap posts a single message', (tester) async {
    await tester.binding.setSurfaceSize(const Size(420, 1400));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final requests = <http.Request>[];
    final client = _client(requests, (request) {
      if (request.method == 'POST' && request.url.path == '/api/v1/lumo/messages') {
        return {
          'message_id': 'm-count',
          'status': 'completed',
          'text': 'Conteo registrado',
          'ui': [],
          'correlation_id': 'c-count',
        };
      }
      return _body(state: 'cash_count_required', cashStatus: 'not_counted');
    });
    await tester.pumpWidget(_app(client));
    await tester.pumpAndSettle();
    final button = find.text('Registrar conteo');
    expect(tester.widget<LumoPrimaryButton>(find.ancestor(of: button, matching: find.byType(LumoPrimaryButton))).enabled,
        isTrue);
    await tester.ensureVisible(button);
    await tester.tap(button);
    await tester.pumpAndSettle();
    expect(tester.widget<LumoComposer>(find.byType(LumoComposer)).emphasized, isTrue);
    final postsBeforeSend = requests.where((r) => r.method == 'POST').length;
    await tester.enterText(find.byType(TextField), 'tengo 22.50 en caja');
    await tester.testTextInput.receiveAction(TextInputAction.send);
    await tester.pumpAndSettle();
    final messagePosts =
        requests.where((r) => r.method == 'POST' && r.url.path == '/api/v1/lumo/messages').toList();
    expect(messagePosts.length - postsBeforeSend, 1);
    final body = jsonDecode(messagePosts.last.body) as Map<String, dynamic>;
    expect(body['message'], 'tengo 22.50 en caja');
    expect(body['conversation_id'], isNotEmpty);
    expect(requests.where((r) => r.url.path == '/api/v1/lumo/actions'), isEmpty);
    expect(find.text('tengo 22.50 en caja'), findsOneWidget);
  });

  testWidgets('revisar cierre posts the phrase on the existing conversation', (tester) async {
    await tester.binding.setSurfaceSize(const Size(420, 1400));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final requests = <http.Request>[];
    final client = _client(requests, (request) {
      if (request.method == 'POST') {
        return _reviewResponse();
      }
      return _body(state: 'ready_to_close', cashStatus: 'balanced', difference: '0.00');
    });
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
    expect(find.text('Falta contar efectivo'), findsOneWidget);
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
    expect(find.text('Todavía no hay actividad registrada'), findsOneWidget);
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
    expect(find.text('Falta contar efectivo'), findsOneWidget);
    expect(find.text('1 venta · \$22.50'), findsOneWidget);
    expect(find.text('1 ventas'), findsNothing);
    await tester.scrollUntilVisible(
      find.text('venta 29'),
      400,
      scrollable: find.descendant(
        of: find.byKey(const Key('inicio-transcript')),
        matching: find.byType(Scrollable),
      ),
    );
    expect(find.text('Buenos días'), findsOneWidget);
    expect(find.text('Falta contar efectivo'), findsOneWidget);
    expect(find.text('venta 0'), findsNothing);
    expect(find.text('venta 29'), findsOneWidget);
  });

  testWidgets('return to Inicio shows the current state without scrolling history', (tester) async {
    await tester.binding.setSurfaceSize(const Size(420, 640));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final client = _client([], (request) {
      if (request.method == 'POST') {
        return {
          'message_id': 'm1',
          'status': 'completed',
          'text': 'Anotado',
          'ui': [],
          'correlation_id': 'c1',
        };
      }
      return _body(state: 'ready_to_close', cashStatus: 'balanced', difference: '0.00');
    });
    await tester.pumpWidget(_app(client));
    await tester.pumpAndSettle();
    for (var index = 0; index < 8; index++) {
      await tester.enterText(find.byType(TextField), 'nota $index');
      await tester.testTextInput.receiveAction(TextInputAction.send);
      await tester.pumpAndSettle();
    }
    await tester.drag(find.byKey(const Key('inicio-transcript')), const Offset(0, -800));
    await tester.pumpAndSettle();
    expect(find.text('Caja cuadrada'), findsOneWidget);
    await tester.tap(find.text('Hoy'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Inicio'));
    await tester.pumpAndSettle();
    expect(find.text('Buenos días'), findsOneWidget);
    expect(find.text('Caja cuadrada'), findsOneWidget);
    expect(tester.getTopLeft(find.text('Caja cuadrada')).dy, lessThan(400));
  });

  testWidgets('Hoy shows server sale and tender figures, coverage, and exports', (tester) async {
    final client = _client([], (_) => _twoTenderBody());
    await tester.pumpWidget(_app(client));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Hoy'));
    await tester.pumpAndSettle();
    expect(find.text('Así va hoy'), findsOneWidget);
    expect(find.text('2 ventas'), findsOneWidget);
    expect(find.text(r'$52.50'), findsOneWidget);
    await tester.scrollUntilVisible(
      find.text('Este cierre considera las operaciones registradas en Lumo.'),
      200,
      scrollable: find.descendant(
        of: find.byKey(const Key('hoy-scroll')),
        matching: find.byType(Scrollable),
      ),
    );
    expect(find.textContaining(r'$22.50'), findsWidgets);
    expect(find.textContaining(r'$30.00'), findsWidgets);
    expect(find.textContaining(r'$0.00'), findsWidgets);
    expect(find.text('Este cierre considera las operaciones registradas en Lumo.'), findsOneWidget);
    await tester.scrollUntilVisible(
      find.text('Descargar Excel'),
      200,
      scrollable: find.descendant(
        of: find.byKey(const Key('hoy-scroll')),
        matching: find.byType(Scrollable),
      ),
    );
    expect(find.text('Descargar Excel'), findsOneWidget);
    expect(find.text('Descargar CSV'), findsOneWidget);
    expect(find.text('Cerrar el día'), findsNothing);
    expect(find.text('Registrar conteo'), findsNothing);
  });

  testWidgets('Hoy shortage copy is the server difference', (tester) async {
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
    expect(find.text('Cerrar el día'), findsNothing);
    expect(find.text('Revisar cierre'), findsOneWidget);
  });

  testWidgets('revisar cierre opens a review sheet without a merchant turn or preparation card', (tester) async {
    await tester.binding.setSurfaceSize(const Size(420, 900));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final requests = <http.Request>[];
    final client = _client(requests, (request) {
      if (request.method == 'POST' && request.url.path == '/api/v1/lumo/messages') {
        return _reviewResponse();
      }
      return _twoTenderBody(state: 'ready_to_close', cashStatus: 'balanced');
    });
    await tester.pumpWidget(_app(client));
    await tester.pumpAndSettle();
    expect(find.text('Confirmar cierre'), findsNothing);
    await tester.tap(find.text('Revisar cierre'));
    await tester.pumpAndSettle();
    final messages = requests.where((request) => request.method == 'POST' && request.url.path == '/api/v1/lumo/messages');
    expect(messages, hasLength(1));
    final posted = jsonDecode(messages.single.body) as Map<String, dynamic>;
    expect(posted['message'], 'cerrar el día');
    expect(posted['conversation_id'], isNotEmpty);
    expect(requests.where((request) => request.url.path.endsWith('/lumo/actions')), isEmpty);
    expect(find.byKey(const Key('close-review-sheet')), findsOneWidget);
    expect(find.text('cerrar el día'), findsNothing);
    expect(find.textContaining('El cierre está preparado'), findsNothing);
    expect(find.textContaining('¿Confirmas el cierre?'), findsNothing);
    expect(find.text('Cierre 2026-09-26'), findsNothing);
    final transcript = find.byKey(const Key('inicio-transcript'));
    expect(find.descendant(of: transcript, matching: find.text('Confirmar cierre')), findsNothing);
    expect(find.descendant(of: find.byKey(const Key('close-review-sheet')), matching: find.text('Confirmar cierre')),
        findsOneWidget);
    expect(find.text('Confirmar cierre'), findsOneWidget);
    expect(find.text('2 ventas'), findsWidgets);
    final sheet = find.byKey(const Key('close-review-sheet'));
    expect(find.descendant(of: sheet, matching: find.textContaining(r'$52.50')), findsOneWidget);
    expect(find.descendant(of: sheet, matching: find.textContaining(r'$30.00')), findsOneWidget);
    expect(find.descendant(of: sheet, matching: find.text('Caja cuadrada')), findsOneWidget);
    expect(
      find.descendant(
        of: sheet,
        matching: find.text('Este cierre considera las operaciones registradas en Lumo.'),
      ),
      findsOneWidget,
    );
    await tester.tap(find.text('Cancelar'));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('close-review-sheet')), findsNothing);
    expect(requests.where((request) => request.url.path.endsWith('/lumo/actions')), isEmpty);
    expect(find.text('Revisar cierre'), findsOneWidget);
    expect(find.text('cerrar el día'), findsNothing);
    expect(find.text('Confirmar cierre'), findsNothing);
    await tester.tap(find.text('Hoy'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Inicio'));
    await tester.pumpAndSettle();
    expect(find.text('cerrar el día'), findsNothing);
    expect(find.text('Confirmar cierre'), findsNothing);
    expect(find.text('Cierre 2026-09-26'), findsNothing);
  });

  testWidgets('revisar cierre keeps the silent response out of the transcript', (tester) async {
    await tester.binding.setSurfaceSize(const Size(420, 900));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    const prose =
        'El cierre está preparado: 2 ventas · \$47.50. Efectivo esperado \$22.50. Contado \$22.50. Diferencia \$0.00. ¿Confirmas el cierre?';
    final client = _client([], (request) {
      if (request.method == 'POST') {
        final body = jsonDecode(request.body) as Map<String, dynamic>;
        if (body['message'] == 'cerrar el día') {
          return _reviewResponse(prose: prose);
        }
        return {
          'message_id': 'm-sale',
          'status': 'completed',
          'text': 'Anoté zanahoria.',
          'ui': [],
          'correlation_id': 'c-sale',
        };
      }
      return _body(
        state: 'ready_to_close',
        cashStatus: 'balanced',
        amount: '22.50',
        saleCount: 2,
        gross: '47.50',
        cash: '22.50',
        card: '25.00',
        transfer: '0.00',
        counted: '22.50',
        difference: '0.00',
      );
    });
    await tester.pumpWidget(_app(client));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), '900gr zanahoria');
    await tester.testTextInput.receiveAction(TextInputAction.send);
    await tester.pumpAndSettle();
    expect(find.text('900gr zanahoria'), findsOneWidget);
    expect(find.text('Anoté zanahoria.'), findsOneWidget);
    await tester.tap(find.text('Revisar cierre'));
    await tester.pumpAndSettle();
    expect(find.text('900gr zanahoria'), findsOneWidget);
    expect(find.text('Anoté zanahoria.'), findsOneWidget);
    expect(find.text('cerrar el día'), findsNothing);
    expect(find.text(prose), findsNothing);
    expect(find.textContaining('¿Confirmas el cierre?'), findsNothing);
    expect(find.text('Cierre 2026-09-26'), findsNothing);
    final transcript = find.byKey(const Key('inicio-transcript'));
    expect(find.descendant(of: transcript, matching: find.text('Confirmar cierre')), findsNothing);
    expect(find.descendant(of: transcript, matching: find.text(prose)), findsNothing);
    final sheet = find.byKey(const Key('close-review-sheet'));
    expect(sheet, findsOneWidget);
    expect(find.descendant(of: sheet, matching: find.text('Confirmar cierre')), findsOneWidget);
    expect(find.text('Confirmar cierre'), findsOneWidget);
    expect(find.descendant(of: sheet, matching: find.text('2 ventas')), findsOneWidget);
    expect(find.descendant(of: sheet, matching: find.text(r'Total $47.50')), findsOneWidget);
    expect(find.descendant(of: sheet, matching: find.text(r'Efectivo $22.50')), findsOneWidget);
    expect(find.descendant(of: sheet, matching: find.text(r'Tarjeta $25.00')), findsOneWidget);
    expect(find.descendant(of: sheet, matching: find.text(r'Transferencia $0.00')), findsOneWidget);
    expect(find.descendant(of: sheet, matching: find.text(r'Esperado $22.50')), findsOneWidget);
    expect(find.descendant(of: sheet, matching: find.text(r'Contado $22.50')), findsOneWidget);
    expect(find.descendant(of: sheet, matching: find.text(r'Diferencia $0.00')), findsOneWidget);
    expect(find.descendant(of: sheet, matching: find.text('Caja cuadrada')), findsOneWidget);
    expect(
      find.descendant(
        of: sheet,
        matching: find.text('Este cierre considera las operaciones registradas en Lumo.'),
      ),
      findsOneWidget,
    );
    expect(find.descendant(of: sheet, matching: find.text('Cancelar')), findsOneWidget);
    final rect = tester.getRect(sheet);
    expect(rect.height, greaterThan(80));
    expect(rect.top, greaterThanOrEqualTo(0));
    expect(rect.bottom, lessThanOrEqualTo(900));
  });

  testWidgets('confirmar cierre posts closing.confirm@1 and refreshes Inicio and Hoy', (tester) async {
    await tester.binding.setSurfaceSize(const Size(420, 900));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final requests = <http.Request>[];
    var confirmed = false;
    final client = _client(requests, (request) {
      if (request.method == 'POST' && request.url.path == '/api/v1/lumo/actions') {
        final body = jsonDecode(request.body) as Map<String, dynamic>;
        expect(body['action_id'], 'closing.confirm@1');
        expect(body['context_token'], 'token-review');
        confirmed = true;
        return {
          'message_id': 'm-confirmed',
          'status': 'completed',
          'text': 'Cierre confirmado',
          'ui': [
            {
              'component': 'daily_close_confirmed',
              'version': 1,
              'fallback_text': 'Cierre confirmado',
              'data': {'day_status': 'closed'},
              'actions': [],
            },
          ],
          'correlation_id': 'c-confirmed',
        };
      }
      if (request.method == 'POST') {
        return _reviewResponse(status: 'short', counted: '20.00', difference: '-2.50');
      }
      if (confirmed) {
        return _twoTenderBody(state: 'closed', cashStatus: 'balanced');
      }
      return _twoTenderBody(state: 'cash_difference', cashStatus: 'short', counted: '20.00', difference: '-2.50');
    });
    await tester.pumpWidget(_app(client));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Revisar cierre'));
    await tester.pumpAndSettle();
    expect(find.descendant(of: find.byKey(const Key('close-review-sheet')), matching: find.textContaining(r'-$2.50')),
        findsOneWidget);
    expect(find.text('Confirmar cierre'), findsOneWidget);
    await tester.tap(find.text('Confirmar cierre'));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('close-review-sheet')), findsNothing);
    expect(find.text('Día cerrado'), findsOneWidget);
    expect(find.text('Cierre confirmado'), findsNothing);
    expect(find.text('cerrar el día'), findsNothing);
    expect(find.text('Registrar conteo'), findsNothing);
    expect(find.text('Revisar cierre'), findsNothing);
    expect(find.text('Confirmar cierre'), findsNothing);
    await tester.tap(find.text('Hoy'));
    await tester.pumpAndSettle();
    expect(find.text('Día cerrado'), findsOneWidget);
    expect(find.textContaining(r'$52.50'), findsWidgets);
    expect(find.text('Descargar Excel'), findsOneWidget);
    expect(find.text('Descargar CSV'), findsOneWidget);
    expect(find.text('Registrar conteo'), findsNothing);
    expect(find.text('Revisar cierre'), findsNothing);
    expect(find.text('Confirmar cierre'), findsNothing);
    expect(find.text('Cerrar el día'), findsNothing);
    expect(requests.where((request) => request.url.path.endsWith('/lumo/actions')), hasLength(1));
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
    expect(find.byKey(const Key('close-review-sheet')), findsNothing);
  });

  testWidgets('Hoy revisar cierre uses the same silent review path', (tester) async {
    await tester.binding.setSurfaceSize(const Size(420, 900));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final requests = <http.Request>[];
    final client = _client(requests, (request) {
      if (request.method == 'POST') {
        return _reviewResponse();
      }
      return _twoTenderBody(state: 'ready_to_close', cashStatus: 'balanced');
    });
    await tester.pumpWidget(_app(client));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Hoy'));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Revisar cierre'));
    await tester.tap(find.text('Revisar cierre'));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('close-review-sheet')), findsOneWidget);
    expect(find.text('cerrar el día'), findsNothing);
    expect(find.text('Confirmar cierre'), findsOneWidget);
    await tester.tap(find.text('Cancelar'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Inicio'));
    await tester.pumpAndSettle();
    expect(find.text('cerrar el día'), findsNothing);
    expect(requests.where((request) => request.method == 'POST'), hasLength(1));
  });

  testWidgets('Hoy registrar conteo focuses the composer', (tester) async {
    await tester.binding.setSurfaceSize(const Size(420, 900));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final client = _client([], (_) => _body(state: 'cash_count_required', cashStatus: 'not_counted'));
    await tester.pumpWidget(_app(client));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Hoy'));
    await tester.pumpAndSettle();
    expect(find.text('Cerrar el día'), findsNothing);
    expect(find.text('Confirmar cierre'), findsNothing);
    await tester.ensureVisible(find.text('Registrar conteo'));
    await tester.tap(find.text('Registrar conteo'));
    await tester.pumpAndSettle();
    expect(find.text('Buenos días'), findsOneWidget);
    final field = tester.widget<TextField>(find.byType(TextField));
    expect(field.focusNode!.hasFocus, isTrue);
    expect(field.controller!.text, isEmpty);
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
          'invocation': 'review_surface',
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
