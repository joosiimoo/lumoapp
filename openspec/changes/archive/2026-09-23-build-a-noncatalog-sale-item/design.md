## Context

`sales.sale_items.product_id` is `UUID NOT NULL REFERENCES catalog.products (id)`. The row also stores `product_name_snapshot`, quantity, unit, `unit_price`, currency, and `line_total`. There is no source discriminator. `AddCatalogSaleItem` treats `ProductMatch.NONE` as a stop: "No encontré ese producto en el catálogo." It never inserts a line. `ProductMatch.AMBIGUOUS` already clarifies and writes nothing.

`sale.add_item@1` requires `product_id`. Catalog price comes from `Product.current_price`. `line_total` is `Money.times` (`ROUND_HALF_UP` to `0.01`). The scripted interpreter parses quantity, mass unit, and a product query. It does not parse a price. `InMemoryPendingClarificationStore` remembers product and quantity when the unit is missing. It is process-local, keyed by `(business_id, actor_id, conversation_id)`, and it is not schema `memory`.

`sale.totalize@1` and `sale.commit@1` sum persisted `line_total` values. Cards render `product_name`. Outbox `sale.item.added` is `{sale_item_id, sale_session_id}` and does not include `product_id`. Audit `sale.add_item@1` does include `product_id` and `product_name`. The product foreign key is not composite with `business_id`. RLS is `ENABLE` and `FORCE` on `sale_items`. `lumo_admin` is `NOBYPASSRLS`. Alembic head is `0007_daily_close_confirmation`.

PRD §7.4 and SRS RF-A-032 / RF-A-033 allow a concept line when policy permits. This change is that policy. ADR-020 records it. ADR-015 through ADR-019 stay as they are.

No new package. The work stays in `domain/sales`, `application/workflows/add_catalog_sale_item.py`, `application/pending.py`, `agent/`, `policies/engine.py`, `infrastructure/persistence`, and Alembic `0008`. The workflow class keeps its name.

## Goals / Non-Goals

**Goals:**

- Persist one free-concept `SaleItem` when resolution is `none` and quantity, unit, and an explicit unit price are known.
- Keep unique and ambiguous catalog behavior, including catalog price.
- Keep totalize, payment, OperationalDay, and Daily Close source-agnostic.
- Make the source visible in audit and `sale.item.added` without a new event or table.

**Non-Goals:**

- The proposal's Non-goals. In particular: no `Product` insert, no price override, no new unit family, no draft row, no new tool, no new card, no badge, and no line edit.

## Decisions

### 1. Durable `SaleItem` shape

Keep `product_name_snapshot varchar(200) NOT NULL` as the only display name. Do not add `concept_name`.

Add `source_type varchar(32) NOT NULL` with values `catalog` and `free_concept`. Make `product_id` nullable.

`ck_sale_items_source`:

```sql
(source_type = 'catalog' AND product_id IS NOT NULL)
OR (
  source_type = 'free_concept'
  AND product_id IS NULL
  AND length(btrim(product_name_snapshot)) > 0
)
```

`ck_sale_items_money_positive`: `unit_price > 0 AND line_total > 0`.

Catalog snapshot remains `Product.name` (existing casing). A free-concept `product_name_snapshot` is the merchant-facing concept span after structural cleanup only. It is not the output of `normalize_product_name`. Length 1..200. A cleaned span that is empty or longer than 200 characters clarifies and is not truncated. No second name column and no normalized-name column on `SaleItem`. The lookup string is transient.

Alternative considered: a second `concept_name` column. Rejected because every reader already uses `product_name_snapshot` / UI `product_name`. Alternative considered: a sentinel product row. Rejected because it would invent catalog data.

### 2. Migration `0008` is required

Revision id `0008_noncatalog_sale_item`. `down_revision` is `0007_daily_close_confirmation`.

`product_id` cannot stay mandatory, and no existing column records source. A sentinel product would be semantically wrong.

Upgrade, inside one transaction:

