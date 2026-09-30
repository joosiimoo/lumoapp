## MODIFIED Requirements

### Requirement: Register sale_confirmed@1
`GenerativeUIRegistry` MUST register component `sale_confirmed` version `1`. `GenerativeUIComposer` MUST emit this contract after a committed `sale.commit@1` **transition**, and MAY emit the same contract as a current-state read-back when the session is already `confirmed` and no newer `open` or `ready_to_charge` session exists for the interaction context. After a successful void, the composer MUST emit a voided confirmation variant of this contract (same component version) whose `data.status` is `voided` and whose void metadata and impact fields are server-provided. A current-state read-back MUST NOT be composed when a newer active session exists. An exact completed idempotency replay MAY still return a previously stored body that contains `sale_confirmed@1`; that replay is not a fresh current-state read-back. A fresh payment action bound to an already confirmed session MUST NOT compose that historical `sale_confirmed@1` when a newer active session exists; it returns `ui_action_stale` with empty `ui`. It MUST refuse unknown components. The backend MUST NOT render Flutter widgets or HTML.

For a live `confirmed` sale, Inicio `sale_confirmed@1` `actions` MUST NOT include `sale.void.request@1`, `sale.void.confirm@1`, or any Anular affordance. Confirmed-sale void entry is Memoria-only (see `memoria-timeline`). For `voided`, `actions` MUST be empty. Money MUST be decimal strings plus `MXN`. `fallback_text` MUST be server-provided and MUST contain the item count, total, and payment method display label (`Efectivo` | `Tarjeta` | `Transferencia`), and for voided MUST convey anulación. The contract version MUST remain `1`. `data.items` MUST include every persisted line.

`data.status` MUST be `confirmed` or `voided`. `data.payment.method` MUST be `cash`, `card`, or `transfer`. `data.payment.amount` MUST equal `data.total`. `data.total.amount` MUST equal the Decimal sum of persisted item `line_total`s. Item order MUST be persistence order (`created_at` ascending). This contract MUST NOT be used for `ready_to_charge` sales. `sale_summary@1` MUST NOT be emitted after a successful commit. PRD name `sale_confirmed_card` MUST remain unregistered.

#### Scenario: Composer emits after committed cash
- **WHEN** `sale.commit@1` has committed a three-item session totaling `56.50` MXN with method `cash`
- **THEN** the agent response `ui` MUST include exactly one `sale_confirmed` version `1` payload whose `data.status` is `confirmed`, `data.total.amount` is `56.50`, `data.payment.method` is `cash`, and `actions` MUST NOT include `sale.void.request@1`

#### Scenario: Composer emits voided confirmation
- **WHEN** `sale.void@1` has voided that session
- **THEN** the response `ui` MUST include `sale_confirmed@1` with `data.status` `voided`, empty `actions`, and fallback text that conveys the sale was anulada

## ADDED Requirements

### Requirement: Inicio confirmed card has no void entry
Flutter MUST NOT render Anular on an Inicio `sale_confirmed@1` card for `status=confirmed`. A `voided` card MAY show voided treatment when returned by a void flow and MUST NOT offer Anular. Confirmed-sale void MUST be started only from Memoria when the timeline provides `sale.void.request@1`.

#### Scenario: Confirmed Inicio card has no Anular
- **WHEN** the renderer receives `sale_confirmed@1` with `status=confirmed` after commit
- **THEN** it MUST NOT show an Anular control and MUST NOT post `sale.void.request@1` from Inicio

#### Scenario: Voided card has no anular
- **WHEN** the renderer receives `sale_confirmed@1` with `status=voided`
- **THEN** it MUST NOT show an Anular action
