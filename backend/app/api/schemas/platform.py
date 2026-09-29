from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SessionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor: dict
    business: dict
    onboarding_status: str
    currency: str | None = None
    timezone: str | None = None
    enabled_payment_methods: list[str] | None = None
    next_required_field: str | None = None
    ui: list[dict] = Field(default_factory=list)


class CreateNoteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)
    business_id: str | None = None


class NoteResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    text: str
    business_id: str
