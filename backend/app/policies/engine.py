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

REGISTERED_SLICE_TOOLS = {
    "catalog.resolve_product@1",
    "sale.start@1",
    "sale.add_item@1",
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
        return PolicyDecision(
            decision=PolicyDecisionName.ALLOW,
            rule_ids=[SEC_003, INT_001, INT_003, INTP_001],
            reason_code="arguments_must_be_revalidated",
        )


def build_policy_engine() -> PolicyEngine:
    return FoundationPolicyEngine()
