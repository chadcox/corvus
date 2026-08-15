# Corvus UI Redesign — Implementation Blueprint

**Status:** Specification only. Nothing in this document has been implemented.
**Audience:** The implementation agent. Read this entire document before touching any file.
**Scope:** `apps/web` presentation and UX only. No API contract, route, or backend changes.

This blueprint is based on direct inspection of the repository as of this writing. All file
paths, component names, CSS class names, and Playwright selectors referenced below are the
real ones in the codebase — do not invent parallel ones.

Ground truth about the current app (verified, do not re-derive incorrectly):

- Routes (in `apps/web/src/App.tsx`): `/login`, `/` (CasesPage), `/cases/:caseId`
  (CaseDetailPage), `/admin/users` (AdminUsersPage), `/admin/control-panel`
  (ControlPanelPage), `*` (NotFoundPage inline in App.tsx).
- There are **no separate routes** for Timeline/Objects/Disk/Browser — they are tabs inside
  `CaseDetailPage` (`type Tab = "timeline" | "object" | "disk" | "mft" | "browser"`).
- Detections are a **sidebar panel** (`SigmaFindingsPanel`), not a page.
- Evidence Sources and Ingest Jobs live in the CaseDetailPage **sidebar** (source card list,
  upload zone, ingest history modal, `IngestStatusPanel`).
- There is **no Settings page**. Do not create one (see §21, P3).
- Styling is two global stylesheets: `src/index.css` (design tokens + base) and
  `src/App.css` (~2,900 lines of component classes). No CSS modules, no Tailwind, no
  component library. State is plain `useState` + the `api` object in `src/api/client.ts`.
- Fonts via `@fontsource`: Syne (display), Libre Franklin (body), Red Hat Mono (mono).
- Virtualization: `@tanstack/react-virtual` in `TimelineView` only.
- E2E: Playwright specs in `apps/web/e2e/` including `screenshots.spec.ts` which writes
  README screenshots to `docs/screenshots/`.

---

## 1. Executive Design Direction

### The target feeling

A mature professional DFIR investigation workstation. The reference class is tooling like
Timeline Explorer, X-Ways, Velociraptor's GUI at its best, and IDE-grade density — not a
SaaS marketing dashboard. An analyst spends 8 hours in this UI scanning tens of thousands
of rows; every design decision optimizes for scanability, information density, and calm.

### Design philosophy

1. **Data is the interface.** Chrome (headers, panels, decorations) recedes; timestamps,
   paths, hashes, and event summaries dominate. Monospace is a first-class citizen.
2. **Density over whitespace.** Default row height 28px, body text 13–14px. An analyst
   should see 25–30 timeline rows per screen, not 6 cards.
3. **Color is signal, never decoration.** The only saturated colors on screen are severity
   markers, status states, and the single interactive accent. Everything else is a neutral
   gray ramp.
4. **Flat, bordered surfaces.** Panels are separated by 1px borders and small background
   steps, not shadows, glows, or elevation theatrics.
5. **Stillness.** No entrance animations, no glow pulses, no fade-up cascades. State changes
   are instant; the only motion is a subtle skeleton shimmer while loading and ≤120ms
   opacity/color transitions on hover/focus.
6. **Every value is actionable.** Hostnames, paths, hashes, IPs, and rule names are pivot
   points — visually marked as such and consistently interactive (see §7).

### What changes at a glance (delta from current UI)

- **Remove** the Syne display font, the `animate-in` fadeUp cascade, `pulse-glow`,
  glow box-shadows (`--shadow-glow`, `--accent-glow`), the Cases page hero, cyan link
  color, and translucent rgba surfaces.
- **Replace** the 320px mixed-purpose case sidebar (upload + sources + actions + findings)
  with a slim navigation rail plus a dedicated context bar; evidence management becomes
  its own view instead of permanent sidebar furniture.
- **Promote** Detections, Evidence Sources, and an Overview to first-class workspace views
  alongside Timeline/Entities/Disk/MFT/Browser.
- **Flatten** typography: one body family (Libre Franklin), heavier use of Red Hat Mono for
  all forensic values, smaller and denser scale.
- **Unify** all tabular data on one table spec (§13) instead of the current mix of
  `.item-list`, `.browser-table`, `.mft-table`, `.data-table`, and card lists.

---

## 2. Current UI Audit

### 2.1 Global / shell (`App.tsx`, `index.css`, `App.css` "Shell" section)

- **Strengths:** Skip link exists; focus-visible styles exist; `prefers-reduced-motion`
  handled; dark theme baseline; token file already exists and is well-organized.
- **Problems:**
  - Syne is a geometric display face with decorative character — reads "crypto startup",
    not forensic tooling. Headings shout.
  - `animate-in` / `animate-in-delay-*` fadeUp on nearly every section makes each
    navigation feel like a slideshow; on a workstation this is friction, and it forces
    `animations: 'disabled'` workarounds in `screenshots.spec.ts`.
  - Links are cyan (`--cyan: #22d3ee`) against a blue accent — two competing accent hues.
  - Buttons glow on hover (`box-shadow: 0 0 0 3px var(--primary-dim)`) and translate on
    press — playful, not professional.
  - Surfaces are translucent rgba layers over a near-black blue (`#06080f`) — causes muddy
    blending and inconsistent perceived color depending on stacking.
  - The header tagline ("Investigation workspace" / "Forensic evidence review") is filler
    prose occupying prime real estate that should show case context.
- **Keep:** `.skip-link`, focus ring approach, reduced-motion block, skeleton pattern.

### 2.2 Cases page (`CasesPage.tsx`, "Cases page" CSS section)

- **Strengths:** Skeleton cards prevent reflow; create-case flow is simple; empty state exists.
- **Problems:**
  - `.cases-hero` with `page-title`/`page-subtitle` ("Digital forensics…") is marketing
    copy inside a tool the analyst already chose to open. Wasted vertical space.
  - Cases render as a `.cases-grid` of `.case-card`s. Cards give every case equal massive
    weight, waste space, and don't scale past ~12 cases. Case metadata (id, evidence count,
    OS badges, dates) is scattered across card corners.
  - Card hover affordance for "open case" competes with inline rename/delete affordances.
- **Redesign:** Replace the card grid with a dense case **table** (name, id, evidence
  sources, platforms, status, created, last activity, row actions). Keep create-case as a
  compact toolbar action + small dialog, not an always-visible form.

### 2.3 Case workspace shell (`CaseDetailPage.tsx`, `.case-workspace`, `.case-sidebar`)

- **Strengths:** Everything an analyst needs is reachable; stat cards pivot into views
  (good instinct — keep the *behavior*); source selector concept is right; ingest status
  surfaces diagnostics.
- **Problems:**
  - The 320px `.case-sidebar` permanently hosts: back link, editable case name, an entire
    upload panel with drop zone, evidence source card list, an Actions panel, and the
    Findings (Sigma) panel. This is four different jobs pinned open at all times. Upload —
    an occasional task — costs more permanent pixels than Detections.
  - Findings (detections) — one of the most important investigation surfaces — is squeezed
    into a ~300px sidebar column with pagination in miniature.
  - View tabs (`.view-tabs` with `.view-tab` buttons) sit inside the main column below the
    stats strip; the hierarchy Case → Source → View is not spatially expressed anywhere.
  - The stats strip (`.stats-strip`, `.stat-card--action`) uses large KPI cards as both
    display and navigation — the "AI dashboard" pattern this redesign removes. The pivot
    behavior is good; the presentation must shrink to a compact strip.
  - Case Summary panel (`.case-summary-panel`, `.summary-kpis`, severity counts, top
    categories/hosts) appears above the tabs, pushing actual evidence below the fold.
  - Source info and ingest history are portal modals with mixed inline styles
    (`style={{ margin: 0 }}` etc.) — inconsistent spacing by construction.
- **Redesign:** See §4/§6.2. Navigation rail + context bar; overview becomes a view;
  upload/actions move into the Sources view; detections get a full view.

### 2.4 Timeline (`TimelineView.tsx`, `.item-list*`, `.virtual-list*`, `TimelineChart`)

- **Strengths:** Virtualized (`@tanstack/react-virtual`), server paging (PAGE_SIZE 10000)
  with placeholder rows, keyboard row navigation (`useRowNavigation`, `role="option"`),
  resizable split with accessible separator, density toggle, CSV export, histogram with
  zoom, Sigma-only toggle, UTC ISO timestamps in mono. The bones are genuinely good.
- **Problems:**
  - Rows are multi-line stacked blocks (est. 84px compact / 144px "analyst") — closer to a
    feed than a forensic timeline. Timestamp, title, subtitle, pivots, and meta all get
    near-equal weight; ~8–10 events visible per screen.
  - Detection state is a badge inside the timestamp line (`SigmaEventBadges`) plus a
    `.sigma-hit-row` background — easy to miss while scrolling; no persistent left-edge
    severity marker.
  - Filters are stacked inputs (`.filters-stack`, `.filters-row`) above the list, costing
    ~140px of vertical space always; `datetime-local` inputs are unlabeled visually.
  - The event detail pane header buries the artifact/type; entity pivot buttons
    (`.event-pivot-*`) render as loose chip groups without grouping labels' hierarchy.
  - "Loaded X of Y events" is centered prose below the list instead of a status-bar figure.
- **Redesign:** §8. Row becomes a single-line 28px grid row (two-line at 44px in analyst
  density) with a 2px severity edge; filters collapse into one 36px toolbar; counts move to
  a status line in the toolbar.

### 2.5 Entities / Object view (`ObjectView.tsx`)

- **Strengths:** Type filter + search; related timeline events with click-to-pivot; raw
  attributes JSON block; ResizableSplit reuse; keyboard navigation.
