# LUMO — Design System Specification v1.0

Reference implementation: the current Lumo/Carrota React prototype (TanStack Start + Tailwind v4).
Purpose: reproduce the exact visual identity and interaction patterns in a new Flutter mobile client.
Nothing in this document redesigns the app. All values are extracted from source; where a value is
not explicitly defined in code, it is marked **(not defined in code)**.

Source of truth files:
- `src/styles.css` — all tokens
- `src/routes/__root.tsx` — fonts, theme-color, toaster
- `src/components/lumo/*` — components
- `src/routes/{index,hoy,memoria,negocio,onboarding}.tsx` — screens

Color tokens are authored in **OKLCH**. Hex values below are exact sRGB conversions of those OKLCH
values (computed, not eyeballed). Flutter should use the hex values.

Tailwind spacing conversion used throughout: `1 unit = 0.25rem = 4px`, base font size 16px.

---

## 1. DESIGN TOKENS

### 1.1 Color tokens (light theme only — no dark theme is implemented)

| Token | OKLCH (source) | Hex | Role |
|---|---|---|---|
| `--background` | `oklch(0.985 0.008 90)` | `#FCFAF4` | App canvas (warm off-white) |
| `--surface` | `oklch(0.985 0.008 90)` | `#FCFAF4` | Alias of background |
| `--surface-elevated` | `oklch(1 0 0)` | `#FFFFFF` | Cards, composer, chips background |
| `--card` | `oklch(1 0 0)` | `#FFFFFF` | shadcn card |
| `--card-foreground` | `oklch(0.18 0.02 155)` | `#0A140E` | Text on card |
| `--foreground` | `oklch(0.18 0.02 155)` | `#0A140E` | Primary text (near-black green) |
| `--popover` | `oklch(1 0 0)` | `#FFFFFF` | Popover surface |
| `--popover-foreground` | `oklch(0.18 0.02 155)` | `#0A140E` | Popover text |
| `--primary` | `oklch(0.52 0.11 155)` | `#267B4C` | Forest green: actions, links, selected chips |
| `--primary-foreground` | `oklch(0.985 0.008 90)` | `#FCFAF4` | Text on primary |
| `--secondary` | `oklch(0.96 0.01 120)` | `#F1F3EB` | Subtle fill |
| `--secondary-foreground` | `oklch(0.22 0.03 155)` | `#0F1F14` | Text on secondary |
| `--muted` | `oklch(0.95 0.008 100)` | `#EFEFE9` | Disabled button fill |
| `--muted-foreground` | `oklch(0.5 0.02 150)` | `#5C675D` | Secondary/caption text |
| `--accent` | `oklch(0.94 0.03 165)` | `#DAF2E6` | Soft mint: status chips, active nav pill, product thumbs |
| `--accent-foreground` | `oklch(0.22 0.05 155)` | `#032110` | Text on accent |
| `--destructive` | `oklch(0.6 0.2 25)` | `#DE3B3D` | Error (declared; **not used in any screen yet**) |
| `--border` | `oklch(0.92 0.01 120)` | `#E3E6DE` | Hairlines, outline buttons, dividers |
| `--input` | `oklch(0.94 0.01 120)` | `#EAECE5` | shadcn input border (unused by Lumo composer) |
| `--ring` | `oklch(0.75 0.06 180)` | `#84BBAF` | Focus ring (shadcn default) |
| `--user` | `oklch(0.52 0.11 155)` | `#267B4C` | User message bubble fill (== primary) |
| `--user-foreground` | `oklch(0.985 0.008 90)` | `#FCFAF4` | User message text |
| `--attention` | `oklch(0.72 0.14 75)` | `#D79628` | Warning text (low stock) |
| `--attention-soft` | `oklch(0.93 0.06 85)` | `#FAE6BB` | Warning fill (declared, reserved) |
| `--lumo-teal` | `oklch(0.82 0.09 195)` | `#78D7D6` | Lumo identity accent (sparkle icon) |
| `--lumo-lavender` | `oklch(0.78 0.09 285)` | `#B1B0EF` | Lumo identity accent |
| `theme-color` (meta) | — | `#faf9f5` | Browser chrome |

There is **no informational (blue) color** and **no explicit disabled color token**; disabled is
expressed as `--muted` + `--muted-foreground`, or `opacity: 0.4`.

### 1.2 Gradients

**Lumo Gradient — Text** (`.lumo-gradient-text`), 100° linear, background-clip: text:
| Stop | OKLCH | Hex |
|---|---|---|
| 0% | `oklch(0.72 0.11 195)` | `#36BABA` |
| 45% | `oklch(0.72 0.11 240)` | `#5EADE2` |
| 100% | `oklch(0.72 0.10 300)` | `#AE96DA` |

**Lumo Gradient — Fill** (`.lumo-gradient-bg`), 100° linear:
| Stop | OKLCH | Hex |
|---|---|---|
| 0% | `oklch(0.78 0.10 195)` | `#5ECBCB` |
| 55% | `oklch(0.72 0.10 260)` | `#80A5E3` |
| 100% | `oklch(0.72 0.10 300)` | `#AE96DA` |

100° in CSS ≈ direction vector 10° past horizontal-right, i.e. in Flutter
`LinearGradient(begin: Alignment(-0.98, -0.17), end: Alignment(0.98, 0.17))` (left→right with a
slight upward tilt).

**LumoMark ring gradient** (SVG, 0,0 → 1,1 diagonal): `#5ECBCB` → `#9794E0`.
**LumoMark halo**: radial-gradient at 30% 30%, `#76E2E2` at 90% alpha → transparent at 65%,
blur radius 12px (`blur-md`), overall opacity 0.6.

### 1.3 Typography tokens

