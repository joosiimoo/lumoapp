from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation


class Money:
    """Exact decimal money. Binary floats are rejected."""

    __slots__ = ("amount", "currency")

    def __init__(self, amount: Decimal | str, currency: str) -> None:
        if isinstance(amount, float):
            raise TypeError("money amounts must not use float")
        if isinstance(amount, Decimal):
            value = amount
        elif isinstance(amount, str):
            try:
                value = Decimal(amount)
            except InvalidOperation as exc:
                raise ValueError("invalid decimal money amount") from exc
        else:
            raise TypeError("money amounts must be Decimal or decimal string")
        if not currency or len(currency) != 3 or not currency.isalpha():
            raise ValueError("currency must be a 3-letter ISO 4217 code")
        self.amount = value
        self.currency = currency.upper()

    def times(self, quantity: Decimal | str) -> Money:
        if isinstance(quantity, float):
            raise TypeError("money amounts must not use float")
        if isinstance(quantity, Decimal):
            qty = quantity
        elif isinstance(quantity, str):
            try:
                qty = Decimal(quantity)
            except InvalidOperation as exc:
                raise ValueError("invalid decimal quantity") from exc
        else:
            raise TypeError("quantity must be Decimal or decimal string")
        product = self.amount * qty
        quantized = product.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return Money(quantized, self.currency)

    def to_json(self) -> dict[str, str]:
        quantized = self.amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return {"amount": f"{quantized:.2f}", "currency": self.currency}
