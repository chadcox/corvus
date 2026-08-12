# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

**Primary: the solo DFIR consultant.** One analyst working an engagement on their own workstation or a dedicated lab host, triaging a handful of endpoint evidence collections at a time. They run the stack themselves, they are the only person looking at the case, and the clock between "ZIP lands on disk" and "first defensible finding" is the thing they are judged on.

Corvus also ships `administrator` and `analyst` roles with local username/password + JWT auth (`apps/api/app/auth/`), so a second analyst or an admin who only manages users is supported. Design decisions resolve in favor of the solo analyst; multi-analyst collaboration is not a confirmed audience.

## Product Purpose

Corvus is an offline forensic triage review platform for endpoint investigations. It ingests Windows, macOS, and Linux evidence folders or ZIPs, normalizes parsed and raw artifacts through source adapters and forensic parsers, runs detections, and presents the result in linked investigation views.

Success is the analyst reaching a correct, evidence-backed conclusion about an endpoint faster than they could by opening parser CSVs by hand — with every claim traceable back to the artifact that produced it.

## Positioning

Three mechanisms a neighboring tool could not truthfully copy at once (user-confirmed):

1. **Linked views.** Timeline, Objects, Disk, MFT, and Browser are one correlated evidence graph, not five separate tools. The analyst pivots from an event to the entity to the file without losing case context.
2. **Multi-platform ingest through source adapters.** One pipeline covers KAPE, UAC, Velociraptor, mac_apt, Plaso, Volatility3 memory, and generic directories (`apps/worker/worker/sources/`), instead of being bound to one collector's output format. KAPE is a compatibility adapter, not the product definition.
3. **Triage speed.** Parsed parser output first, raw artifacts second (`.evtx`, registry hives, prefetch, `$MFT`), collected paths/timestamps third. Findings in minutes from a triage package, with no full disk image required.

Offline operation is true and load-bearing, but the user did not select it as the differentiating claim — treat it as a constraint (below) rather than the headline.

## Operating Context

- Runs as a Docker Compose stack the analyst starts themselves: `api` (FastAPI, :8000), `worker` (Celery ingest queue), `beat` (Sigma rule sync), `web` (React + Vite, :5173), `postgres` (TimescaleDB), `redis`, `opensearch`, optional `playwright`.
- Evidence arrives as an endpoint collection directory or ZIP, stored under the `evidence_data` volume at `/data/evidence`; samples mount read-only from `./samples`.
- Ingest is asynchronous (`worker.tasks.ingest.process_evidence_package`); the analyst watches job progress and partial/failed outcomes rather than waiting on a blocking upload.
- Deployment target is a Linux server by default; the Celery worker moves to Windows Server 2022 with native EZ Tools binaries if the EZ Tools smoke test fails on Linux (`./scripts/smoke-test-eztools.sh`).
- Usage scene is a desktop browser on a trusted host, frequently a lab machine with no internet route.

## Capabilities and Constraints

**Confirmed capabilities**

- Case management, evidence upload/registration, async ingest with job status and explicit partial-result reporting.
- Investigation views: Timeline (with chart), Objects/entities, Disk (logical filesystem from collected paths), MFT, Browser (Hindsight). Supporting panels: ingest status, detections/rules, global search, source stats.
- Detection: Chainsaw hunts over raw `.evtx`, in-process Sigma when `CHAINSAW_INCLUDE_SIGMA=false`, plus YARA and combined detection-rule endpoints. Engine (Chainsaw or Sigma) is shown on the individual match row, not as the product frame.
- Auth: local username/password + JWT, `administrator` / `analyst` roles, admin-only user management, `/api/v1/admin/*`, `/api/v1/validation/*`, `/api/v1/containers/*`.
- Evidence sources carry first-class metadata: `platform`, `collector_version`, `source_type`, `os_version`, `architecture`, `timezone`, `collected_at`.

**Durable constraints (user-confirmed)**

- **Localhost-only default.** Ships as a trusted-host Docker stack with development defaults. UI and copy must never imply a hosted or SaaS product. `SECURITY.md` governs any exposed deployment.
- **Defensive-use framing.** Authorized DFIR and IR work only. The server never executes endpoint collection. The operator is responsible for evidence legality and for third-party tool/rule licenses (`THIRD_PARTY_NOTICES.md`, `docs/OPEN-SOURCE-PARSERS.md`).
- **No invented proof.** MIT-licensed open-source project with no customers, benchmarks, testimonials, case studies, or pricing. No UI or documentation copy may fabricate any of these.

**Repository-sourced scope limits (not user-confirmed as permanent, from `docs/PROJECT.md`)**

- v1 handles triage files and MFT exports, not E01/RAW image mounting.
- Collection execution stays out of scope for the server.
- Multi-user RBAC beyond `administrator`/`analyst` is a stated v1 non-goal, and partial auth work has since landed — treat the long-term ceiling as undecided.

**Terminology** — case, evidence source, ingest job, artifact, timeline event, entity, detection, filesystem node, source adapter. "Detections" is the generic UI term; "Chainsaw" and "Sigma" appear only on match rows.

## Brand Commitments

- Name: **Corvus**. Existing README voice is direct, technical, and warning-forward about authorized use.
- View names are product vocabulary and are binding: **Timeline**, **Objects**, **Disk**, **MFT**, **Browser**.
- No visual identity, palette, or typography has been declared by the user. Nothing in the current implementation is confirmed as intentional brand.

## Evidence on Hand

- Real UI screenshots at `docs/screenshots/` (`02-cases`, `03-timeline`, `04-browser`, `04-disk`, `04-entities`, `04-mft`).
- Sample evidence under `./samples` (`kape-minimal`, `c`) with validation scripts: `./scripts/validate-ingest.sh`, `./scripts/sigma-self-test.sh`.
- Product and architecture docs: `README.md`, `docs/PROJECT.md`, `docs/CODEBASE_MAP.md`, `docs/EVIDENCE-PACKAGE.md`, `docs/PARSER-COMPAT.md`, `docs/DEPLOYMENT.md`, `APPLICATION_AUDIT.md`.
- Playwright e2e suites, including mocked and backed-by-API analyst flows.
- **Absent, must not be fabricated:** users, adoption numbers, performance benchmarks, quotes, logos, certifications, or any deployment claim beyond localhost Docker.

## Product Principles

1. **Evidence over assertion.** Every displayed conclusion traces to the artifact, source, and parser that produced it; unparsed and partial results are stated, never smoothed over.
2. **One case, many lenses.** A pivot between Timeline, Objects, Disk, MFT, and Browser preserves the analyst's place and filters; the views are a single investigation, not separate tools.
3. **Source-agnostic by construction.** Nothing in the product treats one collector, OS, or parser family as the default reality.
4. **Fast to first finding.** Prefer showing a partial, honest result now over a complete result later.
5. **Offline and self-hosted, without apology.** No network dependency, no telemetry, no hosted-product pretense in the interface.

## Accessibility & Inclusion

No product-specific standard has been established by the user. Existing components already carry ARIA roles and attributes (`DiskView`, `GlobalSearch`, `ConfirmDialog`, `LoginPage`, and others), so keyboard operability and screen-reader labeling are the working baseline for dense, table-heavy forensic views. Long review sessions on a desktop browser are the real usage scene.
