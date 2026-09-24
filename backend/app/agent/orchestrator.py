from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import ValidationError

from app.agent.contracts import AgentDecision, AgentResponse, LLMProvider
from app.agent.generative_ui import GenerativeUIAction, GenerativeUIComposer, GenerativeUIContract
from app.agent.tools import ToolRegistry
from app.agent.ui_actions import (
    CONFIRM_CLOSE_ACTION_ID,
    REQUEST_CLOSE_ACTION_ID,
    UiActionRegistry,
)
from app.agent.providers.scripted import normalize_closed_phrase
from app.application.pending import InMemoryPendingClarificationStore
from app.application.closing_confirmation_token import issue_closing_confirmation_token
from app.application.ui_action_token import issue_ui_action_token, verify_ui_action_token
from app.domain.shared.errors import ValidationAppError
from app.domain.shared.ids import new_uuid7
from app.application.workflows.add_catalog_sale_item import AddCatalogSaleItem
from app.application.workflows.commit_sale_session import CommitSaleSession
from app.application.workflows.confirm_daily_close import ConfirmDailyClose
from app.application.workflows.get_daily_close_preparation import (
    CASH_COUNT_REQUIRED_TEXT,
    NO_OPEN_DAY_TEXT,
    GetDailyClosePreparation,
    confirmed_ui_data,
    fingerprint_for_preparation,
    preparation_ui_data,
    request_close_text,
)
from app.application.workflows.get_operational_day_summary import GetOperationalDaySummary
from app.application.workflows.record_cash_count import RecordCashCount
from app.application.workflows.totalize_sale_session import TotalizeSaleSession
from app.domain.sales.concept import basis_question, ground_user_price, parse_sale_utterance
from app.domain.shared.tenant import TenantContext
from app.infrastructure.persistence.base import utcnow
from app.policies import PolicyEngine, PolicyRequest


_CLOSED_INTENTS = frozenset(
    {
        "totalize_sale",
        "commit_sale",
        "day_summary",
        "record_cash_count",
        "close_preparation",
        "request_close",
        "confirm_close",
    }
)
_CLOSED_TOOLS = frozenset(
    {
        "sale.totalize@1",
        "sale.commit@1",
        "operational_day.summary@1",
        "closing.submit_cash_count@1",
        "closing.prepare@1",
        "closing.confirm@1",
    }
)


def _closed_sale_intent(decision: AgentDecision) -> bool:
    return decision.intent in _CLOSED_INTENTS or decision.candidate_tool in _CLOSED_TOOLS


class LumoOrchestrator:
    def handle(self, message: str, context: dict[str, Any] | None = None) -> AgentResponse: ...


