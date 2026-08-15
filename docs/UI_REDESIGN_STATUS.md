# UI Redesign — Implementation Status

Companion to [UI_REDESIGN_PLAN.md](UI_REDESIGN_PLAN.md). Tracks what is actually built,
what was learned, and what the next phase must not trip over.

Last updated: 2026-08-15. Working tree state: **Phase 1 is committed (`3027c60`); Phase 2 is
this commit.** Phases 3-6 are not started.

Phase 2 in one line: the case workspace is now a shell — nav rail, context bar, stat strip,
and a single right-hand `Drawer` — with the pure formatting logic pulled out of
`CaseDetailPage.tsx` into `src/lib/caseFormat.ts` behind a 53-test vitest gate lane.

## Phase status

| Phase | Scope | Status |
| --- | --- | --- |
| 1 | Foundation — tokens, fonts, motion, new CSS sections | **Implemented** (see caveats) |
| 2 | Shell — top bar, CaseNav, Drawer, SeverityBadge, CaseDetailPage re-composition | **Implemented** (see caveats) |
| 3 | Extraction views — SourcesView, OverviewView, Detections | Not started |
| 4 | Investigation views — Timeline, Object, Disk, MFT, Browser | Not started |
| 5 | Peripheral pages — Cases, Control Panel, Admin Users, Login, GlobalSearch, IngestStatusPanel | Not started |
| 6 | QA hardening — dead CSS purge, states, a11y, screenshots, backend smoke | Not started |

---

## Phase 1 — what actually changed

Files touched: `apps/web/src/index.css`, `apps/web/src/App.css`, `apps/web/src/main.tsx`,
`apps/web/package.json`, `apps/web/e2e/analyst-flows.spec.ts`, plus a mechanical class sweep
across 10 `.tsx` files. Net ~334 insertions / ~169 deletions.

### 1. Palette replaced (`index.css` `:root`)

Commercial-security blue/slate → forensic-workbench desaturated neutrals, per plan §3.1.

- **Surfaces are now opaque hex, not `rgba()`.** `--surface` `rgba(19,26,42,.96)` → `#14171c`.
  Nothing stacks translucency anymore; layering reads by value, not by alpha compounding.
- Severity ramp moved to GitHub-dark-adjacent values: `--critical/--danger` `#f85149`,
  `--high` `#f0883e`, `--medium/--warn` `#d29922`, `--low` `#58a6ff`, `--success` `#3fb950`,
  `--info` `#8b949e`. All `*-dim` companions are now opaque near-black tints
  (e.g. `--critical-dim: #2d1517`) instead of alpha washes.
- `--primary` `#2563eb` → `#2f6fed`; `--focus-ring` `#60a5fa` → `#82b1ff`.
- **`--cyan` / `--cyan-dim` were not deleted** — they are aliased to
  `--primary-bright` / `--primary-dim`. Cyan is retired visually while existing references
  keep resolving. Phase 2–5 should drop the references, then drop the aliases in Phase 6.

### 2. Density and geometry

| Token | Before | After |
| --- | --- | --- |
| root `font-size` | 15px | 14px |
| root `line-height` | 1.55 | 1.5 |
| `--header-height` | 56px | 44px |
| `--sidebar-width` | 320px | 200px |
| `--context-bar-height` | — | 40px (new) |
| `--radius-sm` / `--radius` / `--radius-lg` | 4 / 6 / 8px | 2 / 3 / 4px |

New spacing scale added: `--space-xs` 4px, `-sm` 8, `-md` 12, `-lg` 16, `-xl` 24, `-2xl` 32.
Buttons and inputs now share `min-height: 28px`, `font-size: 13px`, `padding: 0 10px`/`0 8px`.

### 3. Fonts — correction to an earlier claim

Libre Franklin and Red Hat Mono were **already** bundled via `@fontsource` before this work.
Phase 1 did not add them. What Phase 1 did:

- **Removed `@fontsource/syne`** from `package.json`, `package-lock.json`, and the three
  `main.tsx` imports (600/700/800).
- Repointed `--font-display` from `"Syne", system-ui, sans-serif` to `var(--font-body)`.
  The `.display` utility class still exists and still works; it is now a no-op visually.
- `--font-mono` gained `ui-monospace` ahead of the `Courier New` fallback, and `.mono` gained
  `font-variant-numeric: tabular-nums` + `font-size: 12.5px`.
- Font-loading e2e assertion dropped from 8 faces to **5**.

### 4. Motion stripped

