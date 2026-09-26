# ADR-025: Source coverage and factual event memory

- Status: Accepted
- Date: 2026-09-25

## Decision

Build A records what Lumo has observed. It does not record that the real-world day is complete.

`operations.source_coverage_records` stores eight columns: `id`, `business_id`, `operational_day_id`, `domain`, `source_type`, `status`, `limitation_code`, and `created_at`. There is no `updated_at`. A row means Lumo observed that domain from that source at least once for that OperationalDay. It does not mean the source is complete, fresh, healthy, or that no sale is missing. Domains are `sales` and `cash_count`. `source_type` is `manual_capture`. `status` is `observed`. `limitation_code` is `only_lumo_registered_operations`. Writes are insert-if-absent. An existing row is never updated. There is no `daily_close` coverage domain.

Recorded-operations completeness is a pure projection over those rows: basis `recorded_operations`, distinct sorted domains, distinct sorted sources, the same limitation, and `merchant_source_declaration` null. Empty coverage still returns that shape. It is not persisted and it has no percentage, score, or complete flag.

`operations.business_events` stores confirmed facts for `sale_confirmed`, `cash_count_recorded`, and `daily_close_completed`. `source_type` is the primary operational data source of the fact, not the writer, workflow, API, or tool. The only value is `manual_capture`: a sale because `Payment.source` is `manual_capture`, a cash count because `CashCount.source` is `manual_capture`, and a close because the close commits Build A facts whose implemented source coverage is `manual_capture`. The close workflow is not a source type. `daily_close_completed` is proved by `source_entity_type=closing_snapshot` and `source_entity_id=ClosingSnapshot.id`. There is no coverage foreign key, no workflow-origin field, and no `outcome_run_id` column. `operational_day_id` is required.

Fact keys are exact. Money values are decimal strings with two fractional digits. `sale_count` is a JSON integer. `occurred_at` is the source fact time: `SaleSession.confirmed_at`, `CashCount.counted_at`, or `ClosingSnapshot.closed_at`. `created_at` is insertion time. Identity is unique on `(business_id, event_type, source_entity_type, source_entity_id)`. A superseding CashCount keeps the previous event and adds one for the new cash count id. Replay does not duplicate. Events are immutable: a `BEFORE UPDATE` trigger rejects every role, and `lumo_app` has `SELECT`, `INSERT`, and `DELETE` only. Product code does not delete events. Delete remains only for the existing tenant reset and test cleanup.

Coverage and events are written in the parent transaction, after OutcomeRun and WorkItem sync and before parent idempotency completes. Sale commit ensures `sales` coverage only. A new CashCount ensures `cash_count` coverage only. Close ensures a missing row when confirmed sales or a current CashCount justify it, then inserts one `daily_close_completed` event whose facts reference the completed OutcomeRun and the ClosingSnapshot. It does not copy the snapshot body or a completeness flag. Failed parent attempts leave no new coverage or event rows.

OutcomeRun schema and evidence are unchanged. `completed` means Daily Close responsibility for operations represented in Lumo was finished. It does not mean every real-world operation was captured. `OutcomeEngine.evaluate` stays pure.

Migration `0012_source_coverage_event_memory` inserts nothing. It does not backfill events. The existing open-today initializer may ensure coverage for today's open day when the facts already exist. It does not insert events, touch closed days, or touch older open days. There is no new audit action, outbox type, idempotency operation, HTTP route, tool, UiAction, or Generative UI component. There is no embedding, vector extension, memory schema, or model prose. Summary text still starts with `Hoy`. Confirmed close text still starts with `Cierre confirmado`.

Both tables use `ENABLE` and `FORCE` row level security with `tenant_isolation`. `lumo_app` and `lumo_admin` stay `NOBYPASSRLS`.

ADR-015 through ADR-024 are unchanged.

## Consequences

Lumo can say which Build A domains it has observed from manual capture, and can keep one immutable fact per confirmed sale, cash count, and close. It still cannot claim that every sale was captured or that the day is fully complete.
