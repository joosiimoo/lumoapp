from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

import jwt

CLOSING_ISSUER = "lumo"
CLOSING_TYPE = "closing_confirm"
_LIFETIME = timedelta(minutes=15)


class TokenVerdict(StrEnum):
    OK = "ok"
    MISSING = "missing"
    INVALID = "invalid"
    STALE = "stale"


def issue_closing_confirmation_token(
    *,
    secret: str,
    business_id: UUID,
    actor_id: UUID,
    operational_day_id: UUID,
    cash_count_id: UUID,
    fingerprint: str,
    issued_at: datetime,
) -> str:
    issued = int(issued_at.timestamp())
    payload = {
        "iss": CLOSING_ISSUER,
        "typ": CLOSING_TYPE,
        "business_id": str(business_id),
        "actor_id": str(actor_id),
        "operational_day_id": str(operational_day_id),
        "cash_count_id": str(cash_count_id),
        "fingerprint": fingerprint,
        "iat": issued,
        "exp": issued + int(_LIFETIME.total_seconds()),
    }
    token = jwt.encode(payload, secret, algorithm="HS256")
    return token if isinstance(token, str) else token.decode("ascii")


def verify_closing_confirmation_token(
    *,
    secret: str,
    token: str | None,
    business_id: UUID,
    actor_id: UUID,
    operational_day_id: UUID,
    cash_count_id: UUID,
    fingerprint: str,
    now: datetime,
) -> TokenVerdict:
    if token is None or not str(token).strip():
        return TokenVerdict.MISSING
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            options={"require": ["exp", "iat", "iss"], "verify_exp": False},
        )
    except jwt.PyJWTError:
        return TokenVerdict.INVALID
    if payload.get("iss") != CLOSING_ISSUER or payload.get("typ") != CLOSING_TYPE:
        return TokenVerdict.INVALID
    if payload.get("business_id") != str(business_id) or payload.get("actor_id") != str(actor_id):
        return TokenVerdict.INVALID
    if int(payload["exp"]) <= int(now.timestamp()):
        return TokenVerdict.INVALID
    if (
        payload.get("operational_day_id") != str(operational_day_id)
        or payload.get("cash_count_id") != str(cash_count_id)
        or payload.get("fingerprint") != fingerprint
    ):
        return TokenVerdict.STALE
    return TokenVerdict.OK