Deleted from `index.css`: `@keyframes fadeUp`, `fadeIn`, `pulse-glow`, and the
`.animate-in` / `.animate-in-delay-1..4` classes. `html { scroll-behavior: smooth }` removed.
Button `:active { transform: translateY(1px) }` removed.

**Kept intentionally:** `@keyframes progress-indeterminate` and `@keyframes skeleton-sweep` —
these communicate real system state and are not decorative.

All `animate-in*` class usages were swept from the 10 consuming `.tsx` files.
Verified zero dangling references remain for `animate-in`, `fadeUp`, `fadeIn`, `pulse-glow`,
and `--shadow-glow`.

### 5. Focus rings — convention change (breaking for new code)

Focus moved from `box-shadow: 0 0 0 3px …` to real outlines. `--shadow-glow` was deleted.

```css
/* the convention every new interactive element must follow */
:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 1px; }
input:focus, select:focus { outline: 2px solid var(--focus-ring); outline-offset: -1px; }
```

Inputs use a negative offset so the ring sits inside the control and does not shift table rows.

### 6. New App.css sections

Three spec-backed sections were added: `Table spec (§13)`, `Severity system (§12)`,
`Pivot affordance (§7)`. They are additive — no existing selector was deleted yet.
Dead-CSS purge is deliberately deferred to Phase 6, so `App.css` is currently *larger*
than it will end up.

---

## Phase 2 — what actually changed

Net across the working tree: **13 modified files, 1270 insertions / 788 deletions** (excluding
`package-lock.json` and six regenerated screenshots) plus **7 new files, 870 lines**:
`src/components/CaseNav.tsx` (173), `Drawer.tsx` (62), `SeverityBadge.tsx` (81),
`src/lib/caseFormat.ts` (111), their tests (`SeverityBadge.test.ts` 114,
`caseFormat.test.ts` 313), and `vitest.config.ts` (16).

### 1. The case workspace became a shell

`CaseDetailPage.tsx` was re-composed (1256 lines changed, 1137 now) into:

- **Nav rail** (`CaseNav`) — the eight case tabs as a vertical `nav` with inline SVG icons,
  per-tab counts, and a severity badge on Detections. `aria-current="page"` marks the active
  tab; the rail collapses to `--sidebar-width-collapsed` (44px) and the collapsed state
  persists in `localStorage` under `corvus.navCollapsed` (`NAV_COLLAPSED_KEY`,
  `CaseDetailPage.tsx:58`). Collapsed labels stay reachable via `title` + `aria-label`, which
  is what the e2e test asserts — collapsing must not drop the accessible name.
- **Context bar** — case name, source selector, and the actions that used to sit in a header
  block. 40px, `--context-bar-height`, sticky under the top bar.
- **Stat strip** — the per-source counts as `button.stat-card--action` pivots into the
  matching view, rather than static cards.
- **Drawer** — one right-hand overlay component replaces the two hand-rolled centered modals
  (ingest history, source info). `createPortal` to `document.body`, `useDialog` for focus
  trap and focus restore, close on backdrop click and `Escape`, default width 420px.

App-level: `App.tsx` top bar restyled to the 44px shell with a `Cases / <case name>`
breadcrumb, case mode goes full-bleed, and the NotFound page was restyled to match.

### 2. Pure logic left the component

Everything in `CaseDetailPage.tsx` that was same-input-same-output moved to
`src/lib/caseFormat.ts`: `sourceCollectorLabel`, `sourcePlatformLabel`, `formatDuration`,
`formatCompactStat`, `topSeverity`, `isActiveJob`, `jobDisplayStatus`, `packageFileName`,
`formatIngestHistoryMessage`, plus `ACTIVE_JOB_STATUSES`, `SEVERITY_RANK`, `PARTIAL_MARKERS`.
`SeverityBadge.tsx` similarly exports `severityClass` / `severityClasses` / `severityAbbrev`
over a single `LEVEL_CLASS` map, so severity styling has exactly one definition;
`SigmaFindingsPanel.tsx` now consumes it instead of its own copy.

This is the point of the split: those functions are cheap to test directly and were
previously only reachable through a browser.

### 3. New test lane — vitest

`npm run test:unit` (`vitest run`, `test:unit:watch` for the loop). 53 tests, ~105ms, no
browser, no network, no fixtures. Wired into `.github/workflows/web-build.yml` *ahead* of
the bundle build so a broken helper fails with an assertion instead of a build error.

Two real bugs came out of writing them, both now regression-tested:

