from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.shared.errors import TenantScopeViolationError, ValidationAppError
from app.domain.shared.tenant import TenantContext
from app.infrastructure.persistence.models import BusinessRow, FoundationNoteRow, MembershipRow, UserRow
from app.infrastructure.persistence.rls import set_current_business_id


class IdentityRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_business(self, tenant: TenantContext) -> BusinessRow:
        if tenant is None:  # type: ignore[truthy-bool]
            raise ValidationAppError("tenant is required")
        set_current_business_id(self._session, tenant.business_id)
        row = self._session.get(BusinessRow, tenant.business_id)
        if row is None:
            raise TenantScopeViolationError("business not found")
        return row

    def get_actor(self, tenant: TenantContext) -> UserRow:
        set_current_business_id(self._session, tenant.business_id)
        row = self._session.get(UserRow, tenant.actor_id)
        if row is None or row.business_id != tenant.business_id:
            raise TenantScopeViolationError("user not found")
        return row

    def require_membership(self, tenant: TenantContext) -> MembershipRow:
        set_current_business_id(self._session, tenant.business_id)
        row = self._session.scalar(
            select(MembershipRow).where(
                MembershipRow.business_id == tenant.business_id,
                MembershipRow.user_id == tenant.actor_id,
            )
        )
        if row is None:
            raise TenantScopeViolationError("membership not found")
        return row


class FoundationNoteRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, *, tenant: TenantContext, text: str) -> FoundationNoteRow:
        if tenant is None:  # type: ignore[truthy-bool]
            raise ValidationAppError("tenant is required")
        set_current_business_id(self._session, tenant.business_id)
        row = FoundationNoteRow(
            business_id=tenant.business_id,
            actor_id=tenant.actor_id,
            text=text,
        )
        self._session.add(row)
        self._session.flush()
        return row

    def get(self, *, tenant: TenantContext, note_id: UUID) -> FoundationNoteRow:
        if tenant is None:  # type: ignore[truthy-bool]
            raise ValidationAppError("tenant is required")
        set_current_business_id(self._session, tenant.business_id)
        row = self._session.get(FoundationNoteRow, note_id)
        if row is None or row.business_id != tenant.business_id:
            raise TenantScopeViolationError("note not found")
        return row