- **Problems:**
  - Entity list rows show display name + type badge only; count/context absent.
  - Detail pane is a flat stack: name, meta, related events, attributes `<pre>` JSON dump.
    The JSON dump gets equal billing with curated fields.
  - Related events cap at a fixed max-height ("200px" inline style) — arbitrary scroll trap.
  - No related-detections section even when the entity appears in Sigma hits.
- **Redesign:** §9.

### 2.6 Disk (`DiskView.tsx`, `.disk-*`)

- **Strengths:** Directory listing with search, file preview (hex/ascii grid), per-file
  hashes, focusPath pivot from other views works.
- **Problems:**
  - Navigation is listing-only (click into directories); current path is not a clickable
    breadcrumb trail; no tree panel for orientation.
  - Listing rows mix icon, name, size, timestamps without column alignment discipline.
  - Preview panel appears/disappears, reflowing the layout.
- **Redesign:** §10.

### 2.7 MFT (`MftView.tsx`, `.mft-*`)

- **Strengths:** Real `<table>` with sortable columns (`SortCol`), draggable column widths
  (`.col-resize-handle`), server pagination (SERVER_PAGE_SIZE 500), MACB detail panel,
  deleted-row treatment (`.mft-row-deleted`), scope note. This is the most "workstation"
  view already — treat it as the seed of the shared table spec.
- **Problems:** Visual style diverges from every other table; pagination controls and page
  info are bespoke (`.mft-pagination`, `.mft-page-info`); header sort affordance
  (`.sort-header`) differs from BrowserView's.
- **Redesign:** Restyle to the §13 table spec; keep all behavior.

### 2.8 Browser (`BrowserView.tsx`, `.browser-*`)

- **Strengths:** Category tabs (`.browser-category-tab`), sortable headers, URL/title/time
  columns, raw JSON details expander.
- **Problems:** Third distinct table style; URL truncation without tooltips; type pills
  (`.browser-type-pill`) restate the active category filter; detail is a `<details>` dump
  rather than an inspector consistent with Timeline's.
- **Redesign:** §11.

### 2.9 Detections (`SigmaFindingsPanel.tsx`, `.sigma-*`)

- **Strengths:** Search, pagination, severity classes (`.sigma-level-critical` … `-info`),
  view-event pivot into Timeline, engine tag (`.detection-engine-tag`), alert banner for
  critical findings.
- **Problems:** Lives in the 300px sidebar; detections wrap into cramped multi-line cards;
  severity is a colored word rather than a systematic badge; no grouping by rule; the
  alert banner (`.sigma-alert-banner`) is the loudest element in the whole app.
- **Redesign:** §12 + §6.7 — promote to a full workspace view with a rule-grouped table.

### 2.10 Ingest status & history (`IngestStatusPanel.tsx`, ingest history modal)

- **Strengths:** Progress with phase message, partial/coverage diagnostics list, compact
  variant, cancel with confirm.
- **Problems:** History is a modal stack of panels-inside-panels with inline styles; job
  status uses prose lines instead of a compact job table.
- **Redesign:** §6.9 — a Sources view section; history becomes a per-source job table in a
  drawer, not a modal of nested panels.

### 2.11 Control Panel (`ControlPanelPage.tsx`) and Admin Users (`AdminUsersPage.tsx`)

- **Strengths:** Real operational content: system status, rules status + sync
  (`SigmaRulesSync`), jobs queue with error filters, containers with logs, bulk case
  delete, search reindex, user management. Role gating works (`me.role`).
- **Problems:** Wall of `.panel`s of equal weight; status values as prose pairs
  (`.status-item`) rather than aligned label/value grids; container/job lists are bespoke
  lists, not tables; page has no internal navigation for its 6+ sections.
- **Redesign:** §6.10.

### 2.12 Login (`LoginPage.tsx`, `.login-*`)

- **Strengths:** Labeled fields, password visibility toggle, error alert.
- **Problems:** Centered floating panel with glow-era styling; brand presentation
  inconsistent with new restrained identity.
- **Redesign:** §6.12 — same structure, retoken; no functional change.

### 2.13 Global search (`GlobalSearch.tsx`)

- **Strengths:** Command-bar behavior with keyboard open, sections for
  timeline/filesystem/entities, disabled note until source is ready.
- **Problems:** Styled as an oversized rounded search pill; results panel typography
  inconsistent with new table spec.
- **Redesign:** Keep behavior; restyle as flat bordered popover per §13 typography. Move
  trigger into top bar (§4).

---

## 3. Global Design System Specification

All tokens live in `src/index.css` `:root`. The implementation agent must **replace the
existing token values in place** (same custom-property names wherever possible), because
~2,900 lines of App.css consume them. Add new tokens rather than renaming, and only delete
a token after removing its last consumer.

### 3.1 Colors

Neutral ramp is a desaturated gray (no blue cast). Surfaces are **opaque hex** — replace
all rgba surface tokens.

