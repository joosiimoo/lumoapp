## MODIFIED Requirements

### Requirement: GenerativeUIRenderer owns rendering
Flutter MUST provide a `GenerativeUIRenderer` that renders only backend-emitted generative UI contracts. It MUST register `sale_item_added` version `1`, `sale_summary` version `1`, `sale_confirmed` version `1`, `operational_day_summary` version `1`, `daily_close_preparation` version `1`, `daily_close_confirmed` version `1`, and `next_best_action` version `1`. Unknown components or versions MUST display `fallback_text` and MUST NOT run actions. Unknown action ids MUST NOT run. Flutter MUST NOT compose or register backend UI contracts. Flutter MUST NOT calculate line totals, session totals, summary totals, payment amounts, daily totals, expected cash, counted cash, or cash differences. Flutter MUST NOT display `confirmation_token` or `context_token`.

When the response contains one known version-1 contract and `text.strip()` equals that contract's `fallback_text.strip()`, Flutter MUST render the card as the assistant artifact and MUST NOT also render a visible prose block if the component is `sale_item_added`, `sale_summary`, `sale_confirmed`, `operational_day_summary`, `next_best_action`, or `daily_close_confirmed`, or if it is `daily_close_preparation` and `fallback_text` starts with `Cierre `. In every other case with a known card, Flutter MUST render the response `text` and the card. An empty `ui` MUST render `text` only. The card SHOULD expose `fallback_text` as an accessibility summary when the visible prose is omitted.

#### Scenario: Fallback for unknown component
- **WHEN** the API returns a UI payload whose `component` is unknown to the renderer
- **THEN** the app MUST show that payload's `fallback_text` and MUST NOT invoke any included action

#### Scenario: Sale summary is handled
- **WHEN** the API returns `sale_summary` version `1`
- **THEN** the renderer MUST handle it and MUST display `data.total` without summing item `line_total`s

#### Scenario: Sale confirmed is handled
- **WHEN** the API returns `sale_confirmed` version `1`
- **THEN** the renderer MUST handle it, MUST display every server item, and MUST display `data.total` without calculating money

#### Scenario: Operational day summary is handled
- **WHEN** the API returns `operational_day_summary` version `1`
- **THEN** the renderer MUST handle it and MUST display the server sale count and daily totals without summing payment methods

#### Scenario: Daily close preparation is handled
- **WHEN** the API returns `daily_close_preparation` version `1`
- **THEN** the renderer MUST handle it and MUST display the server expected cash, counted cash, difference, and status without recomputing them

#### Scenario: Daily close confirmed is handled
- **WHEN** the API returns `daily_close_confirmed` version `1`
- **THEN** the renderer MUST handle it and MUST display the server gross, expected cash, counted cash, and difference without recomputing them

#### Scenario: Next best action is handled
- **WHEN** the API returns `next_best_action` version `1`
- **THEN** the renderer MUST handle it and MUST display the server `title` and `reason` without calculating money or choosing another action

#### Scenario: Duplicate preparation prose is omitted
- **WHEN** the response `text` equals the `daily_close_preparation@1` `fallback_text` and that text starts with `Cierre `
- **THEN** the stream MUST show the card and MUST NOT show a second visible copy of that sentence

#### Scenario: Duplicate next-action prose is omitted
- **WHEN** the response `text` equals the `next_best_action@1` `fallback_text`
- **THEN** the stream MUST show the card and MUST NOT show a second visible copy of that sentence

#### Scenario: Request-close prose is kept
- **WHEN** the response `text` starts with `El cierre está preparado`
- **THEN** the stream MUST show that prose and the preparation card

#### Scenario: Clarification stays prose
- **WHEN** the response has an empty `ui` and a clarification `text`
- **THEN** the stream MUST show that prose and MUST NOT invent a card
