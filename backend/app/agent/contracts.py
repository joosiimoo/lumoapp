from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AgentEntity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    value: str | None = None
    confidence: float = 0.0
    provenance: Literal["user", "model", "system"] = "model"


class AgentDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: str
    entities: list[AgentEntity] = Field(default_factory=list)
    candidate_tool: str | None = None
    missing_fields: list[str] = Field(default_factory=list)
    clarification_question: str | None = None
    response_hints: list[str] = Field(default_factory=list)
    product_query: str | None = None
    quantity: str | None = None
    unit: Literal["gram", "kilogram", "unit", "package"] | None = None

    @field_validator("intent")
    @classmethod
    def intent_not_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("intent is required")
        return value


class AgentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    ui: list[dict[str, Any]] = Field(default_factory=list)


class ProviderStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ready: bool
    provider: str
    detail: str


class LLMProvider(Protocol):
    def interpret(
        self,
        message: str,
        context: dict[str, Any],
        allowed_tools: list[str],
    ) -> AgentDecision: ...

    def compose(self, result: dict[str, Any], ui_contracts: list[dict[str, Any]]) -> AgentResponse: ...

    def health(self) -> ProviderStatus: ...
