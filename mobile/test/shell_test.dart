import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lumo/app/lumo_app.dart';
import 'package:lumo/core/env/app_config.dart';
import 'package:lumo/features/onboarding/onboarding_page.dart';
import 'package:lumo/lumo/widgets/lumo_bottom_navigation.dart';
import 'package:lumo/lumo/widgets/lumo_messages.dart';

void main() {
  testWidgets('four tabs are present', (tester) async {
    await tester.pumpWidget(
      LumoApp(config: const AppConfig(env: 'local', apiBaseUrl: 'http://127.0.0.1:8000')),
    );
    expect(find.text('Inicio'), findsOneWidget);
    expect(find.text('Hoy'), findsOneWidget);
    expect(find.text('Memoria'), findsOneWidget);
    expect(find.text('Negocio'), findsOneWidget);
  });

  testWidgets('user bubble is right aligned and assistant has no bubble', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: Column(
            children: [
              LumoUserMessage(text: '385 tarjeta'),
              LumoMessage(text: 'Listo'),
            ],
          ),
        ),
      ),
    );
    final user = tester.widget<Align>(find.byType(Align).first);
    expect(user.alignment, Alignment.centerRight);
    expect(find.byType(LumoMessage), findsOneWidget);
  });

  testWidgets('onboarding route hides the tab bar', (tester) async {
    await tester.pumpWidget(const MaterialApp(home: OnboardingPage()));
    expect(find.byType(LumoBottomNavigation), findsNothing);
    expect(find.text('Inicio'), findsNothing);
  });
}