1. Disable RLS on `catalog.products` and `sales.sale_items` only for this migration's reads, backfill, and constraint validation. `lumo_admin` is `NOBYPASSRLS` and otherwise cannot see every tenant. Re-enable `ENABLE` and `FORCE` before the migration returns. Do not grant `BYPASSRLS`.
2. Add `source_type`, backfill every existing row to `catalog`, then set `NOT NULL`.
3. Drop `NOT NULL` on `product_id`. Keep the existing `product_id → catalog.products(id)` foreign key so a non-null id must still exist.
4. Add `UNIQUE (id, business_id)` on `catalog.products` as `uq_products_id_business`.
5. Add `fk_sale_items_product_business` on `(product_id, business_id)` referencing `catalog.products (id, business_id)`. Default `MATCH SIMPLE`: a null `product_id` does not have to match a product; a catalog row must match the same business.
6. Add the two checks above.
7. Restore `FORCE` RLS. Do not change the `tenant_isolation` policy. Do not weaken session or payment foreign keys.

Existing catalog rows stay valid. No sale row is deleted.

### 3. `product_id`

Null only for `free_concept`. Catalog adds still set it from the product loaded under the caller's `TenantContext`. The model, the audit payload, and the outbox use JSON `null`. They never store a guessed id.

### 4. `source_type` is persisted

It is not inferred at read time. Queries, audit, and outbox copy the stored value.

### 5. Display name

Two strings, built by deterministic code. They are not the same value.

`product_name_snapshot` is what cards, audit `product_name`, and the success sentence show. It comes from the raw concept span. Allowed cleanup is trim, collapse of repeated internal whitespace, dropping the leading quantity, dropping the trailing price clause, and dropping tokens the unit grammar already excludes from the concept. Accents and the merchant's casing stay. Do not lowercase, strip accents, title-case, spell-correct, translate, or otherwise rewrite the words. Tool input `concept_name` is this display span. UI `product_name` copies the snapshot. No extra card field.

`resolution_query` is `normalize_product_name` of that display span: NFKD, strip marks, lowercase, collapse space. It is used only for `catalog.resolve_product@1` and is not stored on `SaleItem`.

Concept span rules:

- Drop the leading quantity and the trailing price clause.
- Mass tokens (`g`, `gr`, `gramo(s)`, `kg`, `kilo(s)`, `kilogramo(s)`) set the unit and are removed from the display span, including a following `de`.
- `unidad(es)` and `pieza(s)` set `unit` and are removed with a following `de`.
- `bolsa(s)` and `paquete(s)` set `package` and stay in the display span. "2 bolsas de hielo a 18 cada una" snapshots `bolsas de hielo`. "2 bolsas de Hielo Artesanal a 18" snapshots `bolsas de Hielo Artesanal` and resolves `bolsas de hielo artesanal`.
- "2 Cafés de Olla a 45" snapshots `Cafés de Olla` and resolves `cafes de olla`.
- "1 Café Orgánico 50" snapshots `Café Orgánico` and resolves `cafe organico`.
- "500g de Café Molido a 240 por kilo" snapshots `Café Molido` and resolves `cafe molido`.
- If no unit token remains, the unit is `unit`. This default applies only after resolution is `none`. It does not apply to a catalog product.

Catalog matching still uses `resolution_query`. Unique, ambiguous, and inactive results are unchanged. Preserving display spelling does not skip that lookup. A direct `sale.add_item@1` with `source_type=free_concept` receives `concept_name` as display text, stores that span after trim and whitespace collapse, and resolves `normalize_product_name(concept_name)`. It must not treat the display string as the lookup key. Unique or ambiguous resolution still refuses the free-concept write.

The pending store keeps the display span. A later "por kilo" resolves `normalize_product_name` of that stored span and persists the display span, not the lookup string. Success text uses the snapshot, so casing and accents survive in "Agregué 1 Café Orgánico · $50.00".

### 6. `sale.add_item@1` input

Do not register `sale.add_free_item@1`.

