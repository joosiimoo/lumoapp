from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import re
from hashlib import sha256
from typing import Any

from app.agent.contracts import AgentDecision
from app.application.ports import AuditService, CatalogPort, IdempotencyService, IdentityPort, Outbox, SalesPort
from app.domain.catalog import ProductMatch, SaleUnit, normalize_product_name
from app.domain.catalog.product import Product
from app.domain.sales import (
    InputUnit,
    SaleItem,
    SaleItemSource,
    SaleSession,
    SaleSessionStatus,
    calculate_line_total,
    can_add_item,
    format_normalized_quantity,
    normalize_free_concept_quantity,
    normalize_quantity,
    parse_quantity,
    sum_session_total,
)
from app.domain.sales.concept import (
    EMPTY_CONCEPT_TEXT,
    LONG_CONCEPT_TEXT,
    MAX_DISPLAY_SPAN,
    basis_question,
    catalog_mismatch_text,
    collapse_display_span,
    ground_user_price,
    missing_price_text,
    price_problem_text,
)
from app.domain.shared.errors import ProductNotFoundError, ValidationAppError
from app.domain.shared.ids import new_uuid7
from app.domain.shared.money import Money
from app.domain.shared.tenant import TenantContext
from app.policies import PolicyDecision, PolicyDecisionName, PolicyRequest
from app.policies.engine import FoundationPolicyEngine


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
        self._policies = FoundationPolicyEngine()

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
        pending_unit_price: str | None = None,
    ) -> AddItemWorkflowResult:
        if decision.clarification_question and "unit" in decision.missing_fields and not decision.product_query:
            return AddItemWorkflowResult(kind="clarify", text=decision.clarification_question, payload={})

        grounded = ground_user_price(raw_message)
        if grounded.problem:
            return AddItemWorkflowResult(kind="clarify", text=price_problem_text(grounded.problem), payload={})

        amount = grounded.amount
        if _bare_amount_message(raw_message) and not decision.unit_price:
            amount = None
        if amount is None and pending_unit_price:
            amount = Decimal(pending_unit_price)
        per_kilogram = grounded.per_kilogram or decision.price_basis == "per_kilogram"

        display = collapse_display_span(decision.product_query or "")
        if not display or len(display) > MAX_DISPLAY_SPAN:
            return AddItemWorkflowResult(
                kind="clarify",
                text=LONG_CONCEPT_TEXT if len(display) > MAX_DISPLAY_SPAN else EMPTY_CONCEPT_TEXT,
                payload={},
            )

        resolved = self._catalog.resolve(tenant=tenant, query=normalize_product_name(display))
        if resolved.match is ProductMatch.AMBIGUOUS:
            return AddItemWorkflowResult(
                kind="clarify",
                text="Encontré más de un producto. ¿Cuál vendiste?",
                payload={
                    "match": "ambiguous",
                    "clear_pending": True,
                    "candidates": [
                        {"name": product.name, "product_id": str(product.id)} for product in resolved.candidates
                    ],
                },
            )
        if resolved.inactive_collision:
            return AddItemWorkflowResult(
                kind="clarify",
                text="Ese producto está inactivo.",
                payload={"match": "inactive"},
            )
        if resolved.match is ProductMatch.UNIQUE and resolved.product is not None:
            return self._catalog_line(
                tenant=tenant,
                decision=decision,
                conversation_id=conversation_id,
                idempotency_key=idempotency_key,
                correlation_id=correlation_id,
                policy=policy,
                fail_after_write=fail_after_write,
                raw_message=raw_message,
                product=resolved.product,
                uttered=amount,
            )
        return self._free_concept_line(
            tenant=tenant,
            decision=decision,
            conversation_id=conversation_id,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
            policy=policy,
            fail_after_write=fail_after_write,
            raw_message=raw_message,
            display=display,
            amount=amount,
            per_kilogram=per_kilogram,
        )

    def execute_tool(
        self,
        *,
        tenant: TenantContext,
        arguments: dict[str, Any],
        conversation_id: str | None,
        idempotency_key: str,
        correlation_id: str,
    ) -> AddItemWorkflowResult:
        if arguments.get("source_type") != "free_concept":
            raise ValidationAppError("direct catalog adds stay on the message workflow")
        display = collapse_display_span(str(arguments.get("concept_name") or ""))
        if not display or len(display) > MAX_DISPLAY_SPAN:
            return AddItemWorkflowResult(
                kind="clarify",
                text=LONG_CONCEPT_TEXT if len(display) > MAX_DISPLAY_SPAN else EMPTY_CONCEPT_TEXT,
                payload={},
            )
        resolved = self._catalog.resolve(tenant=tenant, query=normalize_product_name(display))
        if resolved.match is ProductMatch.UNIQUE:
            return AddItemWorkflowResult(
                kind="clarify",
                text="Ese producto ya está en el catálogo.",
                payload={"match": "unique"},
            )
        if resolved.match is ProductMatch.AMBIGUOUS or resolved.inactive_collision:
            text = (
                "Ese producto está inactivo."
                if resolved.inactive_collision
                else "Encontré más de un producto. ¿Cuál vendiste?"
            )
            return AddItemWorkflowResult(kind="clarify", text=text, payload={"match": resolved.match.value})
        price_text = str((arguments.get("unit_price") or {}).get("amount") or "")
        try:
            amount = _explicit_price(price_text)
        except ValidationAppError:
            return AddItemWorkflowResult(kind="clarify", text=price_problem_text("non_positive"), payload={})
        unit_name = str(arguments.get("unit") or "")
        if unit_name in {"gram", "kilogram"} and arguments.get("price_basis") != "per_kilogram":
            return AddItemWorkflowResult(
                kind="clarify",
                text=basis_question(amount),
                payload={"reason": "price_basis_required"},
            )
        decision = AgentDecision(
            intent="add_sale_item",
            product_query=display,
            quantity=str(arguments.get("quantity") or ""),
            unit=unit_name,  # type: ignore[arg-type]
            unit_price=f"{amount:.2f}",
            price_basis="per_kilogram" if unit_name in {"gram", "kilogram"} else "per_each",
        )
        return self._free_concept_line(
            tenant=tenant,
            decision=decision,
            conversation_id=conversation_id,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
            policy=None,
            fail_after_write=False,
            raw_message="",
            display=display,
            amount=amount,
            per_kilogram=unit_name in {"gram", "kilogram"},
        )

    def _catalog_line(
        self,
        *,
        tenant: TenantContext,
        decision: AgentDecision,
        conversation_id: str | None,
        idempotency_key: str,
        correlation_id: str,
        policy: PolicyDecision | None,
        fail_after_write: bool,
        raw_message: str,
        product: Product,
        uttered: Decimal | None,
    ) -> AddItemWorkflowResult:
        if uttered is not None and uttered != product.current_price.amount:
            self._policies.evaluate(
                PolicyRequest(
                    action="execute_tool",
                    tool_id="sale.add_item@1",
                    tool_registered=True,
                    arguments={"match": "catalog_price_mismatch"},
                )
            )
            return AddItemWorkflowResult(
                kind="clarify",
                text=catalog_mismatch_text(product.name, product.current_price, product.sale_unit),
                payload={"match": "catalog_price_mismatch", "reason": "catalog_price_mismatch"},
            )
        working = decision
        if working.unit is None:
            if product.sale_unit in {SaleUnit.UNIT, SaleUnit.PACKAGE}:
                working = working.model_copy(
                    update={"unit": product.sale_unit.value, "missing_fields": [], "candidate_tool": "sale.add_item@1"}
                )
            else:
                return AddItemWorkflowResult(
                    kind="clarify_unit",
                    text="¿En qué unidad está esa cantidad? Por ejemplo gramos o kilogramos.",
                    payload={
                        "missing_fields": ["unit"],
                        "pending": {
                            "kind": "catalog_unit",
                            "product_query": working.product_query,
                            "quantity": working.quantity,
                        },
                    },
                )
        if not working.quantity:
            return AddItemWorkflowResult(
                kind="clarify",
                text="¿Cuántos vendiste?",
                payload={"reason": "quantity_required"},
            )
        request_hash = sha256(
            f"{raw_message}|{conversation_id or ''}|{working.quantity}|{working.unit}|{working.product_query}".encode()
        ).hexdigest()
        quantity = parse_quantity(working.quantity)
        unit = InputUnit(working.unit or "")
        quantity_normalized, unit_normalized = normalize_quantity(quantity, unit, product.sale_unit)
        line_total = calculate_line_total(quantity_normalized, product.current_price)
        return self._commit_item(
            tenant=tenant,
            conversation_id=conversation_id,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
            policy=policy,
            fail_after_write=fail_after_write,
            request_hash=request_hash,
            source_type=SaleItemSource.CATALOG,
            product_id=product.id,
            snapshot=product.name,
            quantity=quantity,
            unit=unit,
            quantity_normalized=quantity_normalized,
            unit_normalized=unit_normalized,
            unit_price=product.current_price,
            line_total=line_total,
            text=_catalog_success(quantity_normalized, unit_normalized, product.name, line_total),
        )

    def _free_concept_line(
        self,
        *,
        tenant: TenantContext,
        decision: AgentDecision,
        conversation_id: str | None,
        idempotency_key: str,
        correlation_id: str,
        policy: PolicyDecision | None,
        fail_after_write: bool,
        raw_message: str,
        display: str,
        amount: Decimal | None,
        per_kilogram: bool,
    ) -> AddItemWorkflowResult:
        if not decision.quantity:
            both = amount is None
            return self._remember(
                "¿Cuántos vendiste y a qué precio?" if both else "¿Cuántos vendiste?",
                display=display,
                quantity=None,
                unit=decision.unit,
                unit_price=None if amount is None else f"{amount:.2f}",
                price_basis=None,
                package_word=decision.package_word,
                reason="quantity_required",
                quantity_missing=True,
                price_missing=both,
            )
        unit_name = decision.unit or "unit"
        unit = InputUnit(unit_name)
        mass = unit in {InputUnit.GRAM, InputUnit.KILOGRAM}
        if amount is None:
            return self._remember(
                missing_price_text(unit=unit_name, package_word=decision.package_word),
                display=display,
                quantity=decision.quantity,
                unit=unit_name,
                unit_price=None,
                price_basis=None,
                package_word=decision.package_word,
                reason="price_required",
                price_missing=True,
            )
        if mass and not per_kilogram:
            return self._remember(
                basis_question(amount),
                display=display,
                quantity=decision.quantity,
                unit=unit_name,
                unit_price=f"{amount:.2f}",
                price_basis=None,
                package_word=None,
                reason="price_basis_required",
                price_basis_missing=True,
            )
        if amount <= 0:
            return AddItemWorkflowResult(kind="clarify", text=price_problem_text("non_positive"), payload={})
        business = self._identities.get_business(tenant)
        if business.currency != "MXN":
            return AddItemWorkflowResult(kind="clarify", text=price_problem_text("foreign"), payload={})
        unit_price = Money(amount, business.currency)
        quantity = parse_quantity(decision.quantity)
        quantity_normalized, unit_normalized = normalize_free_concept_quantity(quantity, unit)
        line_total = calculate_line_total(quantity_normalized, unit_price)
        if line_total.amount <= 0:
            return AddItemWorkflowResult(kind="clarify", text=price_problem_text("non_positive"), payload={})
        gate = self._policies.evaluate(
            PolicyRequest(
                action="execute_tool",
                tool_id="sale.add_item@1",
                tool_registered=True,
                arguments={"match": "none", "free_concept_complete": True, "quantity": decision.quantity},
            )
        )
        if gate.decision is not PolicyDecisionName.ALLOW:
            return AddItemWorkflowResult(kind="deny", text="No puedo registrar ese concepto.", payload={})
        request_hash = sha256(
            f"{raw_message}|{conversation_id or ''}|{decision.quantity}|{unit_name}|{display}|{unit_price.to_json()['amount']}".encode()
        ).hexdigest()
        text = _free_success(quantity, quantity_normalized, unit_normalized, display, line_total)
        return self._commit_item(
            tenant=tenant,
            conversation_id=conversation_id,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
            policy=policy or gate,
            fail_after_write=fail_after_write,
            request_hash=request_hash,
            source_type=SaleItemSource.FREE_CONCEPT,
            product_id=None,
            snapshot=display,
            quantity=quantity,
            unit=unit,
            quantity_normalized=quantity_normalized,
            unit_normalized=unit_normalized,
            unit_price=unit_price,
            line_total=line_total,
            text=text,
        )

    def _remember(
        self,
        text: str,
        *,
        display: str,
        quantity: str | None,
        unit: str | None,
        unit_price: str | None,
        price_basis: str | None,
        package_word: str | None,
        reason: str,
        price_missing: bool = False,
        quantity_missing: bool = False,
        price_basis_missing: bool = False,
    ) -> AddItemWorkflowResult:
        self._policies.evaluate(
            PolicyRequest(
                action="execute_tool",
                tool_id="sale.add_item@1",
                tool_registered=True,
                arguments={
                    "match": "none",
                    "price_missing": price_missing,
                    "quantity_missing": quantity_missing,
                    "price_basis_missing": price_basis_missing,
                },
            )
        )
        return AddItemWorkflowResult(
            kind="clarify",
            text=text,
            payload={
                "reason": reason,
                "pending": {
                    "kind": "free_concept",
                    "product_query": display,
                    "quantity": quantity,
                    "unit": unit,
                    "unit_price": unit_price,
                    "price_basis": price_basis,
                    "package_word": package_word,
                },
            },
        )

    def _commit_item(
        self,
        *,
        tenant: TenantContext,
        conversation_id: str | None,
        idempotency_key: str,
        correlation_id: str,
        policy: PolicyDecision | None,
        fail_after_write: bool,
        request_hash: str,
        source_type: SaleItemSource,
        product_id: Any,
        snapshot: str,
        quantity: Decimal,
        unit: InputUnit,
        quantity_normalized: Decimal,
        unit_normalized: SaleUnit,
        unit_price: Money,
        line_total: Money,
        text: str,
    ) -> AddItemWorkflowResult:
        existing = self._sales.get_active_session(
            tenant=tenant,
            conversation_id=conversation_id,
            for_update=True,
        )
        if existing is not None and not can_add_item(existing.status):
            self._policies.evaluate(
                PolicyRequest(
                    action="execute_tool",
                    tool_id="sale.add_item@1",
                    tool_registered=True,
                    arguments={"session_status": existing.status.value},
                )
            )
            return AddItemWorkflowResult(
                kind="deny",
                text="Esta venta ya está lista para cobrar. No puedo agregar más artículos.",
                payload={"code": "SALE_NOT_OPEN"},
            )
        replay = self._idempotency.begin(
            tenant=tenant,
            operation_type=self.operation_type,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if replay is not None:
            body = replay["body"]
            return AddItemWorkflowResult(kind="committed", text=body.get("text", "Listo."), payload=body)

        if source_type is SaleItemSource.CATALOG:
            product = self._catalog.get(tenant=tenant, product_id=product_id)
            if not product.is_active:
                raise ProductNotFoundError("product is inactive")
            unit_price = product.current_price
            snapshot = product.name

        business = self._identities.get_business(tenant)
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
                product_id=product_id,
                source_type=source_type,
                product_name_snapshot=snapshot,
                quantity_input=quantity,
                unit_input=unit,
                quantity_normalized=quantity_normalized,
                unit_normalized=unit_normalized,
                unit_price=unit_price,
                line_total=line_total,
            ),
        )
        items = self._sales.list_items(tenant=tenant, sale_session_id=session.id)
        session_total = sum_session_total(items, currency=session.currency)
        product_id_json = None if product_id is None else str(product_id)
        add_payload = {
            "sale_session_id": str(session.id),
            "sale_item_id": str(item.id),
            "source_type": source_type.value,
            "product_id": product_id_json,
            "product_name": snapshot,
            "quantity_input": format(quantity, "f"),
            "unit_input": unit.value,
            "quantity_normalized": format_normalized_quantity(quantity_normalized, unit_normalized),
            "unit_normalized": unit_normalized.value,
            "unit_price": unit_price.to_json(),
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
            payload={
                "sale_item_id": str(item.id),
                "sale_session_id": str(session.id),
                "source_type": source_type.value,
                "product_id": product_id_json,
                "product_name": snapshot,
            },
        )
        if fail_after_write:
            raise RuntimeError("forced rollback")
        body = {**add_payload, "text": text}
        self._idempotency.complete(
            tenant=tenant,
            operation_type=self.operation_type,
            key=idempotency_key,
            status_code=200,
            body=body,
        )
        return AddItemWorkflowResult(kind="committed", text=text, payload=body)


