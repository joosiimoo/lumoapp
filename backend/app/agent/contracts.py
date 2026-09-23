from __future__ import annotations

import re
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

_COUNTED_AMOUNT = re.compile(r"^\d+(?:\.\d{1,2})?$")


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
    unit_price: str | None = None
    price_basis: Literal["per_each", "per_kilogram"] | None = None
    package_word: Literal["bolsa", "paquete"] | None = None
    payment_method: Literal["cash", "card", "transfer"] | None = None
    counted_amount: str | None = None

    @field_validator("intent")
    @classmethod
    def intent_not_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("intent is required")
        return value

    @field_validator("counted_amount")
    @classmethod
    def counted_amount_is_cash(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not _COUNTED_AMOUNT.match(value):
            raise ValueError("counted_amount must be non-negative with at most two decimals")
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
