## MODIFIED Requirements

### Requirement: Optional product aliases
The catalog MAY persist zero or more aliases per product in `catalog.product_aliases` with `business_id`, `product_id`, `alias`, and `normalized_alias`. Zanahoria and Tomate MUST NOT require an alias. Galleta A MUST persist alias `galletas a` so the utterance `2 galletas A` resolves uniquely after normalization. Resolution MUST consider `name` and any aliases after the same normalization.

#### Scenario: Seed has no alias for Zanahoria
- **WHEN** the local/test seed loads Zanahoria
- **THEN** the product MUST resolve by normalized name without any alias row

#### Scenario: Galleta A matches plural alias
- **WHEN** the query is `galletas a` against the Carrota seed
- **THEN** resolution MUST return the unique product named `Galleta A`

### Requirement: Carrota catalog seed
Local API startup (`APP_ENV=local`) and tests MUST seed business `Carrota` and the following active products, all tenant-scoped to that business. The helper MUST be deterministic and idempotent. Staging and production MUST NOT insert this seed automatically. FORCE RLS remains enabled: a SQL client MUST set `app.current_business_id` to the Carrota business id to see catalog/sales rows; `lumo_admin` MUST NOT bypass RLS. Papa MUST NOT be seeded.

| Name | sale_unit | pricing_type | current_price | aliases |
|---|---|---|---|---|
| Zanahoria | kilogram | per_kilogram | 25.00 MXN | none |
| Tomate | kilogram | per_kilogram | 20.00 MXN | none |
| Galleta A | unit | per_unit | 12.00 MXN | galletas a |

#### Scenario: Seed isolation
- **WHEN** an actor for a different business resolves `zanahoria`
- **THEN** the Carrota product MUST NOT be returned

#### Scenario: Unscoped SQL looks empty
- **WHEN** `lumo_app` or `lumo_admin` selects `catalog.products` without `app.current_business_id`
- **THEN** the result MUST be zero rows even if the seed committed

#### Scenario: Local compose host port
- **WHEN** local Compose publishes PostgreSQL
- **THEN** the host mapping MUST be `5432:5432` and local URLs MUST use `localhost:5432`

#### Scenario: Representative multi-item catalog
- **WHEN** the Carrota seed has been applied
- **THEN** Zanahoria, Tomate, and Galleta A MUST exist with the prices above, and resolving `papa` MUST return none
