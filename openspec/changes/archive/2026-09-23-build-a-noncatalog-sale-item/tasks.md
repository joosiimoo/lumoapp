## 1. Persistence schema

- [x] 1.1 Add Alembic `0008_noncatalog_sale_item` with `down_revision = 0007_daily_close_confirmation`: nullable `product_id`, `source_type` backfilled to `catalog`, `ck_sale_items_source`, `ck_sale_items_money_positive`, `uq_products_id_business`, and `fk_sale_items_product_business`
- [x] 1.2 Disable RLS only inside that upgrade and downgrade existence check, then `ENABLE` and `FORCE` it again before return, without granting `BYPASSRLS`
- [x] 1.3 Implement downgrade that aborts when any `free_concept` row or null `product_id` exists, and otherwise restores `product_id NOT NULL` without deleting catalog rows
- [x] 1.4 Map `source_type` and nullable `product_id` on `SaleItemRow` in `backend/app/infrastructure/persistence/models.py`

## 2. Domain invariants

- [x] 2.1 Add `SaleItemSource` and nullable `product_id` on domain `SaleItem`, with a check that catalog and free concept are mutually exclusive
- [x] 2.2 Validate explicit free-concept unit price as a positive `Decimal` with at most two places, and reject a `Money.times` result of `0.00` or less
- [x] 2.3 Normalize free-concept gram and kilogram through the existing kilogram rule, and keep catalog gram rejection for non-kilogram products
- [x] 2.4 Unit-test the source invariant, `2 * 18.00 = 36.00`, Zanahoria `22.50`, and rejected zero, negative, and three-decimal prices

## 3. Interpreter contract

- [x] 3.1 Add optional `unit_price` on `AgentDecision` and leave `source_type` for the workflow to decide
- [x] 3.2 Extend the scripted sale grammar for priced bags, `1 pastel 250`, bare `pastel`, `2 hielos`, a price-only follow-up, and the per-kilogram markers `el kilo`, `por kilo`, `por kg`, `por kilogramo`, and `el kilogramo`
- [x] 3.3 Map only the approved synonyms, and treat `caja`, `litro`, `ml`, `manojo`, and `docena` as unsupported units with the specified Spanish copy
- [x] 3.4 Add `ground_user_price` over the raw message. Persist a free-concept amount only from that extractor or from a pending amount it stored earlier. Discard a decision amount the text does not contain

## 4. Catalog no-match routing

- [x] 4.1 On a unique catalog match, store `Product.current_price` when no price was uttered or the grounded `Decimal` equals that price. Do not store the user amount
- [x] 4.2 Keep ambiguous resolution on the current clarification and do not store a free-concept draft
- [x] 4.3 Clarify "Ese producto está inactivo." when the normalized name hits an inactive product or alias, and do not create a free-concept line
- [x] 4.4 Route `match=none` with complete facts to one free-concept insert and leave `catalog.resolve_product@1` read-only
- [x] 4.5 When a unique grounded price differs, clarify under `CAT-001` reason `catalog_price_mismatch` with the Tomate copy, and write no item, session, audit, outbox, idempotency row, free concept, or `Product`

## 5. Clarification state

- [x] 5.1 Extend `PendingSaleClarification` with `kind` `catalog_unit` | `free_concept`, optional unit, optional grounded unit price, optional `price_basis`, and optional package word. For `free_concept`, store the display span in `product_query` and do not replace it with `normalize_product_name`
- [x] 5.2 Merge a price-only follow-up only into a `unit` or `package` `free_concept`, and keep `gr` / `kg` merging only into `catalog_unit`
- [x] 5.3 Ask with the closed copy for missing price, missing quantity, and missing both, and write no session or item on those turns
- [x] 5.4 For gram or kilogram with an amount and no per-kilogram marker, store the grounded amount and ask "¿Los $40.00 son por kilogramo? Responde por kilo." Accept only `por kilo`, `por kg`, `el kilo`, `por kilogramo`, and `el kilogramo`. `sí` and `no` repeat the question and write nothing

