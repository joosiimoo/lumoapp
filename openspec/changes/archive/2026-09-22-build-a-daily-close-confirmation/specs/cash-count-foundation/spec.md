## ADDED Requirements

### Requirement: A closed day refuses another cash count
`closing.submit_cash_count@1` MUST lock today's OperationalDay `FOR UPDATE` before appending a count. When that row's `status` is `closed`, the write MUST clarify with reason `operational_day_closed` and the text `La jornada de hoy ya está cerrada. No puedo cambiar el conteo.` It MUST NOT insert a `CashCount`, MUST NOT set `superseded_by_id` on the current row, MUST NOT change the snapshot, and MUST NOT write audit, outbox, or idempotency. The current count MUST remain the count referenced by the `ClosingSnapshot`.

#### Scenario: Recount after close
- **WHEN** today's day is `closed` with a current count of `22.50` and the actor posts `tengo 20 en caja`
- **THEN** the response MUST clarify with `operational_day_closed`, the `22.50` row MUST still have `superseded_by_id` NULL, and no new cash-count, audit, or outbox row MUST exist
