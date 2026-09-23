## ADDED Requirements

### Requirement: UI actions bypass interpretation
`POST /api/v1/lumo/actions` MUST enter the orchestrator without `LLMProvider.interpret`. A registered action MUST call the same handler as the matching typed intent: payment actions call the commit handler, `closing.request@1` calls the request-close handler, and `closing.confirm@1` calls the confirm handler. The action path MUST still evaluate policy and MUST revalidate tenant, actor, permission, and current state. An unregistered action MUST NOT call a tool.

#### Scenario: Payment action skips the interpreter
- **WHEN** `sale.pay.transfer@1` is posted with a valid `ui_action` token
- **THEN** `LLMProvider.interpret` MUST NOT run and `CommitSaleSession` MUST run with method `transfer`

#### Scenario: Unregistered action fails closed
- **WHEN** the action id is not in `UiActionRegistry`
- **THEN** no tool MUST run and no domain row MUST change

## MODIFIED Requirements

### Requirement: Orchestrator routes cash intents to their workflows
For intent `record_cash_count`, the orchestrator MUST request policy and then invoke the cash-count write workflow, and MUST NOT run add-item, totalize, commit, or the day-summary read. For intent `close_preparation`, it MUST invoke the preparation read workflow and MUST NOT run any write workflow. For intent `request_close` and for action `closing.request@1`, it MUST invoke the preparation read and, only when that read is confirmable, attach a confirmation token. It MUST NOT call `closing.confirm@1` for `request_close` or for `closing.request@1`. For intent `confirm_close`, it MUST pass `client_context.confirmation_token` into `closing.confirm@1` and MUST ignore a model-supplied token. For action `closing.confirm@1`, it MUST pass that action's `context_token` into the same confirm workflow argument and MUST ignore any other token. The orchestrator MUST NOT open ORM sessions or database transactions and MUST NOT calculate expected cash or a difference. The write workflows MUST own one application transaction as specified by `cash-count-foundation` and `daily-close-confirmation`. `daily_close_preparation@1` MUST be composed only after a cash-count commit, or immediately for a non-writing preparation or request-close. `daily_close_confirmed@1` MUST be composed only after a confirm commit or from a committed snapshot read. The read workflow MUST NOT open a write transaction.

#### Scenario: Cash count is its own workflow
- **WHEN** Inicio posts `tengo 20 en caja` for a tenant whose OperationalDay exists
- **THEN** the cash-count workflow MUST run, `sale.add_item@1` / `sale.totalize@1` / `sale.commit@1` MUST NOT run, and `daily_close_preparation@1` MUST be composed only after commit

#### Scenario: Preparation is a read workflow
- **WHEN** Inicio posts `preparar el cierre`
- **THEN** the preparation read workflow MUST run, no write workflow MUST run, and no row MUST be inserted or updated

#### Scenario: Cash count does not touch the sale in progress
- **WHEN** an `open` `SaleSession` with items exists for the conversation and the actor posts `tengo 20 en caja`
- **THEN** that session MUST remain `open` with its items and total unchanged, and no `Payment` MUST be created

#### Scenario: Confirm uses the client token
- **WHEN** Inicio posts `confirmar cierre` with `client_context.confirmation_token` and the model decision also contains a different token
- **THEN** the workflow MUST receive only the client token

#### Scenario: Confirm action uses the action token
- **WHEN** Inicio posts action `closing.confirm@1` whose `context_token` is the server close JWT
- **THEN** the confirm workflow MUST receive that token and MUST NOT read a model-supplied token
