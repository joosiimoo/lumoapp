import 'package:flutter/material.dart';
import 'package:lumo/features/inicio/business_stream.dart';
import 'package:lumo/features/inicio/business_stream_panel.dart';
import 'package:lumo/lumo/generative_ui/renderer.dart';
import 'package:lumo/lumo/tokens.dart';
import 'package:lumo/lumo/typography.dart';
import 'package:lumo/lumo/widgets/lumo_mark.dart';
import 'package:lumo/lumo/widgets/lumo_messages.dart';
import 'package:timezone/data/latest.dart' as tzdata;
import 'package:timezone/timezone.dart' as tz;

class InicioTurn {
  const InicioTurn({
    required this.text,
    required this.fromUser,
    this.ui = const [],
    this.occurredAt,
  });

  factory InicioTurn.user(String text, {DateTime? occurredAt}) {
    return InicioTurn(text: text, fromUser: true, occurredAt: occurredAt);
  }

  factory InicioTurn.assistant(
    String text, [
    List<GenerativeUiContract> ui = const [],
    DateTime? occurredAt,
  ]) {
    return InicioTurn(text: text, fromUser: false, ui: ui, occurredAt: occurredAt);
  }

  final String text;
  final bool fromUser;
  final List<GenerativeUiContract> ui;
  final DateTime? occurredAt;
}

class InicioPage extends StatelessWidget {
  const InicioPage({
    super.key,
    this.messages = const [],
    this.businessName,
    this.onAction,
    this.disabledCardKeys = const {},
    this.removedCardKeys = const {},
    this.removedSaleItemIds = const {},
    this.busyCardKey,
    this.busyActionKey,
    this.stream,
    this.streamFailed = false,
    this.onRetryStream,
    this.scrollController,
    this.timezone,
  });

  final List<InicioTurn> messages;
  final String? businessName;
  final void Function(GenerativeUiContract contract, GenerativeUiAction action, {String? voidReason})? onAction;
  final Set<String> disabledCardKeys;
  final Set<String> removedCardKeys;
  final Set<String> removedSaleItemIds;
  final String? busyCardKey;
  final String? busyActionKey;
  final BusinessStream? stream;
  final bool streamFailed;
  final VoidCallback? onRetryStream;
  final ScrollController? scrollController;
  final String? timezone;

  @override
  Widget build(BuildContext context) {
    const renderer = GenerativeUIRenderer();
    final eyebrow = businessName == null || businessName!.trim().isEmpty
        ? 'LUMO'
        : 'LUMO · ${businessName!.trim()}'.toUpperCase();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(20, 24, 20, 0),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
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
              if (streamFailed || stream != null) ...[
                const SizedBox(height: 16),
                InicioOperationalHeader(
                  stream: stream,
                  failed: streamFailed,
                  onRetry: onRetryStream ?? () {},
                ),
              ],
            ],
          ),
        ),
        const SizedBox(height: 12),
        Expanded(
          child: ClipRect(
            child: ListView(
              key: const Key('inicio-transcript'),
              controller: scrollController,
              cacheExtent: 100000,
              padding: const EdgeInsets.fromLTRB(20, 0, 20, 16),
              children: [
                if (messages.isEmpty)
                  Text(
                    'Dile a Lumo qué vendiste. Prueba con 900gr zanahoria.',
                    style: LumoTypography.body,
                  ),
                for (final turn in messages) ...[
                  if (turn.fromUser)
                    LumoUserMessage(text: turn.text)
                  else if (turn.ui.isEmpty)
                    _timedAssistant(
                      child: LumoMessage(text: turn.text),
                      occurredAt: turn.occurredAt,
                    )
                  else
                    _timedAssistant(
                      child: _assistantCard(renderer, turn),
                      occurredAt: turn.occurredAt,
                    ),
                  const SizedBox(height: LumoSpacing.streamGap),
                ],
              ],
            ),
          ),
        ),
      ],
    );
  }

  Widget _timedAssistant({required Widget child, DateTime? occurredAt}) {
    final label = formatInicioEventTime(occurredAt, timezone: timezone);
    if (label == null) {
      return child;
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: LumoTypography.caption),
        const SizedBox(height: 4),
        child,
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
    final dayClosed = stream?.operatorState == 'closed';
    final removed = removedCardKeys.contains(cardKey);
    final chrome = UiActionChrome(
      hideFallback: true,
      disabled: disabledCardKeys.contains(cardKey) || busyCardKey == cardKey || dayClosed || removed,
      hideMutationActions: dayClosed || removed,
      markedRemoved: removed && contract.component == 'sale_item_added',
      removedSaleItemIds: removedSaleItemIds,
      loadingKey: busyCardKey == cardKey ? busyActionKey : null,
      onAction: onAction == null || dayClosed || removed
          ? null
          : (action, {voidReason}) => onAction!(contract, action, voidReason: voidReason),
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

String? formatInicioEventTime(DateTime? occurredAt, {String? timezone}) {
  if (occurredAt == null) {
    return null;
  }
  final local = _toZone(occurredAt, timezone);
  final hour = local.hour.toString().padLeft(2, '0');
  final minute = local.minute.toString().padLeft(2, '0');
  return '$hour:$minute';
}

bool _tzDatabaseReady = false;

void _ensureTzDatabase() {
  if (_tzDatabaseReady) {
    return;
  }
  tzdata.initializeTimeZones();
  _tzDatabaseReady = true;
}

DateTime _toZone(DateTime value, String? timezone) {
  if (timezone == null || timezone.isEmpty) {
    return value.toLocal();
  }
  _ensureTzDatabase();
  try {
    final location = tz.getLocation(timezone);
    return tz.TZDateTime.from(value.toUtc(), location);
  } on Object {
    return value.toLocal();
  }
}

String? productNameForRemove(GenerativeUiContract contract, GenerativeUiAction action) {
  if (contract.component == 'sale_item_added') {
    final name = '${contract.data['product_name'] ?? ''}'.trim();
    return name.isEmpty ? null : name;
  }
  if (contract.component == 'sale_summary') {
    final index = _removeActionIndex(contract, action);
    final items = List<dynamic>.from(contract.data['items'] as List? ?? const []);
    if (index < 0 || index >= items.length || items[index] is! Map) {
      return null;
    }
    final name = '${(items[index] as Map)['product_name'] ?? ''}'.trim();
    return name.isEmpty ? null : name;
  }
  return null;
}

String? saleItemIdForRemove(GenerativeUiContract contract, GenerativeUiAction action) {
  if (contract.component == 'sale_item_added') {
    final id = '${contract.data['sale_item_id'] ?? ''}'.trim();
    return id.isEmpty ? null : id;
  }
  if (contract.component == 'sale_summary') {
    final index = _removeActionIndex(contract, action);
    final items = List<dynamic>.from(contract.data['items'] as List? ?? const []);
    if (index < 0 || index >= items.length || items[index] is! Map) {
      return null;
    }
    final id = '${(items[index] as Map)['sale_item_id'] ?? ''}'.trim();
    return id.isEmpty ? null : id;
  }
  return null;
}

int _removeActionIndex(GenerativeUiContract contract, GenerativeUiAction action) {
  final removes = contractActionsForId(contract, removeItemActionId);
  return removes.indexWhere((item) => item.idempotencyKey == action.idempotencyKey);
}

String namedRemoveConfirmation(String productName, String serverText) {
  final trimmed = serverText.trim();
  if (trimmed.contains(productName)) {
    return trimmed;
  }
  if (trimmed.isEmpty) {
    return 'Quité $productName.';
  }
  return 'Quité $productName. $trimmed';
}
