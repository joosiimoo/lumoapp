from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

import jwt

UI_ACTION_ISSUER = "lumo"
UI_ACTION_TYPE = "ui_action"
_LIFETIME = timedelta(minutes=15)


@dataclass(frozen=True, slots=True)
class VerifiedUiAction:
    action_id: str
    business_id: UUID
    actor_id: UUID
    conversation_id: str
    sale_session_id: UUID | None


def issue_ui_action_token(
    *,
    secret: str,
    action_id: str,
    business_id: UUID,
    actor_id: UUID,
    conversation_id: str,
    issued_at: datetime,
    sale_session_id: UUID | None = None,
) -> str:
    issued = int(issued_at.timestamp())
    payload: dict[str, str | int] = {
        "iss": UI_ACTION_ISSUER,
        "typ": UI_ACTION_TYPE,
        "action_id": action_id,
        "business_id": str(business_id),
        "actor_id": str(actor_id),
        "conversation_id": conversation_id,
        "iat": issued,
        "exp": issued + int(_LIFETIME.total_seconds()),
    }
    if sale_session_id is not None:
        payload["sale_session_id"] = str(sale_session_id)
    token = jwt.encode(payload, secret, algorithm="HS256")
    return token if isinstance(token, str) else token.decode("ascii")


def verify_ui_action_token(
    *,
    secret: str,
    token: str | None,
    action_id: str,
    business_id: UUID,
    actor_id: UUID,
    conversation_id: str,
    now: datetime,
    require_sale_session_id: bool,
) -> VerifiedUiAction | None:
    if token is None or not str(token).strip():
        return None
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            options={"require": ["exp", "iat", "iss"], "verify_exp": False},
        )
    except jwt.PyJWTError:
        return None
    if payload.get("iss") != UI_ACTION_ISSUER or payload.get("typ") != UI_ACTION_TYPE:
        return None
    if payload.get("action_id") != action_id:
        return None
    if payload.get("business_id") != str(business_id) or payload.get("actor_id") != str(actor_id):
        return None
    if payload.get("conversation_id") != conversation_id:
        return None
    if int(payload["exp"]) <= int(now.timestamp()):
        return None
    raw_session = payload.get("sale_session_id")
    if require_sale_session_id:
        if not isinstance(raw_session, str) or not raw_session.strip():
            return None
        try:
            sale_session_id = UUID(raw_session)
        except ValueError:
            return None
    else:
        if raw_session not in (None, ""):
            return None
        sale_session_id = None
    return VerifiedUiAction(
        action_id=action_id,
        business_id=business_id,
        actor_id=actor_id,
        conversation_id=conversation_id,
        sale_session_id=sale_session_id,
    )
