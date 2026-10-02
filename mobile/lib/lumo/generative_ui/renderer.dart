import 'package:flutter/material.dart';
import 'package:lumo/lumo/tokens.dart';
import 'package:lumo/lumo/typography.dart';
import 'package:lumo/lumo/widgets/lumo_card.dart';
import 'package:lumo/lumo/widgets/lumo_buttons.dart';
import 'package:lumo/lumo/widgets/lumo_chips.dart';
import 'package:lumo/lumo/widgets/lumo_mark.dart';
import 'package:lumo/lumo/widgets/lumo_messages.dart';
import 'package:lumo/features/onboarding/onboarding_page.dart';
import 'package:lumo/shared/money_display.dart';

class GenerativeUiAction {
  const GenerativeUiAction({
    required this.actionId,
    this.optionId,
    required this.contextToken,
    required this.idempotencyKey,
  });

  final String actionId;
  final String? optionId;
  final String contextToken;
  final String idempotencyKey;

  factory GenerativeUiAction.fromJson(Map<String, dynamic> json) {
    return GenerativeUiAction(
      actionId: json['action_id'] as String,
      optionId: json['option_id'] as String?,
      contextToken: json['context_token'] as String,
      idempotencyKey: json['idempotency_key'] as String,
    );
  }
}

class GenerativeUiContract {
  const GenerativeUiContract({
    required this.component,
    required this.version,
    required this.data,
    required this.actions,
    required this.fallbackText,
  });

  final String component;
  final int version;
  final Map<String, dynamic> data;
  final List<GenerativeUiAction> actions;
  final String fallbackText;

  factory GenerativeUiContract.fromJson(Map<String, dynamic> json) {
    return GenerativeUiContract(
      component: json['component'] as String,
      version: json['version'] as int,
      data: Map<String, dynamic>.from(json['data'] as Map? ?? {}),
      actions: [
        for (final item in (json['actions'] as List? ?? []))
          GenerativeUiAction.fromJson(Map<String, dynamic>.from(item as Map)),
      ],
      fallbackText: json['fallback_text'] as String,
    );
  }
}

class GenerativeUiRenderResult {
  const GenerativeUiRenderResult({required this.text, this.handled = false});

  final String text;
  final bool handled;
}

const uiActionLabels = <String, String>{
  'sale.pay.cash@1': 'Efectivo',
  'sale.pay.card@1': 'Tarjeta',
  'sale.pay.transfer@1': 'Transferencia',
  'closing.request@1': 'Revisar cierre',
  'closing.confirm@1': 'Confirmar cierre',
};

const removeItemActionId = 'sale.remove_item@1';
const voidRequestActionId = 'sale.void.request@1';
const voidConfirmActionId = 'sale.void.confirm@1';

List<GenerativeUiAction> contractActionsForId(GenerativeUiContract contract, String actionId) {
  return [
    for (final action in contract.actions)
      if (action.actionId == actionId) action,
  ];
}

GenerativeUiAction? firstContractActionForId(GenerativeUiContract contract, String actionId) {
  for (final action in contract.actions) {
    if (action.actionId == actionId) {
      return action;
    }
  }
  return null;
}

bool hideAssistantProse(String text, GenerativeUiContract contract) {
  if (text.trim() != contract.fallbackText.trim()) {
    return false;
  }
  const listed = {
    'sale_item_added',
    'sale_summary',
    'sale_confirmed',
    'operational_day_summary',
    'daily_close_confirmed',
    'next_best_action',
  };
  if (listed.contains(contract.component)) {
    return true;
  }
  return contract.component == 'daily_close_preparation' && contract.fallbackText.startsWith('Cierre ');
}

class UiActionChrome {
  const UiActionChrome({
    this.onAction,
    this.disabled = false,
    this.loadingKey,
    this.hideFallback = false,
    this.hideMutationActions = false,
    this.markedRemoved = false,
    this.removedSaleItemIds = const {},
  });

  final void Function(GenerativeUiAction action, {String? voidReason})? onAction;
  final bool disabled;
  final String? loadingKey;
  final bool hideFallback;

  /// When true, sale mutation controls are omitted (closed operational day).
  final bool hideMutationActions;

  /// When true, a historical `sale_item_added` card was successfully removed.
  final bool markedRemoved;

  /// Historical summary rows whose `sale_item_id` was successfully removed.
  final Set<String> removedSaleItemIds;

