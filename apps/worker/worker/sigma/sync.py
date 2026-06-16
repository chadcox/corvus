"""Download and install Sigma rules from SigmaHQ on GitHub."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from worker.config import settings
from worker.sigma.sync_meta import write_status

FETCH_SCRIPT = Path("/usr/local/bin/fetch-sigma-rules.sh")


def count_rule_files(rules_root: Path) -> int:
    if not rules_root.is_dir():
        return 0
    return sum(1 for _ in rules_root.rglob("*.yml")) + sum(1 for _ in rules_root.rglob("*.yaml"))


def sync_sigma_rules_from_github(
    *,
    ref: str | None = None,
    rules_root: Path | None = None,
    task_id: str | None = None,
) -> dict[str, object]:
    """Fetch the curated Sigma subset into rules_root (replaces existing files)."""
    root = rules_root or Path(settings.sigma_rules_root)
    branch = ref or settings.sigma_ref
    staging = root.with_name(f"{root.name}.staging")

    write_status(
        state="running",
        ref=branch,
        message=f"Downloading Sigma rules ({branch}) from GitHub…",
        task_id=task_id,
    )

    if staging.exists():
        shutil.rmtree(staging)

    script = FETCH_SCRIPT
    if not script.is_file():
        repo_script = Path(__file__).resolve().parents[4] / "scripts" / "fetch-sigma-rules.sh"
        script = repo_script
    if not script.is_file():
        raise FileNotFoundError(f"Sigma fetch script not found: {script}")

    env = os.environ.copy()
    env["SIGMA_REF"] = branch
    proc = subprocess.run(
        ["bash", str(script), str(staging)],
        capture_output=True,
        text=True,
        timeout=600,
        env=env,
        check=False,
    )
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip()[-2000:]
        raise RuntimeError(f"Sigma fetch failed (exit {proc.returncode}): {tail}")

    count = count_rule_files(staging)
    if count == 0:
        shutil.rmtree(staging, ignore_errors=True)
        raise RuntimeError("Sigma fetch produced zero rule files")

    root.mkdir(parents=True, exist_ok=True)
    for child in root.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
    for item in staging.iterdir():
        dest = root / item.name
        if item.is_dir():
            shutil.copytree(item, dest)
        else:
            shutil.copy2(item, dest)
    shutil.rmtree(staging, ignore_errors=True)

    return {"rule_count": count, "ref": branch, "rules_root": str(root)}
