from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from app.agent.contracts import AgentDecision, AgentResponse, LLMProvider
from app.agent.generative_ui import GenerativeUIComposer, GenerativeUIContract
from app.agent.tools import ToolRegistry
from app.application.pending import InMemoryPendingClarificationStore
from app.application.workflows.add_catalog_sale_item import AddCatalogSaleItem
from app.application.workflows.totalize_sale_session import TotalizeSaleSession
from app.domain.shared.tenant import TenantContext
from app.policies import PolicyEngine, PolicyRequest


class LumoOrchestrator:
    def handle(self, message: str, context: dict[str, Any] | None = None) -> AgentResponse: ...


@dataclass
class FoundationOrchestrator:
    provider: LLMProvider
    tools: ToolRegistry
    policies: PolicyEngine
    workflow: AddCatalogSaleItem | None = None
    totalize: TotalizeSaleSession | None = None
    ui_composer: GenerativeUIComposer | None = None
    pending: InMemoryPendingClarificationStore | None = None

    def handle(self, message: str, context: dict[str, Any] | None = None) -> AgentResponse:
        context = context or {}
        raw = self.provider.interpret(message, context, self.tools.allowed_ids())
        try:
            payload = raw.model_dump() if hasattr(raw, "model_dump") else raw
            decision = AgentDecision.model_validate(payload)
        except (ValidationError, AttributeError, TypeError):
            return AgentResponse(text="I could not interpret that safely.", ui=[])

        tenant: TenantContext | None = context.get("tenant")
        conversation_id = context.get("conversation_id")
        decision = self._merge_pending(decision, tenant, conversation_id)

        if decision.intent == "totalize_sale" or decision.candidate_tool == "sale.totalize@1":
            return self._handle_totalize(decision, message, context, tenant, conversation_id)

        resolve_first = (
            decision.intent == "add_sale_item"
            and bool(decision.product_query)
            and bool(decision.quantity)
            and (decision.unit is None or "unit" in decision.missing_fields)
        )
        if decision.missing_fields and not resolve_first:
            self._remember_missing_unit(decision, tenant, conversation_id)
            return AgentResponse(
                text=decision.clarification_question or "Necesito un dato más para continuar.",
                ui=[],
            )

        if decision.candidate_tool or resolve_first:
            tool_id = decision.candidate_tool or "sale.add_item@1"
            registered = self.tools.is_registered(tool_id)
            policy = self.policies.evaluate(
                PolicyRequest(
                    action="execute_tool",
                    tool_id=tool_id,
                    tool_registered=registered,
                    from_llm=True,
                    arguments={
                        "quantity": decision.quantity,
                        "unit": decision.unit,
                        "missing_essentials": bool(decision.missing_fields) and not resolve_first,
                    },
                )
            )
            if not registered or policy.decision.value == "deny":
                return AgentResponse(
                    text=decision.clarification_question or "That action is not available.",
                    ui=[],
                )
            if self.workflow is not None and decision.intent == "add_sale_item":
                if tenant is None:
                    return AgentResponse(text="That action is not available.", ui=[])
                result = self.workflow.execute(
                    tenant=tenant,
                    decision=decision,
                    conversation_id=conversation_id,
                    idempotency_key=context["idempotency_key"],
                    correlation_id=context.get("correlation_id", "unknown"),
                    policy=policy,
                    fail_after_write=bool(context.get("fail_after_write")),
                    raw_message=message,
                )
                if result.kind == "clarify_unit":
                    self._remember_missing_unit(decision, tenant, conversation_id)
                    return AgentResponse(text=result.text, ui=[])
                if result.kind in {"clarify", "deny"}:
                    return AgentResponse(text=result.text, ui=[])
                if self.pending is not None:
                    self.pending.clear(tenant=tenant, conversation_id=conversation_id)
                ui: list[dict[str, Any]] = []
                if self.ui_composer is not None:
                    fallback = result.text
                    contract = GenerativeUIContract(
                        component="sale_item_added",
                        version=1,
                        data={
                            "sale_session_id": result.payload["sale_session_id"],
                            "sale_item_id": result.payload["sale_item_id"],
                            "product_name": result.payload["product_name"],
                            "quantity_input": result.payload["quantity_input"],
                            "unit_input": result.payload["unit_input"],
                            "quantity_normalized": result.payload["quantity_normalized"],
                            "unit_normalized": result.payload["unit_normalized"],
                            "unit_price": result.payload["unit_price"],
                            "line_total": result.payload["line_total"],
                            "session_item_count": result.payload["session_item_count"],
                            "session_total": result.payload["session_total"],
                        },
                        actions=[],
                        fallback_text=fallback,
                    )
                    ui = [self.ui_composer.compose(contract)]
                return AgentResponse(text=result.text, ui=ui)

        result = {
            "text": decision.clarification_question or "Lumo foundation received the message.",
            "intent": decision.intent,
        }
        return self.provider.compose(result, [])

    def _handle_totalize(
        self,
        decision: AgentDecision,
        message: str,
        context: dict[str, Any],
        tenant: TenantContext | None,
        conversation_id: str | None,
    ) -> AgentResponse:
        registered = self.tools.is_registered("sale.totalize@1")
        policy = self.policies.evaluate(
            PolicyRequest(
                action="execute_tool",
                tool_id="sale.totalize@1",
                tool_registered=registered,
                from_llm=True,
                arguments={},
            )
        )
        if not registered or policy.decision.value == "deny":
            return AgentResponse(
                text=decision.clarification_question or "That action is not available.",
                ui=[],
            )
        if self.totalize is None or tenant is None:
            return AgentResponse(text="That action is not available.", ui=[])
        result = self.totalize.execute(
            tenant=tenant,
            conversation_id=conversation_id,
            idempotency_key=context["idempotency_key"],
            correlation_id=context.get("correlation_id", "unknown"),
            policy=policy,
            fail_after_write=bool(context.get("fail_after_write")),
            raw_message=message,
        )
        if result.kind in {"clarify", "deny"}:
            return AgentResponse(text=result.text, ui=[])
        ui: list[dict[str, Any]] = []
        if self.ui_composer is not None:
            contract = GenerativeUIContract(
                component="sale_summary",
                version=1,
                data={
                    "sale_session_id": result.payload["sale_session_id"],
                    "status": result.payload["status"],
                    "currency": result.payload["currency"],
                    "item_count": result.payload["item_count"],
                    "subtotal": result.payload["subtotal"],
                    "total": result.payload["total"],
                    "items": result.payload["items"],
                },
                actions=[],
                fallback_text=result.text,
            )
            ui = [self.ui_composer.compose(contract)]
        return AgentResponse(text=result.text, ui=ui)

    def _merge_pending(
        self,
        decision: AgentDecision,
        tenant: TenantContext | None,
        conversation_id: str | None,
    ) -> AgentDecision:
        if self.pending is None or tenant is None:
            return decision
        if decision.unit and (not decision.product_query or not decision.quantity):
            stored = self.pending.get(tenant=tenant, conversation_id=conversation_id)
            if stored is None:
                return decision
            return decision.model_copy(
                update={
                    "intent": "add_sale_item",
                    "product_query": stored.product_query,
                    "quantity": stored.quantity,
                    "missing_fields": [],
                    "candidate_tool": "sale.add_item@1",
                    "clarification_question": None,
                }
            )
        return decision

    def _remember_missing_unit(
        self,
        decision: AgentDecision,
        tenant: TenantContext | None,
        conversation_id: str | None,
    ) -> None:
        if self.pending is None or tenant is None:
            return
        if "unit" in decision.missing_fields and decision.product_query and decision.quantity:
            self.pending.put(
                tenant=tenant,
                conversation_id=conversation_id,
                product_query=decision.product_query,
                quantity=decision.quantity,
            )


def validate_decision_payload(payload: Any) -> AgentDecision:
    return AgentDecision.model_validate(payload)
