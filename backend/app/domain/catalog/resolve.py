from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.domain.catalog.normalize import normalize_product_name
from app.domain.catalog.product import Product, ProductAlias, ProductStatus


class ProductMatch(StrEnum):
    UNIQUE = "unique"
    AMBIGUOUS = "ambiguous"
    NONE = "none"


@dataclass(frozen=True, slots=True)
class ResolveResult:
    match: ProductMatch
    product: Product | None
    candidates: tuple[Product, ...]
    inactive_collision: bool = False


def resolve_products(
    query: str,
    products: list[Product],
    aliases: list[ProductAlias] | None = None,
) -> ResolveResult:
    normalized = normalize_product_name(query)
    alias_product_ids = {
        alias.product_id
        for alias in (aliases or [])
        if alias.normalized_alias == normalized
    }
    matches = [
        product
        for product in products
        if product.status is ProductStatus.ACTIVE
        and (product.normalized_name == normalized or product.id in alias_product_ids)
    ]
    if len(matches) == 1:
        return ResolveResult(match=ProductMatch.UNIQUE, product=matches[0], candidates=())
    if len(matches) > 1:
        return ResolveResult(match=ProductMatch.AMBIGUOUS, product=None, candidates=tuple(matches))
    inactive = _inactive_collision(normalized, products, alias_product_ids)
    return ResolveResult(match=ProductMatch.NONE, product=None, candidates=(), inactive_collision=inactive)


def _inactive_collision(normalized: str, products: list[Product], alias_product_ids: set) -> bool:
    for product in products:
        if product.status is ProductStatus.ACTIVE:
            continue
        if product.normalized_name == normalized or product.id in alias_product_ids:
            return True
    return False