  bool actionEnabled(GenerativeUiAction action) {
    return !disabled && !hideMutationActions && onAction != null && loadingKey == null;
  }

  bool actionLoading(GenerativeUiAction action) {
    return loadingKey == action.idempotencyKey;
  }

  bool itemRemoved(String? saleItemId) {
    if (saleItemId == null || saleItemId.isEmpty) {
      return false;
    }
    return removedSaleItemIds.contains(saleItemId);
  }
}

class GenerativeUIRenderer {
  const GenerativeUIRenderer();

  static const known = <String, int>{
    'sale_item_added': 1,
    'sale_summary': 1,
    'sale_confirmed': 1,
    'operational_day_summary': 1,
    'daily_close_preparation': 1,
    'daily_close_confirmed': 1,
    'next_best_action': 1,
    'onboarding_choice': 1,
    'onboarding_confirmation': 1,
  };

  GenerativeUiRenderResult render(GenerativeUiContract contract) {
    final version = known[contract.component];
    if (version == null || version != contract.version) {
      return GenerativeUiRenderResult(text: contract.fallbackText);
    }
    return GenerativeUiRenderResult(text: contract.fallbackText, handled: true);
  }

  bool canRunActions(GenerativeUiContract contract) {
    return render(contract).handled;
  }

  Widget build(GenerativeUiContract contract, {UiActionChrome chrome = const UiActionChrome()}) {
    final result = render(contract);
    if (!result.handled) {
      return LumoMessage(text: contract.fallbackText);
    }
    if (contract.component == 'sale_summary') {
      return SaleSummaryView(contract: contract, chrome: chrome);
    }
    if (contract.component == 'sale_confirmed') {
      return SaleConfirmedView(contract: contract, chrome: chrome);
    }
    if (contract.component == 'operational_day_summary') {
      return OperationalDaySummaryView(contract: contract, chrome: chrome);
    }
    if (contract.component == 'daily_close_preparation') {
      return DailyClosePreparationView(contract: contract, chrome: chrome);
    }
    if (contract.component == 'daily_close_confirmed') {
      return DailyCloseConfirmedView(contract: contract, chrome: chrome);
    }
    if (contract.component == 'next_best_action') {
      return NextBestActionView(contract: contract, chrome: chrome);
    }
    if (contract.component == 'onboarding_choice') {
      return OnboardingChoiceView(contract: contract);
    }
    if (contract.component == 'onboarding_confirmation') {
      return OnboardingConfirmationView(contract: contract, chrome: chrome);
    }
    return SaleItemAddedView(contract: contract, chrome: chrome);
  }
}

class UiActionBar extends StatelessWidget {
  const UiActionBar({super.key, required this.actions, required this.chrome});

  final List<GenerativeUiAction> actions;
  final UiActionChrome chrome;

  @override
  Widget build(BuildContext context) {
    final visible = [
      for (final action in actions)
        if (uiActionLabels.containsKey(action.actionId)) action,
    ];
    if (chrome.hideMutationActions || visible.isEmpty) {
      return const SizedBox.shrink();
    }
    return Padding(
      padding: const EdgeInsets.only(top: 12),
      child: Wrap(
        spacing: 8,
        runSpacing: 8,
        children: [
          for (final action in visible)
            _ActionPill(
              label: uiActionLabels[action.actionId]!,
              loading: chrome.loadingKey == action.idempotencyKey,
              enabled: chrome.actionEnabled(action),
              onPressed: () => chrome.onAction?.call(action),
            ),
        ],
      ),
    );
  }
}

class UiSecondaryActionButton extends StatelessWidget {
  const UiSecondaryActionButton({
    super.key,
    required this.label,
    required this.action,
    required this.chrome,
  });

  final String label;
  final GenerativeUiAction action;
  final UiActionChrome chrome;