| Token | Value |
|---|---|
`--font-sans` | `"Inter", ui-sans-serif, system-ui, sans-serif` (weights 400, 500, 600, 700)
`--font-serif` | `"Instrument Serif", ui-serif, Georgia, serif` (regular + italic)

Loaded from Google Fonts in `__root.tsx`:
`Inter:wght@400;500;600;700` and `Instrument+Serif:ital@0;1`.

Font smoothing: `-webkit-font-smoothing: antialiased`. Body font: Inter.

Font sizes actually used (px):
`10, 11, 12 (text-xs), 14 (text-sm), 15 (custom body), 16 (text-base), 20 (text-xl), 26, 32, 34, 36/60 (404)`.

Line heights used: `leading-relaxed` (1.625), `leading-snug` (1.375), `leading-tight` (1.25),
`leading-[1.05]` (home greeting), default `1.5`.

Letter spacing used: `tracking-tight` (-0.025em), `tracking-wider` (0.05em),
`tracking-[0.18em]` (eyebrow labels on Inicio/Memoria/Negocio).

### 1.4 Spacing scale

Tailwind default 4px scale. Values present in code:
`1 (4px), 1.5 (6px), 2 (8px), 2.5 (10px), 3 (12px), 3.5 (14px), 4 (16px), 5 (20px), 6 (24px), 8 (32px)`.

Common combinations:
- Screen horizontal padding: **16px** (`px-4`) for card lists; **20px** (`px-5`) for text headers.
- Card inner padding: `16px × 14px` (`px-4 py-3.5`), or `20px × 16px` / `20px × 20px` for hero cards.
- Vertical gaps: `10px` (memory items), `12px` (grids), `16px` (stream turns, section stack), `24px` (memory groups).

### 1.5 Border radius

| Token | Value |
|---|---|
`--radius` (base) | `1rem` = 16px
`--radius-sm` | 12px
`--radius-md` | 14px
`--radius-lg` | 16px
`--radius-xl` | 20px
`--radius-2xl` | 24px
`--radius-3xl` | 28px
`--radius-4xl` | 32px

Applied radii in components:
- `.soft-card` → **24px** (`1.5rem`, hardcoded in the utility)
- `rounded-2xl` → 24px (Hoy closing-flow button)
- `rounded-3xl` → 28px (user bubble)
- `rounded-xl` → 20px (product thumbnails)
- `rounded-full` → pill / circle (chips, buttons, composer, nav pill, bars)

### 1.6 Borders

- Default border color for every element: `--border` `#E3E6DE` (a global `* { border-color }` rule).
- Hairline width: **1px**.
- Dividers inside cards: `divide-border/60` → `#E3E6DE` at 60% alpha.
- Tab bar top border: `border-border/60`.
- Composer has **no border** — it uses the `ring-lumo` shadow instead.

### 1.7 Shadows

`.soft-card`:
```
0 1px 0   rgba(221,223,216,0.5)      /* oklch(0.9 0.01 120 / 0.5) → #DDDFD8 @ 50% */
0 8px 30px -18px rgba(49,80,60,0.15) /* oklch(0.4 0.05 155 / 0.15) → #31503C @ 15% */
```
`.ring-lumo` (composer / onboarding input):
```
0 0 0 1px  rgba(168,217,216,0.4)     /* #A8D9D8 @ 40% — 1px teal-tinted outline */
0 6px 24px -12px rgba(97,170,193,0.35) /* #61AAC1 @ 35% */
```
Small shadow (`shadow-sm`, Tailwind default) on: user bubble, composer send button, onboarding CTA
→ `0 1px 2px 0 rgb(0 0 0 / 0.05)`.

### 1.8 Opacity values in use

`0.4` (disabled send button), `0.5`/`0.6` (card shadows, dividers, tab-bar border), `0.6` (Lumo mark halo),
`0.8` (chart bars, and `text-foreground/80` on outline-button labels), `0.9` (`text-foreground/90` body copy),
`0.95` (sticky composer / tab-bar background before blur).

Backdrop blur: `backdrop-blur` (8px) on sticky footer and tab bar.

### 1.9 Icon sizing

| Context | Size |
|---|---|
Composer camera / mic | 18px (`h-4.5`)
Composer send arrow | 16px (`h-4`)
Suggestion chip sparkle | 12px (`h-3`)
Tab bar icons | 20px (`h-5`), stroke width **2.2 active / 1.6 inactive**
Closing-flow moon icon | 16px in a 36px circle
LumoMark | 18px in messages/cards, 14px in the Inicio eyebrow, 20px in onboarding header

### 1.10 Component sizing

| Element | Size |
|---|---|
App content column | `max-width: 420px`, centered, full `min-height: 100dvh`
Composer bar height | 44px (`py-2.5` + 24px line box) at 12px horizontal padding
Composer icon buttons | 32×32 (`h-8 w-8`)
Composer send button | 36×36 (`h-9 w-9`)
Tab bar item pill | 56×36 (`h-9 w-14`)
Tab bar total height | ~64px (`pt-2 pb-3` + 36px pill + 11px label)
Product thumbnail (sale card) | 36×36, radius 20px
Product thumbnail (Negocio list) | 40×40, radius 20px
Primary pill button | full width, `py-3.5` (14px) → 48px tall
Sale-card action buttons | `py-2.5` (10px) → ~40px tall
Chip | `px-3 py-1.5` (12×6) → ~28px tall
Status chip | `px-2.5 py-0.5` / `px-2 py-0.5` → ~20px tall
Chart plot area | 96px tall (`h-24`), bars `gap: 6px`, min bar height 8% of area
Status dot | 6×6 (`h-1.5 w-1.5`)

---

## 2. COLOR SYSTEM — usage map