| Token | Value | Use | Don't use for |
|---|---|---|---|
| `--bg` | `#0e1013` | App background only | Panels, inputs |
| `--bg-elevated` | `#111418` | Input/select backgrounds, inset wells | Page background |
| `--surface` | `#14171c` | Panels, table containers, sidebar/nav | Hover states |
| `--surface-2` | `#191d23` | Table header rows, toolbars, modal headers | Body text areas |
| `--surface-3` | `#1f242b` | Popovers, menus, drawers, tooltips | Large page regions |
| `--surface-hover` | `#1b2026` | Row/nav hover fill | Selected state |
| `--border` | `#262b33` | Default 1px borders, table row separators | Text |
| `--border-strong` | `#39404b` | Panel outlines needing emphasis, control borders | Dividers inside tables |
| `--text` | `#d6dae0` | Primary text | Large fills |
| `--text-soft` | `#a7aeb8` | Secondary text, values-at-rest | Primary content |
| `--muted` | `#6c7683` | Metadata, placeholders, disabled text | Body copy |
| `--primary` | `#2f6fed` | Primary buttons, selected-tab underline, checkboxes | Text on dark, severity |
| `--primary-hover` | `#2861cf` | Primary button hover | — |
| `--primary-bright` | `#6ea8fe` | Links, interactive values, active icons | Backgrounds |
| `--primary-dim` | `#16233d` (opaque) | Selected row fill, active nav fill | Hover (use `--surface-hover`) |
| `--primary-border` | `#2f4a7d` | Selected row/nav left borders, focused input border | Static panel borders |
| `--focus-ring` | `#82b1ff` | 2px focus outlines everywhere | Anything decorative |
| `--cyan` | alias to `--primary-bright` | (kept so old CSS doesn't break; links become blue) | New code |
| `--success` | `#3fb950` | Completed status, health OK | Buttons |
| `--warn` | `#d29922` | Partial status, degraded health | Headings |
| `--danger` | `#f85149` | Errors, destructive buttons, failed status | Emphasis of non-error text |
| `--info` | `#8b949e` | Informational status | — |

Severity scale (dedicated tokens; keep names `--critical`, `--high`, `--medium`, `--low`,
`--info` and their `-dim` variants but change values):

| Severity | Token | Value | Dim fill (`*-dim`, opaque) |
|---|---|---|---|
| Critical | `--critical` | `#f85149` | `#2d1517` |
| High | `--high` | `#f0883e` | `#2b1c12` |
| Medium | `--medium` | `#d29922` | `#292112` |
| Low | `--low` | `#58a6ff` | `#14233a` |
| Informational | `--info` | `#8b949e` | `#1c2026` |

Delete after migration: `--accent-glow`, `--shadow-glow`, `--cyan-dim` (verify zero
consumers with grep first).

### 3.2 Typography

- Remove Syne entirely: delete the three `@fontsource/syne` imports in `src/main.tsx`,
  remove the dependency from `package.json`, change `--font-display` to alias
  `var(--font-body)` (keep the token so `.display` and any `--font-display` consumers
  degrade gracefully; then remove usages).
- `--font-body`: `"Libre Franklin", system-ui, sans-serif` (unchanged).
- `--font-mono`: `"Red Hat Mono", ui-monospace, "Courier New", monospace`.

Type scale (root `font-size` drops from 15px to 14px):

| Role | Size | Weight | Line height | Notes |
|---|---|---|---|---|
| Page title (h1) | 18px / 1.286rem | 600 | 1.3 | One per page, in page header |
| Panel/section title (h2) | 14px | 600 | 1.3 | Sentence case |
| Sub-headings (h3) | 13px | 600 | 1.3 | |
| Section label (`.section-label`, `.detail-section-label`) | 11px | 600 | 1.2 | UPPERCASE, letter-spacing 0.06em, `--muted` |
| Body | 14px | 400 | 1.5 | |
| Table cells / dense UI | 13px | 400 | 1.4 | |
| Metadata / captions | 12px | 400 | 1.35 | `--text-soft` or `--muted` |
| Mono values (`.mono`) | 12.5px | 400 | 1.4 | letter-spacing 0 |
| Mono small (hashes, ids in tables) | 12px | 400 | 1.35 | |
| Buttons/inputs | 13px | 500 | 1 | letter-spacing 0 (remove current 0.02em) |

Numerals in tables: add `font-variant-numeric: tabular-nums` on table/mono contexts.

### 3.3 Spacing

4px base grid. Define as tokens and use them when rewriting CSS sections:

```
--space-xs: 4px;  --space-sm: 8px;  --space-md: 12px;
--space-lg: 16px; --space-xl: 24px; --space-2xl: 32px;
```

Rules: panel padding `--space-md` (12px, down from ~20px); toolbar internal gap
`--space-sm`; page content padding `--space-lg`; vertical rhythm between panels
`--space-md`. Never hand-write pixel margins in JSX `style={}` — every inline spacing
style currently in CaseDetailPage/SigmaFindingsPanel/TimelineView must move into classes.

### 3.4 Borders

- Standard: `1px solid var(--border)`.
- Dividers (table rows, list items): `1px solid var(--border)` — same token; do not invent
  a lighter one.
- Selected: `1px solid var(--primary-border)` + 2px left accent where specified.
- Focus: `2px solid var(--focus-ring)` via `outline`, offset 1–2px. Replace all
  `box-shadow: 0 0 0 3px …` focus/hover styles with outlines.
- Severity: 2px **left** border on rows/detail headers using the severity color.

### 3.5 Radius

```
--radius-sm: 2px;  /* buttons, inputs, badges, table container corners */
--radius:    3px;  /* panels */
--radius-lg: 4px;  /* modals, drawers, popovers — the maximum anywhere */
```

No pills, no circles except the 8px status dot (§5) and spinner.

### 3.6 Shadows

Allowed only on: modals/dialogs, drawers, popovers/menus, and the global-search results
panel. Single value: `--shadow: 0 8px 24px rgba(0, 0, 0, 0.4)`. Everything else uses
borders and surface steps. Delete `--shadow-glow` and hover glows.

### 3.7 Control dimensions

| Control | Height | Notes |
|---|---|---|
| Buttons (default) | 28px | padding 0 10px |
| Buttons (primary page action) | 32px | rare; page header only |
| Inputs / selects | 28px | |
| Toolbar (filter bars) | 36px | controls vertically centered |
| Tabs / view switcher items | 32px | 2px bottom active indicator |
| Table rows (dense) | 28px | |
| Table rows (comfortable/analyst) | 40–44px | two-line |
| Table header row | 30px | |
| Nav rail items | 28px | |
| Top bar | 44px | replaces `--header-height: 56px` |
| Context bar (case) | 40px | |

### 3.8 Motion

Keep only: 100–120ms `ease-out` transitions on `background-color`, `border-color`,
`color`, `opacity`; the `.skeleton` shimmer; spinner rotation. Delete `fadeUp`,
`pulse-glow`, `.animate-in*` (remove the classes from JSX too — grep shows them in
App.tsx, CasesPage, CaseDetailPage, TimelineView, ControlPanelPage). Keep the
`prefers-reduced-motion` block.

---

## 4. Application Shell Specification

Two shell modes, both under one 44px top bar:

- **Global mode** (`/`, `/admin/*`, `/login`): no sidebar; centered content column,
  max-width 1200px for `/` and `/admin/users`, 1400px for control panel.
- **Case mode** (`/cases/:caseId`): navigation rail + context bar + content.

### Top bar (44px, full width, `--surface`, bottom border)

Left → right: brand mark + "CORVUS" (13px, 600, letter-spacing 0.08em, uppercase) ·
divider · case breadcrumb when in case mode (`Cases / <case name>`; case name is the
inline-renameable element — keep the existing click-to-rename behavior, `aria-label="Case
name"` input preserved) · spacer · global search trigger (renders `GlobalSearch` trigger;
in case mode only) · "Control Panel" link (admins only, unchanged condition
`user?.role === "administrator"`) · username (`.header-badge` restyled to a plain 12px
mono chip) · Logout (secondary button 28px). Delete the tagline.

### Case mode layout

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ ▲ CORVUS │ Cases / WKS-042 Investigation ✎        [⌕ Search  Ctrl+K] adm ▾  │ 44px
├──────────┬───────────────────────────────────────────────────────────────────┤
│          │ Source: [WKS-042 (Windows) ▾]  ● completed   1,204,331 events    │ 40px
│ CASE     ├───────────────────────────────────────────────────────────────────┤
│ Overview │  Timeline                                    [density ▾][Export]  │
│ Timeline │ ┌──────────────────────────────────────┬───────────────────────┐  │
│ Entities │ │ toolbar: [search][type][artifact]…   │  EVENT INSPECTOR      │  │
│ Disk     │ ├──────────────────────────────────────┤                       │  │
│ MFT      │ │ ▍2024-03-01T09:12:44Z  Logon  4624 … │  2024-03-01T09:12:44Z │  │
│ Browser  │ │ ▍2024-03-01T09:12:45Z  Proc … ▍SIGMA │  Process creation     │  │
│ Detect 12│ │  …virtualized rows 28px…             │  fields / pivots /    │  │
│          │ │                                      │  raw JSON             │  │
│ EVIDENCE │ │                                      │                       │  │
│ Sources 2│ └──────────────────────────────────────┴───────────────────────┘  │
│ Jobs   ● │  status: Loaded 10,000 of 1,204,331 · filtered                    │
└──────────┴───────────────────────────────────────────────────────────────────┘
```

- **Nav rail:** 200px wide, `--surface`, right border. Collapsible to 44px (icon-only,
  labels as `title` tooltips); collapsed state stored in `localStorage`
  (`corvus.navCollapsed`). Section labels "CASE", "EVIDENCE" in section-label style.
  Change `--sidebar-width` token from 320px to 200px.
- **Context bar:** 40px, `--surface-2`, bottom border. Contains the evidence-source
  `<select>` (moved from sidebar source cards; keep the same option data), platform label
  (`sourcePlatformLabel`), status dot + status word, compact ingest progress when a job is
  active (reuse `IngestStatusPanel` compact variant), and an "ⓘ" button opening the
  existing source-details dialog. When the case has no sources, the bar shows "No evidence
  — upload in Sources" with a link that activates the Sources view.
- **Content:** padding 16px; no max-width in case mode (views manage their own layout).
- **Page header per view:** 32px line containing the h2 view title (satisfies existing
  Playwright `getByRole('heading', …)` assertions — keep heading names "Timeline",
  "Entities", "Disk", "MFT Records", "Browser") plus right-aligned view actions.
- **Breadcrumbs:** only the top-bar `Cases / <name>` trail. The back-link
  (`.back-link` "← All cases") is replaced by the breadcrumb's "Cases" link.
- **System status:** not in the shell; remains in Control Panel.

Responsive: below 1100px the nav rail auto-collapses to 44px; below 900px the inspector
panes (§8/§9/§10) stack under the list instead of splitting.

---

## 5. Navigation Specification

Nav model: the rail replaces `.view-tabs`. Implementation keeps `CaseDetailPage`'s `tab`
state, extended: `type Tab = "overview" | "timeline" | "object" | "disk" | "mft" |
"browser" | "detections" | "sources"`. Default tab becomes `"overview"` when the case has
sources, `"sources"` when it has none (so a fresh case lands on upload).

| Item | Label | Icon (inline SVG, 14px, stroke 1.5) | Section | Destination | Badge | Visibility |
|---|---|---|---|---|---|---|
| Overview | `Overview` | grid/compass | CASE | `tab="overview"` | — | case mode |
| Timeline | `Timeline` | clock | CASE | `tab="timeline"` | — | case mode |
| Entities | `Entities` | hexagon/node | CASE | `tab="object"` | — | case mode |
| Disk | `Disk` | folder-tree | CASE | `tab="disk"` | — | case mode |
| MFT | `MFT` | table | CASE | `tab="mft"` | — | case mode; hide when `stats.mft_count === 0` (current UI already gates MFT/Browser tabs on counts — preserve that logic) |
| Browser | `Browser` | globe | CASE | `tab="browser"` | — | case mode; gate on `browser_count > 0` |
| Detections | `Detections` | shield | CASE | `tab="detections"` | count badge = `detections.length`, colored by top severity (12px mono, `*-dim` fill + severity text) | case mode |
| Sources | `Sources` | archive/box | EVIDENCE | `tab="sources"` | source count | case mode |
| Jobs | (row inside Sources view, not a nav item) | — | — | — | active-job dot on Sources item when `isActiveJob(job)` | — |
| Control Panel | `Control Panel` | sliders | top bar | `/admin/control-panel` | — | admin only, global |
| Users | `Users` | people | (link inside Control Panel page header) | `/admin/users` | — | admin only |

States: active item = `--primary-dim` fill + 2px left `--primary` border + `--text` label;
hover = `--surface-hover`; disabled (MFT/Browser gated) = hidden, not disabled — don't
show dead items; keyboard: rail is a `nav` landmark with plain buttons, focus ring per
§3.4. Every nav button keeps the exact accessible names above — e2e tests use
`getByRole('button', { name: 'Entities', exact: true })` etc.

Context comprehension: the analyst always sees `case name` (top bar) + `source`
(context bar) + `view` (rail active item). That triple is the full investigation address.

---

## 6. Page-by-Page Redesign Specifications

### 6.1 Cases (`/`, `CasesPage.tsx`)

- **Purpose:** Pick or create a case; triage which cases have activity.
- **Hierarchy:** Case name ≫ status/activity ≫ metadata.
- **Layout:** Page header row: h1 "Cases" left; right: search-filter input (client-side
  name filter, new but trivial) + primary button "New case" (opens a small dialog with
  name + description — reuse `useDialog`; replace the always-visible `.create-case-form`).
  Below: one full-width table.
- **Table columns:** Name (link, 600 weight) · Case ID (12px mono, `--muted`, truncated
  middle) · Sources (count) · Platforms (compact OS letters reusing `.os-badge` restyled)
  · Status (`.status-badge` restyled per §12 status treatment) · Created (mono date) ·
  Actions (rename ✎, delete — icon buttons appearing on row hover, keyboard reachable).
- **States:** loading = 8 skeleton rows (reshape `.case-card-skeleton` into row
  skeletons); empty = centered block "No cases yet" + New case button; error = inline
  alert row. Delete confirmation keeps `ConfirmDialog`.
- **Responsive:** below 800px drop Case ID and Created columns.
- **Accessibility:** table gets `aria-label="Cases"`; row action buttons get explicit
  aria-labels ("Rename <name>", "Delete <name>"). Keep `getByLabel('Case name')` rename
  input label.

```text
Cases                                    [filter…]        [ New case ]
┌────────────────────────────┬──────────┬────┬──────────┬───────────┬────────┐
│ NAME                       │ ID       │ SRC│ PLATFORMS│ STATUS    │ CREATED│
├────────────────────────────┼──────────┼────┼──────────┼───────────┼────────┤
│ WKS-042 Investigation      │ 2222…22  │  2 │ W L      │ ● ready   │ 03-01  │
│ Mail server triage         │ 91ab…f0  │  1 │ L        │ ◐ ingest  │ 03-04  │
└────────────────────────────┴──────────┴────┴──────────┴───────────┴────────┘
```

### 6.2 Case Overview (new `tab="overview"` inside CaseDetailPage)

- **Purpose:** 30-second orientation: what evidence, what's hot, where to start.
- **Content** (all data already fetched by CaseDetailPage — `stats`, `detections`,
  `sources`, summary derivations like `summaryCategories`, top hosts, `topSeverity`):
  1. **Counts strip** — the existing stat pivots (`Events`, `Entities`, `Paths`,
    `Detections`, `MFT`, `Browser`) as one horizontal strip of compact stat items:
    label 11px uppercase, value 16px mono, 28px tall, separated by borders — not cards.
    Clicking pivots to the view (preserve `.stat-card--action` behavior and keep that
    class name on the buttons — e2e locates `button.stat-card--action`).
  2. **Detections summary** — severity distribution as a single horizontal segmented bar
    (one 8px bar segmented by severity color with counts beside) + top 5 detections table
    (severity badge · title · count · "open" pivot). No giant severity cards. Keep the
    existing `.summary-kpis` container class.
  3. **Evidence sources table** — hostname, platform, collector (`sourceCollectorLabel`),
    status, event count, ingested date; row click selects that source and opens Timeline.
  4. **Top categories / top hosts** — two compact two-column label/count lists.
- **States:** while `stats` null → skeleton strip; ingest running → counts strip shows
  live `IngestStatusPanel` compact row.
- **Wireframe:**

```text
Overview
EVENTS 1,204,331 │ ENTITIES 8,412 │ PATHS 402,118 │ DETECTIONS 37 │ MFT 96,004 │ BROWSER 3,551
┌ Detections ────────────────────────────────┐ ┌ Evidence sources ───────────────┐
│ ▉▉▉▉▉▉▉▉▉▉░░  2 crit · 9 high · 26 other  │ │ WKS-042  Windows  ● completed   │
│ ▍CRIT  Mimikatz creds access      4  open │ │ SRV-DB1  Linux    ◐ running 61% │
│ ▍HIGH  Susp. PowerShell encoded  11  open │ └─────────────────────────────────┘
└────────────────────────────────────────────┘ ┌ Top categories ─┐┌ Top hosts ──┐
```

### 6.3 Timeline — see §8 (full spec).

### 6.4 Object / Entities — see §9.

### 6.5 Disk — see §10.

### 6.6 Browser — see §11. MFT: keep current behavior, restyle per §13; heading stays
"MFT Records"; keep `.mft-count`, `.mft-page-info`, `.mft-scope-note`, `.mft-table`,
`.mft-detail-path` class names (e2e selectors).

### 6.7 Detections (promoted view, `tab="detections"`, refactored `SigmaFindingsPanel`)

- **Purpose:** Triage rule hits; pivot into events.
- **Layout:** Toolbar (search input — keep existing search state —, severity filter
  select, engine filter select [Sigma/Chainsaw], existing pagination relocated right).
  Main: table grouped by rule: group header row = severity badge + rule title + hit
  count + engine tag + tags; expanded rows = individual hits (timestamp mono ·
  event summary · "View event" pivot preserving current `onViewEvent` → Timeline focus
  behavior). Right inspector (360px) shows selected rule: description, level, tags,
  rule id, hit list.
- **Critical-findings banner:** demote `.sigma-alert-banner` to a single 28px line under
  the toolbar (`▍ 2 critical findings` in `--critical-dim` fill), not a boxed banner.
- **States:** empty = "No detections for this source" + note about rule sync (link to
  Control Panel for admins); loading = skeleton rows; keep pagination behavior.

### 6.8 Evidence Sources (promoted view, `tab="sources"`)

Consolidates what the old sidebar did:

- **Sources table:** hostname · platform · collector · status (+progress if running) ·
  counts · ingested at · row actions: Info (existing source-details dialog), Ingest
  history (existing history data, now a right drawer with a per-source job table),
  Re-ingest, Hash files, YARA scan, Cancel (existing confirm flows via `ConfirmDialog` —
  keep dialog titles like "Hash all evidence files"; e2e asserts
  `getByRole('alertdialog', { name: 'Hash all evidence files' })`).
- **Upload panel:** right column (320px) or top strip: the existing drop zone
  (`.upload-drop-hint` behavior: click/keyboard/drag — keep the `role="button"` and
  `aria-label="Drop evidence files or click to select"`), hostname override input,
  platform select, progress. Visually: dashed 1px border, flat, no glow on dragover —
  dragover = `--primary-border` border + `--primary-dim` fill.
- **Active job status:** full `IngestStatusPanel` (non-compact) with diagnostics
  (`.ingest-diagnostics*` restyled as a plain list with coverage table).
- **Hashes:** the evidence-hash panel (`.evidence-hash-*`) becomes part of the source
  Info drawer; keep export link (`evidenceHashExportUrl`).

### 6.9 Ingest Jobs

Not a separate route. Jobs appear: (a) context-bar compact progress; (b) Sources view —
per-source "Ingest history" drawer listing jobs as a table (status badge · started ·
duration `formatDuration` · message · cancel action for active); (c) Control Panel's
admin jobs queue (global, unchanged scope, restyled table with the existing
status/error-code/error-stage filters — keep `getByLabel('Job error code filter')`).

### 6.10 Administration (`/admin/control-panel` + `/admin/users`)

- **Control Panel layout:** page header (h1 "Control Panel", link to Users) + a left
  in-page section nav (sticky, 160px: System · Detection rules · Jobs · Containers ·
  Maintenance) + content sections. Each section is a flat panel:
  - **System:** label/value grid (host, CPU, memory, disk with a thin 4px usage bar —
    keep `totalDisk/usedDisk/diskPct` rendering), queued/running jobs counts.
  - **Detection rules:** one table: engine (Sigma/Chainsaw/YARA) · state · ref ·
    last sync · message · sync button (reuse `SigmaRulesSync` logic; unify the three
    rule-status blocks into rows).
  - **Jobs:** table with existing filters.
  - **Containers:** table (name · service · image · state · health · start action ·
    logs action → logs open in a bottom drawer with mono 12px, `--bg-elevated`).
  - **Maintenance:** bulk case delete (existing multi-select + confirm) and search
    reindex — each one row: description left, action button right. Danger actions use
    `button.danger`.
- **Admin Users:** table (username · role select · active toggle · reset password) +
  "Create user" dialog. Keep all handlers.
- **States:** each section independently loads/errors (already the case — keep).

### 6.11 (reserved — Settings does not exist; see §21 P3.)

### 6.12 Login (`/login`)

Keep structure and all labels (`label[for="username"]`, `label[for="password"]`, password
toggle button inside label — e2e uses `locator('label button')`). Restyle: centered 360px
flat panel (`--surface`, 1px border, radius 4px), brand mark + "CORVUS" 14px above,
"Sign in" h1 18px, fields per §3.7, primary button full-width 32px, error as a
`--danger-dim`-filled bordered line. Background: plain `--bg`, no decoration.

### 6.13 Not found

Keep `NotFoundPage`; restyle to plain centered text block, mono "404" label, link back.

---

## 7. Investigation UX (pivot model)

The core loop: **Detection → Event → Entity/Object → Timeline context → Disk/Browser →
back**. Concrete rules:

1. **Pivot affordance:** every pivotable value (hostname, user, path, hash, IP, domain,
   URL, rule name, event id) renders in mono 12.5px, `--primary-bright`, no underline at
   rest, underline on hover, `cursor: pointer`. Non-pivotable values are plain `--text`.
   One visual language everywhere — the existing `.event-pivot-btn` chips become this.
2. **What opens where:**
   - **Inline expansion:** raw JSON / attribute dumps (`.raw-json-details`,
     `.code-block`) — collapsed by default behind "Raw data" disclosure.
   - **Inspector pane (right split):** the selected row's detail in Timeline, Entities,
     Disk, MFT, Browser, Detections. Never a modal for row detail.
   - **Drawer (overlay from right, 420px, shadow allowed):** source info, ingest
     history, container logs — secondary context that overlays without losing place.
   - **View switch (same page, tab change):** cross-view pivots (existing
     `setFocusTimeline` / `setFocusEntity` / `setFocusPath` + `setTab` mechanics —
     preserve exactly; they already scroll-to and select the target).
   - **New page:** only Cases ↔ case workspace ↔ admin.
3. **Context persistence:** selected source, active view, and each view's selection/filter
   state persist while inside a case (state already lives in CaseDetailPage/children —
   don't unmount views more aggressively than today; current conditional render per tab
   is acceptable, but keep filter state in the parent where it already is).
4. **Return path:** after a cross-view pivot, the target view shows a dismissible 28px
   "pivot chip" under its toolbar: `◄ from Detections: "Mimikatz…"` — clicking returns
   to the originating view (implement as a small `{fromTab, label}` state in
   CaseDetailPage; clearing on manual nav).
5. **Selected-object continuity:** when pivoting from an entity to Timeline, the entity's
   related event is selected in the inspector (already implemented via
   `focusEvent`/`getTimelineEvent`) — keep.
6. **Browser back:** unchanged (tabs are component state today; see §20 URL-state risk).

---

## 8. Timeline Specification

Refactor presentation of `TimelineView.tsx`; keep all data logic: server paging
(PAGE_SIZE 10000), `useVirtualizer`, placeholder rows, `useRowNavigation`, filter opts,
histogram, export URL, sigma-only toggle, focusEvent scroll-to.

### Toolbar (36px, one row, wraps to two below 1200px)

`[search input 240px] [Event type ▾] [Artifact ▾] [start dt] [end dt] [☐ Detections only]
[spacer] [density ▾] [Export CSV]`. All controls 28px. Keep every existing aria-label
(`"Search timeline"`, `"Event type filter"`, `"Artifact type filter"`, `"Start time"`,
`"End time"` if present, `"Timeline row density"`). The sigma-only toggle becomes a
checkbox labeled "Detections only" (keep `onSigmaOnlyChange` wiring).

### Status line (24px, under the list, part of the panel)

Left: `Loaded 10,000 of 1,204,331 events` (mono 12px, `--muted`) — relocate the current
centered prose; paging errors render here in `--danger`. Right: active-filter summary
with a "Clear filters" text button when any filter is set (new, trivial — reset existing
state setters).

### Histogram (`TimelineChart`)

Collapsed by default to a 48px strip above the list; expandable to 120px via a chevron.
Recolor: bars `--border-strong`, detection overlay bars in severity colors, selection
brush `--primary-dim`. Keep zoom controls (`.timeline-zoom-*`) as 24px icon buttons on
the strip's right. Keep hover label; kill legend dots if redundant with overlay.

### Row structure

Single-line grid at 28px ("compact", default) — change `estimateSize` to 28/44:

```text
| 2px sev edge | timestamp 176px mono | type 140px | summary flex | artifact 64px |
▍ 2024-03-01T09:12:44Z  Process create   powershell.exe -enc JAB…      evtx
▍ 2024-03-01T09:12:45Z  4688 Security    cmd.exe /c whoami             evtx   ← high sev edge
```

- Severity edge: 2px left border = highest `sigma_hits` level color; transparent when
  no hits. Additionally a small `▍SIGMA`-style badge is **removed from the timestamp
  cell** — instead a 12px shield glyph in severity color sits after the summary (title
  attribute lists rule names). Keep the `.sigma-hit-row` class on the row (e2e/CSS hook)
  but its background becomes the severity `*-dim` at low emphasis.
- "Analyst" density = 44px, second line: subtitle + up to 4 pivot values (mono,
  pivot-styled per §7.1) — this replaces `.item-list-subtitle`/`.item-list-pivots`
  presentation but keeps `rowPreview()` logic.
- Placeholder (unloaded page) rows: skeleton bars in the timestamp+summary cells, keep
  `timeline-placeholder-row` class.
- Selected: `--primary-dim` fill + 2px left `--primary-border` (severity edge overrides
  color if present, selection shown by fill). Hover: `--surface-hover`. Focus: outline
  per §3.4. Keep `role="option"` / `aria-selected` / listbox semantics from
  `useRowNavigation` (arrow keys, Home/End, Enter to select — verify existing hook
  behavior unchanged).

### Event inspector (right pane, keep resizable splitter)

Keep `.timeline-resizable-grid` + `.timeline-splitter` (role="separator", keyboard
arrows, 35–75% bounds). Inspector content order:
1. Header: severity edge + `timestamp_utc` (mono 13px) + event type + artifact tag.
2. Detections block (if hits): one row per rule — severity badge + rule title (pivot to
   Detections view; new but trivial: `setTab("detections")` + select rule).
3. Summary paragraph.
4. **Fields:** curated key fields as a label/value grid (reuse existing
   `.event-pivot-field/-value` extraction logic; values pivot-styled per §7.1 with the
   existing pivot buttons' behavior: entity pivots, path pivots).
5. Raw data: `<details>` "Raw JSON" with `.code-block` mono 12px (collapsed).
- Empty inspector: keep `.detail-empty-guided` copy.

### States

Loading: 12 skeleton rows. Error: inline alert with retry button (keep existing error
message wiring). Empty: "No events match the current filters" + Clear filters button.
Keep `onLoadStateChange` callback contract with CaseDetailPage.

### Virtualization expectations

Do not change: virtualizer with `measureElement`, overscan 12, absolute-positioned rows,
`.virtual-list-container` (e2e hook), scroll-to-index on focusEvent. After changing row
heights, verify smooth scroll with 100k+ rows and that placeholder→loaded swap doesn't
jump (measureElement handles it).

---

## 9. Object Investigation Specification

Refactor `ObjectView.tsx` presentation; keep data flow (listEntities, type filter,
search, `listEntityTimeline` related events, ResizableSplit, row navigation).

- **Mental model:** left = entity index (a dense directory), right = dossier on one
  entity.
- **Left pane:** toolbar (search + type filter select — keep `"All types"` option), then
  a 28px-row table: type icon+abbrev (US/PR/FI/HO/IP/DO — 11px mono badge with
  `--surface-2` fill) · display name (mono for paths/IPs/hashes; sans for users/hosts) ·
  related-event count if cheap (only if already available; do not add API calls).
- **Inspector (right):**
  1. Header: entity type label (section-label style) + display name (16px, mono when
     value-like) + copy button.
  2. **Attributes:** curated label/value grid from `attributes` (known keys first,
     pivot-style values); full JSON behind "Raw attributes" disclosure (replaces the
     always-open `<pre>` dump).
  3. **Related timeline events:** table rows (timestamp mono · summary · type), click =
     existing `onTimelineClick` pivot to Timeline. Remove the 200px inline max-height;
     let the pane scroll as a whole; cap list at what the API returns.
  4. **Related detections** (new, cheap): filter the already-loaded `detections` prop
     if the parent passes it — only if CaseDetailPage already holds detections for the
     source (it does: `detections` state). One row per matching rule, pivot to
     Detections view. If matching logic (entity value appears in hit event ids) proves
     non-trivial, ship without it (P2) — do not add API endpoints.
- **Empty/loading:** keep existing empty messaging ("No entities match your filters" /
  "No linked timeline events…"), restyled.

---

## 10. Disk Investigation Specification

Refactor `DiskView.tsx` presentation; keep `listFilesystem` lazy directory listing,
preview, hashes, focusPath handling.

```text
Disk                                              [filter in this directory…]
/ C: / Users / admin / AppData / Roaming          ← clickable breadcrumb segments
┌ listing ───────────────────────────────┬ inspector ───────────────────────┐
│ NAME ▲            SIZE      MODIFIED   │ svchost.exe                      │
│ ▸ Microsoft        —        03-01 09:12│ /C:/Users/…/svchost.exe [copy]   │
│ ▸ Mozilla          —        02-28 11:02│ Size 44.5 KB · deleted: no       │
│   svchost.exe     44.5 KB   03-01 09:14│ MACB timestamps (mono grid)      │
│   run.dat          1.2 KB   03-01 09:14│ MD5  9e10…  SHA1 66cb…  [hash]   │
│                                        │ [Preview hex/ascii] [Timeline ↗] │
└────────────────────────────────────────┴──────────────────────────────────┘
```

- **Breadcrumb path bar:** current path as segment buttons (each pivots to that
  directory); root "/" first. Mono 12.5px. Long paths: middle segments collapse to "…"
  menu. This replaces list-only navigation; keep ".." row removal if breadcrumbs exist.
- **Listing:** §13 table, 28px rows; columns Name (icon + name; directories first,
  chevron glyph) · Size (right-aligned mono, `fmtSize`) · Modified (mono). Sort by
  clicking headers (client-side over loaded nodes — keep whatever current sort exists;
  add name/size/mtime sort client-side only). Deleted files keep `.disk-deleted`
  treatment: `--muted` text + strikethrough name + "deleted" tag.
- **Filter:** existing `search` state filters the current listing.
- **Inspector:** fixed 360px right pane (always present; empty state "Select a file").
  Name, full path (wrapping mono, copy button), size, flags, timestamps grid, hashes
  (existing `FileHashes` fetch + compute action), preview action loading the hex/ascii
  grid (`.disk-preview-grid` — restyle: mono 12px, offset gutter `--muted`, hex middle,
  ascii right, `--bg-elevated` background), prev/next page buttons for preview offsets
  (keep `.disk-preview-nav`). "Show in Timeline" pivot if an event references the path
  (only if currently implemented — do not fabricate).
- **Long filenames:** truncate middle with full value in `title` and inspector.
- **States:** loading listing = skeleton rows; empty dir = "Empty directory"; preview
  unavailable/truncated notes preserved from API (`truncated` flag).

---

## 11. Browser Investigation Specification

Refactor `BrowserView.tsx` presentation; keep category tabs, sorting, data extraction
(`eventUrl`, `eventTitle`), raw JSON details.

- **Toolbar:** category tabs (History · Downloads · Cookies · …— keep existing
  `.browser-category-tabs` set driven by data) as §3.7 tabs; search input; profile/
  browser filter if present in data.
- **Table:** Time (mono 176px) · Title (flex; sans) · URL (flex 1.5; mono 12px,
  `--primary-bright`? No — URLs are data, not links: plain `--text-soft` mono, truncate
  middle, full URL in `title` tooltip and inspector) · Browser/profile (96px). Remove
  `.browser-type-pill` from rows (redundant with active tab).
- **Inspector:** right pane consistent with Timeline's: timestamp, title, full URL
  (wrapping, copy), source/profile, all parsed fields as label/value grid, Raw JSON
  disclosure. "View in Timeline" pivot using the row's underlying `TimelineEvent`
  (these are timeline events — pivot via existing focus mechanics).
- **Connection to investigation:** domains in URLs render as pivot values (§7.1) linking
  to the matching Domain entity when one exists in already-loaded entity data; skip if
  not cheaply available (P2).
- **States:** per-category empty ("No downloads parsed for this source"), loading
  skeleton, error inline.

---

## 12. Detection UX / Severity System

One systematic `SeverityBadge` treatment used in: Detections view, Timeline rows +
inspector, Overview, Entities related-detections, admin jobs where applicable.

| Level | Color token | Badge | Icon | Row treatment |
|---|---|---|---|---|
| critical | `--critical` | `CRIT` | filled shield | 2px left edge + `--critical-dim` row fill |
| high | `--high` | `HIGH` | shield | 2px left edge |
| medium | `--medium` | `MED` | shield outline | 2px left edge |
| low | `--low` | `LOW` | shield outline | 2px left edge |
| informational | `--info` | `INFO` | circle-i | 2px left edge, no fill |

Badge spec: 11px 600 uppercase mono, 2px radius, 1px border in severity color, text in
severity color, background `*-dim`. Never a solid saturated fill; never a large card.
Accessibility: badge text carries the level (color is never the only signal); row edges
are supplemented by the badge; icons `aria-hidden` with text alternatives. Map existing
`.sigma-level-*` classes onto this spec (keep class names; e2e may rely on them —
`.summary-severity-*` classes likewise keep names, change values).

Pivot chain: Detection row → expand hits → "View event" (existing) → Timeline selected
event → inspector Detections block → rule (back to Detections view) → entity pivots →
Entities. Every hop is §7 mechanics; no new APIs.

---

## 13. Tables and Data Grids

One spec, applied to: Cases table, Overview tables, Timeline rows (virtualized list
styled as a table), Entities list, Disk listing, MFT table, Browser table, Detections
table, admin jobs/containers/users tables.

- **Implementation approach (deliberate):** shared **CSS classes**, not a shared React
  `<DataTable>` component. The MFT/Timeline views have bespoke behavior (virtualization,
  column resize, server paging) that a generic component would obstruct. Standardize on
  the existing `.data-table` class family in App.css, extended as below; each view keeps
  its own markup. (`ponytail:` a React DataTable abstraction is explicitly rejected —
  revisit only if a future view count makes divergence painful.)
- **Dimensions:** header 30px (`--surface-2`, 11px uppercase 600 `--muted`,
  letter-spacing 0.05em, sticky via `position: sticky; top: 0`); rows 28px dense /
  40px comfortable; cell padding 0 10px; `tabular-nums`.
- **Borders:** row separator `1px solid var(--border)`; no vertical cell borders except
  MFT (keeps its column-resize handles); container 1px border, 2px radius.
- **Hover:** `--surface-hover`. **Selected:** `--primary-dim` + 2px left
  `--primary-border`. **Focus:** outline ring on the row.
- **Sorting:** clickable header with ▲▾ glyph in `--primary-bright` on the active column
  only; unify `.sort-header` (MFT/Browser) styling.
- **Alignment:** text left; numbers/sizes right; timestamps left (mono).
- **Truncation:** single-line `text-overflow: ellipsis`; paths/URLs truncate middle via
  the existing JS helpers where present; every truncated cell sets `title`.
- **Pagination:** one shared visual: `‹ Prev  Page 3 of 41  Next ›` mono 12px right-
  aligned in a 32px footer (restyle `.mft-pagination` and `.sigma-pagination` to match).
- **Empty/loading:** empty = single full-width row, centered `--muted` message + optional
  action; loading = skeleton rows matching column layout (never spinners inside tables).
- **Virtualization:** required only where it exists today (Timeline). MFT stays
  server-paged `<table>`; do not add virtualization elsewhere.

---

## 14. Reusable Component Architecture

New components (keep this list minimal — everything else is CSS):

| Component | File | Purpose | Props | Notes |
|---|---|---|---|---|
| `CaseNav` | `src/components/CaseNav.tsx` (new) | Nav rail in case mode | `active: Tab`, `onSelect(tab)`, `detectionCount`, `topSeverity`, `sourceCount`, `hasActiveJob`, `mftCount`, `browserCount`, `collapsed`, `onToggleCollapsed` | Renders sections/badges per §5; pure presentational |
| `SeverityBadge` | `src/components/SeverityBadge.tsx` (new) | §12 badge | `level: string`, `title?` | Replaces ad-hoc severity markup in SigmaFindingsPanel, TimelineView (`SigmaEventBadges` internals), Overview |
| `StatusBadge` | reuse `.status-badge` CSS only | job/source status | — | No new component; keep class + `partial` modifier (e2e: `.status-badge.partial`) |
| `Drawer` | `src/components/Drawer.tsx` (new) | Right overlay drawer (§7.2) | `open`, `onClose`, `title`, `children`, `width?` | Reuse `useDialog` hook for focus/esc handling; used by source info, ingest history, container logs |
| `PageHeader` | CSS only (`.panel-header` extended) | view title + actions row | — | No component needed |

Existing components that remain the architectural backbone (reuse, restyle):
`ResizableSplit`, `ConfirmDialog`, `GlobalSearch`, `IngestStatusPanel`, `TimelineChart`,
`SigmaRulesSync`, `useDialog`, `useRowNavigation`.

Structure after refactor (indicative):

```text
CaseDetailPage
├── (top bar stays in App.tsx)
├── CaseNav
├── ContextBar        (inline in CaseDetailPage — source select, status, ⓘ)
├── OverviewView      (extracted from CaseDetailPage summary/stats JSX → new file
│                      src/components/OverviewView.tsx to keep page size sane)
├── TimelineView (± TimelineChart, ResizableSplit)
├── ObjectView (ResizableSplit)
├── DiskView / MftView / BrowserView
├── SigmaFindingsPanel (now full-width Detections view)
├── SourcesView       (extracted upload + source table + IngestStatusPanel →
│                      src/components/SourcesView.tsx)
└── Drawer / ConfirmDialog / GlobalSearch portals
```

---

## 15. Existing Component Mapping

| Existing | Action | Reason |
|---|---|---|
| `App.tsx` header | Refactor | Becomes 44px top bar with breadcrumb; drop tagline |
| `CasesPage.tsx` | Refactor | Card grid → table; hero removed; create → dialog |
| `CaseDetailPage.tsx` | Refactor (largest) | Sidebar dissolved into CaseNav + ContextBar + SourcesView + OverviewView; tab union extended |
| `TimelineView.tsx` | Refactor | Keep all data/virtualization logic; new row/toolbar/inspector presentation |
| `TimelineChart.tsx` | Refactor | Collapsible strip, recolor; keep zoom/hover logic |
| `ObjectView.tsx` | Refactor | Table rows + dossier inspector; remove inline max-height |
| `DiskView.tsx` | Refactor | Breadcrumb bar + table + persistent inspector |
| `MftView.tsx` | Restyle only | Behavior is already right; align to §13 |
| `BrowserView.tsx` | Refactor | §13 table + inspector; drop row type pills |
| `SigmaFindingsPanel.tsx` | Refactor | Sidebar panel → full Detections view, grouped table |
| `IngestStatusPanel.tsx` | Restyle | Same logic; §6.8/§6.9 presentation |
| `GlobalSearch.tsx` | Restyle | Flat popover; trigger moves to top bar |
| `ConfirmDialog.tsx` | Keep (retoken) | Works; inherits new tokens automatically |
| `ResizableSplit.tsx` | Keep | Accessible splitter, reused as-is |
| `SigmaRulesSync.tsx` | Refactor | Becomes row(s) in the unified rules table |
| `LoginPage.tsx` | Restyle | Structure/labels unchanged |
| `AdminUsersPage.tsx` | Restyle | List → table |
| `ControlPanelPage.tsx` | Refactor | Section nav + tables |
| `useDialog.ts`, `useRowNavigation.ts` | Keep | Behavior-only hooks |
| `utils/eventCodes.ts`, `utils/generated/*` | Keep | Data, untouched |
| `api/client.ts` | Keep | **Do not modify** |
| `.case-card` / `.cases-grid` / `.cases-hero` CSS | Replace | Card pattern removed |
| `.stat-card` CSS | Refactor | Card → compact stat strip; keep `.stat-card--action` class name |
| `.item-list*` CSS | Replace | Feed rows → table-grid rows |
| `.animate-in*`, `pulse-glow`, `fadeUp` | Delete | Motion policy §3.8 |

---

## 16. File-by-File Implementation Plan

Order within this section = suggested commit order inside each phase (§17).

#### `apps/web/src/index.css` — modify — **Risk: High** (every page inherits)
Replace token values per §3 (same names; add `--space-*`; retarget `--font-display`,
`--cyan`; radius/shadow/sizes; root font-size 14px). Rewrite base `button`, `input`,
`select` rules to §3.7 (28px, flat, outline focus — remove glow shadows and
`translateY` press). Delete `fadeUp`/`pulse-glow`/`.animate-in*` keyframes+classes;
keep `.skeleton`, reduced-motion, `.skip-link`, `.mono`.
**Verify:** app builds; visually sweep every page; `grep -rn "animate-in\|pulse-glow"
src/` returns only files pending cleanup.

#### `apps/web/src/main.tsx` — modify — Risk: Low
Remove the three Syne imports. **Verify:** build passes; no Syne in network/bundle.

#### `apps/web/package.json` — modify — Risk: Low
Remove `@fontsource/syne`. Run `npm install` to update lockfile. **Verify:** Docker web
build succeeds.

#### `apps/web/src/App.css` — modify (large, incremental) — Risk: High
Rewrite section-by-section per specs above, keeping the existing section-comment
organization. Mandatory class-name preservation (e2e/tests): `.view-tab` (if tabs remain
as fallback), `.stat-card--action`, `.status-badge` (+`.partial`), `.summary-kpis`,
`.virtual-list-container`, `.timeline-distribution`, `.ingest-status-panel`,
`.ingest-status-detail`, `.detail-summary`, `.mft-table`, `.mft-count`,
`.mft-page-info`, `.mft-scope-note`, `.mft-detail-path`, `.sigma-level-*`,
`.summary-severity-*`. Add new sections: nav rail, context bar, drawer, table spec,
severity badges, pivot values, stat strip, cases table. Delete dead sections only after
their JSX consumers are gone (grep before deleting).
**Verify:** after each section rewrite, run the mocked e2e suite.

#### `apps/web/src/App.tsx` — modify — Risk: Medium
Top bar per §4: breadcrumb (needs case name — lift via route match + a tiny
context/callback from CaseDetailPage, or render breadcrumb case-name slot via a portal
target in the header; choose the **portal target** approach: header renders
`<span id="header-case-slot"/>`, CaseDetailPage portals its editable case-name element
into it — no data-flow rewiring). Move GlobalSearch trigger here only if simple;
otherwise leave GlobalSearch where it is and skip (P2). Keep auth/logout/Control Panel
logic. Restyle NotFoundPage. **Verify:** login → cases → case → rename via header works;
smoke spec passes.

#### `apps/web/src/pages/CasesPage.tsx` — refactor — Risk: Medium
Table per §6.1; create-case dialog via `useDialog`; keep `api.listCases/createCase/
renameCase/deleteCase` calls and ConfirmDialog. Keep `getByLabel('Case name')` and
button name "Create case". **Verify:** e2e `smoke.spec.ts` + `analyst-flows.spec.ts`
case CRUD paths pass.

#### `apps/web/src/components/CaseNav.tsx` — create — Risk: Low
Per §5/§14. **Verify:** keyboard focus order; names match e2e (`'Entities'`, `'Disk'`,
`'MFT'`, `'Browser'` exact).

#### `apps/web/src/components/SourcesView.tsx` — create (extraction) — Risk: Medium
Move from CaseDetailPage: upload zone JSX + handlers (`handleUploadFile`, drag state),
source list (as table), source actions (hash/yara/reingest/cancel + `ConfirmDialog`
wiring), `IngestStatusPanel` full view, ingest-history (as `Drawer`), source-info (as
`Drawer`). Props: everything it needs passed down from CaseDetailPage (sources, job,
handlers). Pure extraction + restyle — no logic changes. **Verify:** upload a file in
mocked e2e; hash/yara confirm dialogs still found by role/name.

#### `apps/web/src/components/OverviewView.tsx` — create (extraction) — Risk: Medium
Move stats strip + case summary + top-5 detections from CaseDetailPage per §6.2. Keep
`.stat-card--action` buttons and pivot handlers (`pivotToStat`). **Verify:** stat pivot
e2e interactions pass.

#### `apps/web/src/components/Drawer.tsx` — create — Risk: Low
Overlay drawer using `useDialog` focus management + `createPortal` (pattern already in
CaseDetailPage modals). **Verify:** esc closes, focus returns, `role="dialog"` +
labelled title.

#### `apps/web/src/components/SeverityBadge.tsx` — create — Risk: Low
§12. **Verify:** renders all five levels; used by SigmaFindingsPanel/TimelineView.

#### `apps/web/src/pages/CaseDetailPage.tsx` — refactor (largest single task) — Risk: High
Extend `Tab` union (`"overview"`, `"detections"`, `"sources"`); default-tab logic per §5;
render CaseNav + context bar + active view; delete sidebar JSX (moved to
SourcesView/OverviewView); pivot chip state (§7.4); portal case-name into header slot.
Keep every handler, effect, and state hook — this is a re-composition, not a rewrite.
Preserve heading "…Investigation" (e2e: `getByRole('heading', { name: 'WKS-042
Investigation' })` — case name must remain an h1-level heading in the workspace or the
header slot must carry the heading role; simplest: keep an h1 with the case name at the
top of the content area in Overview and a plain breadcrumb in the top bar — decide: **keep
the h1 in the workspace**, breadcrumb shows plain text).
**Verify:** full mocked e2e suite; manual pass through all 8 views with sample case.

#### `apps/web/src/components/TimelineView.tsx` — refactor — Risk: High
Per §8. Presentation only: row markup/classes, toolbar consolidation, status line,
inspector ordering, estimateSize 28/44. Do not touch: fetch/paging logic, virtualizer
config besides sizes, filter state, export, focusEvent effect, `onLoadStateChange`.
**Verify:** `analyst-flows.spec.ts` timeline paths; manual scroll of large source
(`MIN_FILESYSTEM_NODES=1 ./scripts/validate-ingest.sh --sample c` stack) for jank;
selection/keyboard nav; density toggle.

#### `apps/web/src/components/TimelineChart.tsx` — modify — Risk: Low
Collapsible strip + recolor per §8. Keep zoom/hover logic and
`.timeline-distribution` wrapper class. **Verify:** brush/zoom still filter (locator
`.timeline-distribution` test passes).

#### `apps/web/src/components/SigmaFindingsPanel.tsx` — refactor — Risk: Medium
Full-width Detections view per §6.7/§12 (grouped table + inspector + demoted banner).
Keep: data calls, pagination state, search, `onViewEvent` pivot, engine tags. **Verify:**
detections e2e steps; pivot to timeline selects the event.

#### `apps/web/src/components/ObjectView.tsx` / `DiskView.tsx` / `BrowserView.tsx` — refactor — Risk: Medium each
Per §9/§10/§11. Keep all API calls and pivot props (`onTimelineClick`, `focusPath`,
`focusEntity` handling). **Verify:** per-view e2e steps; cross-pivots
(entity→timeline, event→disk path) still land and select.

#### `apps/web/src/components/MftView.tsx` — restyle — Risk: Low
§13 alignment only; keep sorting/resize/pagination logic and all `.mft-*` class names.
**Verify:** MFT e2e assertions (`.mft-table tbody tr`, `.mft-page-info`,
`.mft-scope-note`, heading "MFT Records").

#### `apps/web/src/components/IngestStatusPanel.tsx`, `GlobalSearch.tsx`, `SigmaRulesSync.tsx`, `ConfirmDialog.tsx`, `LoginPage.tsx`, `AdminUsersPage.tsx` — restyle — Risk: Low
Class/markup tweaks to new tokens/specs; zero logic changes. **Verify:** login e2e,
control-panel e2e, dialogs by role/name.

#### `apps/web/src/pages/ControlPanelPage.tsx` — refactor — Risk: Medium
§6.10 layout: section nav + tables. Keep every handler and filter
(`getByLabel('Job error code filter')` preserved). **Verify:** `control-panel.spec.ts`.

#### `apps/web/src/components/ResizableSplit.tsx`, hooks, `api/client.ts`, `utils/*` — no change.

#### `apps/web/e2e/*.spec.ts`, `e2e/helpers.ts` — modify as needed — Risk: Medium
Rule: change a selector **only** when the plan explicitly changed the underlying element
(e.g., `.view-tab.active` → nav rail active class; `.case-card` assertions → table
rows). Prefer role/name selectors that this plan preserves. Update
`screenshots.spec.ts` to also capture: Overview, Detections, Sources, Control Panel,
Login (see §19). **Verify:** full `npm run test:e2e:mocked` green.

#### `apps/web/index.html` — modify — Risk: Low
Ensure title/meta theme-color match new `--bg`.

---

## 17. Implementation Order

Keep the app buildable and the mocked e2e suite green at the end of every phase.

```text
Phase 1 — Foundation (no layout changes yet)
  1. index.css token + base-control rewrite (§3)          → verify: build + visual sweep
  2. main.tsx / package.json Syne removal                 → verify: build
  3. App.css: motion classes deleted; JSX animate-in
     class removal across files                           → verify: e2e mocked
  4. App.css: table spec + severity badge + pivot-value
     sections added (new classes, nothing consumes yet)   → verify: build

Phase 2 — Shell
  5. App.tsx top bar + NotFound restyle                   → verify: smoke.spec
  6. CaseNav + Drawer + SeverityBadge components          → verify: unit-less render via e2e
  7. CaseDetailPage re-composition (tab union, nav rail,
     context bar) with views still in old skins           → verify: full mocked e2e (expect
     view-tab selector updates here)

Phase 3 — Extraction views
  8. SourcesView extraction + restyle                     → verify: upload/hash/yara e2e
  9. OverviewView extraction + restyle                    → verify: stat-pivot e2e
 10. SigmaFindingsPanel → Detections view                 → verify: detections e2e

Phase 4 — Investigation views
 11. TimelineView + TimelineChart (§8)                    → verify: timeline e2e + manual
     large-source scroll
 12. ObjectView (§9)                                      → verify: entity pivot e2e
 13. DiskView (§10), MftView restyle, BrowserView (§11)   → verify: per-view e2e

Phase 5 — Peripheral pages
 14. CasesPage table                                      → verify: case CRUD e2e
 15. ControlPanelPage + AdminUsersPage + SigmaRulesSync   → verify: control-panel.spec
 16. LoginPage + GlobalSearch + IngestStatusPanel restyle → verify: login e2e

Phase 6 — QA hardening
 17. Dead CSS purge (grep every deleted class)            → verify: build + e2e
 18. States pass: every view's loading/empty/error per specs
 19. Accessibility pass (§18 checklist)
 20. screenshots.spec.ts update + capture; visual review  → verify: §19 checklist
 21. Backend smoke: ./scripts/rebuild-stack.sh + validate-ingest sample
```

Dependencies: 7 requires 5–6; 8–10 require 7; 11–13 require 1+4; 17 requires all.

---

## 18. Acceptance Criteria

Functional (all must hold):

- `docker build -f apps/web/Dockerfile -t ff-web-test . && docker run --rm ff-web-test
  npm run build` succeeds (tsc + vite).
- `npm run test:e2e:mocked` passes; `test:e2e:backend` passes against a running stack
  with a sample ingest.
- Routes unchanged: `/login`, `/`, `/cases/:caseId`, `/admin/users`,
  `/admin/control-panel`, 404.
- Zero changes to `src/api/client.ts`; no new network calls introduced by the UI.
- Auth flow (login, me, logout, role gating of admin links/routes) unchanged.
- All existing capabilities still reachable: upload (click/drag/keyboard), rename case,
  delete case, cancel job, re-ingest, hash, YARA, ingest history, source info + hash
  export, CSV export, timeline filters + density + histogram zoom, MFT sort/resize/
  paging, browser categories + sort, entity pivots, disk preview + hashes, global
  search, detections search/paging/pivot, rules sync, admin jobs filters, containers
  start/logs, bulk delete, reindex, user management. **No functionality removed.**
- No placeholder/fake data anywhere; all displayed values come from existing API
  responses.

Design-system conformance:

- No element uses Syne; no `animate-in`/fadeUp/pulse-glow remains (`grep` clean).
- Every table on every page uses the §13 spec (header style, row heights, hover/
  selected/focus states present and visibly distinct).
- Severity rendering everywhere goes through the §12 badge/edge system with identical
  colors; severity never conveyed by color alone.
- All interactive elements show a visible focus ring; listbox/keyboard nav still works
  in Timeline/Entities; splitters keyboard-operable; dialogs/drawers trap focus and
  close on Esc.
- Loading = skeletons shaped like content (no layout jump); every view has explicit
  empty and error states matching the specs.
- Timeline renders 100k+ event sources without jank; ≥25 rows visible at 1080p in
  compact density.

Visual criteria:

- No page contains a grid of visually identical oversized cards where a table/list fits
  (Cases grid and stat cards must be gone).
- No gradients (except `.skeleton` shimmer), no glow shadows, no radius > 4px, shadows
  only on overlays.
- Exactly one accent hue (blue family) + severity colors + status colors on screen;
  links and pivots share one style.
- At 1440×900 the case workspace shows context bar + toolbar + data within the first
  200px of vertical space — no hero, no marketing copy.

---

## 19. Screenshot / Visual QA Plan

Use the existing infra: `apps/web/e2e/screenshots.spec.ts` (mocked API, deterministic,
1440×900, writes `docs/screenshots/*.png`; run `npm run screenshots`). Extend the
capture list to:

| Shot | How | Check |
|---|---|---|
| `01-login` | pre-login | flat panel, labels, focus ring on tab |
| `02-cases` | existing | table not cards; row hover captured via `page.hover` |
| `03-overview` | new tab | stat strip ≤ 32px tall; severity bar; sources table |
| `04-timeline` | existing (rename) | 25+ rows, severity edges, inspector populated (click a row first), toolbar single-line |
| `05-entities` | existing | dossier inspector with related events |
| `06-disk` | existing | breadcrumb bar, aligned columns, inspector |
| `07-mft` | existing | §13 header style, pagination footer |
| `08-browser` | existing | category tabs, URL truncation with tooltip title set |
| `09-detections` | new tab | grouped rows, badges, demoted critical line |
| `10-sources` | new tab | upload zone + sources table + (mock active job progress) |
| `11-control-panel` | admin mock | section nav, rules table, containers table |

Per-shot review checklist: spacing on the 4px grid; a single accent hue; mono for all
timestamps/paths/hashes; borders not shadows; no clipped text; empty space justified.
Also capture one **empty-case** shot (no sources) and one **error** shot (mock a 500 on
timeline) to review those states. Compare against pre-redesign shots in
`docs/screenshots/` (regenerate on `main` first and stash copies).

---

## 20. Regression Risks — read before coding

1. **`api/client.ts` is frozen.** Any diff there is out of scope.
2. **Playwright selectors.** The suite pins: heading names ("WKS-042 Investigation",
   "Timeline", "Entities", "MFT Records", "Browser"), button names ("Entities"/"Disk"/
   "MFT" exact, "Create case", "Continue", "Delete", "Close", "Hash all evidence
   files", "View ingest history"), labels ("Case name", "Password", "Job error code
   filter"), classes (`.stat-card--action`, `.virtual-list-container`,
   `.timeline-distribution`, `.mft-*`, `.ingest-status-*`, `.detail-summary`,
   `.status-badge.partial`, `.summary-kpis`, `.view-tab.active`, `li.coverage`,
   `label[for="username"]`). Preserve them or update the spec in the same commit —
   never leave the suite red between commits.
3. **Virtualization:** changing row markup requires `measureElement` refs and
   absolute-position transform to stay exactly as-is; only `estimateSize` values change.
4. **Server paging:** placeholder-row rendering and page-boundary math in TimelineView
   and MftView must not be touched by presentation edits.
5. **Filters:** every timeline filter maps to query params (`q`, `start`, `end`,
   `event_type`, `artifact_type`, `sigma_only`, `mft_only`, `browser_only`,
   `browser_category`) — toolbar consolidation must not drop any.
6. **Focus/pivot mechanics:** `focusEvent`/`focusPath`/`focusEntity` + `setTab` chains
   are the app's connective tissue; re-composition of CaseDetailPage must pass them
   through unchanged. Tab gating on `mft_count`/`browser_count` must survive.
7. **Dialogs:** `useDialog` provides focus trap/esc; drawers must use it, and existing
   `alertdialog` roles/names must not change.
8. **Portals:** source-info/history modals use `createPortal`; the header case-name
   slot adds another — ensure SSR-free Vite context (fine) and null-check the target.
9. **URL state:** tabs are component state; adding `?view=` query sync is P1 optional —
   if done, guard against remount loops and update e2e; if risky, skip.
10. **Auth:** don't alter `ApiAuthError` handling or redirect logic in App.tsx routes.
11. **Reduced motion / skip link / roles:** keep `.skip-link`, `role="option"` listbox
    semantics, `role="separator"` splitter, labeled dialogs.
12. **Docker/dev parity:** verify with the Docker web build (README warns host npm is
    flaky); after changes run `./scripts/rebuild-stack.sh` for browser-visible check.
13. **CSS deletion:** App.css classes may be referenced from multiple views — grep every
    class before deleting its rules (`grep -rn "class-name" src/ e2e/`).

---

## 21. Prioritized Work List

### P0 — Must have (redesign is "done" only with all of these)
1. Token/base rewrite + Syne removal + motion removal (Phase 1).
2. Shell: top bar, CaseNav rail, context bar, extended tab union.
3. Sidebar dissolution: SourcesView + OverviewView extractions.
4. Detections promoted to full view with §12 severity system.
5. Timeline §8 (rows, toolbar, inspector, status line).
6. §13 table spec applied to Cases, MFT, Browser, Entities, Disk, admin tables.
7. All e2e suites green; screenshots regenerated.

### P1 — Important
8. Pivot chip / return-path (§7.4).
9. Cases table filter input; clear-filters affordance in Timeline.
10. Drawer-ization of source info / ingest history / container logs.
11. Collapsible nav rail with localStorage persistence.
12. Histogram collapsible strip treatment.
13. Optional `?view=` URL sync for tabs (with e2e updates).

### P2 — Polish
14. Entities related-detections section; Browser domain→entity pivots.
15. GlobalSearch trigger relocated into top bar.
16. Copy-to-clipboard buttons on paths/hashes/URLs.
17. Middle-truncation helpers unified; tooltip audit.
18. Empty/error-state illustrations-free copy polish.

### P3 — Future (explicitly out of scope now)
19. Settings page (none exists; requires product definition first).
20. Multi-source aggregate timeline; saved filter presets; tagging/bookmarking events.
21. Light theme.
22. Component-level test harness (Vitest) — repo currently has none for web.

---

## 22. Instructions to the Implementation Agent

1. Read this entire plan before editing anything.
2. Before modifying any file, open and read its current contents; this plan describes
   intent, the code is the ground truth for wiring.
3. Preserve existing functionality absolutely: no removed capabilities, no API-client
   changes, no route changes, no new endpoints, no fake data.
4. Implement in the §17 phase order. Foundation first (tokens/base), shell second,
   views after. Never skip ahead to a view restyle before Phase 1–2 land.
5. Keep the app buildable and `npm run test:e2e:mocked` green at every phase boundary;
   update a Playwright selector only in the same commit as the UI change that requires
   it, per §20.2.
6. Reuse before creating: the only new components are CaseNav, Drawer, SeverityBadge,
   SourcesView (extraction), OverviewView (extraction). Everything else is CSS in
   `index.css`/`App.css` and re-composition of existing components.
7. No inline `style={}` for spacing/layout in final code — move existing inline styles
   you touch into classes; don't chase inline styles in files you aren't otherwise
   editing.
8. When a spec here conflicts with something you find in code (a selector, a behavior),
   stop and prefer preserving behavior; note the deviation in your handoff summary.
9. After Phase 6: run `npm run screenshots`, review every image against §19's checklist,
   then run the real-stack check (`./scripts/rebuild-stack.sh`,
   `./scripts/validate-ingest.sh --sample kape-minimal`, browse the case) before
   declaring completion.
10. Fix inconsistencies by extending the shared spec (a class in App.css), never with
    one-off styles per view.
11. Do not "simplify" forensic density away: timestamps stay full ISO UTC, hashes stay
    full in inspectors, counts stay exact.
12. Deliver per phase: a short summary of files changed, tests run and observed results,
    and any spec deviations.
