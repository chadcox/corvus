"""Run Hindsight CLI against Chromium profile directories."""

from __future__ import annotations

import hashlib
import logging
import re
import shutil
import subprocess
from pathlib import Path
from typing import NamedTuple

from worker.config import settings

log = logging.getLogger(__name__)


class HindsightRun(NamedTuple):
    """Outcome of a single Hindsight invocation."""

    jsonl: Path | None
    error: str | None


def hindsight_available() -> bool:
    for candidate in (
        settings.hindsight_bin,
        "/usr/local/bin/hindsight",
        "/usr/local/bin/hindsight.py",
    ):
        if Path(candidate).is_file():
            return True
    return shutil.which("hindsight.py") is not None


def _resolve_hindsight_bin() -> str:
    for candidate in (
        settings.hindsight_bin,
        "/usr/local/bin/hindsight",
        "/usr/local/bin/hindsight.py",
    ):
        if Path(candidate).is_file():
            return candidate
    found = shutil.which("hindsight.py") or shutil.which("hindsight")
    if found:
        return found
    return settings.hindsight_bin


def output_stem(profile_dir: Path, label: str | None = None) -> str:
    """Stable, collision-free output filename for a profile.

    Two browsers can both have a ``Default`` profile, so the absolute path is
    hashed in to keep their JSONL outputs from overwriting each other.
    """
    base = label or profile_dir.name or "browser"
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("_")[:60] or "browser"
    digest = hashlib.sha1(str(profile_dir.resolve()).encode("utf-8")).hexdigest()[:8]
    return f"{safe}_{digest}"


def run_hindsight(
    profile_dir: Path,
    output_dir: Path,
    out_stem: str | None = None,
) -> HindsightRun:
    """Run ``hindsight.py`` with JSONL output for a single profile directory.

    Returns a :class:`HindsightRun`; on failure ``jsonl`` is ``None`` and
    ``error`` carries a short reason for surfacing to the operator.
    """
    if not hindsight_available():
        return HindsightRun(None, "Hindsight binary not available")
    if not profile_dir.is_dir():
        return HindsightRun(None, f"Profile path missing: {profile_dir.name}")

    output_dir.mkdir(parents=True, exist_ok=True)
    stem = out_stem or output_stem(profile_dir)
    out_base = output_dir / stem

    cmd = [
        _resolve_hindsight_bin(),
        "-i",
        str(profile_dir),
        "-o",
        str(out_base),
        "-f",
        "jsonl",
        "--nocopy",
    ]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=settings.hindsight_timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        log.warning("Hindsight timed out on %s", profile_dir)
        return HindsightRun(None, f"Hindsight timed out on {profile_dir.name}")
    except OSError as exc:
        log.warning("Hindsight failed to launch on %s: %s", profile_dir, exc)
        return HindsightRun(None, f"Hindsight failed to launch: {exc}")

    jsonl_path = Path(f"{out_base}.jsonl")
    # Hindsight may still write partial output on non-fatal plugin errors.
    if jsonl_path.is_file():
        return HindsightRun(jsonl_path, None)

    stderr_tail = (proc.stderr or "").strip().splitlines()
    reason = stderr_tail[-1] if stderr_tail else f"exit code {proc.returncode}"
    log.warning("Hindsight produced no output for %s: %s", profile_dir, reason)
    return HindsightRun(None, f"Hindsight produced no output for {profile_dir.name}: {reason}")
