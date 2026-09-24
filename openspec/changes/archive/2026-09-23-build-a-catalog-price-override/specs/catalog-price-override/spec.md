## Purpose

A catalog sale line may charge a unit price other than `Product.current_price` when the merchant states that price and a reason. The catalog price at commit, the charged price, and the reason stay on the `SaleItem`. The product row does not change.

## ADDED Requirements

### Requirement: Catalog line keeps a price snapshot
Every catalog `SaleItem` MUST persist `catalog_unit_price_snapshot` from the single authoritative `Product.current_price` for that mutation, in the line currency, at scale 2. For an override completion that price is the locked product row. For a normal catalog line it is the one in-transaction product read that also supplies `unit_price` and `line_total`. A normal catalog line MUST set `unit_price` equal to that snapshot and `price_override_reason` NULL. An override line MUST set `unit_price` to the merchant amount and `price_override_reason` to the normalized merchant text. A `free_concept` line MUST persist both new fields as NULL. The domain MUST NOT add `price_source` or `pricing_mode`. An override MUST be recognizable from `source_type=catalog` together with `unit_price` differing from `catalog_unit_price_snapshot`.

#### Scenario: Normal catalog line snapshots the same price
- **WHEN** a catalog line is committed with no uttered price, or with a grounded price equal to `Product.current_price`
- **THEN** `catalog_unit_price_snapshot` MUST equal `unit_price` and `price_override_reason` MUST be NULL

#### Scenario: Override line keeps both prices
- **WHEN** Tomate at `20.00` MXN/kg is sold at a grounded `30.00` after a merchant reason
- **THEN** the `SaleItem` MUST have Tomate's `product_id`, `catalog_unit_price_snapshot` `20.00`, `unit_price` `30.00`, and a non-null `price_override_reason`

#### Scenario: Free concept does not snapshot a catalog price
- **WHEN** a `free_concept` line is committed
- **THEN** `catalog_unit_price_snapshot` and `price_override_reason` MUST be NULL

### Requirement: Merchant reason is required for a difference
A catalog override MUST keep a reason taken from merchant text. The system MUST NOT generate it, infer it, or substitute a stock phrase such as "manual override" unless the merchant typed that phrase. Normalization MUST trim and collapse whitespace, MUST preserve accents and casing, and MUST NOT apply `normalize_product_name`. The normalized reason MUST be non-empty and at most 200 characters. A blank result MUST NOT complete the line. A longer result MUST NOT be truncated and MUST NOT complete the line. The pending override MUST remain in both rejection cases.

#### Scenario: Accents and casing survive
- **WHEN** the merchant answers `Precio especial para el cliente`
- **THEN** `price_override_reason` MUST equal `Precio especial para el cliente`

#### Scenario: Blank reason does not complete
- **WHEN** a catalog override is pending and the merchant sends only whitespace
- **THEN** no `SaleItem` MUST be written and the response MUST be `Necesito un motivo para registrar ese precio.`

#### Scenario: Overlong reason is rejected whole
- **WHEN** the normalized reason is longer than 200 characters
- **THEN** no `SaleItem` MUST be written, the stored reason MUST NOT be a prefix of that text, and the response MUST be `Ese motivo es demasiado largo.`

### Requirement: First mismatch writes nothing
A unique active catalog match whose grounded price differs from `Product.current_price` MUST ask for a reason and MUST NOT persist a `SaleItem`, create a `SaleSession`, reserve idempotency, write audit or outbox, create a free concept, or update the product. The pending kind MUST be `catalog_price_override`. For Tomate at `20.00` MXN/kg and a grounded `30.00`, the response MUST be `Tomate está registrado a $20.00 por kg. ¿Por qué lo vendiste a $30.00?` The unit phrase MUST be `por unidad` or `por paquete` when that is the product `sale_unit`.

#### Scenario: Higher price asks and writes nothing
- **WHEN** a Carrota actor posts `900gr tomate a 30` and Tomate `current_price` is `20.00`
- **THEN** the response MUST be that Tomate question and no sale row, idempotency row, audit row, or outbox row MUST be written

#### Scenario: Lower price asks the same way
- **WHEN** a unique catalog product is `12.00` per unit and the actor posts `2 galletas A a 10`
- **THEN** the response MUST ask why it was sold at `$10.00` and no `SaleItem` MUST be written

### Requirement: Reason turn locks the product and commits one line
The reason turn MUST re-resolve the pending product query, then open the existing add-item write transaction. Inside that transaction, before a `SaleSession` insert, a `SaleItem` insert, or an idempotency reservation, it MUST lock the tenant product with `SELECT ... FOR UPDATE` or the ORM equivalent, require the pending `product_id` and an active product, and read `Product.current_price` from that locked row. That locked price is the catalog snapshot for the commit. The transaction MUST NOT update `Product.current_price`, MUST NOT stay open while waiting for another message, and MUST NOT use a distributed lock or a new workflow.

