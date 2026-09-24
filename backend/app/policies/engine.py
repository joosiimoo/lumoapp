from __future__ import annotations

from decimal import Decimal

from app.policies import PolicyDecision, PolicyDecisionName, PolicyEngine, PolicyRequest

SEC_001 = "SEC-001"
SEC_002 = "SEC-002"
SEC_003 = "SEC-003"
INT_001 = "INT-001"
INT_003 = "INT-003"
INTP_001 = "INTP-001"
INTP_002 = "INTP-002"
CAT_001 = "CAT-001"
CAT_002 = "CAT-002"
SALE_001 = "SALE-001"
SALE_002 = "SALE-002"
SALE_003 = "SALE-003"
SALE_004 = "SALE-004"
SALE_005 = "SALE-005"
PAY_001 = "PAY-001"
DAY_001 = "DAY-001"
CLOSE_001 = "CLOSE-001"
CLOSE_002 = "CLOSE-002"
CLOSE_003 = "CLOSE-003"

REGISTERED_SLICE_TOOLS = {
    "catalog.resolve_product@1",
    "sale.start@1",
    "sale.add_item@1",
    "sale.totalize@1",
    "sale.commit@1",
    "operational_day.summary@1",
    "closing.submit_cash_count@1",
    "closing.prepare@1",
    "closing.confirm@1",
}

CLOSING_TOOLS = {
    "closing.submit_cash_count@1": CLOSE_001,
    "closing.prepare@1": CLOSE_002,
    "closing.confirm@1": CLOSE_003,
}
SERVER_OWNED_CASH_ARGUMENTS = frozenset(
    {
        "expected_cash",
        "counted_cash",
        "cash_difference",
        "cash_status",
        "operational_day_id",
        "business_date",
    }
)
SERVER_OWNED_CLOSE_ARGUMENTS = frozenset(
    {
        "expected_cash",
        "counted_cash",
        "cash_difference",
        "cash_status",
        "operational_day_id",
        "closing_snapshot_id",
        "business_date",
        "closed_at",
        "sale_count",
        "gross_sales_total",
        "cash_total",
        "card_total",
        "transfer_total",
        "currency",
        "actor_id",
        "cash_count_id",
    }
)


