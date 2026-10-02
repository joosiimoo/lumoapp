## MODIFIED Requirements

### Requirement: First mismatch writes nothing
A unique active catalog match whose grounded price differs from `Product.current_price` and whose utterance has no valid inline reason MUST ask for a reason and MUST NOT persist a `SaleItem`, create a `SaleSession`, reserve idempotency, write audit or outbox, create a free concept, or update the product. The pending kind MUST be `catalog_price_override`. For Tomate at `20.00` MXN/kg and a grounded `30.00` with no inline reason, the response MUST be `Tomate está registrado a $20.00 por kg. ¿Por qué lo vendiste a $30.00?` The unit phrase MUST be `por unidad` or `por paquete` when that is the product `sale_unit`. A valid inline reason on that same utterance MUST follow `Same-utterance catalog reason` instead of this ask.

#### Scenario: Higher price asks and writes nothing
- **WHEN** a Carrota actor posts `900gr tomate a 30` and Tomate `current_price` is `20.00`
- **THEN** the response MUST be that Tomate question and no sale row, idempotency row, audit row, or outbox row MUST be written

#### Scenario: Lower price asks the same way
- **WHEN** a unique catalog product is `12.00` per unit and the actor posts `2 galletas A a 10`
- **THEN** the response MUST ask why it was sold at `$10.00` and no `SaleItem` MUST be written

## ADDED Requirements

### Requirement: Same-utterance catalog reason
A trailing `por {motivo}` after a grounded `a {amount}` is an inline override reason when `{motivo}` is non-empty after `normalize_override_reason` and is not a kilogram basis phrase (`el kilo`, `por kilo`, `por kg`, `por kilogramo`, `el kilogramo`). Optional `cada uno` or `cada una` MAY sit between the amount and that clause. The reason MUST be that normalized `{motivo}`: trimmed, whitespace-collapsed, accents and casing preserved, at most 200 characters, and not truncated. `porque`, a bare sentence after the price, and a second product utterance MUST NOT be parsed as this clause.

When the cleaned product span uniquely matches an active catalog product, the grounded price differs from the locked `Product.current_price`, and the inline reason is valid, that same message MUST complete one catalog override with the existing reason-turn write. It MUST set `source_type=catalog`, the product id, `catalog_unit_price_snapshot` from the locked price, `unit_price` to the grounded amount, `price_override_reason` to the normalized motivo, and `line_total` from `Money.times`. It MUST NOT create a free-concept row, MUST NOT leave `catalog_price_override` pending, MUST NOT update `Product.current_price`, and MUST NOT ask the reason question. The writing turn MUST reserve the existing catalog-override idempotency hash that includes the normalized reason. A kilogram basis inside the utterance MUST NOT become the stored reason.

If the locked price equals the grounded amount, the line MUST be a normal catalog line and the inline reason MUST NOT be stored. If the locked price changed and still differs, the existing restart question MUST run and the inline reason MUST NOT be stored. An inline reason longer than 200 characters MUST NOT persist a `SaleItem` or a free concept, MUST NOT be truncated, and MUST respond `Ese motivo es demasiado largo.` It MUST leave `kind=catalog_price_override` pending with the resolved product, quantity, unit, grounded override price, and observed catalog price, and MUST NOT store that over-long text as the reason. A later valid reason message on that conversation MUST complete the override without requiring the merchant to repeat the sale utterance. A trailing `por` with an empty motivo MUST be treated as no inline reason and MUST ask.

#### Scenario: Galleta A promotion completes as a catalog override
- **WHEN** a Carrota actor posts `1 galleta A a 10 por promoción` and Galleta A `current_price` is `12.00` per unit
- **THEN** exactly one catalog `SaleItem` MUST exist for Galleta A with quantity `1`, `catalog_unit_price_snapshot` `12.00`, `unit_price` `10.00`, `price_override_reason` `promoción`, and `line_total` `10.00`, and no free-concept row and no pending override MUST remain

#### Scenario: The whole phrase is not a free concept
- **WHEN** that Galleta A utterance is accepted
- **THEN** no `SaleItem.product_name_snapshot` MUST equal `1 galleta A a 10 por promoción` or `galleta A a 10 por promoción`

#### Scenario: Missing inline reason still asks
- **WHEN** a Carrota actor posts `2 galletas A a 10` and Galleta A `current_price` is `12.00`
- **THEN** the response MUST ask why it was sold at `$10.00` and no `SaleItem` MUST be written

#### Scenario: Kilogram basis is not the reason
- **WHEN** the utterance ends in `por kilo` as the price basis
- **THEN** the stored `price_override_reason` MUST NOT be `kilo` or `por kilo`

#### Scenario: Overlong inline reason writes nothing and stays pending
- **WHEN** the inline motivo of `1 galleta A a 10 por {motivo}` normalizes to more than 200 characters and Galleta A uniquely matches at `12.00`
- **THEN** no `SaleItem` and no free-concept row MUST be written, the stored reason MUST NOT be a prefix of that text, the response MUST be `Ese motivo es demasiado largo.`, and `kind=catalog_price_override` MUST remain pending for Galleta A with quantity `1`, unit price `10.00`, and observed catalog price `12.00` without a reason

#### Scenario: Valid reason completes after an overlong inline reason
- **WHEN** that pending override exists and the actor posts `promoción`
- **THEN** exactly one catalog `SaleItem` MUST exist for Galleta A with `unit_price` `10.00`, `price_override_reason` `promoción`, and `line_total` `10.00`
