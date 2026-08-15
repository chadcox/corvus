---
name: Corvus
description: Offline forensic triage review platform — a lit workbench in a dark lab, where only the evidence carries color.
colors:
  bench-black: "#06080f"
  bg-elevated: "#0a0e18"
  surface: "rgba(19, 26, 42, 0.96)"
  surface-2: "rgba(25, 35, 56, 0.98)"
  surface-3: "rgba(36, 50, 72, 0.98)"
  surface-hover: "rgba(31, 43, 68, 0.98)"
  border: "rgba(148, 163, 184, 0.18)"
  border-strong: "rgba(148, 163, 184, 0.32)"
  bone: "#e5e7eb"
  bone-soft: "#cbd5e1"
  cold-slate: "#94a3b8"
  instrument-blue: "#2563eb"
  instrument-blue-hover: "#1d4ed8"
  instrument-blue-bright: "#60a5fa"
  instrument-blue-dim: "rgba(37, 99, 235, 0.16)"
  instrument-blue-border: "rgba(37, 99, 235, 0.44)"
  trace-cyan: "#22d3ee"
  trace-cyan-dim: "rgba(34, 211, 238, 0.12)"
  success: "#10b981"
  success-dim: "rgba(16, 185, 129, 0.14)"
  warn: "#f59e0b"
  warn-dim: "rgba(245, 158, 11, 0.14)"
  danger: "#ef4444"
  danger-dim: "rgba(239, 68, 68, 0.14)"
  critical: "#ef4444"
  critical-dim: "rgba(239, 68, 68, 0.16)"
  high: "#f97316"
  high-dim: "rgba(249, 115, 22, 0.16)"
  medium: "#eab308"
  medium-dim: "rgba(234, 179, 8, 0.16)"
  low: "#3b82f6"
  low-dim: "rgba(59, 130, 246, 0.14)"
  info: "#94a3b8"
  info-dim: "rgba(148, 163, 184, 0.14)"
typography:
  display:
    fontFamily: "Syne, system-ui, sans-serif"
    fontSize: "1.75rem"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "0"
  brand:
    fontFamily: "Syne, system-ui, sans-serif"
    fontSize: "1.125rem"
    fontWeight: 800
    lineHeight: 1.2
    letterSpacing: "0"
  title:
    fontFamily: "Syne, system-ui, sans-serif"
    fontSize: "0.9375rem"
    fontWeight: 700
    lineHeight: 1.3
    letterSpacing: "0"
  metric:
    fontFamily: "Syne, system-ui, sans-serif"
    fontSize: "1.7rem"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "0"
  body:
    fontFamily: "Libre Franklin, system-ui, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.55
    letterSpacing: "normal"
  body-small:
    fontFamily: "Libre Franklin, system-ui, sans-serif"
    fontSize: "0.8125rem"
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: "normal"
  control:
    fontFamily: "Libre Franklin, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "0.02em"
  label:
    fontFamily: "Red Hat Mono, Courier New, monospace"
    fontSize: "0.6875rem"
    fontWeight: 500
    lineHeight: 1.4
    letterSpacing: "0.1em"
  data:
    fontFamily: "Red Hat Mono, Courier New, monospace"
    fontSize: "0.8125rem"
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: "0"
rounded:
  sm: "4px"
  md: "6px"
  lg: "8px"
spacing:
  xs: "0.35rem"
  sm: "0.45rem"
  md: "0.65rem"
  lg: "1rem"
  xl: "1.25rem"
  2xl: "1.75rem"