class FoundationPolicyEngine:
    def evaluate(self, request: PolicyRequest) -> PolicyDecision:
        if request.from_llm and request.action in {"mutate", "persist", "execute_sql"}:
            return PolicyDecision(
                decision=PolicyDecisionName.DENY,
                rule_ids=[SEC_001],
                reason_code="llm_must_not_mutate",
            )
        if request.tool_id and not request.tool_registered:
            return PolicyDecision(
                decision=PolicyDecisionName.DENY,
                rule_ids=[SEC_002],
                reason_code="unregistered_tool",
            )
        if request.tool_id == "operational_day.summary@1":
            return PolicyDecision(
                decision=PolicyDecisionName.ALLOW,
                rule_ids=[DAY_001, SEC_003, INT_001, INT_003, INTP_001],
                reason_code="operational_day_summary_read",
            )
        arguments = request.arguments or {}
        if request.tool_id in CLOSING_TOOLS:
            return self._evaluate_closing(request.tool_id, arguments)
        if arguments.get("missing_essentials"):
            return PolicyDecision(
                decision=PolicyDecisionName.CLARIFY,
                rule_ids=[INTP_002],
                reason_code="essential_field_missing",
            )
        match = arguments.get("match")
        if match == "ambiguous":
            return PolicyDecision(
                decision=PolicyDecisionName.CLARIFY,
                rule_ids=[CAT_001],
                reason_code="ambiguous_product",
            )
        if match == "catalog_price_override_reason_required":
            return PolicyDecision(
                decision=PolicyDecisionName.CLARIFY,
                rule_ids=[CAT_001],
                reason_code="catalog_price_override_reason_required",
            )
        if arguments.get("catalog_price_override") is True:
            return PolicyDecision(
                decision=PolicyDecisionName.ALLOW,
                rule_ids=[SALE_001, CAT_001, SEC_003, INT_001, INT_003, INTP_001],
                reason_code="catalog_price_override",
            )
        if match == "none":
            return self._evaluate_free_concept(arguments)
        if arguments.get("product_status") == "inactive":
            return PolicyDecision(
                decision=PolicyDecisionName.DENY,
                rule_ids=[CAT_001],
                reason_code="inactive_product",
            )
        quantity = arguments.get("quantity")
        if quantity is not None:
            try:
                if Decimal(str(quantity)) <= 0:
                    return PolicyDecision(
                        decision=PolicyDecisionName.DENY,
                        rule_ids=[SALE_001],
                        reason_code="quantity_not_positive",
                    )
            except Exception:
                return PolicyDecision(
                    decision=PolicyDecisionName.DENY,
                    rule_ids=[SALE_001],
                    reason_code="quantity_not_positive",
                )
        if arguments.get("unit_unsupported"):
            return PolicyDecision(
                decision=PolicyDecisionName.DENY,
                rule_ids=[CAT_002],
                reason_code="unit_not_supported",
            )
        session_status = arguments.get("session_status")
        if request.tool_id == "sale.add_item@1" and session_status is not None:
            if session_status != "open":
                return PolicyDecision(
                    decision=PolicyDecisionName.DENY,
                    rule_ids=[SALE_002],
                    reason_code="sale_not_open",
                )
        if request.tool_id == "sale.totalize@1" and (
            "session_status" in arguments or "item_count" in arguments
        ):
            item_count = arguments.get("item_count") or 0
            try:
                count = int(item_count)
            except (TypeError, ValueError):
                count = 0
            if session_status == "ready_to_charge":
                return PolicyDecision(
                    decision=PolicyDecisionName.ALLOW,
                    rule_ids=[SALE_003, SEC_003, INT_001, INT_003, INTP_001],
                    reason_code="ready_to_charge_read_back",
                )
            if session_status == "open" and count >= 1:
                return PolicyDecision(
                    decision=PolicyDecisionName.ALLOW,
                    rule_ids=[SALE_003, SEC_003, INT_001, INT_003, INTP_001],
                    reason_code="open_session_with_items",
                )
            return PolicyDecision(
                decision=PolicyDecisionName.DENY,
                rule_ids=[SALE_003],
                reason_code="sale_empty",
            )
        if request.tool_id == "sale.commit@1":
            method = arguments.get("payment_method")
            if method not in {"cash", "card", "transfer"}:
                return PolicyDecision(
                    decision=PolicyDecisionName.CLARIFY,
                    rule_ids=[PAY_001],
                    reason_code="payment_method_unknown",
                )
            if "session_status" not in arguments:
                return PolicyDecision(
                    decision=PolicyDecisionName.ALLOW,
                    rule_ids=[SALE_004, PAY_001, SEC_003, INT_001, INT_003, INTP_001],
                    reason_code="payment_method_present",
                )
            if session_status == "ready_to_charge":
                return PolicyDecision(
                    decision=PolicyDecisionName.ALLOW,
                    rule_ids=[SALE_004, PAY_001, SEC_003, INT_001, INT_003, INTP_001],
                    reason_code="ready_to_charge_commit",
                )
            if session_status == "confirmed":
                return PolicyDecision(
                    decision=PolicyDecisionName.ALLOW,
                    rule_ids=[SALE_004, PAY_001, SEC_003, INT_001, INT_003, INTP_001],
                    reason_code="confirmed_read_back",
                )
            if session_status == "open":
                return PolicyDecision(
                    decision=PolicyDecisionName.DENY,
                    rule_ids=[SALE_004],
                    reason_code="sale_not_ready_to_charge",
                )
            return PolicyDecision(
                decision=PolicyDecisionName.DENY,
                rule_ids=[SALE_004],
                reason_code="sale_not_found",
            )
        return PolicyDecision(
            decision=PolicyDecisionName.ALLOW,
            rule_ids=[SEC_003, INT_001, INT_003, INTP_001],
            reason_code="arguments_must_be_revalidated",
        )

    def _evaluate_free_concept(self, arguments: dict[str, object]) -> PolicyDecision:
        if arguments.get("price_not_positive"):
            return PolicyDecision(
                decision=PolicyDecisionName.DENY,
                rule_ids=[SALE_005],
                reason_code="price_not_positive",
            )
        if arguments.get("price_basis_missing"):
            return PolicyDecision(
                decision=PolicyDecisionName.CLARIFY,
                rule_ids=[SALE_005],
                reason_code="price_basis_required",
            )
        if arguments.get("price_missing"):
            return PolicyDecision(
                decision=PolicyDecisionName.CLARIFY,
                rule_ids=[SALE_005],
                reason_code="price_required",
            )
        if arguments.get("quantity_missing"):
            return PolicyDecision(
                decision=PolicyDecisionName.CLARIFY,
                rule_ids=[SALE_005],
                reason_code="quantity_required",
            )
        if arguments.get("free_concept_complete"):
            return PolicyDecision(
                decision=PolicyDecisionName.ALLOW,
                rule_ids=[SALE_005, SEC_003, INT_001, INT_003, INTP_001],
                reason_code="free_concept_complete",
            )
        return PolicyDecision(
            decision=PolicyDecisionName.CLARIFY,
            rule_ids=[CAT_001],
            reason_code="product_not_found",
        )

    def _evaluate_closing(self, tool_id: str, arguments: dict[str, object]) -> PolicyDecision:
        rule_id = CLOSING_TOOLS[tool_id]
        if SERVER_OWNED_CASH_ARGUMENTS & set(arguments) or (
            tool_id == "closing.confirm@1" and SERVER_OWNED_CLOSE_ARGUMENTS & set(arguments)
        ):
            return PolicyDecision(
                decision=PolicyDecisionName.DENY,
                rule_ids=[rule_id],
                reason_code="model_supplied_cash_values",
            )
        if tool_id == "closing.prepare@1":
            return PolicyDecision(
                decision=PolicyDecisionName.ALLOW,
                rule_ids=[CLOSE_002, SEC_003, INT_001, INT_003, INTP_001],
                reason_code="close_preparation_read",
            )
        if tool_id == "closing.confirm@1":
            return PolicyDecision(
                decision=PolicyDecisionName.ALLOW,
                rule_ids=[CLOSE_003, SEC_003, INT_001, INT_003, INTP_001],
                reason_code="closing_confirmation",
            )
        if arguments.get("day_exists") is False:
            return PolicyDecision(
                decision=PolicyDecisionName.CLARIFY,
                rule_ids=[CLOSE_001],
                reason_code="operational_day_not_started",
            )
        amount = arguments.get("counted_amount")
        if amount is not None and not _is_cash_amount(amount):
            return PolicyDecision(
                decision=PolicyDecisionName.DENY,
                rule_ids=[CLOSE_001],
                reason_code="counted_amount_invalid",
            )
        return PolicyDecision(
            decision=PolicyDecisionName.ALLOW,
            rule_ids=[CLOSE_001, SEC_003, INT_001, INT_003, INTP_001],
            reason_code="cash_count_amount_present",
        )


def _is_cash_amount(value: object) -> bool:
    if isinstance(value, float):
        return False
    try:
        amount = Decimal(str(value))
    except (ArithmeticError, TypeError, ValueError):
        return False
    exponent = amount.as_tuple().exponent
    if not isinstance(exponent, int):
        return False
    return amount >= 0 and exponent >= -2


def build_policy_engine() -> PolicyEngine:
    return FoundationPolicyEngine()
