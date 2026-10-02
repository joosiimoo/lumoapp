## Context

Carrota final acceptance recorded five non-blocking UX findings. Sale parsing already supports a catalog price override, but only as two turns: a grounded price that differs from `Product.current_price` asks for a reason, and the next message is that reason. `parse_sale_utterance` treats a trailing `por …` as part of the product span unless it is a kilogram basis (`por kilo`, `por kg`, `por kilogramo`). `1 galleta A a 10 por promoción` therefore misses Galleta A (`current_price` `12.00` per unit in the Carrota seed) and can persist a free concept named from the whole phrase.

Item removal already deletes the line and disables the historical card, but the server copy is `Artículo quitado…` or `Quité el último artículo…` and the card does not show `Quitado`. Inicio keeps the operational summary outside the transcript list, yet acceptance still saw overlap or crowding while scrolling. The Inicio page is rebuilt on tab change, so the transcript scroll offset returns to the oldest turn. Transcript turns have no clock time. User bubbles are specified without a timestamp in `docs/LUMO_DESIGN_SYSTEM_v1.0.md` §4.6; memory cards already use a 12px muted `HH:MM` (§4.16).

Constraints: no product-scope expansion; no onboarding, Daily Close, Memoria, or export edits; no migration; backend changes only for the inline catalog reason; Flutter does not calculate money; no new tool or Generative UI version.

## Goals / Non-Goals

**Goals:**

- Complete one catalog override when the same utterance names a unique catalog product, a grounded price, and an inline `por {motivo}` reason.
- Name the removed product in the confirmation and show `Quitado` on the historical card.
- Keep the operational summary and the transcript from overlapping during scroll.
- Show the latest Inicio activity when the merchant returns to the tab.
- Show `HH:MM` on Inicio assistant events and cards.

**Non-Goals:**

- A general reason grammar (`porque`, `motivo:`, percentages, discounts).
- Changing the two-step question when no inline reason is present.
- Server copy, schema, or API fields for remove, scroll, overlap, or timestamps.
- Onboarding, Daily Close, Memoria, exports, Hoy, or a visual redesign.

## Decisions

1. **Inline reason is only `por {motivo}` after the grounded price.**
   The clause is the remainder after `por`, once quantity, unit, product span, optional `cada uno`/`cada una`, and an optional kilogram basis are removed. It uses the existing `normalize_override_reason` (trim, collapse whitespace, keep accents and casing, reject blank and over-200 without truncation). Kilogram basis phrases stay basis markers and are not reasons. `porque es promoción` is out of scope.
   Alternative considered: treat any text after the amount as a reason. Rejected because it would swallow new sale utterances and basis follow-ups.

2. **Strip that clause before catalog resolution, then reuse the existing override commit.**
   Resolution runs on the cleaned span (`galleta A`), not the whole phrase. A unique match whose grounded price differs, plus a valid inline reason, takes the current reason-turn write: lock the product, snapshot `current_price`, store the charged price and reason, one `SaleItem`, existing idempotency hash that already includes the reason. No pending question remains. No migration and no new column. `Product.current_price` does not change. Count-product unit completion for Galleta A stays as it is today, so this phrase must not add a unit question.
   Alternative considered: ask for the reason even when `por promoción` is present. Rejected because that is the acceptance failure mode.

3. **A price difference without an inline reason still asks and writes nothing.**
   `2 galletas A a 10` stays on the current pending `catalog_price_override` path. An over-long inline reason writes nothing, does not create a free concept, replies `Ese motivo es demasiado largo.`, and MUST leave `catalog_price_override` pending with the resolved product, quantity, unit, grounded override price, and observed catalog price, and without that over-long text as the reason. A later valid reason message completes the override without repeating the sale utterance. An empty `por` is not a reason and asks.

4. **Free-concept names lose the same tail and still store no reason.**
   If the cleaned span matches nothing, the snapshot is the cleaned span. `price_override_reason` stays NULL. The whole original phrase is not a snapshot. This is the same parser change required so Galleta A can match; it is not a new free-concept feature.
   Alternative considered: strip the tail only after a unique catalog match. Rejected because the match never happens while the tail is still in the query.

