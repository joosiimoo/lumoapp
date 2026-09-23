## Context

Archived Build A already registers `sale.commit@1`, `closing.prepare@1`, and `closing.confirm@1`, and Flutter renders `sale_summary@1`, `sale_confirmed@1`, `daily_close_preparation@1`, `daily_close_confirmed@1`, and `operational_day_summary@1`. `GenerativeUIAction` (`action_id`, optional `option_id`, `context_token`, `idempotency_key`) is part of the versioned envelope in `backend/app/agent/generative_ui.py`. Every composer passes `actions=[]`. Flutter parses actions and never executes them.

The only agent route is `POST /api/v1/lumo/messages` (`message` required, `conversation_id`, `client_context.confirmation_token`, header `Idempotency-Key`). Architecture §6 and SRS §8.3 already name one generic `POST /api/v1/lumo/actions`. It is not implemented. There is no per-button route and no client pattern that turns a tap into a hidden phrase.

Card widgets currently paint `fallback_text` above the card, so the stream shows the sentence twice. Inicio does not also paint `response.text` when `ui` is non-empty. `sale_confirmed@1.data.items` already exists; the card shows a count instead of the lines. Preparation data has `sale_count` and cash fields, and deliberately omits `gross_sales_total` (ADR-017). `request_close_text` mentions gross; the card does not. The close JWT stays in `data.confirmation_token` and is echoed on the next message. ADR-015, ADR-016, ADR-017, and ADR-018 stay as written.

## Goals / Non-Goals

### Goals

- Conversation remains the control plane. A card shows current operational state. A tap is a second modality for a next step the server already recognizes.
- Taps and the approved phrases share one workflow, one policy check, one idempotency operation type, and one audit/outbox event.
- Flutter submits typed action fields only. The server resolves the sale, the day, the amounts, and whether the action is legal.
- Recognized cards stop repeating a sentence they already display. `fallback_text` stays in the payload.

### Non-Goals

Same list as the proposal. No migration. No new domain entity or workflow state. No inventory, card authorization, mixed payment, undo, notes, analytics, Hoy redesign, reopen, WorkItems, NBA, OutcomeRuns, or export.

## Decisions

### 1. Action transport

Implement the architecture endpoint. Do not translate a tap into `"efectivo"` or `"cerrar el día"`.

`POST /api/v1/lumo/actions`

```json
{
  "action_id": "sale.pay.cash@1",
  "option_id": null,
  "context_token": "<server-issued token>",
  "conversation_id": "<Inicio uuid>",
  "idempotency_key": "<server-issued uuid>"
}
```

Headers: `Authorization`, `Idempotency-Key` (must equal `idempotency_key`), `X-Correlation-ID`.

`payload`, if present, MUST be `{}`. Any amount, payment method, `operational_day_id`, snapshot id, cash figure, or other property is a validation error and MUST NOT mutate. `extra` fields are forbidden. `option_id` MUST be null in this slice; the action id is the only selector.

The response body is the existing message shape: `message_id`, `status`, `text`, `ui`, `correlation_id`. No `outcome` and no `next_best_action`.

The handler authenticates, derives `TenantContext` from the session, and calls one new orchestrator method `handle_ui_action`. That method MUST NOT call `LLMProvider.interpret`. It looks up a closed `UiActionRegistry`, verifies the context token, builds the same in-process decision the typed path would use, and calls the existing `_handle_commit`, `_handle_request_close`, or `_handle_confirm_close`. Unknown action ids return a non-mutating clarification and an empty `ui`. They are not passed to `ToolRegistry`.

`POST /api/v1/lumo/messages` is unchanged.

Directory: action catalog and token helpers live under `backend/app/agent/` and `backend/app/application/`. The route stays in `backend/app/api/routes/lumo.py`. No new domain package. Flutter dispatcher stays in `mobile/lib/app/lumo_app.dart` and `mobile/lib/lumo/generative_ui/`.

### 2. Contract version stays 1