def _bare_amount_message(raw_message: str) -> bool:
    return re.fullmatch(r"\s*-?\$?\d+(?:[.,]\d+)?\s*", raw_message or "") is not None


def _explicit_price(amount: str) -> Decimal:
    if "." in amount and len(amount.split(".", 1)[1]) > 2:
        raise ValidationAppError("price scale")
    value = Decimal(amount)
    if value <= 0:
        raise ValidationAppError("price must be greater than zero")
    return value


def _catalog_success(quantity: Decimal, unit: SaleUnit, name: str, line_total: Money) -> str:
    qty_label = format_normalized_quantity(quantity, unit)
    unit_label = "kg" if unit is SaleUnit.KILOGRAM else unit.value
    return f"Agregué {qty_label} {unit_label} de {name} · ${line_total.to_json()['amount']}"


def _free_success(
    quantity: Decimal,
    quantity_normalized: Decimal,
    unit: SaleUnit,
    snapshot: str,
    line_total: Money,
) -> str:
    amount = line_total.to_json()["amount"]
    if unit is SaleUnit.KILOGRAM:
        qty = format_normalized_quantity(quantity_normalized, unit)
        return f"Agregué {qty} kg de {snapshot} · ${amount}"
    qty = format(quantity, "f")
    return f"Agregué {qty} {snapshot} · ${amount}"