- **Primary `#267B4C`** — user message bubble fill; selected payment-method chip; selected demo-scenario
  chip; memory card action links ("Ver evidencia / Corregir / Explicar / Olvidar"); "Venta registrada"
  label + dot; 404/error page buttons.
- **Secondary `#F1F3EB`** — declared token, shadcn components only; not used in Lumo screens.
- **Background `#FCFAF4`** — every screen canvas, sticky footer (at 95% + blur), tab bar.
- **Surface / card `#FFFFFF`** — `.soft-card` (all cards), composer, chips, outline buttons.
- **Text primary `#0A140E`** — headings, metric values, card titles, names.
- **Text body** — `#0A140E` at 90% opacity for conversational and narrative paragraphs.
- **Text secondary/muted `#5C675D`** — eyebrow labels, captions, timestamps, hints, placeholder,
  inactive tab labels, chart axis labels, "Acción deshecha" text.
- **Success** — there is no separate success color: success is expressed with **primary green**
  (registered-sale dot + label, "Todo coincide").
- **Warning `#D79628`** (`--attention`) — low-stock product line in Negocio (`stock < 6` → "· atención").
  `--attention-soft #FAE6BB` is defined but not yet applied.
- **Error `#DE3B3D`** (`--destructive`) — defined, no current usage.
- **Informational** — none defined; the Lumo gradient plays the "assistant/AI" informational role.
- **Disabled** — `bg-muted #EFEFE9` + `text-muted-foreground #5C675D` (Registrar venta without a
  payment method), or `opacity: 0.4` (onboarding send button).
- **Borders / dividers `#E3E6DE`** (60% alpha inside cards).
- **Accent `#DAF2E6`** — "Preparado" / "Resumen" / memory-kind status chips, operations count chip,
  active tab pill, product thumbnail background.
- **Gradients** — Lumo identity only: greeting words, business name in Memoria title, primary CTAs,
  chart bars, send button, closing-flow icon circle, LumoMark ring.

---

## 3. TYPOGRAPHY STYLES

| Style | Font | Size | Weight | Line height | Tracking | Usage |
|---|---|---|---|---|---|---|
Display greeting | Instrument Serif *italic* + Inter | 34px | 400 (serif) / 400 (name) | 1.05 | -0.025em | Inicio: "Buenos días," (gradient text) + "Jorge." (foreground)
Screen title (serif) | Instrument Serif | 32px | 400 | 1.25 | — | Negocio: business name
Screen title (serif, 2-line) | Instrument Serif | 26px | 400 | 1.25 | — | Memoria: "Lo que Lumo recuerda de {nombre}" (name in gradient italic)
Eyebrow / screen label | Inter | 11px | 400 | 1.5 | 0.18em, UPPERCASE | "Lumo · Carrota", "Memoria", "Negocio"
Section label | Inter | 11px | 400 | 1.5 | 0.05em, UPPERCASE | "Ingresos", "Pagos", "Productos", memory group headers ("Hoy", "Hace 2 días")
Body / narrative | Inter | 15px | 400 | 1.625 | — | Lumo summary card, "Lumo observa", assistant messages
Assistant message | Inter | 15px | 400 | 1.625 | — | `foreground/90`, no bubble, preceded by LumoMark; `**bold**` → weight 700, `*italic*` → italic + muted
User message | Inter | 15px | 400 | 1.5 | — | White text on green bubble
Card title | Inter | 14px | 500 | 1.5 | — | "Venta preparada", "Lumo observa", product names
Card title (registered) | Inter | 16px | 600 | 1.5 | — | "$385 · Tarjeta"
Metric value (hero) | Inter | 36px | 600 | 1 | -0.025em | Hoy: total revenue
Metric value (card) | Inter | 20px | 600 | 1.5 | — | Sale card Total
Metric value (row) | Inter | 14px | 600 | 1.5 | — | Item subtotal, product price
Metric label | Inter | 11px | 400 | 1.5 | 0.05em, UPPERCASE | "Moneda", "Zona horaria", "Estado de caja"
Field value | Inter | 16px | 500 | 1.5 | — | "MXN", "CDMX", "Activa", "Todo coincide"
Caption | Inter | 12px | 400 | 1.5 | — | timestamps, hints, item detail lines, product stock
Micro caption | Inter | 10px | 400 | 1.5 | — | chart hour axis
Button (primary) | Inter | 14px | 500 | 1.5 | — | "Registrar venta", "Empezar a hablar con {nombre}"
Button (secondary/outline) | Inter | 14px | 400 | 1.5 | — | "Corregir"
Button (small outline) | Inter | 12px | 400 | 1.5 | — | "Agregar detalle", "Deshacer"
Chip | Inter | 12px | 400 | 1.5 | — | suggestion chips, payment methods, question chips
Status chip | Inter | 11px | 500 | 1.5 | — | "Preparado", "Resumen", "Registrado"
Input / placeholder | Inter | 14px | 400 | 1.5 | — | composer
Navigation label | Inter | 11px | 400 / 500 active | 1.5 | — | tab bar
Link action | Inter | 14px | 400 | 1.5 | — | memory card actions, primary color

---

## 4. COMPONENT INVENTORY

Notation: padding as `horizontal × vertical`.

### 4.1 App Shell / Scaffold (`AppShell.tsx`)
Purpose: mobile frame for every app screen.
Structure: full-bleed background `#FCFAF4` → centered column `max-width 420px`, `min-height 100dvh`,
flex-column: scrollable content (`flex: 1`, `overflow-x: hidden`) → optional sticky footer (composer)
→ optional sticky bottom navigation.
Footer wrapper: `background #FCFAF4 @95%` + 8px backdrop blur, `padding-bottom: 4px`, transparent top border.
Tab-bar wrapper: same background/blur, 1px top border `#E3E6DE @60%`.
Variants: `showTabBar` true/false; `footer` present/absent.

