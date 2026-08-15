"""Run Chainsaw hunt against EVTX artefacts in a KAPE package."""

from __future__ import annotations

import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from worker.chainsaw.evtx_select import find_evtx_files, find_evtx_files_with_count
from worker.chainsaw.sigma_rules import resolve_sigma_rules_root
from worker.config import settings

_SLUG_RE = re.compile(r"[^a-z0-9]+")
_UNSET = object()
PARTIAL_DETECTION_COVERAGE_PREFIX = "Partial detection coverage:"


@dataclass
class ChainsawHuntRun:
    """Hits and count-only coverage from a set of Chainsaw batches."""

    hits: list[dict[str, Any]]
    hunted_files: int
    failed_files: int
    failed_batches: int


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


def _run_chainsaw_hunt_batch(
    evtx_paths: list[Path],
    *,
    sigma_root: Path | None | object = _UNSET,
) -> tuple[list[dict[str, Any]], bool]:
    """Execute one batch and report whether every selected file was hunted."""
    if not evtx_paths:
        return [], True
    if not chainsaw_available():
        return [], False

    rules_evtx = Path(settings.chainsaw_rules_root) / "evtx"
    if not rules_evtx.is_dir():
        rules_evtx = Path(settings.chainsaw_rules_root)
    if not rules_evtx.is_dir():
        return [], False

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
        return [], False

    # Retain any parseable matches Chainsaw emitted before a non-zero exit, as
    # the legacy runner did, while still marking the whole batch as incomplete.
    return _parse_hunt_stdout(proc.stdout or ""), proc.returncode == 0


def run_chainsaw_hunt(
    evtx_paths: list[Path],
    *,
    sigma_root: Path | None | object = _UNSET,
) -> list[dict[str, Any]]:
    """Execute ``chainsaw hunt`` on one EVTX batch and return parsed JSON hits."""
    hits, _ = _run_chainsaw_hunt_batch(evtx_paths, sigma_root=sigma_root)
    return hits


def _evtx_batches(paths: list[Path]) -> list[list[Path]]:
    size = max(1, settings.chainsaw_evtx_batch_size)
    return [paths[i : i + size] for i in range(0, len(paths), size)]


def run_chainsaw_hunt_parallel(
    evtx_paths: list[Path],
    *,
    sigma_root: Path | None | object = _UNSET,
) -> list[dict[str, Any]]:
    """Run Chainsaw hunt in parallel over EVTX batches; merge hits."""
    return run_chainsaw_hunt_parallel_with_coverage(
        evtx_paths,
        sigma_root=sigma_root,
    ).hits


def run_chainsaw_hunt_parallel_with_coverage(
    evtx_paths: list[Path],
    *,
    sigma_root: Path | None | object = _UNSET,
) -> ChainsawHuntRun:
    """Run batches in parallel and retain count-only success/failure coverage."""
    if not evtx_paths:
        return ChainsawHuntRun([], 0, 0, 0)
    if sigma_root is _UNSET:
        sigma_root = resolve_sigma_rules_root()

    batches = _evtx_batches(evtx_paths)
    if len(batches) == 1:
        hits, succeeded = _run_chainsaw_hunt_batch(batches[0], sigma_root=sigma_root)
        return ChainsawHuntRun(
            hits=hits,
            hunted_files=len(batches[0]) if succeeded else 0,
            failed_files=0 if succeeded else len(batches[0]),
            failed_batches=0 if succeeded else 1,
        )

    workers = min(max(1, settings.chainsaw_evtx_parallel), len(batches))
    hits: list[dict[str, Any]] = []
    hunted_files = 0
    failed_files = 0
    failed_batches = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_run_chainsaw_hunt_batch, batch, sigma_root=sigma_root): batch
            for batch in batches
        }
        for future in as_completed(futures):
            batch = futures[future]
            try:
                batch_hits, succeeded = future.result()
            except Exception:
                batch_hits, succeeded = [], False
            hits.extend(batch_hits)
            if succeeded:
                hunted_files += len(batch)
            else:
                failed_files += len(batch)
                failed_batches += 1
    return ChainsawHuntRun(hits, hunted_files, failed_files, failed_batches)


def collect_evtx_for_hunt(package_dir: Path) -> list[Path]:
    """Package EVTX list using configured priority / limits."""
    return find_evtx_files(
        package_dir,
        max_files=max(1, settings.chainsaw_evtx_max),
        mode=settings.chainsaw_evtx_mode,
    )


def collect_evtx_for_hunt_with_count(package_dir: Path) -> tuple[list[Path], int, int]:
    """Return selected files, total found, and the effective configured ceiling."""
    effective_max = max(1, settings.chainsaw_evtx_max)
    selected, found_count = find_evtx_files_with_count(
        package_dir,
        max_files=effective_max,
        mode=settings.chainsaw_evtx_mode,
    )
    return selected, found_count, effective_max


def detection_coverage_note(
    *,
    found_files: int,
    selected_files: int,
    effective_max: int,
    run: ChainsawHuntRun,
) -> str | None:
    """Describe EVTX not hunted using counts only, never collected path data."""
    omitted_files = max(0, found_files - selected_files)
    failed_files = max(0, run.failed_files)
    not_hunted = omitted_files + failed_files
    if not_hunted == 0:
        return None

    reasons: list[str] = []
    if omitted_files:
        reasons.append(
            f"{omitted_files} omitted by the effective CHAINSAW_EVTX_MAX ceiling of "
            f"{effective_max}"
        )
    if failed_files:
        reasons.append(
            f"{failed_files} in {run.failed_batches} failed or timed-out Chainsaw batch(es)"
        )
    reason = " and ".join(reasons)
    remedy = (
        "Re-ingest with a higher CHAINSAW_EVTX_MAX to hunt the omitted files."
        if omitted_files and not failed_files
        else "Re-ingest after raising CHAINSAW_EVTX_MAX and resolving batch failures."
        if omitted_files
        else "Re-ingest to retry Chainsaw detection on the files not hunted."
    )
    return (
        f"{PARTIAL_DETECTION_COVERAGE_PREFIX} {found_files} EVTX file(s) found, "
        f"{run.hunted_files} hunted, {not_hunted} not hunted ({reason}). {remedy}"
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