Required: `sale_session_id`, `quantity`, `unit` (`gram|kilogram|unit|package`), `source_type` (`catalog|free_concept`).

- `catalog`: `product_id` required. `concept_name` and `unit_price` are absent from the tool input and are not the stored price. Before that call, the workflow still compares any price `ground_user_price` found in the user text with `Product.current_price`.
- `free_concept`: `product_id` null or absent. `concept_name` required. `unit_price` required as `{amount, currency}`.

Output keeps today's fields, adds `source_type`, and allows `product_id` to be null. The message path builds these arguments after resolution. The model does not supply `product_id` or `line_total` (ADR-006, `SEC-003`).

### 7. Interpreter no-match contract

`AgentDecision` gains optional `unit_price` (decimal string). It is set only when the utterance contains an explicit amount. Provenance is the user text, not the model. The decision does not choose `source_type`. The workflow does, after `catalog.resolve_product@1`:

| Resolution | Next step |
|---|---|
| `unique`, no grounded price | Catalog path. `Product.current_price`. Count-product unit completion stays as it is. A kilogram product with no unit still asks for the unit. |
| `unique`, grounded price `Decimal`-equal to `current_price` | Same catalog path. Store `Product.current_price`, not the user amount. |
| `unique`, grounded price different from `current_price` | Clarify under `CAT-001` reason `catalog_price_mismatch`. No `SaleItem`, no new `SaleSession`, no audit, outbox, or idempotency row. Do not apply the uttered price. Do not silently keep the catalog price. Do not create a free concept or a `Product`. |
| `ambiguous` | Existing clarification. Do not store a free-concept draft. Do not add a line. |
| Inactive name or alias in this tenant | Clarify "Ese producto está inactivo." Write nothing. Do not fall through to free concept. |
| `none` | Free-concept rules below. |

The scripted interpreter must accept, without a vendor LLM:

- Existing catalog utterances, including `900gr zanahoria`, `2 galletas A`, and `900 zanahoria` then `gr`.
- `2 bolsas de hielo a 18 cada una` and `2 bolsas de hielo a 18`.
- `1 pastel 250`.
- `2 hielos`, then `18` or `18 cada uno`.
- `pastel` with no quantity and no price.
- `900gr tomate` adds Tomate at `20.00`. `900gr tomate a 20` does the same and still stores `Product.current_price`. `900gr tomate a 30` clarifies and writes nothing.
- An ambiguous alias stays ambiguous even if the utterance includes `a 18`.

Closed commands (payment, totalize, day, cash count, close) keep matching first.

### 8. Clarification state

Extend `PendingSaleClarification` in the existing in-memory store. Do not persist a draft `SaleItem`, do not put partial state on `SaleSession`, and do not create schema `memory`.

`kind` is `catalog_unit` or `free_concept`. Fields: `product_query`, optional `quantity`, optional canonical `unit`, optional `unit_price` (only a previously grounded amount), optional `price_basis` (`per_each` or `per_kilogram`), optional `package_word` (`bolsa` or `paquete`) for copy. For `free_concept`, `product_query` is the display span. A follow-up resolves `normalize_product_name` of that stored span and persists the span. It does not replace `product_query` with the lookup string. Catalog pending stays as it is today.

- Missing catalog unit uses `catalog_unit`, as today. A later `gr` / `kg` completes that path. A bare `18` does not.
- Missing free-concept price or quantity uses `free_concept`. The first turn resolves before asking, writes nothing, and does not call `idempotency.begin`.
- A price-only follow-up (`18`, `a 18`, `18 cada una`, `18 cada uno`) fills `unit_price` on a `free_concept` pending that already has concept, quantity, and unit `unit` or `package`. One add follows. The follow-up is not a new concept named "18".
- A gram or kilogram utterance that has a grounded amount but no per-kilogram marker stores that amount with `price_basis` missing and asks the basis question. It does not call `idempotency.begin`. A later `por kilo`, `por kg`, `el kilo`, `por kilogramo`, or `el kilogramo` sets the basis and adds one line. `sí` and `no` do not.
- A quantity-only follow-up fills quantity. If price is still missing, ask for price and still write nothing.
- `pastel` then `2` then `250` writes one line on the third turn.
- A new complete utterance replaces pending.
- Ambiguous resolution clears a free-concept pending.
- Success clears pending.
- A price follow-up with no pending clarifies and writes nothing.

