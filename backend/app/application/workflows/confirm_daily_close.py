from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
from typing import Any

from app.application.closing_confirmation_token import (
    TokenVerdict,
    issue_closing_confirmation_token,
    verify_closing_confirmation_token,
)
from app.application.ports import AuditService, IdempotencyService, IdentityPort, Outbox
from app.application.workflows.get_daily_close_preparation import (
    CASH_COUNT_REQUIRED_TEXT,
    NO_OPEN_DAY_TEXT,
    STALE_CONFIRMATION_TEXT,
    build_close_preparation,
    build_confirmed_close,
    business_date_now,
    fingerprint_for_preparation,
)
from app.domain.operations import ClosingSnapshot, OperationalDayStatus, cash_difference, cash_status_for
from app.domain.shared.errors import ValidationAppError
from app.domain.shared.ids import new_uuid7
from app.domain.shared.tenant import TenantContext
from app.infrastructure.persistence.operations import OperationsRepository

CONFIRMATION_REQUIRED_TEXT = "Para cerrar, confirma el resumen del cierre."
CONFIRMATION_INVALID_TEXT = "Esa confirmación no es válida. Pide el cierre otra vez."


@dataclass(frozen=True, slots=True)
class ConfirmDailyCloseResult:
    kind: str
    text: str
    payload: dict[str, Any]


