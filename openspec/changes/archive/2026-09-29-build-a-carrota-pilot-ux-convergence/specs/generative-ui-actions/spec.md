## ADDED Requirements

### Requirement: Operator review uses silent request_close then closing.confirm@1
`closing.request@1` and `closing.confirm@1` MUST remain the only close action ids. The approved operator `Revisar cierre` path MUST mint the confirmation token by silently running existing `request_close` via `POST /api/v1/lumo/messages` with the today GET technical identifier `cerrar el día`. The review surface MUST then post `closing.confirm@1` with that server-issued token. Flutter MUST NOT treat that identifier as merchant-visible copy. Typed composer `cerrar el día` and `confirmar cierre` MUST keep working as the historical conversational path. The action catalog MUST NOT gain a mixed-payment action, an inventory action, or `closing.reopen@1`. `closing.request@1` MUST still run `request_close` and MUST NOT call `closing.confirm@1`. `closing.confirm@1` MUST still require the server confirmation token.

If inspecting `/lumo/messages` persistence shows that the silent POST necessarily stores a visible merchant turn that would reappear after transcript reload, implementation MUST NOT hide that turn only in local UI. It MUST use the smallest existing `POST /api/v1/lumo/actions` `closing.request@1` path that executes `request_close` without creating a merchant turn. It MUST NOT invent a new close workflow or state machine.

#### Scenario: Request close from review does not require a bubble
- **WHEN** the merchant taps `Revisar cierre` on a counted open day
- **THEN** existing `request_close` MUST run, the day MUST remain `open`, a confirmation token MUST be issued, and the client MUST NOT show a merchant bubble `cerrar el día`

#### Scenario: Confirm from the sheet is the same workflow
- **WHEN** the review surface posts `closing.confirm@1` with a matching unexpired token
- **THEN** the confirm MUST follow the existing `closing.confirm@1` workflow and MUST NOT use a second close state machine
