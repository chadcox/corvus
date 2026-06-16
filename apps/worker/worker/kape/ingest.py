import concurrent.futures
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import UUID

from worker.kape.detector import detect_kape_layout
from worker.parsers.csv_events import parse_csv_to_events
from worker.parsers.entities import extract_entities_from_events
from worker.parsers.filesystem import build_filesystem_nodes
from worker.parsers.filesystem_paths import build_filesystem_from_paths
from worker.config import settings
from worker.eztools.runner import (
    run_amcacheparser,
    run_evtxecmd,
    run_mftecmd,
    run_pecmd,
    run_recmd,
)
from worker.hindsight.parser import parse_hindsight_jsonl
from worker.hindsight.profiles import find_browser_dirs_without_history
from worker.hindsight.runner import hindsight_available, output_stem, run_hindsight


# Bound parallelism per category so dotnet subprocesses don't saturate the host.
# Each tool invocation calls out to subprocess.run, so threads release the GIL
# while waiting; this is I/O-bound from Python's perspective despite being
# CPU-bound in the child process.
_MAX_TOOL_WORKERS = max(1, min(4, (os.cpu_count() or 4) // 2))


def _run_tool_and_parse(
    run_fn: Callable[[Path, Path], Path | None],
    input_path: Path,
    output_dir: Path,
    eid: str,
) -> list[dict[str, Any]]:
    """Run a single EZ Tool then parse its CSV output. Thread-safe."""
    csv_out = run_fn(input_path, output_dir)
    if csv_out:
        evts, _ = parse_csv_to_events(csv_out, eid)
        return evts
    return []


def _parallel_tool_parse(
    run_fn: Callable[[Path, Path], Path | None],
    inputs: list[Path],
    output_dir: Path,
    eid: str,
) -> list[dict[str, Any]]:
    """Run run_fn across inputs in a bounded thread pool, concatenate events."""
    if not inputs:
        return []
    out: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=_MAX_TOOL_WORKERS) as pool:
        futures = [
            pool.submit(_run_tool_and_parse, run_fn, p, output_dir, eid)
            for p in inputs
        ]
        for fut in concurrent.futures.as_completed(futures):
            out.extend(fut.result())
    return out


# Module CSV filename hint → the raw-artifact category it already covers.
# When a package ships a pre-parsed EZ Tools CSV, re-running the same tool on
# raw artifacts of that category would double-count every event.
_MODULE_CSV_CATEGORY: dict[str, str] = {
    "evtxecmd": "evtx",
    "mftecmd": "mft",
    "pecmd": "prefetch",
    "recmd": "registry",
    "amcache": "amcache",
}


def _browser_profile_label(profile_dir: Path, package_dir: Path) -> str:
    """Human-readable profile identifier relative to the package root.

    Avoids leaking container-internal absolute paths into the UI while keeping
    the user/browser context (e.g. ``C/Users/alice/.../Chrome/User Data/Default``).
    """
    try:
        return str(profile_dir.relative_to(package_dir)).replace("\\", "/")
    except ValueError:
        return profile_dir.name


def _preparsed_categories(csv_files: list[Path]) -> set[str]:
    """Categories already represented by pre-parsed EZ Tools module CSVs."""
    found: set[str] = set()
    for csv_path in csv_files:
        lower = csv_path.name.lower()
        for hint, category in _MODULE_CSV_CATEGORY.items():
            if hint in lower:
                found.add(category)
    return found


def ingest_package(
    package_dir: Path,
    evidence_source_id: UUID,
    on_progress: Callable[[int, str], None] | None = None,
) -> dict[str, Any]:
    """Scan evidence package and return counts of ingested records."""
    layout = detect_kape_layout(package_dir)
    eid = str(evidence_source_id)
    timeline: list[dict[str, Any]] = []
    filesystem: list[dict[str, Any]] = []

    def progress(pct: int, msg: str) -> None:
        if on_progress:
            on_progress(pct, msg)

    progress(10, "Scanning evidence package")

    ingest_notes: list[str] = []
    for csv_path in layout.csv_files:
        events, note = parse_csv_to_events(csv_path, eid)
        timeline.extend(events)
        if note:
            ingest_notes.append(note)

    progress(40, f"Parsed {len(layout.csv_files)} CSV files → {len(timeline)} events")

    if layout.raw_collection:
        filesystem = build_filesystem_nodes(layout.raw_collection, eid)

    progress(60, f"Indexed {len(filesystem)} filesystem nodes")

    # Skip raw re-parsing for any category the package already ships as a
    # pre-parsed EZ Tools module CSV — otherwise events are double-counted.
    preparsed = _preparsed_categories(layout.csv_files)

    parsed_dir = package_dir / "_ff_parsed"
    if "evtx" not in preparsed:
        progress(
            65,
            f"Running EvtxECmd on {len(layout.evtx_files)} EVTX file(s) "
            f"({_MAX_TOOL_WORKERS} workers)",
        )
        timeline.extend(
            _parallel_tool_parse(run_evtxecmd, layout.evtx_files, parsed_dir / "evtx", eid)
        )

    if "mft" not in preparsed:
        progress(
            70,
            f"Running MFTECmd on {len(layout.mft_files)} MFT export(s) "
            f"({_MAX_TOOL_WORKERS} workers)",
        )
        timeline.extend(
            _parallel_tool_parse(run_mftecmd, layout.mft_files, parsed_dir / "mft", eid)
        )

    if "registry" not in preparsed:
        progress(
            75,
            f"Running RECmd on {len(layout.registry_hives)} registry hive(s) "
            f"({_MAX_TOOL_WORKERS} workers)",
        )
        timeline.extend(
            _parallel_tool_parse(run_recmd, layout.registry_hives, parsed_dir / "registry", eid)
        )

    if "prefetch" not in preparsed:
        prefetch_inputs = layout.prefetch_files[:100]
        progress(
            80,
            f"Running PECmd on {len(prefetch_inputs)} prefetch file(s) "
            f"({_MAX_TOOL_WORKERS} workers)",
        )
        timeline.extend(
            _parallel_tool_parse(run_pecmd, prefetch_inputs, parsed_dir / "prefetch", eid)
        )

    if "amcache" not in preparsed:
        amcache_inputs = layout.amcache_files[:10]
        progress(
            85,
            f"Running AmcacheParser on {len(amcache_inputs)} amcache hive(s) "
            f"({_MAX_TOOL_WORKERS} workers)",
        )
        timeline.extend(
            _parallel_tool_parse(
                run_amcacheparser, amcache_inputs, parsed_dir / "amcache", eid
            )
        )

    browser_events = 0
    if settings.hindsight_enabled and hindsight_available() and layout.browser_profile_dirs:
        browser_dirs = layout.browser_profile_dirs[: settings.hindsight_max_profiles]
        progress(86, f"Running Hindsight on {len(browser_dirs)} Chromium profile(s)")
        browser_errors: list[str] = []
        for profile_dir in browser_dirs:
            label = _browser_profile_label(profile_dir, package_dir)
            result = run_hindsight(
                profile_dir,
                parsed_dir / "browser",
                out_stem=output_stem(profile_dir, label),
            )
            if result.jsonl is None:
                if result.error:
                    browser_errors.append(result.error)
                continue
            evts = parse_hindsight_jsonl(result.jsonl, eid, profile_hint=label)
            browser_events += len(evts)
            timeline.extend(evts)
        if browser_events:
            ingest_notes.append(f"Browser: {browser_events} events from {len(browser_dirs)} profile(s)")
        elif browser_errors:
            ingest_notes.append(f"Browser: no events ({browser_errors[0]})")

    # No browser history ingested but Chromium data was collected without its
    # history databases (e.g. only Cache) — warn instead of failing silently.
    if settings.hindsight_enabled and not browser_events:
        empty_dirs = find_browser_dirs_without_history(package_dir)
        if empty_dirs:
            ingest_notes.append(
                f"Chromium browser data found in {len(empty_dirs)} location(s) but no history "
                f"databases were collected (only cache/other) — re-collect with a browser-history target"
            )

    progress(88, "Extracting entities from timeline events")
    entities = extract_entities_from_events(timeline, eid)

    csv_paths = build_filesystem_from_paths(timeline, eid)
    if csv_paths:
        existing = {n["full_path"] for n in filesystem}
        for node in csv_paths:
            if node["full_path"] not in existing:
                filesystem.append(node)
                existing.add(node["full_path"])

    progress(90, f"Total timeline events: {len(timeline)}, entities: {len(entities)}")

    return {
        "timeline_events": timeline,
        "filesystem_nodes": filesystem,
        "entities": entities,
        "relations": [],
        "ingest_notes": ingest_notes,
    }