  @override
  Widget build(BuildContext context) {
    final loading = chrome.actionLoading(action);
    final enabled = chrome.actionEnabled(action);
    if (chrome.hideMutationActions) {
      return const SizedBox.shrink();
    }
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: enabled ? () => chrome.onAction?.call(action) : null,
        borderRadius: BorderRadius.circular(LumoRadius.pill),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 4),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (loading) ...[
                const SizedBox(
                  width: 12,
                  height: 12,
                  child: CircularProgressIndicator(strokeWidth: 2),
                ),
                const SizedBox(width: 6),
              ],
              Text(
                label,
                style: LumoTypography.buttonSecondary.copyWith(
                  color: enabled ? LumoColors.primary : LumoColors.mutedForeground,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _ActionPill extends StatelessWidget {
  const _ActionPill({
    required this.label,
    required this.loading,
    required this.enabled,
    required this.onPressed,
  });

  final String label;
  final bool loading;
  final bool enabled;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: enabled ? LumoColors.primary : LumoColors.muted,
      borderRadius: BorderRadius.circular(LumoRadius.pill),
      child: InkWell(
        onTap: enabled ? onPressed : null,
        borderRadius: BorderRadius.circular(LumoRadius.pill),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (loading) ...[
                const SizedBox(
                  width: 14,
                  height: 14,
                  child: CircularProgressIndicator(strokeWidth: 2),
                ),
                const SizedBox(width: 8),
              ],
              Text(
                label,
                style: LumoTypography.buttonSecondary.copyWith(
                  color: enabled ? LumoColors.primaryForeground : LumoColors.mutedForeground,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class SaleItemAddedView extends StatelessWidget {
  const SaleItemAddedView({super.key, required this.contract, this.chrome = const UiActionChrome()});

  final GenerativeUiContract contract;
  final UiActionChrome chrome;

  @override
  Widget build(BuildContext context) {
    final data = contract.data;
    final productName = '${data['product_name'] ?? ''}';
    final quantity = '${data['quantity_normalized'] ?? ''}';
    final unit = '${data['unit_normalized'] ?? ''}';
    final unitPrice = SaleItemAddedView.formatAmount(data['unit_price']);
    final lineTotal = SaleItemAddedView.formatAmount(data['line_total']);
    final sessionCount = '${data['session_item_count'] ?? ''}';
    final sessionTotal = SaleItemAddedView.formatAmount(data['session_total']);
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Padding(
          padding: EdgeInsets.only(top: 4),
          child: LumoMark(),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (!chrome.hideFallback) ...[
                Text(contract.fallbackText, style: LumoTypography.body),
                const SizedBox(height: 8),
              ],
              Semantics(
                label: chrome.hideFallback ? contract.fallbackText : null,
                child: LumoCard(
                padding: const EdgeInsets.fromLTRB(16, 10, 16, 10),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    if (chrome.markedRemoved) ...[
                      const Align(
                        alignment: Alignment.centerLeft,
                        child: LumoStatusChip(label: 'Quitado'),
                      ),
                      const SizedBox(height: 8),
                    ],
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.center,
                      children: [
                        Container(
                          width: LumoSizes.thumbSm,
                          height: LumoSizes.thumbSm,
                          alignment: Alignment.center,
                          decoration: const BoxDecoration(
                            color: LumoColors.accent,
                            borderRadius: BorderRadius.all(Radius.circular(LumoRadius.thumb)),
                          ),
                          child: Text(
                            productName.isEmpty ? '' : productName[0],
                            style: LumoTypography.cardTitle.copyWith(color: LumoColors.accentForeground),
                          ),
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                productName,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: LumoTypography.cardTitle,
                              ),
                              Text(
                                '$quantity ${SaleItemAddedView.displayUnit(unit)} · $unitPrice/${SaleItemAddedView.displayUnit(unit)}',
                                style: LumoTypography.caption,
                              ),
                              if (SaleItemAddedView.adjustedPriceCaption(data) != null)
                                Text(
                                  SaleItemAddedView.adjustedPriceCaption(data)!,
                                  style: LumoTypography.caption,
                                ),
                            ],
                          ),
                        ),
                        Text(lineTotal, style: LumoTypography.metricSm),
                      ],
                    ),
                    if (sessionCount.isNotEmpty || sessionTotal.isNotEmpty) ...[
                      const SizedBox(height: 8),
                      Text(
                        [
                          if (sessionCount.isNotEmpty)
                            '$sessionCount ${sessionCount == '1' ? 'artículo' : 'artículos'}',
                          if (sessionTotal.isNotEmpty) sessionTotal,
                        ].join(' · '),
                        style: LumoTypography.caption,
                      ),
                    ],
                    if (firstContractActionForId(contract, removeItemActionId) != null &&
                        !chrome.hideMutationActions &&
                        !chrome.markedRemoved) ...[
                      const SizedBox(height: 8),
                      Align(
                        alignment: Alignment.centerLeft,
                        child: UiSecondaryActionButton(
                          label: 'Quitar',
                          action: firstContractActionForId(contract, removeItemActionId)!,
                          chrome: chrome,
                        ),
                      ),
                    ],
                  ],
                ),
              ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  static String displayUnit(String canonical) {
    switch (canonical) {
      case 'kilogram':
        return 'kg';
      case 'gram':
        return 'g';
      case 'unit':
        return 'unidad';
      case 'package':
        return 'paquete';
      default:
        return canonical;
    }
  }

  static String? adjustedPriceCaption(Map<dynamic, dynamic> data) {
    final prior = data['catalog_unit_price'];
    if (prior is! Map) {
      return null;
    }
    final amount = formatAmount(prior);
    if (amount.isEmpty) {
      return null;
    }
    final unit = displayUnit('${data['unit_normalized'] ?? ''}');
    return 'Precio ajustado · antes $amount/$unit';
  }

  static String formatAmount(Object? value) {
    if (value is Map) {
      return MoneyDisplay.format(
        amount: '${value['amount'] ?? ''}',
        currency: '${value['currency'] ?? 'MXN'}',
      );
    }
    return '';
  }
}

class SaleSummaryView extends StatelessWidget {
  const SaleSummaryView({super.key, required this.contract, this.chrome = const UiActionChrome()});

  final GenerativeUiContract contract;
  final UiActionChrome chrome;

  @override
  Widget build(BuildContext context) {
    final data = contract.data;
    final items = List<dynamic>.from(data['items'] as List? ?? const []);
    final removeActions = contractActionsForId(contract, removeItemActionId);
    final count = '${data['item_count'] ?? ''}';
    final total = SaleItemAddedView.formatAmount(data['total']);
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Padding(
          padding: EdgeInsets.only(top: 4),
          child: LumoMark(),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (!chrome.hideFallback) ...[
                Text(contract.fallbackText, style: LumoTypography.body),
                const SizedBox(height: 8),
              ],
              Semantics(
                label: chrome.hideFallback ? contract.fallbackText : null,
                child: LumoCard(
                padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    if (!chrome.hideMutationActions) ...[
                      const Align(
                        alignment: Alignment.centerLeft,
                        child: LumoStatusChip(label: 'Lista para cobrar'),
                      ),
                      const SizedBox(height: 10),
                    ],
                    for (var index = 0; index < items.length; index++)
                      _itemRow(
                        Map<String, dynamic>.from(items[index] as Map),
                        removeAction: chrome.hideMutationActions
                            ? null
                            : (index < removeActions.length ? removeActions[index] : null),
                        chrome: chrome,
                      ),
                    const SizedBox(height: 8),
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            '$count ${count == '1' ? 'artículo' : 'artículos'}',
                            style: LumoTypography.caption,
                          ),
                        ),
                        Text(total, style: LumoTypography.metricSm),
                      ],
                    ),
                    if (!chrome.hideMutationActions &&
                        contract.actions.any((action) => uiActionLabels.containsKey(action.actionId))) ...[
                      const SizedBox(height: 12),
                      Text('¿Cómo pagó?', style: LumoTypography.cardTitle),
                      UiActionBar(actions: contract.actions, chrome: chrome),
                    ],
                  ],
                ),
              ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  static Widget _itemRow(
    Map<String, dynamic> item, {
    GenerativeUiAction? removeAction,
    UiActionChrome chrome = const UiActionChrome(),
  }) {
    final productName = '${item['product_name'] ?? ''}';
    final saleItemId = '${item['sale_item_id'] ?? ''}';
    final removed = chrome.itemRemoved(saleItemId);
    final quantity = '${item['quantity_normalized'] ?? ''}';
    final unit = SaleItemAddedView.displayUnit('${item['unit_normalized'] ?? ''}');
    final unitPrice = SaleItemAddedView.formatAmount(item['unit_price']);
    final lineTotal = SaleItemAddedView.formatAmount(item['line_total']);
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (removed) ...[
                  const Align(
                    alignment: Alignment.centerLeft,
                    child: LumoStatusChip(label: 'Quitado'),
                  ),
                  const SizedBox(height: 4),
                ],
                Text(
                  productName,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: LumoTypography.cardTitle,
                ),
                Text(
                  '$quantity $unit · $unitPrice/$unit',
                  style: LumoTypography.caption,
                ),
                if (SaleItemAddedView.adjustedPriceCaption(item) != null)
                  Text(
                    SaleItemAddedView.adjustedPriceCaption(item)!,
                    style: LumoTypography.caption,
                  ),
                if (removeAction != null && !removed)
                  UiSecondaryActionButton(
                    label: 'Quitar',
                    action: removeAction,
                    chrome: chrome,
                  ),
              ],
            ),
          ),
          Text(lineTotal, style: LumoTypography.metricSm),
        ],
      ),
    );
  }
}