### 4.2 App Header (per-screen, not a shared component)
Structure (Inicio): `padding 20px / 24px top / 12px bottom` → eyebrow row [LumoMark 14px + gap 8px +
"LUMO · {NEGOCIO}" 11px uppercase 0.18em muted] → 12px gap → serif 34px greeting.
Memoria/Negocio variant: eyebrow label, 8px gap, serif title 26–32px.
No back button, no app bar elevation, no shadow anywhere in headers.

### 4.3 Bottom Navigation (`TabBar.tsx`)
4 items, equal flex, `padding 16px × (8px top / 12px bottom)`, `justify-around`, gap 4px.
Item: column, gap 4px → 56×36 pill (radius: full; active fill `#DAF2E6`, inactive transparent) →
icon 20px → label 11px.
Active: `color #0A140E`, icon stroke 2.2, label weight 500, accent pill.
Inactive: `color #5C675D`, icon stroke 1.6, no pill.
Items and icons (Lucide): Inicio `Home` · Hoy `CalendarDays` · Memoria `Sparkles` · Negocio `Store`.
Selection is derived from exact pathname equality. Transition: `transition` (150ms, color/background).

### 4.4 Conversation Composer (`Composer.tsx`)
Purpose: the persistent way to talk to the business. Present on Inicio, Hoy, Memoria; **absent on Negocio**.
Wrapper: `max-width 420px`, `padding 16px horizontal, 8px top`.
Optional chip row above (see 4.12), `margin-bottom 12px`.
Bar: pill (radius full), background `#FFFFFF`, **no border**, `ring-lumo` shadow,
`padding 12px × 10px`, children gap 8px.
Left: 32px circular icon button, `Camera` 18px, muted → foreground on hover. Tapping shows toast
"Cámara — próximamente".
Middle: transparent text input, 14px, placeholder `#5C675D`, placeholder text **"Dile algo a tu negocio…"**
(Memoria override: "Pregunta algo sobre tu negocio…"), no focus outline.
Right: swaps on content — empty input → 32px `Mic` muted button (toast "Voz — próximamente");
non-empty → 36px circular send button, Lumo gradient fill, white `ArrowUp` 16px, `shadow-sm`.
Submit: Enter or send tap; input clears; empty/whitespace input is ignored.

### 4.5 Lumo Message (`LumoMessage`)
No bubble, no fill. Row, `align-items: flex-start`, gap 12px: LumoMark 18px (offset 4px down) +
paragraph 15px/1.625 at `foreground/90`. Supports inline `**bold**` (weight 700), `*italic*`
(italic + muted color) and `\n` → line break.

### 4.6 User Message Bubble (`UserBubble`)
Right-aligned; `max-width 85%`; fill `#267B4C`; text `#FCFAF4` 15px; radius 28px;
`padding 16px × 10px`; `shadow-sm`. No tail, no avatar, no timestamp.

### 4.7 Lumo Card Wrapper (`LumoCardWrapper`)
Row, gap 12px: LumoMark 18px (offset 8px down) + flexible card content. Every generative card
Lumo emits is wrapped in this, so cards visually belong to the assistant.

### 4.8 Soft Card (`.soft-card`) — base card
White fill, radius 24px, no border, two-layer soft shadow (§1.7). All cards derive from it.
Variants by padding: summary `20×16`, hero metric `20×20`, standard `16×14`, list container
(`overflow: hidden` + internal dividers `#E3E6DE @60%`).

### 4.9 Summary Card (Inicio narrative)
Soft card, `padding 20×16`, single 15px/1.625 paragraph with bolded business name and amounts.
Two states: empty ("aún no registra ventas hoy") and active ("lleva $X en N ventas / La caja coincide").

### 4.10 Metric Card (Hoy hero)
Soft card `20×20`: label "INGRESOS" 11px uppercase → 4px → baseline row (gap 12px) of 36px/600
amount + accent count chip → 24px → chart (§4.22) → 4px → hour axis row (10px muted, space-between:
8:00 / 12:00 / 16:00 / 20:00).

Secondary metric cards: 1-column on mobile, 2-column ≥640px, gap 12px, `padding 16×14`, label
11px uppercase + content (key/value rows 14px `space-between`, or value 16px/500 + 12px caption).

### 4.11 Sale Prepared Card (`SaleCard.tsx`, status `prepared`)
The core generative component. Soft card, `overflow: hidden`, stacked sections separated by 1px
`#E3E6DE @60%` dividers:
1. **Header** `padding 16px, top 14px`: accent status chip "Preparado" (radius full, `10×2`, 11px/500,
   fill `#DAF2E6`, text `#032110`) + gap 8px + "Venta preparada" 14px/500.
2. **Body** `padding 16px, top 12px` — one of three variants:
   - `structured`: divided list of Product Rows (§4.13).
   - `concepts`: bullet lines "· {concepto}" 14px at `foreground/90`, gap 6px, plus a 12px muted
     footnote "Estos conceptos se guardarán con la venta. No se crean productos."
   - `amount`: single 14px muted line "Sin detalle · puedes agregar lo vendido después."
3. **Total row** `16×12`, `space-between`: "Total" 14px muted / amount 20px/600.
4. **Payment section** `16×12`: hint "¿Cómo pagó?" 12px muted, 8px gap, wrapped method chips
   Efectivo · Tarjeta · Transferencia · Pago combinado (§4.19).