Copy, and no taxonomy in the merchant's voice:

- Missing price, package word `bolsa`: "¿A qué precio vendiste cada bolsa?"
- Missing price, package word `paquete`: "¿A qué precio vendiste cada paquete?"
- Missing price, unit `unit`: "¿A qué precio vendiste cada uno?"
- Missing price, gram or kilogram, and no amount yet: "¿A qué precio vendiste cada kilogramo?"
- Amount present, gram or kilogram, basis missing: "¿Los $40.00 son por kilogramo? Responde por kilo." The amount in that sentence is the grounded candidate formatted to two decimals.
- Missing quantity: "¿Cuántos vendiste?"
- Missing quantity and price: "¿Cuántos vendiste y a qué precio?"
- Unsupported unit: "No reconozco esa unidad. Puedo registrar unidad, paquete, gramos o kilogramos."
- Invalid price: "El precio tiene que ser mayor que cero."
- Foreign currency word (`usd`, `dolar`, `dolares`, `eur`): "Solo puedo registrar precios en pesos."
- Success, unit or package: `Agregué {quantity} {snapshot} · ${line_total}` → "Agregué 2 bolsas de hielo · $36.00", "Agregué 1 pastel · $250.00".
- Success, kilogram: `Agregué {quantity_normalized} kg de {snapshot} · ${line_total}`.
- Catalog success text stays `Agregué {qty} {unit label} de {Product.name} · ${amount}`.
- Catalog price mismatch, using the product `sale_unit`: "{Name} está registrado a ${current_price} por {kg|unidad|paquete}. En esta versión no puedo cambiar el precio de un producto del catálogo." Tomate at 30 is "Tomate está registrado a $20.00 por kg. En esta versión no puedo cambiar el precio de un producto del catálogo."

`text` and `sale_item_added@1.fallback_text` are that success sentence.

### 9. Units

No new `SaleUnit`. Input units stay `gram`, `kilogram`, `unit`, `package`.

Approved synonyms, mapped only by the interpreter table:

- gram: `g`, `gr`, `gramo`, `gramos`
- kilogram: `kg`, `kilo`, `kilos`, `kilogramo`, `kilogramos`
- package: `bolsa`, `bolsas`, `paquete`, `paquetes`
- unit: `unidad`, `unidades`, `pieza`, `piezas`, plus the count default after `match=none`

`caja`, `cajas`, `litro`, `litros`, `ml`, `manojo`, `manojos`, `docena`, `docenas` are unsupported. Clarify. Do not convert them to `package` or `unit`.

Gram on a catalog product is still legal only when `sale_unit=kilogram`. Gram or kilogram on a free concept normalizes with the existing rule by passing `sale_unit=kilogram`: grams divide by `Decimal('1000')` and `unit_normalized=kilogram`. That normalization does not decide the price basis.

For `unit` and `package`, one explicit positive amount is the price per that unit. "cada una" and "cada uno" are optional. "2 bolsas de hielo a 18" is 18.00 per package and totals 36.00. "1 pastel 250" is 250.00 per unit. This shortcut does not apply to gram or kilogram.

For gram or kilogram, the same utterance or a later reply must contain an explicit per-kilogram marker: `el kilo`, `por kilo`, `por kg`, `por kilogramo`, or `el kilogramo`. "500g de hielo a 40 por kilo", "a 40 el kilo", "a 40 por kg", and "el kilo a 40" persist `0.500` kg, unit price `40.00`, line total `20.00`. "500g de hielo a 40" and "2 kg de hielo a 40" do not persist.