- `formatIngestHistoryMessage(" ")` returned `[""]` and painted a blank line in the ingest
  history drawer. Whitespace-only now returns `["No details available."]`.
- A message ending in a separator (`"Ingested 20 events; "`) rendered with a dangling `;`,
  because the section split needs `"; "` exactly. Trailing `[;—\s]+` is now stripped before
  the split.

### 4. e2e additions

Two tests in `analyst-flows.spec.ts` (now 17 there, 22 mocked overall):

- `detail drawers overlay the workspace from every opener and close on the backdrop` — opens
  the drawer from each entry point, asserts the overlay geometry, backdrop close, and that
  focus returns to the opener.
- `nav rail collapse survives reload and keeps its labels reachable` — collapses, reloads,
  asserts the persisted state and that every item still exposes its accessible name.

`backend-analyst-flow.spec.ts` picked up the shell selectors (+6 lines).

### 5. Two crash fixes found by the suite

- `helpers.ts` — the mock `/filesystem` list route was matching before `/preview` and
  `/hashes`, so preview requests got a list payload. Routes are now anchored and ordered.
- `DiskView.tsx:303` — read `preview.offset` / `preview.length` / `preview.file_size` with
  `.toLocaleString()` unguarded and threw `Cannot read properties of undefined` on any
  payload missing them (the browser stack trace points at the served line 571). Each is now
  `?? 0`. The mock bug hid a genuine one: a real API response that omits `file_size` would
  have blanked the whole Disk view, not just that line.

### 6. Caveats — what Phase 2 did not do

- **The old modal CSS is still in `App.css`.** `Drawer` replaced the two case-detail modals,
  but `.modal-backdrop` / `.modal-card` remain for the confirm dialogs elsewhere. The dead
  subset gets purged in Phase 6 with the rest, not now.
- **`--cyan` / `--cyan-dim` references were not dropped.** Phase 1 left them aliased and
  Phase 2 did not sweep them; still on the Phase 3-5 list per §1 above.
- **The severity left-edge is still 3px, not the spec'd 2px** (G6). `SeverityBadge` unified
  the *badge*; the row treatment is a §12 rollout owned by Phase 3/4.
- **Sources got a shell-level view, not the Phase 3 SourcesView.** The `sources` tab and its
  CSS block exist so the nav rail has eight real destinations; the extraction-view rebuild
  (per-source cards, collector detail, re-ingest affordances) is still Phase 3.
- **No visual review.** Screenshots were regenerated so they are not stale, but nobody has
  looked at them against the plan. Phase 6.

---

## Gotchas for the next phase

Read these before writing Phase 3 code.

### G1. `--muted` fails body-text contrast — do not use it for readable text

`--muted` is `#6c7683`. On `--surface-2` (`#191d23`) that is **≈3.6:1** — fine for a
3:1 non-text/large-text floor, below the 4.5:1 body-text floor.

The P0 e2e test asserts `>= 4.5` on `.stat-label`, `.stat-value`, `.view-tab.active`, and
submit buttons, computing the real blended background up the DOM chain. Phase 1 already had
to switch `.stat-label` off `--muted` to pass.

The plan text assigns `--muted` to labels and metadata in several later sections. **Treat
that as a known plan/accessibility conflict**: use `--text-soft` (`#a7aeb8`) for anything a
user reads. Reserve `--muted` for icons, separators, and disabled affordances.

### G2. Assert outlines, not box-shadows, in tests

`analyst-flows.spec.ts` now asserts `outline-style: solid` and
`outline-color: rgb(130, 177, 255)` — that RGB is `--focus-ring` `#82b1ff`. Any change to
`--focus-ring` breaks the suite in two places. Any new focusable element styled with
`box-shadow` will silently violate the established convention.

### G3. Build only inside Docker

Host `node_modules` under `apps/web` has root-owned paths from prior container runs; host
`npm install` / `vite build` hit `EACCES`. Use the documented path:

```bash
docker build -f apps/web/Dockerfile -t ff-web-test .
docker run --rm ff-web-test npm run build
```

The mocked e2e suite likewise runs in `mcr.microsoft.com/playwright:v1.61.0-noble` on the
`corvus_default` network with `PLAYWRIGHT_USE_WEBSERVER=0` and
`PLAYWRIGHT_BASE_URL=http://web:5173`. Playwright writes `test-results/` as root — it is
untracked and should stay that way.

**Phase 2 addendum — adding a dependency.** `vitest` could not be installed from the host
(`npm error code EACCES ... @rollup/rollup-linux-x64-gnu`, root-owned `node_modules`). The
working sequence, for the next time a package is added:

