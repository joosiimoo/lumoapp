## Purpose

A sale line may be a free concept when catalog resolution finds no active product. The line stores the concept, quantity, unit, explicit unit price, and a server-calculated line total. It does not create catalog data.

## ADDED Requirements

### Requirement: Free concept is sale data
A `SaleItem` with `source_type=free_concept` MUST have `product_id` NULL and a non-empty `product_name_snapshot`. The snapshot MUST be the merchant-facing concept span after structural cleanup only. It MUST NOT be the output of `normalize_product_name`. Adding that line MUST NOT insert a `catalog.products` row, a `catalog.product_aliases` row, a SKU, or an inventory row. The line MUST NOT be updated or deleted by any tool in this change.

#### Scenario: Unknown concept does not create a product
- **WHEN** a Carrota actor adds "2 bolsas de hielo a 18 cada una" and no active product matches
- **THEN** one `SaleItem` MUST exist with `source_type=free_concept`, `product_id` NULL, and `product_name_snapshot=bolsas de hielo`, and the count of `catalog.products` for that business MUST be unchanged

#### Scenario: No edit tool
- **WHEN** the tool registry is inspected after this change
- **THEN** it MUST NOT contain a sale-item edit or delete tool

### Requirement: Display snapshot is not the resolution query
`product_name_snapshot` for a free concept MUST be built from the raw concept span. Deterministic cleanup MUST be limited to trimming, collapsing repeated internal whitespace, removing the leading quantity, removing the trailing price clause, and removing mass or count tokens that the unit grammar already excludes, including a following `de` where that grammar removes it. `bolsa`, `bolsas`, `paquete`, and `paquetes` MUST remain in the snapshot and MUST still set `unit_normalized` to `package`. The snapshot MUST preserve accents and the merchant's casing. It MUST NOT be lowercased, accent-stripped, title-cased, spell-corrected, translated, or rewritten. Catalog resolution MUST use `normalize_product_name` of that display span as a transient `resolution_query` and MUST NOT persist that query on `SaleItem`. There MUST be no second display column and no normalized-name column. A direct `sale.add_item@1` with `concept_name` MUST store that display value after trim and whitespace collapse and MUST resolve `normalize_product_name(concept_name)` before it may persist `free_concept`. Unique or ambiguous resolution MUST still refuse that write. Cards MUST receive `product_name` equal to the snapshot. Flutter MUST render that string as supplied and MUST NOT lowercase it or strip accents.

#### Scenario: Lowercase bags keep both strings
- **WHEN** the actor posts "2 bolsas de hielo a 18" and resolution of normalized "bolsas de hielo" is `none`
- **THEN** `product_name_snapshot` MUST be `bolsas de hielo` and `unit_normalized` MUST be `package`

#### Scenario: Accented coffee keeps its casing
- **WHEN** the actor posts "1 Café Orgánico 50" and normalized "cafe organico" matches no catalog product
- **THEN** `product_name_snapshot` MUST be `Café Orgánico` and `sale_item_added@1` `data.product_name` MUST be `Café Orgánico`

#### Scenario: Mass coffee drops the unit token only
- **WHEN** the actor posts "500g de Café Molido a 240 por kilo" and normalized "cafe molido" matches nothing
- **THEN** `product_name_snapshot` MUST be `Café Molido`, `quantity_normalized` MUST be `0.500`, and `unit_normalized` MUST be `kilogram`

#### Scenario: Normalized coffee still hits the catalog
- **WHEN** normalized "cafe organico" uniquely matches an active catalog product and the actor posts "1 Café Orgánico 50"
- **THEN** the line MUST be `source_type=catalog` and no free-concept row MUST be written

#### Scenario: Flutter shows the snapshot unchanged
- **WHEN** Flutter receives `product_name` `Café Orgánico`
- **THEN** it MUST show `Café Orgánico` and MUST NOT show `cafe organico`

### Requirement: Explicit unit price
A free-concept unit price MUST come from the user utterance or from a later clarification in the same conversation. The system MUST NOT use a similar catalog price, a historical price, a model guess, a default price, or an external lookup. The amount MUST be a positive `Decimal` with at most two decimal places and currency equal to the business currency. Zero, negative, and three-or-more-decimal amounts MUST be rejected with no `SaleItem`. A foreign-currency word MUST be rejected with no `SaleItem`.

