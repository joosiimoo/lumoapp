from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from app.application.ports import AuditService, IdempotencyService, Outbox, SalesPort
from app.domain.sales import (
    SaleItem,
    SaleSession,
    SaleSessionStatus,
    TotalizeKind,
    classify_totalize,
    format_normalized_quantity,
    sum_session_total,
)
from app.domain.shared.tenant import TenantContext
from app.policies import PolicyDecision, PolicyDecisionName, PolicyRequest
from app.policies.engine import FoundationPolicyEngine


@dataclass(frozen=True, slots=True)
class TotalizeWorkflowResult:
    kind: str
    text: str
    payload: dict[str, Any]


def _item_payloads(items: list[SaleItem]) -> list[dict[str, Any]]:
    return [
        {
            "sale_item_id": str(item.id),
            "product_name": item.product_name_snapshot,
            "quantity_normalized": format_normalized_quantity(item.quantity_normalized, item.unit_normalized),
            "unit_normalized": item.unit_normalized.value,
            "unit_price": item.unit_price.to_json(),
            "line_total": item.line_total.to_json(),
        }
        for item in items
    ]


def build_sale_summary(session: SaleSession, items: list[SaleItem]) -> dict[str, Any]:
    total = sum_session_total(items, currency=session.currency)
    count = len(items)
    noun = "artículo" if count == 1 else "artículos"
    amount = total.to_json()["amount"]
    return {
        "sale_session_id": str(session.id),
        "status": SaleSessionStatus.READY_TO_CHARGE.value,
        "currency": session.currency,
        "item_count": count,
        "subtotal": total.to_json(),
        "total": total.to_json(),
        "items": _item_payloads(items),
        "text": f"Venta lista para cobrar · {count} {noun} · ${amount}",
    }


class TotalizeSaleSession:
    operation_type = "lumo.message.totalize_sale"

    def __init__(
        self,
        *,
        sales: SalesPort,
        audit: AuditService,
        idempotency: IdempotencyService,
        outbox: Outbox,
    ) -> None:
        self._sales = sales
        self._audit = audit
        self._idempotency = idempotency
        self._outbox = outbox
        self._policies = FoundationPolicyEngine()

    def execute(
        self,
        *,
        tenant: TenantContext,
        conversation_id: str | None,
        idempotency_key: str,
        correlation_id: str,
        policy: PolicyDecision | None = None,
        fail_after_write: bool = False,
        raw_message: str = "",
    ) -> TotalizeWorkflowResult:
        request_hash = sha256(f"{raw_message}|{conversation_id or ''}|totalize".encode()).hexdigest()
        replay = self._idempotency.peek(
            tenant=tenant,
            operation_type=self.operation_type,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if replay is not None:
            body = replay["body"]
            return TotalizeWorkflowResult(kind="replay", text=body.get("text", "Listo."), payload=body)

        session = self._sales.get_active_session(
            tenant=tenant,
            conversation_id=conversation_id,
            for_update=True,
        )
        items = self._sales.list_items(tenant=tenant, sale_session_id=session.id) if session is not None else []
        kind = classify_totalize(session.status if session is not None else None, len(items))
        gate = self._policies.evaluate(
            PolicyRequest(
                action="execute_tool",
                tool_id="sale.totalize@1",
                tool_registered=True,
                from_llm=True,
                arguments={
                    "session_status": session.status.value if session is not None else None,
                    "item_count": len(items),
                },
            )
        )
        if kind is TotalizeKind.EMPTY or gate.decision is PolicyDecisionName.DENY:
            return TotalizeWorkflowResult(
                kind="clarify",
                text="No hay artículos para totalizar. Agrega un producto primero.",
                payload={"code": "SALE_EMPTY"},
            )

        if kind is TotalizeKind.READ_BACK:
            same_key = self._idempotency.peek(
                tenant=tenant,
                operation_type=self.operation_type,
                key=idempotency_key,
                request_hash=request_hash,
            )
            if same_key is not None:
                body = same_key["body"]
                return TotalizeWorkflowResult(kind="replay", text=body.get("text", "Listo."), payload=body)
            assert session is not None
            payload = build_sale_summary(session, items)
            return TotalizeWorkflowResult(kind="read_back", text=payload["text"], payload=payload)

        replay = self._idempotency.begin(
            tenant=tenant,
            operation_type=self.operation_type,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if replay is not None:
            body = replay["body"]
            return TotalizeWorkflowResult(kind="replay", text=body.get("text", "Listo."), payload=body)

        assert session is not None
        updated = self._sales.update_session_status(
            tenant=tenant,
            sale_session_id=session.id,
            status=SaleSessionStatus.READY_TO_CHARGE,
        )
        payload = build_sale_summary(updated, items)
        policy_payload = policy.model_dump() if policy is not None else None
        self._audit.record(
            tenant=tenant,
            action="sale.totalize@1",
            route_or_tool="sale.totalize@1",
            result="committed",
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            policy_decision=policy_payload,
            after_payload={
                "sale_session_id": payload["sale_session_id"],
                "status": payload["status"],
                "item_count": payload["item_count"],
                "total": payload["total"],
            },
        )
        self._outbox.enqueue(
            tenant=tenant,
            event_type="sale.ready_to_charge",
            payload={"sale_session_id": str(updated.id)},
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
        return TotalizeWorkflowResult(kind="committed", text=payload["text"], payload=payload)