`actions` is already a required envelope field and defaults to empty. Data schemas do not gain required fields. Empty `actions` remains valid. Old clients that ignore `actions` still render version 1 data and `fallback_text`, and typed phrases still work. A version 2 would make today's renderer drop the card and show only `fallback_text`.

This change revises the requirements that currently say `actions` MUST be empty and that Flutter MUST NOT show payment or close controls. That is an intentional spec change, not a silent wire break.

### 3. Action ids

Closed catalog. Version lives in the id because `GenerativeUIAction` has no version field.

| `action_id` | Label Flutter may show | Dispatch |
|---|---|---|
| `sale.pay.cash@1` | Efectivo | `commit_sale` / `sale.commit@1`, method `cash` |
| `sale.pay.card@1` | Tarjeta | method `card` |
| `sale.pay.transfer@1` | Transferencia | method `transfer` |
| `closing.request@1` | Cerrar el día | existing `request_close` |
| `closing.confirm@1` | Confirmar cierre | existing `confirm_close` / tool `closing.confirm@1` |

`closing.confirm@1` equals the tool id on purpose so audit can correlate the tap with the tool. It is registered only in `UiActionRegistry`, not as a new tool. The dispatcher MUST resolve the action catalog first.

`option_id` is always null. Labels are a closed Flutter map for these five ids. The server MUST NOT trust a label. Any other id is not rendered and not executed.

### 4. Action context

No client-supplied totals, payment amount, day id, snapshot id, or cash figures.

`closing.request@1` uses an HS256 JWT, `iss=lumo`, `typ=ui_action`, signed with `DEV_TOKEN_SECRET`, `exp = iat + 15 minutes`. Claims: `action_id`, `business_id`, `actor_id`, `conversation_id`. No amounts, no `sale_session_id`, and no `operational_day_id`. It stays a read that recomputes the current preparation.

`sale.pay.cash@1`, `sale.pay.card@1`, and `sale.pay.transfer@1` use the same `typ=ui_action` JWT with one added claim: `sale_session_id`, the persisted session that was `ready_to_charge` when the card was composed. Full payment claims: `iss`, `typ`, `action_id`, `business_id`, `actor_id`, `conversation_id`, `sale_session_id`, `iat`, `exp`. No amount, total, payment amount, payment method, `operational_day_id`, or product rows. The method still comes only from the action id. `sale_session_id` is not a body field. A body that contains it, or any other domain id, is a validation error and writes nothing.

Envelope checks, before any idempotency or state lookup: signature, `typ=ui_action`, expiry, `iss=lumo`, action id match, tenant match, actor match, conversation match, and, for the three payment ids, a present `sale_session_id`. A missing claim, a tampered token, or a tenant, actor, or conversation mismatch writes nothing and does not interpret a phrase.

`closing.confirm@1` uses the existing `typ=closing_confirm` JWT as `context_token`. Do not wrap it and do not add `sale_session_id`. `ConfirmDailyClose` remains the only verifier. Claims, fingerprint, and 15-minute life stay as ADR-018.

The payment handler MUST select the session named by the token. It MUST NOT treat the conversation's newest `ready_to_charge` session as the target. Amounts still come from that session's persisted rows. `CommitSaleSession` runs only when the locked active session id equals `token.sale_session_id` and that row is `ready_to_charge`. The check happens under the session lock and before `idempotency.begin`.

### 5. Tap idempotency

The composer puts a new UUIDv7 in `idempotency_key` on every emitted action. Flutter sends that value as the header and the body field and MUST NOT mint a replacement. A mismatch is a validation error with no mutation.

- `sale.pay.*@1` uses operation type `lumo.message.commit_sale`. The request hash input is `action_id|conversation_id|commit|payment_method|sale_session_id`, not a phrase.
- `closing.confirm@1` uses `lumo.message.confirm_close`. The hash input is `action_id|conversation_id|token`.
- Payment handling order is fixed:
  1. Validate the request envelope.
  2. Verify the JWT.
  3. Compute the request hash, including `sale_session_id`.
  4. Peek idempotency.
  5. A completed same key and same hash returns the stored body immediately. This is an exact replay, including a historical `sale_confirmed@1`, and it is not a fresh current-state read-back.
  6. Load the token-bound `SaleSession`.
  7. Inspect whether a newer `open` or `ready_to_charge` session exists in that conversation.
  8. Decide: current commit, confirmed read-back, or `ui_action_stale`.
  9. Only the current commit may reach `idempotency.begin`.