#### Scenario: Priced bags are accepted
- **WHEN** the actor posts "2 bolsas de hielo a 18 cada una" and resolution is `none`
- **THEN** the persisted `unit_price.amount` MUST be `18.00` and `currency` MUST be `MXN`

#### Scenario: Missing price writes nothing
- **WHEN** the actor posts "2 bolsas de hielo" and resolution is `none`
- **THEN** the response MUST be "¿A qué precio vendiste cada bolsa?", `ui` MUST be empty, and no `SaleSession` or `SaleItem` MUST be created for that message

#### Scenario: Zero price is rejected
- **WHEN** the actor posts "2 bolsas de hielo a 0"
- **THEN** no `SaleItem` MUST be persisted and the response MUST be "El precio tiene que ser mayor que cero."

#### Scenario: Three decimal places are rejected
- **WHEN** the actor posts "2 bolsas de hielo a 18.005"
- **THEN** no `SaleItem` MUST be persisted

### Requirement: Deterministic free-concept total
The trusted line total MUST be `quantity_normalized * unit_price`, calculated once by `Money.times` with `ROUND_HALF_UP` to `0.01`. Flutter and the LLM MUST NOT calculate it. A model-supplied line total MUST be ignored. A result that quantizes to `0.00` or less MUST be rejected with no row.

#### Scenario: Two bags at 18
- **WHEN** quantity normalized is `2`, unit is `package`, and unit price is `18.00` MXN
- **THEN** persisted and returned `line_total.amount` MUST be `36.00`

#### Scenario: One pastel at 250
- **WHEN** the actor posts "1 pastel 250" and resolution is `none`
- **THEN** quantity normalized MUST be `1`, `unit_normalized` MUST be `unit`, `unit_price.amount` MUST be `250.00`, and `line_total.amount` MUST be `250.00`

### Requirement: Supported units only
Free-concept input units MUST be `gram`, `kilogram`, `unit`, and `package`. `bolsa` and `bolsas` and `paquete` and `paquetes` MUST map to `package` and MUST remain inside the snapshot. `unidad`, `unidades`, `pieza`, and `piezas` MUST map to `unit` and MUST be removed from the snapshot. Existing gram and kilogram synonyms MUST map as they do today. After `match=none`, a quantity with no unit token MUST use `unit`. `caja`, `litro`, `ml`, `manojo`, and `docena` MUST NOT be converted. Gram and kilogram on a free concept MUST normalize to `kilogram` using `Decimal`. That normalization MUST NOT decide the price basis.

#### Scenario: Bags map to package
- **WHEN** "2 bolsas de hielo a 18 cada una" is added as a free concept
- **THEN** `unit_normalized` MUST be `package` and `quantity_normalized` MUST be `2`

#### Scenario: Bare count defaults to unit
- **WHEN** "2 hielos" is interpreted and resolution is `none`
- **THEN** the pending unit MUST be `unit` and the system MUST ask for the price rather than for a unit

#### Scenario: Unsupported box is not a package
- **WHEN** the actor posts "2 cajas de hielo a 18"
- **THEN** the response MUST be "No reconozco esa unidad. Puedo registrar unidad, paquete, gramos o kilogramos." and no `SaleItem` MUST be persisted

#### Scenario: Grams without a basis write nothing
- **WHEN** the actor posts "500g de hielo a 40" and resolution is `none`
- **THEN** the response MUST be "¿Los $40.00 son por kilogramo? Responde por kilo." and no `SaleSession`, `SaleItem`, audit row, outbox row, or idempotency row MUST be written

#### Scenario: Explicit per-kilogram price
- **WHEN** the actor posts "500g de hielo a 40 por kilo" and resolution is `none`
- **THEN** `quantity_normalized` MUST be `0.500`, `unit_normalized` MUST be `kilogram`, `unit_price.amount` MUST be `40.00`, and `line_total.amount` MUST be `20.00`

#### Scenario: Basis follow-up adds one line
- **WHEN** the actor posts "500g de hielo a 40" and then "por kilo" on the same `conversation_id` and resolution stays `none`
- **THEN** the first turn MUST write nothing and the second MUST persist exactly one free-concept line with `line_total.amount` `20.00`

