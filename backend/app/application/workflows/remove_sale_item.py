from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any
from uuid import UUID

from app.application.ports import AuditService, IdempotencyService, IdentityPort, Outbox, SalesPort
from app.application.workflows.totalize_sale_session import _item_payloads, build_sale_summary
from app.domain.identity.onboarding import sales_allowed
from app.domain.sales import SaleSessionStatus, sum_session_total
from app.domain.shared.errors import OnboardingIncompleteError, ValidationAppError
from app.domain.shared.tenant import TenantContext
from app.policies import PolicyDecision, PolicyDecisionName, PolicyRequest
from app.policies.engine import FoundationPolicyEngine

UI_ACTION_STALE_TEXT = "Esta acción ya no aplica a la venta en curso."


@dataclass(frozen=True, slots=True)
class RemoveSaleItemResult:
    kind: str
    text: str
    payload: dict[str, Any]


class RemoveSaleItem:
    operation_type = "lumo.message.remove_sale_item"

    def __init__(
        self,
        *,
        sales: SalesPort,
        identities: IdentityPort,
        audit: AuditService,
        idempotency: IdempotencyService,
        outbox: Outbox,
    ) -> None:
        self._sales = sales
        self._identities = identities
        self._audit = audit
        self._idempotency = idempotency
        self._outbox = outbox
        self._policies = FoundationPolicyEngine()

    def execute(
        self,
        *,
        tenant: TenantContext,
        conversation_id: str | None,
        sale_session_id: UUID,
        sale_item_id: UUID,
        idempotency_key: str,
        correlation_id: str,
        policy: PolicyDecision | None = None,
        fail_after_write: bool = False,
        raw_message: str = "",
        ui_action_id: str | None = None,
    ) -> RemoveSaleItemResult:
        business = self._identities.get_business(tenant)
        if not sales_allowed(onboarding_status=business.onboarding_status):
            raise OnboardingIncompleteError("onboarding is not completed")

        if ui_action_id is not None:
            request_hash = sha256(
                f"{ui_action_id}|{conversation_id or ''}|remove|{sale_session_id}|{sale_item_id}".encode()
            ).hexdigest()
        else:
            request_hash = sha256(
                f"{raw_message}|{conversation_id or ''}|remove|{sale_session_id}|{sale_item_id}".encode()
            ).hexdigest()

        replay = self._idempotency.peek(
            tenant=tenant,
            operation_type=self.operation_type,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if replay is not None:
            body = replay["body"]
            return RemoveSaleItemResult(kind="replay", text=body.get("text", "Listo."), payload=body)

        session = self._sales.get_session_by_id(
            tenant=tenant,
            sale_session_id=sale_session_id,
            for_update=True,
        )
        if session is None or (session.conversation_id or "") != (conversation_id or ""):
            return RemoveSaleItemResult(
                kind="stale",
                text=UI_ACTION_STALE_TEXT,
                payload={"code": "UI_ACTION_STALE", "reason_code": "ui_action_stale"},
            )

        gate = self._policies.evaluate(
            PolicyRequest(
                action="execute_tool",
                tool_id="sale.remove_item@1",
                tool_registered=True,
                from_llm=True,
                arguments={"session_status": session.status.value},
            )
        )
        if gate.decision is PolicyDecisionName.DENY:
            return RemoveSaleItemResult(
                kind="deny",
                text="No puedo quitar artículos de una venta ya confirmada o anulada.",
                payload={"code": "SALE_NOT_ACTIVE", "reason_code": gate.reason_code},
            )

        if session.status not in (SaleSessionStatus.OPEN, SaleSessionStatus.READY_TO_CHARGE):
            return RemoveSaleItemResult(
                kind="deny",
                text="No puedo quitar artículos de una venta ya confirmada o anulada.",
                payload={"code": "SALE_NOT_ACTIVE", "reason_code": "sale_not_active"},
            )

        replay = self._idempotency.begin(
            tenant=tenant,
            operation_type=self.operation_type,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if replay is not None:
            body = replay["body"]
            return RemoveSaleItemResult(kind="replay", text=body.get("text", "Listo."), payload=body)

        was_ready = session.status is SaleSessionStatus.READY_TO_CHARGE
        removed = self._sales.remove_item(
            tenant=tenant,
            sale_session_id=session.id,
            sale_item_id=sale_item_id,
        )
        if not removed:
            # Concurrent remove / missing item: stable clarify without inventing a line.
            items = self._sales.list_items(tenant=tenant, sale_session_id=session.id)
            total = sum_session_total(items, currency=session.currency)
            payload = {
                "sale_session_id": str(session.id),
                "sale_item_id": str(sale_item_id),
                "removed": False,
                "status": session.status.value,
                "sale_revision": session.sale_revision,
                "item_count": len(items),
                "total": total.to_json(),
                "items": _item_payloads(items),
                "text": "Ese artículo ya no está en la venta.",
                "code": "SALE_ITEM_MISSING",
            }
            self._idempotency.complete(
                tenant=tenant,
                operation_type=self.operation_type,
                key=idempotency_key,
                status_code=200,
                body=payload,
            )
            return RemoveSaleItemResult(kind="clarify", text=payload["text"], payload=payload)

        items = self._sales.list_items(tenant=tenant, sale_session_id=session.id)
        updated = session
        if was_ready:
            updated = self._sales.advance_sale_revision(tenant=tenant, sale_session_id=session.id)
            if not items:
                updated = self._sales.update_session_status(
                    tenant=tenant,
                    sale_session_id=session.id,
                    status=SaleSessionStatus.OPEN,
                )
                # Preserve advanced revision on demotion.
                if updated.sale_revision != session.sale_revision + 1:
                    # re-read after status update; advance already applied
                    updated = self._sales.get_session_by_id(
                        tenant=tenant, sale_session_id=session.id, for_update=False
                    ) or updated

        total = sum_session_total(items, currency=updated.currency)
        if updated.status is SaleSessionStatus.READY_TO_CHARGE and items:
            summary = build_sale_summary(updated, items)
            text = summary["text"]
            payload = {
                **summary,
                "sale_item_id": str(sale_item_id),
                "removed": True,
                "sale_revision": updated.sale_revision,
                "compose": "sale_summary",
            }
        elif not items:
            text = "Quité el último artículo. La venta sigue abierta sin productos."
            payload = {
                "sale_session_id": str(updated.id),
                "sale_item_id": str(sale_item_id),
                "removed": True,
                "status": updated.status.value,
                "sale_revision": updated.sale_revision,
                "item_count": 0,
                "total": total.to_json(),
                "items": [],
                "text": text,
                "compose": "empty_open",
            }
        else:
            text = f"Artículo quitado. Quedan {len(items)} en la venta · ${total.to_json()['amount']}"
            payload = {
                "sale_session_id": str(updated.id),
                "sale_item_id": str(sale_item_id),
                "removed": True,
                "status": updated.status.value,
                "sale_revision": updated.sale_revision,
                "item_count": len(items),
                "total": total.to_json(),
                "items": _item_payloads(items),
                "text": text,
                "compose": "open_remaining",
            }

        policy_payload = policy.model_dump() if policy is not None else None
        self._audit.record(
            tenant=tenant,
            action="sale.remove_item@1",
            route_or_tool="sale.remove_item@1",
            result="committed",
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            policy_decision=policy_payload,
            after_payload={
                "sale_session_id": str(updated.id),
                "sale_item_id": str(sale_item_id),
                "status": updated.status.value,
                "sale_revision": updated.sale_revision,
                "item_count": len(items),
                "total": total.to_json(),
                **({"ui_action_id": ui_action_id} if ui_action_id else {}),
            },
        )
        self._outbox.enqueue(
            tenant=tenant,
            event_type="sale.item.removed",
            payload={
                "sale_session_id": str(updated.id),
                "sale_item_id": str(sale_item_id),
                "sale_revision": updated.sale_revision,
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
        return RemoveSaleItemResult(kind="committed", text=text, payload=payload)
