from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from app.agent.contracts import AgentDecision
from app.application.ports import AuditService, CatalogPort, IdempotencyService, IdentityPort, Outbox, SalesPort
from app.domain.catalog import ProductMatch
from app.domain.sales import (
    InputUnit,
    SaleItem,
    SaleSession,
    SaleSessionStatus,
    calculate_line_total,
    format_normalized_quantity,
    normalize_quantity,
    parse_quantity,
)
from app.domain.shared.errors import ProductNotFoundError
from app.domain.shared.ids import new_uuid7
from app.domain.shared.money import Money
from app.domain.shared.tenant import TenantContext
from app.policies import PolicyDecision


@dataclass(frozen=True, slots=True)
class AddItemWorkflowResult:
    kind: str
    text: str
    payload: dict[str, Any]


class AddCatalogSaleItem:
    operation_type = "lumo.message.add_sale_item"

    def __init__(
        self,
        *,
        catalog: CatalogPort,
        sales: SalesPort,
        identities: IdentityPort,
        audit: AuditService,
        idempotency: IdempotencyService,
        outbox: Outbox,
    ) -> None:
        self._catalog = catalog
        self._sales = sales
        self._identities = identities
        self._audit = audit
        self._idempotency = idempotency
        self._outbox = outbox

    def execute(
        self,
        *,
        tenant: TenantContext,
        decision: AgentDecision,
        conversation_id: str | None,
        idempotency_key: str,
        correlation_id: str,
        policy: PolicyDecision | None = None,
        fail_after_write: bool = False,
        raw_message: str = "",
    ) -> AddItemWorkflowResult:
        resolved = self._catalog.resolve(tenant=tenant, query=decision.product_query or "")
        if resolved.match is ProductMatch.AMBIGUOUS:
            return AddItemWorkflowResult(
                kind="clarify",
                text="Encontré más de un producto. ¿Cuál vendiste?",
                payload={
                    "match": "ambiguous",
                    "candidates": [
                        {"name": product.name, "product_id": str(product.id)} for product in resolved.candidates
                    ],
                },
            )
        if resolved.match is ProductMatch.NONE or resolved.product is None:
            return AddItemWorkflowResult(
                kind="clarify",
                text="No encontré ese producto en el catálogo.",
                payload={"match": "none"},
            )

        request_hash = sha256(
            f"{raw_message}|{conversation_id or ''}|{decision.quantity}|{decision.unit}|{decision.product_query}".encode()
        ).hexdigest()
        replay = self._idempotency.begin(
            tenant=tenant,
            operation_type=self.operation_type,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if replay is not None:
            body = replay["body"]
            return AddItemWorkflowResult(kind="committed", text=body.get("text", "Listo."), payload=body)

        product = self._catalog.get(tenant=tenant, product_id=resolved.product.id)
        if not product.is_active:
            raise ProductNotFoundError("product is inactive")

        quantity = parse_quantity(decision.quantity or "")
        unit = InputUnit(decision.unit or "")
        quantity_normalized, unit_normalized = normalize_quantity(quantity, unit, product.sale_unit)
        line_total = calculate_line_total(quantity_normalized, product.current_price)
        business = self._identities.get_business(tenant)
        existing = self._sales.get_open_session(tenant=tenant, conversation_id=conversation_id)
        created = existing is None
        if existing is None:
            session = self._sales.add_session(
                tenant=tenant,
                session=SaleSession(
                    id=new_uuid7(),
                    business_id=tenant.business_id,
                    actor_id=tenant.actor_id,
                    conversation_id=conversation_id,
                    status=SaleSessionStatus.OPEN,
                    currency=business.currency,
                ),
            )
        else:
            session = existing

        item = self._sales.add_item(
            tenant=tenant,
            item=SaleItem(
                id=new_uuid7(),
                business_id=tenant.business_id,
                sale_session_id=session.id,
                product_id=product.id,
                product_name_snapshot=product.name,
                quantity_input=quantity,
                unit_input=unit,
                quantity_normalized=quantity_normalized,
                unit_normalized=unit_normalized,
                unit_price=product.current_price,
                line_total=line_total,
            ),
        )
        items = self._sales.list_items(tenant=tenant, sale_session_id=session.id)
        session_total = _money_sum(items)
        add_payload = {
            "sale_session_id": str(session.id),
            "sale_item_id": str(item.id),
            "product_id": str(product.id),
            "product_name": product.name,
            "quantity_input": format(quantity, "f"),
            "unit_input": unit.value,
            "quantity_normalized": format_normalized_quantity(quantity_normalized, unit_normalized),
            "unit_normalized": unit_normalized.value,
            "unit_price": product.current_price.to_json(),
            "line_total": line_total.to_json(),
            "session_item_count": len(items),
            "session_total": session_total.to_json(),
            "created_session": created,
        }
        policy_payload = policy.model_dump() if policy is not None else None
        self._audit.record(
            tenant=tenant,
            action="sale.start@1",
            route_or_tool="sale.start@1",
            result="committed",
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            policy_decision=policy_payload,
            after_payload={"sale_session_id": str(session.id), "created": created},
        )
        self._audit.record(
            tenant=tenant,
            action="sale.add_item@1",
            route_or_tool="sale.add_item@1",
            result="committed",
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            policy_decision=policy_payload,
            after_payload=add_payload,
        )
        self._outbox.enqueue(
            tenant=tenant,
            event_type="sale.item.added",
            payload={"sale_item_id": str(item.id), "sale_session_id": str(session.id)},
        )
        if fail_after_write:
            raise RuntimeError("forced rollback")
        qty_label = add_payload["quantity_normalized"]
        unit_label = "kg" if unit_normalized.value == "kilogram" else unit_normalized.value
        text = f"Agregué {qty_label} {unit_label} de {product.name} · ${add_payload['line_total']['amount']}"
        body = {**add_payload, "text": text}
        self._idempotency.complete(
            tenant=tenant,
            operation_type=self.operation_type,
            key=idempotency_key,
            status_code=200,
            body=body,
        )
        return AddItemWorkflowResult(kind="committed", text=text, payload=body)


def _money_sum(items: list[SaleItem]) -> Money:
    if not items:
        return Money("0.00", "MXN")
    total = items[0].line_total.amount
    currency = items[0].line_total.currency
    for item in items[1:]:
        total = total + item.line_total.amount
    return Money(total, currency)
