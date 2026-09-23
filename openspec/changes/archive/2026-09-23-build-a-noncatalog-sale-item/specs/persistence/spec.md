## ADDED Requirements

### Requirement: Noncatalog sale item migration
Alembic revision id MUST be `0008_noncatalog_sale_item` and `down_revision` MUST be `0007_daily_close_confirmation`. It MUST add `sales.sale_items.source_type` `VARCHAR(32) NOT NULL`, backfill every existing row to `catalog`, and drop `NOT NULL` on `product_id` while keeping the foreign key from `product_id` to `catalog.products(id)`. It MUST add `ck_sale_items_source` so `catalog` rows have `product_id` NOT NULL and `free_concept` rows have `product_id` NULL and a non-blank `product_name_snapshot`. It MUST add `ck_sale_items_money_positive` so `unit_price > 0` and `line_total > 0`. It MUST add `uq_products_id_business` on `catalog.products (id, business_id)` and `fk_sale_items_product_business` from `sales.sale_items (product_id, business_id)` to `catalog.products (id, business_id)`. It MUST NOT delete sale rows. It MUST NOT grant `BYPASSRLS`. Because `lumo_admin` is `NOBYPASSRLS`, the upgrade MUST disable row level security on `catalog.products` and `sales.sale_items` only while it backfills and validates constraints, then `ENABLE` and `FORCE` row level security again before it returns. `tenant_isolation` MUST remain. Head revision after a successful upgrade MUST be `0008_noncatalog_sale_item`.

#### Scenario: Upgrade preserves catalog lines
- **WHEN** Alembic upgrade runs from `0007_daily_close_confirmation` on a database that already has catalog `SaleItem` rows
- **THEN** those rows MUST have `source_type=catalog`, their `product_id` values MUST be unchanged, and `FORCE` row level security MUST still be enabled on `sales.sale_items`

#### Scenario: Catalog line cannot point at another business
- **WHEN** a `SaleItem` is inserted with `source_type=catalog` and a `product_id` that belongs to a different `business_id`
- **THEN** `fk_sale_items_product_business` MUST reject the row

#### Scenario: Free concept allows a null product
- **WHEN** a `SaleItem` is inserted with `source_type=free_concept`, `product_id` NULL, a non-blank `product_name_snapshot`, and positive money
- **THEN** the insert MUST succeed under that row's `business_id`

#### Scenario: Downgrade refuses free-concept rows
- **WHEN** any `sales.sale_items` row has `source_type=free_concept` or `product_id` NULL and downgrade from `0008_noncatalog_sale_item` is attempted
- **THEN** the downgrade MUST abort, those rows MUST remain, and the revision MUST stay `0008_noncatalog_sale_item`

#### Scenario: Downgrade of a catalog-only database
- **WHEN** every `SaleItem` has `source_type=catalog` and a non-null `product_id`, and the database is downgraded to `0007_daily_close_confirmation`
- **THEN** `source_type` MUST NOT exist, `product_id` MUST be `NOT NULL`, and the catalog sale rows MUST remain

### Requirement: Tenant cannot read another business free-concept line
`sales.sale_items` MUST keep `ENABLE` and `FORCE` row level security and policy `tenant_isolation` on `business_id`. A session whose `app.current_business_id` is business B MUST NOT read business A's free-concept rows.

#### Scenario: Cross-tenant read is empty
- **WHEN** business A has a free-concept `SaleItem` and the session GUC is business B
- **THEN** a select of `sales.sale_items` MUST NOT return that row