- Same key and a different hash, including a different `sale_session_id`, is `IDEMPOTENCY_CONFLICT` and writes nothing.
- A fresh attempt whose bound session is `confirmed`, and no newer `open` or `ready_to_charge` session exists, returns that session's `sale_confirmed@1` as the existing non-mutating read-back. No payment, audit, outbox, or idempotency row.
- A fresh attempt whose bound session is `confirmed`, and a newer `open` or `ready_to_charge` session exists, returns reason `ui_action_stale`, text `Esta acción ya no aplica a la venta en curso.`, and `ui: []`. It does not compose that historical `sale_confirmed@1` and does not touch the newer session. No payment, audit, outbox, or idempotency reservation.
- The same stale result applies when the token session is missing, is `open` but is not the locked actionable sale, is `ready_to_charge` but is not the locked actionable sale, or is any other signed state that is not an exact replay, the current `ready_to_charge` target, or a confirmed read-back with no newer active sale. The handler does not retarget the action.
- Two in-flight taps of the same action share the key, so the existing peek/begin path cannot create a second payment or snapshot.
- `closing.request@1` stays a read. It does not insert an idempotency row, matching typed `request_close`. A repeated request may issue another token. Neither request closes the day. The client in-flight guard sends one HTTP call per tap gesture; a transport retry reuses the key.

Typed phrases keep client-generated message keys and hash the phrase. They do not require a `ui_action` token. Sharing one key across a phrase and a tap is an `IDEMPOTENCY_CONFLICT` because the hashes differ. That is two different requests, not a second domain path.

Unused-button example. Sale A is totalized and its `sale_summary@1` signs `sale.pay.cash@1` to Sale A's id. The user confirms Sale A by typing `efectivo`, so Sale A's button key is never completed. Sale B is then opened and totalized in the same conversation. Tapping Sale A's button peeks, finds no completed record, sees Sale A `confirmed` and Sale B `ready_to_charge`, and returns `ui_action_stale` with text `Esta acción ya no aplica a la venta en curso.` and `ui: []`. Sale A stays confirmed with its one payment. Sale B stays `ready_to_charge` with no payment. No idempotency row is inserted. Repeating that unused key repeats the same stale result, because nothing was stored.

Exact-replay example. Sale A is confirmed by its own `sale.pay.cash@1`, so that key, hash, and body are stored. Sale B is later `ready_to_charge` in the same conversation. Retrying that exact request returns the stored Sale A body, including `sale_confirmed@1`, before the newer-session check. Sale B is untouched. That response is a replay of a completed request, not a fresh current-state read-back.

### 6. Confirmation token location

One JWT is issued per confirmable `request_close`.

Canonical button carrier: `actions[].context_token` on the single `closing.confirm@1` action.

Compatibility mirror: `data.confirmation_token` MUST be that same string. The composer MUST refuse the contract if they differ. When no confirm action is emitted, `data.confirmation_token` is null and no confirm action exists.

Typed `confirmar cierre` still sends `client_context.confirmation_token`. Flutter copies it from the confirm action's `context_token` (the mirror must match). The text path still ignores a model-supplied token. The action path passes `context_token` into the same `confirmation_token` argument. Neither copy is rendered.

### 7. Typed and tapped equivalence

| Input | Handler | Durable result |
|---|---|---|
| `efectivo` or `sale.pay.cash@1` | `CommitSaleSession` | one `Payment` method `cash`, `sale_confirmed@1` |
| `tarjeta` / `sale.pay.card@1` | same | method `card` |
| `transferencia` / `sale.pay.transfer@1` | same | method `transfer` |
| `cerrar el día` or `closing.request@1` | `request_close` | day stays `open`, token issued, no snapshot |
| `confirmar cierre` or `closing.confirm@1` | `closing.confirm@1` | one snapshot, day `closed` |