Mass-basis follow-up, only while that pending record exists, accepts those same markers and no others. Bare "sí" and "no" do not complete the line. They leave the pending record in place and repeat the basis question. "por kilo" then adds exactly one line, using the amount grounded on the earlier turn.

### 10. Decimal rule

Domain code parses quantity with `parse_quantity` (positive `Decimal`, no float). Unit price is a `Decimal` string, greater than zero, at most two decimal places, currency equal to the business currency (MXN for Carrota). Three-decimal prices and zero or negative prices are rejected before persist. Do not quantize an invalid unit price into a valid one.

`line_total = unit_price.times(quantity_normalized)` once. `Money.times` quantizes the product to `0.01` with `ROUND_HALF_UP`. If that result is `0.00` or less, reject and persist nothing. Catalog lines still multiply `Product.current_price`. The user amount is never the stored catalog price. Compare a grounded user amount to `current_price` with `Decimal` equality after both sides are already scale 2. An amount with more than two decimal places is invalid and is not rounded into a match. Do not compare strings or floats. A model entity `line_total=99.00` is still ignored.

### 10a. Price provenance

`AgentDecision.unit_price` is not financial authority. A pure function `ground_user_price(raw_message)` parses the current user text and returns a `Decimal` amount and, for mass, whether a per-kilogram marker is present. It does not call the model or the database, and it does not store source spans.

The workflow persists a free-concept amount only when that function extracted it from the current message, or when the current message is an accepted basis-only follow-up and the pending store already holds an amount this same function extracted on an earlier turn. If `decision.unit_price` disagrees with the extracted amount, the decision amount is discarded. If the decision has an amount and the text has none and no pending grounded amount applies, nothing is persisted. Pending `unit_price` is written only from `ground_user_price`.

Examples: `2 * 18.00 = 36.00`, `1 * 250.00 = 250.00`, Zanahoria `0.900 * 25.00 = 22.50`.

### 11. Audit

Same actions: `sale.start@1` and `sale.add_item@1`. No new audit table.

`sale.add_item@1` `after_payload` adds `source_type`. `product_id` is a string for catalog and JSON `null` for free concept. `product_name` is the snapshot. `unit_price` is the persisted price. Do not add a candidate product id or a similarity score.

### 12. Outbox

Keep event type `sale.item.added`. Extend the payload to:

```json
{
  "sale_item_id": "<uuid>",
  "sale_session_id": "<uuid>",
  "source_type": "catalog",
  "product_id": "<uuid or null>",
  "product_name": "<snapshot>"
}
```

Free concept sends `source_type=free_concept` and `product_id=null`. Do not add `sale.free_item.added`.

### 13. Downgrade

Before dropping anything, if any `sale_items` row has `source_type=free_concept` or `product_id IS NULL`, raise and leave the schema at `0008`. Do not delete those rows and do not invent products so the old `NOT NULL` column can be restored.

When no such row exists, drop the new checks and `fk_sale_items_product_business`, drop `uq_products_id_business`, drop `source_type`, and set `product_id` `NOT NULL`. Keep the original `product_id` foreign key. Catalog sale rows stay. The same temporary RLS disable/restore used on upgrade applies so the existence check sees every tenant.

### 14. Cards

No `source_type` on `sale_item_added@1`, `sale_summary@1`, or `sale_confirmed@1`. No "Concepto libre" badge. No save-to-catalog action. Version stays `1`. The name row is `product_name`. The existing detail line still uses `quantity_normalized`, `unit_normalized` (`paquete`, `unidad`, `kg`), and server `unit_price` / `line_total`. Flutter does not multiply.

### 15. Copy

Section 8 is the closed copy. Do not say "Producto no encontrado" or "Creando item libre".

### 16. Later edit

No. Free-concept lines are insert-only, same as catalog lines. No edit or delete tool in this change.

### Idempotency, totalize, commit, close

Operation type stays `lumo.message.add_sale_item`. A clarification turn does not reserve a key. The completing turn reserves once.

