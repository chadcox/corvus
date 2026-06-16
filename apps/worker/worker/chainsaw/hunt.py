"""Run Chainsaw hunt against EVTX artefacts in a KAPE package."""

from __future__ import annotations

import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from worker.chainsaw.evtx_select import find_evtx_files
from worker.chainsaw.sigma_rules import resolve_sigma_rules_root
from worker.config import settings

_SLUG_RE = re.compile(r"[^a-z0-9]+")
_UNSET = object()


def chainsaw_available() -> bool:
    return Path(settings.chainsaw_bin).is_file()


def _sigma_mapping_path() -> Path | None:
    mappings = Path(settings.chainsaw_mappings_root)
    preferred = mappings / "sigma-event-logs-all.yml"
    if preferred.is_file():
        return preferred
    for path in sorted(mappings.glob("*.yml")):
        if "sigma" in path.name.lower():
            return path
    return None


def _parse_hunt_stdout(stdout: str) -> list[dict[str, Any]]:
    stdout = (stdout or "").strip()
    if not stdout:
        return []
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        for line in reversed(stdout.splitlines()):
            line = line.strip()
            if line.startswith("["):
                try:
                    data = json.loads(line)
                    break
                except json.JSONDecodeError:
                    continue
        else:
            return []

    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        for key in ("hits", "detections", "results", "documents"):
            val = data.get(key)
            if isinstance(val, list):
                return [row for row in val if isinstance(row, dict)]
    return []


def run_chainsaw_hunt(
    evtx_paths: list[Path],
    *,
    sigma_root: Path | None | object = _UNSET,
) -> list[dict[str, Any]]:
    """Execute ``chainsaw hunt`` on one EVTX batch and return parsed JSON hits."""
    if not evtx_paths or not chainsaw_available():
        return []

    rules_evtx = Path(settings.chainsaw_rules_root) / "evtx"
    if not rules_evtx.is_dir():
        rules_evtx = Path(settings.chainsaw_rules_root)
    if not rules_evtx.is_dir():
        return []

    cmd: list[str] = [
        settings.chainsaw_bin,
        "hunt",
        "--json",
        "-q",
        "--skip-errors",
        "-r",
        str(rules_evtx),
    ]

    if sigma_root is _UNSET:
        sigma_root = resolve_sigma_rules_root()
    if sigma_root is not None:
        mapping = _sigma_mapping_path()
        if mapping and mapping.is_file() and Path(sigma_root).is_dir():
            cmd.extend(["-s", str(sigma_root), "-m", str(mapping)])

    cmd.extend(str(p) for p in evtx_paths)

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=settings.chainsaw_hunt_batch_timeout_seconds,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []

    return _parse_hunt_stdout(proc.stdout or "")


def _evtx_batches(paths: list[Path]) -> list[list[Path]]:
    size = max(1, settings.chainsaw_evtx_batch_size)
    return [paths[i : i + size] for i in range(0, len(paths), size)]


def run_chainsaw_hunt_parallel(
    evtx_paths: list[Path],
    *,
    sigma_root: Path | None | object = _UNSET,
) -> list[dict[str, Any]]:
    """Run Chainsaw hunt in parallel over EVTX batches; merge hits."""
    if not evtx_paths:
        return []
    if sigma_root is _UNSET:
        sigma_root = resolve_sigma_rules_root()

    batches = _evtx_batches(evtx_paths)
    if len(batches) == 1:
        return run_chainsaw_hunt(batches[0], sigma_root=sigma_root)

    workers = min(max(1, settings.chainsaw_evtx_parallel), len(batches))
    hits: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(run_chainsaw_hunt, batch, sigma_root=sigma_root): batch
            for batch in batches
        }
        for future in as_completed(futures):
            try:
                hits.extend(future.result())
            except Exception:
                continue
    return hits


def collect_evtx_for_hunt(package_dir: Path) -> list[Path]:
    """Package EVTX list using configured priority / limits."""
    return find_evtx_files(
        package_dir,
        max_files=max(1, settings.chainsaw_evtx_max),
        mode=settings.chainsaw_evtx_mode,
    )


def _slug(value: str) -> str:
    return _SLUG_RE.sub("-", value.lower()).strip("-")[:96] or "rule"


def _first_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return str(value[0]) if value else ""
    return str(value)


def _field(hit: dict[str, Any], *keys: str) -> str:
    for key in keys:
        if key in hit and hit[key] not in (None, ""):
            return _first_str(hit[key])
        for k, v in hit.items():
            if k.lower() == key.lower() and v not in (None, ""):
                return _first_str(v)
    return ""


def _chainsaw_event_system(hit: dict[str, Any]) -> dict[str, Any]:
    """Chainsaw 2.x JSON nests EVTX fields under document.data.Event.System."""
    doc = hit.get("document")
    if not isinstance(doc, dict):
        return {}
    data = doc.get("data")
    if not isinstance(data, dict):
        return {}
    event = data.get("Event")
    if not isinstance(event, dict):
        return {}
    system = event.get("System")
    return system if isinstance(system, dict) else {}


def hit_engine(hit: dict[str, Any]) -> str:
    """Detection engine that produced this Chainsaw hunt hit."""
    source = _field(hit, "source", "Source").lower()
    if source == "sigma":
        return "sigma"
    return "chainsaw"


def hit_rule_id(hit: dict[str, Any]) -> str:
    if hit_engine(hit) == "sigma":
        rid = _field(hit, "id", "Id")
        if rid:
            return f"sigma:{rid}"
    group = _field(hit, "group", "Group") or "chainsaw"
    title = _field(hit, "name", "detections", "title", "Title") or "detection"
    return f"chainsaw:{_slug(group)}:{_slug(title)}"


def hit_title(hit: dict[str, Any]) -> str:
    title = _field(hit, "name", "detections", "title", "Title")
    if title:
        return title[:512]
    return hit_rule_id(hit).split(":")[-1].replace("-", " ").title()[:512]


def hit_level(hit: dict[str, Any]) -> str:
    level = _field(hit, "level", "Level", "severity").lower()
    if level in ("critical", "high", "medium", "low", "informational"):
        return level
    if level == "info":
        return "informational"
    return "medium"


def hit_correlation_keys(hit: dict[str, Any]) -> tuple[str, str, str]:
    """(event_id, record_id, computer) for matching timeline rows."""
    system = _chainsaw_event_system(hit)
    eid = _field(hit, "Event ID", "EventID", "EventId", "event_id") or _first_str(
        system.get("EventID")
    )
    rid = _field(hit, "Record ID", "RecordId", "EventRecordID", "record_id") or _first_str(
        system.get("EventRecordID")
    )
    host = (
        _field(hit, "Computer", "computer", "Hostname")
        or _first_str(system.get("Computer"))
    ).lower()
    return (eid, rid, host)
