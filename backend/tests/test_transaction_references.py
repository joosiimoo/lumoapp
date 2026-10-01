"""Transaction references (ADR-033): TRX format, allocator, confirm/void/close, export."""

from __future__ import annotations

import csv
import io
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy import func, select, text

from app.application.queries.export_daily_sales import SalesExport, SalesExportLine
from app.domain.operations.business_event import (
    BusinessEventType,
    daily_close_completed_facts,
    sale_confirmed_facts,
    sale_voided_facts,
    validate_business_event_facts,
)
from app.domain.shared.errors import ValidationAppError
from app.domain.shared.ids import new_uuid7
from app.domain.shared.tenant import TenantContext
from app.domain.shared.transaction_number import format_transaction_number
from app.infrastructure.export.columns import COLUMN_WIDTHS, EXPORT_COLUMNS
from app.infrastructure.export.daily_sales_csv import render_daily_sales_csv
from app.infrastructure.export.daily_sales_xlsx import render_daily_sales_xlsx
from app.infrastructure.persistence.engine import create_engine_from_settings, create_session_factory
from app.infrastructure.persistence.models import (
    BusinessEventRow,
    BusinessTransactionCounterRow,
    ClosingSnapshotRow,
    SaleSessionRow,
)
from app.infrastructure.persistence.operations import OperationsRepository
from app.infrastructure.persistence.rls import set_current_business_id
from tests.conftest import make_settings, postgres_available, seed_business
from tests.test_daily_close_confirmation import _confirm as _close_confirm
from tests.test_daily_close_confirmation import _post as _message
from tests.test_daily_close_confirmation import _ready as _close_ready
from tests.test_daily_close_preparation import _rows
from tests.test_sale_corrections import _void_confirm_action, _void_with
from tests.test_ui_actions import _action_by_id, _auth, _pay, _ready, _seed

TRX_RE = re.compile(r"^TRX-[0-9]{6,}$")

requires_postgres = pytest.mark.skipif(
    not postgres_available(make_settings()), reason="PostgreSQL is not available"
)


# --- format ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("sequence", "expected"),
    [
        (1, "TRX-000001"),
        (42, "TRX-000042"),
        (999_999, "TRX-999999"),
        (1_000_000, "TRX-1000000"),
        (12_345_678, "TRX-12345678"),
    ],
)
def test_format_transaction_number(sequence: int, expected: str) -> None:
    assert format_transaction_number(sequence) == expected


@pytest.mark.parametrize("bad", [0, -1, True, "1", 1.0, None])
def test_format_transaction_number_rejects_non_positive_ints(bad) -> None:
    with pytest.raises(ValueError):
        format_transaction_number(bad)  # type: ignore[arg-type]


def test_event_facts_require_a_trx_string() -> None:
    sale_id = new_uuid7()
    facts = sale_confirmed_facts(
        sale_session_id=sale_id,
        payment_id=new_uuid7(),
        payment_method="cash",
        amount="10.00",
        currency="MXN",
        transaction_number="TRX-000001",
    )
    assert validate_business_event_facts(
        event_type=BusinessEventType.SALE_CONFIRMED, source_entity_id=sale_id, facts=facts
    ) == facts
    for bad in ("000001", "TRX-", "TRX-12a", "trx-000001", "TRX-000001\n", 1):
        broken = dict(facts, transaction_number=bad)
        with pytest.raises(ValidationAppError):
            validate_business_event_facts(
                event_type=BusinessEventType.SALE_CONFIRMED, source_entity_id=sale_id, facts=broken
            )
    missing = {key: value for key, value in facts.items() if key != "transaction_number"}
    with pytest.raises(ValidationAppError, match="approved keys"):
        validate_business_event_facts(
            event_type=BusinessEventType.SALE_CONFIRMED, source_entity_id=sale_id, facts=missing
        )


