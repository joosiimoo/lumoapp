import 'package:flutter/material.dart';
import 'package:lumo/features/inicio/business_stream.dart';
import 'package:lumo/lumo/typography.dart';
import 'package:lumo/lumo/widgets/lumo_buttons.dart';
import 'package:lumo/lumo/widgets/lumo_card.dart';

/// Compact current-state panel. It displays server fields and does not rank or sum.
class BusinessStreamPanel extends StatelessWidget {
  const BusinessStreamPanel({
    super.key,
    required this.stream,
    required this.failed,
    required this.onRetry,
    required this.onRecordCashCount,
    required this.onReviewClose,
  });

  final BusinessStream? stream;
  final bool failed;
  final VoidCallback onRetry;
  final VoidCallback onRecordCashCount;
  final VoidCallback onReviewClose;

  @override
  Widget build(BuildContext context) {
    if (failed) {
      return LumoCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(streamUnavailableResponsibility, style: LumoTypography.body),
            const SizedBox(height: 12),
            LumoSecondaryButton(label: 'Reintentar', onPressed: onRetry),
          ],
        ),
      );
    }
    final current = stream;
    if (current == null) {
      return const SizedBox.shrink();
    }
    final lines = _lines(current);
    final action = current.primaryAction;
    return LumoCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          for (var index = 0; index < lines.length; index++) ...[
            if (index > 0) const SizedBox(height: 4),
            Text(lines[index], style: index == 0 ? LumoTypography.cardTitle : LumoTypography.body),
          ],
          if (action != null) ...[
            const SizedBox(height: 12),
            SizedBox(
              width: double.infinity,
              child: LumoPrimaryButton(
                label: action.label,
                onPressed: () => _invoke(action),
              ),
            ),
          ],
        ],
      ),
    );
  }

  void _invoke(StreamPrimaryAction action) {
    if (action.kind == 'record_cash_count' && action.invocation == 'composer') {
      onRecordCashCount();
      return;
    }
    if (action.kind == 'request_close' && action.invocation == 'review_surface') {
      onReviewClose();
    }
  }
}

List<String> _lines(BusinessStream stream) {
  final summary = stream.factualSummary;
  final state = stream.operatorState;
  if (state == 'no_active_day') {
    return [stream.responsibility];
  }
  if (state == 'unavailable' || summary == null) {
    return [stream.responsibility.isEmpty ? streamUnavailableResponsibility : stream.responsibility];
  }
  final sales = '${saleCountLabel(summary.saleCount)} · ${formatStreamAmount(summary.grossSalesTotal.amount)}';
  if (state == 'closed') {
    return ['Día cerrado', sales];
  }
  if (state == 'organizing') {
    return [sales, ..._tenders(summary)];
  }
  final headline = switch (state) {
    'cash_count_required' => 'Falta contar efectivo',
    'cash_difference' || 'ready_to_close' => cashStatusLabel(summary.cashStatus),
    _ => stream.responsibility,
  };
  final lines = <String>[headline, sales, ..._tenders(summary)];
  lines.add('Esperado ${formatStreamAmount(summary.drawerExpected.amount)}');
  final counted = summary.countedCash;
  if (counted != null) {
    lines.add('Contado ${formatStreamAmount(counted.amount)}');
  }
  final difference = summary.cashDifference;
  if (difference != null) {
    lines.add('Diferencia ${formatStreamAmount(difference.amount)}');
  }
  return lines;
}

List<String> _tenders(StreamFactualSummary summary) {
  return [
    'Efectivo ${formatStreamAmount(summary.cashTotal.amount)}',
    'Tarjeta ${formatStreamAmount(summary.cardTotal.amount)}',
    'Transferencia ${formatStreamAmount(summary.transferTotal.amount)}',
  ];
}
