"""Select Sigma rules useful for incident-response / DFIR investigations."""

from __future__ import annotations

# Noisy Windows channels — rarely actionable during IR triage
_EXCLUDED_PATH_PREFIXES = (
    "rules/windows/builtin/system/",
    "rules/windows/builtin/application/",
)

# EvtxECmd timeline + typical IR triage focus
_DFIR_PATH_HINTS = (
    "rules/windows/builtin/security/",
    "rules/windows/sysmon/",
    "rules/windows/powershell/",
    "rules/windows/registry/",
    "rules/windows/network_connection/",
    "rules/windows/file/",
    "rules/windows/process_creation/",
    "rules-threat-hunting/",
    "rules-dfir/",
)


def is_dfir_relevant(*, rel_path: str, level: str, status: str) -> bool:
    """
    Keep rules an IR analyst would care about on Windows endpoint evidence.

    - Drop deprecated / informational rules
    - Drop system & application builtin noise
    - Security channel: keep medium and above (plus low — often logon context)
    - Process creation: high/critical only (largest category; medium is mostly noise)
    - Other IR categories: medium and above
    """
    level = level.lower()
    status = status.lower()
    rel = rel_path.replace("\\", "/")

    if status == "deprecated":
        return False
    if level == "informational":
        return False
    if any(rel.startswith(prefix) for prefix in _EXCLUDED_PATH_PREFIXES):
        return False
    if not any(hint in rel for hint in _DFIR_PATH_HINTS):
        return False

    if rel.startswith("rules/windows/builtin/security/"):
        return level in ("critical", "high", "medium", "low")

    if "process_creation" in rel:
        return level in ("critical", "high")

    return level in ("critical", "high", "medium")
