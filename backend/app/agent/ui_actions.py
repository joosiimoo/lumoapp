from __future__ import annotations


PAYMENT_ACTION_IDS = (
    "sale.pay.cash@1",
    "sale.pay.card@1",
    "sale.pay.transfer@1",
)
REMOVE_ITEM_ACTION_ID = "sale.remove_item@1"
VOID_REQUEST_ACTION_ID = "sale.void.request@1"
VOID_CONFIRM_ACTION_ID = "sale.void.confirm@1"
REQUEST_CLOSE_ACTION_ID = "closing.request@1"
CONFIRM_CLOSE_ACTION_ID = "closing.confirm@1"
SUBMIT_CASH_COUNT_ACTION_ID = "closing.submit_cash_count@1"

_PAYMENT_METHODS = {
    "sale.pay.cash@1": "cash",
    "sale.pay.card@1": "card",
    "sale.pay.transfer@1": "transfer",
}

_CATALOG = (
    *PAYMENT_ACTION_IDS,
    REMOVE_ITEM_ACTION_ID,
    VOID_REQUEST_ACTION_ID,
    VOID_CONFIRM_ACTION_ID,
    REQUEST_CLOSE_ACTION_ID,
    CONFIRM_CLOSE_ACTION_ID,
    SUBMIT_CASH_COUNT_ACTION_ID,
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

    def is_remove_item(self, action_id: str) -> bool:
        return action_id == REMOVE_ITEM_ACTION_ID

    def is_void_request(self, action_id: str) -> bool:
        return action_id == VOID_REQUEST_ACTION_ID

    def is_void_confirm(self, action_id: str) -> bool:
        return action_id == VOID_CONFIRM_ACTION_ID

    def is_submit_cash_count(self, action_id: str) -> bool:
        return action_id == SUBMIT_CASH_COUNT_ACTION_ID

    def is_request_close(self, action_id: str) -> bool:
        return action_id == REQUEST_CLOSE_ACTION_ID

    def is_confirm_close(self, action_id: str) -> bool:
        return action_id == CONFIRM_CLOSE_ACTION_ID
