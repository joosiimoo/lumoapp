import 'package:flutter/material.dart';
import 'package:lumo/lumo/generative_ui/renderer.dart';
import 'package:lumo/lumo/tokens.dart';
import 'package:lumo/lumo/typography.dart';
import 'package:lumo/lumo/widgets/lumo_mark.dart';
import 'package:lumo/lumo/widgets/lumo_messages.dart';

class InicioTurn {
  const InicioTurn({
    required this.text,
    required this.fromUser,
    this.ui = const [],
  });

  factory InicioTurn.user(String text) => InicioTurn(text: text, fromUser: true);

  factory InicioTurn.assistant(String text, [List<GenerativeUiContract> ui = const []]) {
    return InicioTurn(text: text, fromUser: false, ui: ui);
  }

  final String text;
  final bool fromUser;
  final List<GenerativeUiContract> ui;
}

class InicioPage extends StatelessWidget {
  const InicioPage({
    super.key,
    this.messages = const [],
    this.businessName,
    this.onAction,
    this.disabledCardKeys = const {},
    this.busyCardKey,
    this.busyActionKey,
  });

  final List<InicioTurn> messages;
  final String? businessName;
  final void Function(GenerativeUiContract contract, GenerativeUiAction action)? onAction;
  final Set<String> disabledCardKeys;
  final String? busyCardKey;
  final String? busyActionKey;

  @override
  Widget build(BuildContext context) {
    const renderer = GenerativeUIRenderer();
    final eyebrow = businessName == null || businessName!.trim().isEmpty
        ? 'LUMO'
        : 'LUMO · ${businessName!.trim()}'.toUpperCase();
    return ListView(
      padding: const EdgeInsets.fromLTRB(20, 24, 20, 16),
      children: [
        Row(
          children: [
            const LumoMark(size: LumoSizes.markSm),
            const SizedBox(width: 8),
            Text(eyebrow, style: LumoTypography.eyebrow),
          ],
        ),
        const SizedBox(height: 12),
        ShaderMask(
          blendMode: BlendMode.srcIn,
          shaderCallback: (bounds) => LumoGradients.lumoTextGradient.createShader(bounds),
          child: Text('Buenos días', style: LumoTypography.displayGreeting.copyWith(color: Colors.white)),
        ),
        const SizedBox(height: 16),
        if (messages.isEmpty)
          Text(
            'Dile a Lumo qué vendiste. Prueba con 900gr zanahoria.',
            style: LumoTypography.body,
          ),
        for (final turn in messages) ...[
          if (turn.fromUser)
            LumoUserMessage(text: turn.text)
          else if (turn.ui.isEmpty)
            LumoMessage(text: turn.text)
          else
            _assistantCard(renderer, turn),
          const SizedBox(height: LumoSpacing.streamGap),
        ],
      ],
    );
  }

  Widget _assistantCard(GenerativeUIRenderer renderer, InicioTurn turn) {
    final contract = turn.ui.first;
    if (!renderer.render(contract).handled) {
      return LumoMessage(text: contract.fallbackText);
    }
    final hide = hideAssistantProse(turn.text, contract);
    final cardKey = uiCardKey(contract);
    final chrome = UiActionChrome(
      hideFallback: true,
      disabled: disabledCardKeys.contains(cardKey) || busyCardKey == cardKey,
      loadingKey: busyCardKey == cardKey ? busyActionKey : null,
      onAction: onAction == null ? null : (action) => onAction!(contract, action),
    );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (!hide) ...[
          Text(turn.text, style: LumoTypography.body),
          const SizedBox(height: 8),
        ],
        renderer.build(contract, chrome: chrome),
      ],
    );
  }
}

String uiCardKey(GenerativeUiContract contract) {
  final actionKeys = contract.actions.map((action) => action.idempotencyKey).join(',');
  final session = '${contract.data['sale_session_id'] ?? ''}';
  final day = '${contract.data['operational_day_id'] ?? ''}';
  final token = '${contract.data['confirmation_token'] ?? ''}';
  return '${contract.component}|$session|$day|$token|$actionKeys';
}
