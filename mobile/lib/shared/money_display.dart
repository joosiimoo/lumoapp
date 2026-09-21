class MoneyDisplay {
  static String format({required String amount, required String currency}) {
    if (currency.isEmpty) {
      return amount;
    }
    return '\$$amount';
  }
}
