import 'package:flutter_test/flutter_test.dart';
import 'package:lumo/lumo/generative_ui/renderer.dart';

void main() {
  test('unknown component shows fallback and cannot run actions', () {
    const renderer = GenerativeUIRenderer();
    final contract = GenerativeUiContract.fromJson({
      'component': 'sale_confirmed_card',
      'version': 1,
      'data': {},
      'actions': [
        {
          'action_id': 'sale.confirm',
          'context_token': 'tok',
          'idempotency_key': 'k',
        }
      ],
      'fallback_text': 'Venta registrada',
    });
    final result = renderer.render(contract);
    expect(result.text, 'Venta registrada');
    expect(result.handled, isFalse);
    expect(renderer.canRunActions(contract), isFalse);
  });
}
