# Acceptance notes

Manual acceptance PASS:

- cash_count_required visible automatically
- balanced transition
- close action appeared
- close completion removed next action
- short difference displayed correctly
- short pending_count = 1
- short remained closable
- export panel remained intact

Non-blocking UX notes:

- A raw UTC timestamp was observed in the close-confirmed card. This is a non-blocking UX note.
- A semicolon variant of the cash-count phrase did not match the exact grammar. This is consistent with the intentionally closed phrase grammar and is not a blocker.

Manual balanced and short-path acceptance was completed successfully before the current database was cleared. The retained database therefore cannot replay those historical WorkItem generations. Final read-only acceptance confirmed schema, RLS, pure reads, policies, registries, persistence invariants, and existing-flow boundaries. This is an evidence-retention limitation, not a product failure.
