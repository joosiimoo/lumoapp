from __future__ import annotations

from uuid import UUID

import jwt

from app.bootstrap.settings import Settings
from app.domain.shared.errors import ForbiddenError, ValidationAppError
from app.domain.shared.tenant import TenantContext

DEV_ISSUER = "lumo-dev"


def issue_dev_token(*, user_id: UUID, business_id: UUID, secret: str) -> str:
    return jwt.encode(
        {
            "sub": str(user_id),
            "business_id": str(business_id),
            "iss": DEV_ISSUER,
            "typ": "dev",
        },
        secret,
        algorithm="HS256",
    )


def resolve_tenant_from_authorization(authorization: str | None, settings: Settings) -> TenantContext:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise ForbiddenError("authentication required")
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = jwt.decode(token, settings.dev_token_secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise ForbiddenError("invalid token") from exc
    if payload.get("iss") != DEV_ISSUER or payload.get("typ") != "dev":
        raise ForbiddenError("unsupported token")
    if not settings.allows_dev_tokens:
        raise ForbiddenError("dev tokens are not accepted in this environment")
    try:
        actor_id = UUID(str(payload["sub"]))
        business_id = UUID(str(payload["business_id"]))
    except (KeyError, ValueError) as exc:
        raise ValidationAppError("token is missing tenant claims") from exc
    return TenantContext(business_id=business_id, actor_id=actor_id)