5. **Actions** `16×12`, row gap 8px: "Registrar venta" — flexible primary pill (`16×10`, 14px/500),
   Lumo gradient + white text when a method is selected, disabled `#EFEFE9`/`#5C675D` otherwise;
   "Corregir" — outline pill, 1px `#E3E6DE`, `16×10`, 14px `foreground/80` (toast "Corregir — próximamente").

Currency format: `$` + `es-MX` grouping, 0 decimals (e.g. `$1,240`).

### 4.12 Sale Registered Card (status `registered`)
Soft card `16×14`: row [6px primary dot + "VENTA REGISTRADA" 11px uppercase 0.05em primary] →
6px → "$385 · Tarjeta" 16px/600 → "hace unos segundos" 12px muted → 12px → small outline pills
"Agregar detalle" and (only while it is the last action) "Deshacer" (`12×6`, 12px, 1px border).

### 4.13 Sale Undone Card (status `undone`)
Soft card `16×12`, single 14px muted line "Acción deshecha · $385". No actions.

### 4.14 Product Row (inside structured sale)
`padding-y 10px`, row gap 12px: 36px accent-filled rounded square (radius 20px) with the product
emoji at 18px → column [name 14px/500 truncated; detail 12px muted `{qty} × {unit} · ${price} c/u`]
→ subtotal 14px/600, right-aligned. Rows separated by 1px dividers.

### 4.15 Product List (Negocio)
Section label "PRODUCTOS" 11px uppercase → soft card with dividers, rows `16×12`, 40px accent
thumbnail (radius 20px), name 14px/500, stock line 12px — muted normally, `#D79628` plus
"· atención" when `stock < 6` — and price 14px/600.

### 4.16 Memory Card (`memoria.tsx`)
Soft card `16×14`: header row [accent kind chip (`Registrado` / `Corregido` / `Observado` /
`Confirmado` / `Calculado`) + 12px muted time `HH:MM`] → 8px → title 15px/500 leading-snug → 4px →
body 14px muted → 12px → action link row (wrap, column gap 16px, row gap 4px), 14px primary:
Ver evidencia · Corregir · Explicar · Olvidar.

### 4.17 Timeline / Group Item (Memoria)
Groups stacked with 24px spacing; each group = 11px uppercase muted header ("Hoy", "Ayer",
"Hace N días", "La semana pasada") with `margin-bottom 8px, padding-left 4px`, then memory cards
spaced 10px. There is **no vertical rail or connector line** — grouping is purely typographic.

### 4.18 Action Card (Hoy closing flow entry)
Full-width outlined button, radius 24px, 1px `#E3E6DE`, white fill, `padding 16×12`, `space-between`:
left group (gap 12px) = 36px circular gradient badge with white `Moon` 16px + column [title 14px/500
"Preparar el cierre del día"; caption 12px muted "Confirma efectivo y revisa pendientes"], right
chevron `›` muted. Currently opens a toast "Preparar el cierre — próximamente".

### 4.19 Suggestion Chip / Question Chip
Pill, white fill, 1px `#E3E6DE`, `padding 12×6`, 12px text `foreground/80`.
Composer variant additionally leads with a 12px `Sparkle` icon in `--lumo-teal`, gap 6px, and the
row is preceded by a static 11px uppercase muted label "Sugerencias".
Hover: border → `--lumo-teal @50%` (composer chips) or `--primary @50%` (method chips).
Rows scroll horizontally, scrollbar hidden, `padding-bottom 4px`, items `flex-shrink: 0`.

Content: Inicio — "Registrar una venta", "Recibir mercadería" (Carrota) / "Notas del día" (La Esquina),
"Ver el día". Hoy — "¿Por qué vendimos más?", "Ver ventas con tarjeta", "Comparar con ayer".
Memoria — "¿Cuándo cambié un precio?", "¿A quién le compro?".

### 4.20 Selectable Chip (payment method, demo scenario)
Idle: 1px `#E3E6DE`, transparent fill, 12px `foreground/80`.
Selected: 1px `#267B4C`, fill `#267B4C`, text `#FCFAF4`.
Hover (idle): border `#267B4C @50%`. 150ms transition. Radius full, `padding 12×6`
(scenario variant `12×8`, flexible width).

### 4.21 Status Chip
Radius full, fill `#DAF2E6`, text `#032110`, 11px/500, `padding 10×2` (or `8×2` for the Hoy
"Resumen" and count chips). Non-interactive.

### 4.22 Chart Styles (Hoy)
13 hourly bins (08:00–20:00). Plot 96px tall, bars `flex: 1`, gap 6px, radius full, Lumo gradient
fill at 80% opacity, height = `max(8%, value / maxValue × 100%)` so empty hours still render a stub.
No axes, gridlines, labels on bars, or tooltips. Hour axis = 4 evenly distributed 10px muted labels.

### 4.23 Input Field (onboarding)
Pill, white fill, `ring-lumo` shadow, `padding 16×10`, gap 8px, transparent 14px input, autofocus,
36px gradient circular send button with 16px `ArrowUp`, `opacity 0.4` when empty.

### 4.24 Primary Button
Radius full, Lumo gradient fill, white 14px/500 text, `shadow-sm`.
Sizes: full-width `py-3.5` (onboarding CTA, 48px) and in-card `px-4 py-2.5` (40px).
Disabled: fill `#EFEFE9`, text `#5C675D`, no shadow.

### 4.25 Secondary / Outline Button
Radius full, transparent fill, 1px `#E3E6DE`, text `foreground/80`.
Sizes: `16×10` with 14px text, or `12×6` with 12px text.

### 4.26 Text / Link Button
No fill, no border. Primary-colored 14px (memory actions) or 11px uppercase muted 0.05em
("Modo demostración" / "Ocultar" toggle in Negocio).