```bash
docker run --rm -v "$PWD/apps/web:/app" -w /app node:20-alpine \
  npm install -D vitest --ignore-scripts   # updates package.json + package-lock.json
docker compose build web && docker compose up -d web
```

`--ignore-scripts` avoids writing platform binaries into the bind mount; the real install
happens in the image build. `npm run test:unit` then runs in the `web` container.

### G4. The `impeccable` design hook conflicts with the plan

The Stop hook flags `App.css`/`index.css` against `DESIGN.md` and its sidecar tonal ramps,
reporting literal colors and off-ramp font sizes as drift (100+ findings on the last pass).
`UI_REDESIGN_PLAN.md` is the authority for this work; `DESIGN.md` predates it and is stale.

Do not churn the palette to satisfy the hook. Either refresh the design sidecar
(`/impeccable document`) or record scoped ignores.

**Phase 2 update:** the hook entries were removed from `.claude/settings.local.json` at the
start of Phase 2, so it no longer fires on Stop. `.impeccable/` (config, cache, critique,
`design.json`) is still on disk. Still unresolved on the merits — if the hook is ever
re-enabled, refresh the sidecar from `UI_REDESIGN_PLAN.md` first or it will re-flag every
Phase 1/2 token.

### G5. Opaque surfaces change stacking

Overlays, drawers, popovers, and sticky table headers previously relied on translucent
surfaces reading correctly over whatever sat beneath. With opaque tokens, anything that
needs separation now needs an explicit border or `--shadow`.

**Phase 2 result:** confirmed. `.drawer-panel` needs all three — `background: var(--surface)`,
`border-left: 1px solid var(--border-strong)`, and `box-shadow: -12px 0 32px rgba(0,0,0,0.45)`
— to read as a layer above the workspace. `.drawer-head` carries its own `--surface-2` so it
stays opaque when the body scrolls under it. The `rgba(0,0,0,0.5)` backdrop at `z-index: 60`
(panel at 61) does the rest.

### G6. Severity rails are spec-intended — and currently off-spec at 3px

`.item-list-row.sigma-hit-row` (`App.css` L2491 after Phase 2) uses
`border-left: 3px solid var(--critical)`.
The design hook flags this as a `side-tab` accent. It is **not** decoration: plan §12
specifies a left edge as the systematic row treatment for all five severity levels, always
paired with a `SeverityBadge` whose text carries the level so color is never the only signal.

Two things to carry into Phase 3/4:

- The spec says **2px**; the code is **3px**. Fix it as part of the §12 rollout, not as a
  one-off — the whole row treatment is being rebuilt.
- Only `critical` gets the `*-dim` row fill. `high`/`medium`/`low` get the edge alone, and
  `informational` gets the edge with no fill.

Expect the design hook to keep flagging this rule for the whole redesign. It is a known,
justified divergence; decide once whether to persist a scoped ignore rather than re-litigating
it each pass.

### G7. Route-order bugs in the e2e mocks masquerade as app bugs

`installApiMocks` (`e2e/helpers.ts`) registers Playwright routes in order and the first glob
match wins. The `/filesystem` list route was shadowing `/filesystem/preview` and
`/filesystem/hashes`, so `DiskView` got a list payload where it expected a preview and
crashed on a missing field. Two rules for Phases 3-5, which add a lot of mocks:

- Register the most specific path first, or anchor the glob (`**/filesystem?**` will eat
  `**/filesystem/preview**`).
- When a view crashes under mocks, check the payload the mock actually returned before
  touching the component. Here both were wrong, and the mock hid the real one.

### G8. Component tests go in the vitest lane, not Playwright

`npm run test:unit` exists now (53 tests, ~105ms). Anything that is pure input → output —
formatters, rank/sort helpers, class-name mappers, status derivation — belongs there. Reserve
Playwright for what needs a real DOM, routing, or a network round trip. Phase 3's
SourcesView/OverviewView extraction should push its formatting helpers into
`src/lib/caseFormat.ts` (or a sibling in `src/lib/`) as it goes, rather than leaving them
inline and untested.

### G9. Severity styling has exactly one definition now

`SeverityBadge.tsx` owns `LEVEL_CLASS` and exports `severityClass` / `severityClasses` /
`severityAbbrev`. `SigmaFindingsPanel.tsx` was converted; any Phase 3/4 view that renders a
level must import from there rather than re-deriving `sigma-level-*` strings. Note the
deliberate fallback: an unknown or null level maps to `sigma-level-medium`, not to a
throw or a blank — asserted in `SeverityBadge.test.ts`.

