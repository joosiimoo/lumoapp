## Purpose

Flutter visual identity from `docs/LUMO_DESIGN_SYSTEM_v1.0.md`: tokens and base widgets only. No dark theme and no invented product components.

## Requirements

### Requirement: Token parity with the approved design system
The Flutter design module MUST expose color, gradient, typography, spacing, radius, shadow, and size tokens from `docs/LUMO_DESIGN_SYSTEM_v1.0.md` using the documented hex values. It MUST NOT introduce a dark theme, a blue informational color, or a new accent hue.

#### Scenario: Canvas and primary colors
- **WHEN** the token module is read
- **THEN** background MUST be `#FCFAF4` and primary MUST be `#267B4C`

#### Scenario: Forbidden identity changes
- **WHEN** the token set is inspected
- **THEN** it MUST NOT define a dark-theme palette or an informational blue

### Requirement: Typography tokens
The app MUST load Inter (400/500/600/700) and Instrument Serif (regular and italic). Named text styles MUST match the design-system Flutter handoff for greeting, titles, eyebrow, body, metrics, buttons, chips, and navigation labels.

#### Scenario: Greeting uses serif italic
- **WHEN** a screen uses the display greeting style
- **THEN** it MUST use Instrument Serif italic at 34px with line height 1.05

### Requirement: Base components
The `lumo` module MUST provide base widgets mapped from the design system: scaffold/shell, bottom navigation, composer shell, Lumo mark, message, user bubble, soft card, primary button, secondary button, text button, chips, and toast host. Components that the reference app does not implement MUST NOT be invented in this change, except that a bottom sheet widget MUST remain unspecified.

#### Scenario: Soft card appearance
- **WHEN** `LumoCard` is rendered
- **THEN** it MUST use white fill, 24px radius, no border, and the documented two-layer soft shadow

#### Scenario: User versus assistant
- **WHEN** a user message and an assistant message are rendered
- **THEN** the user message MUST be a right-aligned primary-filled bubble and the assistant message MUST be unbubbled text preceded by the Lumo mark

### Requirement: Visual identity freeze
This change MUST reproduce the approved visual identity and MUST NOT redesign layout, motion, or iconography. Motion MUST be limited to the documented 150ms color/fill transitions. Loading skeletons, ripples, and new entrance animations MUST NOT be added.

#### Scenario: No invented motion
- **WHEN** the foundation shell is exercised
- **THEN** it MUST NOT play card entrance, typing-indicator, or page-transition animations that are absent from the design system