### 4.27 Toast (only overlay currently implemented)
`sonner` `<Toaster position="top-center" />` mounted once at the root, default sonner styling
bound to shadcn tokens. Used for every not-yet-built affordance.

### 4.28 Not implemented in the reference app
The following were requested in the inventory but **do not exist** in the current prototype and must
not be invented from this document: **Search Field** (Memoria uses question chips, not a search
input), **Switch**, **Bottom Sheet**, **Closing Flow screen**, **Cash Count Input**, **Success State
screen**, **Alert Card** (the low-stock warning exists only as inline `--attention` text inside the
product row), and **Alert/ Attention card in the sale flow**. Tokens exist for warnings
(`--attention`, `--attention-soft`) and errors (`--destructive`) but no component consumes them yet.

---

## 5. GENERATIVE UI

The conversation is a single vertical stream of typed turns rendered in order (`Stream.tsx`).
Turn kinds currently implemented: `user-text`, `lumo-text`, `sale-card`.

Visual contract that makes generated UI read as *Lumo speaking*:
- Every assistant artifact — plain message or structured card — is preceded by the **LumoMark** in a
  12px-gap row. The user's turns are the only right-aligned, filled bubbles.
- Structured cards never use a bubble: they are white soft cards (radius 24px, soft shadow) occupying
  the assistant's column width (full width minus 18px mark minus 12px gap).
- Cards are separated from messages by the same 16px stream rhythm — no special spacing, so text and
  UI feel like one conversation.
- Structured cards are *stateful in place*: the same turn mutates `prepared → registered → undone`
  rather than appending a new card. History is therefore honest and compact.

Contracts:

| Contract | Visual form | State |
|---|---|---|
`sale prepared` | Sectioned soft card: status chip header, variant body, total row, payment chips, actions | interactive; blocks registration until a method is chosen |
`sale item` | Product Row: emoji thumb, name, qty × unit · unit price, subtotal | read-only |
`payment required` | "¿Cómo pagó?" hint + method chip group; primary action rendered disabled | resolves on chip select |
`clarification` | Plain Lumo message (e.g. "Puedo registrar ventas o responder sobre el negocio. Prueba con *385 tarjeta*.") | terminal |
`pending action` | `prepared` sale card left in the stream | resolves on Registrar / Corregir |
`warning` | Inline `--attention` text on a product row (`stock < 6` → "· atención") | passive; no card exists yet |
`daily summary` | Inicio narrative soft card + Hoy "Lumo observa" card (accent "Resumen" chip + 15px narrative) | passive |
`closing ready` | Hoy Action Card with gradient moon badge | toast placeholder |
`cash difference` | **Not implemented.** Nearest: "Estado de caja → Todo coincide / Sin movimientos" | — |
`success confirmation` | `registered` sale card: primary dot + "VENTA REGISTRADA" + amount · method + relative time | offers Deshacer while it is the last action |
`recommendation` | Suggestion / question chips above the composer | tappable, injects the text as a user turn |

Coexistence rules: the stream auto-scrolls to the newest turn (`scrollIntoView`, smooth, block end)
whenever the turn count changes. Only the most recent registered sale exposes "Deshacer".

---

## 6. LAYOUT SYSTEM

- **Content column**: centered, `max-width 420px`; primary design target **390px** (iPhone 14/15),
  holds down to 360px. Beyond 420px the column stays 420px on the same warm background (no desktop layout).
- **Horizontal margins**: 16px for card/stream content; 20px for text-only headers (Inicio greeting,
  Memoria/Negocio titles). Cards therefore span `viewport − 32px` and are never full-bleed.
- **Vertical rhythm**: screen top padding 24px (`pt-6`), 32px in onboarding; section stack 16px;
  card list 10–12px; in-card element gaps 4/6/8/12px; bottom content padding 16px before the sticky region.
- **Safe areas**: handled implicitly by `100dvh` plus footer `padding-bottom 4px` and tab-bar
  `padding-bottom 12px`. **No explicit `env(safe-area-inset-*)` usage** — Flutter should use real
  `SafeArea` insets and treat the 12px as additional padding.
- **Grid behavior**: single column everywhere except Hoy's secondary metric cards (1 col mobile,
  2 cols ≥640px, gap 12px) and Negocio's 2×2 business-facts grid inside one card (gap 16px).
- **Scrolling**: the whole content column scrolls as one; `overflow-x: hidden`. Chip rows are the only
  horizontal scrollers (hidden scrollbars). The stream is not a separate scroll view.
- **Sticky composer**: `position: sticky; bottom: 0`, above the tab bar in DOM order, background
  `#FCFAF4 @95%` + 8px blur, so content passes translucently underneath.
- **Bottom navigation**: also sticky at the bottom, 1px top hairline, same translucent background;
  always visible on Inicio/Hoy/Memoria/Negocio, hidden on onboarding and on pre-hydration states.
- **Bottom sheets**: none implemented. Toasts appear **top-center**.

---

## 7. INTERACTION STATES

| Component | Idle | Pressed | Focused | Selected | Loading | Disabled |
|---|---|---|---|---|---|---|
Tab item | muted icon/label, stroke 1.6 | no explicit press style | browser default outline | accent pill, foreground color, stroke 2.2, label 500 | n/a | n/a |
Composer input | placeholder muted | — | `outline: none` (ring-lumo shadow is permanent) | — | n/a | n/a |
Composer send | gradient + shadow-sm | — | default | — | none | replaced by Mic when empty; onboarding variant `opacity 0.4` |
Icon buttons (camera/mic) | muted | — | default | — | n/a | n/a |
Suggestion chip | white, border `#E3E6DE` | — | default | n/a | n/a | n/a |
Method chip | border `#E3E6DE`, text 80% | — | default | primary fill + light text | n/a | n/a |
Hover (pointer only) | chip border → teal/primary @50%, icon → foreground | — | — | — | — | — |
Primary button | gradient, white text | — | default | — | **none implemented** | `#EFEFE9` fill, muted text, no pointer feedback |
Outline button | 1px border, text 80% | — | default | — | none | n/a |
Memory action link | primary text | — | default | — | none | n/a |
Sale card | `prepared` | — | — | — | — | Registrar disabled until method chosen |

