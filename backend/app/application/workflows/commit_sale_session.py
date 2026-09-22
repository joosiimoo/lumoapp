from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

from app.application.ports import AuditService, IdempotencyService, IdentityPort, Outbox, SalesPort
from app.domain.operations import InvalidBusinessTimezone, business_date_for
from app.infrastructure.persistence.base import utcnow
from app.infrastructure.persistence.operations import OperationsRepository
from app.application.workflows.totalize_sale_session import _item_payloads
from app.domain.sales import (
    PAYMENT_METHOD_LABELS,
    CommitKind,
    Payment,
    PaymentMethod,
    PaymentSource,
    PaymentStatus,
    SaleItem,
    SaleSession,
    SaleSessionStatus,
    classify_commit,
    sum_session_total,
)
from app.domain.shared.errors import ValidationAppError
from app.domain.shared.ids import new_uuid7
from app.domain.shared.tenant import TenantContext
from app.policies import PolicyDecision, PolicyRequest
from app.policies.engine import FoundationPolicyEngine


@dataclass(frozen=True, slots=True)
class CommitWorkflowResult:
    kind: str
    text: str
    payload: dict[str, Any]


def build_sale_confirmed(session: SaleSession, items: list[SaleItem], payment: Payment) -> dict[str, Any]:
    total = sum_session_total(items, currency=session.currency)
    count = len(items)
    noun = "artículo" if count == 1 else "artículos"
    amount = total.to_json()["amount"]
    method_label = PAYMENT_METHOD_LABELS[payment.method]
    return {
        "sale_session_id": str(session.id),
        "payment_id": str(payment.id),
        "status": SaleSessionStatus.CONFIRMED.value,
        "currency": session.currency,
        "item_count": count,
        "total": total.to_json(),
        "payment": {
            "method": payment.method.value,
            "amount": payment.amount.to_json(),
            "status": PaymentStatus.RECORDED.value,
        },
        "items": _item_payloads(items),
        "text": f"Venta registrada · {count} {noun} · ${amount} · {method_label}",
    }


