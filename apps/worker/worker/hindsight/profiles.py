"""Locate Chromium profile directories in evidence packages for Hindsight."""

from __future__ import annotations

from pathlib import Path

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
