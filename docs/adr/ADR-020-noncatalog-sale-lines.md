# ADR-020: Noncatalog sale lines are durable sale data, not catalog entities

- Status: Accepted
- Date: 2026-09-23

## Decision

A merchant can complete a sale when no catalog product matches. Catalog resolution and sale-line persistence are separate.

A `SaleItem` is exactly one of:

- `source_type=catalog`: `product_id` is not null and references that tenant's product. `product_name_snapshot` is the product name captured at add time. `unit_price` is `Product.current_price`.
- `source_type=free_concept`: `product_id` is null. `product_name_snapshot` is the merchant's concept span after structural cleanup only. Accents and casing stay. `normalize_product_name` is a transient catalog lookup, not the stored name. `unit_price` is the explicit user amount.

It is never both, and it is never a guessed product. Selling a free concept does not insert a `Product`, alias, SKU, or inventory row.

`catalog.resolve_product@1` stays a read. A unique match with no uttered price, or with a `Decimal` amount equal to `Product.current_price`, stays on the catalog path and stores `Product.current_price`. A different uttered price is a guard, not an override: clarify, write no `SaleItem`, create no session, reserve no idempotency key, and do not create a free concept or a `Product`. An ambiguous match stays a clarification. Only `match=none`, with no inactive name collision, may become a free concept.

The price is not inferred from the catalog, from history, or from the model. `AgentDecision.unit_price` is a candidate. The workflow persists a free-concept amount only when a deterministic extractor finds it in the current user message, or when a pending clarification already stored that grounded amount. For `unit` and `package`, one explicit amount is the per-each price. For gram and kilogram, the utterance or a later reply must also say the amount is per kilogram. "500g de hielo a 40" asks and writes nothing. "500g de hielo a 40 por kilo" stores 0.500 kg at 40.00, line total 20.00. Missing price, quantity, unit, or mass basis is held in the existing in-memory pending clarification store. Incomplete lines are not persisted. There is no schema `memory` and no draft `SaleItem`. Bare "sí" does not confirm a mass basis. The completing reply is an explicit phrase such as "por kilo".

Trusted `line_total` is `quantity_normalized * unit_price` in domain code through `Money.times` (`ROUND_HALF_UP` to `0.01`). Flutter and the LLM do not calculate it.

`sale.add_item@1` grows a `source_type` mode. `sale.add_free_item@1` is not registered. `sale.totalize@1`, `sale.commit@1`, payment, OperationalDay, and Daily Close sum persisted line totals and do not branch on source. A closed day still refuses commit.

Audit and the existing `sale.item.added` event record `source_type` and a nullable `product_id`. They do not record a guessed product. Cards stay `sale_item_added@1`, `sale_summary@1`, and `sale_confirmed@1`, using `product_name`, with no free-concept badge and no save-to-catalog action.

Alembic `0008_noncatalog_sale_item` makes `product_id` nullable, adds `source_type`, backfills existing rows as `catalog`, and adds a composite `(product_id, business_id)` foreign key so a catalog line cannot point at another tenant's product. Downgrade aborts when any free-concept row exists. It does not delete sale data.

Free-concept lines are not editable in this change.

## Consequences

Catalog-backed sales keep `Product.current_price`. A merchant who names a different catalog price is told the registered price and is not silently charged the catalog price or the named price. Merchants can sell an unknown concept once quantity, a supported unit, and a grounded explicit price are known, including a per-kilogram basis when the unit is gram or kilogram. ADR-015 through ADR-019 are unchanged. Price override, catalog learning, inventory, and amount-only sales remain future work.
