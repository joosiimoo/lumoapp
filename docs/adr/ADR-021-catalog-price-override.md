# ADR-021: Catalog price override is per-sale evidence, not a catalog mutation

- Status: Accepted
- Date: 2026-09-23

## Decision

A merchant may sell a catalog product at a unit price other than `Product.current_price`. That difference is evidence on the `SaleItem`. It does not change the catalog, and it is not a promotion or a discount rule.

`Product.current_price` stays catalog truth. A catalog `SaleItem` stores `catalog_unit_price_snapshot` from the product price read at commit. `unit_price` is the amount charged. When they differ, `price_override_reason` is the merchant's non-empty text. When they are equal, the reason is null. A `free_concept` line keeps both new fields null. There is no `price_source` or `pricing_mode`. Override status is the catalog row whose charged price differs from the snapshot.

The reason is required, comes from the merchant, and is not generated or inferred. The maximum is 200 characters after trim and whitespace collapse. Accents and casing stay. Blank and overlong text do not complete the line and are not truncated.

The first utterance that names a different grounded price asks why and writes nothing. The reason turn is the confirmation. It opens the existing add-item write transaction and locks the product with `SELECT ... FOR UPDATE` before any session insert or idempotency reservation. The locked `Product.current_price` is the snapshot. If that price changed and still differs from the proposed amount, the transaction rolls back with no item, no new session, and no idempotency row, and the question restarts against the locked price. If the proposed amount now equals the locked price, the line is a normal catalog line and the reason is not stored. The lock is not held while waiting for the next message. `Product.current_price` is not updated.

A normal catalog line takes `catalog_unit_price_snapshot`, `unit_price`, and `line_total` from one product read inside that same style of write transaction. It does not add a product row lock. The resolve-time price is not stored beside a different commit-time price.

`line_total` is `quantity_normalized * unit_price` through `Money.times` (`ROUND_HALF_UP` to `0.01`). For a kilogram catalog product, the grounded amount is per kilogram without a separate "por kilo". Flutter and the LLM do not calculate the total.

Pending state stays in the in-memory clarification store under `catalog_price_override`. It is not schema `memory` and not a draft `SaleItem`.

`sale.add_item@1` remains the only add-item tool. Catalog mode may carry `price_override` only after the reason flow, or on a direct call that still passes the same checks. The server does not trust a model-only price or a model-only reason. No call updates `Product.current_price`.

Audit stays `sale.add_item@1` and records the snapshot, the charged price, and the reason. The outbox event stays `sale.item.added` with those facts. There is no `sale.price.overridden` event. Cards stay version `1` and may show `catalog_unit_price` only on an override line.

Alembic `0009_catalog_price_override` backfills existing catalog rows with the snapshot equal to `unit_price`. Downgrade to `0008` aborts only when a catalog override exists: `source_type = 'catalog'` and either a non-null reason or a snapshot distinct from `unit_price`. A free-concept row, whose snapshot is null, does not block that downgrade. `NULL IS DISTINCT FROM` a price is true in PostgreSQL, so the predicate is limited to catalog rows. An abort deletes nothing. RLS is unchanged.

`sale.totalize@1`, payment, OperationalDay, CashCount, and Daily Close keep using persisted `line_total`. `sale.commit@1` still refuses a closed operational day.

ADR-015 through ADR-020 are unchanged. ADR-020 recorded override as future work for the free-concept change. This decision is that later work, limited to a catalog line.

## Consequences

A sale line can show both the catalog price at commit and the price actually charged, with the merchant's reason, without a second pricing engine. A catalog price that moves during the question is not applied silently. Free-concept prices stay explicit and do not ask for an override reason.