## 6. sale.add_item extension

- [x] 6.1 Extend the `sale.add_item@1` registration with `source_type`, conditional `product_id`, `concept_name`, and `unit_price`, and do not register `sale.add_free_item@1`
- [x] 6.2 Persist `product_name_snapshot` from the display span after trim and whitespace collapse, keeping accents and casing. Resolve with `normalize_product_name` of that span and do not store the lookup string. Keep the workflow class name
- [x] 6.3 Add `SALE-005` for a complete free concept. For gram or kilogram also require a per-kilogram basis and clarify with `price_basis_required` when it is missing. Keep catalog price mismatch on `CAT-001`, not `SALE-005`
- [x] 6.4 Set success text to `Agregué 2 bolsas de hielo · $36.00` for that case, and leave the Zanahoria success sentence unchanged
- [x] 6.5 On a direct `free_concept` call, treat `concept_name` as display text. Normalize it only for the catalog safety check. Unique or ambiguous resolution still refuses the free-concept row

## 7. Audit and outbox

- [x] 7.1 Add `source_type` and nullable `product_id` to the `sale.add_item@1` audit payload and to `sale.item.added`, without a new event type or a guessed product id
- [x] 7.2 Keep catalog idempotency hashes unchanged and append `|unit_price` only for a free-concept hash, still under `lumo.message.add_sale_item`
- [x] 7.3 Do not reserve an idempotency key on a clarification turn, including a catalog price mismatch and a missing mass basis

## 8. Generative UI

- [x] 8.1 Compose `sale_item_added@1`, `sale_summary@1`, and `sale_confirmed@1` with `product_name` set to the snapshot and without `source_type`, a badge, or a new action
- [x] 8.2 Add Flutter widget coverage that a free-concept payload shows the server name and total exactly, including `Café Orgánico`, and does not lowercase it or show "Concepto libre" or a save-to-catalog control

## 9. Regression

- [x] 9.1 Keep `900gr zanahoria`, `2 galletas A`, `900 zanahoria` then `gr`, and ambiguous zanahoria on the catalog path. `900gr tomate a 20` stores catalog `20.00`. `900gr tomate a 30` clarifies and writes nothing
- [x] 9.2 Cover acceptance flows for priced bags, `2 bolsas de hielo a 18` as per package, pastel, missing price, price follow-up, unsupported unit, mixed totalize, and cash, card, and transfer commit
- [x] 9.3 Cover same-key replay, a second new-key utterance, post-close commit refusal, and no new `Product` row
- [x] 9.4 Cover `500g de hielo a 40` writing nothing, `500g de hielo a 40 por kilo` totaling `20.00`, then "por kilo" adding exactly one line, `sí` not completing that basis, a model price absent from the user text not persisting, and a catalog mismatch creating neither a free concept nor an idempotency row
- [x] 9.5 Cover "2 bolsas de hielo a 18" snapshot `bolsas de hielo`, "1 Café Orgánico 50" snapshot and card `Café Orgánico` with lookup `cafe organico`, "500g de Café Molido a 240 por kilo" snapshot `Café Molido`, and a unique catalog match for `cafe organico` staying on the catalog path

## 10. Migration and RLS acceptance

- [x] 10.1 Test upgrade from `0007` backfills `catalog`, downgrade aborts when a free-concept row exists, and downgrade succeeds when none exist
- [x] 10.2 Test the composite foreign key rejects a cross-tenant `product_id`, and RLS hides another business's free-concept line
- [x] 10.3 Confirm a confirmed free-concept sale is included in the operational-day summary and the closing snapshot, and that commit on a closed day still writes nothing

## 11. ADR guard

- [x] 11.1 Follow `docs/adr/ADR-020-noncatalog-sale-lines.md` during implementation and do not edit ADR-015 through ADR-019
