# ADR-009: Controlled generative UI contract

- Status: Accepted
- Date: 2026-09-19

## Decision

Backend `GenerativeUIRegistry` and `GenerativeUIComposer` validate and emit only registered versioned JSON contracts (`component`, `version`, `data`, `actions`, `fallback_text`). Flutter `GenerativeUIRenderer` is the only renderer. Unknown components show `fallback_text` and do not run actions.