When the locked price equals the observed catalog price and differs from the grounded override, the same transaction MUST create or reuse the open `SaleSession` and insert exactly one catalog `SaleItem`. `catalog_unit_price_snapshot` MUST be the locked price. `unit_price` MUST be the override. The merchant reason MUST be stored. `line_total` MUST be `quantity_normalized * unit_price` via `Money.times`, quantized once to `0.01` with `ROUND_HALF_UP`. The success text MUST be `Agregué 0.900 kg de Tomate · $27.00` for 0.900 kg at `30.00`. Merchant-facing copy MUST NOT contain `override`, `pricing_mode`, `CAT-001`, or `exception policy`.

#### Scenario: Override snapshot comes from the locked row
- **WHEN** the Tomate override question observed `20.00`, the product row is locked at `20.00`, and the actor posts a valid reason for `30.00`
- **THEN** the committed snapshot MUST be the locked `20.00` and `Product.current_price` MUST remain `20.00`

#### Scenario: Tomate reason completes one line
- **WHEN** the Tomate override question is pending and the actor posts `precio especial para cliente`
- **THEN** exactly one catalog `SaleItem` MUST exist with `quantity_normalized` `0.900`, snapshot `20.00`, `unit_price` `30.00`, reason `precio especial para cliente`, and `line_total` `27.00`

#### Scenario: Kilogram basis comes from the product
- **WHEN** that Tomate line is committed
- **THEN** the override unit price MUST be `30.00` MXN per kilogram and the merchant MUST NOT have been required to say `por kilo`

#### Scenario: Unit product uses a per-each override
- **WHEN** Galleta A `current_price` is `12.00`, the actor posts `2 galletas A a 10`, then a valid reason
- **THEN** the line MUST have quantity `2`, snapshot `12.00`, `unit_price` `10.00`, and `line_total` `20.00`

#### Scenario: Package product uses a per-package override
- **WHEN** a catalog product with `sale_unit=package` and `current_price` `15.00` is sold as `3` packages at grounded `11.00`, then a valid reason
- **THEN** the line MUST have `quantity_normalized` `3`, snapshot `15.00`, `unit_price` `11.00`, and `line_total` `33.00`

### Requirement: Catalog price change restarts the question
If the locked `Product.current_price` differs from the pending observed catalog price and differs from the grounded override price, the reason turn MUST roll back that write transaction. It MUST NOT write a `SaleItem`, MUST NOT create a `SaleSession`, and MUST NOT reserve idempotency. After the rollback, it MUST replace the pending observed price with the locked price, keep the product, quantity, unit, and override price, discard the reason just typed, and ask `{Name} ahora está registrado a ${current} por {kg|unidad|paquete}. ¿Por qué lo vendiste a ${override}?`

#### Scenario: Tomate moves from 20 to 22
- **WHEN** the pending observed price is `20.00`, the override is `30.00`, and the locked price is `22.00`
- **THEN** no `SaleItem` and no idempotency row MUST be written, the typed reason MUST NOT be stored, and the response MUST ask why Tomate was sold at `$30.00` against the new `$22.00` per kg

### Requirement: Equal recheck drops the reason
If the locked `Product.current_price` equals the grounded override price, the same transaction MUST persist one normal catalog line with snapshot and `unit_price` equal to that locked price and `price_override_reason` NULL. The typed reason MUST NOT be stored. The response MUST be the normal catalog success sentence, and the card MUST NOT include `catalog_unit_price`.

#### Scenario: Proposed 30 becomes the catalog price
- **WHEN** the pending override is `30.00` and the locked Tomate price is `30.00`
- **THEN** one catalog `SaleItem` MUST exist with snapshot `30.00`, `unit_price` `30.00`, and `price_override_reason` NULL

### Requirement: Normal catalog money uses one product read
A normal catalog add MUST derive `catalog_unit_price_snapshot`, `unit_price`, and `line_total` from one `Product.current_price` read inside the add-item write transaction. The resolve-time price MUST NOT be stored as a second price on that row. `line_total` MUST be `quantity_normalized` times that same price. This path MUST NOT add a product row lock. The existing in-transaction product read remains that authority.

#### Scenario: Snapshot, unit price, and total share one price
- **WHEN** a normal catalog line is committed for Zanahoria at `25.00` MXN and quantity `0.900` kg
- **THEN** `catalog_unit_price_snapshot` and `unit_price` MUST be `25.00` from that in-transaction read and `line_total` MUST be `22.50` from the same price

### Requirement: Cancellation and replacement write nothing from the pending override
While `catalog_price_override` is pending, `cancelar`, `cancela`, and `no` after closed-phrase normalization MUST clear that pending and MUST write no session, item, or idempotency row. The response MUST be `Listo, no registré ese producto.` A new utterance that `parse_sale_utterance` classifies as `utterance` with both a quantity and a display span MUST clear the pending override and MUST be interpreted as a new add, not as a reason. A closed totalize, payment, day-summary, cash-count, or close intent MUST clear the pending override, write no override line, and run that intent. A reason-shaped message with no pending override MUST NOT create an override.

