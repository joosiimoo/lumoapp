from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from app.domain.catalog.product import SaleUnit
from app.domain.sales.quantity import (
    InputUnit,
    calculate_line_total,
    format_normalized_quantity,
    normalize_quantity,
    parse_quantity,
)
from app.domain.sales.session import (
    CommitKind,
    PaymentMethod,
    PaymentSource,
    PaymentStatus,
    SaleItem,
    SaleSessionStatus,
    TotalizeKind,
    can_add_item,
    can_commit,
    classify_commit,
    classify_totalize,
    payment_amount_matches_total,
    sum_session_total,
)
from app.domain.shared.errors import UnitNotSupportedError, ValidationAppError
from app.domain.shared.money import Money


def test_900_grams_becomes_0_900_kg_and_22_50() -> None:
    quantity = parse_quantity("900")
    normalized, unit = normalize_quantity(quantity, InputUnit.GRAM, SaleUnit.KILOGRAM)
    assert format_normalized_quantity(normalized, unit) == "0.900"
    total = calculate_line_total(normalized, Money(Decimal("25.00"), "MXN"))
    assert total.to_json() == {"amount": "22.50", "currency": "MXN"}


def test_zero_quantity_rejected() -> None:
    with pytest.raises(ValidationAppError):
        parse_quantity("0")


def test_gram_on_unit_product_rejected() -> None:
    with pytest.raises(UnitNotSupportedError):
        normalize_quantity(Decimal("900"), InputUnit.GRAM, SaleUnit.UNIT)


def test_line_total_rejects_float() -> None:
    with pytest.raises(TypeError, match="float"):
        Money(Decimal("25.00"), "MXN").times(0.9)  # type: ignore[arg-type]


def test_items_only_while_open() -> None:
    assert can_add_item(SaleSessionStatus.OPEN) is True
    assert can_add_item(SaleSessionStatus.READY_TO_CHARGE) is False
    assert can_add_item(SaleSessionStatus.CONFIRMED) is False


def test_payment_enums() -> None:
    assert {member.value for member in PaymentMethod} == {"cash", "card", "transfer"}
    assert PaymentStatus.RECORDED.value == "recorded"
    assert PaymentSource.MANUAL_CAPTURE.value == "manual_capture"
    assert SaleSessionStatus.CONFIRMED.value == "confirmed"


def test_commit_only_from_ready_to_charge() -> None:
    assert can_commit(SaleSessionStatus.READY_TO_CHARGE) is True
    assert can_commit(SaleSessionStatus.OPEN) is False
    assert can_commit(SaleSessionStatus.CONFIRMED) is False
    assert can_commit(None) is False
    assert classify_commit(SaleSessionStatus.READY_TO_CHARGE, confirmed_exists=False) is CommitKind.TRANSITION
    assert classify_commit(SaleSessionStatus.OPEN, confirmed_exists=False) is CommitKind.NOT_READY
    assert classify_commit(None, confirmed_exists=True) is CommitKind.READ_BACK
    assert classify_commit(None, confirmed_exists=False) is CommitKind.NOT_FOUND


def test_totalize_transition_requires_open_with_items() -> None:
    assert classify_totalize(SaleSessionStatus.OPEN, 2) is TotalizeKind.TRANSITION
    assert classify_totalize(SaleSessionStatus.OPEN, 0) is TotalizeKind.EMPTY
    assert classify_totalize(None, 0) is TotalizeKind.EMPTY
    assert classify_totalize(SaleSessionStatus.READY_TO_CHARGE, 2) is TotalizeKind.READ_BACK


def _item(amount: str) -> SaleItem:
    money = Money(Decimal(amount), "MXN")
    return SaleItem(
        id=uuid4(),
        business_id=uuid4(),
        sale_session_id=uuid4(),
        product_id=uuid4(),
        product_name_snapshot="x",
        quantity_input=Decimal("1"),
        unit_input=InputUnit.UNIT,
        quantity_normalized=Decimal("1"),
        unit_normalized=SaleUnit.UNIT,
        unit_price=money,
        line_total=money,
    )


def test_session_total_is_derived_sum() -> None:
    two = sum_session_total([_item("22.50"), _item("10.00")])
    assert two.to_json() == {"amount": "32.50", "currency": "MXN"}
    three = sum_session_total([_item("22.50"), _item("10.00"), _item("24.00")])
    assert three.to_json() == {"amount": "56.50", "currency": "MXN"}
    assert payment_amount_matches_total(three, [_item("22.50"), _item("10.00"), _item("24.00")]) is True
    assert payment_amount_matches_total(Money(Decimal("10.00"), "MXN"), [_item("22.50")]) is False
