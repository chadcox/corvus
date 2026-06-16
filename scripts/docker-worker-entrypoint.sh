#!/usr/bin/env bash
# Seed writable Sigma and Chainsaw rule volumes from image bundles when empty.
set -euo pipefail

seed_if_empty() {
  local bundled="$1"
  local root="$2"
  local label="$3"
  local pattern="${4:-*.yml}"
  mkdir -p "${root}"
  if ! find "${root}" -name "${pattern}" -print -quit 2>/dev/null | grep -q .; then
    if [[ -d "${bundled}" ]] && find "${bundled}" -name "${pattern}" -print -quit 2>/dev/null | grep -q .; then
      echo "Seeding ${label} from image bundle into ${root}…"
      cp -a "${bundled}/." "${root}/"
    fi
  fi
}

seed_if_empty "${SIGMA_RULES_BUNDLED:-/opt/sigma-bundled}" "${SIGMA_RULES_ROOT:-/opt/sigma/rules}" "Sigma rules" "*.yml"
seed_if_empty "${CHAINSAW_RULES_BUNDLED:-/opt/chainsaw-bundled}/rules" "${CHAINSAW_RULES_ROOT:-/opt/chainsaw/rules}" "Chainsaw rules" "*.yml"
seed_if_empty "${YARA_RULES_BUNDLED:-/opt/yara-bundled/signature-base}/yara" "${YARA_RULES_ROOT:-/opt/yara/rules}" "YARA rules" "*.yara"
if ! find "${YARA_RULES_ROOT:-/opt/yara/rules}" -name '*.yar' -print -quit 2>/dev/null | grep -q .; then
  if [[ -d "${YARA_RULES_BUNDLED:-/opt/yara-bundled/signature-base}/yara" ]] && find "${YARA_RULES_BUNDLED:-/opt/yara-bundled/signature-base}/yara" -name '*.yar' -print -quit 2>/dev/null | grep -q .; then
    cp -a "${YARA_RULES_BUNDLED:-/opt/yara-bundled/signature-base}/yara/." "${YARA_RULES_ROOT:-/opt/yara/rules}/"
  fi
fi
if [[ -f "${YARA_RULES_BUNDLED:-/opt/yara-bundled/signature-base}/yara/zz_smoketest.yar" ]] && [[ ! -f "${YARA_RULES_ROOT:-/opt/yara/rules}/zz_smoketest.yar" ]]; then
  echo "Seeding YARA smoke test rule into ${YARA_RULES_ROOT:-/opt/yara/rules}…"
  cp "${YARA_RULES_BUNDLED:-/opt/yara-bundled/signature-base}/yara/zz_smoketest.yar" "${YARA_RULES_ROOT:-/opt/yara/rules}/zz_smoketest.yar"
fi
CHAINSAW_MAP_BUNDLED="${CHAINSAW_RULES_BUNDLED:-/opt/chainsaw-bundled}/mappings"
CHAINSAW_MAP_ROOT="${CHAINSAW_MAPPINGS_ROOT:-/opt/chainsaw/mappings}"
mkdir -p "${CHAINSAW_MAP_ROOT}"
if ! find "${CHAINSAW_MAP_ROOT}" -name '*.yml' -print -quit 2>/dev/null | grep -q .; then
  if [[ -d "${CHAINSAW_MAP_BUNDLED}" ]]; then
    echo "Seeding Chainsaw mappings into ${CHAINSAW_MAP_ROOT}…"
    cp -a "${CHAINSAW_MAP_BUNDLED}/." "${CHAINSAW_MAP_ROOT}/"
  fi
fi

if [[ "${CHAINSAW_INCLUDE_SIGMA:-true}" == "true" ]] && [[ "${CHAINSAW_SIGMA_PROFILE:-dfir}" == "dfir" ]]; then
  python3 -c "
from worker.chainsaw.sigma_rules import resolve_sigma_rules_root
resolve_sigma_rules_root('dfir')
print('Sigma DFIR cache ready')
" 2>/dev/null || true
fi

# Initialise Redis rule-status keys from actual file counts so the UI shows
# the correct numbers immediately on first deploy (before any sync task runs).
python3 - << 'PYEOF'
import sys
try:
    from pathlib import Path
    from worker.config import settings
    import redis, json
    r = redis.Redis.from_url(settings.redis_url, decode_responses=True)

    # Sigma
    sigma_key = "forensicflow:sigma:rules:status"
    raw = r.get(sigma_key)
    current = json.loads(raw) if raw else {}
    if not current.get("rule_count"):
        count = len(list(Path(settings.sigma_rules_root).rglob("*.yml")))
        if count > 0:
            from worker.sigma.sync_meta import write_status
            write_status(state="ok", rule_count=count,
                         message=f"Ready — {count:,} rules seeded from image bundle.")
            print(f"Sigma status initialised: {count} rules")

    # Chainsaw
    cw_key = "forensicflow:chainsaw:rules:status"
    if not r.get(cw_key):
        r_count = len(list(Path(settings.chainsaw_rules_root).rglob("*.yml")))
        m_count  = len(list(Path(settings.chainsaw_mappings_root).rglob("*.yml")))
        if r_count > 0:
            from worker.chainsaw.sync_meta import write_status as cw_write
            cw_write(state="ok", rule_count=r_count, mapping_count=m_count,
                     binary_available=True,
                     message=f"Ready — {r_count:,} chainsaw rules seeded from image bundle.")
            print(f"Chainsaw status initialised: {r_count} rules")
except Exception as exc:
    print(f"Warning: rule status init skipped — {exc}", file=sys.stderr)
PYEOF

exec "$@"