#### Scenario: Cancel clears the question
- **WHEN** a catalog override is pending and the actor posts `cancelar`
- **THEN** the pending entry MUST be gone and no `SaleItem` or `SaleSession` MUST be created for it

#### Scenario: A new sale replaces the question
- **WHEN** a Tomate override is pending and the actor posts `2 galletas A`
- **THEN** the Tomate override MUST NOT be persisted and the new utterance MUST be handled as its own add

#### Scenario: Reason without pending does nothing
- **WHEN** no override is pending and the actor posts `precio especial para cliente`
- **THEN** no override `SaleItem` MUST be created

### Requirement: Grounded amounts only
The override unit price MUST come from `ground_user_price` on the merchant utterance, or from the pending amount that extractor stored. An `AgentDecision` amount that the text does not contain MUST NOT start or complete an override. An `AgentDecision` reason that the completion message does not contain MUST NOT be stored. The amount MUST be a positive `Decimal` with scale at most 2 in the business currency. A higher or lower amount is allowed. This slice MUST NOT apply a percentage limit.

#### Scenario: Model-only price does not override
- **WHEN** the user message is `900gr tomate` and the decision carries `unit_price` `30.00`
- **THEN** the line MUST be a normal catalog line at Tomate `current_price` and no override reason MUST be requested

#### Scenario: Model-only reason is ignored
- **WHEN** an override is pending and the user message is `precio especial para cliente` while a model field carries a different reason
- **THEN** the stored reason MUST be `precio especial para cliente`

### Requirement: Direct override uses the same checks
A direct `sale.add_item@1` with `source_type=catalog` and `price_override` MUST lock the tenant product inside its write transaction, MUST take `catalog_unit_price_snapshot` from that locked `current_price`, MUST require `sale.create` and an open session, MUST validate the amount and the normalized reason, and MUST NOT update `Product.current_price`. It has no pending observed price, so a locked price that still differs does not restart a question. A missing or blank reason when the amount differs MUST NOT persist a line. A direct catalog call without `price_override` MUST remain on the message workflow.

#### Scenario: Direct call cannot skip the reason
- **WHEN** a direct catalog call sets `price_override.unit_price` to `30.00` and omits a non-empty reason while the product price is `20.00`
- **THEN** no `SaleItem` MUST be written and `Product.current_price` MUST remain `20.00`

### Requirement: Replay does not duplicate
The reason-request turn MUST NOT reserve idempotency. The writing completion MUST reserve `lumo.message.add_sale_item` with hash `catalog-price-override|v1|{conversation_id}|{product_id}|{quantity}|{unit}|{snapshot_amount}|{charged_amount}|{normalized_reason}`. An empty reason slot MUST be used when the equal-recheck path discards the reason. The same key and hash MUST replay the original body and MUST NOT insert a second `SaleItem`.

#### Scenario: Same completion key replays
- **WHEN** the reason turn is retried with the same idempotency key and the same hash
- **THEN** one `SaleItem` MUST remain and the stored response MUST be returned

### Requirement: Audit and outbox keep the prices
`sale.add_item@1` `after_payload` MUST include `source_type`, `product_id`, `product_name`, `catalog_unit_price_snapshot`, `unit_price`, `price_override_reason`, and `line_total`. An override commit MUST record policy reason `catalog_price_override` with rule ids including `SALE-001` and `CAT-001`. `sale.item.added` MUST include `catalog_unit_price_snapshot`, `unit_price`, and `price_override_reason`. The system MUST NOT emit `sale.price.overridden` and MUST NOT add an audit action solely because the prices differ.

#### Scenario: Override audit is reconstructable without a second table
- **WHEN** the Tomate override line commits
- **THEN** the `sale.add_item@1` audit payload MUST show snapshot `20.00`, `unit_price` `30.00`, the merchant reason, and `line_total` `27.00`

#### Scenario: Outbox carries the same facts
- **WHEN** that line commits
- **THEN** the `sale.item.added` payload MUST include snapshot `20.00`, `unit_price` `30.00`, and the reason, and no `sale.price.overridden` event MUST exist

### Requirement: Later sale steps ignore the pricing exception
`sale.totalize@1` and `sale.commit@1` MUST sum persisted `line_total` values and MUST NOT branch on an override. Cash, card, and transfer confirmation MUST stay unchanged. OperationalDay and Daily Close MUST include the payment as they do for any other line. `sale.commit@1` MUST still refuse `operational_day_closed`. A cross-tenant `product_id` MUST still fail `fk_sale_items_product_business`.

#### Scenario: Mixed session totalizes the charged totals
- **WHEN** an open session has a normal Zanahoria line `22.50`, a Tomate override line `27.00`, and a free-concept line `36.00`
- **THEN** `sale.totalize@1` MUST report `85.50` and MUST NOT reprice the Tomate line from its snapshot

#### Scenario: Closed day still refuses commit
- **WHEN** the operational day is closed and commit is attempted for a session that contains an override line
- **THEN** commit MUST refuse `operational_day_closed` and MUST NOT confirm the session
