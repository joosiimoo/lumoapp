/// Typed Business Stream body. The client does not choose a state or compute money.
library;

const streamUnavailableResponsibility = 'No pude consultar el estado de hoy.';

class StreamMoney {
  const StreamMoney({required this.amount, required this.currency});

  final String amount;
  final String currency;

  factory StreamMoney.fromJson(Map<String, dynamic> json) {
    return StreamMoney(amount: '${json['amount']}', currency: '${json['currency']}');
  }
}

class StreamFactualSummary {
  const StreamFactualSummary({
    required this.basis,
    required this.saleCount,
    required this.grossSalesTotal,
    required this.cashTotal,
    required this.cardTotal,
    required this.transferTotal,
    required this.drawerExpected,
    required this.countedCash,
    required this.cashDifference,
    required this.cashStatus,
    required this.closedAt,
  });

  final String basis;
  final int saleCount;
  final StreamMoney grossSalesTotal;
  final StreamMoney cashTotal;
  final StreamMoney cardTotal;
  final StreamMoney transferTotal;
  final StreamMoney drawerExpected;
  final StreamMoney? countedCash;
  final StreamMoney? cashDifference;
  final String cashStatus;
  final String? closedAt;

  factory StreamFactualSummary.fromJson(Map<String, dynamic> json) {
    return StreamFactualSummary(
      basis: '${json['basis']}',
      saleCount: json['sale_count'] as int,
      grossSalesTotal: StreamMoney.fromJson(_map(json['gross_sales_total'])),
      cashTotal: StreamMoney.fromJson(_map(json['cash_total'])),
      cardTotal: StreamMoney.fromJson(_map(json['card_total'])),
      transferTotal: StreamMoney.fromJson(_map(json['transfer_total'])),
      drawerExpected: StreamMoney.fromJson(_map(json['expected_cash'])),
      countedCash: json['counted_cash'] == null ? null : StreamMoney.fromJson(_map(json['counted_cash'])),
      cashDifference: json['cash_difference'] == null ? null : StreamMoney.fromJson(_map(json['cash_difference'])),
      cashStatus: '${json['cash_status']}',
      closedAt: json['closed_at'] as String?,
    );
  }
}

class StreamPrimaryAction {
  const StreamPrimaryAction({
    required this.kind,
    required this.label,
    required this.invocation,
    required this.message,
    required this.actionId,
    required this.workItemId,
    required this.outcomeRunId,
  });

  final String kind;
  final String label;
  final String invocation;
  final String? message;
  final String? actionId;
  final String? workItemId;
  final String? outcomeRunId;

  factory StreamPrimaryAction.fromJson(Map<String, dynamic> json) {
    return StreamPrimaryAction(
      kind: '${json['kind']}',
      label: '${json['label']}',
      invocation: '${json['invocation']}',
      message: json['message'] as String?,
      actionId: json['action_id'] as String?,
      workItemId: json['work_item_id'] as String?,
      outcomeRunId: json['outcome_run_id'] as String?,
    );
  }
}

class BusinessStream {
  const BusinessStream({
    required this.businessDate,
    required this.operatorState,
    required this.closeProgress,
    required this.responsibility,
    required this.detail,
    required this.factualSummary,
    required this.attentionWhy,
    required this.primaryAction,
    required this.coverageSentence,
    required this.asOf,
  });

  final String businessDate;
  final String operatorState;
  final String? closeProgress;
  final String responsibility;
  final String? detail;
  final StreamFactualSummary? factualSummary;
  final String? attentionWhy;
  final StreamPrimaryAction? primaryAction;
  final String? coverageSentence;
  final String asOf;

  factory BusinessStream.fromJson(Map<String, dynamic> json) {
    final attention = json['attention'];
    final coverage = json['coverage'];
    final summary = json['factual_summary'];
    final action = json['primary_action'];
    return BusinessStream(
      businessDate: '${json['business_date']}',
      operatorState: '${json['operator_state']}',
      closeProgress: json['close_progress'] as String?,
      responsibility: '${json['responsibility']}',
      detail: json['detail'] as String?,
      factualSummary: summary == null ? null : StreamFactualSummary.fromJson(_map(summary)),
      attentionWhy: attention == null ? null : '${_map(attention)['why']}',
      primaryAction: action == null ? null : StreamPrimaryAction.fromJson(_map(action)),
      coverageSentence: coverage == null ? null : '${_map(coverage)['sentence']}',
      asOf: '${json['as_of']}',
    );
  }
}

String cashStatusLabel(String status) {
  switch (status) {
    case 'not_counted':
      return 'Falta contar efectivo';
    case 'balanced':
      return 'Caja cuadrada';
    case 'short':
      return 'Faltante';
    case 'over':
      return 'Sobrante';
  }
  throw FormatException('unknown cash_status');
}

/// Display a server decimal string. This does not add, compare, or recompute it.
String saleCountLabel(int saleCount) {
  if (saleCount == 1) {
    return '1 venta';
  }
  return '$saleCount ventas';
}

String formatStreamAmount(String amount) {
  if (amount.startsWith('-')) {
    return '-\$${amount.substring(1)}';
  }
  return '\$$amount';
}

Map<String, dynamic> _map(Object? value) {
  if (value is Map<String, dynamic>) {
    return value;
  }
  if (value is Map) {
    return Map<String, dynamic>.from(value);
  }
  throw const FormatException('expected an object');
}
