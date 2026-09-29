import 'package:lumo/lumo/generative_ui/renderer.dart';

enum StartupDestination { onboarding, inicio }

/// Pre-tenant and in-progress sessions stay on onboarding, including ready_to_complete.
/// A completed tenant, including Carrota, opens Inicio.
StartupDestination destinationForSession(Map<String, dynamic>? session) {
  if (session == null) {
    return StartupDestination.inicio;
  }
  final status = session['onboarding_status'];
  if (status == 'not_started' || status == 'in_progress') {
    return StartupDestination.onboarding;
  }
  return StartupDestination.inicio;
}

bool shouldMountBusinessStream(Map<String, dynamic>? session) {
  return destinationForSession(session) == StartupDestination.inicio && session != null;
}

/// Builds the confirmation card from apply or session/status JSON.
/// Chat history is not an input.
GenerativeUiContract? confirmationCardFromState(Map<String, dynamic>? state) {
  if (state == null || state['next_required_field'] != 'ready_to_complete') {
    return null;
  }
  final ui = state['ui'];
  if (ui is List) {
    for (final item in ui) {
      if (item is Map && item['component'] == 'onboarding_confirmation') {
        return GenerativeUiContract.fromJson(Map<String, dynamic>.from(item));
      }
    }
  }
  final source = state['confirmation'] is Map
      ? Map<String, dynamic>.from(state['confirmation'] as Map)
      : state['business'] is Map
          ? Map<String, dynamic>.from(state['business'] as Map)
          : state;
  final methods = source['enabled_payment_methods'] ?? state['enabled_payment_methods'];
  if (source['name'] == null || source['currency'] == null || source['timezone'] == null || methods is! List) {
    return null;
  }
  return GenerativeUiContract(
    component: 'onboarding_confirmation',
    version: 1,
    data: {
      'name': source['name'],
      'currency': source['currency'],
      'timezone': source['timezone'],
      'enabled_payment_methods': methods,
    },
    actions: const [
      GenerativeUiAction(
        actionId: 'start_using_lumo',
        contextToken: 'ready_to_complete',
        idempotencyKey: 'start_using_lumo',
      ),
    ],
    fallbackText: '${source['name']} · ${source['currency']} · ${source['timezone']}',
  );
}

/// Composer text never means completion. Only the card action does.
Map<String, dynamic>? onboardingApplyBody(String text, String? nextField) {
  final value = text.trim();
  if (value.isEmpty || nextField == 'ready_to_complete' || nextField == null) {
    return null;
  }
  if (nextField == 'business_name') {
    return {'name': value};
  }
  if (nextField == 'currency') {
    return {'currency': value};
  }
  if (nextField == 'timezone') {
    return {'timezone': value};
  }
  if (nextField == 'payment_methods') {
    return {
      'payment_methods': [
        for (final part in value.split(RegExp(r'[\s,]+')))
          if (part.isNotEmpty) part,
      ],
    };
  }
  return null;
}
