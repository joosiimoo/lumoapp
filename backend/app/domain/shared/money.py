from __future__ import annotations

from decimal import Decimal, InvalidOperation


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

    def to_json(self) -> dict[str, str]:
        return {"amount": format(self.amount, "f"), "currency": self.currency}
