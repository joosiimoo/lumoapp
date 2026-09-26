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
  test('placeholder copy is gone and cards stay deterministic', () {
    expect(
      memoriaCardView({
        'event_type': 'sale_confirmed',
        'business_date': '2026-09-25',
        'local_time': '23:30',
        'facts': {'amount': '22.50', 'payment_method': 'cash'},
      })!.lines,
      ['22.50 · Efectivo'],
    );
    expect(
      memoriaCardView({
        'event_type': 'sale_confirmed',
        'local_time': '01:00',
        'facts': {'amount': '10.00', 'payment_method': 'card'},
      })!.lines.single,
      '10.00 · Tarjeta',
    );
    expect(
      memoriaCardView({
        'event_type': 'sale_confirmed',
        'local_time': '01:00',
        'facts': {'amount': '8.00', 'payment_method': 'transfer'},
      })!.lines.single,
      '8.00 · Transferencia',
    );
    final cash = memoriaCardView({
      'event_type': 'cash_count_recorded',
      'local_time': '18:00',
      'facts': {
        'expected_cash': '22.50',
        'counted_cash': '10.00',
        'cash_difference': '-12.50',
        'cash_status': 'short',
      },
    })!;
    expect(cash.title, 'Conteo de efectivo');
    expect(cash.lines, ['Esperado 22.50', 'Contado 10.00', 'Diferencia -12.50']);
    expect(cash.chip, 'Faltante');
    expect(
      memoriaCardView({
        'event_type': 'cash_count_recorded',
        'local_time': '18:00',
        'facts': {'expected_cash': '1.00', 'counted_cash': '1.00', 'cash_difference': '0.00', 'cash_status': 'balanced'},
      })!.chip,
      'Cuadrado',
    );
    expect(
      memoriaCardView({
        'event_type': 'cash_count_recorded',
        'local_time': '18:00',
        'facts': {'expected_cash': '1.00', 'counted_cash': '2.00', 'cash_difference': '1.00', 'cash_status': 'over'},
      })!.chip,
      'Sobrante',
    );
    final close = memoriaCardView({
      'event_type': 'daily_close_completed',
      'local_time': '19:00',
      'facts': {
        'sale_count': 1,
        'gross_sales_total': '22.50',
        'cash_difference': '-2.50',
        'cash_status': 'short',
      },
    })!;
    expect(close.title, 'Cierre completado');
    expect(close.lines, ['Ventas registradas 22.50', 'Caja Faltante', 'Diferencia -2.50']);
    expect(close.lines, isNot(contains('Ventas registradas 1')));
    expect(memoriaCardView({'event_type': 'unknown', 'local_time': '19:00', 'facts': {}}), isNull);
  });

  test('groups use the server business date across a UTC boundary', () {
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
          'event_type': 'note',
          'business_date': '2026-09-25',
          'local_time': '23:40',
          'facts': {},
        },
      ],
      businessToday: '2026-09-25',
      businessYesterday: '2026-09-24',
    );
    expect(groups.map((group) => group.label), ['Hoy', 'Ayer']);
    expect(groups.first.cards.single.title, 'Venta registrada');
    expect(groups.last.cards.single.title, 'Cierre completado');
    expect(
      memoriaDateLabel(
        businessDate: '2026-09-20',
        businessToday: '2026-09-25',
        businessYesterday: '2026-09-24',
      ),
      '20 de septiembre de 2026',
    );
  });

  testWidgets('empty Memoria uses the registered copy and one footer', (tester) async {
    await tester.pumpWidget(_app(_client(_payload(events: []))));
    await tester.pumpAndSettle();
    expect(find.text('La memoria factual se habilitará cuando existan eventos confirmados.'), findsNothing);
    expect(find.text(memoriaEmptyTitle), findsOneWidget);
    expect(find.text(memoriaEmptyBody), findsOneWidget);
    expect(find.text('No hubo actividad.'), findsNothing);
    expect(find.text(memoriaFooter, skipOffstage: false), findsOneWidget);
    expect(find.text('Ver anteriores'), findsNothing);
    expect(find.byType(TextField), findsNothing);
    expect(find.text('Corregir'), findsNothing);
    expect(find.text('Explicar'), findsNothing);
    expect(find.text('Olvidar'), findsNothing);
    expect(find.text('Ver evidencia'), findsNothing);
  });

  testWidgets('Memoria renders server cards and stops at a null cursor', (tester) async {
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
    expect(find.text('Venta registrada'), findsOneWidget);
    expect(find.text('22.50 · Efectivo'), findsOneWidget);
    expect(find.text('Cierre completado'), findsOneWidget);
    expect(find.text('Ventas registradas 22.50'), findsOneWidget);
    expect(find.text('Ventas registradas 1'), findsNothing);
    expect(find.text('Hoy'), findsOneWidget);
    expect(find.text('23:30'), findsWidgets);
    expect(find.text('Ver anteriores'), findsOneWidget);
    expect(find.textContaining('event_id'), findsNothing);
    await tester.tap(find.text('Ver anteriores'));
    await tester.pumpAndSettle();
    expect(find.text('Conteo de efectivo'), findsOneWidget);
    expect(find.widgetWithText(LumoStatusChip, 'Faltante'), findsOneWidget);
    expect(find.text('Ver anteriores'), findsNothing);
    expect(requests.last.queryParameters['before'], 'cursor-2');
    expect(find.text(memoriaFooter, skipOffstage: false), findsOneWidget);
  });

  testWidgets('close card uses gross sales and cash status is a chip', (tester) async {
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
    expect(find.text('Ventas registradas 22.50'), findsOneWidget);
    expect(find.text('Ventas registradas 1'), findsNothing);
    expect(find.text('Caja Faltante'), findsOneWidget);
    expect(find.text('Diferencia -2.50'), findsWidgets);
    expect(find.text('Esperado 22.50'), findsOneWidget);
    expect(find.text('Contado 20.00'), findsOneWidget);
    expect(find.widgetWithText(LumoStatusChip, 'Faltante'), findsOneWidget);
    expect(find.widgetWithText(LumoStatusChip, 'Cuadrado', skipOffstage: false), findsOneWidget);
    expect(find.widgetWithText(LumoStatusChip, 'Sobrante', skipOffstage: false), findsOneWidget);
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