### Requirement: Clarification completes as one line
Missing free-concept fields MUST be held only in the in-memory pending clarification store for `(business_id, actor_id, conversation_id)`. The store MUST NOT be schema `memory` and MUST NOT insert a `SaleItem`. A later message that supplies only the missing price MUST add exactly one line on the same conversation and MUST NOT treat the price as a new concept. A price follow-up with no pending state MUST write nothing.

#### Scenario: Price follow-up adds one line
- **WHEN** the actor posts "2 hielos" and then "18 cada uno" with the same `conversation_id` and resolution stays `none`
- **THEN** the first response MUST ask "¿A qué precio vendiste cada uno?" with no item, and the second MUST persist exactly one free-concept line with `line_total.amount` `36.00`

#### Scenario: Bare concept asks and writes nothing
- **WHEN** the actor posts "pastel" and resolution is `none`
- **THEN** the response MUST be "¿Cuántos vendiste y a qué precio?" and no `SaleItem` MUST exist

#### Scenario: Quantity then price is still one line
- **WHEN** the actor posts "pastel", then "2", then "250" on the same `conversation_id` and resolution stays `none`
- **THEN** exactly one free-concept `SaleItem` MUST exist, for `pastel` at `250.00`

#### Scenario: Price without pending writes nothing
- **WHEN** the actor posts "18" and no free-concept clarification is pending for that conversation
- **THEN** no `SaleItem` MUST be persisted

### Requirement: Count and package price means per each
When the free-concept unit is `unit` or `package`, one explicit positive amount in the utterance MUST be the price per that unit. "cada una" and "cada uno" MUST be optional. This shortcut MUST NOT apply to `gram` or `kilogram`.

#### Scenario: Bags without cada una
- **WHEN** the actor posts "2 bolsas de hielo a 18" and resolution is `none`
- **THEN** `unit_normalized` MUST be `package`, `unit_price.amount` MUST be `18.00`, and `line_total.amount` MUST be `36.00`

### Requirement: Mass price requires a per-kilogram basis
A free-concept line whose input unit is `gram` or `kilogram` MUST NOT be persisted unless the current utterance, or an accepted follow-up, explicitly marks the amount as per kilogram. The accepted markers MUST be `el kilo`, `por kilo`, `por kg`, `por kilogramo`, and `el kilogramo`. Bare "sí" and "no" MUST NOT set that basis. The missing-basis turn MUST ask "¿Los $40.00 son por kilogramo? Responde por kilo." using the grounded amount at two decimals, and MUST NOT write a `SaleSession`, `SaleItem`, audit row, outbox row, or idempotency row.

#### Scenario: Kilogram without a marker asks
- **WHEN** the actor posts "2 kg de hielo a 40" and resolution is `none`
- **THEN** no `SaleItem` MUST be persisted

#### Scenario: Si does not confirm the basis
- **WHEN** a mass-basis clarification is pending and the actor posts "sí"
- **THEN** no `SaleItem` MUST be persisted and the pending grounded amount MUST remain

### Requirement: Grounded price only
`AgentDecision.unit_price` MUST be treated as a candidate. The workflow MUST persist a free-concept amount only when a deterministic extractor finds that amount in the current raw user message, or when the current message is an accepted basis-only follow-up and the pending store already holds an amount extracted from an earlier user message. A candidate that the user text does not contain MUST NOT be persisted. The extractor result MUST win when it disagrees with the candidate. No source span MUST be stored. Catalog comparison MUST use `Decimal` equality of scale-2 amounts and MUST NOT use strings or floats. An amount with more than two decimal places MUST NOT be rounded into equality.

#### Scenario: Model price is not in the text
- **WHEN** the user message is "2 bolsas de hielo" and the decision carries `unit_price` `99.00`
- **THEN** no `SaleItem` MUST be persisted at `99.00`

#### Scenario: Equal catalog amount still stores the catalog price
- **WHEN** a Carrota actor posts "900gr tomate a 20"
- **THEN** the line MUST be `source_type=catalog` and `unit_price.amount` MUST be `20.00` taken from `Product.current_price`

