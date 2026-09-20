import 'package:flutter/material.dart';
import 'package:lumo/lumo/widgets/lumo_messages.dart';
import 'package:lumo/lumo/widgets/lumo_scaffold.dart';

class OnboardingPage extends StatelessWidget {
  const OnboardingPage({super.key});

  @override
  Widget build(BuildContext context) {
    return const LumoScaffold(
      showTabBar: false,
      body: Padding(
        padding: EdgeInsets.fromLTRB(16, 32, 16, 16),
        child: LumoMessage(text: 'Onboarding llega en un cambio posterior.'),
      ),
    );
  }
}
