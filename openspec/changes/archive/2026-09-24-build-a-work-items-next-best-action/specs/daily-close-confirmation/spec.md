## ADDED Requirements

### Requirement: Successful close resolves open Daily Close WorkItems
In the same transaction that inserts the `ClosingSnapshot` and sets the day to `closed`, `closing.confirm@1` MUST resolve the one open WorkItem for that day with `resolution_code=day_closed`, `resolution_actor_type=business`, and the confirmer's actor id. It MUST NOT insert a WorkItem, a `NextBestAction` row, or an OutcomeRun. A short or over day MUST be closable while its only open row is `cash_difference_review`. `balanced`, `short`, and `over` MUST remain closable. `not_counted` MUST still clarify with `cash_count_required` and MUST NOT close. A clarify or stale confirmation MUST NOT resolve WorkItems by itself. A same-key replay and a different-key read-back of an already closed day MUST NOT resolve rows again and MUST NOT insert a second snapshot.

#### Scenario: Short close still commits and clears active work
- **WHEN** expected cash is `22.50`, the current count is `20.00`, the only open Daily Close WorkItem is `cash_difference_review`, and the actor confirms with a matching token
- **THEN** the snapshot MUST store `cash_difference` `-2.50` and `cash_status=short`, the day MUST be `closed`, that difference row MUST be `resolved` with `resolution_code=day_closed` and `resolution_actor_type=business`, and no `close_confirmation_required` row needs to have existed or be inserted

#### Scenario: Not counted still cannot close
- **WHEN** the actor confirms and no current `CashCount` exists
- **THEN** the response MUST clarify with `cash_count_required`, the day MUST stay `open`, and no snapshot MUST be written

#### Scenario: Already closed read-back does not rewrite WorkItems
- **WHEN** the day is already `closed` and a new confirm key returns the existing snapshot
- **THEN** no additional WorkItem resolve audit MUST be written for that read-back
