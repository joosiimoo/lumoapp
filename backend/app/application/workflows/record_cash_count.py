from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
from typing import Any

from app.application.ports import AuditService, IdempotencyService, IdentityPort, Outbox
from app.application.workflows.get_daily_close_preparation import (
    build_close_preparation,
    business_date_now,
)
from app.application.workflows.sync_daily_close_work_items import sync_daily_close_work_items
from app.domain.operations import CashCount, CashCountSource, OperationalDayStatus, parse_counted_amount
from app.domain.shared.ids import new_uuid7
from app.domain.shared.tenant import TenantContext
from app.infrastructure.persistence.operations import OperationsRepository
from app.policies import PolicyDecision, PolicyRequest
from app.policies.engine import FoundationPolicyEngine

NO_DAY_TEXT = (
    "Todavía no hay ventas registradas hoy, así que aún no puedo comparar el efectivo. "
    "Registra la primera venta del día y vuelve a contar la caja."
)


@dataclass(frozen=True, slots=True)
class RecordCashCountResult:
    kind: str
    text: str
    payload: dict[str, Any]


class RecordCashCount:
    """closing.submit_cash_count@1. One application transaction, steps A-L of design §7."""

    operation_type = "lumo.message.record_cash_count"

    def __init__(
        self,
        *,
        identities: IdentityPort,
        operations: OperationsRepository,
        audit: AuditService,
        idempotency: IdempotencyService,
        outbox: Outbox,
    ) -> None:
        self._identities = identities
        self._operations = operations
        self._audit = audit
        self._idempotency = idempotency
        self._outbox = outbox
        self._policies = FoundationPolicyEngine()

    def execute(
        self,
        *,
        tenant: TenantContext,
        conversation_id: str | None,
        counted_amount: str | None,
        idempotency_key: str,
        correlation_id: str,
        policy: PolicyDecision | None = None,
        fail_after_write: bool = False,
        raw_message: str = "",
        counted_at: datetime | None = None,
    ) -> RecordCashCountResult:
        amount = parse_counted_amount(counted_amount)
        request_hash = sha256(
            f"{raw_message}|{conversation_id or ''}|record_cash_count|{amount}".encode()
        ).hexdigest()

        # A. Peek before the day lock. A completed record is immutable persisted state, so the
        # stored body is returned verbatim even if expected cash moved since that count.
        replay = self._idempotency.peek(
            tenant=tenant,
            operation_type=self.operation_type,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if replay is not None:
            body = replay["body"]
            return RecordCashCountResult(kind="replay", text=body.get("text", "Listo."), payload=body)

        # B, C. Business timezone and currency, then one clock reading.
        business = self._identities.get_business(tenant)
        instant, business_date = business_date_now(timezone_name=business.timezone, now=counted_at)

        # D. Lock the day. A cash count never creates one.
        day = self._operations.lock_day_for_update(tenant=tenant, business_date=business_date)
        if day is None:
            gate = self._policies.evaluate(
                PolicyRequest(
                    action="execute_tool",
                    tool_id="closing.submit_cash_count@1",
                    tool_registered=True,
                    from_llm=True,
                    arguments={"day_exists": False},
                )
            )
            return RecordCashCountResult(
                kind="clarify",
                text=NO_DAY_TEXT,
                payload={"code": "OPERATIONAL_DAY_NOT_STARTED", "reason_code": gate.reason_code},
            )

        if day.status is OperationalDayStatus.CLOSED:
            return RecordCashCountResult(
                kind="clarify",
                text="La jornada de hoy ya está cerrada. No puedo cambiar el conteo.",
                payload={"code": "OPERATIONAL_DAY_CLOSED", "reason_code": "operational_day_closed"},
            )

        # E. Expected cash under the lock.
        expected_cash = self._operations.expected_cash(
            tenant=tenant,
            operational_day_id=day.id,
            currency=business.currency,
        )
        totals = self._operations.summarize_day(
            tenant=tenant,
            operational_day_id=day.id,
            currency=business.currency,
        )

        # F. Current count. An equal amount changes nothing, so it must not reserve a key.
        previous = self._operations.get_current_cash_count(tenant=tenant, operational_day_id=day.id)
        if previous is not None and Decimal(previous.amount) == amount:
            payload = self._payload(
                business_date=business_date,
                currency=business.currency,
                day=day,
                sale_count=totals.sale_count,
                expected_cash=expected_cash,
                count=previous,
                supersedes=previous.supersedes_cash_count_id,
            )
            return RecordCashCountResult(kind="read_back", text=payload["text"], payload=payload)

        # G. Only now reserve the key.
        replay = self._idempotency.begin(
            tenant=tenant,
            operation_type=self.operation_type,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if replay is not None:
            body = replay["body"]
            return RecordCashCountResult(kind="replay", text=body.get("text", "Listo."), payload=body)

        # H. Retire the previous row before inserting the new one.
        new_count_id = new_uuid7()
        if previous is not None:
            self._operations.mark_superseded(
                tenant=tenant,
                previous_id=previous.id,
                new_id=new_count_id,
                updated_at=instant,
            )
        count = self._operations.insert_cash_count(
            tenant=tenant,
            cash_count=CashCount(
                id=new_count_id,
                business_id=tenant.business_id,
                operational_day_id=day.id,
                actor_id=tenant.actor_id,
                amount=amount,
                currency=business.currency,
                source=CashCountSource.MANUAL_CAPTURE,
                counted_at=instant,
                supersedes_cash_count_id=previous.id if previous is not None else None,
            ),
        )
        payload = self._payload(
            business_date=business_date,
            currency=business.currency,
            day=day,
            sale_count=totals.sale_count,
            expected_cash=expected_cash,
            count=count,
            supersedes=count.supersedes_cash_count_id,
        )

        # I. Audit.
        policy_payload = policy.model_dump() if policy is not None else None
        self._audit.record(
            tenant=tenant,
            action="closing.submit_cash_count@1",
            route_or_tool="closing.submit_cash_count@1",
            result="committed",
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            policy_decision=policy_payload,
            before_payload=(
                {
                    "cash_count_id": str(previous.id),
                    "amount": _amount_string(previous.amount),
                }
                if previous is not None
                else None
            ),
            after_payload={
                "cash_count_id": payload["cash_count_id"],
                "operational_day_id": payload["operational_day_id"],
                "business_date": payload["business_date"],
                "amount": payload["counted_cash"]["amount"],
                "currency": payload["currency"],
                "expected_cash": payload["expected_cash"]["amount"],
                "cash_difference": payload["cash_difference"]["amount"],
                "cash_status": payload["cash_status"],
                "counted_at": payload["counted_at"],
                "supersedes_cash_count_id": payload["supersedes_cash_count_id"],
            },
        )

        # J. Outbox.
        self._outbox.enqueue(
            tenant=tenant,
            event_type="cash_count.recorded",
            payload={
                "cash_count_id": payload["cash_count_id"],
                "operational_day_id": payload["operational_day_id"],
                "business_date": payload["business_date"],
                "amount": payload["counted_cash"]["amount"],
                "currency": payload["currency"],
                "supersedes_cash_count_id": payload["supersedes_cash_count_id"],
            },
        )
        sync_daily_close_work_items(
            identities=self._identities,
            operations=self._operations,
            audit=self._audit,
            tenant=tenant,
            now=instant,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            route_or_tool="closing.submit_cash_count@1",
        )
        if fail_after_write:
            raise RuntimeError("forced rollback")

        # K. Complete the record. L. Commit is owned by the request transaction.
        self._idempotency.complete(
            tenant=tenant,
            operation_type=self.operation_type,
            key=idempotency_key,
            status_code=200,
            body=payload,
        )
        return RecordCashCountResult(kind="committed", text=payload["text"], payload=payload)

    def _payload(
        self,
        *,
        business_date,
        currency: str,
        day,
        sale_count: int,
        expected_cash: str,
        count: CashCount,
        supersedes,
    ) -> dict[str, Any]:
        payload = build_close_preparation(
            business_date=business_date,
            currency=currency,
            day=day,
            sale_count=sale_count,
            expected_cash=expected_cash,
            count=count,
        )
        payload["supersedes_cash_count_id"] = str(supersedes) if supersedes is not None else None
        return payload


def _amount_string(amount: Decimal) -> str:
    return f"{Decimal(amount):.2f}"
