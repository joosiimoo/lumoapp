import 'package:flutter/material.dart';
import 'package:lumo/features/inicio/business_stream.dart';
import 'package:lumo/lumo/typography.dart';
import 'package:lumo/lumo/widgets/lumo_buttons.dart';
import 'package:lumo/lumo/widgets/lumo_card.dart';

/// Light Inicio operational header. Displays server facts only; no close CTAs.
class InicioOperationalHeader extends StatelessWidget {
  const InicioOperationalHeader({
    super.key,
    required this.stream,
    required this.failed,
    required this.onRetry,
  });

  final BusinessStream? stream;
  final bool failed;
  final VoidCallback onRetry;

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
    final summary = current.factualSummary;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(_operationalSentence(current), style: LumoTypography.body),
        if (summary != null) ...[
          const SizedBox(height: 12),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: _indicatorCard(
                  label: 'VENTAS HOY',
                  primary: formatStreamAmount(summary.grossSalesTotal.amount),
                  secondary: saleCountLabel(summary.saleCount),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: _indicatorCard(
                  label: 'CAJA',
                  primary: formatStreamAmount(summary.drawerExpected.amount),
                  secondary: operatorCashStateLabel(
                    operatorState: current.operatorState,
                    cashStatus: summary.cashStatus,
                  ),
                ),
              ),
            ],
          ),
        ],
      ],
    );
  }

  Widget _indicatorCard({
    required String label,
    required String primary,
    required String secondary,
  }) {
    return LumoCard(
      padding: const EdgeInsets.fromLTRB(12, 12, 12, 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(label, style: LumoTypography.sectionLabel),
          const SizedBox(height: 6),
          Text(primary, style: LumoTypography.metricSm),
          const SizedBox(height: 4),
          Text(secondary, style: LumoTypography.caption),
        ],
      ),
    );
  }
}

String _operationalSentence(BusinessStream stream) {
  final summary = stream.factualSummary;
  if (summary != null) {
    return 'Llevas ${formatStreamAmount(summary.grossSalesTotal.amount)} en ventas.';
  }
  if (stream.responsibility.isEmpty) {
    return streamUnavailableResponsibility;
  }
  return stream.responsibility;
}
