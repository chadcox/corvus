import concurrent.futures
import os
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any
from uuid import UUID

from worker.kape.detector import detect_kape_layout
from worker.parsers.csv_events import PARTIAL_PARSE_NOTE_PREFIX, parse_csv_to_events
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
from worker.hindsight.profiles import find_browser_dirs_without_history, select_browser_profiles
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
) -> tuple[list[dict[str, Any]], list[str]]:
    """Run a single EZ Tool then parse its CSV output. Thread-safe.

    Returns (events, notes); parser notes (cap/partial-parse warnings) are kept
    so tool-generated CSVs surface the same warnings as pre-parsed ones.
    """
    csv_out = run_fn(input_path, output_dir)
    if csv_out:
        evts, note = parse_csv_to_events(csv_out, eid)
        return evts, [note] if note else []
    return [], []


def _parallel_tool_parse(
    run_fn: Callable[[Path, Path], Path | None],
    inputs: list[Path],
    output_dir: Path,
    eid: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Run run_fn across inputs in a bounded thread pool, concatenate results.

    Results are collected in input order — every task must finish before the
    pool exits either way, so ordering costs nothing and keeps events and notes
    deterministic for a given package.
    """
    if not inputs:
        return [], []
    out: list[dict[str, Any]] = []
    notes: list[str] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=_MAX_TOOL_WORKERS) as pool:
        futures = [
            pool.submit(_run_tool_and_parse, run_fn, p, output_dir, eid)
            for p in inputs
        ]
        for fut in futures:
            evts, tool_notes = fut.result()
            out.extend(evts)
            notes.extend(tool_notes)
    return out, notes


def _extend_from_tools(
    timeline: list[dict[str, Any]],
    ingest_notes: list[str],
    run_fn: Callable[[Path, Path], Path | None],
    inputs: list[Path],
    output_dir: Path,
    eid: str,
) -> None:
    """Run a tool over inputs and fold both events and parser notes into ingest."""
    events, notes = _parallel_tool_parse(run_fn, inputs, output_dir, eid)
    timeline.extend(events)
    ingest_notes.extend(notes)


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


def resolve_prefetch_max_files() -> int:
    """Configured raw Prefetch ceiling, clamped to a usable value.

    A zero or negative PREFETCH_MAX_FILES would skip Prefetch parsing entirely
    without ever saying so — the same silent omission this ceiling exists to
    report — so anything below one file is treated as one.
    """
    return max(1, settings.prefetch_max_files)


def _package_sort_key(path: Path, package_dir: Path) -> tuple[str, str]:
    """Package-relative ordering key, independent of filesystem traversal order.

    Paths outside the package (there should be none) fall back to their own
    string form, which still orders deterministically.
    """
    try:
        relative = str(path.relative_to(package_dir))
    except ValueError:
        relative = str(path)
    normalized = relative.replace("\\", "/")
    return (normalized.casefold(), normalized)


def select_prefetch_inputs(
    prefetch_files: Sequence[Path], package_dir: Path, limit: int
) -> tuple[list[Path], str | None]:
    """Pick which raw .pf files PECmd parses, and say so when some are left out.

    Selection is by package-relative path so the same package always yields the
    same subset — re-ingesting a package must not silently swap which files were
    covered. When the package holds more Prefetch files than the ceiling allows,
    the returned note carries counts only (never a collected path, which is
    attacker-controlled text) and uses the partial-parse prefix so the ingest is
    treated as incomplete end to end: the job is flagged in the UI and the
    package is kept on disk even when post-ingest deletion is enabled.
    """
    ordered = sorted(prefetch_files, key=lambda p: _package_sort_key(p, package_dir))
    if len(ordered) <= limit:
        return ordered, None
    omitted = len(ordered) - limit
    note = (
        f"{PARTIAL_PARSE_NOTE_PREFIX} {len(ordered)} raw prefetch file(s) found, "
        f"{limit} parsed, {omitted} omitted by the PREFETCH_MAX_FILES ceiling "
        f"({limit}). Raise PREFETCH_MAX_FILES and re-ingest to parse the rest."
    )
    return ordered[:limit], note


def _module_categories(csv_path: Path) -> set[str]:
    """Raw-artifact categories a module CSV filename claims to cover."""
    lower = csv_path.name.lower()
    return {category for hint, category in _MODULE_CSV_CATEGORY.items() if hint in lower}


def _preparsed_categories(
    csv_event_counts: Sequence[tuple[Path, int]],
) -> tuple[set[str], dict[str, int]]:
    """Split module-CSV categories into suppressed and empty-but-present.

    A category only suppresses raw re-parsing when at least one matching module
    CSV actually contributed timeline events. A header-only CSV — or one whose
    rows carry no parseable timestamp — yields nothing, so the raw artifacts are
    the only remaining source for that category and must still be parsed.

    Returns (suppressed_categories, empty_module_csv_counts). The second value
    counts, per still-unsuppressed category, how many matching module CSVs
    contributed no events, so the caller can explain the fallback.
    """
    suppressed: set[str] = set()
    empty: dict[str, int] = {}
    for csv_path, event_count in csv_event_counts:
        for category in _module_categories(csv_path):
            if event_count > 0:
                suppressed.add(category)
            else:
                empty[category] = empty.get(category, 0) + 1
    # A populated CSV anywhere in the package wins: mixed empty/populated
    # matches stay suppressed and need no note.
    return suppressed, {c: n for c, n in empty.items() if c not in suppressed}


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
    csv_event_counts: list[tuple[Path, int]] = []
    for csv_path in layout.csv_files:
        events, note = parse_csv_to_events(csv_path, eid)
        csv_event_counts.append((csv_path, len(events)))
        timeline.extend(events)
        if note:
            ingest_notes.append(note)

    progress(40, f"Parsed {len(layout.csv_files)} CSV files → {len(timeline)} events")

    if layout.raw_collection:
        filesystem = build_filesystem_nodes(layout.raw_collection, eid)

    progress(60, f"Indexed {len(filesystem)} filesystem nodes")

    # Skip raw re-parsing for any category the package already ships as a
    # pre-parsed EZ Tools module CSV that yielded events — otherwise events are
    # double-counted. A module CSV that contributed nothing suppresses nothing.
    preparsed, empty_modules = _preparsed_categories(csv_event_counts)
    for category in sorted(empty_modules):
        ingest_notes.append(
            f"{category}: {empty_modules[category]} pre-parsed module CSV(s) contributed no "
            f"timeline events (empty or no parseable timestamps) — raw {category} parsing "
            f"not suppressed"
        )

    parsed_dir = package_dir / "_ff_parsed"
    if "evtx" not in preparsed:
        progress(
            65,
            f"Running EvtxECmd on {len(layout.evtx_files)} EVTX file(s) "
            f"({_MAX_TOOL_WORKERS} workers)",
        )
        _extend_from_tools(
            timeline, ingest_notes, run_evtxecmd, layout.evtx_files, parsed_dir / "evtx", eid
        )

    if "mft" not in preparsed:
        progress(
            70,
            f"Running MFTECmd on {len(layout.mft_files)} MFT export(s) "
            f"({_MAX_TOOL_WORKERS} workers)",
        )
        _extend_from_tools(
            timeline, ingest_notes, run_mftecmd, layout.mft_files, parsed_dir / "mft", eid
        )

    if "registry" not in preparsed:
        progress(
            75,
            f"Running RECmd on {len(layout.registry_hives)} registry hive(s) "
            f"({_MAX_TOOL_WORKERS} workers)",
        )
        _extend_from_tools(
            timeline, ingest_notes, run_recmd, layout.registry_hives, parsed_dir / "registry", eid
        )

    if "prefetch" not in preparsed:
        prefetch_inputs, prefetch_note = select_prefetch_inputs(
            layout.prefetch_files, package_dir, resolve_prefetch_max_files()
        )
        if prefetch_note:
            ingest_notes.append(prefetch_note)
        progress(
            80,
            f"Running PECmd on {len(prefetch_inputs)} prefetch file(s) "
            f"({_MAX_TOOL_WORKERS} workers)",
        )
        _extend_from_tools(
            timeline, ingest_notes, run_pecmd, prefetch_inputs, parsed_dir / "prefetch", eid
        )

    if "amcache" not in preparsed:
        amcache_inputs = layout.amcache_files[:10]
        progress(
            85,
            f"Running AmcacheParser on {len(amcache_inputs)} amcache hive(s) "
            f"({_MAX_TOOL_WORKERS} workers)",
        )
        _extend_from_tools(
            timeline, ingest_notes, run_amcacheparser, amcache_inputs, parsed_dir / "amcache", eid
        )

    browser_events = 0
    if settings.hindsight_enabled and hindsight_available() and layout.browser_profile_dirs:
        browser_dirs, cap_note = select_browser_profiles(
            layout.browser_profile_dirs, settings.hindsight_max_profiles
        )
        # Recorded before the run so the omission survives regardless of what
        # the processed profiles yield.
        if cap_note:
            ingest_notes.append(cap_note)
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
