# Corvus — Forensic Triage Platform

## Purpose
An **offline forensic triage review platform** for digital forensics and incident response (DFIR). Corvus ingests endpoint evidence packages (Windows, macOS, Linux), normalizes artifacts through forensic parsers, runs automated threat detection, and presents evidence in linked investigation views.

## Architecture

```
┌──────────────────┐    REST API     ┌──────────────────┐
│    apps/web      │ ◄─────────────►│    apps/api      │
│   (React+Vite)   │                 │  (FastAPI: 8000)   │
│   port: 5173     │                 └──────────────────┘
└──────────────────┘                         │
                                         Celery queues
                                         │
                                      ┌────┴────┐
                                      │ worker  │
                                      │ (Celery)│
                                      │ port: N/A│
                                      └────┬────┘
                                           │
                                    ┌──────┴────────┐
                                    │ PostgreSQL (Timescale)
                                    │ Redis (broker/cache)
                                    │ OpenSearch (search)
                                    └─────────────────┘
```

### Key Services

| Service | Role |
|---------|------|
| `apps/api` (FastAPI) | REST API, auth, orchestration, health probes |
| `apps/worker` (Celery) | Evidence ingest, parsing, detection, indexing |
| `apps/web` (React+Vite) | Analyst investigation UI — Timeline, Object, Disk, Browser views |
| `packages/corvus_core` | Shared Pydantic schemas and constants |

## Tech Stack