class SaleVoidImpactView {
  static List<String> impactLines(Map<String, dynamic>? impact) {
    if (impact == null) {
      return const [];
    }
    final before = Map<String, dynamic>.from(impact['before'] as Map? ?? const {});
    final after = Map<String, dynamic>.from(impact['after'] as Map? ?? const {});
    final lines = <String>[];
    void pair(String label, String key, {String? format}) {
      final left = _impactValue(before, key, format: format);
      final right = _impactValue(after, key, format: format);
      if (left.isEmpty && right.isEmpty) {
        return;
      }
      lines.add('$label: $left → $right');
    }

    pair('Ventas del día', 'sale_count', format: 'count');
    pair('Total vendido', 'gross_sales_total', format: 'money');
    pair('Efectivo esperado', 'expected_cash', format: 'money');
    if (before.containsKey('cash_difference') || after.containsKey('cash_difference')) {
      pair('Diferencia de caja', 'cash_difference', format: 'money');
    }
    if (before.containsKey('cash_status') || after.containsKey('cash_status')) {
      pair('Estado de caja', 'cash_status', format: 'cash_status');
    }
    return lines;
  }

  static String _impactValue(Map<String, dynamic> side, String key, {String? format}) {
    final value = side[key];
    if (value == null) {
      return '';
    }
    if (format == 'count') {
      return '$value';
    }
    if (format == 'cash_status') {
      return DailyClosePreparationView.statusLabel('$value');
    }
    return SaleItemAddedView.formatAmount(value);
  }
}