def test_void_and_close_facts_carry_references() -> None:
    sale_id = new_uuid7()
    void = sale_voided_facts(
        sale_session_id=sale_id,
        payment_id=new_uuid7(),
        payment_method="cash",
        amount="10.00",
        currency="MXN",
        void_reason="duplicado",
        voided_by_actor_id=new_uuid7(),
        transaction_number="TRX-000002",
        original_transaction_number="TRX-000001",
    )
    assert void["transaction_number"] == "TRX-000002"
    assert void["original_transaction_number"] == "TRX-000001"
    validate_business_event_facts(
        event_type=BusinessEventType.SALE_VOIDED, source_entity_id=sale_id, facts=void
    )
    same = dict(void, original_transaction_number="TRX-000002")
    with pytest.raises(ValidationAppError, match="differ"):
        validate_business_event_facts(
            event_type=BusinessEventType.SALE_VOIDED, source_entity_id=sale_id, facts=same
        )
    snapshot_id = new_uuid7()
    close = daily_close_completed_facts(
        outcome_run_id=new_uuid7(),
        closing_snapshot_id=snapshot_id,
        sale_count=1,
        gross_sales_total="10.00",
        expected_cash="10.00",
        counted_cash="10.00",
        cash_difference_amount="0.00",
        cash_status="balanced",
        currency="MXN",
        transaction_number="TRX-000003",
    )
    assert close["transaction_number"] == "TRX-000003"
    validate_business_event_facts(
        event_type=BusinessEventType.DAILY_CLOSE_COMPLETED, source_entity_id=snapshot_id, facts=close
    )
    with pytest.raises(ValidationAppError):
        daily_close_completed_facts(
            outcome_run_id=new_uuid7(),
            closing_snapshot_id=snapshot_id,
            sale_count=1,
            gross_sales_total="10.00",
            expected_cash="10.00",
            counted_cash="10.00",
            cash_difference_amount="0.00",
            cash_status="balanced",
            currency="MXN",
            transaction_number="TRX-x",
        )


# --- allocator ------------------------------------------------------------------------------


def _tenant(business_id: UUID, actor_id: UUID) -> TenantContext:
    return TenantContext(business_id=business_id, actor_id=actor_id)


def _counter_rows(session, business_id: UUID) -> list[BusinessTransactionCounterRow]:
    set_current_business_id(session, business_id)
    session.expire_all()
    return list(
        session.scalars(
            select(BusinessTransactionCounterRow).where(
                BusinessTransactionCounterRow.business_id == business_id
            )
        ).all()
    )


@requires_postgres
def test_allocate_first_value_and_increment(db_session) -> None:
    business_id, actor_id, _ = seed_business(db_session, name="TRX alloc")
    tenant = _tenant(business_id, actor_id)
    repo = OperationsRepository(db_session)
    assert _counter_rows(db_session, business_id) == []
    assert repo.allocate_transaction_sequence(tenant=tenant) == 1
    assert repo.allocate_transaction_sequence(tenant=tenant) == 2
    assert repo.allocate_transaction_sequence(tenant=tenant) == 3
    db_session.commit()
    rows = _counter_rows(db_session, business_id)
    assert len(rows) == 1
    assert rows[0].last_value == 3


@requires_postgres
def test_allocate_is_isolated_per_business(db_session) -> None:
    a_id, a_actor, _ = seed_business(db_session, name="TRX tenant A")
    b_id, b_actor, _ = seed_business(db_session, name="TRX tenant B")
    repo = OperationsRepository(db_session)
    assert repo.allocate_transaction_sequence(tenant=_tenant(a_id, a_actor)) == 1
    assert repo.allocate_transaction_sequence(tenant=_tenant(a_id, a_actor)) == 2
    assert repo.allocate_transaction_sequence(tenant=_tenant(b_id, b_actor)) == 1
    assert repo.allocate_transaction_sequence(tenant=_tenant(a_id, a_actor)) == 3
    db_session.commit()
    # Forced RLS: another tenant's counter is invisible under this tenant's context.
    set_current_business_id(db_session, b_id)
    visible = db_session.scalars(select(BusinessTransactionCounterRow.business_id)).all()
    assert visible == [b_id]
    assert db_session.scalar(
        select(BusinessTransactionCounterRow.last_value).where(
            BusinessTransactionCounterRow.business_id == a_id
        )
    ) is None


