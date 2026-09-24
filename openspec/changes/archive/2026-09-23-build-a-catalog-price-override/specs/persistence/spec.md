## MODIFIED Requirements

### Requirement: Noncatalog sale item migration
Alembic revision id MUST be `0008_noncatalog_sale_item` and `down_revision` MUST be `0007_daily_close_confirmation`. It MUST add `sales.sale_items.source_type` `VARCHAR(32) NOT NULL`, backfill every existing row to `catalog`, and drop `NOT NULL` on `product_id` while keeping the foreign key from `product_id` to `catalog.products(id)`. It MUST add `ck_sale_items_source` so `catalog` rows have `product_id` NOT NULL and `free_concept` rows have `product_id` NULL and a non-blank `product_name_snapshot`. It MUST add `ck_sale_items_money_positive` so `unit_price > 0` and `line_total > 0`. It MUST add `uq_products_id_business` on `catalog.products (id, business_id)` and `fk_sale_items_product_business` from `sales.sale_items (product_id, business_id)` to `catalog.products (id, business_id)`. It MUST NOT delete sale rows. It MUST NOT grant `BYPASSRLS`. Because `lumo_admin` is `NOBYPASSRLS`, the upgrade MUST disable row level security on `catalog.products` and `sales.sale_items` only while it backfills and validates constraints, then `ENABLE` and `FORCE` row level security again before it returns. `tenant_isolation` MUST remain. After `0009_catalog_price_override` is applied, head revision MUST be `0009_catalog_price_override`, not `0008_noncatalog_sale_item`.

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

## ADDED Requirements

### Requirement: Catalog price override migration
Alembic revision id MUST be `0009_catalog_price_override` and `down_revision` MUST be `0008_noncatalog_sale_item`. It MUST add `sales.sale_items.catalog_unit_price_snapshot` `NUMERIC(12, 2) NULL` and `sales.sale_items.price_override_reason` `VARCHAR(200) NULL`. It MUST backfill `source_type=catalog` rows with `catalog_unit_price_snapshot = unit_price` and `price_override_reason` NULL, and `source_type=free_concept` rows with both columns NULL. It MUST add `ck_sale_items_catalog_price` so a catalog row has a positive snapshot and either equal `unit_price` with a null reason, or a different `unit_price` with a non-blank trimmed reason, and a free-concept row has both columns NULL. It MUST keep `ck_sale_items_source`, `ck_sale_items_money_positive`, `fk_sale_items_product_business`, and `tenant_isolation`. Downgrade MUST refuse only catalog overrides, using `source_type = 'catalog' AND (price_override_reason IS NOT NULL OR catalog_unit_price_snapshot IS DISTINCT FROM unit_price)`. It MUST NOT treat a `free_concept` null snapshot as an override. It MUST NOT delete sale rows and MUST NOT grant `BYPASSRLS`. Because `lumo_admin` is `NOBYPASSRLS`, the upgrade MUST disable row level security on `sales.sale_items` only while it backfills and validates the new check, then `ENABLE` and `FORCE` row level security again before it returns. Head revision after a successful upgrade MUST be `0009_catalog_price_override`.

#### Scenario: Existing catalog rows gain an equal snapshot
- **WHEN** upgrade runs on a database whose catalog `SaleItem` rows have `unit_price` `20.00`
- **THEN** those rows MUST have `catalog_unit_price_snapshot` `20.00` and `price_override_reason` NULL, and `FORCE` row level security MUST still be enabled

#### Scenario: Existing free-concept rows stay without a snapshot
- **WHEN** upgrade runs on a database that already has a `free_concept` `SaleItem`
- **THEN** that row MUST have `catalog_unit_price_snapshot` NULL and `price_override_reason` NULL

#### Scenario: Override without a reason is rejected
- **WHEN** a catalog insert sets `unit_price` different from `catalog_unit_price_snapshot` and `price_override_reason` NULL
- **THEN** `ck_sale_items_catalog_price` MUST reject the row

#### Scenario: Catalog-only database downgrades
- **WHEN** every `SaleItem` is `source_type=catalog`, every snapshot equals `unit_price`, every reason is NULL, and downgrade to `0008_noncatalog_sale_item` runs
- **THEN** the downgrade MUST succeed and both new columns MUST NOT exist

#### Scenario: Free-concept rows do not block downgrade
- **WHEN** the database has normal catalog rows and `free_concept` rows, no catalog row has a reason or a snapshot distinct from `unit_price`, and downgrade to `0008_noncatalog_sale_item` runs
- **THEN** the downgrade MUST succeed and those sale rows MUST remain

#### Scenario: A free-concept null snapshot is not an override
- **WHEN** a `free_concept` row has `catalog_unit_price_snapshot` NULL and `unit_price` `18.00`, and no catalog override exists
- **THEN** downgrade MUST NOT treat that row as a catalog override

#### Scenario: Downgrade refuses a catalog override
- **WHEN** at least one `source_type=catalog` row has a non-null `price_override_reason` or a snapshot distinct from `unit_price`, and downgrade from `0009_catalog_price_override` is attempted
- **THEN** the downgrade MUST abort, no sale row MUST be deleted, and the revision MUST stay `0009_catalog_price_override`

#### Scenario: Successful downgrade keeps free-concept rows
- **WHEN** downgrade from `0009_catalog_price_override` to `0008_noncatalog_sale_item` succeeds on a database that contains a `free_concept` row
- **THEN** that row MUST still exist with `source_type=free_concept`, `product_id` NULL, its `product_name_snapshot`, its `unit_price`, and its `line_total`

### Requirement: Tenant cannot read another business override line
`sales.sale_items` MUST keep `ENABLE` and `FORCE` row level security and policy `tenant_isolation` on `business_id`. A session whose `app.current_business_id` is business B MUST NOT read business A's override rows. This migration MUST NOT add a policy and MUST NOT change `tenant_isolation`.

#### Scenario: Cross-tenant override read is empty
- **WHEN** business A has a catalog override `SaleItem` and the session GUC is business B
- **THEN** a select of `sales.sale_items` MUST NOT return that row