Audit action and outbox event names stay `sale.commit@1` / `sale.confirmed` / `payment.recorded` and `closing.confirm@1` / `closing.confirmed`. The action path MAY add `ui_action_id` to the existing audit JSON. It MUST NOT add a table, event type, or domain state. Typed audit payloads stay as they are.

### 8. When actions are emitted

The backend decides. Flutter MUST NOT invent a legal action.

- `sale_summary@1` for `ready_to_charge`: exactly the three `sale.pay.*@1` actions, in cash, card, transfer order.
- `sale_confirmed@1`, `sale_item_added@1`, `operational_day_summary@1`, `daily_close_confirmed@1`: `actions` empty.
- `daily_close_preparation@1` with an open day, a current `CashCount`, and `cash_status` of `balanced`, `short`, or `over`, and a null token: exactly `closing.request@1`.
- That same preparation after `request_close` has issued a token: exactly `closing.confirm@1`. Do not also emit request-close. Do not call `closing.confirm@1` from the request action.
- `not_counted`, no day, or no current count: `actions` empty.
- Closed day: `daily_close_confirmed@1` with empty actions. No reopen control.

Short and over still receive request-close, because explicit confirmation is already allowed.

### 9. Duplicate prose

Do not suppress every assistant sentence.

Omit the visible prose block only when all of these hold:

1. `ui` has one contract the renderer knows at version 1.
2. `text.strip()` equals that contract's `fallback_text.strip()`.
3. The component is `sale_item_added`, `sale_summary`, `sale_confirmed`, `operational_day_summary`, or `daily_close_confirmed`, OR it is `daily_close_preparation` and `fallback_text` starts with `Cierre `.

That last prefix is `close_preparation_text`, whose facts the cash card already shows.

Otherwise:

- Known card and any other `text`: show that prose and the card. This keeps `El cierre está preparado…` (it includes gross, which the card does not), the stale-confirmation warning, and the not-started or cash-required sentences.
- Empty `ui`: show `text` only. Clarification, unsupported input, and errors stay prose.
- Unknown component or version: show `fallback_text` only and run no action.

`fallback_text` remains in JSON. The card SHOULD expose it as an accessibility summary so hiding the paragraph does not drop the sentence from assistive tech. Do not paint it as a second visible block when the rule says card only.

### 10. Sale summary and sale confirmed presentation

`sale_summary@1` card, server strings only:

- Chip `Lista para cobrar`.
- Each `data.items` row: name, `quantity_normalized` plus display unit, unit price, server `line_total`.
- One total row from `data.total`. No client sum.
- When the three payment actions are present, the static prompt `¿Cómo pagó?` and the three pills. The prompt is chrome for those actions, not a second assistant message.
- No authorization field, mixed payment, Registrar, or Corregir.

`sale_confirmed@1` card:

- Chip `Venta registrada`.
- Every `data.items` row, same line pattern. Order is the server array.
- One total from `data.total`.
- Payment row labeled `Pago` with `Efectivo`, `Tarjeta`, or `Transferencia`. Do not render a second amount; the contract already requires `payment.amount` to equal `total`.
- No undo, detail navigation, inventory line, or payment actions.

### 11. Close presentation

Preparation card uses only current fields. Do not add `gross_sales_total`. `sale_count` MAY be shown as `1 venta` or `N ventas` because it is already in the payload.

- `balanced`: calm chip `Caja cuadrada`. Difference is the server zero amount.
- `short`: chip `Faltante`. Show the server signed difference (the amount already begins with `-`).
- `over`: chip `Sobrante`. Prefix `+` to the formatted positive server amount for display only. Do not recompute it.
- Counted open, no token: primary button `Cerrar el día`.
- Token present: primary button `Confirmar cierre` only.
- `not_counted`: `Falta contar efectivo`, expected cash, no counted amount, no difference, no amount field, no close button. The composer remains how the merchant says `tengo 3150 en caja`.