class ConfirmDailyClose:
    """closing.confirm@1. One application transaction, design §7 steps 1–13."""

    operation_type = "lumo.message.confirm_close"

    def __init__(
        self,
        *,
        identities: IdentityPort,
        operations: OperationsRepository,
        audit: AuditService,
        idempotency: IdempotencyService,
        outbox: Outbox,
        token_secret: str,
    ) -> None:
        self._identities = identities
        self._operations = operations
        self._audit = audit
        self._idempotency = idempotency
        self._outbox = outbox
        self._token_secret = token_secret

    def execute(
        self,
        *,
        tenant: TenantContext,
        conversation_id: str | None,
        confirmation_token: str | None,
        idempotency_key: str,
        correlation_id: str,
        policy: Any = None,
        fail_after_write: bool = False,
        raw_message: str = "",
        now: datetime | None = None,
        hash_material: str | None = None,
        ui_action_id: str | None = None,
    ) -> ConfirmDailyCloseResult:
        token = confirmation_token or ""
        if hash_material is not None:
            request_hash = sha256(hash_material.encode()).hexdigest()
        else:
            request_hash = sha256(
                f"{raw_message}|{conversation_id or ''}|{token}".encode()
            ).hexdigest()

        replay = self._peek(tenant, idempotency_key, request_hash)
        if replay is not None:
            return replay

        business = self._identities.get_business(tenant)
        instant, business_date = business_date_now(timezone_name=business.timezone, now=now)
        day = self._operations.lock_day_for_update(tenant=tenant, business_date=business_date)
        if day is None:
            return ConfirmDailyCloseResult(
                kind="clarify",
                text=NO_OPEN_DAY_TEXT,
                payload={"code": "OPERATIONAL_DAY_NOT_STARTED", "reason_code": "operational_day_not_started"},
            )

        replay = self._peek(tenant, idempotency_key, request_hash)
        if replay is not None:
            return replay

        if day.status is OperationalDayStatus.CLOSED:
            snapshot = self._operations.get_snapshot_for_day(tenant=tenant, operational_day_id=day.id)
            if snapshot is None:
                raise ValidationAppError("closed day is missing its closing snapshot")
            payload = build_confirmed_close(snapshot)
            return ConfirmDailyCloseResult(kind="read_back", text=payload["text"], payload=payload)

        count = self._operations.get_current_cash_count(tenant=tenant, operational_day_id=day.id)
        if count is None:
            return ConfirmDailyCloseResult(
                kind="clarify",
                text=CASH_COUNT_REQUIRED_TEXT,
                payload={"code": "CASH_COUNT_REQUIRED", "reason_code": "cash_count_required"},
            )

        totals = self._operations.summarize_day(
            tenant=tenant,
            operational_day_id=day.id,
            currency=business.currency,
        )
        live = build_close_preparation(
            business_date=day.business_date,
            currency=business.currency,
            day=day,
            sale_count=totals.sale_count,
            expected_cash=totals.cash_total,
            count=count,
            totals=totals,
        )
        if live["cash_status"] == "not_counted":
            return ConfirmDailyCloseResult(
                kind="clarify",
                text=CASH_COUNT_REQUIRED_TEXT,
                payload={"code": "CASH_COUNT_REQUIRED", "reason_code": "cash_count_required"},
            )
        fingerprint = fingerprint_for_preparation(live, business_id=tenant.business_id)
        verdict = verify_closing_confirmation_token(
            secret=self._token_secret,
            token=confirmation_token,
            business_id=tenant.business_id,
            actor_id=tenant.actor_id,
            operational_day_id=day.id,
            cash_count_id=count.id,
            fingerprint=fingerprint,
            now=instant,
        )
        if verdict is TokenVerdict.MISSING:
            return ConfirmDailyCloseResult(
                kind="clarify",
                text=CONFIRMATION_REQUIRED_TEXT,
                payload={"code": "CONFIRMATION_REQUIRED", "reason_code": "confirmation_required"},
            )
        if verdict is TokenVerdict.INVALID:
            return ConfirmDailyCloseResult(
                kind="clarify",
                text=CONFIRMATION_INVALID_TEXT,
                payload={"code": "CONFIRMATION_INVALID", "reason_code": "confirmation_invalid"},
            )
        if verdict is TokenVerdict.STALE:
            live["confirmation_token"] = issue_closing_confirmation_token(
                secret=self._token_secret,
                business_id=tenant.business_id,
                actor_id=tenant.actor_id,
                operational_day_id=day.id,
                cash_count_id=count.id,
                fingerprint=fingerprint,
                issued_at=instant,
            )
            live["text"] = STALE_CONFIRMATION_TEXT
            return ConfirmDailyCloseResult(kind="stale", text=STALE_CONFIRMATION_TEXT, payload=live)

        difference = cash_difference(Decimal(totals.cash_total), count.amount)
        status = cash_status_for(difference)
        if status.value == "not_counted" or difference is None:
            raise ValidationAppError("a closing snapshot cannot be not_counted")

        replay = self._idempotency.begin(
            tenant=tenant,
            operation_type=self.operation_type,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if replay is not None:
            body = replay["body"]
            return ConfirmDailyCloseResult(kind="replay", text=body.get("text", "Listo."), payload=body)

        snapshot = self._operations.insert_snapshot(
            tenant=tenant,
            snapshot=ClosingSnapshot(
                id=new_uuid7(),
                business_id=tenant.business_id,
                operational_day_id=day.id,
                cash_count_id=count.id,
                actor_id=tenant.actor_id,
                business_date=day.business_date,
                currency=business.currency,
                sale_count=totals.sale_count,
                gross_sales_total=Decimal(totals.gross_sales_total),
                cash_total=Decimal(totals.cash_total),
                card_total=Decimal(totals.card_total),
                transfer_total=Decimal(totals.transfer_total),
                expected_cash=Decimal(totals.cash_total),
                counted_cash=count.amount,
                cash_difference=difference,
                cash_status=status,
                closed_at=instant,
                created_at=instant,
                updated_at=instant,
            ),
        )
        self._operations.close_open_day(
            tenant=tenant,
            operational_day_id=day.id,
            closed_at=instant,
        )
        payload = build_confirmed_close(snapshot)
        policy_payload = policy.model_dump() if policy is not None and hasattr(policy, "model_dump") else None
        self._audit.record(
            tenant=tenant,
            action="closing.confirm@1",
            route_or_tool="closing.confirm@1",
            result="committed",
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            policy_decision=policy_payload,
            before_payload={
                "status": "open",
                "operational_day_id": str(day.id),
                "cash_count_id": str(count.id),
            },
            after_payload={
                "closing_snapshot_id": payload["closing_snapshot_id"],
                "operational_day_id": payload["operational_day_id"],
                "cash_count_id": str(count.id),
                "business_date": payload["business_date"],
                "currency": payload["currency"],
                "sale_count": payload["sale_count"],
                "gross_sales_total": payload["gross_sales_total"]["amount"],
                "cash_total": totals.cash_total,
                "card_total": totals.card_total,
                "transfer_total": totals.transfer_total,
                "expected_cash": payload["expected_cash"]["amount"],
                "counted_cash": payload["counted_cash"]["amount"],
                "cash_difference": payload["cash_difference"]["amount"],
                "cash_status": payload["cash_status"],
                "closed_at": payload["closed_at"],
                "previous_status": "open",
                "new_status": "closed",
                **({"ui_action_id": ui_action_id} if ui_action_id else {}),
            },
        )
        self._outbox.enqueue(
            tenant=tenant,
            event_type="closing.confirmed",
            payload={
                "closing_snapshot_id": payload["closing_snapshot_id"],
                "operational_day_id": payload["operational_day_id"],
                "cash_count_id": str(count.id),
                "business_date": payload["business_date"],
                "currency": payload["currency"],
                "sale_count": payload["sale_count"],
                "gross_sales_total": payload["gross_sales_total"]["amount"],
                "cash_total": totals.cash_total,
                "card_total": totals.card_total,
                "transfer_total": totals.transfer_total,
                "expected_cash": payload["expected_cash"]["amount"],
                "counted_cash": payload["counted_cash"]["amount"],
                "cash_difference": payload["cash_difference"]["amount"],
                "cash_status": payload["cash_status"],
                "closed_at": payload["closed_at"],
            },
        )
        if fail_after_write:
            raise RuntimeError("forced rollback")
        self._idempotency.complete(
            tenant=tenant,
            operation_type=self.operation_type,
            key=idempotency_key,
            status_code=200,
            body=payload,
        )
        return ConfirmDailyCloseResult(kind="committed", text=payload["text"], payload=payload)

    def _peek(self, tenant: TenantContext, key: str, request_hash: str) -> ConfirmDailyCloseResult | None:
        replay = self._idempotency.peek(
            tenant=tenant,
            operation_type=self.operation_type,
            key=key,
            request_hash=request_hash,
        )
        if replay is None:
            return None
        body = replay["body"]
        return ConfirmDailyCloseResult(kind="replay", text=body.get("text", "Listo."), payload=body)
