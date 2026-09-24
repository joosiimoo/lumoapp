# Acceptance notes

Manual acceptance PASS:

- missing-current copy
- real confirmed sale
- Excel file downloaded/shared
- Excel file opened and inspected
- CSV downloaded/shared
- CSV .bin macOS issue found
- root cause identified as XFile.fromData filename loss
- temp staging fix applied
- CSV shared with exact .csv filename
- CSV opened/inspected
- CSV BOM valid
- XLSX structure valid
- CSV/XLSX logical rows matched
- gross reconciled

Final DB/API acceptance passed with an evidence limitation. The PostgreSQL volume was recreated after manual acceptance, so previously accepted live sales were no longer available for replay. CSV/XLSX contents, filenames, reconciliation, and sharing had already been manually validated against real persisted sales before the reset. Current read-only verification confirmed migration head, absence of export persistence, API route/error behavior, no-side-effects, registry boundaries, RLS, and NOBYPASSRLS. Automated tests continue to cover empty-day, foreign-tenant, mixed-sale, payment invariant, reconciliation, and historical snapshot scenarios.
