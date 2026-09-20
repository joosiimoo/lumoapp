from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field


class PolicyDecisionName(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    CLARIFY = "clarify"
    CONFIRM = "confirm"


class PolicyDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: PolicyDecisionName
    rule_ids: list[str]
    reason_code: str
    evidence_requirements: list[str] = Field(default_factory=list)


class PolicyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str
    tool_id: str | None = None
    tool_registered: bool = False
    arguments: dict[str, Any] = Field(default_factory=dict)
    from_llm: bool = False


class PolicyEngine(Protocol):
    def evaluate(self, request: PolicyRequest) -> PolicyDecision: ...
