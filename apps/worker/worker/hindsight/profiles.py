"""Locate Chromium profile directories in evidence packages for Hindsight."""

from __future__ import annotations

from pathlib import Path

from worker.parsers.csv_events import PARTIAL_PARSE_NOTE_PREFIX

# Files that mark a directory as a Chromium profile. History alone is not
# enough — a profile whose history was cleared may still hold cookies, saved
# logins, or web data, and skipping it would lose forensically relevant data.
_PROFILE_MARKER_FILES = ("History", "Cookies", "Web Data", "Login Data")

# Directory names that indicate a Chromium browser data root was collected.
_BROWSER_ROOT_DIR_NAMES = ("User Data", "Opera Stable")


def find_browser_profiles(package_dir: Path) -> list[Path]:
    """Return unique Chromium profile directories to hand to Hindsight.

    Each returned path is a single profile directory (e.g. ``Default`` or
    ``Profile 1``) so Hindsight can be run per profile, keeping per-profile
    attribution on the resulting events.
    """
    found: dict[str, Path] = {}

    for marker in _PROFILE_MARKER_FILES:
        for hit in package_dir.rglob(marker):
            if not hit.is_file():
                continue
            profile_dir = hit.parent
            # Modern Chrome stores cookies under <profile>/Network/Cookies.
            if marker == "Cookies" and profile_dir.name == "Network":
                profile_dir = profile_dir.parent
            found[str(profile_dir.resolve())] = profile_dir

    return sorted(found.values(), key=lambda p: str(p).lower())


def select_browser_profiles(
    profiles: list[Path], limit: int
) -> tuple[list[Path], str | None]:
    """Apply the per-package Chromium profile ceiling to ``profiles``.

    Hindsight is run once per profile, so an unbounded package could pin the
    worker for hours; the cap keeps ingest bounded. Returns the profiles to
    process plus, when profiles were left out, a partial-parse note so the
    omission is visible in the job message and the package is retained for a
    re-ingest with a higher limit instead of being deleted.

    Selection is the lowest-sorted profiles, matching the deterministic order
    ``find_browser_profiles`` returns, so the same package always yields the
    same subset. A non-positive limit is clamped to one profile rather than
    silently disabling browser parsing (``HINDSIGHT_ENABLED=false`` does that).
    The note carries counts only, never collected paths or profile names, since
    those come from the evidence under investigation, and no semicolon, which
    the UI treats as a message separator.
    """
    ordered = sorted(profiles, key=lambda p: str(p).lower())
    effective = max(1, limit)
    if len(ordered) <= effective:
        return ordered, None

    omitted = len(ordered) - effective
    note = (
        f"{PARTIAL_PARSE_NOTE_PREFIX} {len(ordered)} Chromium browser profile(s) found, "
        f"{effective} processed, {omitted} not parsed. The per-package cap "
        f"HINDSIGHT_MAX_PROFILES limited this ingest to {effective} profile(s). "
        f"Raise it and re-ingest the retained package to parse the rest."
    )
    return ordered[:effective], note


def find_browser_dirs_without_history(package_dir: Path) -> list[Path]:
    """Chromium browser data roots that were collected without parseable
    history databases (e.g. only ``Cache`` was captured).

    Returns ``User Data`` (or Opera) directories that exist but contain no
    profile with a History/Cookies/Web Data/Login Data file beneath them, so
    the ingest can warn that browser history was not collected.
    """
    profiles = find_browser_profiles(package_dir)
    resolved_profiles = [p.resolve() for p in profiles]

    empty: dict[str, Path] = {}
    for name in _BROWSER_ROOT_DIR_NAMES:
        for root in package_dir.rglob(name):
            if not root.is_dir():
                continue
            root_res = root.resolve()
            if any(prof.is_relative_to(root_res) for prof in resolved_profiles):
                continue
            empty[str(root_res)] = root

    return sorted(empty.values(), key=lambda p: str(p).lower())
