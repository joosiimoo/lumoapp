/// Deterministic Memoria copy. Amounts and times come from the server payload.
library;

import 'package:lumo/lumo/generative_ui/renderer.dart';

const memoriaEmptyTitle = 'Aún no hay actividad registrada.';
const memoriaVoidRequestActionId = 'sale.void.request@1';

/// Deterministic sale sentence from server payment_method + amount.
///
/// - cash → `Venta en efectivo por $X`
/// - card → `Venta con tarjeta por $X`
/// - transfer → `Venta por transferencia de $X` (avoids "por … por")
String? memoriaSalePrimary({required String paymentMethod, required String amount}) {
  final money = _money(amount);
  switch (paymentMethod) {
    case 'cash':
      return 'Venta en efectivo por $money';
    case 'card':
      return 'Venta con tarjeta por $money';
    case 'transfer':
      return 'Venta por transferencia de $money';
    default:
      return null;
  }
}

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

const _cashStatusLabels = {
  'balanced': 'Cuadrado',
  'short': 'Faltante',
  'over': 'Sobrante',
};

class MemoriaFeedItem {
  const MemoriaFeedItem({
    required this.typeLabel,
    required this.primary,
    this.secondary,
    this.note,
    this.statusChip,
    required this.localTime,
    this.voidRequest,
    this.voidConversationId,
  });

  final String typeLabel;
  final String primary;
  final String? secondary;
  final String? note;
  final String? statusChip;
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
  const MemoriaDateGroup({required this.label, required this.items});

  final String label;
  final List<MemoriaFeedItem> items;
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

String _money(Object? value) => '\$$value';

MemoriaFeedItem? memoriaFeedItem(Map<String, dynamic> event) {
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
    final amount = values['amount'];
    final method = values['payment_method'];
    if (amount is! String || method is! String) {
      return null;
    }
    final primary = memoriaSalePrimary(paymentMethod: method, amount: amount);
    if (primary == null) {
      return null;
    }
    final voidAction = memoriaVoidRequest(event);
    return MemoriaFeedItem(
      typeLabel: 'Venta',
      primary: primary,
      localTime: localTime,
      voidRequest: voidAction?.action,
      voidConversationId: voidAction?.conversationId,
    );
  }
  if (type == 'sale_voided') {
    final amount = values['amount'];
    final method = values['payment_method'];
    if (amount is! String || method is! String) {
      return null;
    }
    final primary = memoriaSalePrimary(paymentMethod: method, amount: amount);
    if (primary == null) {
      return null;
    }
    final reason = values['void_reason'];
    return MemoriaFeedItem(
      typeLabel: 'Venta anulada',
      primary: primary,
      secondary: reason is String && reason.isNotEmpty ? 'Motivo: $reason' : null,
      localTime: localTime,
    );
  }
  if (type == 'cash_count_recorded') {
    final status = _cashStatusLabels[values['cash_status']];
    final counted = values['counted_cash'];
    final expected = values['expected_cash'];
    final difference = values['cash_difference'];
    if (status == null || counted is! String || expected is! String || difference is! String) {
      return null;
    }
    return MemoriaFeedItem(
      typeLabel: 'Conteo',
      primary: 'Efectivo contado ${_money(counted)}',
      secondary: 'Esperado ${_money(expected)} · diferencia ${_money(difference)}',
      // Balanced is already implied by diferencia $0.00; keep exception chips only.
      statusChip: status == 'Cuadrado' ? null : status,
      localTime: localTime,
    );
  }
  if (type == 'daily_close_completed') {
    final status = _cashStatusLabels[values['cash_status']];
    final gross = values['gross_sales_total'];
    final difference = values['cash_difference'];
    if (status == null || gross is! String || difference is! String) {
      return null;
    }
    final note = values['close_note'];
    return MemoriaFeedItem(
      typeLabel: 'Cierre',
      primary: 'Cierre completado · ${_money(gross)} en ventas',
      secondary: '$status · diferencia ${_money(difference)}',
      note: note is String && note.isNotEmpty ? note : null,
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
  final items = <MemoriaFeedItem>[];
  void flush() {
    final date = currentDate;
    if (date == null || items.isEmpty) {
      items.clear();
      return;
    }
    groups.add(
      MemoriaDateGroup(
        label: memoriaDateLabel(
          businessDate: date,
          businessToday: businessToday,
          businessYesterday: businessYesterday,
        ),
        items: List<MemoriaFeedItem>.from(items),
      ),
    );
    items.clear();
  }

  for (final event in events) {
    final view = memoriaFeedItem(event);
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
    items.add(view);
  }
  flush();
  return groups;
}
