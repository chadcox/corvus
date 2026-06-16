#!/usr/bin/env bash
set -euo pipefail

cd /app/apps/api

echo "[migrations] downgrade to base"
alembic downgrade base

echo "[migrations] upgrade to head"
alembic upgrade head

echo "[migrations] current revision"
alembic current