Success state = registered sale card (primary dot + label). Warning state = `--attention` inline text.
**No error state, no loading/skeleton state, and no explicit pressed/ripple styling exists.**
Pre-hydration screens render an empty shell (background only) rather than a skeleton.

---

## 8. MOTION

Explicitly implemented:
- Tailwind `transition` (all properties, 150ms, cubic-bezier(0.4,0,0.2,1)) on tab items, method chips,
  and the Registrar-venta button — i.e. color/fill cross-fades only.
- Smooth auto-scroll of the conversation to the newest turn: `scrollIntoView({behavior:"smooth", block:"end"})`.
- `tw-animate-css` is imported and sonner toasts animate with their library defaults (slide + fade
  from top-center).
- `backdrop-filter: blur(8px)` on sticky regions (static, not animated).

**Not implemented:** card entrance/appearance animation, typing or processing indicator, bottom-sheet
animation, loading spinner, haptic or ripple feedback, page transitions, gradient animation.
These should be treated as absent in the reference, not invented.

---

## 9. ASSETS

| Asset | Form | Path |
|---|---|---|
Lumo logo (`LumoMark`) | Inline SVG + CSS halo, no image file: 24-viewBox circle `r=9.5` stroked 2px with the ring gradient, plus a solid `#042C43` core `r=4.5`, over a blurred radial teal halo | `src/components/lumo/LumoMark.tsx` |
Icons | **Lucide** only: `Home`, `CalendarDays`, `Sparkles`, `Store`, `Camera`, `Mic`, `ArrowUp`, `Sparkle`, `Moon` | `lucide-react` |
Illustrations | none | — |
Product imagery | **Unicode emoji** as glyphs on accent tiles: 🍅 Tomate saladet, 🥬 Lechuga italiana, 🥕 Zanahoria, 🌿 Cilantro, 🥗 Espinaca, 🥑 Aguacate | `src/lib/demo-scenarios.ts` |
Fonts | Inter (400/500/600/700), Instrument Serif (regular + italic), Google Fonts CDN | `src/routes/__root.tsx` |
Favicon | `favicon.ico` | `public/favicon.ico` |

Demo catalogue reference values (unit / price MXN / stock): Tomate kg 30/42 · Lechuga pieza 28/4 ·
Zanahoria kg 20/18 · Cilantro manojo 12/3 · Espinaca bolsa 28/14 · Aguacate kg 55/22.
Scenarios: `esquina` ("La Esquina", tiendita de barrio, no catalogue) and `carrota` ("Carrota",
huerto urbano y sostenible, catalogue).

---

## 10. SCREEN INVENTORY

**Onboarding** (`/onboarding`) — no tab bar, no AppShell. Column `max-width 420px`,
`padding 16px, top 32px`. Header row: LumoMark 20px + "Lumo" 14px/500. Then conversational turns
(Lumo messages left, user bubbles right, 16px apart). Sticky bottom region
(`padding 16px, top 8px, bottom 24px`, translucent + blur) holds the pill input; at the final step
the input is replaced by a full-width gradient CTA "Empezar a hablar con {nombre}".
Steps: greet/name → type → ready → done (redirect to `/`).

**Inicio / Business Stream** (`/`) — header (eyebrow + serif gradient greeting) → narrative summary
soft card → conversation stream → sticky composer with suggestion chips → tab bar. Redirects to
onboarding when no business exists.

**Hoy** (`/hoy`) — hero metric card with bar chart → 2-up metric cards (Pagos / Estado de caja) →
"Lumo observa" narrative card with accent "Resumen" chip → horizontal question chips (only when
operations exist) → "Preparar el cierre del día" action card → composer (no chips) → tab bar.

**Memoria** (`/memoria`) — "MEMORIA" eyebrow + serif 26px title with the business name in gradient
italic → question chips → grouped memory cards (or an empty-state soft card centered, 14px muted) →
composer with the "Pregunta algo…" placeholder → tab bar.

**Negocio** (`/negocio`) — "NEGOCIO" eyebrow + serif 32px business name + 14px muted type → 2×2
facts card (Moneda MXN, Zona horaria CDMX, Pagos, Memoria Activa) → product list (catalogue
scenarios) or "Conceptos detectados" tag card (non-catalogue) → centered 11px uppercase
"Modo demostración" toggle revealing a soft card with the scenario switch and "Reiniciar onboarding"
→ tab bar. **No composer on this screen.**

**Conversational sale flow** — user turn → optional short Lumo message → prepared sale card
(amount / concepts / structured) → method selection → Registrar → the card becomes the registered
confirmation → optional Deshacer → undone card.

**Closing flow** — entry point only (action card + toast). No screen exists.

---

## 11. FLUTTER HANDOFF

### ColorTokens
```
background          #FCFAF4
surface             #FCFAF4
surfaceElevated     #FFFFFF
foreground          #0A140E
mutedForeground     #5C675D
primary             #267B4C
primaryForeground   #FCFAF4
secondary           #F1F3EB
secondaryForeground #0F1F14
muted               #EFEFE9
accent              #DAF2E6
accentForeground    #032110
border              #E3E6DE
input               #EAECE5
ring                #84BBAF
destructive         #DE3B3D
user                #267B4C
userForeground      #FCFAF4
attention           #D79628
attentionSoft       #FAE6BB
lumoTeal            #78D7D6
lumoLavender        #B1B0EF
markCore            #042C43
```

