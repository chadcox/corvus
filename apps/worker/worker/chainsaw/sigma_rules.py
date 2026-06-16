"""Resolve Sigma rule directory for Chainsaw hunt (full vs DFIR tier)."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import yaml

from worker.config import settings
from worker.sigma.dfir_filter import is_dfir_relevant


def resolve_sigma_rules_root(profile: str | None = None) -> Path | None:
    """
    Return Sigma rules root for ``chainsaw hunt -s``, or None to skip Sigma.

    profile: ``dfir`` (default), ``full``, or ``off``.
    """
    profile = (profile or settings.chainsaw_sigma_profile or "dfir").lower()
    if profile == "off" or not settings.chainsaw_include_sigma:
        return None

    source = Path(settings.sigma_rules_root)
    if not source.is_dir():
        return None

    if profile == "full":
        return source

    cache = Path(settings.chainsaw_sigma_dfir_cache)
    if _cache_fresh(source, cache):
        return cache

    _build_dfir_cache(source, cache)
    return cache if cache.is_dir() else source


def _cache_fresh(source: Path, cache: Path) -> bool:
    marker = cache / ".ff-dfir-cache"
    if not marker.is_file():
        return False
    try:
        expected = int(marker.read_text(encoding="utf-8").strip())
    except ValueError:
        return False
    actual = sum(1 for _ in source.rglob("*.yml"))
    return expected == actual and any(cache.rglob("*.yml"))


def _build_dfir_cache(source: Path, cache: Path) -> int:
    """Hardlink DFIR-filtered Sigma rules into cache (preserves relative paths)."""
    if cache.exists():
        shutil.rmtree(cache)
    cache.mkdir(parents=True, exist_ok=True)

    count = 0
    for path in sorted(source.rglob("*.yml")):
        rel = path.relative_to(source)
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, yaml.YAMLError):
            continue
        if not isinstance(raw, dict):
            continue
        level = str(raw.get("level") or "medium").lower()
        status = str(raw.get("status") or "experimental").lower()
        if not is_dfir_relevant(
            rel_path=str(rel).replace("\\", "/"),
            level=level,
            status=status,
        ):
            continue
        dest = cache / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(path, dest)
        except OSError:
            shutil.copy2(path, dest)
        count += 1

    (cache / ".ff-dfir-cache").write_text(str(sum(1 for _ in source.rglob("*.yml"))), encoding="utf-8")
    return count
