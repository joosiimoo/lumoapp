from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import re
from hashlib import sha256
from typing import Any

from uuid import UUID

from app.agent.contracts import AgentDecision
from app.application.pending import PendingSaleClarification
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
    BLANK_OVERRIDE_REASON_TEXT,
    LONG_OVERRIDE_REASON_TEXT,
    MAX_OVERRIDE_REASON,
    basis_question,
    catalog_override_question,
    collapse_display_span,
    ground_user_price,
    missing_price_text,
    normalize_override_reason,
    price_problem_text,
)
from app.domain.shared.errors import IdempotencyConflictError, ProductNotFoundError, ValidationAppError
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

    def replay_override_completion(
        self,
        *,
        tenant: TenantContext,
        idempotency_key: str,
        raw_message: str,
    ) -> AddItemWorkflowResult | None:
        found = self._idempotency.find_completed(
            tenant=tenant,
            operation_type=self.operation_type,
            key=idempotency_key,
        )
        if found is None:
            return None
        marker = found["body"].get("replay_reason")
        if not isinstance(marker, str) or not marker:
            return None
        if normalize_override_reason(raw_message) != marker:
            raise IdempotencyConflictError("Idempotency key reused with a different payload")
        body = found["body"]
        return AddItemWorkflowResult(kind="committed", text=body.get("text", "Listo."), payload=body)

    def complete_price_override(
        self,
        *,
        tenant: TenantContext,
        pending: PendingSaleClarification,
        raw_message: str,
        conversation_id: str | None,
        idempotency_key: str,
        correlation_id: str,
        fail_after_write: bool = False,
    ) -> AddItemWorkflowResult:
        kept = _override_pending_payload(pending)
        reason = normalize_override_reason(raw_message)
        if not reason:
            return AddItemWorkflowResult(kind="clarify", text=BLANK_OVERRIDE_REASON_TEXT, payload={"pending": kept})
        if len(reason) > MAX_OVERRIDE_REASON:
            return AddItemWorkflowResult(kind="clarify", text=LONG_OVERRIDE_REASON_TEXT, payload={"pending": kept})
        if not pending.product_id or not pending.quantity or not pending.unit or not pending.unit_price:
            return AddItemWorkflowResult(
                kind="clarify",
                text="Encontré más de un producto. ¿Cuál vendiste?",
                payload={"clear_pending": True, "match": "ambiguous"},
            )
        resolved = self._catalog.resolve(
            tenant=tenant, query=normalize_product_name(pending.product_query or "")
        )
        if resolved.inactive_collision:
            return AddItemWorkflowResult(
                kind="clarify",
                text="Ese producto está inactivo.",
                payload={"clear_pending": True, "match": "inactive"},
            )
        if (
            resolved.match is not ProductMatch.UNIQUE
            or resolved.product is None
            or str(resolved.product.id) != pending.product_id
        ):
            return AddItemWorkflowResult(
                kind="clarify",
                text="Encontré más de un producto. ¿Cuál vendiste?",
                payload={"clear_pending": True, "match": "ambiguous"},
            )
        try:
            override_amount = _explicit_price(pending.unit_price)
        except (ValidationAppError, ValueError):
            return AddItemWorkflowResult(
                kind="clarify",
                text=price_problem_text("non_positive"),
                payload={"clear_pending": True},
            )
        try:
            locked = self._catalog.get_for_update(tenant=tenant, product_id=UUID(pending.product_id))
        except ProductNotFoundError:
            return AddItemWorkflowResult(
                kind="clarify",
                text="Ese producto está inactivo.",
                payload={"clear_pending": True, "match": "inactive"},
            )
        if not locked.is_active or str(locked.id) != pending.product_id:
            self._catalog.rollback_product_lock()
            return AddItemWorkflowResult(
                kind="clarify",
                text="Ese producto está inactivo.",
                payload={"clear_pending": True, "match": "inactive"},
            )
        observed = Decimal(pending.observed_catalog_unit_price or "0")
        locked_amount = locked.current_price.amount
        if locked_amount != observed and locked_amount != override_amount:
            self._catalog.rollback_product_lock()
            restarted = _override_pending_payload(
                pending, observed=locked.current_price.to_json()["amount"]
            )
            return AddItemWorkflowResult(
                kind="clarify",
                text=catalog_override_question(
                    locked.name,
                    locked.current_price,
                    override_amount,
                    locked.sale_unit,
                    changed=True,
                ),
                payload={"pending": restarted, "reason": "catalog_price_override_reason_required"},
            )
        charged = locked.current_price if locked_amount == override_amount else Money(override_amount, locked.current_price.currency)
        stored_reason = None if locked_amount == override_amount else reason
        return self._commit_locked_catalog(
            tenant=tenant,
            conversation_id=conversation_id,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
            fail_after_write=fail_after_write,
            product=locked,
            quantity_text=pending.quantity,
            unit_name=pending.unit,
            charged=charged,
            reason=stored_reason,
            replay_reason=reason,
            create_session=True,
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
        if arguments.get("source_type") == "catalog" and arguments.get("price_override"):
            return self._direct_override(
                tenant=tenant,
                arguments=arguments,
                conversation_id=conversation_id,
                idempotency_key=idempotency_key,
                correlation_id=correlation_id,
            )
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
        if uttered is not None and uttered != product.current_price.amount:
            self._policies.evaluate(
                PolicyRequest(
                    action="execute_tool",
                    tool_id="sale.add_item@1",
                    tool_registered=True,
                    arguments={"match": "catalog_price_override_reason_required"},
                )
            )
            observed = product.current_price.to_json()["amount"]
            return AddItemWorkflowResult(
                kind="clarify",
                text=catalog_override_question(product.name, product.current_price, uttered, product.sale_unit),
                payload={
                    "match": "catalog_price_override_reason_required",
                    "reason": "catalog_price_override_reason_required",
                    "pending": {
                        "kind": "catalog_price_override",
                        "product_query": working.product_query,
                        "product_id": str(product.id),
                        "quantity": working.quantity,
                        "unit": working.unit,
                        "unit_price": f"{uttered.quantize(Decimal('0.01')):.2f}",
                        "observed_catalog_unit_price": observed,
                    },
                },
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

    def _direct_override(
        self,
        *,
        tenant: TenantContext,
        arguments: dict[str, Any],
        conversation_id: str | None,
        idempotency_key: str,
        correlation_id: str,
    ) -> AddItemWorkflowResult:
        product_text = arguments.get("product_id")
        if not product_text:
            raise ValidationAppError("a catalog override requires a product")
        override = arguments.get("price_override") or {}
        price = override.get("unit_price") or {}
        try:
            amount = _explicit_price(str(price.get("amount") or ""))
        except (ValidationAppError, ValueError):
            return AddItemWorkflowResult(kind="clarify", text=price_problem_text("non_positive"), payload={})
        currency = str(price.get("currency") or "")
        if currency != "MXN":
            return AddItemWorkflowResult(kind="clarify", text=price_problem_text("non_positive"), payload={})
        existing = self._sales.get_active_session(tenant=tenant, conversation_id=conversation_id)
        if existing is not None and not can_add_item(existing.status):
            return AddItemWorkflowResult(
                kind="deny",
                text="Esta venta ya está lista para cobrar. No puedo agregar más artículos.",
                payload={"code": "SALE_NOT_OPEN"},
            )
        if existing is None:
            return AddItemWorkflowResult(
                kind="deny",
                text="No hay una venta abierta.",
                payload={"code": "SALE_NOT_OPEN"},
            )
        try:
            locked = self._catalog.get_for_update(tenant=tenant, product_id=UUID(str(product_text)))
        except (ProductNotFoundError, ValueError):
            return AddItemWorkflowResult(
                kind="clarify",
                text="Ese producto está inactivo.",
                payload={"match": "inactive"},
            )
        if not locked.is_active:
            self._catalog.rollback_product_lock()
            return AddItemWorkflowResult(
                kind="clarify",
                text="Ese producto está inactivo.",
                payload={"match": "inactive"},
            )
        if locked.current_price.currency != currency:
            self._catalog.rollback_product_lock()
            return AddItemWorkflowResult(kind="clarify", text=price_problem_text("non_positive"), payload={})
        if locked.current_price.amount == amount:
            charged = locked.current_price
            stored_reason = None
        else:
            stored_reason = normalize_override_reason(str(override.get("reason") or ""))
            if not stored_reason:
                self._catalog.rollback_product_lock()
                return AddItemWorkflowResult(kind="clarify", text=BLANK_OVERRIDE_REASON_TEXT, payload={})
            if len(stored_reason) > MAX_OVERRIDE_REASON:
                self._catalog.rollback_product_lock()
                return AddItemWorkflowResult(kind="clarify", text=LONG_OVERRIDE_REASON_TEXT, payload={})
            charged = Money(amount, locked.current_price.currency)
        return self._commit_locked_catalog(
            tenant=tenant,
            conversation_id=conversation_id,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
            fail_after_write=False,
            product=locked,
            quantity_text=str(arguments.get("quantity") or ""),
            unit_name=str(arguments.get("unit") or ""),
            charged=charged,
            reason=stored_reason,
            replay_reason=normalize_override_reason(str(override.get("reason") or "")) or None,
            create_session=False,
        )

    def _commit_locked_catalog(
        self,
        *,
        tenant: TenantContext,
        conversation_id: str | None,
        idempotency_key: str,
        correlation_id: str,
        fail_after_write: bool,
        product: Product,
        quantity_text: str,
        unit_name: str,
        charged: Money,
        reason: str | None,
        create_session: bool,
        replay_reason: str | None = None,
    ) -> AddItemWorkflowResult:
        try:
            quantity = parse_quantity(quantity_text)
            unit = InputUnit(unit_name)
            quantity_normalized, unit_normalized = normalize_quantity(quantity, unit, product.sale_unit)
        except (ValidationAppError, ValueError):
            self._catalog.rollback_product_lock()
            return AddItemWorkflowResult(kind="clarify", text="¿Cuántos vendiste?", payload={})
        line_total = calculate_line_total(quantity_normalized, charged)
        if line_total.amount <= 0:
            self._catalog.rollback_product_lock()
            return AddItemWorkflowResult(kind="clarify", text=price_problem_text("non_positive"), payload={})
        override = reason is not None
        policy = self._policies.evaluate(
            PolicyRequest(
                action="execute_tool",
                tool_id="sale.add_item@1",
                tool_registered=True,
                arguments=(
                    {"catalog_price_override": True, "quantity": quantity_text, "unit": unit_name}
                    if override
                    else {"quantity": quantity_text, "unit": unit_name}
                ),
            )
        )
        request_hash = _override_hash(
            conversation_id=conversation_id,
            product_id=product.id,
            quantity_normalized=quantity_normalized,
            unit=unit_normalized,
            snapshot_amount=product.current_price.amount,
            charged_amount=charged.amount,
            reason=reason,
        )
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
            unit_price=charged,
            line_total=line_total,
            text=_catalog_success(quantity_normalized, unit_normalized, product.name, line_total),
            catalog_unit_price_snapshot=product.current_price,
            price_override_reason=reason,
            prices_locked=True,
            create_session=create_session,
            replay_reason=replay_reason,
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
        catalog_unit_price_snapshot: Money | None = None,
        price_override_reason: str | None = None,
        prices_locked: bool = False,
        create_session: bool = True,
        replay_reason: str | None = None,
    ) -> AddItemWorkflowResult:
        existing = self._sales.get_active_session(
            tenant=tenant,
            conversation_id=conversation_id,
            for_update=True,
        )
        if existing is not None and not can_add_item(existing.status):
            if prices_locked:
                self._catalog.rollback_product_lock()
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
        if existing is None and not create_session:
            if prices_locked:
                self._catalog.rollback_product_lock()
            return AddItemWorkflowResult(
                kind="deny",
                text="No hay una venta abierta.",
                payload={"code": "SALE_NOT_OPEN"},
            )
        replay = self._idempotency.begin(
            tenant=tenant,
            operation_type=self.operation_type,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if replay is not None:
            if prices_locked:
                self._catalog.rollback_product_lock()
            body = replay["body"]
            return AddItemWorkflowResult(kind="committed", text=body.get("text", "Listo."), payload=body)

        if source_type is SaleItemSource.CATALOG and not prices_locked:
            product = self._catalog.get(tenant=tenant, product_id=product_id)
            if not product.is_active:
                raise ProductNotFoundError("product is inactive")
            unit_price = product.current_price
            snapshot = product.name
            catalog_unit_price_snapshot = product.current_price
            price_override_reason = None
            line_total = calculate_line_total(quantity_normalized, unit_price)
            text = _catalog_success(quantity_normalized, unit_normalized, snapshot, line_total)

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
                catalog_unit_price_snapshot=catalog_unit_price_snapshot,
                price_override_reason=price_override_reason,
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
            "catalog_unit_price_snapshot": (
                None if catalog_unit_price_snapshot is None else catalog_unit_price_snapshot.to_json()
            ),
            "price_override_reason": price_override_reason,
            "session_item_count": len(items),
            "session_total": session_total.to_json(),
            "created_session": created,
        }
        if (
            catalog_unit_price_snapshot is not None
            and unit_price.amount != catalog_unit_price_snapshot.amount
        ):
            add_payload["catalog_unit_price"] = catalog_unit_price_snapshot.to_json()
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
                "catalog_unit_price_snapshot": (
                    None if catalog_unit_price_snapshot is None else catalog_unit_price_snapshot.to_json()
                ),
                "unit_price": unit_price.to_json(),
                "price_override_reason": price_override_reason,
            },
        )
        if fail_after_write:
            raise RuntimeError("forced rollback")
        body = {**add_payload, "text": text}
        if replay_reason:
            body["replay_reason"] = replay_reason
        self._idempotency.complete(
            tenant=tenant,
            operation_type=self.operation_type,
            key=idempotency_key,
            status_code=200,
            body=body,
        )
        return AddItemWorkflowResult(kind="committed", text=text, payload=body)


def _override_pending_payload(pending: PendingSaleClarification, *, observed: str | None = None) -> dict[str, Any]:
    return {
        "kind": "catalog_price_override",
        "product_query": pending.product_query,
        "product_id": pending.product_id,
        "quantity": pending.quantity,
        "unit": pending.unit,
        "unit_price": pending.unit_price,
        "observed_catalog_unit_price": observed or pending.observed_catalog_unit_price,
    }


def _override_hash(
    *,
    conversation_id: str | None,
    product_id: UUID,
    quantity_normalized: Decimal,
    unit: SaleUnit,
    snapshot_amount: Decimal,
    charged_amount: Decimal,
    reason: str | None,
) -> str:
    canonical = "|".join(
        [
            "catalog-price-override",
            "v1",
            conversation_id or "",
            str(product_id),
            format(quantity_normalized, "f"),
            unit.value,
            f"{snapshot_amount.quantize(Decimal('0.01')):.2f}",
            f"{charged_amount.quantize(Decimal('0.01')):.2f}",
            reason or "",
        ]
    )
    return sha256(canonical.encode()).hexdigest()


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
