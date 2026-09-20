from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.domain.shared.errors import ValidationAppError


class GenerativeUIAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_id: str
    option_id: str | None = None
    context_token: str
    idempotency_key: str


class GenerativeUIContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    component: str
    version: int
    data: dict[str, Any] = Field(default_factory=dict)
    actions: list[GenerativeUIAction] = Field(default_factory=list)
    fallback_text: str


class GenerativeUIRegistration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    component: str
    version: int
    data_schema: dict[str, Any] = Field(default_factory=dict)


class GenerativeUIRegistry:
    def __init__(self) -> None:
        self._items: dict[tuple[str, int], GenerativeUIRegistration] = {}

    def register(self, item: GenerativeUIRegistration) -> None:
        self._items[(item.component, item.version)] = item

    def get(self, component: str, version: int) -> GenerativeUIRegistration | None:
        return self._items.get((component, version))


class GenerativeUIComposer:
    def __init__(self, registry: GenerativeUIRegistry) -> None:
        self._registry = registry

    def compose(self, contract: GenerativeUIContract) -> dict[str, Any]:
        if self._registry.get(contract.component, contract.version) is None:
            raise ValidationAppError(
                "unregistered generative UI component",
                details={"component": contract.component, "version": contract.version},
            )
        payload = contract.model_dump()
        forbidden = ("html", "widget", "flutter", "javascript")
        blob = str(payload).lower()
        if any(token in blob for token in ("<html", "<script")):
            raise ValidationAppError("generative UI must be declarative JSON")
        _ = forbidden
        return payload