components:
  button-primary:
    backgroundColor: "{colors.instrument-blue}"
    textColor: "#ffffff"
    typography: "{typography.control}"
    rounded: "{rounded.sm}"
    padding: "0.55rem 1.1rem"
  button-primary-hover:
    backgroundColor: "{colors.instrument-blue-hover}"
    textColor: "#ffffff"
  button-secondary:
    backgroundColor: "transparent"
    textColor: "{colors.bone-soft}"
    typography: "{typography.control}"
    rounded: "{rounded.sm}"
    padding: "0.55rem 1.1rem"
  button-secondary-hover:
    backgroundColor: "{colors.surface-2}"
    textColor: "{colors.bone}"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.cold-slate}"
    typography: "{typography.control}"
    rounded: "{rounded.sm}"
    padding: "0.35rem 0.6rem"
  button-ghost-hover:
    backgroundColor: "{colors.danger-dim}"
    textColor: "{colors.danger}"
  button-danger:
    backgroundColor: "{colors.danger}"
    textColor: "#ffffff"
    typography: "{typography.control}"
    rounded: "{rounded.sm}"
    padding: "0.55rem 1.1rem"
  input:
    backgroundColor: "{colors.bg-elevated}"
    textColor: "{colors.bone}"
    typography: "{typography.control}"
    rounded: "{rounded.sm}"
    padding: "0.55rem 0.75rem"
  panel:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.bone}"
    rounded: "{rounded.lg}"
    padding: "1.25rem"
  stat-card:
    backgroundColor: "{colors.surface-2}"
    textColor: "{colors.bone}"
    rounded: "{rounded.md}"
    padding: "0.95rem 0.85rem"
  view-tab:
    backgroundColor: "transparent"
    textColor: "{colors.cold-slate}"
    typography: "{typography.control}"
    rounded: "{rounded.md}"
    padding: "0.8rem 1rem"
  view-tab-active:
    backgroundColor: "{colors.instrument-blue-dim}"
    textColor: "{colors.bone}"
  status-badge:
    backgroundColor: "{colors.success-dim}"
    textColor: "{colors.success}"
    typography: "{typography.label}"
    rounded: "{rounded.sm}"
    padding: "0.2rem 0.55rem"
  severity-badge:
    backgroundColor: "{colors.critical-dim}"
    textColor: "#fecaca"
    typography: "{typography.label}"
    rounded: "{rounded.sm}"
    padding: "0.3rem 0.55rem"
---

# Design System: Corvus

## Overview

**Creative North Star: "The Evidence Bench"**

Corvus is a lit workbench in a dark room. The interface is the bench — matte, cold, unremarkable on purpose — and the artifact under examination is the only thing allowed to hold light. Every surface decision follows from that: a near-black `#06080f` canvas, translucent slate panels that read as machined trays rather than floating cards, hairline borders instead of drop shadows, and exactly one accent hue for interaction. When an analyst looks at a Corvus screen at hour six of a triage, the chrome should have receded entirely and the timeline rows, hashes, and paths should be the only things visible.

The mood is quiet, exacting, and unsentimental. This is a tool that presents parsed forensic output and states plainly when parsing was partial — so the visual system never smooths anything over, never implies confidence it doesn't have, and never dramatizes a finding. Density is high and deliberate: 15px body text, 0.8125rem table rows, 0.6875rem monospace labels, 0.45–1rem gaps. Whitespace is spent on separating investigative regions, not on making the product feel airy. The confirmed anti-reference is the gamified "hacker" dashboard — neon grid backgrounds, glow-for-glow's-sake, animated scan lines, terminal-green. Corvus is instrumentation, not theater.

The typographic pairing does the personality work that color refuses to: Syne, a geometric display face with unusual widths, carries titles and metrics; Libre Franklin carries prose; Red Hat Mono carries every machine-produced value. The result is a workspace that is technical without cosplaying as a terminal.

**Key Characteristics:**
- Near-black canvas with a four-step translucent slate surface ladder; depth by tone, not by shadow.
- One accent hue (Instrument Blue) for all interaction; cyan for links and pivots.
- Red/orange/yellow are reserved for severity and job status — nowhere else.
- Monospace, uppercase, letter-spaced micro-labels as the recurring texture.
- Tight 4/6/8px radii, 1px hairline borders, 0.12–0.15s transitions.
- Tabular numerics on every metric; nothing about a count should shift as it updates.

## Colors