---

## Verification status

### Phase 1

| Check | Result |
| --- | --- |
| `docker run --rm ff-web-test npm run build` | Passed — clean production build |
| Dangling-reference greps (`animate-in`, `fadeUp`, `fadeIn`, `pulse-glow`, `--shadow-glow`) | Passed — zero hits |
| TypeScript / `vite build` type errors | Passed as part of the image build |
| Mocked Playwright suite (`smoke`, `analyst-flows`, `control-panel`) | Passed — **20/20 in 5.8s**, run after the final contrast/focus fixes |
| Backend smoke (`validate-ingest.sh`, `sigma-self-test.sh`) | Not run — no backend change in Phase 1 |
| Visual screenshot review beyond `04-mft.png` | Not done — deferred to Phase 6 |

### Phase 2

| Check | Result |
| --- | --- |
| `npm run test:unit` (vitest) | Passed — **53/53 in ~105ms**, new lane |
| Mocked Playwright suite (`smoke`, `analyst-flows`, `control-panel`) | Passed — **22/22 in 7.6s** (20 → 22: drawer overlay, nav collapse persistence) |
| Backend Playwright flow (`backend-analyst-flow.spec.ts`, `PLAYWRIGHT_BACKEND_E2E=1`) | Passed — **1/1** against the live stack with real ingest data |
| `docker build -f apps/web/Dockerfile` → `npm run build` | Passed — clean production build |
| CI workflow (`.github/workflows/web-build.yml`) | Updated — `test:unit` runs before the bundle build |
| Screenshots | Regenerated — `02-cases`, `03-timeline`, `04-browser`, `04-disk`, `04-entities`, `04-mft` |
| Backend smoke (`validate-ingest.sh`, `sigma-self-test.sh`) | Not run — no backend change in Phase 2 (the API fix in `69bbb25` was verified separately) |
| Visual screenshot review | Not done — still deferred to Phase 6 |

Reproduce the two Playwright lanes:

```bash
docker compose run --rm --no-deps \
  -e PLAYWRIGHT_USE_WEBSERVER=0 -e PLAYWRIGHT_BASE_URL=http://web:5173 \
  playwright npm run test:e2e:mocked

docker compose run --rm \
  -e PLAYWRIGHT_USE_WEBSERVER=0 -e PLAYWRIGHT_BASE_URL=http://web:5173 \
  -e PLAYWRIGHT_BACKEND_E2E=1 \
  playwright npx playwright test e2e/backend-analyst-flow.spec.ts --reporter=line
```

The `web` container serves the bind-mounted tree through vite, so source edits are live and
no rebuild is needed between e2e runs.

**Stale artifact warning:** there is a root-owned `test-results/.last-run.json` at the
**repository root** still reading `"status": "failed"`, left by an earlier run invoked from
the wrong directory. The authoritative file is `apps/web/test-results/.last-run.json`
(`"status": "passed"`), because `playwright.config.ts` resolves relative to `apps/web`.
Ignore or remove the repo-root copy; do not read Phase 1 status from it.

Reproduce the passing run with:

```bash
docker run --rm --network corvus_default -v "$PWD/apps/web:/w" -w /w \
  -e PLAYWRIGHT_BASE_URL=http://web:5173 -e PLAYWRIGHT_USE_WEBSERVER=0 \
  mcr.microsoft.com/playwright:v1.61.0-noble \
  npx playwright test e2e/smoke.spec.ts e2e/analyst-flows.spec.ts e2e/control-panel.spec.ts \
  --reporter=line
```

---

## Next — Phase 3 entry point

Phase 3 is the extraction views (plan §6.1-6.3): SourcesView, OverviewView, Detections. The
shell is done, so these are now pure content rebuilds inside `.case-content` — no layout
plumbing left to fight.

Suggested order:

1. **SourcesView** — the largest win and the thinnest current implementation. Per-source
   cards, collector/platform detail, ingest history entry point (the `Drawer` already exists),
   re-ingest and delete affordances.
2. **OverviewView** — the stat strip is already pivoting correctly; this is about the summary
   panels beneath it (top severities, top hosts, coverage gaps).
3. **Detections** — the §12 severity rollout lands here: left-edge to 2px, `SeverityBadge`
   everywhere, `*-dim` fill only for critical (G6, G9).

Do the helper extraction as you go, not after (G8). Both new views should ship with vitest
coverage for their formatters in the same commit.