### GradientTokens
```
lumoText   [#36BABA 0%, #5EADE2 45%, #AE96DA 100%]  angle 100deg
lumoFill   [#5ECBCB 0%, #80A5E3 55%, #AE96DA 100%]  angle 100deg
markRing   [#5ECBCB, #9794E0]                       diagonal TL→BR
markHalo   radial #76E2E2 @90% → transparent 65%, blur 12, opacity 0.6
```

### TypographyTokens (family / size / weight / height-multiple / letterSpacing)
```
displayGreeting   InstrumentSerif italic 34 w400 1.05 -0.85px   (+ Inter 34 w400 for the name)
titleSerifLg      InstrumentSerif 32 w400 1.25
titleSerifMd      InstrumentSerif 26 w400 1.25
eyebrow           Inter 11 w400 1.5  +1.98px  UPPERCASE
sectionLabel      Inter 11 w400 1.5  +0.55px  UPPERCASE
body              Inter 15 w400 1.625
cardTitle         Inter 14 w500 1.5
cardTitleStrong   Inter 16 w600 1.5
metricHero        Inter 36 w600 1.0  -0.9px
metricLg          Inter 20 w600 1.5
metricSm          Inter 14 w600 1.5
fieldValue        Inter 16 w500 1.5
caption           Inter 12 w400 1.5
captionMicro      Inter 10 w400 1.5
buttonPrimary     Inter 14 w500 1.5
buttonSecondary   Inter 14 w400 1.5
chip              Inter 12 w400 1.5
statusChip        Inter 11 w500 1.5
navLabel          Inter 11 w400 1.5 (active w500)
input             Inter 14 w400 1.5
```

### SpacingTokens
```
xs 4  sm 8  smPlus 10  md 12  mdPlus 14  lg 16  xl 20  xxl 24  xxxl 32
screenPaddingH 16      headerPaddingH 20
cardPaddingStd 16/14   cardPaddingLg 20/16   cardPaddingHero 20/20
streamGap 16           listGap 10            gridGap 12           groupGap 24
```

### RadiusTokens
```
sm 12  md 14  lg 16  xl 20  xxl 24  xxxl 28  xxxxl 32  pill 999
card 24   userBubble 28   thumb 20   actionCard 24
```

### ShadowTokens
```
softCard  [ (0,1,0,   #DDDFD8 50%), (0,8,30, spread -18, #31503C 15%) ]
ringLumo  [ (0,0,0, spread 1, #A8D9D8 40%), (0,6,24, spread -12, #61AAC1 35%) ]
small     [ (0,1,2, #000000 5%) ]
```

### SizeTokens
```
contentMaxWidth 420   designWidth 390
composerHeight 44     composerIconButton 32   sendButton 36
navPill 56x36         navIcon 20              navBarHeight ~64
thumbSm 36            thumbMd 40              markSm 14  markMd 18  markLg 20
primaryButtonHeight 48  inCardButtonHeight 40  chipHeight 28  statusChipHeight 20
chartHeight 96        chartBarGap 6           chartMinBar 8%
```

### Suggested Flutter component mapping
| Flutter widget | Reference component |
|---|---|
`LumoScaffold` | `AppShell` — 420px column, canvas, sticky footer + nav slots |
`LumoBottomNavigation` | `TabBar` — 4 items, accent pill, stroke-weight swap |
`LumoComposer` | `Composer` — pill bar, ring-lumo shadow, camera/mic/send swap, chip row |
`LumoSuggestionChipRow` | horizontal chip scroller with "Sugerencias" label |
`LumoMessage` | `LumoMessage` — mark + 15px body, inline bold/italic |
`LumoUserMessage` | `UserBubble` — green pill, 85% max width |
`LumoAssistantSlot` | `LumoCardWrapper` — mark gutter for any generated card |
`LumoCard` | `.soft-card` base |
`LumoMetricCard` | Hoy hero + secondary metric cards |
`LumoSummaryCard` | Inicio narrative / "Lumo observa" |
`LumoSaleCard` | prepared / registered / undone sale card (3 states × 3 variants) |
`LumoSaleItemRow` | Product Row |
`LumoProductList` | Negocio product list |
`LumoMemoryCard` | Memoria card with action links |
`LumoTimelineGroup` | Memoria typographic group header |
`LumoActionCard` | "Preparar el cierre del día" |
`LumoActionChip` | suggestion / question chip |
`LumoStatusChip` | accent status chip |
`LumoSelectableChip` | payment method / scenario chip |
`LumoPrimaryButton` | gradient pill button + disabled variant |
`LumoSecondaryButton` | outline pill button (2 sizes) |
`LumoTextButton` | memory action link, demo toggle |
`LumoInputField` | onboarding pill input |
`LumoMark` | SVG logo + halo |
`LumoBarChart` | Hoy hourly bars |
`LumoToast` | top-center toast |
`LumoBottomSheet` | **new** — no reference implementation exists; design before building |

### Reproduction notes
- Do not introduce a dark theme, blue informational color, or new accent hue: the identity is
  warm off-white + forest green + the teal→lavender Lumo gradient only.
- The gradient is reserved for Lumo's own voice and primary commitment actions; never use it for
  ordinary surfaces or for the user's own content.
- Cards have shadows, not borders; borders appear only on hairlines, dividers and outline buttons.
- Assistant text has no bubble. That asymmetry (user = filled bubble, Lumo = bare text + mark) is the
  single most important pattern to preserve.
- Format money as `$` + `es-MX` thousands grouping, no decimals. Copy language is Spanish (`lang="es"`).
