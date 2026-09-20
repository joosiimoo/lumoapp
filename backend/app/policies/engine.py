from __future__ import annotations

from app.policies import PolicyDecision, PolicyDecisionName, PolicyEngine, PolicyRequest

SEC_001 = "SEC-001"
SEC_002 = "SEC-002"
SEC_003 = "SEC-003"


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
        return PolicyDecision(
            decision=PolicyDecisionName.ALLOW,
            rule_ids=[SEC_003],
            reason_code="arguments_must_be_revalidated",
        )


def build_policy_engine() -> PolicyEngine:
    return FoundationPolicyEngine()