Catalog request hash stays `raw_message|conversation_id|quantity|unit|product_query`. Free-concept hash appends `|unit_price`. Same key and hash returns the original body and does not insert a second line. A second complete utterance with a new key inserts a second line, as catalog add already does.

Totalize and commit do not read `source_type`. Mixed sessions sum `line_total`. Cash, card, and transfer stay the closed methods. OperationalDay gross and the closing snapshot include the payment because the sale is confirmed, not because of the line source.

Add-item and totalize still do not consult the day. `sale.commit@1` still refuses a closed day with `operational_day_closed` and writes no payment. A free-concept line on a new open session after close does not weaken that guard.

### Policy `SALE-005`

Register `SALE-005` beside the existing sale rules.

- Allow a free concept only when resolution is `none`, there is no inactive collision, quantity is positive, the unit is supported, and `unit_price` is an explicit positive MXN amount with scale at most 2 that `ground_user_price` accepted.
- For `unit` and `package`, that amount is the per-each price.
- For `gram` and `kilogram`, also require `price_basis=per_kilogram`. If the amount is present and the basis is not, clarify with `price_basis_required` and write nothing.
- Clarify when price or quantity is missing. Reason `price_required` or `quantity_required`.
- Deny non-positive price with `price_not_positive`.
- A unique catalog match whose grounded price differs from `Product.current_price` is `CAT-001` / `catalog_price_mismatch`. It is not `SALE-005`.
- `CAT-001` still clarifies ambiguity and still rejects an inactive product. `match=none` is not by itself `product_not_found` when `SALE-005` allows the line.
- `CAT-002` still rejects an unsupported or incompatible unit.
- A direct tool call with `source_type=free_concept` resolves `normalize_product_name(concept_name)` and persists the display `concept_name`. Unique or ambiguous results do not persist a free concept.

### RLS

`business_id` stays on the row. `FORCE` RLS and `tenant_isolation` stay. The new composite foreign key is what stops a catalog line from referencing another business's product id. A free-concept row cannot reference a product because `product_id` is null. Application code still copies `business_id` from `TenantContext`.

## Risks / Trade-offs

- [In-memory pending is lost on process restart] → The merchant repeats the missing fact. No partial sale row is left behind. A durable draft would be a new workflow, which this slice refuses.
- [Defaulting a bare count to `unit`] → Applies only after `match=none`. Catalog kilogram products still ask for a unit. "2 zanahoria" must not become two units of Zanahoria.
- [Keeping "bolsas" inside the snapshot and also storing `package`] → The sentence matches the merchant's words. The card's detail line still says `paquete` through the existing label map. No second display string.
- [Catalog lookup lowercases and strips accents] → That string is transient. `product_name_snapshot` keeps the merchant's spelling so "Café Orgánico" does not become "cafe organico" on the card.
- [A named catalog price can differ from `current_price`] → Clarify and write nothing. Do not silently keep the catalog price and do not apply the named price. Override stays out of scope.
- [A mass amount without "por kilo" is ambiguous] → Ask for an explicit per-kilogram phrase. Do not treat 40 as either per kilogram or per gram. Bare "sí" does not complete it.
- [`MATCH SIMPLE` skips the composite FK when `product_id` is null] → That is the free-concept case. Catalog rows have both columns set and must match.
- [Constraint validation under `NOBYPASSRLS`] → The migration disables RLS only inside its transaction and turns `FORCE` back on before return, same constraint as `0005` / `0007`.
- [Downgrade cannot represent free-concept rows] → Abort. Do not drop them.

## Migration Plan

Deploy `0008` before the application that writes `free_concept`. The old application cannot insert a null `product_id`; it also cannot read a `source_type` column it does not know if it uses `SELECT *` into a fixed ORM. Ship migration and application together. Rollback of the application without downgrade is safe only if no free-concept row exists; otherwise leave the schema at `0008` and roll forward.

## Open Questions

None. The catalog price guard, the per-kilogram mass basis, and the split between the display snapshot and the transient resolution query are closed. A cleaned span longer than 200 characters clarifies and is not truncated.
