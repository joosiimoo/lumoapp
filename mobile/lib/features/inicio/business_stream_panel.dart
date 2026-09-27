import 'package:flutter/material.dart';
import 'package:lumo/features/inicio/business_stream.dart';
import 'package:lumo/lumo/typography.dart';
import 'package:lumo/lumo/widgets/lumo_buttons.dart';
import 'package:lumo/lumo/widgets/lumo_card.dart';

/// One operator panel. It displays the server projection and does not rank or sum.
class BusinessStreamPanel extends StatelessWidget {
  const BusinessStreamPanel({
    super.key,
    required this.stream,
    required this.failed,
    required this.onRetry,
    required this.onRecordCashCount,
    required this.onRequestClose,
  });

  final BusinessStream? stream;
  final bool failed;
  final VoidCallback onRetry;
  final VoidCallback onRecordCashCount;
  final void Function(String message) onRequestClose;

  @override
  Widget build(BuildContext context) {
    if (failed) {
      return LumoCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
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
    final summary = current.factualSummary;
    final action = current.primaryAction;
    return LumoCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(current.responsibility, style: LumoTypography.cardTitle),
          if (current.detail != null) ...[
            const SizedBox(height: 8),
            Text(current.detail!, style: LumoTypography.body),
          ],
          if (summary != null) ...[
            const SizedBox(height: 12),
            Text(saleCountLabel(summary.saleCount), style: LumoTypography.body),
            Text('Total ${formatStreamAmount(summary.grossSalesTotal.amount)}', style: LumoTypography.body),
            Text('Efectivo ${formatStreamAmount(summary.cashTotal.amount)}', style: LumoTypography.body),
            Text('Tarjeta ${formatStreamAmount(summary.cardTotal.amount)}', style: LumoTypography.body),
            Text('Transferencia ${formatStreamAmount(summary.transferTotal.amount)}', style: LumoTypography.body),
            Text(cashStatusLabel(summary.cashStatus), style: LumoTypography.body),
            Text('Esperado ${formatStreamAmount(summary.drawerExpected.amount)}', style: LumoTypography.body),
            if (summary.countedCash != null)
              Text('Contado ${formatStreamAmount(summary.countedCash!.amount)}', style: LumoTypography.body),
            if (summary.cashDifference != null)
              Text('Diferencia ${formatStreamAmount(summary.cashDifference!.amount)}', style: LumoTypography.body),
          ],
          if (current.attentionWhy != null) ...[
            const SizedBox(height: 8),
            Text(current.attentionWhy!, style: LumoTypography.caption),
          ],
          if (current.coverageSentence != null) ...[
            const SizedBox(height: 8),
            Text(current.coverageSentence!, style: LumoTypography.caption),
          ],
          if (action != null) ...[
            const SizedBox(height: 16),
            LumoPrimaryButton(
              label: action.label,
              onPressed: () => _invoke(action),
            ),
          ],
        ],
      ),
    );
  }

  void _invoke(StreamPrimaryAction action) {
    if (action.invocation == 'composer' && action.kind == 'record_cash_count') {
      onRecordCashCount();
      return;
    }
    final message = action.message;
    if (action.invocation == 'message' && message != null && message.isNotEmpty) {
      onRequestClose(message);
    }
  }
}