A cold, low-chroma workspace palette: near-black ground, blue-grey slate surfaces, a single saturated blue for interaction, and a strictly quarantined warm range for severity.

### Primary
- **Instrument Blue** (`#2563eb`): The only interaction color. Primary buttons, active view tabs, active stat-card rails, focus borders, progress fill. Its dim form `rgba(37, 99, 235, 0.16)` fills active states; its border form `rgba(37, 99, 235, 0.44)` outlines them.
- **Instrument Blue Hover** (`#1d4ed8`): Primary-button hover background; darker than the resting blue so white control text keeps at least AA contrast.
- **Instrument Blue Bright** (`#60a5fa`): Link hover, focus ring, and `.section-label` micro-headings — the one place the accent is used as text at rest.

### Secondary
- **Trace Cyan** (`#22d3ee`): Links and cross-view pivots — the "follow this into another view" color. Distinct from the accent so a navigable trace never reads as a button.

### Neutral
- **Bench Black** (`#06080f`): The application ground. Everything sits on it; nothing else uses it.
- **Bench Black Elevated** (`#0a0e18`): Input and select fields, progress tracks — recessed wells, darker than the panel they sit in.
- **Tray Slate** (`rgba(19, 26, 42, 0.96)`): The panel surface. Translucent so the ground shows through and panels read as seated on the bench.
- **Tray Slate Raised** (`rgba(25, 35, 56, 0.98)`), **Tray Slate High** (`rgba(36, 50, 72, 0.98)`), **Tray Slate Hover** (`rgba(31, 43, 68, 0.98)`): The nesting ladder — stat cards and table row hovers, selected rows, and pointer feedback respectively.
- **Hairline** (`rgba(148, 163, 184, 0.18)`) and **Hairline Strong** (`rgba(148, 163, 184, 0.32)`): Every border and divider in the product. Alpha, never solid, so borders sit under the content rather than boxing it.
- **Bone** (`#e5e7eb`): Primary text. **Bone Soft** (`#cbd5e1`): Panel titles and secondary controls. **Cold Slate** (`#94a3b8`): Muted metadata, table headers, placeholders, disabled states.

### Severity & Status
- **Critical / Danger** (`#ef4444`), **High** (`#f97316`), **Medium** (`#eab308`), **Low** (`#3b82f6`), **Informational** (`#94a3b8`): Detection severity. Each pairs a `-dim` tint background with a pale text value (`#fecaca`, `#fed7aa`, `#fef08a`, `#bfdbfe`) so badges stay legible at 0.72rem on dark.
- **Success** (`#10b981`) and **Warn** (`#f59e0b`): Ingest job status only — completed, running/pending, failed.

### Named Rules
**The Reserved Channel Rule.** Red, orange, and yellow carry exactly two meanings in Corvus: detection severity and job/system status. They are never a brand accent, never a chart palette, never decoration. If a new surface needs emphasis, it uses Instrument Blue or it uses none.

**The One Accent Rule.** `--accent` is an alias of `--primary`, and it stays that way. Corvus has a single interaction hue; introducing a second one splits the analyst's attention model between "this is clickable" and "this matters."

## Typography

**Display Font:** Syne (with `system-ui, sans-serif`) — weights 600/700/800
**Body Font:** Libre Franklin (with `system-ui, sans-serif`) — weights 400/500/600
**Label/Mono Font:** Red Hat Mono (with `Courier New, monospace`) — weights 400/500

**Character:** Syne's geometric, slightly irregular widths give headings a built, engineered quality without any decorative flourish; Libre Franklin underneath is neutral and highly legible at small sizes; Red Hat Mono handles the constant stream of hashes, paths, timestamps, and IDs. Technical, not terminal.

