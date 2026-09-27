## ADDED Requirements

### Requirement: Inicio hosts the business stream above the conversation
Inicio MUST show the Business Stream panel when the tab becomes visible, below the existing `Buenos días` greeting and above the conversation. It MUST keep `LumoComposer`, the four-tab shell, and the current conversation-card renderer. The panel MUST NOT replace Hoy, Memoria, or Negocio. A `record_cash_count` control MUST only focus that composer. A `request_close` control MUST post `cerrar el día` with the same `conversation_id` Inicio already uses for close phrases. After a successful message or action from that conversation, Inicio MUST reload the panel. Transport failure MUST show `No pude consultar el estado de hoy.` and MUST NOT present the last successful totals as current.

#### Scenario: Greeting and composer stay
- **WHEN** Inicio renders with a business stream panel
- **THEN** `Buenos días` MUST remain visible and the existing composer MUST remain usable

#### Scenario: Close from the panel reuses the conversation
- **WHEN** the merchant taps `Revisar cierre` on the Inicio panel
- **THEN** the message POST MUST send the shell `conversation_id` and Flutter MUST NOT generate a new UUID

#### Scenario: Other tabs stay
- **WHEN** the merchant opens Hoy or Memoria after this panel exists
- **THEN** Hoy MUST still load its own next-best-action block and Memoria MUST still load its event timeline
