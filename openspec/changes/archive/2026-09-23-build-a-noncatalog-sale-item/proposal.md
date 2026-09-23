## Why

Carrota sells products that are not in Lumo's catalog. PRD §7.4 and SRS RF-A-032 / RF-A-033 allow a detailed sale line made of a concept, quantity, unit, and price, and they require the catalog to be optional. Today `sales.sale_items.product_id` is `NOT NULL`, and a `match=none` resolution stops the sale with "No encontré ese producto en el catálogo." The merchant cannot complete "2 bolsas de hielo a 18 cada una".

## What Changes

- Separate catalog resolution from sale-line persistence. A `SaleItem` is either catalog-backed or a free concept, never both and never ambiguous. A free concept is immutable sale data. Selling it does not create a `Product`, alias, SKU, or inventory row (PRD §7.4; ADR-006 / ADR-007 still hold).
- **BREAKING** schema: Alembic `0008_noncatalog_sale_item` makes `product_id` nullable, adds `source_type` (`catalog` | `free_concept`), and backfills existing rows as `catalog`. The durable display name stays the existing `product_name_snapshot` column. No second name column.
- `catalog.resolve_product@1` stays a read and does not create free concepts. A unique match with no uttered price, or with a `Decimal` amount equal to `Product.current_price`, uses that catalog price. A different uttered price clarifies and writes nothing: no line, no new session, no free concept, and no price override. An ambiguous match stays a clarification. `match=none` may add a free-concept line only when quantity, a supported unit, and an explicit user price are present. For gram or kilogram that price must also say it is per kilogram.
- Extend `sale.add_item@1` with a source mode. Do not register `sale.add_free_item@1`.
- Missing price, quantity, or an unsupported unit asks in Spanish and writes nothing. The partial draft lives in the existing in-memory pending clarification store, keyed by tenant, actor, and `conversation_id`. It is not a `SaleItem` and not schema `memory`.
- Trusted money stays server-side `Decimal` via `Money.times` (`ROUND_HALF_UP` to `0.01`). Catalog lines still store `Product.current_price`, never the uttered amount. A free-concept price is persisted only when a deterministic extractor grounds it in the user text or in a pending clarification that came from that text. An `AgentDecision` amount that the text does not contain is not stored. Flutter and the LLM do not calculate money. For `unit` and `package`, one explicit amount is the per-each price. That shortcut does not apply to gram or kilogram.
- `sale.totalize@1` and `sale.commit@1` aggregate persisted `line_total` values and do not branch on source. Payment, OperationalDay, and Daily Close stay unchanged. `sale_item_added@1`, `sale_summary@1`, and `sale_confirmed@1` render the server display name. No new card, no "Concepto libre" badge, and no save-to-catalog action.
- Audit and the existing `sale.item.added` event record `source_type` and a nullable `product_id`. Message idempotency stays `lumo.message.add_sale_item`. A clarification continuation writes one line, not one line per turn.
- Record ADR-020. Do not edit ADR-015 through ADR-019.

## Non-goals

- Automatic or suggested catalog creation, alias learning, fuzzy alias persistence, SKU, barcode, or photo recognition.
- Inventory, stock deduction, replenishment, supplier mapping, price history, remembered price, default price, or an AI price suggestion.
- Promotions, discounts, and price override of a catalog item.
- Edit or delete of a sale line, mixed payments, receipts, invoices, analytics, and export.
- Amount-only sales with no line ("385 tarjeta", "250"), WorkItems, and a workflow engine.
- New units beyond `unit`, `package`, `kilogram`, and input `gram`. New measurement families.
- A new tool, event, card, audit table, or idempotency operation type.

## Capabilities

### New Capabilities

- `noncatalog-sale-item`: Free-concept sale line: source invariant, explicit price, supported units, in-memory clarification, deterministic money, and no catalog side effect.

### Modified Capabilities

- `persistence`: Migration `0008`, nullable `product_id`, `source_type`, tenant FK, and refusing downgrade when free-concept rows exist.
- `sales-session-foundation`: `SaleItem` may be catalog or free concept; line total uses catalog price or the explicit unit price.
- `catalog-foundation`: `match=none` still invents no product. A mismatched catalog price is refused under `CAT-001` and is not an override.
- `conversational-sale-runtime`: Interpreter fields, no-match routing, pending price clarification, and extended `sale.add_item@1`.
- `conversational-sale-session`: Mixed lines in one session; clarification writes one line; post-close commit still refuses.
- `ai-native-contracts`: `sale.add_item@1` input accepts a source mode. `SALE-005` allows a complete free concept, and for gram or kilogram only with an explicit per-kilogram basis. Catalog price mismatch stays on `CAT-001`.
- `sale-item-added-ui`: Existing card shows the free-concept display name and server totals, with no badge.
- `sale-summary-ui`: Summary rows use the same display name for both sources.
- `sale-confirmed-ui`: Confirmed rows use the same display name for both sources.

## Impact

- Backend: `SaleItem`, Alembic `0008`, `AddCatalogSaleItem` (still the add-item workflow), scripted interpreter, pending store, policy `SALE-005`, audit and `sale.item.added` payloads.
- Mobile: no new component. Existing product rows render `product_name`.
- Data: existing catalog lines remain valid. Downgrade aborts if any free-concept row exists.
- Tests: flows A–F and acceptance A–R, without weakening RLS or the closed-day commit guard.