class SaleVoidConfirmationPanel extends StatefulWidget {
  const SaleVoidConfirmationPanel({
    super.key,
    required this.impact,
    required this.confirmAction,
    required this.chrome,
  });

  final Map<String, dynamic> impact;
  final GenerativeUiAction confirmAction;
  final UiActionChrome chrome;

  @override
  State<SaleVoidConfirmationPanel> createState() => _SaleVoidConfirmationPanelState();
}

class _SaleVoidConfirmationPanelState extends State<SaleVoidConfirmationPanel> {
  final _reasonController = TextEditingController();

  @override
  void dispose() {
    _reasonController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final reason = _reasonController.text.trim();
    final lines = SaleVoidImpactView.impactLines(widget.impact);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const SizedBox(height: 12),
        Text('Confirmar anulación', style: LumoTypography.cardTitle),
        const SizedBox(height: 8),
        for (final line in lines)
          Padding(
            padding: const EdgeInsets.only(bottom: 4),
            child: Text(line, style: LumoTypography.body),
          ),
        const SizedBox(height: 8),
        TextField(
          controller: _reasonController,
          onChanged: (_) => setState(() {}),
          decoration: const InputDecoration(
            hintText: 'Motivo de la anulación',
            border: OutlineInputBorder(),
          ),
        ),
        const SizedBox(height: 12),
        LumoPrimaryButton(
          label: 'Anular venta',
          enabled: reason.isNotEmpty && widget.chrome.actionEnabled(widget.confirmAction),
          onPressed: reason.isEmpty
              ? null
              : () => widget.chrome.onAction?.call(widget.confirmAction, voidReason: reason),
        ),
      ],
    );
  }
}

class SaleConfirmedView extends StatelessWidget {
  const SaleConfirmedView({super.key, required this.contract, this.chrome = const UiActionChrome()});

  final GenerativeUiContract contract;
  final UiActionChrome chrome;

