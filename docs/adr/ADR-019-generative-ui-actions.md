# ADR-019: Generative UI actions and structured-artifact-first interaction

- Status: Accepted
- Date: 2026-09-22

## Decision

The conversation stays the control plane. A registered structured card is the operational state the merchant sees. Obvious next steps are closed, versioned actions that Flutter submits and the backend executes. Flutter does not decide legality, does not calculate money, and does not turn a tap into a hidden phrase.

`POST /api/v1/lumo/actions` is the single action route from Architecture §6 and SRS §8.3. It does not call the interpreter. The closed ids are `sale.pay.cash@1`, `sale.pay.card@1`, `sale.pay.transfer@1`, `closing.request@1`, and `closing.confirm@1`. They dispatch into the existing `sale.commit@1`, `request_close`, and `closing.confirm@1` handlers. Typed phrases on `POST /api/v1/lumo/messages` remain valid and reach those same handlers.

Payment and confirm taps use the existing idempotency operation types. The server issues the action key; a retry reuses it, and that replay is checked before any stale-session comparison. `closing.request@1` stays a non-persisting read and does not close the day. Confirm still requires the existing fingerprint-bound `typ=closing_confirm` token, carried as the action `context_token` and mirrored in `data.confirmation_token`. Payment and request actions use a separate `typ=ui_action` token with no amounts. A payment token also carries the emitting `sale_session_id`. The action body does not. The handler confirms only that session. An exact completed replay returns the stored body before any newer-session check. A fresh tap of an already confirmed session read-backs `sale_confirmed@1` only when no newer active sale exists. If a newer `open` or `ready_to_charge` sale exists, that fresh tap is `ui_action_stale` with empty `ui` and does not append the historical confirmed card. Any other session mismatch is also `ui_action_stale` and writes nothing. Flutter disabling old buttons is only a UX aid.

Contracts stay at version 1. `actions` is already on the envelope and remains optional. Unknown components show `fallback_text` and run nothing. Unknown action ids are not executed. Visible assistant prose is omitted only when the card already shows every fact in that sentence, using the component rule in the `build-a-lovable-ux-convergence` design. `fallback_text` stays in the payload.

No new table, tool, domain entity, or workflow state is introduced.

## Consequences

Inicio can offer Efectivo, Tarjeta, Transferencia, Cerrar el día, and Confirmar cierre without a second sale or close path. A payment button stays bound to the sale that rendered it, including when `conversation_id` is reused. Short and over may still proceed to explicit confirmation. Not-counted stays conversational. Preparation does not gain gross sales. Hoy is unchanged. ADR-015, ADR-016, ADR-017, and ADR-018 are not revised.
