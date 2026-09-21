import 'package:flutter/material.dart';
import 'package:lumo/lumo/tokens.dart';
import 'package:lumo/lumo/typography.dart';
import 'package:lumo/lumo/widgets/lumo_card.dart';
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
    final unitPrice = _amountOf(data['unit_price']);
    final lineTotal = _amountOf(data['line_total']);
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
                child: Row(
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

  static String _amountOf(Object? value) {
    if (value is Map) {
      return MoneyDisplay.format(
        amount: '${value['amount'] ?? ''}',
        currency: '${value['currency'] ?? 'MXN'}',
      );
    }
    return '';
  }
}
