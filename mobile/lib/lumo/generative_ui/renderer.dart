import 'package:flutter/material.dart';
import 'package:lumo/lumo/tokens.dart';
import 'package:lumo/lumo/typography.dart';
import 'package:lumo/lumo/widgets/lumo_card.dart';
import 'package:lumo/lumo/widgets/lumo_chips.dart';
import 'package:lumo/lumo/widgets/lumo_mark.dart';
import 'package:lumo/lumo/widgets/lumo_messages.dart';
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

class GenerativeUIRenderer {
  const GenerativeUIRenderer();

  static const known = <String, int>{
    'sale_item_added': 1,
    'sale_summary': 1,
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

  Widget build(GenerativeUiContract contract) {
    final result = render(contract);
    if (!result.handled) {
      return LumoMessage(text: contract.fallbackText);
    }
    if (contract.component == 'sale_summary') {
      return SaleSummaryView(contract: contract);
    }
    return SaleItemAddedView(contract: contract);
  }
}

class SaleItemAddedView extends StatelessWidget {
  const SaleItemAddedView({super.key, required this.contract});

  final GenerativeUiContract contract;

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
              Text(contract.fallbackText, style: LumoTypography.body),
              const SizedBox(height: 8),
              LumoCard(
                padding: const EdgeInsets.fromLTRB(16, 10, 16, 10),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
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
                  ],
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
  const SaleSummaryView({super.key, required this.contract});

  final GenerativeUiContract contract;

  @override
  Widget build(BuildContext context) {
    final data = contract.data;
    final items = List<dynamic>.from(data['items'] as List? ?? const []);
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
              Text(contract.fallbackText, style: LumoTypography.body),
              const SizedBox(height: 8),
              LumoCard(
                padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    const Align(
                      alignment: Alignment.centerLeft,
                      child: LumoStatusChip(label: 'Lista para cobrar'),
                    ),
                    const SizedBox(height: 10),
                    for (final raw in items) _itemRow(Map<String, dynamic>.from(raw as Map)),
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
                  ],
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  static Widget _itemRow(Map<String, dynamic> item) {
    final productName = '${item['product_name'] ?? ''}';
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
              ],
            ),
          ),
          Text(lineTotal, style: LumoTypography.metricSm),
        ],
      ),
    );
  }
}
