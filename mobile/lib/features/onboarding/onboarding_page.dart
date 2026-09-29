import 'package:flutter/material.dart';
import 'package:lumo/lumo/generative_ui/renderer.dart';
import 'package:lumo/lumo/widgets/lumo_card.dart';
import 'package:lumo/lumo/widgets/lumo_composer.dart';
import 'package:lumo/lumo/widgets/lumo_messages.dart';
import 'package:lumo/lumo/widgets/lumo_scaffold.dart';

class OnboardingPage extends StatefulWidget {
  const OnboardingPage({
    super.key,
    this.prompt = '¿Cómo se llama tu negocio?',
    this.cards = const [],
    this.onStartUsingLumo,
    this.onSend,
  });

  final String prompt;
  final List<GenerativeUiContract> cards;
  final VoidCallback? onStartUsingLumo;
  final ValueChanged<String>? onSend;

  @override
  State<OnboardingPage> createState() => _OnboardingPageState();
}

class _OnboardingPageState extends State<OnboardingPage> {
  final _composer = TextEditingController();

  @override
  void dispose() {
    _composer.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return LumoScaffold(
      showTabBar: false,
      footer: LumoComposer(
        controller: _composer,
        onSend: () {
          final text = _composer.text.trim();
          if (text.isEmpty) {
            return;
          }
          widget.onSend?.call(text);
          _composer.clear();
        },
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 24, 16, 16),
        children: [
          LumoMessage(text: widget.prompt),
          for (final card in widget.cards)
            Padding(
              padding: const EdgeInsets.only(top: 12),
              child: GenerativeUIRenderer().build(
                card,
                chrome: UiActionChrome(
                  onAction: (action) {
                    if (action.actionId == 'start_using_lumo') {
                      widget.onStartUsingLumo?.call();
                    }
                  },
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class OnboardingChoiceView extends StatelessWidget {
  const OnboardingChoiceView({super.key, required this.contract});

  final GenerativeUiContract contract;

  @override
  Widget build(BuildContext context) {
    final options = contract.data['options'];
    final labels = options is List ? options.map((item) => '$item').toList() : <String>[];
    return LumoCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          for (final label in labels)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Text(label),
            ),
        ],
      ),
    );
  }
}

class OnboardingConfirmationView extends StatelessWidget {
  const OnboardingConfirmationView({
    super.key,
    required this.contract,
    required this.chrome,
  });

  final GenerativeUiContract contract;
  final UiActionChrome chrome;

  @override
  Widget build(BuildContext context) {
    final data = contract.data;
    final methods = data['enabled_payment_methods'];
    final methodText = methods is List ? methods.join(', ') : '';
    return LumoCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('${data['name']}'),
          Text('${data['currency']}'),
          Text('${data['timezone']}'),
          Text(methodText),
          const SizedBox(height: 12),
          FilledButton(
            onPressed: chrome.disabled
                ? null
                : () {
                    final action = contract.actions.cast<GenerativeUiAction?>().firstWhere(
                          (item) => item?.actionId == 'start_using_lumo',
                          orElse: () => null,
                        );
                    if (action != null) {
                      chrome.onAction?.call(action);
                    }
                  },
            child: const Text('Empezar a usar Lumo'),
          ),
        ],
      ),
    );
  }
}