### Hierarchy
- **Page Title** (Syne 700, 1.75rem, ls 0): Case and list page headings. One per screen.
- **Brand** (Syne 800, 1.125rem, ls 0): The header wordmark, beside the 28px raven mark.
- **Metric** (Syne 700, 1.7rem, line-height 1.2, `tabular-nums`): Stat card values.
- **Panel Title** (Syne 700, 0.9375rem, `--text-soft`): Every `.panel h2`. Small on purpose — panels are labeled, not announced.
- **Body** (Libre Franklin 400, 15px base, line-height 1.55): Prose and descriptions; page subtitles capped at `52ch`.
- **Body Small** (Libre Franklin 400, 0.8125rem): Panel descriptions, table cells, the working density of the product.
- **Control** (Libre Franklin 600, 0.875rem, ls 0.02em): Buttons, inputs, tabs.
- **Section Label** (Red Hat Mono 500, 0.6875rem, ls 0.1em, uppercase, Instrument Blue Bright): Region markers above grouped content.
- **Micro Label** (Red Hat Mono 500, 0.6875rem, ls 0.06em, uppercase): Status badges, table headers, the header environment badge.
- **Data** (Red Hat Mono 400, 0.8125rem, ls 0): Hashes, paths, timestamps, artifact identifiers.

### Named Rules
**The Machine Voice Rule.** Monospace means "a machine produced this value." Hashes, paths, timestamps, IDs, statuses, and enum labels are mono; human prose never is. Mono is also the only face that gets uppercased and letter-spaced — a mono micro-label is how Corvus marks a boundary between regions.

## Layout

A sticky 56px header (`rgba(11, 16, 32, 0.92)` with `blur(12px)`) sits above a single scrolling main column padded `1.75rem 1.5rem 3rem`. The case workspace is a two-column grid — `300px minmax(0, 1fr)` with a 1.25rem gutter — where the left column is a sticky sidebar (`top: calc(var(--header-height) + 1rem)`, capped at `--sidebar-width: 320px`) holding case metadata, ingest status, and stats, and the right column holds the active view. Below 1024px the grid collapses to one column and the sidebar goes static.

Spacing runs on a rem rhythm rather than a strict 8pt grid: `0.35 / 0.45 / 0.65 / 1 / 1.25 / 1.75rem`, with 1rem, 0.5rem, 0.45rem, and 0.35rem carrying most of the load. Panels pad 1.25rem; sidebar panels tighten to `0.7rem 0.45rem` on stat cards and 0.45rem gaps. Grids use `minmax(0, 1fr)` everywhere so long paths and hashes can't blow out a column — `overflow-wrap: anywhere` and `table-layout: fixed` are the standing defenses. Stat strips are 2×2 in the sidebar and 4-up in main content; the sidebar variant is pinned to two columns by an explicit override and must stay that way.

Responsive breakpoints in use: 1180px, 1100px, 1024px (the workspace collapse), 960px, and 900px. There is no mobile-first layer — Corvus is a desk tool and the layouts degrade downward rather than reflow for phones.

## Elevation & Depth

Corvus is tonal-first. Depth comes from the surface ladder — ground `#06080f`, panel `rgba(19,26,42,0.96)`, raised `rgba(25,35,56,0.98)`, high `rgba(36,50,72,0.98)` — plus 1px alpha hairlines. There is exactly one ambient shadow in the system and it does one job: seating panels on the bench. Everything else that reads as "raised" is a lighter translucent surface, not a cast shadow. Glow is a state signal, never decoration.

### Shadow Vocabulary
- **Panel seat** (`box-shadow: 0 10px 28px rgba(0, 0, 0, 0.28)`): Ambient, applied to `.panel` only. Soft and low-contrast — you should notice the panel edge, not the shadow.
- **Focus ring** (`box-shadow: 0 0 0 3px #60a5fa`): The universal keyboard-focus ring on buttons and inputs. Danger controls use the solid danger hue.
- **Active rail** (`box-shadow: inset 3px 0 0 var(--primary)` on cards, `inset 0 -3px 0 var(--primary)` on tabs): Selection is marked by an inset rail, not by lifting the element.

