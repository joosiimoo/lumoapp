import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:lumo/api/lumo_api_client.dart';
import 'package:lumo/core/env/app_config.dart';
import 'package:lumo/core/session/session_store.dart';
import 'package:lumo/features/memoria/memoria_page.dart';
import 'package:lumo/features/memoria/memoria_timeline.dart';
import 'package:lumo/lumo/widgets/lumo_chips.dart';

void main() {
  test('sale_confirmed compact rendering is deterministic', () {
    final cash = memoriaFeedItem({
      'event_type': 'sale_confirmed',
      'business_date': '2026-09-25',
      'local_time': '23:30',
      'facts': {'amount': '22.50', 'payment_method': 'cash'},
    })!;
    expect(cash.typeLabel, 'Venta');
    expect(cash.primary, 'Venta en efectivo por \$22.50');
    expect(cash.secondary, isNull);
    expect(cash.localTime, '23:30');
    expect(
      memoriaFeedItem({
        'event_type': 'sale_confirmed',
        'local_time': '01:00',
        'facts': {'amount': '10.00', 'payment_method': 'card'},
      })!.primary,
      'Venta con tarjeta por \$10.00',
    );
    expect(
      memoriaFeedItem({
        'event_type': 'sale_confirmed',
        'local_time': '01:00',
        'facts': {'amount': '8.00', 'payment_method': 'transfer'},
      })!.primary,
      'Venta por transferencia de \$8.00',
    );
    expect(memoriaSalePrimary(paymentMethod: 'cash', amount: '195.00'), 'Venta en efectivo por \$195.00');
    expect(memoriaSalePrimary(paymentMethod: 'card', amount: '195.00'), 'Venta con tarjeta por \$195.00');
    expect(memoriaSalePrimary(paymentMethod: 'transfer', amount: '120.00'), 'Venta por transferencia de \$120.00');
  });

  test('sale_voided renders reason and never attaches Anular', () {
    final voided = memoriaFeedItem({
      'event_type': 'sale_voided',
      'local_time': '12:10',
      'facts': {
        'amount': '22.50',
        'payment_method': 'cash',
        'void_reason': 'cobro duplicado',
      },
      'actions': [
        {
          'action_id': 'sale.void.request@1',
          'option_id': null,
          'context_token': 'should-ignore',
          'idempotency_key': 'x',
          'conversation_id': 'conv',
        },
      ],
    })!;
    expect(voided.typeLabel, 'Venta anulada');
    expect(voided.primary, 'Venta en efectivo por \$22.50');
    expect(voided.secondary, 'Motivo: cobro duplicado');
    expect(voided.voidRequest, isNull);
  });

  test('cash_count_recorded renders counted primary and exception status chips only', () {
    final cash = memoriaFeedItem({
      'event_type': 'cash_count_recorded',
      'local_time': '18:00',
      'facts': {
        'expected_cash': '22.50',
        'counted_cash': '10.00',
        'cash_difference': '-12.50',
        'cash_status': 'short',
      },
    })!;
    expect(cash.typeLabel, 'Conteo');
    expect(cash.primary, 'Efectivo contado \$10.00');
    expect(cash.secondary, 'Esperado \$22.50 · diferencia \$-12.50');
    expect(cash.statusChip, 'Faltante');
    final balanced = memoriaFeedItem({
      'event_type': 'cash_count_recorded',
      'local_time': '18:00',
      'facts': {
        'expected_cash': '1.00',
        'counted_cash': '1.00',
        'cash_difference': '0.00',
        'cash_status': 'balanced',
      },
    })!;
    expect(balanced.primary, 'Efectivo contado \$1.00');
    expect(balanced.secondary, 'Esperado \$1.00 · diferencia \$0.00');
    expect(balanced.statusChip, isNull);
    expect(
      memoriaFeedItem({
        'event_type': 'cash_count_recorded',
        'local_time': '18:00',
        'facts': {
          'expected_cash': '1.00',
          'counted_cash': '2.00',
          'cash_difference': '1.00',
          'cash_status': 'over',
        },
      })!.statusChip,
      'Sobrante',
    );
  });

  test('daily_close_completed renders gross total, status, and optional note', () {
    final close = memoriaFeedItem({
      'event_type': 'daily_close_completed',
      'local_time': '19:00',
      'facts': {
        'sale_count': 1,
        'gross_sales_total': '22.50',
        'cash_difference': '-2.50',
        'cash_status': 'short',
      },
    })!;
    expect(close.typeLabel, 'Cierre');
    expect(close.primary, 'Cierre completado · \$22.50 en ventas');
    expect(close.secondary, 'Faltante · diferencia \$-2.50');
    expect(close.note, isNull);
    expect(close.primary, isNot(contains('1')));
    final withNote = memoriaFeedItem({
      'event_type': 'daily_close_completed',
      'local_time': '19:00',
      'facts': {
        'sale_count': 1,
        'gross_sales_total': '22.50',
        'cash_difference': '-2.50',
        'cash_status': 'short',
        'close_note': 'Faltaron dos billetes',
      },
    })!;
    expect(withNote.note, 'Faltaron dos billetes');
    expect(withNote.primary, isNot(contains('Faltaron')));
    expect(withNote.secondary, isNot(contains('Faltaron')));
    expect(memoriaFeedItem({'event_type': 'unknown', 'local_time': '19:00', 'facts': {}}), isNull);
  });

  test('sale, void, and close expose a secondary TRX reference from server facts only', () {
    final sale = memoriaFeedItem({
      'event_type': 'sale_confirmed',
      'local_time': '10:00',
      'facts': {'amount': '22.50', 'payment_method': 'cash', 'transaction_number': 'TRX-000003'},
    })!;
    expect(sale.reference, 'TRX-000003');
    expect(sale.typeLabel, 'Venta');
    expect(sale.statusChip, isNull);
    final voided = memoriaFeedItem({
      'event_type': 'sale_voided',
      'local_time': '10:05',
      'facts': {
        'amount': '22.50',
        'payment_method': 'cash',
        'void_reason': 'cobro duplicado',
        'transaction_number': 'TRX-000005',
        'original_transaction_number': 'TRX-000003',
      },
    })!;
    expect(voided.reference, 'TRX-000005 · Anula TRX-000003');
    expect(voided.typeLabel, 'Venta anulada');
    final close = memoriaFeedItem({
      'event_type': 'daily_close_completed',
      'local_time': '19:00',
      'facts': {
        'sale_count': 1,
        'gross_sales_total': '22.50',
        'cash_difference': '0.00',
        'cash_status': 'balanced',
        'transaction_number': 'TRX-1000000',
      },
    })!;
    expect(close.reference, 'TRX-1000000');
    expect(close.typeLabel, 'Cierre');
    // Cash counts never carry a reference, even if a stray fact is present.
    final cash = memoriaFeedItem({
      'event_type': 'cash_count_recorded',
      'local_time': '18:00',
      'facts': {
        'expected_cash': '1.00',
        'counted_cash': '1.00',
        'cash_difference': '0.00',
        'cash_status': 'balanced',
        'transaction_number': 'TRX-000009',
      },
    })!;
    expect(cash.reference, isNull);
    // Legacy rows without the fact, or malformed values, render no reference.
    expect(
      memoriaFeedItem({
        'event_type': 'sale_confirmed',
        'local_time': '10:00',
        'facts': {'amount': '1.00', 'payment_method': 'cash', 'transaction_number': 'bad'},
      })!.reference,
      isNull,
    );
  });

  testWidgets('Memoria renders the TRX line under the primary text and keeps the timeline', (tester) async {
    await tester.pumpWidget(
      _app(
        _client(
          _payload(
            events: [
              {
                'event_type': 'sale_voided',
                'business_date': '2026-09-25',
                'local_time': '12:10',
                'facts': {
                  'amount': '22.50',
                  'payment_method': 'cash',
                  'void_reason': 'cobro duplicado',
                  'transaction_number': 'TRX-000005',
                  'original_transaction_number': 'TRX-000003',
                },
              },
              {
                'event_type': 'sale_confirmed',
                'business_date': '2026-09-25',
                'local_time': '10:00',
                'facts': {'amount': '22.50', 'payment_method': 'cash', 'transaction_number': 'TRX-000003'},
              },
              {
                'event_type': 'cash_count_recorded',
                'business_date': '2026-09-25',
                'local_time': '09:00',
                'facts': {
                  'expected_cash': '1.00',
                  'counted_cash': '1.00',
                  'cash_difference': '0.00',
                  'cash_status': 'balanced',
                },
              },
            ],
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('TRX-000005 · Anula TRX-000003'), findsOneWidget);
    expect(find.text('TRX-000003'), findsOneWidget);
    expect(find.widgetWithText(LumoStatusChip, 'TRX-000003'), findsNothing);
    expect(find.byType(MemoriaTimelineEvent), findsNWidgets(3));
    expect(find.byType(Divider), findsNothing);
    final events = tester.widgetList<MemoriaTimelineEvent>(find.byType(MemoriaTimelineEvent)).toList();
    expect(events[0].connectBelow, isTrue);
    expect(events[2].connectAbove, isTrue);
  });

  test('feed items do not duplicate unnecessary facts', () {
    final sale = memoriaFeedItem({
      'event_type': 'sale_confirmed',
      'local_time': '10:00',
      'facts': {'amount': '12.00', 'payment_method': 'cash'},
    })!;
    expect(sale.secondary, isNull);
    expect(sale.note, isNull);
    final cash = memoriaFeedItem({
      'event_type': 'cash_count_recorded',
      'local_time': '18:00',
      'facts': {
        'expected_cash': '12.00',
        'counted_cash': '12.00',
        'cash_difference': '0.00',
        'cash_status': 'balanced',
      },
    })!;
    expect(cash.primary, 'Efectivo contado \$12.00');
    expect(cash.secondary!.contains('contado'), isFalse);
    final close = memoriaFeedItem({
      'event_type': 'daily_close_completed',
      'local_time': '19:00',
      'facts': {
        'sale_count': 3,
        'gross_sales_total': '36.00',
        'cash_difference': '0.00',
        'cash_status': 'balanced',
      },
    })!;
    expect(close.primary, contains('\$36.00'));
    expect(close.secondary, isNot(contains('\$36.00')));
    expect(close.secondary, isNot(contains('3')));
  });

  test('groups use Hoy, Ayer, and calendar labels from server business dates', () {
    final groups = memoriaGroups(
      events: [
        {
          'event_type': 'sale_confirmed',
          'business_date': '2026-09-25',
          'occurred_at': '2026-09-26T05:30:00+00:00',
          'local_time': '23:30',
          'facts': {'amount': '22.50', 'payment_method': 'cash'},
        },
        {
          'event_type': 'daily_close_completed',
          'business_date': '2026-09-24',
          'occurred_at': '2026-09-25T02:00:00+00:00',
          'local_time': '20:00',
          'facts': {
            'sale_count': 1,
            'gross_sales_total': '22.50',
            'cash_difference': '0.00',
            'cash_status': 'balanced',
          },
        },
        {
          'event_type': 'sale_confirmed',
          'business_date': '2026-09-20',
          'local_time': '12:00',
          'facts': {'amount': '5.00', 'payment_method': 'card'},
        },
        {
          'event_type': 'note',
          'business_date': '2026-09-25',
          'local_time': '23:40',
          'facts': {},
        },
      ],
      businessToday: '2026-09-25',
      businessYesterday: '2026-09-24',
    );
    expect(groups.map((group) => group.label), [
      'Hoy',
      'Ayer',
      '20 de septiembre de 2026',
    ]);
    expect(groups.first.items.single.typeLabel, 'Venta');
    expect(groups[1].items.single.typeLabel, 'Cierre');
    expect(groups.last.items.single.typeLabel, 'Venta');
    expect(
      memoriaDateLabel(
        businessDate: '2026-09-20',
        businessToday: '2026-09-25',
        businessYesterday: '2026-09-24',
      ),
      '20 de septiembre de 2026',
    );
  });

  test('newest-first API order is preserved within groups', () {
    final groups = memoriaGroups(
      events: [
        {
          'event_type': 'sale_confirmed',
          'business_date': '2026-09-25',
          'local_time': '12:06',
          'facts': {'amount': '12.00', 'payment_method': 'cash'},
        },
        {
          'event_type': 'sale_confirmed',
          'business_date': '2026-09-25',
          'local_time': '10:00',
          'facts': {'amount': '8.00', 'payment_method': 'card'},
        },
      ],
      businessToday: '2026-09-25',
      businessYesterday: '2026-09-24',
    );
    expect(groups.single.items.map((item) => item.localTime), ['12:06', '10:00']);
  });

  testWidgets('empty Memoria uses lightweight copy and no footer', (tester) async {
    await tester.pumpWidget(_app(_client(_payload(events: []))));
    await tester.pumpAndSettle();
    expect(find.text('La memoria factual se habilitará cuando existan eventos confirmados.'), findsNothing);
    expect(find.text(memoriaEmptyTitle), findsOneWidget);
    expect(find.text('ACTIVIDAD'), findsNothing);
    expect(find.text('Todavía no hay actividad registrada'), findsNothing);
    expect(find.text('Las ventas, conteos y cierres confirmados aparecerán aquí.'), findsNothing);
    expect(find.text('No hubo actividad.'), findsNothing);
    expect(find.text('Memoria muestra operaciones confirmadas registradas en Lumo.'), findsNothing);
    expect(find.text('Ver anteriores'), findsNothing);
    expect(find.byType(TextField), findsNothing);
    expect(find.text('Corregir'), findsNothing);
    expect(find.text('Explicar'), findsNothing);
    expect(find.text('Olvidar'), findsNothing);
    expect(find.text('Ver evidencia'), findsNothing);
    expect(find.textContaining('Buscar'), findsNothing);
    expect(find.textContaining('Patrones'), findsNothing);
  });

  testWidgets('date groups share one ACTIVIDAD timeline without horizontal dividers', (tester) async {
    await tester.pumpWidget(
      _app(
        _client(
          _payload(
            events: [
              {
                'event_type': 'sale_confirmed',
                'business_date': '2026-09-25',
                'local_time': '12:06',
                'facts': {'amount': '12.00', 'payment_method': 'cash'},
              },
              {
                'event_type': 'sale_confirmed',
                'business_date': '2026-09-25',
                'local_time': '10:00',
                'facts': {'amount': '8.00', 'payment_method': 'card'},
              },
              {
                'event_type': 'cash_count_recorded',
                'business_date': '2026-09-24',
                'local_time': '18:00',
                'facts': {
                  'expected_cash': '1.00',
                  'counted_cash': '1.00',
                  'cash_difference': '0.00',
                  'cash_status': 'balanced',
                },
              },
            ],
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Hoy'), findsOneWidget);
    expect(find.text('Ayer'), findsOneWidget);
    expect(find.text('ACTIVIDAD'), findsNWidgets(2));
    expect(find.text('Venta en efectivo por \$12.00'), findsOneWidget);
    expect(find.text('Venta con tarjeta por \$8.00'), findsOneWidget);
    expect(find.text('Conteo'), findsOneWidget);
    expect(find.byType(Divider), findsNothing);
    expect(find.byType(MemoriaTimelineEvent), findsNWidgets(3));
    final hoyEvents = tester.widgetList<MemoriaTimelineEvent>(find.byType(MemoriaTimelineEvent)).toList();
    expect(hoyEvents.where((event) => event.connectAbove || event.connectBelow).length, greaterThan(0));
    expect(hoyEvents[0].connectAbove, isFalse);
    expect(hoyEvents[0].connectBelow, isTrue);
    expect(hoyEvents[1].connectAbove, isTrue);
    expect(hoyEvents[1].connectBelow, isFalse);
  });

  testWidgets('single-event group renders node without broken connector', (tester) async {
    await tester.pumpWidget(
      _app(
        _client(
          _payload(
            events: [
              {
                'event_type': 'sale_confirmed',
                'business_date': '2026-09-25',
                'local_time': '16:34',
                'facts': {'amount': '195.00', 'payment_method': 'card'},
              },
            ],
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.byType(MemoriaTimelineEvent), findsOneWidget);
    final event = tester.widget<MemoriaTimelineEvent>(find.byType(MemoriaTimelineEvent));
    expect(event.connectAbove, isFalse);
    expect(event.connectBelow, isFalse);
    expect(find.text('Venta con tarjeta por \$195.00'), findsOneWidget);
    expect(find.byType(Divider), findsNothing);
  });

  testWidgets('Memoria renders compact feed and Ver anteriores', (tester) async {
    final requests = <Uri>[];
    final httpClient = MockClient((request) async {
      requests.add(request.url);
      final before = request.url.queryParameters['before'];
      if (before == null) {
        return http.Response(jsonEncode(_body(next: 'cursor-2')), 200, headers: {'content-type': 'application/json'});
      }
      return http.Response(
        jsonEncode(_body(next: null, events: [_event('cash_count_recorded', '2026-09-24', '18:00')])),
        200,
        headers: {'content-type': 'application/json'},
      );
    });
    await tester.pumpWidget(_app(_client(httpClient)));
    await tester.pumpAndSettle();
    expect(find.text('MEMORIA'), findsOneWidget);
    expect(find.text('Lo que Lumo recuerda'), findsOneWidget);
    expect(find.text('ACTIVIDAD'), findsOneWidget);
    expect(find.text('Venta'), findsOneWidget);
    expect(find.text('Venta en efectivo por \$22.50'), findsOneWidget);
    expect(find.text('Cierre'), findsOneWidget);
    expect(find.text('Cierre completado · \$22.50 en ventas'), findsOneWidget);
    expect(find.text('Ventas registradas 22.50'), findsNothing);
    expect(find.text('Hoy'), findsOneWidget);
    expect(find.text('23:30'), findsWidgets);
    expect(find.text('Ver anteriores'), findsOneWidget);
    expect(find.textContaining('event_id'), findsNothing);
    expect(find.text('Memoria muestra operaciones confirmadas registradas en Lumo.'), findsNothing);
    expect(find.byType(Divider), findsNothing);
    expect(find.byType(MemoriaTimelineEvent), findsNWidgets(2));
    await tester.tap(find.text('Ver anteriores'));
    await tester.pumpAndSettle();
    expect(find.text('Conteo'), findsOneWidget);
    expect(find.text('Efectivo contado \$10.00'), findsOneWidget);
    expect(find.widgetWithText(LumoStatusChip, 'Faltante'), findsOneWidget);
    expect(find.text('Ver anteriores'), findsNothing);
    expect(requests.last.queryParameters['before'], 'cursor-2');
  });

  test('void request is parsed only from server actions on sale_confirmed', () {
    final without = memoriaFeedItem({
      'event_type': 'sale_confirmed',
      'local_time': '10:00',
      'facts': {'amount': '22.50', 'payment_method': 'cash'},
    })!;
    expect(without.voidRequest, isNull);
    expect(without.voidConversationId, isNull);
    final withAction = memoriaFeedItem({
      'event_type': 'sale_confirmed',
      'local_time': '10:00',
      'facts': {'amount': '22.50', 'payment_method': 'cash'},
      'actions': [
        {
          'action_id': 'sale.void.request@1',
          'option_id': null,
          'context_token': 'tok-void',
          'idempotency_key': 'idem-void',
          'conversation_id': 'conv-memoria',
        },
      ],
    })!;
    expect(withAction.voidRequest?.actionId, 'sale.void.request@1');
    expect(withAction.voidRequest?.contextToken, 'tok-void');
    expect(withAction.voidConversationId, 'conv-memoria');
  });

  testWidgets('Memoria shows Anular only when server action is present', (tester) async {
    await tester.pumpWidget(
      _app(
        _client(
          _payload(
            events: [
              {
                'event_type': 'sale_confirmed',
                'business_date': '2026-09-25',
                'local_time': '10:00',
                'facts': {'amount': '22.50', 'payment_method': 'cash'},
                'actions': [
                  {
                    'action_id': 'sale.void.request@1',
                    'option_id': null,
                    'context_token': 'tok-void',
                    'idempotency_key': 'idem-void',
                    'conversation_id': 'conv-memoria',
                  },
                ],
              },
              {
                'event_type': 'sale_confirmed',
                'business_date': '2026-09-25',
                'local_time': '09:00',
                'facts': {'amount': '10.00', 'payment_method': 'card'},
              },
              {
                'event_type': 'sale_confirmed',
                'business_date': '2026-09-24',
                'local_time': '18:00',
                'facts': {'amount': '5.00', 'payment_method': 'cash'},
              },
            ],
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Anular'), findsOneWidget);
    expect(find.text('Venta en efectivo por \$22.50'), findsOneWidget);
    expect(find.text('Venta con tarjeta por \$10.00'), findsOneWidget);
    expect(find.text('Ayer'), findsOneWidget);
  });

  testWidgets('Memoria Anular posts void request then confirm and refreshes', (tester) async {
    final posts = <Map<String, dynamic>>[];
    var memoryLoads = 0;
    final httpClient = MockClient((request) async {
      if (request.method == 'GET' && request.url.path.endsWith('/api/v1/memory/events')) {
        memoryLoads += 1;
        final events = memoryLoads == 1
            ? [
                {
                  'event_type': 'sale_confirmed',
                  'business_date': '2026-09-25',
                  'local_time': '10:00',
                  'facts': {'amount': '22.50', 'payment_method': 'cash'},
                  'actions': [
                    {
                      'action_id': 'sale.void.request@1',
                      'option_id': null,
                      'context_token': 'tok-void-req',
                      'idempotency_key': 'idem-void-req',
                      'conversation_id': 'conv-memoria',
                    },
                  ],
                },
              ]
            : [
                {
                  'event_type': 'sale_voided',
                  'business_date': '2026-09-25',
                  'local_time': '10:05',
                  'facts': {
                    'amount': '22.50',
                    'payment_method': 'cash',
                    'void_reason': 'cobro duplicado',
                  },
                },
                {
                  'event_type': 'sale_confirmed',
                  'business_date': '2026-09-25',
                  'local_time': '10:00',
                  'facts': {'amount': '22.50', 'payment_method': 'cash'},
                },
              ];
        return http.Response(
          jsonEncode({
            'events': events,
            'next_cursor': null,
            'business_today': '2026-09-25',
            'business_yesterday': '2026-09-24',
          }),
          200,
          headers: {'content-type': 'application/json'},
        );
      }
      if (request.method == 'POST' && request.url.path.endsWith('/api/v1/lumo/actions')) {
        final body = jsonDecode(request.body) as Map<String, dynamic>;
        posts.add(body);
        if (body['action_id'] == 'sale.void.request@1') {
          return http.Response(
            jsonEncode({
              'text': 'Confirma la anulación',
              'ui': [
                {
                  'component': 'sale_confirmed',
                  'version': 1,
                  'data': {
                    'sale_session_id': 'sess',
                    'payment_id': 'pay',
                    'status': 'confirmed',
                    'currency': 'MXN',
                    'item_count': 1,
                    'total': {'amount': '22.50', 'currency': 'MXN'},
                    'payment': {
                      'method': 'cash',
                      'amount': {'amount': '22.50', 'currency': 'MXN'},
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
                    ],
                    'impact': {
                      'before': {
                        'sale_count': 1,
                        'gross_sales_total': {'amount': '22.50', 'currency': 'MXN'},
                        'expected_cash': {'amount': '22.50', 'currency': 'MXN'},
                      },
                      'after': {
                        'sale_count': 0,
                        'gross_sales_total': {'amount': '0.00', 'currency': 'MXN'},
                        'expected_cash': {'amount': '0.00', 'currency': 'MXN'},
                      },
                    },
                  },
                  'actions': [
                    {
                      'action_id': 'sale.void.confirm@1',
                      'option_id': null,
                      'context_token': 'tok-void-confirm',
                      'idempotency_key': 'idem-void-confirm',
                    },
                  ],
                  'fallback_text': 'Confirma la anulación',
                },
              ],
            }),
            200,
            headers: {'content-type': 'application/json'},
          );
        }
        return http.Response(
          jsonEncode({
            'text': '',
            'ui': [
              {
                'component': 'sale_confirmed',
                'version': 1,
                'data': {
                  'sale_session_id': 'sess',
                  'payment_id': 'pay',
                  'status': 'voided',
                  'currency': 'MXN',
                  'item_count': 1,
                  'total': {'amount': '22.50', 'currency': 'MXN'},
                  'payment': {
                    'method': 'cash',
                    'amount': {'amount': '22.50', 'currency': 'MXN'},
                    'status': 'recorded',
                  },
                  'items': [],
                  'void_reason': 'cobro duplicado',
                },
                'actions': [],
                'fallback_text': 'Venta anulada',
              },
            ],
          }),
          200,
          headers: {'content-type': 'application/json'},
        );
      }
      return http.Response('not found', 404);
    });
    await tester.pumpWidget(_app(_client(httpClient)));
    await tester.pumpAndSettle();
    expect(find.text('Anular'), findsOneWidget);
    await tester.tap(find.text('Anular'));
    await tester.pumpAndSettle();
    expect(posts, isNotEmpty);
    expect(posts.first['action_id'], 'sale.void.request@1');
    expect(posts.first['conversation_id'], 'conv-memoria');
    expect(posts.first['context_token'], 'tok-void-req');
    expect(find.text('Anular venta'), findsOneWidget);
    await tester.enterText(find.byType(TextField), 'cobro duplicado');
    await tester.pump();
    await tester.tap(find.text('Anular venta'));
    await tester.pumpAndSettle();
    expect(posts.length, 2);
    expect(posts.last['action_id'], 'sale.void.confirm@1');
    expect(posts.last['conversation_id'], 'conv-memoria');
    expect(posts.last['payload'], {'void_reason': 'cobro duplicado'});
    expect(find.text('Venta anulada'), findsOneWidget);
    expect(find.text('Venta'), findsOneWidget);
    expect(find.text('Motivo: cobro duplicado'), findsOneWidget);
    expect(find.text('Anular'), findsNothing);
    expect(memoryLoads, greaterThanOrEqualTo(2));
  });

  testWidgets('close and cash status chips render without duplicated sales count', (tester) async {
    await tester.pumpWidget(
      _app(
        _client(
          _payload(
            events: [
              {
                'event_type': 'daily_close_completed',
                'business_date': '2026-09-26',
                'local_time': '08:22',
                'facts': {
                  'sale_count': 1,
                  'gross_sales_total': '22.50',
                  'cash_difference': '-2.50',
                  'cash_status': 'short',
                  'close_note': 'Faltaron dos billetes',
                },
              },
              {
                'event_type': 'cash_count_recorded',
                'business_date': '2026-09-26',
                'local_time': '08:14',
                'facts': {
                  'expected_cash': '22.50',
                  'counted_cash': '20.00',
                  'cash_difference': '-2.50',
                  'cash_status': 'short',
                },
              },
              {
                'event_type': 'daily_close_completed',
                'business_date': '2026-09-25',
                'local_time': '19:00',
                'facts': {
                  'sale_count': 1,
                  'gross_sales_total': '12.00',
                  'cash_difference': '0.00',
                  'cash_status': 'balanced',
                },
              },
              {
                'event_type': 'cash_count_recorded',
                'business_date': '2026-09-25',
                'local_time': '18:00',
                'facts': {
                  'expected_cash': '1.00',
                  'counted_cash': '1.00',
                  'cash_difference': '0.00',
                  'cash_status': 'balanced',
                },
              },
              {
                'event_type': 'cash_count_recorded',
                'business_date': '2026-09-24',
                'local_time': '18:00',
                'facts': {
                  'expected_cash': '1.00',
                  'counted_cash': '2.00',
                  'cash_difference': '1.00',
                  'cash_status': 'over',
                },
              },
            ],
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Cierre completado · \$22.50 en ventas'), findsOneWidget);
    expect(find.text('Faltante · diferencia \$-2.50'), findsOneWidget);
    expect(find.text('Faltaron dos billetes'), findsOneWidget);
    expect(find.text('Ventas registradas 1'), findsNothing);
    expect(find.text('Efectivo contado \$20.00'), findsOneWidget);
    expect(find.text('Esperado \$22.50 · diferencia \$-2.50'), findsOneWidget);
    expect(find.text('Efectivo contado \$1.00'), findsOneWidget);
    expect(find.text('Esperado \$1.00 · diferencia \$0.00'), findsOneWidget);
    expect(find.widgetWithText(LumoStatusChip, 'Faltante'), findsOneWidget);
    expect(find.widgetWithText(LumoStatusChip, 'Sobrante', skipOffstage: false), findsOneWidget);
    // Conteo balanced: no standalone Cuadrado chip.
    expect(find.widgetWithText(LumoStatusChip, 'Cuadrado'), findsNothing);
    // Cierre balanced: status remains in secondary summary.
    expect(find.text('Cuadrado · diferencia \$0.00'), findsOneWidget);
  });
}

Map<String, dynamic> _body({required String? next, List<Map<String, dynamic>>? events}) {
  return {
    'events': events ??
        [
          _event('sale_confirmed', '2026-09-25', '23:30'),
          _event('daily_close_completed', '2026-09-25', '23:40'),
          {'event_type': 'mystery', 'business_date': '2026-09-25', 'local_time': '23:50', 'facts': {}},
        ],
    'next_cursor': next,
    'business_today': '2026-09-25',
    'business_yesterday': '2026-09-24',
  };
}

Map<String, dynamic> _event(String type, String businessDate, String localTime) {
  if (type == 'sale_confirmed') {
    return {
      'event_type': type,
      'business_date': businessDate,
      'local_time': localTime,
      'event_id': 'should-not-render',
      'facts': {'amount': '22.50', 'payment_method': 'cash'},
    };
  }
  if (type == 'cash_count_recorded') {
    return {
      'event_type': type,
      'business_date': businessDate,
      'local_time': localTime,
      'facts': {
        'expected_cash': '22.50',
        'counted_cash': '10.00',
        'cash_difference': '-12.50',
        'cash_status': 'short',
      },
    };
  }
  return {
    'event_type': type,
    'business_date': businessDate,
    'local_time': localTime,
    'facts': {
      'sale_count': 1,
      'gross_sales_total': '22.50',
      'cash_difference': '-2.50',
      'cash_status': 'short',
    },
  };
}

http.Client _payload({required List<Map<String, dynamic>> events}) {
  return MockClient((request) async {
    return http.Response(
      jsonEncode({
        'events': events,
        'next_cursor': null,
        'business_today': '2026-09-25',
        'business_yesterday': '2026-09-24',
      }),
      200,
      headers: {'content-type': 'application/json'},
    );
  });
}

Widget _app(LumoApiClient client) {
  return MaterialApp(home: MemoriaPage(apiClient: client));
}

LumoApiClient _client(http.Client httpClient) {
  return LumoApiClient(
    config: const AppConfig(env: 'test', apiBaseUrl: 'http://lumo.test'),
    session: SessionStore()..accessToken = 'tok',
    httpClient: httpClient,
  );
}