5. **Remove confirmation and `Quitado` are Flutter presentation of data already on the card.**
   The visible confirmation includes the removed line's `product_name` from the `sale_item_added@1` or `sale_summary@1` payload that owned the `sale.remove_item@1` action. Remaining count and total stay the server values in the remove response. Flutter does not recompute them and does not add an API field. The historical card or row shows the label `Quitado` and no enabled `Quitar`. A later server summary remains the actionable card. A failed remove does not show `Quitado`.
   Alternative considered: change `remove_sale_item` copy to include the name. Rejected because the product name is already on the card and this change forbids backend work beyond the inline reason.

6. **Operational summary and transcript are non-overlapping regions.**
   The summary stays fixed above the transcript. Scrolling the transcript does not move the summary and does not paint cards through it. At least 12px separates the summary's bottom edge from transcript content. The header stays compact and is not a dashboard. No new Generative UI component.
   Alternative considered: put the summary inside the scrolling list and pin it. Rejected because the current requirement is a region outside the transcript, and pinning inside the list is what crowded the two regions.

7. **Returning to Inicio shows the latest turns, not the first turn.**
   Tab changes rebuild Inicio, which resets scroll to the top. On becoming visible, and when a new turn is appended while Inicio is visible, the transcript viewport shows the most recent turns. Earlier turns remain in the list. The operational header still refreshes from the today GET and stays at the top. This does not restore an arbitrary mid-list offset from the previous visit.
   Alternative considered: preserve the exact previous offset. Rejected because the acceptance failure is landing on the start of the transcript, and "actividad reciente" is the end of the list.

8. **Event time is the client append time, formatted in the session timezone.**
   Assistant turns and generated cards show a muted 12px `HH:MM` caption. The zone is the authenticated session `timezone` already on the session payload (`America/Mexico_City` for Carrota). If that value is absent, use the device zone. User bubbles stay without a timestamp (§4.6). The clock is not persisted, not sent as a domain fact, and not shown on Memoria.
   Alternative considered: add `occurred_at` to message responses. Rejected because the transcript is in-memory and this change avoids backend work for timestamps.

9. **No ADR.**
   Parsing stays in the sale utterance domain. Layout stays in the Flutter shell. No new architectural boundary, registry entry, or infrastructure.

## Risks / Trade-offs

- [Risk] Merchants phrase the reason as `porque es promoción` or `motivo promoción` and still get the two-step question or a bad span → Mitigation: this change only accepts `por {motivo}`. The residual phrase is called out before implementation and is not silently expanded.
- [Risk] Unknown products that end in `por promoción` lose that tail from the snapshot and do not store it as a reason → Mitigation: required so catalog lookup sees the product. Free-concept rows still have a null reason. No new persistence.
- [Risk] `Quitado` and the product name exist only in the in-memory transcript → Mitigation: the transcript is already in-memory. App restart does not gain a new history gap.
- [Risk] Session `timezone` is missing on the home screen, so `HH:MM` follows the device clock → Mitigation: use the session field when present; do not add an API field in this change.
- [Risk] The overlap seen in acceptance was the composer blur rather than the operational summary → Mitigation: the requirement names the summary and the transcript. Composer and tab bar treatment stay unchanged unless a widget test shows they are the intersecting regions.
- [Risk] Same-turn completion and the two-step question diverge in idempotency → Mitigation: the writing turn uses the existing override completion hash, which already includes the normalized reason. The ask turn still reserves nothing.

## Migration Plan

No Alembic revision. Deploy the parser with the application that completes an inline reason. Rolling back that application restores the previous parse. Flutter layout, `Quitado`, scroll, and timestamps can ship in the same mobile build and do not depend on a schema change. No data backfill.

## Open Questions

None that block implementation. The reason grammar, the client-owned remove label, the return-to-latest scroll, and the session-timezone clock are decided above. Residual phrase coverage (`porque`, `motivo:`) stays out of scope unless the pilot asks for it in a later change.
