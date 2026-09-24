## 1. Schema and migration

- [x] 1.1 Add Alembic `0009_catalog_price_override` with `down_revision = 0008_noncatalog_sale_item`: `catalog_unit_price_snapshot NUMERIC(12, 2) NULL`, `price_override_reason VARCHAR(200) NULL`, catalog backfill `snapshot = unit_price`, free-concept backfill both NULL, and `ck_sale_items_catalog_price`
- [x] 1.2 Disable RLS only while that upgrade backfills and validates, then `ENABLE` and `FORCE` it again, without granting `BYPASSRLS` or changing `tenant_isolation`
- [x] 1.3 Downgrade aborts with `cannot downgrade 0009 while a catalog price override exists` only when `source_type = 'catalog'` and (`price_override_reason` is non-null or `catalog_unit_price_snapshot` is distinct from `unit_price`). A free-concept null snapshot MUST NOT block downgrade. Otherwise drop the check and both columns without deleting sale rows
- [x] 1.4 Map both columns on `SaleItemRow` and the domain `SaleItem`, with no `price_source` or `pricing_mode`

## 2. Domain invariant

- [x] 2.1 Enforce catalog snapshot present, free-concept snapshot and reason null, and override only when `unit_price` differs and the reason is non-empty
- [x] 2.2 Calculate `line_total` with `Money.times` on the charged `unit_price`: normal catalog `0.900 * 25.00 = 22.50`, override `0.900 * 30.00 = 27.00`, package `3 * 11.00 = 33.00`
- [x] 2.3 Reject a non-positive override, scale greater than 2, a foreign currency, and a line total of `0.00` or less without persisting

## 3. Pending state

- [x] 3.1 Add `kind=catalog_price_override` with `product_query`, `product_id`, quantity, unit, grounded override amount, and `observed_catalog_unit_price`
- [x] 3.2 Store that pending on the first mismatch and do not create a `SaleSession`, `SaleItem`, schema `memory`, or idempotency row

## 4. Interpreter, cancellation, and reason

- [x] 4.1 While that kind is pending, treat `cancelar`, `cancela`, and `no` as cancellation with `Listo, no registré ese producto.` and no write
- [x] 4.2 Treat a `parse_sale_utterance` `utterance` that has quantity and a display span as a new sale that clears the pending override
- [x] 4.3 Treat other pending text as the reason after trim and whitespace collapse, preserving accents and casing, rejecting blank and length over 200 without truncation
- [x] 4.4 Clear the pending override and run a closed totalize, payment, day-summary, cash-count, or close intent without writing an override line
- [x] 4.5 A reason-shaped message with no pending override MUST NOT create an override

## 5. Catalog mismatch routing

- [x] 5.1 Keep equal and missing grounded prices on the normal catalog path. Inside the existing write transaction, derive `catalog_unit_price_snapshot`, `unit_price`, and `line_total` from one product read. Do not add a product row lock on this path
- [x] 5.2 Replace `catalog_price_mismatch` with the reason question `Tomate está registrado a $20.00 por kg. ¿Por qué lo vendiste a $30.00?`, using `por unidad` or `por paquete` for those sale units
- [x] 5.3 For a kilogram catalog product, take `900gr tomate a 30` as `30.00` per kilogram without requiring `por kilo`
- [x] 5.4 On the reason turn, open the add-item write transaction, `SELECT ... FOR UPDATE` the tenant product, and decide from that locked `current_price` before any session insert or idempotency reservation. Case A commits the override. Case B rolls back with no item, session, or idempotency row, then updates pending and asks again. Case C commits a normal catalog line and drops the reason. Do not update `Product.current_price` or hold the transaction for the next message
- [x] 5.5 Do not update `Product.current_price`, and do not ask a free-concept line for an override reason

## 6. sale.add_item extension

- [x] 6.1 Add optional catalog `price_override` `{unit_price, reason}` to `sale.add_item@1` version `1`, and do not register `sale.override_price@1` or `sale.add_override_item@1`
- [x] 6.2 Build that object in the conversational workflow only from the grounded amount and the normalized merchant reason
- [x] 6.3 Direct catalog calls without `price_override` stay on the message workflow. Direct calls with `price_override` lock the product in the write transaction, require an open session and `sale.create`, and refuse a difference without a valid reason

## 7. Policy

- [x] 7.1 Clarify the first difference under `CAT-001` reason `catalog_price_override_reason_required`, not `SALE-005`, and do not reserve idempotency
- [x] 7.2 Allow the accepted completion under `SALE-001` and `CAT-001` with reason `catalog_price_override`

## 8. Audit and outbox

- [x] 8.1 Extend `sale.add_item@1` `after_payload` with `catalog_unit_price_snapshot` and `price_override_reason`, keeping `source_type`, `product_id`, `product_name`, `unit_price`, and `line_total`
- [x] 8.2 Extend `sale.item.added` with `catalog_unit_price_snapshot`, `unit_price`, and `price_override_reason`, and do not emit `sale.price.overridden`
- [x] 8.3 Hash a writing completion as `catalog-price-override|v1|{conversation_id}|{product_id}|{quantity}|{unit}|{snapshot_amount}|{charged_amount}|{normalized_reason}` on `lumo.message.add_sale_item`. Same key and hash replays one line

## 9. Generative UI

- [x] 9.1 Keep `sale_item_added@1`, `sale_summary@1`, and `sale_confirmed@1` at version `1`. Include `catalog_unit_price` only on override lines
- [x] 9.2 Flutter shows `Precio ajustado · antes $20.00/kg` only when that field is present, and does not show the reason or recompute money

## 10. Regression

- [x] 10.1 Cover acceptance A–AF: normal catalog, equal price, lower and higher questions, one completing line, accents, blank, overlong, cancel, replacement, price-change restart, equal recheck, kilogram, unit, package, charged line total, unchanged product price, unchanged free concept, mixed totalize, cash/card/transfer, operational day and close, post-close refusal, audit, outbox, replay, reason without pending, model-only reason, model-only price, and cross-tenant product rejection
- [x] 10.2 Assert `sale.totalize@1`, payment, OperationalDay, CashCount, and Daily Close still use persisted `line_total` and do not gain an override branch
- [x] 10.3 Test the locked completion: a price change before the reason writes no item and no idempotency row and does not store the old reason; a price that becomes the override amount stores one normal catalog line with snapshot equal to `unit_price` and a null reason; a committed override snapshot equals the locked product price; a normal catalog line derives snapshot, `unit_price`, and `line_total` from one in-transaction `Product.current_price`

## 11. Migration and RLS acceptance

- [x] 11.1 Test upgrade backfill, the new check, and downgrade: catalog-only succeeds; normal catalog plus free concept with no override succeeds and free-concept rows remain; one catalog override refuses, deletes nothing, and stays on `0009`
- [x] 11.2 Test that business B cannot read business A's override row and that `fk_sale_items_product_business` still rejects a cross-tenant product

## 12. ADR

- [x] 12.1 Follow `docs/adr/ADR-021-catalog-price-override.md` during implementation and do not edit ADR-015 through ADR-020
