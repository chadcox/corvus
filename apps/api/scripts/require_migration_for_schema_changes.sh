#!/usr/bin/env bash
set -euo pipefail

BASE_REF="${1:-${GITHUB_BASE_REF:-}}"
if [[ -z "${BASE_REF}" ]]; then
  echo "[migration-guard] No base ref provided; skipping changed-file guard."
  exit 0
fi

cd /workspace

git fetch --no-tags origin "${BASE_REF}" --depth=1 >/dev/null 2>&1 || true
DIFF_RANGE="origin/${BASE_REF}...HEAD"
CHANGED="$(git diff --name-only "${DIFF_RANGE}")"

if [[ -z "${CHANGED}" ]]; then
  echo "[migration-guard] No changed files detected."
  exit 0
fi

SCHEMA_TOUCHED=0
MIGRATION_TOUCHED=0
while IFS= read -r f; do
  case "${f}" in
    apps/api/app/models.py|apps/api/app/schema_migrations.py|apps/api/app/database.py)
      SCHEMA_TOUCHED=1
      ;;
    apps/api/alembic/versions/*.py)
      MIGRATION_TOUCHED=1
      ;;
  esac
done <<< "${CHANGED}"

if [[ "${SCHEMA_TOUCHED}" -eq 1 && "${MIGRATION_TOUCHED}" -eq 0 ]]; then
  echo "[migration-guard] Schema-related files changed without a new Alembic revision."
  echo "[migration-guard] Add at least one file under apps/api/alembic/versions/*.py"
  exit 1
fi

echo "[migration-guard] OK"
