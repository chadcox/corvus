# UI Redesign — Implementation Status

Companion to [UI_REDESIGN_PLAN.md](UI_REDESIGN_PLAN.md). Tracks what is actually built,
what was learned, and what the next phase must not trip over.

Last updated: 2026-08-15. Working tree state: **all Phase 1 work is uncommitted.**

## Phase status

| Phase | Scope | Status |
| --- | --- | --- |
| 1 | Foundation — tokens, fonts, motion, new CSS sections | **Implemented** (see caveats) |
| 2 | Shell — top bar, CaseNav, Drawer, SeverityBadge, CaseDetailPage re-composition | Not started |
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

## Gotchas for the next phase

Read these before writing Phase 2 code.

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

### G4. The `impeccable` design hook conflicts with the plan

The Stop hook flags `App.css`/`index.css` against `DESIGN.md` and its sidecar tonal ramps,
reporting literal colors and off-ramp font sizes as drift (100+ findings on the last pass).
`UI_REDESIGN_PLAN.md` is the authority for this work; `DESIGN.md` predates it and is stale.

Do not churn the palette to satisfy the hook. Either refresh the design sidecar
(`/impeccable document`) or record scoped ignores. Unresolved as of Phase 1.

### G5. Opaque surfaces change stacking

Overlays, drawers, popovers, and sticky table headers previously relied on translucent
surfaces reading correctly over whatever sat beneath. With opaque tokens, anything that
needs separation now needs an explicit border or `--shadow`. Phase 2's Drawer and top bar are
the first real test of this.

### G6. Severity rails are spec-intended — and currently off-spec at 3px

`.item-list-row.sigma-hit-row` (`App.css` L2236) uses `border-left: 3px solid var(--critical)`.
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

### G7. Phase 1 is uncommitted

Nothing has been committed. `docs/UI_REDESIGN_PLAN.md`, this file, and `test-results/` are
untracked; the 16 source/asset files are modified in place. `docs/screenshots/04-mft.png` was
regenerated and differs. Commit Phase 1 before starting Phase 2 so the phases stay
independently reviewable and revertible.

---

## Verification status

| Check | Result |
| --- | --- |
| `docker run --rm ff-web-test npm run build` | Passed — clean production build |
| Dangling-reference greps (`animate-in`, `fadeUp`, `fadeIn`, `pulse-glow`, `--shadow-glow`) | Passed — zero hits |
| TypeScript / `vite build` type errors | Passed as part of the image build |
| Mocked Playwright suite (`smoke`, `analyst-flows`, `control-panel`) | Passed — **20/20 in 5.8s**, run after the final contrast/focus fixes |
| Backend smoke (`validate-ingest.sh`, `sigma-self-test.sh`) | Not run — no backend change in Phase 1 |
| Visual screenshot review beyond `04-mft.png` | Not done — deferred to Phase 6 |

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