- **Python 3.14** — FastAPI, Celery, SQLAlchemy 2.0, Pydantic v2
- **PostgreSQL 16** + TimescaleDB — primary database; timeline events stored as hypertable
- **Redis** — Celery broker, JWT token revocation, rule sync state
- **OpenSearch 2** — full-text search over timeline/events/filesystems/entities
- **React 19** + **Vite** — frontend investigation workspace
- **External forensic tools** (bundled in worker Docker image):
  - [Eric Zimmerman EZ Tools](https://ericzimmerman.github.io/) — Windows artifact parsing (EvtxECmd, MFTECmd, etc.)
  - [WithSecure Chainsaw](https://github.com/WithSecureLabs/chainsaw) — EVTX hunting
  - [Sigma rules](https://github.com/SigmaHQ/sigma) — detection rule engine
  - [Hindsight](https://github.com/obsidianforensics/hindsight) — Chromium browser forensics
  - [Plaso/log2timeline](https://github.com/log2timeline/plaso) — cross-platform timeline parsing
  - [mac_apt](https://github.com/ydkhatri/mac_apt) — macOS artifact extraction

## Building and Running

### Prerequisites
- Docker Engine 24+ and Docker Compose v2
- 16 GB RAM minimum (32 GB recommended), 500 GB SSD minimum

### Development (fast mode — live code reload)

```bash
# 1. Copy and edit environment
cp .env.example .env

# 2. Start the full stack (api, worker, beat, web, postgres, redis, opensearch)
./scripts/rebuild-stack.sh

# 3. Verify
curl http://localhost:8000/health/ready

# 4. URLs
#   Web:    http://localhost:5173
#   API:    http://localhost:8000
#   Docs:   http://localhost:8000/docs
```

### Development modes

| Command | Description |
|---------|-------------|
| `./scripts/rebuild-stack.sh` | Default: live-mounted code for API/web, prebuilt worker image |
| `./scripts/rebuild-stack.sh --tools` | Uses prebuilt worker-tools image (faster; use when code hasn't changed) |
| `./scripts/rebuild-stack.sh --full` | Full image rebuild (when Dockerfile or dependencies change) |
| `docker compose up -d --build` | Manual Compose rebuild (same as --full) |

### Authentication

Corvus enforces JWT-based authentication by default. Set these before first startup:

```bash
# Required in .env for production; auto-generated in development
AUTH_SECRET_KEY='your-secret-min-32-chars'
AUTH_BOOTSTRAP_ADMIN_USERNAME=admin
AUTH_BOOTSTRAP_ADMIN_PASSWORD='strong-password-here'
```

Roles:
- `administrator` — full workflow + user management + admin endpoints
- `analyst` — normal forensic workflow (no user management)

### Admin/Validation APIs (disabled by default)

```bash
# Enable in .env:
ENABLE_ADMIN_API=true
ENABLE_VALIDATION_API=true

# Rebuild and access admin endpoints:
./scripts/rebuild-stack.sh
curl http://localhost:8000/api/v1/admin/overview
```

## Evidence Pipeline

### Package format

Evidence is ingested as a directory or ZIP file with this recommended structure:

```
WKS-042_20250528/
  manifest.json          ← optional but recommended
  C/                     ← raw target files
  EvidenceOfExecution/   ← parser/module output (pre-parsed CSVs)
  Registry/
  EventLogs/
  ...
```

**Ingest priority:**
1. Parser CSV/JSON output → timeline events
2. Raw artifacts (`.evtx`, registry hives, prefetch, `$MFT`)
3. Collected file paths/timestamps → filesystem nodes

### Ingest workflow

```
Upload ZIP/folder
    │
    ▼
Parse (Plaso/KAPE/EZ Tools/Hindsight)
    │
    ├──→ Timeline events
    ├──→ Entities (users, hosts, files, IPs)
    ├──→ Filesystem nodes
    └──→ Detection hits (Sigma/Chainsaw)
    │
    ▼
Write to PostgreSQL
    │
    ▼
Index to OpenSearch (optional)
```

### Detection engines

| Engine | Description | Config |
|--------|-------------|--------|
| **Sigma** | In-process Python matcher against EvtxECmd CSV | `sigma_profile=dfir|full`, `sigma_refresh_interval_hours=24` |
| **Chainsaw** | Native EVTX hunting with WithSecureLabs rules | `chainsaw_evtx_mode=priority`, `chainsaw_evtx_max=64` |
| **Chainsaw+Sigma** | Sigma rules run within Chainsaw hunt | `chainsaw_include_sigma=true` |
| **YARA** | Static file signature scanning | `yara_enabled=true` |

## Database Schema

Key tables:

- **`cases`** — Investigation projects (UUID, name, description)
- **`evidence_sources`** — Evidence packages per case (platform, collector, hashes, status)
- **`ingest_jobs`** — Async ingest progress + error staging
- **`timeline_events`** — Parsed events (timestamp, type, summary, sigma_hits)
- **`sigma_detections`** — Detection engine results (UNIQUE on source+engine+rule_id)
- **`entities`** — Extracted entities (type, display_name, attributes)
- **`filesystem_nodes`** — Logical filesystem tree
- **`relations`** — Entity-to-entity links
- **`users`** — Auth users (username, bcrypt hash, role)

## Search

Full-text search over timeline events, filesystem paths, and entities:

```bash
GET /api/v1/cases/{caseId}/sources/{sourceId}/search?q=malware&limit=50
```

Fallback to PostgreSQL `ILIKE` if OpenSearch is unavailable.

## Testing

```bash
# API tests
cd apps/api && python -m pytest tests/

# Worker tests
cd apps/worker && python -m pytest tests/

# Web build (via Docker to avoid host npm issues)
docker build -f apps/web/Dockerfile -t ff-web-test .
docker run --rm ff-web-test npm run build

# E2E tests (Playwright)
docker compose run --rm playwright bash -lc 'npm install && npm run test:e2e'
```

## Code Organization

```
corvus/
├── apps/api/          # FastAPI REST API
│   ├── app/
│   │   ├── routers/  # 22 router modules
│   │   ├── services/ # Admin, OpenSearch, Docker, readiness, purge
│   │   ├── auth/     # Local auth + JWT, OIDC stub
│   │   └── util/     # Evidence storage helpers
│   ├── tests/        # pytest
│   ├── alembic/      # DB migrations
│   └── Dockerfile    # Python 3.14-slim, uvicorn
├── apps/worker/       # Celery ingest engine
│   ├── worker/
│   │   ├── tasks/    # ingest, hash_evidence, recovery, rule sync
│   │   ├── chainsaw/ # EVTX selection, hunt, evaluate, sync
│   │   ├── parsers/  # CSV/JSON/CSV parsers, filesystem paths, entities
│   │   ├── sources/  # 8 adapters (KAPE, Plaso, Hindsight, etc.)
│   │   └── util/     # PG sanitization, search indexing
│   ├── tests/        # pytest (20+ files)
│   └── Dockerfile    # Python 3.14 + EZ Tools + Chainsaw + Plaso + Hindsight
├── apps/web/          # React + Vite investigation UI
│   ├── src/
│   │   ├── components/ # Timeline, Objects, Disk, Browser views + panels
│   │   ├── pages/      # Cases, CaseDetail, Login, Admin pages
│   │   ├── api/        # HTTP client wrapper
│   │   └── e2e/        # Playwright E2E tests
│   └── package.json  # React 19, Vite, Playwright
├── packages/corvus_core/  # Shared Pydantic schemas & constants
└── scripts/            # Build, validate, smoke tests, checker scripts
```

## Configuration (Env Vars)

Key toggles in `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `CHAINSAW_ENABLED` | `true` | Enable Chainsaw EVTX hunting |
| `CHAINSAW_INCLUDE_SIGMA` | `true` | Run Sigma rules via Chainsaw |
| `HINDSIGHT_ENABLED` | `true` | Chromium browser forensics |
| `PLASO_ENABLED` | `true` | Plaso log2timeline parsing |
| `PLASO_PARALLEL_ENABLED` | `true` | Parallel parser-family runs |
| `DELETE_EVIDENCE_AFTER_INGEST` | `false` | Auto-delete extracted evidence |
| `SEARCH_BACKEND` | `opensearch` | `opensearch` or `postgres` |
| `SIGMA_REFRESH_INTERVAL_HOURS` | `24` | Auto-refresh Sigma bundles |

## Important Notes

- **No FUSE mounts** — disk images are parsed by Plaso directly, no privileged containers needed
- **TimescaleDB** — `timeline_events` converted to hypertable when TimescaleDB is available
- **Validation mode** — `ff_validation_mode=fast` skips Sigma, Chainsaw, and OpenSearch for CI/testing
- **Rule sync** — Sigma and Chainsaw rules refreshed from GitHub; YARA from Neo23x0
- **Open source license** — MIT for the platform; third-party tools use their own licenses
