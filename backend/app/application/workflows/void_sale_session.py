from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from typing import Any
from uuid import UUID

from app.application.ports import AuditService, IdempotencyService, IdentityPort, Outbox, SalesPort
from app.application.workflows.commit_sale_session import build_sale_confirmed
from app.application.workflows.record_source_memory import record_voided_sale
from app.application.workflows.sync_daily_close_outcome import maintain_open_daily_close
from app.application.workflows.totalize_sale_session import _item_payloads
from app.domain.identity.onboarding import sales_allowed
from app.domain.operations import OperationalDayStatus, cash_difference, cash_status_for
from app.domain.sales import SaleSession, SaleSessionStatus, sum_session_total
from app.domain.shared.errors import OnboardingIncompleteError, ValidationAppError
from app.domain.shared.money import Money
from app.domain.shared.tenant import TenantContext
from app.domain.shared.transaction_number import format_transaction_number
from app.infrastructure.persistence.base import utcnow
from app.infrastructure.persistence.operations import OperationsRepository
from app.policies import PolicyDecision, PolicyDecisionName, PolicyRequest
from app.policies.engine import FoundationPolicyEngine


@dataclass(frozen=True, slots=True)
class VoidSaleSessionResult:
    kind: str
    text: str
    payload: dict[str, Any]


