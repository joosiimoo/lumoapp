# ADR-027: Business Stream is a dedicated today projection

- Status: Accepted
- Date: 2026-09-26

## Decision

Inicio's operator surface is one deterministic read, `GET /api/v1/business-stream/today`. The server composes it from today's OperationalDay, the existing Daily Close predicates, the current CashCount, the live confirmed-sales summary, the ClosingSnapshot when the day is closed, and the recorded-operations declaration. Flutter renders that payload. It does not assemble the surface from other endpoints and it does not choose the state.

The route is not an extension of `GET /api/v1/operational-days/current/next-best-action`. That route stays the Hoy next-step read: it is null when there is no day, no confirmed sales, or the day is closed, and it does not carry sales totals or source coverage. The new route also does not replace `operational_day.summary@1`, `closing.prepare@1`, or `memory.business_facts@1`.

No Generative UI component is registered. Sale and close cards stay conversation artifacts. The cash-count control only focuses the existing composer. For a cash difference and for ready-to-close, the panel label is `Revisar cierre` and the tap posts `cerrar el día` to `POST /api/v1/lumo/messages`. `primary_action.action_id` is null. `closing.request@1` remains the existing card action from `generative-ui-actions`; this read does not repeat it as metadata. `closing.confirm@1` stays on the conversation card that follows that phrase. The GET does not mint a confirmation token.

The read does not create an OperationalDay, reconcile WorkItems, or write an OutcomeRun, audit, outbox, idempotency, coverage, or business event. Tenant scope stays the session. There is no migration.

ADR-016 through ADR-026 are unchanged.

## Consequences

Opening Inicio can show today's responsibility without a question and without an LLM. Hoy's next-step contract stays stable. A skipped WorkItem row is not repaired by the read; the visible state still follows the same pure Daily Close predicate the write path already uses. Closed money comes from the snapshot. The merchant sentence stays limited to operations registered in Lumo.
