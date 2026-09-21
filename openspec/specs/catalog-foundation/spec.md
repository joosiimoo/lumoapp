## Purpose

Tenant-scoped catalog persistence, name normalization, sale units, pricing types, and product resolution for conversational add-item.

## Requirements

### Requirement: Catalog schema and Product entity
Persistence MUST create PostgreSQL schema `catalog` and a `products` table. Each `Product` MUST include `id` (UUIDv7), `business_id`, `name`, `normalized_name`, `sale_unit`, `pricing_type`, `current_price` (`numeric`), `status` (`active` or `inactive`), `created_at`, and `updated_at` (`timestamptz` UTC). Domain `Product` MUST NOT be a SQLAlchemy model. Tenant-scoped catalog tables MUST enable RLS and MUST be queried only with an explicit tenant argument.

#### Scenario: Product row shape
- **WHEN** Alembic migrations for this capability complete
- **THEN** `catalog.products` MUST exist with the required columns and MUST NOT store money as `float`/`double precision`

#### Scenario: Tenant required
- **WHEN** application code calls a catalog repository method without a tenant
- **THEN** the call MUST fail before executing SQL

### Requirement: Optional product aliases
The catalog MAY persist zero or more aliases per product in `catalog.product_aliases` with `business_id`, `product_id`, `alias`, and `normalized_alias`. Zanahoria MUST NOT require an alias. Resolution MUST consider `name` and any aliases after the same normalization.

#### Scenario: Seed has no alias
- **WHEN** the local/test seed loads Zanahoria
- **THEN** the product MUST resolve by normalized name without any alias row

### Requirement: Sale units and pricing types
`sale_unit` MUST be one of `unit`, `package`, or `kilogram`. `pricing_type` MUST be one of `per_unit`, `per_package`, or `per_kilogram`. `gram` MUST NOT be stored as a `sale_unit`. A product MUST pair `kilogram` with `per_kilogram`, `unit` with `per_unit`, and `package` with `per_package`.

#### Scenario: Invalid pairing rejected
- **WHEN** a product is written with `sale_unit=kilogram` and `pricing_type=per_unit`
- **THEN** persistence or domain validation MUST reject the write

### Requirement: Name normalization
`normalized_name` MUST be computed in backend domain logic by Unicode NFKD, stripping combining marks, lowercasing, and collapsing internal whitespace. Catalog resolution MUST compare the normalized query to `normalized_name` and `normalized_alias` for the session tenant only. Inactive products MUST NOT resolve for new sale items.

#### Scenario: Accent-insensitive unique match
- **WHEN** the query is `ZANAHORÍA` and an active product named `Zanahoria` exists in the same business
- **THEN** resolution MUST return that unique product

#### Scenario: Inactive product excluded
- **WHEN** the only name match is a product with `status=inactive`
- **THEN** resolution MUST return no product and MUST NOT be used to create a `SaleItem`

### Requirement: Unique versus ambiguous resolution
If exactly one active tenant product matches, resolution MUST return that product. If more than one active product matches, resolution MUST return an ambiguous result and MUST NOT choose silently. If none match, resolution MUST return not found. Unknown or non-catalog products MUST NOT be invented.

#### Scenario: Unique Zanahoria
- **WHEN** `catalog.resolve_product@1` is invoked with query `zanahoria` against the Carrota seed
- **THEN** the result MUST be a unique match for product name `Zanahoria` with `sale_unit=kilogram` and `pricing_type=per_kilogram`

#### Scenario: Ambiguous catalog names
- **WHEN** two active products in the same business both match the normalized query
- **THEN** the result MUST be `ambiguous` and no sale mutation MUST run from that interpretation

### Requirement: Current price is catalog truth
`current_price` on the active `Product` MUST be the price source for add-item. The LLM MUST NOT supply a trusted price. Price versioning tables, overrides, and discounts are out of scope.

#### Scenario: Seed price
- **WHEN** the Carrota seed product Zanahoria is loaded
- **THEN** `current_price` MUST be `25.00` MXN stored as `numeric`

### Requirement: Carrota catalog seed
Local API startup (`APP_ENV=local`) and tests MUST seed business `Carrota` and an active product `Zanahoria` with `sale_unit=kilogram`, `pricing_type=per_kilogram`, and `current_price=25.00` MXN. The helper MUST be deterministic and idempotent. Staging and production MUST NOT insert this seed automatically. The seed MUST be tenant-scoped to that business. FORCE RLS remains enabled: a SQL client MUST set `app.current_business_id` to the Carrota business id to see catalog/sales rows; `lumo_admin` MUST NOT bypass RLS.

#### Scenario: Seed isolation
- **WHEN** an actor for a different business resolves `zanahoria`
- **THEN** the Carrota product MUST NOT be returned

#### Scenario: Unscoped SQL looks empty
- **WHEN** `lumo_app` or `lumo_admin` selects `catalog.products` without `app.current_business_id`
- **THEN** the result MUST be zero rows even if the seed committed

#### Scenario: Local compose host port
- **WHEN** local Compose publishes PostgreSQL
- **THEN** the host mapping MUST be `5432:5432` and local URLs MUST use `localhost:5432`
