class IdempotencyStore {
  final Map<String, String> _keys = {};

  String keyFor(String operation) {
    return _keys.putIfAbsent(operation, IdempotencyStore._newKey);
  }

  void clear(String operation) => _keys.remove(operation);

  static int _counter = 0;
  static String _newKey() {
    _counter += 1;
    return 'mobile-${DateTime.now().microsecondsSinceEpoch}-$_counter';
  }
}
