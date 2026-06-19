# Deployment

## OS selection (Phase 0 gate)

Run parser smoke tests before production deploy:

```bash
./scripts/smoke-test-eztools.sh    # Linux
./scripts/smoke-test-eztools.ps1   # Windows Server
```

| Result | Deploy target |
|--------|----------------|
| All v1 parsers pass on Linux | **Linux server** + Docker Compose (default) |
| Any critical parser fails | **Windows Server 2022** — native `.exe` EZ Tools |

Critical parsers: EvtxECmd, MFTECmd, RECmd, AmcacheParser, **PECmd**.

## Linux (default)

```bash
docker compose up --build -d
```

### Database migration contract

Schema changes are managed by Alembic revisions in `apps/api/alembic/versions/`.

Deploy order:

1. Build/start updated API image.
2. Run migration smoke/upgrade checks:
   - `docker compose exec -T api bash /app/apps/api/scripts/check_migrations.sh`
3. Verify API readiness:
   - `curl -sf http://localhost:8000/health/ready`

Rollback expectations:

- Prefer restoring database backups for destructive rollback scenarios.
- `alembic downgrade` is available for development/testing but may not fully reverse data-destructive transitions.
- Use expand/contract migrations for high-risk schema/data changes to minimize rollback risk.

Services: `api`, `worker`, `web`, `postgres`, `redis`.

Worker image includes .NET 9 runtime; EZ Tools installed to `/opt/eztools` at image build (see `apps/worker/Dockerfile`). Tool zip SHA-256 pins live in `scripts/eztools-checksums.sha256` (2026.5.0 as of May 2026); regenerate with `scripts/capture-eztools-checksums.sh`.

### Sizing (starting point)

| Resource | Minimum | Comfortable |
|----------|---------|-------------|
| CPU | 4 cores | 8+ |
| RAM | 16 GB | 32 GB |
| Disk | 500 GB SSD | 1 TB+ dedicated evidence volume |

## Windows Server (fallback)

Run the same components without Linux-only assumptions:

| Component | Path / notes |
|-----------|----------------|
| EZ Tools | `C:\Corvus\tools\` — sync via `Get-ZimmermanTools.ps1` |
| API | Python 3.12 venv, Windows service or IIS reverse proxy |
| Worker | Celery worker service on same host |
| Evidence | `D:\Corvus\evidence` |
| Postgres / Redis | Native install or Docker Desktop |

Use `docker-compose.windows.yml` pattern (future): API + web in containers optional; **workers on Windows host** with native EZ Tools is simplest for v1.

## Environment variables

See [.env.example](../.env.example).

## Optional macOS/Linux parser tooling

The default worker image keeps third-party parser installation conservative. To
install permissive open-source parser tools during the worker build:

```bash
INSTALL_OPEN_FORENSICS=true docker compose up -d --build
```

This enables Plaso/log2timeline and mac_apt installation.

Velociraptor exports are supported as imports, but Velociraptor is not bundled
because it is AGPL licensed. See [OPEN-SOURCE-PARSERS.md](OPEN-SOURCE-PARSERS.md).

## Evidence storage

`EVIDENCE_ROOT` must be a fast volume with ample space. Exclude real-time AV scanning on ingest paths when policy allows.
