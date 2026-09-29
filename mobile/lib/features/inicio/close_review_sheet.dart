import 'package:flutter/material.dart';
import 'package:lumo/features/inicio/business_stream.dart';
import 'package:lumo/lumo/generative_ui/renderer.dart';
import 'package:lumo/lumo/tokens.dart';
import 'package:lumo/lumo/typography.dart';
import 'package:lumo/lumo/widgets/lumo_buttons.dart';
import 'package:lumo/lumo/widgets/lumo_card.dart';

/// Parsed silent `request_close` result. Assistant prose is not retained.
class CloseReviewRequest {
  const CloseReviewRequest({required this.action, required this.preparation});

  final GenerativeUiAction action;
  final Map<String, dynamic> preparation;

  static CloseReviewRequest? fromUi(List<GenerativeUiContract> ui) {
    final action = reviewConfirmationAction(ui);
    final preparation = reviewPreparationData(ui);
    if (action == null || preparation == null) {
      return null;
    }
    return CloseReviewRequest(action: action, preparation: preparation);
  }
}

/// Server-issued confirm action from a silent `request_close` response.
///
/// Returns null unless `daily_close_preparation` carries a confirmation token
/// that matches `closing.confirm@1`.
GenerativeUiAction? reviewConfirmationAction(List<GenerativeUiContract> ui) {
  for (final contract in ui.reversed) {
    if (contract.component != 'daily_close_preparation' || contract.version != 1) {
      continue;
    }
    final value = contract.data['confirmation_token'];
    if (value is! String || value.isEmpty) {
      continue;
    }
    for (final action in contract.actions) {
      if (action.actionId == 'closing.confirm@1' && action.contextToken == value) {
        return action;
      }
    }
  }
  return null;
}

Map<String, dynamic>? reviewPreparationData(List<GenerativeUiContract> ui) {
  final action = reviewConfirmationAction(ui);
  if (action == null) {
    return null;
  }
  for (final contract in ui.reversed) {
    if (contract.component == 'daily_close_preparation' &&
        contract.data['confirmation_token'] == action.contextToken) {
      return contract.data;
    }
  }
  return null;
}

/// Facts the sheet may display. Every value is copied from the today GET or the
/// `request_close` payload. Nothing here adds, subtracts, or ranks.
class CloseReviewFacts {
  const CloseReviewFacts({
    required this.sales,
    required this.gross,
    required this.cash,
    required this.card,
    required this.transfer,
    required this.expected,
    required this.counted,
    required this.difference,
    required this.statusLabel,
    required this.coverage,
  });

  final String? sales;
  final String? gross;
  final String? cash;
  final String? card;
  final String? transfer;
  final String? expected;
  final String? counted;
  final String? difference;
  final String? statusLabel;
  final String? coverage;

  factory CloseReviewFacts.fromServer({
    required BusinessStream stream,
    required Map<String, dynamic> preparation,
  }) {
    final summary = stream.factualSummary;
    final saleCount = preparation['sale_count'] is int ? preparation['sale_count'] as int : summary?.saleCount;
    final status = _string(preparation['cash_status']) ?? summary?.cashStatus;
    return CloseReviewFacts(
      sales: saleCount == null ? null : saleCountLabel(saleCount),
      gross: summary == null ? null : formatStreamAmount(summary.grossSalesTotal.amount),
      cash: summary == null ? null : formatStreamAmount(summary.cashTotal.amount),
      card: summary == null ? null : formatStreamAmount(summary.cardTotal.amount),
      transfer: summary == null ? null : formatStreamAmount(summary.transferTotal.amount),
      expected: _money(preparation['expected_cash']) ?? _summaryMoney(summary?.drawerExpected),
      counted: _money(preparation['counted_cash']) ?? _summaryMoney(summary?.countedCash),
      difference: _money(preparation['cash_difference']) ?? _summaryMoney(summary?.cashDifference),
      statusLabel: status == null || status.isEmpty ? null : cashStatusLabel(status),
      coverage: stream.coverageSentence,
    );
  }
}

String? _summaryMoney(StreamMoney? money) {
  if (money == null) {
    return null;
  }
  return formatStreamAmount(money.amount);
}

String? _money(Object? value) {
  if (value is! Map) {
    return null;
  }
  final amount = value['amount'];
  if (amount is! String || amount.isEmpty) {
    return null;
  }
  return formatStreamAmount(amount);
}

String? _string(Object? value) {
  if (value is String && value.isNotEmpty) {
    return value;
  }
  return null;
}

class CloseReviewSheet extends StatefulWidget {
  const CloseReviewSheet({
    super.key,
    required this.facts,
    required this.onConfirm,
  });

  final CloseReviewFacts facts;
  final Future<String?> Function() onConfirm;

  @override
  State<CloseReviewSheet> createState() => _CloseReviewSheetState();
}

class _CloseReviewSheetState extends State<CloseReviewSheet> {
  bool _confirming = false;
  String? _notice;

  Future<void> _confirm() async {
    if (_confirming) {
      return;
    }
    setState(() {
      _confirming = true;
      _notice = null;
    });
    final notice = await widget.onConfirm();
    if (!mounted) {
      return;
    }
    if (notice == null) {
      Navigator.of(context).pop();
      return;
    }
    setState(() {
      _confirming = false;
      _notice = notice;
    });
  }

  @override
  Widget build(BuildContext context) {
    final facts = widget.facts;
    return SafeArea(
      child: Align(
        alignment: Alignment.bottomCenter,
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: LumoSizes.contentMaxWidth),
          child: Material(
            color: LumoColors.background,
            child: Padding(
              padding: const EdgeInsets.fromLTRB(20, 12, 20, 16),
              child: LumoCard(
                key: const Key('close-review-sheet'),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('Revisar cierre', style: LumoTypography.cardTitle),
                    const SizedBox(height: 12),
                    if (facts.sales != null) Text(facts.sales!, style: LumoTypography.body),
                    if (facts.gross != null) Text('Total ${facts.gross}', style: LumoTypography.body),
                    if (facts.cash != null) Text('Efectivo ${facts.cash}', style: LumoTypography.body),
                    if (facts.card != null) Text('Tarjeta ${facts.card}', style: LumoTypography.body),
                    if (facts.transfer != null) Text('Transferencia ${facts.transfer}', style: LumoTypography.body),
                    if (facts.expected != null) Text('Esperado ${facts.expected}', style: LumoTypography.body),
                    if (facts.counted != null) Text('Contado ${facts.counted}', style: LumoTypography.body),
                    if (facts.difference != null) Text('Diferencia ${facts.difference}', style: LumoTypography.body),
                    if (facts.statusLabel != null) ...[
                      const SizedBox(height: 8),
                      Text(facts.statusLabel!, style: LumoTypography.cardTitle),
                    ],
                    if (facts.coverage != null) ...[
                      const SizedBox(height: 8),
                      Text(facts.coverage!, style: LumoTypography.caption),
                    ],
                    if (_notice != null) ...[
                      const SizedBox(height: 8),
                      Text(_notice!, style: LumoTypography.body),
                    ],
                    const SizedBox(height: 16),
                    SizedBox(
                      width: double.infinity,
                      child: LumoPrimaryButton(
                        label: 'Confirmar cierre',
                        enabled: !_confirming,
                        onPressed: _confirm,
                      ),
                    ),
                    const SizedBox(height: 8),
                    LumoSecondaryButton(
                      label: 'Cancelar',
                      onPressed: () {
                        if (_confirming) {
                          return;
                        }
                        Navigator.of(context).pop();
                      },
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