  @override
  Widget build(BuildContext context) {
    final data = contract.data;
    final status = '${data['status'] ?? 'confirmed'}';
    final voided = status == 'voided';
    final count = '${data['item_count'] ?? ''}';
    final total = SaleItemAddedView.formatAmount(data['total']);
    final payment = Map<String, dynamic>.from(data['payment'] as Map? ?? const {});
    final methodLabel = SaleConfirmedView.displayMethod('${payment['method'] ?? ''}');
    final items = List<dynamic>.from(data['items'] as List? ?? const []);
    final voidRequest =
        voided || chrome.hideMutationActions ? null : firstContractActionForId(contract, voidRequestActionId);
    final voidConfirm =
        chrome.hideMutationActions ? null : firstContractActionForId(contract, voidConfirmActionId);
    final impact = data['impact'] is Map ? Map<String, dynamic>.from(data['impact'] as Map) : null;
    final voidReason = '${data['void_reason'] ?? ''}'.trim();
    final transactionNumber = SaleConfirmedView.displayTransactionNumber(data['transaction_number']);
    final originalNumber = SaleConfirmedView.displayTransactionNumber(data['original_transaction_number']);
    final String? reference = transactionNumber == null
        ? null
        : (voided && originalNumber != null ? '$transactionNumber · Anula $originalNumber' : transactionNumber);
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Padding(
          padding: EdgeInsets.only(top: 4),
          child: LumoMark(),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (!chrome.hideFallback) ...[
                Text(contract.fallbackText, style: LumoTypography.body),
                const SizedBox(height: 8),
              ],
              Semantics(
                label: chrome.hideFallback ? contract.fallbackText : null,
                child: LumoCard(
                padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Align(
                      alignment: Alignment.centerLeft,
                      child: LumoStatusChip(label: voided ? 'Venta anulada' : 'Venta registrada'),
                    ),
                    if (reference != null) ...[
                      const SizedBox(height: 4),
                      Text(reference, style: LumoTypography.caption),
                    ],
                    const SizedBox(height: 10),
                    for (final raw in items) SaleSummaryView._itemRow(Map<String, dynamic>.from(raw as Map)),
                    const SizedBox(height: 8),
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            '$count ${count == '1' ? 'artículo' : 'artículos'}',
                            style: LumoTypography.caption,
                          ),
                        ),
                        Text(total, style: LumoTypography.metricSm),
                      ],
                    ),
                    const SizedBox(height: 8),
                    Text('Pago $methodLabel', style: LumoTypography.cardTitle),
                    if (voided && voidReason.isNotEmpty) ...[
                      const SizedBox(height: 8),
                      Text('Motivo: $voidReason', style: LumoTypography.caption),
                    ],
                    if (voidRequest != null) ...[
                      const SizedBox(height: 8),
                      Align(
                        alignment: Alignment.centerLeft,
                        child: UiSecondaryActionButton(
                          label: 'Anular',
                          action: voidRequest,
                          chrome: chrome,
                        ),
                      ),
                    ],
                    if (voidConfirm != null && impact != null)
                      SaleVoidConfirmationPanel(
                        impact: impact,
                        confirmAction: voidConfirm,
                        chrome: chrome,
                      ),
                  ],
                ),
              ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  static final _transactionNumberPattern = RegExp(r'^TRX-[0-9]+$');

  /// Server-issued reference only; anything that is not `TRX-<digits>` is ignored.
  static String? displayTransactionNumber(Object? value) {
    return value is String && _transactionNumberPattern.hasMatch(value) ? value : null;
  }

  static String displayMethod(String method) {
    switch (method) {
      case 'cash':
        return 'Efectivo';
      case 'card':
        return 'Tarjeta';
      case 'transfer':
        return 'Transferencia';
      default:
        return method;
    }
  }
}

class OperationalDaySummaryView extends StatelessWidget {
  const OperationalDaySummaryView({super.key, required this.contract, this.chrome = const UiActionChrome()});

  final GenerativeUiContract contract;
  final UiActionChrome chrome;

