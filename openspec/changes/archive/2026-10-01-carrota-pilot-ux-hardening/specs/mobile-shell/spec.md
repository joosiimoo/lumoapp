## MODIFIED Requirements

### Requirement: Inicio current state is pinned above a scrolling transcript
Inicio MUST compose a compact header region (eyebrow, greeting, light operational header) that is not an `InicioTurn` and a separate scrolling transcript for merchant messages, Lumo responses, and generated interaction cards. The header MUST show the short sentence and informative indicators only. It MUST NOT consume most of the viewport or become a dashboard. The independently scrolling transcript MUST remain the main content region below it. The operational summary and the transcript MUST occupy non-overlapping regions: scrolling the transcript MUST NOT move the summary, and transcript content MUST NOT paint through or collide with the summary. A gap of at least 12px MUST remain between the summary's bottom edge and the transcript content. Conversation growth MUST NOT hide the current-state region. Returning to Inicio MUST show current state from a fresh or just-refreshed today GET, not by scrolling to an old card. On that return, the transcript viewport MUST show the most recent turns and MUST NOT reset to the oldest turn. When a new turn is appended while Inicio is visible, the latest turn MUST be brought into view. Earlier turns MUST remain reachable by scrolling. Conversational sale (`900gr zanahoria` → sale card → totalize → payment) MUST remain on Inicio.

#### Scenario: Sale cards do not bury current state
- **WHEN** the merchant has confirmed two sales on Inicio
- **THEN** the light operational header MUST remain visible without scrolling the sale cards, and the transcript MUST remain independently scrollable below it

#### Scenario: Header stays compact while transcript scrolls
- **WHEN** the merchant scrolls the Inicio transcript
- **THEN** the compact light header MUST remain visible and MUST NOT expand into a dashboard

#### Scenario: Sale flow stays conversational
- **WHEN** the merchant submits `900gr zanahoria` on Inicio
- **THEN** the client MUST keep the existing sale-card path and MUST NOT replace it with a sale form

#### Scenario: Scroll does not overlap the operational summary
- **WHEN** the merchant scrolls the Inicio transcript while the operational summary is visible
- **THEN** the summary MUST stay fixed, transcript cards MUST NOT intersect its bounds, and at least 12px MUST separate the summary from the transcript content

#### Scenario: Return shows recent activity
- **WHEN** the transcript has older turns and a latest sale card, the merchant opens Hoy, and then returns to Inicio
- **THEN** the latest sale card MUST be in view, the oldest turn MUST NOT be the restored viewport, and the operational header MUST remain visible at the top

## ADDED Requirements

### Requirement: Inicio transcript cards show the event time
Each assistant transcript turn and each generated card on Inicio MUST show a muted 12px caption time `HH:MM`, 24-hour and zero-padded, for the moment that turn was appended. The zone MUST be the authenticated session `timezone` when that value is present, including Carrota `America/Mexico_City`. When the session timezone is absent, the device zone MUST be used. User bubbles MUST NOT show a timestamp. The caption MUST NOT be submitted as a domain fact, MUST NOT change sale, close, memory, or export payloads, and MUST NOT add a Memoria field. Flutter MUST NOT invent a server `occurred_at`.

#### Scenario: Card shows the append time
- **WHEN** an assistant card is appended at 14:05 in the session timezone
- **THEN** that card MUST show `14:05` and the merchant user bubble for the same exchange MUST NOT show a time

#### Scenario: Closed day keeps historical times
- **WHEN** today GET `operator_state` is `closed` and historical Inicio cards remain
- **THEN** those cards MUST still show their append times and MUST still hide sale mutation controls
