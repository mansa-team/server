---
name: Mansa
description: B3 investing workstation — ledger-accurate wallet, market data, and a wallet-aware agent.
---

<!-- SEED: established with the user before implementation; re-run /impeccable document once there's code to capture the actual tokens and components. -->

# Design System: Mansa

## Overview

**Creative North Star: "The Abyssal Terminal"**

Mansa looks like an editorial trading desk sunk in deep water: a near-black abyss ground carries oversized Bodoni Moda statements with a single electric-yellow signal word, while dense fintech work (ledgers, screeners, TWR curves) runs underneath in quiet Geist Sans tables stamped with IBM Plex Mono technical labels. The waku.one reference is the attitude proof — monumental serif, tracked mono kickers, hairline grid, a terminal install bar, and a living particle field — translated from AI-memory marketing into a daily B3 workstation that must stay legible at 8px tabular numerals and hundreds of table rows.

The world spans two temperatures. Persuade surfaces (landing, empty states, onboarding) run drenched: deep-teal abyss, full particle currents, parallax depth, one yellow idea per viewport. Operate surfaces (wallet, screener, Orunmila chat) run restrained on the same ground: particles recede to a static ember field or off, parallax collapses to flat, and the yellow signal fires only on the primary action or the single most important figure. One world, two volumes — never two skins.

Motion is material, not decoration: scroll-driven parallax (particle field slowest, hairline grid mid, content at scroll speed) and pointer/scroll-reactive particle currents (lime drifting into yellow where attention concentrates) on persuade surfaces; orchestrated single-rise reveals; streaming shimmer confined to Orunmila's in-flight tokens; eased number transitions on summary equity only. Everything expensive is bounded (canvas pauses offscreen, particle counts cap by viewport, `prefers-reduced-motion` collapses all of it to static fades), and no motion ever touches data tables.

**Key Characteristics:**

- Abyssal dark-first: deep teal owns persuade grounds, near-black owns app grounds, off-white owns text.
- One-signal discipline: electric yellow marks exactly one idea per viewport, never data polarity.
- Editorial-meets-terminal type: Bodoni Moda monuments, Geist Sans work, Plex Mono evidence stamps.
- Matte noise + hairline grid: fine monochromatic grain over flat tonal steps, 1px structure lines, zero drop shadows.
- Currents, not confetti: particles flow like market depth — slow, directional, reactive — and vanish where work begins.

## Colors

Deep-water character: the ground does the work, greens carry meaning, yellow is reserved for the single decisive signal.

### Primary