@requires_postgres
def test_allocate_rolls_back_with_the_caller_transaction(db_session) -> None:
    business_id, actor_id, _ = seed_business(db_session, name="TRX rollback")
    tenant = _tenant(business_id, actor_id)
    repo = OperationsRepository(db_session)
    assert repo.allocate_transaction_sequence(tenant=tenant) == 1
    db_session.commit()
    assert repo.allocate_transaction_sequence(tenant=tenant) == 2
    db_session.rollback()
    assert _counter_rows(db_session, business_id)[0].last_value == 1
    assert repo.allocate_transaction_sequence(tenant=tenant) == 2
    db_session.commit()
    assert _counter_rows(db_session, business_id)[0].last_value == 2


@requires_postgres
def test_allocate_requires_a_business() -> None:
    repo = OperationsRepository(None)  # type: ignore[arg-type]
    with pytest.raises(Exception):
        repo.allocate_transaction_sequence(tenant=None)  # type: ignore[arg-type]


def _allocate_in_own_session(factory, tenant: TenantContext, *, start: threading.Barrier | None = None) -> int:
    session = factory()
    try:
        if start is not None:
            start.wait(timeout=10)
        value = OperationsRepository(session).allocate_transaction_sequence(tenant=tenant)
        session.commit()
        return value
    finally:
        session.close()


@requires_postgres
def test_concurrent_allocations_are_unique_and_monotonic(db_session) -> None:
    business_id, actor_id, _ = seed_business(db_session, name="TRX concurrent")
    tenant = _tenant(business_id, actor_id)
    engine = create_engine_from_settings(make_settings())
    factory = create_session_factory(engine)
    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            values = list(pool.map(lambda _: _allocate_in_own_session(factory, tenant), range(24)))
    finally:
        engine.dispose()
    assert sorted(values) == list(range(1, 25))
    rows = _counter_rows(db_session, business_id)
    assert len(rows) == 1
    assert rows[0].last_value == 24


@requires_postgres
def test_concurrent_first_allocation_creates_one_counter_row(db_session) -> None:
    engine = create_engine_from_settings(make_settings())
    factory = create_session_factory(engine)
    try:
        for index in range(6):
            business_id, actor_id, _ = seed_business(db_session, name=f"TRX first {index}")
            tenant = _tenant(business_id, actor_id)
            start = threading.Barrier(2)
            with ThreadPoolExecutor(max_workers=2) as pool:
                left = pool.submit(_allocate_in_own_session, factory, tenant, start=start)
                right = pool.submit(_allocate_in_own_session, factory, tenant, start=start)
                values = sorted([left.result(timeout=30), right.result(timeout=30)])
            assert values == [1, 2]
            rows = _counter_rows(db_session, business_id)
            assert len(rows) == 1
            assert rows[0].last_value == 2
    finally:
        engine.dispose()


