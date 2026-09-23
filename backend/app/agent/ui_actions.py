from __future__ import annotations


PAYMENT_ACTION_IDS = (
    "sale.pay.cash@1",
    "sale.pay.card@1",
    "sale.pay.transfer@1",
)
REQUEST_CLOSE_ACTION_ID = "closing.request@1"
CONFIRM_CLOSE_ACTION_ID = "closing.confirm@1"

_PAYMENT_METHODS = {
    "sale.pay.cash@1": "cash",
    "sale.pay.card@1": "card",
    "sale.pay.transfer@1": "transfer",
}

_CATALOG = (
    *PAYMENT_ACTION_IDS,
    REQUEST_CLOSE_ACTION_ID,
    CONFIRM_CLOSE_ACTION_ID,
)


class UiActionRegistry:
    def __init__(self) -> None:
        self._ids = set(_CATALOG)

    def is_registered(self, action_id: str) -> bool:
        return action_id in self._ids

    def ids(self) -> list[str]:
        return list(_CATALOG)

    def payment_method(self, action_id: str) -> str | None:
        return _PAYMENT_METHODS.get(action_id)

    def is_payment(self, action_id: str) -> bool:
        return action_id in _PAYMENT_METHODS
