# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

ForensicFlow is an offline forensic triage review platform for endpoint investigations. It ingests Windows, macOS, and Linux evidence folders or ZIPs, normalizes parsed and raw artifacts with source adapters and forensic parsers, runs detections, and presents evidence in linked investigation views. KAPE packages are supported, but should be treated as one compatible evidence source rather than the central product definition.

Primary services are defined in `docker-compose.yml`:

- `api`: FastAPI REST API on port 8000.
- `worker`: Celery worker for source-adapter ingest, parsing, entity extraction, Hindsight, and detection.
- `beat`: Celery beat scheduler, mainly for Sigma rule sync.
- `web`: React + Vite UI on port 5173.
- `postgres` and `redis`: persistence and Celery broker/backend.

## Commands

### Run the stack

```bash
cp .env.example .env
docker compose up -d --build
```

Useful URLs:

- Web UI: http://localhost:5173
- API: http://localhost:8000
- API docs: http://localhost:8000/docs
- Readiness: http://localhost:8000/health/ready

After code changes, rebuild the running stack so changes are visible in the browser:

```bash
./scripts/rebuild-stack.sh
# or: docker compose up -d --build
```

### Health and validation

```bash
curl -sf http://localhost:8000/health/ready
./scripts/validate-ingest.sh --sample kape-minimal
MIN_FILESYSTEM_NODES=1 ./scripts/validate-ingest.sh --sample c --max-wait 900
./scripts/sigma-self-test.sh
```

Run parser compatibility checks before choosing Linux vs Windows Server worker deployment:

```bash
./scripts/smoke-test-eztools.sh
```

### API tests

```bash
cd apps/api && python -m pytest tests/
cd apps/api && python -m pytest tests/test_package_extract.py
cd apps/api && python -m pytest tests/test_package_extract.py::test_name
```

### Worker tests

```bash
cd apps/worker && python -m pytest tests/
cd apps/worker && python -m pytest tests/test_hindsight_parser.py
cd apps/worker && python -m pytest tests/test_hindsight_parser.py::test_name
```

### Web build/dev

The README recommends Docker for web builds to avoid host npm issues:

```bash
docker build -f apps/web/Dockerfile -t ff-web-test .
docker run --rm ff-web-test npm run build
```

For local frontend work:

```bash
cd apps/web && npm run dev
cd apps/web && npm run build
cd apps/web && npm run preview
```

There is no lint script/config currently defined for the web package, and no project-level Python lint config is present.

## Architecture notes

### API (`apps/api`)

- FastAPI app setup is in `apps/api/app/main.py`.
- Startup calls `init_db()` from the lifespan hook; schema creation/migration logic lives with the API database/model code.
- Routers are mounted under `/api/v1` for cases, evidence, jobs, validation, ingest outcome, timeline, filesystem, entities, search, stats, Sigma/Chainsaw rules, combined detection rules, and admin endpoints. Health routes are mounted separately.
- Admin and validation routes are controlled by `ENABLE_ADMIN_API` and `ENABLE_VALIDATION_API`.

### Worker (`apps/worker`)

- Celery app and tasks handle evidence ingest asynchronously.
- Main ingest task: `worker.tasks.ingest.process_evidence_package`.
- Ingest flow: select a source adapter, detect package layout, prefer pre-generated parser CSV/JSON output, fall back to raw artifacts where supported, build filesystem nodes, parse browser artifacts via Hindsight, extract entities, run detections where applicable, then bulk insert timeline events, detections, entities, and filesystem nodes.
- Source adapters live under `apps/worker/worker/sources`; KAPE is handled as a compatibility adapter and generic directories are the default adapter.
- macOS/Linux parser integrations are adapter-based: Plaso/log2timeline, mac_apt, UAC import, and Velociraptor import. Windows memory captures use the Volatility3 adapter. See `docs/OPEN-SOURCE-PARSERS.md` for licensing posture.
- Chainsaw hunts raw `.evtx` files. In-process Sigma is used when Chainsaw Sigma integration is disabled (`CHAINSAW_INCLUDE_SIGMA=false`).
- Worker image installs .NET runtime, EZ Tools, Chainsaw, bundled rules, and Hindsight.

### Web (`apps/web`)

- React + Vite application.
- Routes are defined in `apps/web/src/App.tsx`:
  - `/`: cases list.
  - `/cases/:caseId`: investigation workspace.
- Case investigation uses primary views for Timeline, Objects, Disk, MFT, and Browser, plus supporting panels for ingest status, detections/rules, search, and source stats.
- API access is centralized under `apps/web/src/api/client.ts`.

### Shared package (`packages/ff_core`)

Shared Pydantic schemas and constants used across services.

## Evidence and detection model

- Primary input is an endpoint evidence directory or ZIP containing parsed outputs, raw artifacts, filesystem path data, and optional metadata.
- Evidence sources have first-class platform/source metadata: `platform`, `collector_version`, `source_type`, `os_version`, `architecture`, `timezone`, and `collected_at`.
- KAPE collections are supported as one input format, but documentation and UI copy should not frame ForensicFlow as KAPE-only.
- Ingest priority is: parser CSV/JSON output first, raw artifacts second (`.evtx`, registry hives, prefetch, `$MFT`), then collected file paths/timestamps for filesystem nodes.
- Evidence is stored under the Docker `evidence_data` volume mounted at `/data/evidence`; samples are mounted read-only from `./samples`.
- Detection results are shown generically as detections in the UI, with the specific engine (Chainsaw or Sigma) shown on individual match rows.

## Important configuration

Common environment toggles are documented in `.env.example`, `README.md`, and `docker-compose.yml`. Frequently relevant ones include:

- `ENABLE_ADMIN_API`
- `ENABLE_VALIDATION_API`
- `CHAINSAW_ENABLED`
- `CHAINSAW_INCLUDE_SIGMA`
- `CHAINSAW_EVTX_MODE`
- `CHAINSAW_EVTX_MAX`
- `CHAINSAW_EVTX_PARALLEL`
- `CHAINSAW_EVTX_BATCH_SIZE`
- `CHAINSAW_HUNT_BATCH_TIMEOUT_SECONDS`
- `CHAINSAW_SIGMA_PROFILE`
- `SIGMA_PROFILE`
- `SIGMA_REFRESH_INTERVAL_HOURS`
- `HINDSIGHT_ENABLED`
- `HINDSIGHT_MAX_PROFILES`
- `HINDSIGHT_TIMEOUT_SECONDS`

## Deployment assumptions from docs

- Linux server is the default deployment target if critical EZ Tools smoke tests pass.
- If EvtxECmd, MFTECmd, RECmd, AmcacheParser, or PECmd fails on Linux, deploy the Celery worker on Windows Server 2022 with native EZ Tools binaries while API and web can remain in Docker.
- v1 scope is endpoint triage files and MFT exports, not full E01/RAW image mounting.