### Named Rules
**The Flat-By-Default Rule.** Surfaces are flat at rest. Shadow appears only as ambient panel seating or as a response to state — focus, hover, selection. Nothing in Corvus floats to show importance; it changes tone.

## Shapes

A tight, machined radius scale: 4px on controls (buttons, inputs, badges, chips), 6px on interior blocks (stat cards, tabs, list rows), 8px on panels and tab bars. Nothing is pill-shaped and nothing is square — the radii are small enough to read as milled edges rather than as softness. Progress tracks are the one exception at 2px, and the brand mark is the only free-form silhouette in the product.

Borders are 1px alpha slate, applied nearly universally; a Corvus element is defined by its outline plus its surface tone, which is why the shadow budget can stay at one. Selection and active state are expressed as 3px inset rails on the leading or bottom edge — a consistent, non-lifting way to say "you are here."

## Components

Components should feel **tactile and responsive**: every control acknowledges input — a 1px press translate, a 3px focus glow, a tone shift on hover — while staying visually restrained. Fast (0.1–0.15s), small, and physical, never bouncy.

### Buttons
- **Shape:** 4px radius (`--radius-sm`), no border on the primary.
- **Primary:** Instrument Blue `#2563eb` on white text, `0.55rem 1.1rem`, Libre Franklin 600 / 0.875rem / ls 0.02em.
- **Hover / Focus:** hover darkens to `#1d4ed8`; keyboard focus adds a `0 0 0 3px #60a5fa` ring; `:active` translates 1px down; `:disabled` drops to 0.45 opacity with `not-allowed`.
- **Secondary:** transparent on a `rgba(148,163,184,0.32)` hairline with `--text-soft` label; hover fills `--surface-2` and shifts the border to accent-dim; keyboard focus keeps the universal ring.
- **Ghost:** transparent, borderless, muted, `0.35rem 0.6rem` — and notably hovers to `--danger` on `--danger-dim`, because ghost is the destructive-adjacent slot (remove, clear, delete).
- **Danger:** solid `#ef4444`, white text, red-tinted focus ring.

### Chips / Badges
- **Status badge:** mono 0.6875rem uppercase, ls 0.06em, `0.2rem 0.55rem`, 4px radius, `-dim` tint background with a pale text color and a matching border. Completed → success, partial/running/pending → warn, failed → danger.
- **Severity badge:** mono 0.72rem 700 uppercase, `0.3rem 0.55rem`, `-dim` background with a pale text value and a 45%-alpha border of the severity hue; informational falls back to `--text-soft` on `--info-dim`.
- **State:** badges are read-only labels. Filter chips that toggle use the stat-card action pattern (accent-dim fill + inset rail), not badge styling.

### Cards / Containers
- **Corner Style:** 8px on `.panel`, 6px on `.stat-card`.
- **Background:** `rgba(19,26,42,0.96)` for panels, `rgba(25,35,56,0.98)` for stat cards nested inside them.
- **Shadow Strategy:** panel seat only (see Elevation); stat cards get none.
- **Border:** 1px `rgba(148,163,184,0.18)`, strengthening to `--border-strong` on interactive hover.
- **Internal Padding:** 1.25rem panels, `0.95rem 0.85rem` stat cards, `0.7rem 0.45rem` in the sidebar. Panel titles sit 0.85rem above their content; `.panel-desc` pulls up `-0.5rem` to stay tied to its heading.
- **Interactive cards:** `button.stat-card--action` keeps card geometry, adds `border-color/background/box-shadow` transitions at 0.15s, a 2px accent focus outline at 2px offset, and an `inset 3px 0 0 var(--primary)` rail plus accent-dim fill when active.

### Inputs / Fields
- **Style:** recessed — `#0a0e18` well inside a `--border` hairline, 4px radius, `0.55rem 0.75rem`, 0.875rem text.
- **Focus:** outline removed, border shifts to `rgba(59,130,246,0.44)`, 3px accent-dim ring. Transition `border-color 0.15s, box-shadow 0.15s`.
- **Placeholder:** `--muted`. Disabled follows the button convention (0.45 opacity).

