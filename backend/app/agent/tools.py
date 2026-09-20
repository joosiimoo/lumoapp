from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ToolRegistration:
    tool_id: str
    version: int
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    permission: str
    policy_id: str
    requires_idempotency: bool
    side_effect: str

    @property
    def qualified_id(self) -> str:
        return f"{self.tool_id}@{self.version}"


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolRegistration] = {}

    def register(self, registration: ToolRegistration) -> None:
        self._tools[registration.qualified_id] = registration

    def get(self, qualified_id: str) -> ToolRegistration | None:
        return self._tools.get(qualified_id)

    def allowed_ids(self) -> list[str]:
        return sorted(self._tools)

    def is_registered(self, qualified_id: str) -> bool:
        return qualified_id in self._tools
