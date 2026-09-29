import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:lumo/api/lumo_api_client.dart';
import 'package:lumo/app/lumo_app.dart';
import 'package:lumo/core/env/app_config.dart';
import 'package:lumo/core/session/session_store.dart';
import 'package:lumo/features/onboarding/onboarding_page.dart';
import 'package:lumo/features/onboarding/startup.dart';
import 'package:lumo/lumo/generative_ui/renderer.dart';
import 'package:lumo/lumo/widgets/lumo_bottom_navigation.dart';

GenerativeUiContract _choice() {
  return const GenerativeUiContract(
    component: 'onboarding_choice',
    version: 1,
    data: {
      'field': 'currency',
      'options': ['MXN'],
    },
    actions: [],
    fallbackText: 'Elige la moneda',
  );
}

GenerativeUiContract _confirmation() {
  return const GenerativeUiContract(
    component: 'onboarding_confirmation',
    version: 1,
    data: {
      'name': 'Panadería',
      'currency': 'MXN',
      'timezone': 'America/Mexico_City',
      'enabled_payment_methods': ['cash', 'transfer'],
    },
    actions: [
      GenerativeUiAction(
        actionId: 'start_using_lumo',
        contextToken: 'ready',
        idempotencyKey: 'complete-1',
      ),
    ],
    fallbackText: 'Confirma para empezar',
  );
}

void main() {
  test('pre-tenant session routes to onboarding', () {
    expect(
      destinationForSession({'onboarding_status': 'not_started', 'next_required_field': 'business_name'}),
      StartupDestination.onboarding,
    );
    expect(shouldMountBusinessStream({'onboarding_status': 'not_started'}), isFalse);
  });

  test('in progress and ready_to_complete stay on onboarding', () {
    expect(
      destinationForSession({'onboarding_status': 'in_progress', 'next_required_field': 'timezone'}),
      StartupDestination.onboarding,
    );
    expect(
      destinationForSession({'onboarding_status': 'in_progress', 'next_required_field': 'ready_to_complete'}),
      StartupDestination.onboarding,
    );
    expect(shouldMountBusinessStream({'onboarding_status': 'in_progress'}), isFalse);
  });

  test('completed session opens inicio and may mount Business Stream', () {
    final session = {'onboarding_status': 'completed'};
    expect(destinationForSession(session), StartupDestination.inicio);
    expect(shouldMountBusinessStream(session), isTrue);
  });

  testWidgets('onboarding choice card renders options', (tester) async {
    await tester.pumpWidget(
      MaterialApp(home: OnboardingPage(cards: [_choice()])),
    );
    expect(find.byType(LumoBottomNavigation), findsNothing);
    expect(find.text('MXN'), findsOneWidget);
  });

  testWidgets('confirmation card renders summary and start_using_lumo', (tester) async {
    var started = false;
    await tester.pumpWidget(
      MaterialApp(
        home: OnboardingPage(
          prompt: 'Revisa tu negocio antes de empezar.',
          cards: [_confirmation()],
          onStartUsingLumo: () => started = true,
        ),
      ),
    );
    expect(find.text('Panadería'), findsOneWidget);
    expect(find.text('America/Mexico_City'), findsOneWidget);
    expect(find.text('cash, transfer'), findsOneWidget);
    await tester.tap(find.text('Empezar a usar Lumo'));
    await tester.pump();
    expect(started, isTrue);
  });

  test('free text at ready_to_complete is not a completion body', () {
    expect(onboardingApplyBody('sí, empecemos', 'ready_to_complete'), isNull);
    expect(onboardingApplyBody('Panadería', 'business_name'), {'name': 'Panadería'});
  });

  testWidgets('live onboarding renders confirmation from session and completes to Inicio', (tester) async {
    var streamCalls = 0;
    var lumoCalls = 0;
    final httpClient = MockClient((request) async {
      if (request.url.path == '/api/v1/session') {
        return http.Response(jsonEncode(_readySession()), 200);
      }
      if (request.url.path == '/api/v1/onboarding/apply') {
        final body = jsonDecode(request.body) as Map<String, dynamic>;
        expect(body['start_using_lumo'], isTrue);
        expect(body.containsKey('name'), isFalse);
        return http.Response(
          jsonEncode({
            'onboarding_status': 'completed',
            'next_required_field': null,
            'name': 'Panadería',
            'access_token': 'tenant-token',
            'ui': [],
          }),
          200,
        );
      }
      if (request.url.path == '/api/v1/lumo/messages' || request.url.path == '/api/v1/lumo/actions') {
        lumoCalls += 1;
        return http.Response(jsonEncode({'error': {'code': 'ONBOARDING_INCOMPLETE'}}), 409);
      }
      if (request.url.path == '/api/v1/business-stream/today') {
        streamCalls += 1;
        return http.Response(jsonEncode({'facts': []}), 200);
      }
      return http.Response('{}', 404);
    });
    await tester.pumpWidget(
      LumoApp(
        config: const AppConfig(env: 'test', apiBaseUrl: 'http://lumo.test'),
        apiClient: LumoApiClient(
          config: const AppConfig(env: 'test', apiBaseUrl: 'http://lumo.test'),
          session: SessionStore()..accessToken = 'tenant-token',
          httpClient: httpClient,
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Panadería'), findsOneWidget);
    expect(find.text('America/Mexico_City'), findsOneWidget);
    expect(find.text('Empezar a usar Lumo'), findsOneWidget);
    expect(find.byType(LumoBottomNavigation), findsNothing);
    expect(streamCalls, 0);
    expect(lumoCalls, 0);

    await tester.tap(find.text('Empezar a usar Lumo'));
    await tester.pumpAndSettle();
    expect(find.text('Inicio'), findsOneWidget);
    expect(find.byType(LumoBottomNavigation), findsOneWidget);
    expect(streamCalls, greaterThan(0));
  });
}

Map<String, dynamic> _readySession() {
  return {
    'onboarding_status': 'in_progress',
    'next_required_field': 'ready_to_complete',
    'actor': {'id': 'a', 'name': 'Ana'},
    'business': {
      'id': 'b',
      'name': 'Panadería',
      'currency': 'MXN',
      'timezone': 'America/Mexico_City',
      'enabled_payment_methods': ['cash', 'transfer'],
    },
    'ui': [
      {
        'component': 'onboarding_confirmation',
        'version': 1,
        'data': {
          'name': 'Panadería',
          'currency': 'MXN',
          'timezone': 'America/Mexico_City',
          'enabled_payment_methods': ['cash', 'transfer'],
        },
        'actions': [
          {
            'action_id': 'start_using_lumo',
            'option_id': null,
            'context_token': 'ready_to_complete',
            'idempotency_key': 'start_using_lumo',
          },
        ],
        'fallback_text': 'Panadería · MXN · America/Mexico_City',
      },
    ],
  };
}
