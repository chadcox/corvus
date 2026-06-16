# Alembic Workflow

This project uses Alembic as the only supported schema change mechanism.

## Rules

- Do not add startup DDL mutations in API code.
- Do not run ad-hoc `ALTER TABLE` outside Alembic revisions.
- Any schema-affecting change in API models/migration helpers must include a new revision under `apps/api/alembic/versions/`.

## Local commands

Run from `apps/api`:

```bash
# show current revision
alembic current

# apply all migrations
alembic upgrade head

# rollback to base (development only)
alembic downgrade base
```

Project smoke check:

```bash
docker compose exec -T api bash /app/apps/api/scripts/check_migrations.sh
```

## Creating a new revision

```bash
cd apps/api
alembic revision -m "describe change"
```

Then implement `upgrade()` (and `downgrade()` when practical) in the new file under `apps/api/alembic/versions/`.

## Migration strategy guidance

### Expand/contract for risky changes

1. Expand: add new nullable columns/tables/indexes.
2. Backfill: migrate data in safe batches.
3. Contract: drop old structures only after code has fully switched.

### Backfill guidance

- Use chunked updates.
- Keep transactions bounded.
- Add retry/continuation for long-running operations.
- Avoid table-wide locks during peak operations.

## CI enforcement

Hosted workflow runs:

- migration guard: schema changes require a revision
- migration smoke: downgrade base -> upgrade head
- integrity tests: single-head + linear chain assertions
- full API regression

Workflow file: `.github/workflows/api-migrations.yml`.