### Navigation
- **Header:** sticky, 56px, translucent `rgba(11,16,32,0.92)` with 12px backdrop blur and a bottom hairline. Syne 800 wordmark + 28px mark, a 20px vertical divider, an uppercase tracked tagline, then right-aligned mono environment badge.
- **View tabs:** the primary navigation for Timeline / Objects / Disk / MFT / Browser. A `.view-tabs` bar (panel surface, 8px radius, 0.45rem padding) holds equal-flex tabs at `0.8rem 1rem`, 6px radius, muted label. Hover fills `--surface-hover` and brightens the label; active fills `--primary-dim`, takes an accent border, brightens to `--text`, and gains `inset 0 -3px 0 var(--primary)`. Tab icons ride at 1rem / 0.85 opacity.
- **Links:** Trace Cyan by default, `--accent-bright` on hover, no underline.

### Data Table (signature)
The densest and most-used surface in the product. `table-layout: fixed`, 0.8125rem body, mono uppercase 0.6875rem headers in `--muted` with 0.06em tracking, `0.55rem 0.65rem` cells, and 1px `--border` row separators. Clickable rows hover to `--surface-2` over a 0.12s transition; path columns drop to 0.6875rem muted with `overflow-wrap: anywhere` and a 420px cap. Fixed first/second column widths (34% / 6.5rem) keep artifact names and timestamps aligned across every view.

### Motion
Four keyframes carry all of it: `fadeUp` (0.55s `cubic-bezier(0.22, 1, 0.36, 1)`, staggered 0.06s per `.animate-in-delay-*` step) for content entrance, `fadeIn`, `pulse-glow` for live/processing state, and `progress-indeterminate` for unknown-duration ingest. State transitions are 0.1–0.15s; nothing else animates.

## Do's and Don'ts

### Do:
- **Do** build depth with the surface ladder — `--surface` → `--surface-2` → `--surface-3` — and 1px alpha hairlines, per the Flat-By-Default Rule.
- **Do** use Instrument Blue for every interactive affordance and Trace Cyan for cross-view pivots; keep `--accent` aliased to `--primary`.
- **Do** mark selection with a 3px inset rail (`inset 3px 0 0` on cards, `inset 0 -3px 0` on tabs) plus a `--primary-dim` fill.
- **Do** set machine-produced values in Red Hat Mono, and uppercase + track (0.06–0.1em) any mono label.
- **Do** apply `tabular-nums` to every count, size, and offset so numbers don't jitter as they refresh.
- **Do** defend against long paths and hashes: `minmax(0, 1fr)` grid tracks, `min-width: 0`, `overflow-wrap: anywhere`, `table-layout: fixed`.
- **Do** keep the focus ring at `0 0 0 3px` accent-dim on controls, and `2px solid var(--accent)` at 2px offset on card-shaped buttons.
- **Do** state partial or failed parsing in the UI with the warn/danger status badges rather than hiding the gap.

### Don't:
- **Don't** use red, orange, or yellow for anything but detection severity or job/system status — the Reserved Channel Rule.
- **Don't** add a second accent hue, a gradient, or a neon "hacker dashboard" treatment: no glow grids, scan lines, or terminal-green.
- **Don't** introduce new shadow values. There is one ambient shadow (`0 10px 28px rgba(0,0,0,0.28)`) and one focus ring; elevate with tone instead.
- **Don't** set prose in monospace, or uppercase a proportional face beyond the existing tagline treatment.
- **Don't** exceed the 4 / 6 / 8px radius scale — no pills, no fully square panels.
- **Don't** widen the sidebar stat strip beyond two columns; `.case-sidebar .stats-strip` is pinned to 2×2 for a 300px column.
- **Don't** rename the five view labels — Timeline, Objects, Disk, MFT, Browser are product vocabulary, not design copy.
- **Don't** animate beyond the four defined keyframes or push state transitions past 0.15s; the interface should feel immediate, not choreographed.