### Requirement: Catalog match wins
A unique active catalog match with no grounded price, or with a grounded price `Decimal`-equal to `Product.current_price`, MUST stay on the catalog path and MUST store `Product.current_price`. A grounded price that differs MUST clarify under `CAT-001` with reason `catalog_price_mismatch`, MUST NOT persist a `SaleItem`, MUST NOT create a `SaleSession`, MUST NOT reserve idempotency, and MUST NOT create a free concept or a `Product`. The copy MUST be "Tomate está registrado a $20.00 por kg. En esta versión no puedo cambiar el precio de un producto del catálogo." for that Tomate case, and the same sentence with `por unidad` or `por paquete` for those sale units. An ambiguous match MUST keep the current clarification and MUST NOT become a free concept even when a price was uttered. An inactive product or alias with the same normalized name MUST NOT become a free concept.

#### Scenario: Tomate stays catalog
- **WHEN** a Carrota actor posts "900gr tomate"
- **THEN** the line MUST have `source_type=catalog`, Tomate's `product_id`, `unit_price.amount` `20.00`, and `line_total.amount` `18.00`

#### Scenario: Uttered catalog price is refused
- **WHEN** a Carrota actor posts "900gr tomate a 30"
- **THEN** the response MUST be "Tomate está registrado a $20.00 por kg. En esta versión no puedo cambiar el precio de un producto del catálogo." and no `SaleItem`, new `SaleSession`, or idempotency row MUST be written

#### Scenario: Ambiguity is not a free concept
- **WHEN** two active products share the alias used in "900gr zanahoria a 18"
- **THEN** the response MUST ask which product was sold, and no `SaleItem` MUST be persisted

#### Scenario: Inactive name is not a free concept
- **WHEN** the only name match is an inactive product
- **THEN** the response MUST be "Ese producto está inactivo." and no `SaleItem` or `Product` MUST be inserted

### Requirement: Mixed sale, totalize, and payment
A free-concept line MUST be allowed on an `open` session that already has catalog lines. `sale.totalize@1` MUST sum persisted `line_total` values of both sources. `sale.commit@1` with `cash`, `card`, or `transfer` MUST confirm that session and MUST NOT branch on `source_type`. The confirmed sale's payment MUST be included in the operational-day totals and in Daily Close the same way as a catalog-only sale. Commit into a closed day MUST still refuse.

#### Scenario: Mixed total
- **WHEN** an open session has Zanahoria `22.50` and a free-concept line `36.00`
- **THEN** totalize MUST return `58.50` and both display names MUST appear in `sale_summary@1`

#### Scenario: Cash commit of a mixed sale
- **WHEN** that session is `ready_to_charge` and the actor pays `efectivo`
- **THEN** the session MUST become `confirmed`, one `Payment` MUST equal `58.50`, and `sale_confirmed@1` MUST show the free-concept display name

#### Scenario: Card and transfer also commit
- **WHEN** a `ready_to_charge` session whose lines include a free concept is committed with `card` or `transfer`
- **THEN** the payment method MUST be that method and the session MUST be `confirmed`

#### Scenario: Closed day still refuses commit
- **WHEN** today's operational day is `closed` and the actor tries to commit a `ready_to_charge` session that contains a free-concept line
- **THEN** commit MUST refuse with `operational_day_closed` and MUST NOT insert a `Payment`

#### Scenario: Confirmed free-concept sale counts in the day
- **WHEN** a sale that contains a free-concept line is confirmed with cash before close
- **THEN** `operational_day.summary@1` gross sales and the later closing snapshot MUST include that payment amount

### Requirement: Idempotent free-concept add
The completing add MUST use `lumo.message.add_sale_item`. The same key and request hash MUST return the original body and MUST NOT insert a second line. Clarification turns MUST NOT insert an idempotency row. A price follow-up MUST NOT insert one line per turn.

#### Scenario: Replay does not duplicate
- **WHEN** the completing message "2 bolsas de hielo a 18 cada una" is resubmitted with the same idempotency key and payload hash
- **THEN** the original `sale_item_id` MUST be returned and exactly one free-concept row MUST exist

#### Scenario: Clarification is not a reserved key
- **WHEN** the actor posts "2 bolsas de hielo" with a fresh idempotency key and the price is missing
- **THEN** no `lumo.message.add_sale_item` row MUST be written for that key