@requires_postgres
def test_concurrent_first_allocation_waits_for_uncommitted_insert(db_session) -> None:
    """B starts while A holds the uncommitted first insert: B waits, then gets the next value."""
    business_id, actor_id, _ = seed_business(db_session, name="TRX first held")
    tenant = _tenant(business_id, actor_id)
    engine = create_engine_from_settings(make_settings())
    factory = create_session_factory(engine)
    a_allocated = threading.Event()
    results: dict[str, int] = {}

    def first() -> None:
        session = factory()
        try:
            results["a"] = OperationsRepository(session).allocate_transaction_sequence(tenant=tenant)
            a_allocated.set()
            time.sleep(0.6)
            session.commit()
        finally:
            session.close()

    def second() -> None:
        assert a_allocated.wait(timeout=10)
        results["b"] = _allocate_in_own_session(factory, tenant)

    try:
        threads = [threading.Thread(target=first), threading.Thread(target=second)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
    finally:
        engine.dispose()
    assert results == {"a": 1, "b": 2}
    rows = _counter_rows(db_session, business_id)
    assert len(rows) == 1
    assert rows[0].last_value == 2


# --- confirm / void / close -----------------------------------------------------------------


def _payload_trx(payload: dict) -> str:
    value = payload["transaction_number"]
    assert TRX_RE.fullmatch(value), value
    return value


def _last_value(db_session, business_id: UUID) -> int:
    rows = _counter_rows(db_session, business_id)
    return rows[0].last_value if rows else 0


@requires_postgres
def test_confirm_assigns_number_and_replay_does_not_reallocate(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    conversation_id = "conv-trx-confirm"
    card = _ready(client, token, conversation_id, "trx-confirm")
    action = _action_by_id(card, "sale.pay.cash@1")
    paid = _pay(client, token, conversation_id, action)
    assert paid.status_code == 200, paid.text
    data = paid.json()["ui"][0]["data"]
    trx = _payload_trx(data)
    assert trx == "TRX-000001"

    session = _rows(db_session, tenant.business_id, SaleSessionRow)[0]
    assert session.transaction_sequence == 1
    assert session.void_transaction_sequence is None
    assert format_transaction_number(session.transaction_sequence) == trx
    events = _rows(db_session, tenant.business_id, BusinessEventRow)
    assert [event.facts["transaction_number"] for event in events] == [trx]

    # Same key: stored replay body. Different key: entity read-back. Neither re-allocates.
    replay = _pay(client, token, conversation_id, action)
    assert replay.status_code == 200, replay.text
    assert replay.json()["ui"][0]["data"]["transaction_number"] == trx
    other_key = {**action, "idempotency_key": "trx-confirm-read-back"}
    read_back = _pay(client, token, conversation_id, other_key)
    assert read_back.status_code == 200, read_back.text
    assert read_back.json()["ui"][0]["data"]["transaction_number"] == trx
    assert _last_value(db_session, tenant.business_id) == 1
    assert len(_rows(db_session, tenant.business_id, BusinessEventRow)) == 1


@requires_postgres
def test_multi_item_sale_shares_one_number(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    conversation_id = "conv-trx-multi"
    for index, text_ in enumerate(("900gr zanahoria", "900gr zanahoria")):
        added = _message(client, token, text_, f"trx-multi-{index}", conversation_id)
        assert added.status_code == 200, added.text
    totaled = _message(client, token, "totalizar", "trx-multi-tot", conversation_id)
    assert totaled.status_code == 200, totaled.text
    paid = _message(client, token, "efectivo", "trx-multi-pay", conversation_id)
    assert paid.status_code == 200, paid.text
    data = paid.json()["ui"][0]["data"]
    assert data["item_count"] == 2
    assert _payload_trx(data) == "TRX-000001"
    assert _last_value(db_session, tenant.business_id) == 1


@requires_postgres
def test_failed_confirm_commits_no_reference(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    conversation_id = "conv-trx-fail"
    card = _ready(client, token, conversation_id, "trx-fail")
    action = _action_by_id(card, "sale.pay.cash@1")
    failed = client.post(
        "/api/v1/lumo/actions",
        json={
            "action_id": action["action_id"],
            "option_id": None,
            "context_token": action["context_token"],
            "conversation_id": conversation_id,
            "idempotency_key": "trx-fail-1",
        },
        headers={**_auth(token, "trx-fail-1"), "X-Debug-Fail-After-Write": "1"},
    )
    assert failed.status_code >= 500
    assert _last_value(db_session, tenant.business_id) == 0
    assert _rows(db_session, tenant.business_id, SaleSessionRow)[0].transaction_sequence is None
    paid = _pay(client, token, conversation_id, action)
    assert paid.status_code == 200, paid.text
    assert paid.json()["ui"][0]["data"]["transaction_number"] == "TRX-000001"


def _sale_then_void(client: TestClient, token: str, conversation_id: str, prefix: str) -> tuple[dict, dict, dict]:
    card = _ready(client, token, conversation_id, prefix)
    paid = _pay(client, token, conversation_id, _action_by_id(card, "sale.pay.cash@1"))
    assert paid.status_code == 200, paid.text
    confirmed = paid.json()["ui"][0]
    confirm = _void_confirm_action(client, token, conversation_id, confirmed)
    return confirmed, confirm, card


@requires_postgres
def test_void_gets_its_own_number_and_keeps_the_original(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    conversation_id = "conv-trx-void"
    confirmed, confirm, _card = _sale_then_void(client, token, conversation_id, "trx-void")
    sale_trx = _payload_trx(confirmed["data"])
    assert sale_trx == "TRX-000001"

    voided = _void_with(client, token, conversation_id, confirm, key="trx-void-1")
    assert voided.status_code == 200, voided.text
    data = voided.json()["ui"][0]["data"]
    assert data["status"] == "voided"
    assert data["transaction_number"] == "TRX-000002"
    assert data["original_transaction_number"] == sale_trx
    assert data["transaction_number"] != data["original_transaction_number"]

    session = _rows(db_session, tenant.business_id, SaleSessionRow)[0]
    assert session.transaction_sequence == 1
    assert session.void_transaction_sequence == 2
    events = {event.event_type: event for event in _rows(db_session, tenant.business_id, BusinessEventRow)}
    assert events["sale_confirmed"].facts["transaction_number"] == "TRX-000001"
    assert events["sale_voided"].facts["transaction_number"] == "TRX-000002"
    assert events["sale_voided"].facts["original_transaction_number"] == "TRX-000001"
    assert "original_transaction_number" not in events["sale_confirmed"].facts

    # Same key replay + new-key read-back of an already voided sale: nothing re-allocates.
    replay = _void_with(client, token, conversation_id, confirm, key="trx-void-1")
    assert replay.status_code == 200, replay.text
    assert replay.json()["ui"][0]["data"]["transaction_number"] == "TRX-000002"
    again = _void_with(client, token, conversation_id, confirm, key="trx-void-2", reason="otra vez")
    assert again.status_code == 200, again.text
    again_data = again.json()["ui"][0]["data"]
    assert again_data["transaction_number"] == "TRX-000002"
    assert again_data["original_transaction_number"] == "TRX-000001"
    assert _last_value(db_session, tenant.business_id) == 2
    assert len([e for e in _rows(db_session, tenant.business_id, BusinessEventRow) if e.event_type == "sale_voided"]) == 1


@requires_postgres
def test_concurrent_void_allocates_one_void_number(app, db_session) -> None:
    tenant, token = _seed(db_session)
    conversation_id = "conv-trx-void-race"
    with TestClient(app, raise_server_exceptions=False) as setup:
        _confirmed, confirm, _card = _sale_then_void(setup, token, conversation_id, "trx-void-race")

    def void_once(key: str):
        with TestClient(app, raise_server_exceptions=False) as local:
            return _void_with(local, token, conversation_id, confirm, key=key)

    with ThreadPoolExecutor(max_workers=2) as pool:
        left = pool.submit(void_once, "trx-void-race-a")
        right = pool.submit(void_once, "trx-void-race-b")
        first = left.result(timeout=30)
        second = right.result(timeout=30)
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    numbers = {
        first.json()["ui"][0]["data"]["transaction_number"],
        second.json()["ui"][0]["data"]["transaction_number"],
    }
    assert numbers == {"TRX-000002"}
    session = _rows(db_session, tenant.business_id, SaleSessionRow)[0]
    assert (session.transaction_sequence, session.void_transaction_sequence) == (1, 2)
    assert _last_value(db_session, tenant.business_id) == 2


@requires_postgres
def test_close_gets_a_number_and_replay_is_stable(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    confirmation, _requested = _close_ready(client, token, "trx-close")
    # Cash count allocated nothing; the sale used TRX-000001.
    assert _last_value(db_session, tenant.business_id) == 1
    cash_events = [
        event
        for event in _rows(db_session, tenant.business_id, BusinessEventRow)
        if event.event_type == "cash_count_recorded"
    ]
    assert len(cash_events) == 1
    assert "transaction_number" not in cash_events[0].facts

    first = _close_confirm(client, token, "trx-close", confirmation, key="trx-close-1")
    assert first.status_code == 200, first.text
    data = first.json()["ui"][0]["data"]
    assert _payload_trx(data) == "TRX-000002"
    snapshot = _rows(db_session, tenant.business_id, ClosingSnapshotRow)[0]
    assert snapshot.transaction_sequence == 2
    close_event = next(
        event
        for event in _rows(db_session, tenant.business_id, BusinessEventRow)
        if event.event_type == "daily_close_completed"
    )
    assert close_event.facts["transaction_number"] == "TRX-000002"

    replay = _close_confirm(client, token, "trx-close", confirmation, key="trx-close-1")
    assert replay.status_code == 200, replay.text
    assert replay.json()["ui"][0]["data"]["transaction_number"] == "TRX-000002"
    other = _close_confirm(client, token, "trx-close", confirmation, key="trx-close-2", message="confirmar")
    assert other.status_code == 200, other.text
    assert other.json()["ui"][0]["data"]["transaction_number"] == "TRX-000002"
    assert _last_value(db_session, tenant.business_id) == 2


@requires_postgres
def test_failed_close_commits_no_reference(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    confirmation, _requested = _close_ready(client, token, "trx-close-fail")
    failed = _close_confirm(
        client,
        token,
        "trx-close-fail",
        confirmation,
        key="trx-close-fail-1",
        **{"X-Debug-Fail-After-Write": "1"},
    )
    assert failed.status_code >= 500
    assert _rows(db_session, tenant.business_id, ClosingSnapshotRow) == []
    assert _last_value(db_session, tenant.business_id) == 1
    closed = _close_confirm(client, token, "trx-close-fail", confirmation, key="trx-close-fail-2")
    assert closed.status_code == 200, closed.text
    assert closed.json()["ui"][0]["data"]["transaction_number"] == "TRX-000002"


# --- export ---------------------------------------------------------------------------------


def _export_line(**overrides) -> SalesExportLine:
    base = dict(
        business_date=date(2026, 9, 23),
        sale_session_id=UUID("55555555-5555-4555-8555-555555555555"),
        sale_transaction_sequence=12,
        sale_status="confirmed",
        sale_confirmed_at=datetime(2026, 9, 23, 20, 5, tzinfo=UTC),
        sale_item_id=new_uuid7(),
        product_name="Zanahoria",
        source_type="catalog",
        product_id=new_uuid7(),
        quantity=Decimal("1"),
        unit="unit",
        catalog_unit_price=Decimal("20.00"),
        unit_price=Decimal("20.00"),
        price_override_reason=None,
        line_total=Decimal("20.00"),
        currency="MXN",
        payment_id=new_uuid7(),
        payment_method="cash",
        payment_amount=Decimal("40.00"),
    )
    base.update(overrides)
    return SalesExportLine(**base)


def _export() -> SalesExport:
    voided_session = UUID("66666666-6666-4666-8666-666666666666")
    return SalesExport(
        business_name="Carrota",
        business_date=date(2026, 9, 23),
        timezone_name="America/Mexico_City",
        currency="MXN",
        status="open",
        lines=(
            _export_line(),
            _export_line(),
            _export_line(
                sale_session_id=voided_session,
                sale_transaction_sequence=13,
                void_transaction_sequence=1_000_000,
                sale_status="voided",
            ),
        ),
    )


def test_export_columns_and_widths() -> None:
    assert EXPORT_COLUMNS[:6] == (
        "business_date",
        "sale_session_id",
        "sale_transaction_number",
        "void_transaction_number",
        "sale_status",
        "sale_confirmed_at",
    )
    assert len(EXPORT_COLUMNS) == len(COLUMN_WIDTHS) == 20
    assert COLUMN_WIDTHS[:4] == (14, 38, 18, 18)


def test_csv_repeats_references_and_blanks_void_on_confirmed_rows() -> None:
    rows = list(csv.reader(io.StringIO(render_daily_sales_csv(_export()).decode("utf-8-sig"))))
    assert rows[0] == list(EXPORT_COLUMNS)
    sale_col = EXPORT_COLUMNS.index("sale_transaction_number")
    void_col = EXPORT_COLUMNS.index("void_transaction_number")
    assert [(row[sale_col], row[void_col]) for row in rows[1:]] == [
        ("TRX-000012", ""),
        ("TRX-000012", ""),
        ("TRX-000013", "TRX-1000000"),
    ]


def test_xlsx_repeats_references_and_blanks_void_on_confirmed_rows() -> None:
    sheet = load_workbook(io.BytesIO(render_daily_sales_xlsx(_export())))["Ventas"]
    assert [cell.value for cell in sheet[1]] == list(EXPORT_COLUMNS)
    sale_col = EXPORT_COLUMNS.index("sale_transaction_number")
    void_col = EXPORT_COLUMNS.index("void_transaction_number")
    values = [(row[sale_col].value, row[void_col].value) for row in sheet.iter_rows(min_row=2)]
    assert values == [("TRX-000012", None), ("TRX-000012", None), ("TRX-000013", "TRX-1000000")]
    widths = [sheet.column_dimensions[chr(64 + index)].width for index in range(1, 21)]
    assert widths == list(COLUMN_WIDTHS)
    assert sheet.auto_filter.ref == f"A1:T{sheet.max_row}"


@requires_postgres
def test_export_endpoint_exposes_sale_and_void_numbers(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    conversation_id = "conv-trx-export"
    confirmed, confirm, _card = _sale_then_void(client, token, conversation_id, "trx-export")
    sale_trx = confirmed["data"]["transaction_number"]

    def rows_now() -> list[dict[str, str]]:
        response = client.get(
            "/api/v1/operational-days/current/sales-export?format=csv",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200, response.text
        return list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))

    before = rows_now()
    assert before
    assert {row["sale_transaction_number"] for row in before} == {sale_trx}
    assert {row["void_transaction_number"] for row in before} == {""}

    voided = _void_with(client, token, conversation_id, confirm, key="trx-export-void")
    assert voided.status_code == 200, voided.text
    after = rows_now()
    assert {row["sale_transaction_number"] for row in after} == {sale_trx}
    assert {row["void_transaction_number"] for row in after} == {"TRX-000002"}
    assert {row["sale_status"] for row in after} == {"voided"}
    assert _last_value(db_session, tenant.business_id) == 2


@requires_postgres
def test_counter_sequence_count_matches_stored_entities(client: TestClient, db_session) -> None:
    """The shared stream has no gaps for committed sale + void + close."""
    tenant, token = _seed(db_session)
    confirmed, confirm, _card = _sale_then_void(client, token, "conv-trx-stream", "trx-stream")
    assert _void_with(client, token, "conv-trx-stream", confirm, key="trx-stream-void").status_code == 200
    set_current_business_id(db_session, tenant.business_id)
    db_session.expire_all()
    sequences = db_session.execute(
        text(
            """
            SELECT transaction_sequence FROM sales.sale_sessions WHERE business_id = :b
            UNION ALL
            SELECT void_transaction_sequence FROM sales.sale_sessions
            WHERE business_id = :b AND void_transaction_sequence IS NOT NULL
            """
        ),
        {"b": tenant.business_id},
    ).scalars().all()
    assert sorted(sequences) == list(range(1, _last_value(db_session, tenant.business_id) + 1))
    assert db_session.scalar(select(func.count()).select_from(SaleSessionRow)) == 1
