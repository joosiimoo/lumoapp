import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('feature code does not compute totals or build API URIs', () {
    final files = Directory('lib/features').listSync(recursive: true).whereType<File>();
    for (final file in files) {
      final source = file.readAsStringSync();
      expect(source.contains('Uri.parse'), isFalse, reason: file.path);
      expect(source.contains('Uri.https'), isFalse, reason: file.path);
      expect(source.contains('Uri('), isFalse, reason: file.path);
      expect(source.contains('reduce('), isFalse, reason: file.path);
      expect(source.contains('expectedCash'), isFalse, reason: file.path);
    }
  });
}
