import 'package:flutter_test/flutter_test.dart';
import 'package:lumo/api/api_error.dart';
import 'package:lumo/api/idempotency_store.dart';

void main() {
  test('error envelope is decoded', () {
    final error = ApiError.fromEnvelope({
      'error': {
        'code': 'VALIDATION_ERROR',
        'message': 'bad',
        'retryable': false,
        'correlation_id': 'abc',
      },
    });
    expect(error.code, 'VALIDATION_ERROR');
    expect(error.message, 'bad');
    expect(error.retryable, isFalse);
    expect(error.correlationId, 'abc');
  });

  test('mutation retry reuses the same idempotency key', () {
    final store = IdempotencyStore();
    final first = store.keyFor('platform.note.create');
    final retry = store.keyFor('platform.note.create');
    expect(retry, first);
  });
}
