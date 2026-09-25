## ADDED Requirements

### Requirement: Pending-work phrases read the Next Best Action
After accent folding, case folding, whitespace collapse, and stripping one surrounding layer of `¿?¡!`, only these exact strings MUST map to `intent=next_best_action` and `candidate_tool=operational_day.next_best_action@1`: `que sigue`, `que falta`, `que tengo pendiente`, `que sigue con el cierre`, `que falta para cerrar`, `que falta para el cierre`, and `que tengo pendiente para cerrar`. Matching MUST be exact, MUST run with the other closed operational phrases, and MUST run before product parsing. The interpreter MUST NOT access a repository and MUST NOT use free-form NLU. The orchestrator MUST invoke the pure read query and MUST NOT open a business transaction itself. This path MUST NOT insert a WorkItem, an audit row, or an idempotency row. `preparar el cierre`, `ventas de hoy`, and the export phrases MUST keep their current routing and MUST NOT also emit `next_best_action@1`.

#### Scenario: Qué sigue selects the read tool
- **WHEN** the actor posts `¿qué sigue?`
- **THEN** the decision MUST be `next_best_action` for `operational_day.next_best_action@1`

#### Scenario: Closed close variants match
- **WHEN** the actor posts `qué sigue con el cierre`, `qué falta para cerrar`, `qué falta para el cierre`, or `qué tengo pendiente para cerrar`
- **THEN** each decision MUST select `operational_day.next_best_action@1`

#### Scenario: Qué falta and qué tengo pendiente match
- **WHEN** the actor posts `qué falta` or `¿qué tengo pendiente?`
- **THEN** each decision MUST select `operational_day.next_best_action@1`

#### Scenario: Preparation does not attach the next-action card
- **WHEN** the actor posts `preparar el cierre`
- **THEN** the orchestrator MUST run `closing.prepare@1` and the response `ui` MUST NOT include `next_best_action`

#### Scenario: Day summary does not attach the next-action card
- **WHEN** the actor posts `ventas de hoy`
- **THEN** the orchestrator MUST run `operational_day.summary@1` and the response `ui` MUST NOT include `next_best_action`

#### Scenario: A phrase outside the closed grammar stays unsupported
- **WHEN** the actor posts `qué sigue con el cierre por favor`
- **THEN** the interpreter MUST NOT select `operational_day.next_best_action@1`