class VoidSaleSession:
    operation_type = "lumo.message.void_sale"

    def __init__(
        self,
        *,
        sales: SalesPort,
        identities: IdentityPort,
        operations: OperationsRepository,
        audit: AuditService,
        idempotency: IdempotencyService,
        outbox: Outbox,
    ) -> None:
        self._sales = sales
        self._identities = identities
        self._operations = operations
        self._audit = audit
        self._idempotency = idempotency
        self._outbox = outbox
        self._policies = FoundationPolicyEngine()

    def impact_for(
        self,
        *,
        tenant: TenantContext,
        session: SaleSession,
    ) -> dict[str, Any]:
        """Server before/after impact for void confirmation. Does not mutate."""
        business = self._identities.get_business(tenant)
        if session.operational_day_id is None:
            raise ValidationAppError("void impact requires day membership")
        payment = self._sales.get_payment_for_session(tenant=tenant, sale_session_id=session.id)
        if payment is None:
            raise ValidationAppError("void impact requires a payment")
        totals = self._operations.summarize_day(
            tenant=tenant,
            operational_day_id=session.operational_day_id,
            currency=business.currency,
        )
        sale_amount = payment.amount.amount
        after_count = max(0, totals.sale_count - 1)
        after_gross = Money(Decimal(totals.gross_sales_total) - sale_amount, business.currency)
        before_expected = Money(totals.cash_total, business.currency)
        after_expected = before_expected
        if payment.method.value == "cash":
            after_expected = Money(Decimal(totals.cash_total) - sale_amount, business.currency)
        impact: dict[str, Any] = {
            "before": {
                "sale_count": totals.sale_count,
                "gross_sales_total": Money(totals.gross_sales_total, business.currency).to_json(),
                "expected_cash": before_expected.to_json(),
            },
            "after": {
                "sale_count": after_count,
                "gross_sales_total": after_gross.to_json(),
                "expected_cash": after_expected.to_json(),
            },
        }
        current = self._operations.get_current_cash_count(
            tenant=tenant,
            operational_day_id=session.operational_day_id,
        )
        if current is not None:
            counted = Money(current.amount, business.currency)
            before_diff = cash_difference(before_expected.amount, counted.amount)
            after_diff = cash_difference(after_expected.amount, counted.amount)
            if before_diff is None or after_diff is None:
                raise ValidationAppError("cash difference requires counted cash")
            impact["before"]["counted_cash"] = counted.to_json()
            impact["after"]["counted_cash"] = counted.to_json()
            impact["before"]["cash_difference"] = Money(before_diff, business.currency).to_json()
            impact["after"]["cash_difference"] = Money(after_diff, business.currency).to_json()
            impact["before"]["cash_status"] = cash_status_for(before_diff).value
            impact["after"]["cash_status"] = cash_status_for(after_diff).value
        return impact

    def execute(
        self,
        *,
        tenant: TenantContext,
        conversation_id: str | None,
        sale_session_id: UUID,
        void_reason: str | None,
        idempotency_key: str,
        correlation_id: str,
        policy: PolicyDecision | None = None,
        fail_after_write: bool = False,
        raw_message: str = "",
        ui_action_id: str | None = None,
        voided_at: datetime | None = None,
        mutate: bool = True,
    ) -> VoidSaleSessionResult:
        business = self._identities.get_business(tenant)
        if not sales_allowed(onboarding_status=business.onboarding_status):
            raise OnboardingIncompleteError("onboarding is not completed")

        reason = (void_reason or "").strip()
        if ui_action_id is not None:
            request_hash = sha256(
                f"{ui_action_id}|{conversation_id or ''}|void|{sale_session_id}|{reason}".encode()
            ).hexdigest()
        else:
            request_hash = sha256(
                f"{raw_message}|{conversation_id or ''}|void|{sale_session_id}|{reason}".encode()
            ).hexdigest()

        replay = self._idempotency.peek(
            tenant=tenant,
            operation_type=self.operation_type,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if replay is not None:
            body = replay["body"]
            return VoidSaleSessionResult(kind="replay", text=body.get("text", "Listo."), payload=body)

        session = self._sales.get_session_by_id(
            tenant=tenant,
            sale_session_id=sale_session_id,
            for_update=True,
        )
        if session is None or (session.conversation_id or "") != (conversation_id or ""):
            return VoidSaleSessionResult(
                kind="deny",
                text="No encontré esa venta.",
                payload={"code": "SALE_NOT_FOUND", "reason_code": "sale_not_found"},
            )

        gate = self._policies.evaluate(
            PolicyRequest(
                action="execute_tool",
                tool_id="sale.void@1",
                tool_registered=True,
                from_llm=True,
                arguments={
                    "session_status": session.status.value,
                    "void_reason": reason,
                    "mutate": mutate,
                },
            )
        )

        if session.status is SaleSessionStatus.VOIDED:
            return self._read_back(tenant=tenant, session=session)

        if session.status is not SaleSessionStatus.CONFIRMED:
            return VoidSaleSessionResult(
                kind="deny",
                text="Solo puedo anular una venta ya confirmada.",
                payload={"code": "SALE_NOT_CONFIRMED", "reason_code": "sale_not_confirmed"},
            )

        if not mutate:
            impact = self.impact_for(tenant=tenant, session=session)
            items = self._sales.list_items(tenant=tenant, sale_session_id=session.id)
            payment = self._sales.get_payment_for_session(tenant=tenant, sale_session_id=session.id)
            assert payment is not None
            payload = {
                **build_sale_confirmed(session, items, payment),
                "impact": impact,
                "compose": "void_request",
            }
            return VoidSaleSessionResult(
                kind="impact",
                text="Confirma si quieres anular esta venta.",
                payload=payload,
            )

        if gate.decision is PolicyDecisionName.DENY and gate.reason_code == "void_reason_required":
            return VoidSaleSessionResult(
                kind="deny",
                text="Indica un motivo para anular la venta.",
                payload={"code": "VOID_REASON_REQUIRED", "reason_code": "void_reason_required"},
            )
        if not reason:
            return VoidSaleSessionResult(
                kind="deny",
                text="Indica un motivo para anular la venta.",
                payload={"code": "VOID_REASON_REQUIRED", "reason_code": "void_reason_required"},
            )

        if session.operational_day_id is None:
            raise ValidationAppError("confirmed sale requires operational day")
        day = self._operations.lock_day_by_id_for_update(
            tenant=tenant,
            operational_day_id=session.operational_day_id,
        )
        if day is None:
            raise ValidationAppError("operational day not found")
        if day.status is not OperationalDayStatus.OPEN:
            return VoidSaleSessionResult(
                kind="deny",
                text="La jornada ya está cerrada. No puedo anular esta venta.",
                payload={"code": "OPERATIONAL_DAY_CLOSED", "reason_code": "operational_day_closed"},
            )

        replay = self._idempotency.begin(
            tenant=tenant,
            operation_type=self.operation_type,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if replay is not None:
            body = replay["body"]
            return VoidSaleSessionResult(kind="replay", text=body.get("text", "Listo."), payload=body)

        instant = _utc_instant(voided_at)
        payment = self._sales.get_payment_for_session(tenant=tenant, sale_session_id=session.id)
        if payment is None:
            raise ValidationAppError("confirmed sale requires a payment")
        items = self._sales.list_items(tenant=tenant, sale_session_id=session.id)
        impact = self.impact_for(tenant=tenant, session=session)

        void_transaction_sequence = self._operations.allocate_transaction_sequence(tenant=tenant)
        updated = self._sales.void_session(
            tenant=tenant,
            sale_session_id=session.id,
            voided_at=instant,
            voided_by_actor_id=tenant.actor_id,
            void_reason=reason,
            void_transaction_sequence=void_transaction_sequence,
        )
        payload = build_voided_sale(updated, items, payment)
        payload["impact"] = impact
        payload["compose"] = "sale_voided"

        policy_payload = policy.model_dump() if policy is not None else None
        self._audit.record(
            tenant=tenant,
            action="sale.void@1",
            route_or_tool="sale.void@1",
            result="committed",
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            policy_decision=policy_payload,
            after_payload={
                "sale_session_id": str(updated.id),
                "status": updated.status.value,
                "void_reason": updated.void_reason,
                "transaction_number": payload["transaction_number"],
                "original_transaction_number": payload["original_transaction_number"],
                "voided_at": instant.isoformat(),
                "voided_by_actor_id": str(tenant.actor_id),
                **({"ui_action_id": ui_action_id} if ui_action_id else {}),
            },
        )
        self._outbox.enqueue(
            tenant=tenant,
            event_type="sale.voided",
            payload={
                "sale_session_id": str(updated.id),
                "payment_id": str(payment.id),
                "operational_day_id": str(updated.operational_day_id),
            },
        )
        record_voided_sale(
            operations=self._operations,
            tenant=tenant,
            operational_day_id=updated.operational_day_id,  # type: ignore[arg-type]
            sale_session_id=updated.id,
            payment_id=payment.id,
            payment_method=payment.method.value,
            amount=payment.amount.amount,
            currency=payment.amount.currency,
            void_reason=reason,
            voided_by_actor_id=tenant.actor_id,
            transaction_number=payload["transaction_number"],
            original_transaction_number=payload["original_transaction_number"],
            occurred_at=instant,
            created_at=instant,
        )
        maintain_open_daily_close(
            identities=self._identities,
            operations=self._operations,
            audit=self._audit,
            tenant=tenant,
            now=instant,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            route_or_tool="sale.void@1",
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
        return VoidSaleSessionResult(kind="committed", text=payload["text"], payload=payload)

    def _read_back(self, *, tenant: TenantContext, session: SaleSession) -> VoidSaleSessionResult:
        items = self._sales.list_items(tenant=tenant, sale_session_id=session.id)
        payment = self._sales.get_payment_for_session(tenant=tenant, sale_session_id=session.id)
        if payment is None:
            raise ValidationAppError("voided sale requires a payment")
        payload = build_voided_sale(session, items, payment)
        payload["compose"] = "sale_voided"
        return VoidSaleSessionResult(kind="read_back", text=payload["text"], payload=payload)


def build_voided_sale(session: SaleSession, items: list, payment) -> dict[str, Any]:
    base = build_sale_confirmed(session, items, payment)
    base["status"] = SaleSessionStatus.VOIDED.value
    base["void_reason"] = session.void_reason
    base["voided_at"] = session.voided_at.isoformat() if session.voided_at else None
    base["voided_by_actor_id"] = str(session.voided_by_actor_id) if session.voided_by_actor_id else None
    amount = base["total"]["amount"]
    base["text"] = f"Venta anulada · ${amount}"
    base["items"] = _item_payloads(items)
    # Void-result semantics (ADR-033): ``transaction_number`` identifies the void
    # transaction; the sale identity stays in ``original_transaction_number``.
    if session.transaction_sequence is None or session.void_transaction_sequence is None:
        raise ValidationAppError("voided sale requires stored transaction references")
    base["original_transaction_number"] = format_transaction_number(session.transaction_sequence)
    base["transaction_number"] = format_transaction_number(session.void_transaction_sequence)
    return base


def _utc_instant(value: datetime | None) -> datetime:
    instant = value if value is not None else utcnow()
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValidationAppError("voided_at must be timezone-aware UTC")
    return instant.astimezone(UTC)
