## 1. Action contract and transport

- [x] 1.1 Add `UiActionRegistry` with exactly `sale.pay.cash@1`, `sale.pay.card@1`, `sale.pay.transfer@1`, `closing.request@1`, and `closing.confirm@1`. Do not register those ids on `ToolRegistry`.
- [x] 1.2 Add HS256 `typ=ui_action` issue and verify helpers using `DEV_TOKEN_SECRET` and a 15-minute expiry. `closing.request@1` claims are `action_id`, `business_id`, `actor_id`, and `conversation_id`. The three payment actions add `sale_session_id` and still omit amounts. Reject a payment token that omits that claim.
- [x] 1.3 Add `POST /api/v1/lumo/actions` with the design body, empty-or-absent `payload`, header/body idempotency equality, auth, and the existing message response shape. Leave `POST /api/v1/lumo/messages` unchanged.

## 2. Backend action routing

- [x] 2.1 Add `FoundationOrchestrator.handle_ui_action` that does not call `LLMProvider.interpret`, rejects unknown ids without a tool call, and dispatches the five ids to the existing commit, request-close, and confirm handlers.
- [x] 2.2 Map a current payment action to `CommitSaleSession` only when the locked active session id equals the token `sale_session_id`. Hash `action_id|conversation_id|commit|payment_method|sale_session_id` under `lumo.message.commit_sale`. Order: envelope, JWT, hash, peek, exact completed replay, load the bound session, inspect newer active sessions, then commit, confirmed read-back, or `ui_action_stale`. Only commit calls `idempotency.begin`. A confirmed bound session with no newer active sale read-backs `sale_confirmed@1`. A fresh unused key for a confirmed session while a newer `open` or `ready_to_charge` session exists returns `ui_action_stale` with empty `ui` and writes no payment, audit, outbox, or idempotency row.
- [x] 2.3 Map `closing.request@1` to `request_close` with no confirm call and no idempotency insert. Map `closing.confirm@1` to the confirm workflow using `context_token`, hashed as `action_id|conversation_id|token` under `lumo.message.confirm_close`.
- [x] 2.4 On the action path only, add `ui_action_id` to the existing audit JSON. Do not add an event name, table, or migration.

## 3. Generative UI emission

- [x] 3.1 When composing `sale_summary@1` for `ready_to_charge`, emit the three payment actions with null `option_id`, a `ui_action` token bound to that `data.sale_session_id`, and a new UUIDv7 idempotency key. Keep version `1` and the current data fields. Do not add `sale_session_id` to the action body.
- [x] 3.2 Emit `closing.request@1` on counted open preparation (`balanced`, `short`, `over`, null token). Emit only `closing.confirm@1` after a token is issued, and set `data.confirmation_token` to that same JWT. Emit no actions for not-counted, no day, or no current count.
- [x] 3.3 Keep `actions` empty on `sale_item_added@1`, `sale_confirmed@1`, `operational_day_summary@1`, and `daily_close_confirmed@1`. Refuse the composer if the confirm token and `data.confirmation_token` differ.

## 4. Flutter action dispatcher

- [x] 4.1 Post a recognized tap to `/api/v1/lumo/actions` with the emitted fields and the same `conversation_id`. Do not append a user bubble and do not synthesize a phrase.
- [x] 4.2 Disable that card's actions and show loading on the tapped control until the response. A second tap MUST NOT send. Treat that disablement as UX only; do not rewrite a token toward a later sale. On transport failure, keep the card, toast the existing non-destructive error, and retry with the same server key. On `ui_action_stale`, keep the source card disabled, show the server clarification, and append neither a user bubble nor `sale_confirmed@1`. On success, append the assistant turn and leave the source actions disabled.
- [x] 4.3 Keep typed confirm on `client_context.confirmation_token`, copied from the confirm action `context_token`. If `data.confirmation_token` differs, do not send a token. Never render either token.

## 5. Card presentation

- [x] 5.1 Restyle `sale_summary@1` to the charge-ready hierarchy: chip `Lista para cobrar`, server line rows, server total, and `¿Cómo pagó?` plus Efectivo / Tarjeta / Transferencia only when those actions are present.
- [x] 5.2 Restyle `sale_confirmed@1` to show every server item, one server total, and `Pago` plus the method label. No second amount, undo, or inventory line.
- [x] 5.3 Restyle preparation: `Caja cuadrada`, `Faltante` with the signed server difference, `Sobrante` with a display-only `+`, `Cerrar el día`, then `Confirmar cierre`. Not-counted stays `Falta contar efectivo` with no input and no close button. Do not add gross sales.
- [x] 5.4 Restyle `daily_close_confirmed@1` with the confirmed treatment and the existing snapshot fields, and no reopen control. Align `operational_day_summary@1` to the same card language without a chart or a Hoy change.

## 6. Duplicate prose

- [x] 6.1 Apply the design rule: omit visible prose only for the listed components when `text` equals `fallback_text`, and for preparation only when that text starts with `Cierre `. Otherwise show prose and the card, or prose alone when `ui` is empty.
- [x] 6.2 Expose `fallback_text` as an accessibility summary when the visible paragraph is omitted. Unknown component versions still show `fallback_text` and run nothing.

## 7. ADR and config

- [x] 7.1 Keep `docs/adr/ADR-019-generative-ui-actions.md` aligned with design decision 14. Do not edit ADR-015 through ADR-018. Mark it Accepted only when this change is implemented.
- [x] 7.2 Update `openspec/config.yaml` context so this change is the active UX slice, the action catalog and `POST /api/v1/lumo/actions` are described, and no new tool, table, or domain state is claimed.

## 8. Acceptance tests

- [x] 8.1 Backend: typed `efectivo` and `sale.pay.cash@1` each create one cash payment and `sale_confirmed@1` with empty actions; a double submit of one action key creates one payment; an unknown action writes nothing.
- [x] 8.2 Backend: counted open preparation emits only `closing.request@1`; that action does not close; the follow-up emits only `closing.confirm@1` with matching token fields; confirm creates one snapshot. Short and over still request and confirm. Not-counted and closed emit no close action.
- [x] 8.3 Flutter: payment and close buttons use server labels, loading blocks a second tap, failure keeps the card and the key, a tap does not create a user bubble, the body omits `sale_session_id`, and duplicate `Cierre ` prose is hidden while `El cierre está preparado` stays visible.
- [x] 8.4 Backend payment binding: a current token confirms that sale; an exact completed Sale A key still replays Sale A's stored `sale_confirmed@1` after Sale B exists; an unused Sale A button after typed confirmation of A, while B is `ready_to_charge`, returns `ui_action_stale` with empty `ui` and does not compose Sale A's card; B stays `ready_to_charge` with no payment; A keeps one payment; the stale attempt writes no audit, outbox, or idempotency row; a confirmed sale with no newer active session still read-backs `sale_confirmed@1`; a tampered or mismatched token writes nothing. Server tests MUST pass with the client disablement absent.
