## Why

A merchant sometimes sells a catalog product at a different unit price on purpose. PRD §7.5 and SRS RF-A-039 require that difference to keep a non-empty reason and to stay visible. Today a grounded price that differs from `Product.current_price` clarifies under `CAT-001` / `catalog_price_mismatch` and writes nothing (ADR-020). The merchant cannot complete "900gr tomate a 30" when Tomate is registered at $20.00/kg.

## What Changes

- A catalog `SaleItem` may charge a unit price other than the catalog price that existed when the line was committed. The difference is per line. It does not update `Product.current_price`, and it is not a promotion or a discount rule.
- Persist `catalog_unit_price_snapshot` and `price_override_reason` on `sales.sale_items`. Override status is derived from `source_type=catalog` and `unit_price` differing from that snapshot. No `price_source` or `pricing_mode` column.
- Alembic `0009_catalog_price_override` (`down_revision` `0008_noncatalog_sale_item`) backfills existing catalog rows with the snapshot equal to `unit_price` and a null reason, and free-concept rows with both null. Downgrade aborts only when a catalog override row exists. A free-concept row does not block it.
- The first mismatched utterance asks why and writes nothing. The merchant's next reason is the confirmation. A blank, model-only, or overlong reason does not complete the line.
- `sale.add_item@1` stays the only add-item tool. Catalog mode may carry an explicit `price_override` after that reason flow. The server re-reads `Product.current_price`, calculates money, and enforces the reason. If the catalog price changed before the reason, the line is not written and the question restarts. If the proposed price now equals the catalog price, the line is a normal catalog line and the reason is not stored.
- Cards stay version `1`. An override line may add `catalog_unit_price` so the merchant can see "Precio ajustado". The reason stays in the sale row, audit, and outbox, not on the compact card.
- Record ADR-021. Do not edit ADR-015 through ADR-020.

## Non-goals

- Updating `Product.current_price`, price history, scheduled prices, or saving the override as the new catalog price.
- Promotions, coupons, markdown rules, bulk price changes, percentage thresholds, risk scoring, manager PIN, or an authorization hierarchy.
- Customer-specific pricing, tax changes, inventory impact, or learning from overrides.
- Applying this flow to `free_concept`. Those prices are already explicit.
- Editing or deleting a persisted `SaleItem`, refunds, receipts, invoices, mixed payment, analytics, or export.
- Changing `sale.totalize@1`, payment semantics, OperationalDay, CashCount, or Daily Close. A closed day still refuses `sale.commit@1`.
- A new tool, audit action, audit table, or `sale.price.overridden` event.

## Capabilities

### New Capabilities

- `catalog-price-override`: Per-line catalog price exception: snapshot, charged price, required merchant reason, in-memory confirmation, and deterministic money. `Product.current_price` stays catalog truth.

### Modified Capabilities

- `persistence`: Migration `0009`, snapshot and reason columns, check constraints, backfill, and downgrade that refuses override rows.
- `sales-session-foundation`: `SaleItem` stores the catalog snapshot and optional reason; line total uses the charged unit price.
- `catalog-foundation`: A different grounded price starts an override-reason clarification. It does not mutate the product and it is not a free concept.
- `noncatalog-sale-item`: A catalog price difference stays on the catalog product. It does not become a free concept, and the old refusal copy is replaced by the override-reason question.
- `conversational-sale-runtime`: Pending `catalog_price_override`, reason and cancellation handling, and `sale.add_item@1` catalog override input.
- `conversational-sale-session`: The reason turn writes one line; a new complete sale replaces the pending override; totalize and commit stay source-agnostic.
- `ai-native-contracts`: `CAT-001` asks for a reason instead of refusing the price. No new tool. UI versions stay `1`.
- `sale-item-added-ui`: Version `1` may show a subtle adjusted-price caption from `catalog_unit_price`.
- `sale-summary-ui`: Summary rows use the same caption when that field is present.
- `sale-confirmed-ui`: Confirmed rows use the same caption when that field is present.

## Impact

- Backend: `SaleItem`, Alembic `0009`, pending clarification, scripted interpreter, `AddCatalogSaleItem`, `CAT-001`, audit `sale.add_item@1`, and `sale.item.added`.
- Mobile: existing `sale_item_added@1`, `sale_summary@1`, and `sale_confirmed@1` render the caption only when `catalog_unit_price` is present. No new component and no version bump.
- Data: existing catalog and free-concept rows remain valid. RLS policies are unchanged. Downgrade aborts if any override row exists.
- Docs: ADR-021 only. ADR-015 through ADR-020 stay as written.