@dataclass
class FoundationOrchestrator:
    provider: LLMProvider
    tools: ToolRegistry
    policies: PolicyEngine
    workflow: AddCatalogSaleItem | None = None
    totalize: TotalizeSaleSession | None = None
    commit: CommitSaleSession | None = None
    day_summary: GetOperationalDaySummary | None = None
    record_cash_count: RecordCashCount | None = None
    close_preparation: GetDailyClosePreparation | None = None
    confirm_close: ConfirmDailyClose | None = None
    token_secret: str = ""
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
        if self.workflow is not None and tenant is not None and context.get("idempotency_key"):
            replayed = self.workflow.replay_override_completion(
                tenant=tenant,
                idempotency_key=context["idempotency_key"],
                raw_message=message,
            )
            if replayed is not None:
                return self._finish_add_item(replayed, tenant, conversation_id)
        stored = (
            self.pending.get(tenant=tenant, conversation_id=conversation_id)
            if self.pending is not None and tenant is not None
            else None
        )
        if (
            stored is not None
            and stored.kind == "catalog_price_override"
            and tenant is not None
            and self.pending is not None
        ):
            override_turn = self._catalog_override_turn(
                message, decision, context, tenant, conversation_id, stored
            )
            if override_turn is not None:
                return override_turn
            stored = self.pending.get(tenant=tenant, conversation_id=conversation_id)
        if self.pending is not None and tenant is not None:
            repeated = self._mass_basis_yes_no(message, tenant, conversation_id)
            if repeated is not None:
                return AgentResponse(text=repeated, ui=[])
        if (
            stored is not None
            and decision.product_query
            and decision.product_query != stored.product_query
            and self.pending is not None
            and tenant is not None
        ):
            self.pending.clear(tenant=tenant, conversation_id=conversation_id)
            stored = None
        decision = self._merge_pending(decision, tenant, conversation_id)
        grounded_now = ground_user_price(message)
        pending_price = None
        if stored is not None and stored.unit_price and grounded_now.amount is None and grounded_now.problem is None:
            pending_price = stored.unit_price

        if decision.intent == "day_summary" or decision.candidate_tool == "operational_day.summary@1":
            return self._handle_day_summary(decision, context, tenant)

        if decision.intent == "record_cash_count" or decision.candidate_tool == "closing.submit_cash_count@1":
            return self._handle_cash_count(decision, message, context, tenant, conversation_id)

        if decision.intent == "request_close":
            return self._handle_request_close(decision, context, tenant)

        if decision.intent == "confirm_close" or decision.candidate_tool == "closing.confirm@1":
            return self._handle_confirm_close(decision, message, context, tenant, conversation_id)

        if decision.intent == "close_preparation" or decision.candidate_tool == "closing.prepare@1":
            return self._handle_close_preparation(decision, context, tenant)

        if decision.intent == "commit_sale" or decision.candidate_tool == "sale.commit@1":
            return self._handle_commit(decision, message, context, tenant, conversation_id)

        if decision.intent == "totalize_sale" or decision.candidate_tool == "sale.totalize@1":
            return self._handle_totalize(decision, message, context, tenant, conversation_id)

        if decision.intent == "add_sale_item" and decision.product_query:
            if self.workflow is None or tenant is None:
                return AgentResponse(text="That action is not available.", ui=[])
            tool_id = "sale.add_item@1"
            registered = self.tools.is_registered(tool_id)
            policy = self.policies.evaluate(
                PolicyRequest(
                    action="execute_tool",
                    tool_id=tool_id,
                    tool_registered=registered,
                    from_llm=True,
                    arguments={"quantity": decision.quantity, "unit": decision.unit},
                )
            )
            if not registered or policy.decision.value == "deny":
                return AgentResponse(text=decision.clarification_question or "That action is not available.", ui=[])
            result = self.workflow.execute(
                tenant=tenant,
                decision=decision,
                conversation_id=conversation_id,
                idempotency_key=context["idempotency_key"],
                correlation_id=context.get("correlation_id", "unknown"),
                policy=policy,
                fail_after_write=bool(context.get("fail_after_write")),
                raw_message=message,
                pending_unit_price=pending_price,
            )
            return self._finish_add_item(result, tenant, conversation_id)

        if decision.intent == "add_sale_item" or decision.missing_fields:
            if (
                stored is not None
                and stored.kind == "free_concept"
                and stored.unit in {"gram", "kilogram"}
                and stored.unit_price
                and not stored.price_basis
            ):
                return AgentResponse(text=basis_question(Decimal(stored.unit_price)), ui=[])
            return AgentResponse(
                text=decision.clarification_question or "¿Qué vendiste?",
                ui=[],
            )

        result = {
            "text": decision.clarification_question or "Lumo foundation received the message.",
            "intent": decision.intent,
        }
        return self.provider.compose(result, [])

    def _catalog_override_turn(
        self,
        message: str,
        decision: AgentDecision,
        context: dict[str, Any],
        tenant: TenantContext,
        conversation_id: str | None,
        stored: Any,
    ) -> AgentResponse | None:
        if self.pending is None:
            return None
        normalized = normalize_closed_phrase(message)
        if normalized in {"cancelar", "cancela", "no"}:
            self.pending.clear(tenant=tenant, conversation_id=conversation_id)
            return AgentResponse(text="Listo, no registré ese producto.", ui=[])
        if _closed_sale_intent(decision):
            self.pending.clear(tenant=tenant, conversation_id=conversation_id)
            return None
        parsed = parse_sale_utterance(message)
        if parsed is not None and parsed.kind == "utterance" and parsed.quantity and parsed.display_span:
            self.pending.clear(tenant=tenant, conversation_id=conversation_id)
            return None
        if self.workflow is None:
            return AgentResponse(text="That action is not available.", ui=[])
        result = self.workflow.complete_price_override(
            tenant=tenant,
            pending=stored,
            raw_message=message,
            conversation_id=conversation_id,
            idempotency_key=context["idempotency_key"],
            correlation_id=context.get("correlation_id", "unknown"),
            fail_after_write=bool(context.get("fail_after_write")),
        )
        return self._finish_add_item(result, tenant, conversation_id)

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
                actions=self._payment_actions(
                    tenant=tenant,
                    conversation_id=conversation_id,
                    sale_session_id=result.payload["sale_session_id"],
                    issued_at=context.get("now") or utcnow(),
                    status=result.payload["status"],
                ),
                fallback_text=result.text,
            )
            ui = [self.ui_composer.compose(contract)]
        return AgentResponse(text=result.text, ui=ui)

    def _handle_commit(
        self,
        decision: AgentDecision,
        message: str,
        context: dict[str, Any],
        tenant: TenantContext | None,
        conversation_id: str | None,
    ) -> AgentResponse:
        registered = self.tools.is_registered("sale.commit@1")
        policy = self.policies.evaluate(
            PolicyRequest(
                action="execute_tool",
                tool_id="sale.commit@1",
                tool_registered=registered,
                from_llm=True,
                arguments={"payment_method": decision.payment_method},
            )
        )
        if not registered or policy.decision.value == "deny":
            return AgentResponse(
                text=decision.clarification_question or "That action is not available.",
                ui=[],
            )
        if policy.decision.value == "clarify":
            return AgentResponse(
                text=decision.clarification_question
                or "¿Cómo pagó? Puedo registrar *efectivo*, *tarjeta* o *transferencia*.",
                ui=[],
            )
        if self.commit is None or tenant is None:
            return AgentResponse(text="That action is not available.", ui=[])
        result = self.commit.execute(
            tenant=tenant,
            conversation_id=conversation_id,
            payment_method=decision.payment_method,
            idempotency_key=context["idempotency_key"],
            correlation_id=context.get("correlation_id", "unknown"),
            policy=policy,
            fail_after_write=bool(context.get("fail_after_write")),
            raw_message=message,
            confirmed_at=context.get("now"),
        )
        return self._sale_confirmed_response(result)

    def _sale_confirmed_response(self, result: Any) -> AgentResponse:
        if result.kind in {"clarify", "deny", "stale"}:
            return AgentResponse(text=result.text, ui=[])
        ui: list[dict[str, Any]] = []
        if self.ui_composer is not None:
            contract = GenerativeUIContract(
                component="sale_confirmed",
                version=1,
                data={
                    "sale_session_id": result.payload["sale_session_id"],
                    "payment_id": result.payload["payment_id"],
                    "status": result.payload["status"],
                    "currency": result.payload["currency"],
                    "item_count": result.payload["item_count"],
                    "total": result.payload["total"],
                    "payment": result.payload["payment"],
                    "items": result.payload["items"],
                },
                actions=[],
                fallback_text=result.text,
            )
            ui = [self.ui_composer.compose(contract)]
        return AgentResponse(text=result.text, ui=ui)

    def _handle_day_summary(
        self,
        decision: AgentDecision,
        context: dict[str, Any],
        tenant: TenantContext | None,
    ) -> AgentResponse:
        registered = self.tools.is_registered("operational_day.summary@1")
        policy = self.policies.evaluate(
            PolicyRequest(
                action="execute_tool",
                tool_id="operational_day.summary@1",
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
        if self.day_summary is None or tenant is None:
            return AgentResponse(text="That action is not available.", ui=[])
        result = self.day_summary.execute(tenant=tenant, now=context.get("now"))
        ui: list[dict[str, Any]] = []
        if self.ui_composer is not None:
            contract = GenerativeUIContract(
                component="operational_day_summary",
                version=1,
                data={
                    "operational_day_id": result["operational_day_id"],
                    "business_date": result["business_date"],
                    "status": result["status"],
                    "currency": result["currency"],
                    "sale_count": result["sale_count"],
                    "gross_sales_total": result["gross_sales_total"],
                    "cash_total": result["cash_total"],
                    "card_total": result["card_total"],
                    "transfer_total": result["transfer_total"],
                },
                actions=[],
                fallback_text=result["text"],
            )
            ui = [self.ui_composer.compose(contract)]
        return AgentResponse(text=result["text"], ui=ui)

    def _handle_cash_count(
        self,
        decision: AgentDecision,
        message: str,
        context: dict[str, Any],
        tenant: TenantContext | None,
        conversation_id: str | None,
    ) -> AgentResponse:
        registered = self.tools.is_registered("closing.submit_cash_count@1")
        policy = self.policies.evaluate(
            PolicyRequest(
                action="execute_tool",
                tool_id="closing.submit_cash_count@1",
                tool_registered=registered,
                from_llm=True,
                arguments={"counted_amount": decision.counted_amount},
            )
        )
        if not registered or policy.decision.value == "deny":
            return AgentResponse(
                text=decision.clarification_question or "That action is not available.",
                ui=[],
            )
        if self.record_cash_count is None or tenant is None or decision.counted_amount is None:
            return AgentResponse(text="That action is not available.", ui=[])
        result = self.record_cash_count.execute(
            tenant=tenant,
            conversation_id=conversation_id,
            counted_amount=decision.counted_amount,
            idempotency_key=context["idempotency_key"],
            correlation_id=context.get("correlation_id", "unknown"),
            policy=policy,
            fail_after_write=bool(context.get("fail_after_write")),
            raw_message=message,
            counted_at=context.get("now"),
        )
        if result.kind in {"clarify", "deny"}:
            return AgentResponse(text=result.text, ui=[])
        return AgentResponse(
            text=result.text,
            ui=self._preparation_ui(result.payload, tenant, conversation_id, context),
        )

    def _handle_close_preparation(
        self,
        decision: AgentDecision,
        context: dict[str, Any],
        tenant: TenantContext | None,
    ) -> AgentResponse:
        registered = self.tools.is_registered("closing.prepare@1")
        policy = self.policies.evaluate(
            PolicyRequest(
                action="execute_tool",
                tool_id="closing.prepare@1",
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
        if self.close_preparation is None or tenant is None:
            return AgentResponse(text="That action is not available.", ui=[])
        payload = self.close_preparation.execute(tenant=tenant, now=context.get("now"))
        if payload.get("day_status") == "closed":
            return AgentResponse(text=payload["text"], ui=self._confirmed_ui(payload))
        return AgentResponse(
            text=payload["text"],
            ui=self._preparation_ui(payload, tenant, context.get("conversation_id"), context),
        )

    def _handle_request_close(
        self,
        decision: AgentDecision,
        context: dict[str, Any],
        tenant: TenantContext | None,
    ) -> AgentResponse:
        registered = self.tools.is_registered("closing.prepare@1")
        policy = self.policies.evaluate(
            PolicyRequest(
                action="execute_tool",
                tool_id="closing.prepare@1",
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
        if self.close_preparation is None or tenant is None:
            return AgentResponse(text="That action is not available.", ui=[])
        payload = self.close_preparation.execute(tenant=tenant, now=context.get("now"))
        if payload.get("day_status") == "closed":
            return AgentResponse(text=payload["text"], ui=self._confirmed_ui(payload))
        if payload.get("operational_day_id") is None:
            return AgentResponse(
                text=NO_OPEN_DAY_TEXT,
                ui=self._preparation_ui(payload, tenant, context.get("conversation_id"), context),
            )
        if payload.get("cash_count_id") is None or payload.get("cash_status") == "not_counted":
            return AgentResponse(
                text=CASH_COUNT_REQUIRED_TEXT,
                ui=self._preparation_ui(payload, tenant, context.get("conversation_id"), context),
            )
        issued_at = context.get("now") or utcnow()
        fingerprint = fingerprint_for_preparation(payload, business_id=tenant.business_id)
        payload = dict(payload)
        payload["confirmation_token"] = issue_closing_confirmation_token(
            secret=self.token_secret,
            business_id=tenant.business_id,
            actor_id=tenant.actor_id,
            operational_day_id=UUID(str(payload["operational_day_id"])),
            cash_count_id=UUID(str(payload["cash_count_id"])),
            fingerprint=fingerprint,
            issued_at=issued_at,
        )
        text = request_close_text(payload)
        payload["text"] = text
        return AgentResponse(
            text=text,
            ui=self._preparation_ui(payload, tenant, context.get("conversation_id"), context),
        )

    def _handle_confirm_close(
        self,
        decision: AgentDecision,
        message: str,
        context: dict[str, Any],
        tenant: TenantContext | None,
        conversation_id: str | None,
    ) -> AgentResponse:
        client_context = context.get("client_context") or {}
        confirmation_token = client_context.get("confirmation_token")
        if not isinstance(confirmation_token, str):
            confirmation_token = None
        registered = self.tools.is_registered("closing.confirm@1")
        policy = self.policies.evaluate(
            PolicyRequest(
                action="execute_tool",
                tool_id="closing.confirm@1",
                tool_registered=registered,
                from_llm=True,
                arguments={"confirmation_token": confirmation_token} if confirmation_token else {},
            )
        )
        if not registered or policy.decision.value == "deny":
            return AgentResponse(
                text=decision.clarification_question or "That action is not available.",
                ui=[],
            )
        if self.confirm_close is None or tenant is None:
            return AgentResponse(text="That action is not available.", ui=[])
        result = self.confirm_close.execute(
            tenant=tenant,
            conversation_id=conversation_id,
            confirmation_token=confirmation_token,
            idempotency_key=context["idempotency_key"],
            correlation_id=context.get("correlation_id", "unknown"),
            policy=policy,
            fail_after_write=bool(context.get("fail_after_write")),
            raw_message=message,
            now=context.get("now"),
            hash_material=context.get("hash_material"),
            ui_action_id=context.get("ui_action_id"),
        )
        if result.kind == "stale":
            return AgentResponse(
                text=result.text,
                ui=self._preparation_ui(result.payload, tenant, conversation_id, context),
            )
        if result.kind in {"committed", "read_back", "replay"} and result.payload.get("day_status") == "closed":
            return AgentResponse(text=result.text, ui=self._confirmed_ui(result.payload))
        return AgentResponse(text=result.text, ui=[])

    def _preparation_ui(
        self,
        payload: dict[str, Any],
        tenant: TenantContext | None,
        conversation_id: str | None,
        context: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if self.ui_composer is None:
            return []
        data = preparation_ui_data(payload)
        actions = self._close_actions(data, tenant, conversation_id, context.get("now") or utcnow())
        contract = GenerativeUIContract(
            component="daily_close_preparation",
            version=1,
            data=data,
            actions=actions,
            fallback_text=payload["text"],
        )
        return [self.ui_composer.compose(contract)]

    def _confirmed_ui(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        if self.ui_composer is None:
            return []
        contract = GenerativeUIContract(
            component="daily_close_confirmed",
            version=1,
            data=confirmed_ui_data(payload),
            actions=[],
            fallback_text=payload["text"],
        )
        return [self.ui_composer.compose(contract)]

    def handle_ui_action(self, action: dict[str, Any], context: dict[str, Any]) -> AgentResponse:
        registry = UiActionRegistry()
        action_id = str(action.get("action_id") or "")
        if not registry.is_registered(action_id):
            return AgentResponse(text="Esa acción no está disponible.", ui=[])
        tenant: TenantContext | None = context.get("tenant")
        conversation_id = context.get("conversation_id")
        if tenant is None or not isinstance(conversation_id, str) or not conversation_id:
            return AgentResponse(text="Esa acción no está disponible.", ui=[])
        now = context.get("now") or utcnow()
        token = action.get("context_token")
        token_text = token if isinstance(token, str) else None
        if registry.is_payment(action_id):
            verified = verify_ui_action_token(
                secret=self.token_secret,
                token=token_text,
                action_id=action_id,
                business_id=tenant.business_id,
                actor_id=tenant.actor_id,
                conversation_id=conversation_id,
                now=now,
                require_sale_session_id=True,
            )
            if verified is None or verified.sale_session_id is None or self.commit is None:
                return AgentResponse(text="No pude verificar esa acción.", ui=[])
            method = registry.payment_method(action_id)
            registered = self.tools.is_registered("sale.commit@1")
            policy = self.policies.evaluate(
                PolicyRequest(
                    action="execute_tool",
                    tool_id="sale.commit@1",
                    tool_registered=registered,
                    from_llm=True,
                    arguments={"payment_method": method},
                )
            )
            if not registered or policy.decision.value != "allow":
                return AgentResponse(text="That action is not available.", ui=[])
            result = self.commit.execute(
                tenant=tenant,
                conversation_id=conversation_id,
                payment_method=method,
                idempotency_key=context["idempotency_key"],
                correlation_id=context.get("correlation_id", "unknown"),
                policy=policy,
                fail_after_write=bool(context.get("fail_after_write")),
                confirmed_at=now,
                ui_action_id=action_id,
                bound_sale_session_id=verified.sale_session_id,
            )
            return self._sale_confirmed_response(result)
        if action_id == REQUEST_CLOSE_ACTION_ID:
            verified = verify_ui_action_token(
                secret=self.token_secret,
                token=token_text,
                action_id=action_id,
                business_id=tenant.business_id,
                actor_id=tenant.actor_id,
                conversation_id=conversation_id,
                now=now,
                require_sale_session_id=False,
            )
            if verified is None:
                return AgentResponse(text="No pude verificar esa acción.", ui=[])
            return self._handle_request_close(AgentDecision(intent="request_close"), context, tenant)
        updated = {
            **context,
            "client_context": {"confirmation_token": token_text},
            "hash_material": f"{action_id}|{conversation_id}|{token_text or ''}",
            "ui_action_id": action_id,
        }
        return self._handle_confirm_close(
            AgentDecision(intent="confirm_close", candidate_tool="closing.confirm@1"),
            "",
            updated,
            tenant,
            conversation_id,
        )

    def _payment_actions(
        self,
        *,
        tenant: TenantContext | None,
        conversation_id: str | None,
        sale_session_id: str,
        issued_at: Any,
        status: str,
    ) -> list[GenerativeUIAction]:
        if tenant is None or status != "ready_to_charge" or not conversation_id:
            return []
        actions: list[GenerativeUIAction] = []
        for action_id in UiActionRegistry().ids():
            if not UiActionRegistry().is_payment(action_id):
                continue
            actions.append(
                GenerativeUIAction(
                    action_id=action_id,
                    option_id=None,
                    context_token=issue_ui_action_token(
                        secret=self.token_secret,
                        action_id=action_id,
                        business_id=tenant.business_id,
                        actor_id=tenant.actor_id,
                        conversation_id=conversation_id,
                        issued_at=issued_at,
                        sale_session_id=UUID(str(sale_session_id)),
                    ),
                    idempotency_key=str(new_uuid7()),
                )
            )
        return actions

    def _close_actions(
        self,
        data: dict[str, Any],
        tenant: TenantContext | None,
        conversation_id: str | None,
        issued_at: Any,
    ) -> list[GenerativeUIAction]:
        if tenant is None or not conversation_id:
            return []
        if data.get("day_status") != "open":
            return []
        if data.get("operational_day_id") is None or data.get("cash_count_id") is None:
            return []
        if data.get("cash_status") not in {"balanced", "short", "over"}:
            return []
        token = data.get("confirmation_token")
        if isinstance(token, str) and token:
            if token != data.get("confirmation_token"):
                raise ValidationAppError("confirmation token mismatch")
            return [
                GenerativeUIAction(
                    action_id=CONFIRM_CLOSE_ACTION_ID,
                    option_id=None,
                    context_token=token,
                    idempotency_key=str(new_uuid7()),
                )
            ]
        return [
            GenerativeUIAction(
                action_id=REQUEST_CLOSE_ACTION_ID,
                option_id=None,
                context_token=issue_ui_action_token(
                    secret=self.token_secret,
                    action_id=REQUEST_CLOSE_ACTION_ID,
                    business_id=tenant.business_id,
                    actor_id=tenant.actor_id,
                    conversation_id=conversation_id,
                    issued_at=issued_at,
                ),
                idempotency_key=str(new_uuid7()),
            )
        ]

    def _finish_add_item(
        self,
        result: Any,
        tenant: TenantContext,
        conversation_id: str | None,
    ) -> AgentResponse:
        pending_payload = result.payload.get("pending") if isinstance(result.payload, dict) else None
        if pending_payload and self.pending is not None:
            self.pending.put(
                tenant=tenant,
                conversation_id=conversation_id,
                product_query=pending_payload["product_query"],
                quantity=pending_payload.get("quantity"),
                kind=pending_payload.get("kind", "free_concept"),
                unit=pending_payload.get("unit"),
                unit_price=pending_payload.get("unit_price"),
                price_basis=pending_payload.get("price_basis"),
                package_word=pending_payload.get("package_word"),
                product_id=pending_payload.get("product_id"),
                observed_catalog_unit_price=pending_payload.get("observed_catalog_unit_price"),
            )
            return AgentResponse(text=result.text, ui=[])
        if result.kind in {"clarify", "clarify_unit", "deny"}:
            if result.payload.get("clear_pending") and self.pending is not None:
                self.pending.clear(tenant=tenant, conversation_id=conversation_id)
            return AgentResponse(text=result.text, ui=[])
        if self.pending is not None:
            self.pending.clear(tenant=tenant, conversation_id=conversation_id)
        ui: list[dict[str, Any]] = []
        if self.ui_composer is not None and result.payload.get("sale_item_id"):
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
                    **(
                        {"catalog_unit_price": result.payload["catalog_unit_price"]}
                        if result.payload.get("catalog_unit_price")
                        else {}
                    ),
                    "session_item_count": result.payload["session_item_count"],
                    "session_total": result.payload["session_total"],
                },
                actions=[],
                fallback_text=result.text,
            )
            ui = [self.ui_composer.compose(contract)]
        return AgentResponse(text=result.text, ui=ui)

    def _mass_basis_yes_no(
        self,
        message: str,
        tenant: TenantContext,
        conversation_id: str | None,
    ) -> str | None:
        if self.pending is None:
            return None
        stored = self.pending.get(tenant=tenant, conversation_id=conversation_id)
        if stored is None or stored.kind != "free_concept" or stored.unit not in {"gram", "kilogram"}:
            return None
        if not stored.unit_price or stored.price_basis:
            return None
        if normalize_closed_phrase(message) not in {"si", "no"}:
            return None
        return basis_question(Decimal(stored.unit_price))

    def _merge_pending(
        self,
        decision: AgentDecision,
        tenant: TenantContext | None,
        conversation_id: str | None,
    ) -> AgentDecision:
        if self.pending is None or tenant is None:
            return decision
        stored = self.pending.get(tenant=tenant, conversation_id=conversation_id)
        if stored is None or decision.product_query:
            return decision
        if decision.price_basis == "per_kilogram" and stored.kind == "free_concept":
            return decision.model_copy(
                update={
                    "intent": "add_sale_item",
                    "product_query": stored.product_query,
                    "quantity": stored.quantity,
                    "unit": stored.unit,
                    "unit_price": stored.unit_price,
                    "price_basis": "per_kilogram",
                    "package_word": stored.package_word,
                    "missing_fields": [],
                    "candidate_tool": "sale.add_item@1",
                    "clarification_question": None,
                }
            )
        bare = decision.quantity and decision.unit_price and decision.quantity == decision.unit_price
        if bare and stored.kind == "free_concept" and not stored.quantity:
            return decision.model_copy(
                update={
                    "intent": "add_sale_item",
                    "product_query": stored.product_query,
                    "quantity": decision.quantity,
                    "unit": stored.unit,
                    "unit_price": None,
                    "package_word": stored.package_word,
                    "missing_fields": [],
                    "candidate_tool": "sale.add_item@1",
                    "clarification_question": None,
                }
            )
        if (decision.unit_price or bare) and stored.kind == "free_concept" and stored.unit in {"unit", "package"}:
            return decision.model_copy(
                update={
                    "intent": "add_sale_item",
                    "product_query": stored.product_query,
                    "quantity": stored.quantity,
                    "unit": stored.unit,
                    "unit_price": decision.unit_price,
                    "price_basis": "per_each",
                    "package_word": stored.package_word,
                    "missing_fields": [],
                    "candidate_tool": "sale.add_item@1",
                    "clarification_question": None,
                }
            )
        if decision.unit and not decision.product_query and stored.kind == "catalog_unit":
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
