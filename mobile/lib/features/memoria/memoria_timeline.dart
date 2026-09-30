/// Deterministic Memoria copy. Amounts and times come from the server payload.
library;

import 'package:lumo/lumo/generative_ui/renderer.dart';

const memoriaEmptyTitle = 'Todavía no hay actividad registrada';
const memoriaEmptyBody = 'Las ventas, conteos y cierres confirmados aparecerán aquí.';
const memoriaFooter = 'Memoria muestra operaciones confirmadas registradas en Lumo.';
const memoriaVoidRequestActionId = 'sale.void.request@1';

const _months = [
  'enero',
  'febrero',
  'marzo',
  'abril',
  'mayo',
  'junio',
  'julio',
  'agosto',
  'septiembre',
  'octubre',
  'noviembre',
  'diciembre',
];

const _paymentLabels = {
  'cash': 'Efectivo',
  'card': 'Tarjeta',
  'transfer': 'Transferencia',
};

const _cashStatusLabels = {
  'balanced': 'Cuadrado',
  'short': 'Faltante',
  'over': 'Sobrante',
};

class MemoriaCardView {
  const MemoriaCardView({
    required this.title,
    required this.lines,
    this.chip,
    required this.localTime,
    this.voidRequest,
    this.voidConversationId,
  });

  final String title;
  final List<String> lines;
  final String? chip;
  final String localTime;
  final GenerativeUiAction? voidRequest;
  final String? voidConversationId;
}

/// Server-authored Anular from a timeline event, if present.
({GenerativeUiAction action, String conversationId})? memoriaVoidRequest(Map<String, dynamic> event) {
  final raw = event['actions'];
  if (raw is! List) {
    return null;
  }
  for (final item in raw) {
    if (item is! Map) {
      continue;
    }
    final map = Map<String, dynamic>.from(item);
    if (map['action_id'] != memoriaVoidRequestActionId) {
      continue;
    }
    final conversationId = map['conversation_id'];
    if (conversationId is! String || conversationId.isEmpty) {
      return null;
    }
    return (
      action: GenerativeUiAction.fromJson(map),
      conversationId: conversationId,
    );
  }
  return null;
}

class MemoriaDateGroup {
  const MemoriaDateGroup({required this.label, required this.cards});

  final String label;
  final List<MemoriaCardView> cards;
}

String memoriaDateLabel({
  required String businessDate,
  required String businessToday,
  required String businessYesterday,
}) {
  if (businessDate == businessToday) {
    return 'Hoy';
  }
  if (businessDate == businessYesterday) {
    return 'Ayer';
  }
  final parts = businessDate.split('-');
  if (parts.length != 3) {
    return businessDate;
  }
  final monthIndex = int.parse(parts[1]) - 1;
  final day = int.parse(parts[2]);
  if (monthIndex < 0 || monthIndex >= _months.length) {
    return businessDate;
  }
  return '$day de ${_months[monthIndex]} de ${parts[0]}';
}

MemoriaCardView? memoriaCardView(Map<String, dynamic> event) {
  final type = event['event_type'];
  final facts = event['facts'];
  if (facts is! Map) {
    return null;
  }
  final localTime = event['local_time'];
  if (localTime is! String || localTime.isEmpty) {
    return null;
  }
  final values = facts.map((key, value) => MapEntry(key.toString(), value));
  if (type == 'sale_confirmed') {
    final method = _paymentLabels[values['payment_method']];
    final amount = values['amount'];
    if (method == null || amount is! String) {
      return null;
    }
    final voidAction = memoriaVoidRequest(event);
    return MemoriaCardView(
      title: 'Venta registrada',
      lines: ['$amount · $method'],
      localTime: localTime,
      voidRequest: voidAction?.action,
      voidConversationId: voidAction?.conversationId,
    );
  }
  if (type == 'sale_voided') {
    final method = _paymentLabels[values['payment_method']];
    final amount = values['amount'];
    if (method == null || amount is! String) {
      return null;
    }
    final reason = values['void_reason'];
    final lines = <String>['$amount · $method'];
    if (reason is String && reason.isNotEmpty) {
      lines.add(reason);
    }
    return MemoriaCardView(
      title: 'Venta anulada',
      lines: lines,
      localTime: localTime,
    );
  }
  if (type == 'cash_count_recorded') {
    final status = _cashStatusLabels[values['cash_status']];
    if (status == null) {
      return null;
    }
    return MemoriaCardView(
      title: 'Conteo de efectivo',
      lines: [
        'Esperado ${values['expected_cash']}',
        'Contado ${values['counted_cash']}',
        'Diferencia ${values['cash_difference']}',
      ],
      chip: status,
      localTime: localTime,
    );
  }
  if (type == 'daily_close_completed') {
    final status = _cashStatusLabels[values['cash_status']];
    final gross = values['gross_sales_total'];
    if (status == null || gross is! String) {
      return null;
    }
    return MemoriaCardView(
      title: 'Cierre completado',
      lines: [
        'Ventas registradas $gross',
        'Caja $status',
        'Diferencia ${values['cash_difference']}',
      ],
      localTime: localTime,
    );
  }
  return null;
}

List<MemoriaDateGroup> memoriaGroups({
  required List<Map<String, dynamic>> events,
  required String businessToday,
  required String businessYesterday,
}) {
  final groups = <MemoriaDateGroup>[];
  String? currentDate;
  final cards = <MemoriaCardView>[];
  void flush() {
    final date = currentDate;
    if (date == null || cards.isEmpty) {
      cards.clear();
      return;
    }
    groups.add(
      MemoriaDateGroup(
        label: memoriaDateLabel(
          businessDate: date,
          businessToday: businessToday,
          businessYesterday: businessYesterday,
        ),
        cards: List<MemoriaCardView>.from(cards),
      ),
    );
    cards.clear();
  }

  for (final event in events) {
    final view = memoriaCardView(event);
    if (view == null) {
      continue;
    }
    final businessDate = event['business_date'];
    if (businessDate is! String) {
      continue;
    }
    if (currentDate != businessDate) {
      flush();
      currentDate = businessDate;
    }
    cards.add(view);
  }
  flush();
  return groups;
}
