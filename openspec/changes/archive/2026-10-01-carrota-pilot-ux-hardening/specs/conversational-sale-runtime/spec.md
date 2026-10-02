## MODIFIED Requirements

### Requirement: Pending catalog price override
When a unique catalog price differs and the utterance has no valid inline reason, the runtime MUST store `kind=catalog_price_override` in the existing in-memory store keyed by `(business_id, actor_id, conversation_id)`. The entry MUST include the merchant product query, the resolved `product_id`, quantity, unit, the grounded override amount, and the observed catalog price. It MUST NOT include a reason. Schema `memory` MUST NOT be created. While that kind is pending, `cancelar`, `cancela`, and `no` after closed-phrase normalization MUST clear it and write nothing. A `parse_sale_utterance` result of kind `utterance` with both quantity and a display span MUST clear it and MUST be interpreted as a new add. Other text MUST be the reason candidate, not a model field. A closed totalize, payment, day-summary, cash-count, or close intent MUST clear it and run that intent. A unique catalog match whose same utterance already contains a valid inline reason MUST complete that override in the message and MUST NOT leave this pending kind stored. A unique catalog match whose same utterance contains an inline reason longer than 200 characters MUST respond `Ese motivo es demasiado largo.`, MUST write nothing, and MUST leave this pending kind stored with product, quantity, unit, grounded override amount, and observed catalog price, and without a reason, so a later valid reason message can complete it.

#### Scenario: Reason is the next merchant message
- **WHEN** a Tomate override is pending and the actor posts `precio especial para cliente`
- **THEN** the runtime MUST treat that text as the reason and MUST NOT parse it as a new product

#### Scenario: Cancel writes nothing
- **WHEN** a catalog override is pending and the actor posts `no`
- **THEN** the pending entry MUST be cleared and no `SaleItem` MUST be written

#### Scenario: Inline reason does not stay pending
- **WHEN** a Carrota actor posts `1 galleta A a 10 por promoción` and Galleta A uniquely matches at `12.00`
- **THEN** the runtime MUST NOT leave `kind=catalog_price_override` pending after the response

#### Scenario: Overlong inline reason leaves pending override
- **WHEN** a Carrota actor posts `1 galleta A a 10 por` plus a motivo longer than 200 characters and Galleta A uniquely matches at `12.00`
- **THEN** the runtime MUST leave `kind=catalog_price_override` pending without a reason, and a later `promoción` MUST complete that override

## ADDED Requirements

### Requirement: Scripted interpreter keeps an inline catalog reason on the catalog path
The scripted interpreter MUST treat `1 galleta A a 10 por promoción` as `add_sale_item` for the cleaned span `galleta A`, with grounded unit price `10.00` and inline reason `promoción`. It MUST NOT set a free-concept name to the whole phrase. It MUST NOT require a vendor LLM. `2 galletas A` MUST remain a catalog add-item decision with no required unit price.

#### Scenario: Promotion phrase is not a free-concept name
- **WHEN** the scripted interpreter receives `1 galleta A a 10 por promoción`
- **THEN** the decision MUST be `add_sale_item` for span `galleta A` with unit price `10.00` and reason `promoción`, and the concept name MUST NOT be `1 galleta A a 10 por promoción`