  @override
  Widget build(BuildContext context) {
    final data = contract.data;
    final businessDate = displayBusinessDate('${data['business_date'] ?? ''}');
    final count = '${data['sale_count'] ?? '0'}';
    final currency = '${data['currency'] ?? 'MXN'}';
    final gross = formatDecimal(data['gross_sales_total'], currency);
    final cash = formatDecimal(data['cash_total'], currency);
    final card = formatDecimal(data['card_total'], currency);
    final transfer = formatDecimal(data['transfer_total'], currency);
    final noun = count == '1' ? 'venta' : 'ventas';
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Padding(
          padding: EdgeInsets.only(top: 4),
          child: LumoMark(),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: LumoSizes.contentMaxWidth),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (!chrome.hideFallback) ...[
                  Text(contract.fallbackText, style: LumoTypography.body),
                  const SizedBox(height: 8),
                ],
                Semantics(
                  label: chrome.hideFallback ? contract.fallbackText : null,
                  child: LumoCard(
                  padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Align(
                        alignment: Alignment.centerLeft,
                        child: LumoStatusChip(label: businessDate),
                      ),
                      const SizedBox(height: 10),
                      Text('$count $noun · $gross', style: LumoTypography.metricSm),
                      if ('${data['status'] ?? ''}' == 'closed') ...[
                        const SizedBox(height: 8),
                        const Align(
                          alignment: Alignment.centerLeft,
                          child: LumoStatusChip(label: 'Cerrado'),
                        ),
                      ],
                      const SizedBox(height: 8),
                      Text('Efectivo $cash', style: LumoTypography.caption),
                      Text('Tarjeta $card', style: LumoTypography.caption),
                      Text('Transferencia $transfer', style: LumoTypography.caption),
                    ],
                  ),
                ),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }

  static String displayBusinessDate(String value) {
    final parts = value.split('-');
    if (parts.length != 3) {
      return value;
    }
    final year = parts[0];
    final month = parts[1];
    final day = parts[2];
    if (year.length != 4 || month.length != 2 || day.length != 2) {
      return value;
    }
    return '$year-$month-$day';
  }

  static String formatDecimal(Object? value, String currency) {
    if (value is! String || value.isEmpty) {
      return '';
    }
    return MoneyDisplay.format(amount: value, currency: currency);
  }
}

class DailyClosePreparationView extends StatelessWidget {
  const DailyClosePreparationView({super.key, required this.contract, this.chrome = const UiActionChrome()});

  final GenerativeUiContract contract;
  final UiActionChrome chrome;

  @override
  Widget build(BuildContext context) {
    final data = contract.data;
    final status = '${data['cash_status'] ?? ''}';
    final businessDate = OperationalDaySummaryView.displayBusinessDate('${data['business_date'] ?? ''}');
    final expected = formatMoney(data['expected_cash']);
    final counted = formatMoney(data['counted_cash']);
    final notCounted = status == 'not_counted';
    final saleCount = '${data['sale_count'] ?? ''}';
    final saleLabel = saleCount == '1' ? '1 venta' : '$saleCount ventas';
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Padding(
          padding: EdgeInsets.only(top: 4),
          child: LumoMark(),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: LumoSizes.contentMaxWidth),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (!chrome.hideFallback) ...[
                  Text(contract.fallbackText, style: LumoTypography.body),
                  const SizedBox(height: 8),
                ],
                Semantics(
                  label: chrome.hideFallback ? contract.fallbackText : null,
                  child: LumoCard(
                  padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Align(
                        alignment: Alignment.centerLeft,
                        child: LumoStatusChip(label: statusLabel(status)),
                      ),
                      const SizedBox(height: 10),
                      Text('Cierre $businessDate', style: LumoTypography.caption),
                      if (saleCount.isNotEmpty) Text(saleLabel, style: LumoTypography.caption),
                      const SizedBox(height: 8),
                      _metricRow('EFECTIVO ESPERADO', expected),
                      if (notCounted)
                        Padding(
                          padding: const EdgeInsets.only(top: 8),
                          child: Text('Falta contar efectivo', style: LumoTypography.cardTitle),
                        )
                      else ...[
                        _metricRow('CONTADO', counted),
                        _metricRow('DIFERENCIA', displayDifference(status, data['cash_difference'])),
                      ],
                      UiActionBar(actions: contract.actions, chrome: chrome),
                    ],
                  ),
                ),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }

  static Widget _metricRow(String label, String value) {
    return Padding(
      padding: const EdgeInsets.only(top: 6),
      child: Row(
        children: [
          Expanded(child: Text(label, style: LumoTypography.sectionLabel)),
          Text(value, style: LumoTypography.metricSm),
        ],
      ),
    );
  }

  static String statusLabel(String status) {
    switch (status) {
      case 'not_counted':
        return 'Sin contar';
      case 'balanced':
        return 'Caja cuadrada';
      case 'over':
        return 'Sobrante';
      case 'short':
        return 'Faltante';
      default:
        return status;
    }
  }

  /// Formats the server decimal string. The sign is moved in front of the symbol; no amount is
  /// derived, compared, or summed on the client.
  static String formatMoney(Object? value) {
    if (value is! Map) {
      return '';
    }
    final amount = '${value['amount'] ?? ''}';
    final currency = '${value['currency'] ?? 'MXN'}';
    if (amount.isEmpty) {
      return '';
    }
    if (amount.startsWith('-')) {
      return '-${MoneyDisplay.format(amount: amount.substring(1), currency: currency)}';
    }
    return MoneyDisplay.format(amount: amount, currency: currency);
  }

  static String displayDifference(String status, Object? value) {
    final formatted = formatMoney(value);
    if (status == 'over' && formatted.isNotEmpty && !formatted.startsWith('+') && !formatted.startsWith('-')) {
      return '+$formatted';
    }
    return formatted;
  }
}