Confirmed card: check treatment, `Cierre confirmado`, server date, `sale_count`, `gross_sales_total`, expected, counted, signed difference, status word, `closed_at`. Snapshot values only. No reopen, comparison, or top product.

`operational_day_summary@1` may use the same gutter, radius, chip, and type ramp. It stays a compact Inicio card: date, count, gross, three methods, and `Cerrado` only when `status` is `closed`. No chart and no Hoy work.

Visual language stays the design system: warm canvas, forest green, soft white 24px cards, soft shadow, Lumo mark gutter, Inter / Instrument Serif, user bubbles on the right, structured artifacts unbubbled, existing bottom navigation and sticky composer.

### 12. Flutter loading, history, and failure

A tap does not append a user bubble and does not write a phrase into the composer. The stream keeps the source card and, on success, appends the assistant turn from the response. There is no conversation-message table; the durable record is the existing sale, payment, snapshot, audit, and outbox rows.

On tap: that card's actions disable, the tapped control shows a loading state, and a second tap on that card MUST NOT start another request. That disablement is a UX optimization only. Correctness does not depend on it. A rebuilt widget, a restored stream, or a still-enabled old card can still submit the original action, and the server binding rejects any effect on a different sale. Do not swap in a confirmed or closed card before the HTTP success. The composer stays available; a phrase sent during the flight is a different idempotency key and still hits the same row lock and read-back rules. A typed phrase does not carry a UI-action token.

On transport failure: leave the source card and its server key in place, show the existing non-destructive toast, and let a retry send that same key. Do not clear the composer because of an action failure.

On `ui_action_stale`: keep the source card, leave its actions disabled in the current stream, show `Esta acción ya no aplica a la venta en curso.` as assistant prose, and append neither a user bubble nor a `sale_confirmed@1` card.

After a successful commit, actions on the source card stay disabled. A later exact retry of a completed key replays the stored body. A fresh unused key follows the stale or read-back rule above and MUST NOT create a second payment or snapshot.

### 13. API and database

API change: add `POST /api/v1/lumo/actions` only. Message schema unchanged.

Database change: none. No Alembic revision. `ui_action` tokens are stateless JWTs, same secret as the close token.

### 14. ADR-019

Propose `docs/adr/ADR-019-generative-ui-actions.md`. Status Proposed until this change is implemented. Do not edit ADR-015 through ADR-018.

Decision to record: the conversation is the control plane; the structured card is the operational state; taps are closed versioned actions executed only by the backend through existing tools; payment tokens are bound to the emitting `sale_session_id`; typed and tapped inputs are equivalent; idempotency peek precedes stale checks; Flutter disablement is not authoritative; duplicate prose is suppressed only by the rule in decision 9; unknown actions fail closed; version 1 stays.

## Risks / Trade-offs

- Request-close prose still appears beside the card so gross is not lost. Adding gross to the card was rejected to keep the preparation contract cash-focused.
- `closing.request@1` is not idempotent-persisted. Two successful calls can mint two tokens. The client sends one, and confirm still needs a matching fingerprint, so this cannot double-close.
- A phrase and a tap use different request hashes. They converge on domain state, not on one idempotency row.
- `conversation_id` is reused across sales. Payment correctness is the signed `sale_session_id`, not Flutter's disabled buttons. A fresh confirmed action read-backs only when no newer active sale exists. Otherwise it is `ui_action_stale` and does not paint a historical confirmed card. Exact replay is the exception and returns the stored body.
- Old Flutter builds ignore new actions and keep today's prose-plus-card layout. That is compatible and simply lacks buttons.

## Migration Plan

No data migration. Ship the route, the five action ids, and the Flutter dispatcher together. Empty `actions` remains valid during rollout. Rollback is removing the route and emitting `actions: []` again; persisted sales and snapshots do not depend on the new route.

## Open Questions

None. The eighteen review points in the change request are decided above.
