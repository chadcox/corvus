# ForensicFlow — Project Definition

## Vision

Ingest offline endpoint evidence packages from Windows, macOS, and Linux systems and present correlated findings in linked investigation views:

| View | Purpose |
|------|---------|
| **Timeline** | Chronological events across all artifact sources |
| **Object** | Entities (users, processes, files, IPs) and relationships |
| **Disk** | Logical filesystem from collected paths and file metadata (not full E01 imaging in v1) |

## Locked decisions

| Topic | Decision |
|-------|----------|
| Deployment | Linux server default; **Windows Server 2022** if Phase 0 EZ Tools smoke test fails |
| Collection | External endpoint collection tools; collection execution is out of scope for the server |
| Ingest | Evidence folders / ZIPs containing parser output, raw artifacts, filesystem data, and platform/source metadata |
| Parsers | Source adapters plus forensic parsers; EZ Tools are the mature Windows parser family |
| Users | Solo analyst first |
| Disk images | No full disk in v1 — triage files and MFT exports only |
| Stack | Python FastAPI, Celery, PostgreSQL, Redis, React + Vite |

## Roadmap

### Phase 0 (current) — Scaffold

- Monorepo, Docker Compose, DB schema, API stubs, worker stubs, UI shell
- EZ Tools smoke tests; deployment OS gate

### Phase 1 — Evidence Ingest MVP

- Source-adapter registry, package layout detection, CSV/JSON mappers, EZ CLI fallbacks
- Timeline, disk tree, object list with cross-view linking

### Phase 2 — Enrichment

- Entity resolution, bookmarks, tags, export

### Phase 3 — Scale & sources

- Additional macOS/Linux artifacts, Velociraptor, OpenSearch if needed, optional Plaso/disk image path

## Non-goals (v1)

- Running endpoint collection tools on the server
- E01/RAW mounting
- Multi-user RBAC
- Replacing Autopsy / commercial suites