- **Abyssal Teal** (#072824): persuade backgrounds, landing hero ground, marketing section fields. The drenched color — owns whole regions, never appears as small accents inside the app.
- **Terminal Black** (#141414): app background, chat and dashboard ground, the default surface once authenticated.
- **Signal Yellow** (#FFF95B): the one-signal accent. Primary CTA, active tab underline, hero signal word, Orunmila's streaming caret. Never encodes gain/loss, never fills large areas, never appears twice competing in one viewport.

### Secondary

- **Current Lime** (#94D251): gain, growth, positive variation, healthy Xango readings, particle-field drift color. The only positive-polarity hue.
- **Undergrowth Forest** (#439240): secondary accent for sustained/structural greens — allocation fills, progression baselines, tertiary chart series, focus rings on dark. Quieter than lime by design.
- **Drift Soft Lime** (#A1D958): hover lift on lime elements, particle highlight where currents concentrate, gain-glow state. Never a text color.

### Tertiary

- **Loss Signal** ([to be resolved during implementation]): the palette ships no loss hue. Constraint committed now: losses are never yellow and never any green in this system; resolution proposes one muted warm tone (clay/ember candidate) pending user approval, and until then losses render as dimmed off-white with directional glyphs, never color alone.

### Neutral

- **Ledger Off-White** (#F2F3EE): primary text, display type, table numerals on dark.
- **Noise Base** (#202020): textured card and panel ground with the monochromatic fine-grain finish (RGB variation ±7, low opacity, matte, no gradient, no scratches).
- **Rail Gray** (#292929): secondary surfaces — sidebar, input wells, terminal bars, table header wells.
- **Range Ink** (#1B1B1B–#272727, subtle): the permitted noise band; tonal steps between panels must stay inside it so depth reads as material, not shadow.

### Named Rules

- **The One-Signal Rule.** Electric yellow marks at most one idea per viewport. Its rarity is the point; a second yellow anywhere in the same viewport is a defect.
- **The Yellow-Is-Not-Data Rule.** Yellow never encodes gain, loss, rating, or chart polarity. Data polarity belongs to lime (up) and the resolved loss tone (down) only.
- **The Abyss Gradient Ban.** No linear gradients as backgrounds, no glow shadows, no glassmorphism. Depth comes from tonal steps, grain, hairlines, and parallax — never from painted light.

## Typography

**Display Font:** Bodoni Moda (user-pinned; with Georgia, serif fallback)
**Body Font:** Geist Sans (user-pinned; with system-ui, sans-serif fallback)
**Label/Mono Font:** IBM Plex Mono (user-pinned; with ui-monospace, monospace fallback)

**Character:** A financial broadsheet arguing with a terminal. Bodoni Moda supplies monumentality and editorial confidence at large sizes; Geist Sans does the invisible work of tables, forms, and chat; Plex Mono stamps provenance — tickers, kickers, timestamps, SSE states, code — in tracked uppercase. (Note on defaults: these faces are explicit user-pinned constraints from the brief, which beats the training-data-default caution; Bodoni is committed here for waku-class serif monumentality, not chosen as a generic editorial reflex.)

### Hierarchy

- **Display** (Bodoni Moda, 400–600, clamp(3rem, 8vw, 7rem), line-height 0.95–1.0): landing hero statements and empty-state monuments only. Title case or uppercase per surface; exactly one signal-yellow word per statement.
- **Headline** (Bodoni Moda, 500, clamp(1.75rem, 3.5vw, 2.75rem), line-height 1.05): section openers on persuade surfaces and wallet empty states. Never inside data tables.
- **Title** (Geist Sans, 600, 1.125–1.375rem, line-height 1.3): panel titles, card headers, chat session titles, screener column-group labels.
- **Body** (Geist Sans, 400–500, 0.875–1rem, line-height 1.55, max 65–75ch): explanations, chat prose, form help, Orunmila citations. Tabular numerals on for any inline figure.
- **Label** (IBM Plex Mono, 500, 0.6875–0.75rem, letter-spacing 0.12–0.18em, uppercase): kickers (`OWN YOUR WALLET`), field labels, ticker stamps, status pills, timestamps, TWR window tags, button micro-labels where terminal voice is required.

### Named Rules

- **The Numerals Rule.** Figures below 48px set in Geist Sans with tabular numerals, or Plex Mono for technical stamps. Bodoni numerals appear only in display-size hero figures; a Didone digit in a table is a defect.
- **The Kicker Rule.** Every persuade viewport opens with a mono uppercase kicker before its display line. Every operate panel opens with a title, never a kicker — kickers are arrival language, not furniture.
- **The Ticker-Stamp Rule.** Tickers (PETR4, VALE3) always render in Plex Mono uppercase with wide tracking, at any size, in any surface. A ticker in a proportional face is a defect.

## Layout

Spatial grammar is a hairline grid over the abyss: 12 columns on persuade surfaces (container max 1440px, 24px gutters, 80–120px section rhythm), collapsing to an app shell inside the product — left rail (nav + wallets), center work surface (tables, charts, chat stream), right inspector (position detail, Orunmila citations, workspace files) at ≥1280px; rail collapses to icon bar at 1024px, inspector becomes a sheet below 1024px, single column with bottom nav at 390px.

Density is two-speed: persuade sections alternate monumental display passages with quiet proof bands (terminal bar, stat strip, single chart), one idea per screen height; operate surfaces are compact (32–40px row heights, 12–16px panel padding, sticky table headers, virtualized beyond ~200 rows) with generous panel separation so density never reads as cramped. Spacing rides an 8pt rhythm (8/16/24/32/48/80), with more space above a heading than below it throughout.

The waku hairline device is structural: 1px vertical rules at 8–12% off-white divide hero columns and app regions; full-bleed section dividers carry the mono kicker of the next section. Parallax layers (particles behind, grid mid, content at speed) exist on persuade hero and section transitions only; operate surfaces are flat — sticky headers and the streaming chat affordance supply all the depth work needs.

Responsive invariants: the display line never wraps its signal word onto a line alone; the terminal/install bar goes full-width below 768px; tables scroll horizontally inside their panel with the first (ticker) column pinned; the Orunmila composer is thumb-reachable (bottom-docked) on mobile.

## Elevation & Depth

Flat by default, deep by motion and material. This system uses **tonal layering, not shadows**: Terminal Black → Noise Base panels → Rail Gray wells, separated by 1px hairlines and the matte grain finish. There are no drop shadows anywhere; the single permitted glow is a 0 0 24px rgba(255,249,91,0.25) halo on the primary CTA hover/focus and the streaming caret — signal light, not elevation.

Depth cues in order: (1) parallax drift on persuade surfaces, (2) particle current density, (3) tonal steps with grain, (4) hairline containment. Cards do not lift on hover; instead the hovered row or card brightens one tonal step and its hairline goes to 24% off-white. Focus is a 2px forest-green outline offset 2px (visible on black, distinct from the yellow signal). Modals and sheets sit on a 60% black scrim with no blur — grain stays legible behind them.

### Named Rules

- **The Flat-By-Default Rule.** Surfaces are flat at rest. Nothing casts a shadow; hover brightens tone, focus draws green, signal glows yellow — and nothing else emits light.
- **The Grain-Is-Material Rule.** Noise renders at low opacity over flat grounds only, never over photography, charts, or particle canvas. If the grain is visible in a screenshot thumbnail, it is too strong.

## Shapes

Form language is **sharp-terminal with editorial softness where hands land**: data surfaces, terminal bars, table wells, and code blocks are near-square (0–2px radius); touch controls — buttons, inputs, chips, toggles — take a small confident radius (6px); status pills and ticker stamps are full-round or 4px respectively and never anything in between. One geometry per job, no gradient of radii across a surface.

Borders are hairlines (1px, 8–12% off-white at rest, 24% on hover, forest green on focus); cards carry a border and tonal step but no top accent bar; charts are borderless inside bordered panels. Clipping is rectangular throughout — no blobs, arches, or many-vertex clip-path polygons; the particle canvas supplies all organic form. Buttons are solid (yellow primary on black text, lime-ghost secondary with lime hairline, gray tertiary), square-shouldered at 6px, with mono uppercase micro-labels at small sizes.

## Do's and Don'ts

Durable guardrails for every surface this world touches. (Components section omitted per seed mode — no components exist yet; canonical primitives land on the scan-mode re-run.)

### Do:

- **Do** give every persuade viewport exactly one yellow idea — one signal word, one CTA, or one live figure, never two.
- **Do** set tickers, timestamps, and system states in Plex Mono uppercase; set every number a user might compare in tabular figures.
- **Do** collapse particles and parallax to static on operate surfaces, on `prefers-reduced-motion`, and whenever the viewport is narrower than 768px — the abyss stays, the weather goes.
- **Do** build chat (assistant-ui) and fintech (shadcn-fintech charts/tables) on shadcn/ui primitives so the terminal voice and the data voice share radius, hairlines, and focus behavior.
- **Do** design empty, loading, stale-cache (503), quota (429), and offline states as first-class surfaces in this world's voice — the abyss admits what it does not know.

### Don't:

- **Don't** use yellow for gains, losses, ratings, or chart series — ever. Lime is up, the resolved warm tone is down, yellow is signal.
- **Don't** place Bodoni below 28px or inside tables, forms, or chat prose. Display type monuments; it does not work.
- **Don't** add gradients, glass blur, drop shadows, glow text, or generic icon-tile illustrations where authored evidence (a real position, a real TWR curve, a real Orunmila citation) belongs.
- **Don't** animate tables, tickers, or live prices beyond the crossfade on update; streaming shimmer belongs to in-flight chat tokens only.
- **Don't** invent commercial claims, testimonials, benchmarks, or performance figures for persuade surfaces — author synthetic demonstration data at full fidelity and label it synthetic.