class CommitSaleSession:
    operation_type = "lumo.message.commit_sale"

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

    def execute(
        self,
        *,
        tenant: TenantContext,
        conversation_id: str | None,
        payment_method: str | None,
        idempotency_key: str,
        correlation_id: str,
        policy: PolicyDecision | None = None,
        fail_after_write: bool = False,
        raw_message: str = "",
        confirmed_at: datetime | None = None,
    ) -> CommitWorkflowResult:
        request_hash = sha256(
            f"{raw_message}|{conversation_id or ''}|commit|{payment_method or ''}".encode()
        ).hexdigest()
        replay = self._idempotency.peek(
            tenant=tenant,
            operation_type=self.operation_type,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if replay is not None:
            body = replay["body"]
            return CommitWorkflowResult(kind="replay", text=body.get("text", "Listo."), payload=body)

        session = self._sales.get_active_session(
            tenant=tenant,
            conversation_id=conversation_id,
            for_update=True,
        )
        confirmed = None
        if session is None:
            confirmed = self._sales.get_latest_confirmed_session(
                tenant=tenant,
                conversation_id=conversation_id,
            )
        kind = classify_commit(
            session.status if session is not None else None,
            confirmed_exists=confirmed is not None,
        )
        status_value = (
            session.status.value
            if session is not None
            else (confirmed.status.value if confirmed is not None else None)
        )
        gate = self._policies.evaluate(
            PolicyRequest(
                action="execute_tool",
                tool_id="sale.commit@1",
                tool_registered=True,
                from_llm=True,
                arguments={
                    "session_status": status_value,
                    "payment_method": payment_method,
                },
            )
        )
        if gate.reason_code == "payment_method_unknown" or payment_method not in {"cash", "card", "transfer"}:
            return CommitWorkflowResult(
                kind="clarify",
                text="¿Cómo pagó? Puedo registrar *efectivo*, *tarjeta* o *transferencia*.",
                payload={"code": "PAYMENT_METHOD_UNKNOWN"},
            )
        if kind is CommitKind.NOT_READY or (session is not None and session.status is SaleSessionStatus.OPEN):
            return CommitWorkflowResult(
                kind="clarify",
                text="Esta venta aún no está lista para cobrar. Totaliza primero.",
                payload={"code": "SALE_NOT_READY_TO_CHARGE"},
            )
        if kind is CommitKind.NOT_FOUND or gate.reason_code == "sale_not_found":
            return CommitWorkflowResult(
                kind="clarify",
                text="No hay una venta para cobrar. Agrega un producto primero.",
                payload={"code": "SALE_NOT_FOUND"},
            )

        if kind is CommitKind.READ_BACK:
            assert confirmed is not None
            items = self._sales.list_items(tenant=tenant, sale_session_id=confirmed.id)
            payment = self._sales.get_payment_for_session(tenant=tenant, sale_session_id=confirmed.id)
            if payment is None:
                return CommitWorkflowResult(
                    kind="clarify",
                    text="No hay una venta para cobrar. Agrega un producto primero.",
                    payload={"code": "SALE_NOT_FOUND"},
                )
            payload = build_sale_confirmed(confirmed, items, payment)
            return CommitWorkflowResult(kind="read_back", text=payload["text"], payload=payload)

        assert session is not None
        business = self._identities.get_business(tenant)
        instant = _utc_instant(confirmed_at)
        try:
            business_date = business_date_for(instant, business.timezone)
        except InvalidBusinessTimezone as exc:
            raise ValidationAppError("invalid business timezone") from exc
        existing_day = self._operations.lock_day_for_update(tenant=tenant, business_date=business_date)
        if existing_day is not None and existing_day.status.value == "closed":
            return CommitWorkflowResult(
                kind="clarify",
                text="La jornada de hoy ya está cerrada. No puedo registrar otra venta en ese día.",
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
            return CommitWorkflowResult(kind="replay", text=body.get("text", "Listo."), payload=body)

        day, created = self._operations.ensure_open_day(
            tenant=tenant,
            business_date=business_date,
            timezone_name=business.timezone,
            day_id=new_uuid7(),
            opened_at=instant,
        )
        items = self._sales.list_items(tenant=tenant, sale_session_id=session.id)
        total = sum_session_total(items, currency=session.currency)
        if session.currency != business.currency:
            raise ValidationAppError("sale currency does not match the business")
        method = PaymentMethod(payment_method)
        payment = self._sales.add_payment(
            tenant=tenant,
            payment=Payment(
                id=new_uuid7(),
                business_id=tenant.business_id,
                sale_session_id=session.id,
                actor_id=tenant.actor_id,
                method=method,
                amount=total,
                status=PaymentStatus.RECORDED,
                source=PaymentSource.MANUAL_CAPTURE,
            ),
        )
        updated = self._sales.confirm_session(
            tenant=tenant,
            sale_session_id=session.id,
            operational_day_id=day.id,
            confirmed_at=instant,
        )
        payload = build_sale_confirmed(updated, items, payment)
        policy_payload = policy.model_dump() if policy is not None else None
        self._audit.record(
            tenant=tenant,
            action="sale.commit@1",
            route_or_tool="sale.commit@1",
            result="committed",
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            policy_decision=policy_payload,
            after_payload={
                "sale_session_id": payload["sale_session_id"],
                "payment_id": payload["payment_id"],
                "status": payload["status"],
                "item_count": payload["item_count"],
                "total": payload["total"],
                "method": payment.method.value,
                "operational_day_id": str(day.id),
                "business_date": business_date.isoformat(),
                "confirmed_at": instant.isoformat(),
            },
        )
        if created:
            opened = {
                "operational_day_id": str(day.id),
                "business_date": business_date.isoformat(),
                "timezone": day.timezone,
                "status": day.status.value,
            }
            self._audit.record(
                tenant=tenant,
                action="operational_day.opened",
                route_or_tool="sale.commit@1",
                result="opened",
                correlation_id=correlation_id,
                idempotency_key=idempotency_key,
                policy_decision=policy_payload,
                after_payload=opened,
            )
            self._outbox.enqueue(
                tenant=tenant,
                event_type="operational_day.opened",
                payload=opened,
            )
        self._outbox.enqueue(
            tenant=tenant,
            event_type="sale.confirmed",
            payload={
                "sale_session_id": str(updated.id),
                "payment_id": str(payment.id),
                "operational_day_id": str(day.id),
            },
        )
        self._outbox.enqueue(
            tenant=tenant,
            event_type="payment.recorded",
            payload={"payment_id": str(payment.id), "sale_session_id": str(updated.id)},
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
        return CommitWorkflowResult(kind="committed", text=payload["text"], payload=payload)


def _utc_instant(value: datetime | None) -> datetime:
    instant = value if value is not None else utcnow()
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValidationAppError("confirmed_at must be timezone-aware UTC")
    return instant.astimezone(UTC)