class DailyCloseConfirmedView extends StatelessWidget {
  const DailyCloseConfirmedView({super.key, required this.contract, this.chrome = const UiActionChrome()});

  final GenerativeUiContract contract;
  final UiActionChrome chrome;

  @override
  Widget build(BuildContext context) {
    final data = contract.data;
    final businessDate = OperationalDaySummaryView.displayBusinessDate('${data['business_date'] ?? ''}');
    final closedAt = '${data['closed_at'] ?? ''}';
    final gross = DailyClosePreparationView.formatMoney(data['gross_sales_total']);
    final expected = DailyClosePreparationView.formatMoney(data['expected_cash']);
    final counted = DailyClosePreparationView.formatMoney(data['counted_cash']);
    final difference = DailyClosePreparationView.formatMoney(data['cash_difference']);
    final status = DailyClosePreparationView.statusLabel('${data['cash_status'] ?? ''}');
    final saleCount = '${data['sale_count'] ?? ''}';
    final saleLabel = saleCount == '1' ? '1 venta' : '$saleCount ventas';
    final reference = SaleConfirmedView.displayTransactionNumber(data['transaction_number']);
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Padding(
          padding: EdgeInsets.only(top: 4),
          child: LumoMark(),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: LumoSizes.contentMaxWidth),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (!chrome.hideFallback) ...[
                  Text(contract.fallbackText, style: LumoTypography.body),
                  const SizedBox(height: 8),
                ],
                Semantics(
                  label: chrome.hideFallback ? contract.fallbackText : null,
                  child: LumoCard(
                  padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      const Align(
                        alignment: Alignment.centerLeft,
                        child: LumoStatusChip(label: 'Cierre confirmado'),
                      ),
                      if (reference != null) ...[
                        const SizedBox(height: 4),
                        Text(reference, style: LumoTypography.caption),
                      ],
                      const SizedBox(height: 10),
                      Text('Cierre $businessDate', style: LumoTypography.caption),
                      if (saleCount.isNotEmpty) Text(saleLabel, style: LumoTypography.caption),
                      Text(closedAt, style: LumoTypography.caption),
                      DailyClosePreparationView._metricRow('VENTAS', gross),
                      DailyClosePreparationView._metricRow('EFECTIVO ESPERADO', expected),
                      DailyClosePreparationView._metricRow('CONTADO', counted),
                      DailyClosePreparationView._metricRow('DIFERENCIA', difference),
                      const SizedBox(height: 8),
                      Text(status, style: LumoTypography.cardTitle),
                    ],
                  ),
                ),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

class NextBestActionView extends StatelessWidget {
  const NextBestActionView({super.key, required this.contract, required this.chrome});

  final GenerativeUiContract contract;
  final UiActionChrome chrome;

  @override
  Widget build(BuildContext context) {
    final title = '${contract.data['title'] ?? ''}';
    final reason = '${contract.data['reason'] ?? ''}';
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const LumoMark(),
        const SizedBox(width: 8),
        Expanded(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: LumoSizes.contentMaxWidth),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (!chrome.hideFallback) ...[
                  Text(contract.fallbackText, style: LumoTypography.body),
                  const SizedBox(height: 8),
                ],
                Semantics(
                  label: chrome.hideFallback ? contract.fallbackText : null,
                  child: LumoCard(
                    padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Text(title, style: LumoTypography.cardTitle),
                        const SizedBox(height: 8),
                        Text(reason, style: LumoTypography.body),
                        UiActionBar(actions: contract.actions, chrome: chrome),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}
