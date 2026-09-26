## ADDED Requirements

### Requirement: Closed factual phrases read memory.business_facts@1
After accent folding, case folding, whitespace collapse, and stripping one surrounding layer of `¿?¡!`, only the phrases in this requirement MUST select `candidate_tool=memory.business_facts@1`. Matching MUST run with the other closed operational phrases, after the existing day-summary phrases, and before product parsing. The interpreter MUST NOT access a repository. The orchestrator MUST resolve `today` and `yesterday` to a business-local date before the tool call. `como vamos hoy`, `ventas de hoy`, and `cuanto vendimos hoy` MUST still select `operational_day.summary@1`.

The exact mappings are: `que paso hoy` to `day_summary` for today; `que paso ayer` to `day_summary` for yesterday; `cuanto vendi hoy` and `cuantas ventas tuve hoy` to `sales_summary` for today; `cuanto vendi ayer` and `cuantas ventas tuve ayer` to `sales_summary` for yesterday; `como cerre hoy` to `close_summary` for today; `como cerre ayer` to `close_summary` for yesterday; `cual fue mi ultimo cierre` and `que paso en el ultimo cierre` to `latest_close`; `hubo diferencia de caja` and `hay diferencia de caja` to `cash_summary` for today; `he tenido diferencias de caja ultimamente` to `recent_cash_differences` with `recent_days` 7; `que eventos hubo hoy` to `day_events` for today; `que eventos hubo ayer` to `day_events` for yesterday. `que paso el YYYY-MM-DD`, and `que paso el <day> de <spanish month>` with an optional year, MUST map only to `day_summary`. A missing year MUST be the year of business-local today. The interpreter MUST NOT move a future date to the previous year.

#### Scenario: Qué pasó hoy selects the day summary
- **WHEN** the actor posts `¿Qué pasó hoy?`
- **THEN** the decision MUST select `memory.business_facts@1` with `query_type` `day_summary` for the business-local today

#### Scenario: Existing hoy summary phrases stay put
- **WHEN** the actor posts `¿Cuánto vendimos hoy?`
- **THEN** the decision MUST select `operational_day.summary@1` and MUST NOT select `memory.business_facts@1`

#### Scenario: Últimamente uses a seven-day window
- **WHEN** the actor posts `¿He tenido diferencias de caja últimamente?`
- **THEN** the decision MUST select `recent_cash_differences` with `recent_days` 7

#### Scenario: An explicit past date is a day summary
- **WHEN** business-local today is 2026-09-25 and the actor posts `¿Qué pasó el 24 de septiembre?`
- **THEN** the decision MUST select `day_summary` with `business_date` `2026-09-24`

### Requirement: Unsupported history does not invent an answer
The exact phrases `el trimestre pasado`, `este ano`, `el ano pasado`, `que paso el trimestre pasado`, `que paso este ano`, `que vendi este ano`, and `que vendi el ano pasado` MUST NOT select a tool and MUST NOT be parsed as a sale. A `que paso el …` date that is invalid or after business-local today MUST NOT select a tool and MUST NOT create an `OperationalDay`. The reply MUST be "Puedo consultar hechos registrados en Lumo para hoy, ayer, una fecha ya transcurrida, el último cierre, o las diferencias de caja de los últimos días. No encuentro esa consulta entre esos hechos." The model MUST NOT answer that question from its own knowledge. Every other unmatched utterance MUST keep its current path.

#### Scenario: Last quarter explains the supported scope
- **WHEN** the actor posts `el trimestre pasado`
- **THEN** the response MUST be the scope sentence above, no tool MUST run, and no business row MUST be written

#### Scenario: A future date is not queried
- **WHEN** business-local today is 2026-09-25 and the actor posts `¿Qué pasó el 26 de septiembre?`
- **THEN** the tool MUST NOT run and no `OperationalDay` MUST be created
