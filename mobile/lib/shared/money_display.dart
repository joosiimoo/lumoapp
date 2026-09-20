class MoneyDisplay {
  static String format({required String amount, required String currency}) {
    return '\$$amount $currency';
  }
}
