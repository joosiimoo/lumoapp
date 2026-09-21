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
PAY_001 = "PAY-001"

REGISTERED_SLICE_TOOLS = {
    "catalog.resolve_product@1",
    "sale.start@1",
    "sale.add_item@1",
    "sale.totalize@1",
    "sale.commit@1",
}


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
        arguments = request.arguments or {}
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
        if match == "none":
            return PolicyDecision(
                decision=PolicyDecisionName.CLARIFY,
                rule_ids=[CAT_001],
                reason_code="product_not_found",
            )
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


def build_policy_engine() -> PolicyEngine:
    return FoundationPolicyEngine()
