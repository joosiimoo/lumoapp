from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.domain.shared.tenant import TenantContext


@dataclass(frozen=True, slots=True)
class PendingSaleClarification:
    product_query: str
    quantity: str | None = None
    kind: str = "catalog_unit"
    unit: str | None = None
    unit_price: str | None = None
    price_basis: str | None = None
    package_word: str | None = None
    product_id: str | None = None
    observed_catalog_unit_price: str | None = None


class InMemoryPendingClarificationStore:
    """Minimal pending clarification. Not a memory module and not durable across processes."""

    def __init__(self) -> None:
        self._items: dict[tuple[UUID, UUID, str], PendingSaleClarification] = {}

    def _key(self, tenant: TenantContext, conversation_id: str | None) -> tuple[UUID, UUID, str]:
        return (tenant.business_id, tenant.actor_id, conversation_id or "")

    def get(self, *, tenant: TenantContext, conversation_id: str | None) -> PendingSaleClarification | None:
        return self._items.get(self._key(tenant, conversation_id))

    def put(
        self,
        *,
        tenant: TenantContext,
        conversation_id: str | None,
        product_query: str,
        quantity: str | None,
        kind: str = "catalog_unit",
        unit: str | None = None,
        unit_price: str | None = None,
        price_basis: str | None = None,
        package_word: str | None = None,
        product_id: str | None = None,
        observed_catalog_unit_price: str | None = None,
    ) -> None:
        self._items[self._key(tenant, conversation_id)] = PendingSaleClarification(
            product_query=product_query,
            quantity=quantity,
            kind=kind,
            unit=unit,
            unit_price=unit_price,
            price_basis=price_basis,
            package_word=package_word,
            product_id=product_id,
            observed_catalog_unit_price=observed_catalog_unit_price,
        )

    def clear(self, *, tenant: TenantContext, conversation_id: str | None) -> None:
        self._items.pop(self._key(tenant, conversation_id), None)
