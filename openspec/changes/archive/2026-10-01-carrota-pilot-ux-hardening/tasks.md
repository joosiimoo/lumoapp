## 1. Inline catalog reason

- [x] 1.1 Strip a trailing non-basis `por {motivo}` before catalog resolution, and keep kilogram basis phrases as basis markers
- [x] 1.2 Complete one catalog override on the same turn when the cleaned span uniquely matches, the grounded price differs, and the inline reason is valid, using the existing lock, snapshot, and reason idempotency hash
- [x] 1.3 Keep `2 galletas A a 10` on the ask-and-write-nothing path; reject an over-long inline reason without a SaleItem, free-concept, or truncation; leave `catalog_price_override` pending without reason; and let a later valid reason complete it
- [x] 1.4 When resolution is `none`, persist the cleaned span as the free-concept snapshot with `price_override_reason` NULL

## 2. Parser tests

- [x] 2.1 Add a backend test that `1 galleta A a 10 por promoción` persists Galleta A at snapshot `12.00`, charged `10.00`, reason `promoción`, and line total `10.00`, with no free-concept row and no pending override
- [x] 2.2 Add a backend test that the whole phrase is not `product_name_snapshot`, that `por kilo` is not stored as a reason, and that an unknown `1 hielo suelto a 10 por promoción` snapshots `hielo suelto` with a null reason
- [x] 2.3 Add a scripted-interpreter test that the promotion phrase is `add_sale_item` for `galleta A` and not a free-concept name

## 3. Remove confirmation

- [x] 3.1 After a successful remove from `sale_item_added@1`, show a confirmation that includes that card's `product_name` and mark the historical card `Quitado` without an enabled `Quitar`
- [x] 3.2 After a successful remove from `sale_summary@1`, name the removed row, mark that row `Quitado`, and disable `Quitar` on the historical summary while leaving the next server summary actionable
- [x] 3.3 Leave the card unmarked when remove fails, and do not recompute remaining count or total

## 4. Inicio transcript

- [x] 4.1 Separate the operational summary and the transcript so scroll does not move or overlap the summary, with at least 12px between them
- [x] 4.2 On return to Inicio, and when a new turn is appended, show the latest transcript turns instead of the oldest turn, while keeping the operational header visible
- [x] 4.3 Show muted 12px `HH:MM` on assistant turns and generated cards using the session timezone when present, and keep user bubbles without a timestamp

## 5. Flutter tests

- [x] 5.1 Add widget tests for named remove confirmation, `Quitado` on the item card and the summary row, and no `Quitado` after a failed remove
- [x] 5.2 Add widget tests that scrolling the transcript does not intersect the operational summary and that returning to Inicio shows the latest card
- [x] 5.3 Add a widget test that a card appended at 14:05 shows `14:05` and the user bubble does not

## 6. Final validation evidence

**Automated (pre-archive):**

- Backend pytest: **435 passed**
- Flutter tests: **117 passed**
- Flutter analyze: **No issues found**
- `openspec validate carrota-pilot-ux-hardening --strict`: **valid**
- Tasks: **16/16** complete

**Operator manual validation:**

- UX-01 inline catalog override: **PASS**
- UX-02 remove confirmation + Quitado: **PASS**
- UX-03 Inicio no-overlap: **PASS**
- UX-04 regreso a actividad reciente: **PASS**
- UX-05 timestamps: **PASS**
