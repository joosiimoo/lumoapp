## MODIFIED Requirements

### Requirement: Backend generative UI contracts
The backend MUST expose `GenerativeUIRegistry` and `GenerativeUIComposer` ports. The shared versioned contract is `component`, `version`, `data`, `actions`, and `fallback_text`. Actions MUST carry opaque `action_id`, optional `option_id`, `context_token`, and an idempotency key. `GenerativeUIRegistry` MUST include `sale_item_added@1`, `sale_summary@1`, `sale_confirmed@1`, `operational_day_summary@1`, `daily_close_preparation@1`, and `daily_close_confirmed@1`, and MUST NOT include `closing_ready_card`, `cash_difference_card`, `daily_summary_card`, `sale_confirmed_card`, or `sale_completed`. `GenerativeUIComposer` MUST validate against the registry and emit only registered versioned contracts. The backend MUST NOT render widgets. Component versions MUST remain `1`. `actions` MUST remain optional: an empty array is valid. `sale_summary@1` MUST emit `sale.pay.cash@1`, `sale.pay.card@1`, and `sale.pay.transfer@1` only while the session is `ready_to_charge`. `sale_confirmed@1`, `sale_item_added@1`, `operational_day_summary@1`, and `daily_close_confirmed@1` MUST keep `actions` empty. `daily_close_preparation@1` MUST emit `closing.request@1` only for a counted open day with `cash_status` `balanced`, `short`, or `over` and a null confirmation token, and MUST emit only `closing.confirm@1` after `request_close` issues a token. It MUST emit no actions when `cash_status` is `not_counted`, when no day exists, or when no current cash count exists. The close confirmation token MUST be the `closing.confirm@1` action `context_token` and MUST also be copied to `data.confirmation_token`. Those two strings MUST be equal. `fallback_text` MUST remain present and MUST NOT contain the token.

#### Scenario: Closed registry on backend
- **WHEN** the composer is asked to emit an unregistered component
- **THEN** the backend MUST refuse to include it in the response

#### Scenario: Backend does not render
- **WHEN** a registered contract is composed
- **THEN** the API MUST return the declarative payload and MUST NOT return HTML, Flutter widgets, or executable UI code

#### Scenario: sale_item_added registered
- **WHEN** the registry is queried for component `sale_item_added` version `1`
- **THEN** it MUST be present and its `actions` MUST be empty

#### Scenario: sale_summary registered
- **WHEN** the registry is queried for component `sale_summary` version `1` composed for `ready_to_charge`
- **THEN** it MUST be present at version `1` and its `actions` MUST be the three payment action ids

#### Scenario: sale_confirmed registered
- **WHEN** the registry is queried for component `sale_confirmed` version `1`
- **THEN** it MUST be present and its `actions` MUST be empty

#### Scenario: operational_day_summary registered
- **WHEN** the registry is queried for component `operational_day_summary` version `1`
- **THEN** it MUST be present and its `actions` MUST be empty

#### Scenario: daily_close_preparation registered
- **WHEN** the registry is queried for component `daily_close_preparation` version `1`
- **THEN** it MUST be present, and `closing_ready_card` and `cash_difference_card` MUST be absent

#### Scenario: daily_close_confirmed registered
- **WHEN** the registry is queried for component `daily_close_confirmed` version `1`
- **THEN** it MUST be present and its `actions` MUST be empty

#### Scenario: Confirm token is not duplicated as a second authority
- **WHEN** a confirmable preparation contract is composed
- **THEN** `data.confirmation_token` and the `closing.confirm@1` `context_token` MUST be the same server-issued JWT

### Requirement: Flutter GenerativeUIRenderer
Flutter MUST own `GenerativeUIRenderer`. It is solely responsible for rendering backend-emitted contracts. The renderer MUST reject unknown component names or versions and show `fallback_text`. It MUST NOT execute an action whose id is not in the closed five-id catalog. An unknown action id on a known component MUST NOT replace that component with `fallback_text` and MUST NOT render a button. Flutter MUST NOT decide that a payment or close action is legal when the server omitted it.

#### Scenario: Unknown component rejected
- **WHEN** a payload names a component that is not registered in the Flutter renderer
- **THEN** Flutter MUST render `fallback_text` and MUST NOT execute any action from that payload

#### Scenario: Unknown action is ignored
- **WHEN** `sale_summary` version `1` includes an action id outside the closed catalog
- **THEN** Flutter MUST still render the summary card and MUST NOT execute that action
