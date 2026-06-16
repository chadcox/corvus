"""Sync Chainsaw rules and mappings from GitHub."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from worker.config import settings


def count_rule_files(rules_root: Path) -> int:
    if not rules_root.is_dir():
        return 0
    return sum(1 for _ in rules_root.rglob("*.yml")) + sum(1 for _ in rules_root.rglob("*.yaml"))


def sync_chainsaw_rules_from_github(
    *,
    ref: str | None = None,
    dest_root: Path | None = None,
) -> dict[str, object]:
    branch = ref or settings.chainsaw_ref
    rules_dest = dest_root or Path(settings.chainsaw_rules_root)
    mappings_dest = Path(settings.chainsaw_mappings_root)

    script = Path("/usr/local/bin/fetch-chainsaw-rules.sh")
    if not script.is_file():
        script = Path(__file__).resolve().parents[4] / "scripts" / "fetch-chainsaw-rules.sh"

    bundle = Path("/tmp/chainsaw-fetch-bundle")
    env = {**os.environ, "CHAINSAW_REF": branch}
    subprocess.run(
        [str(script), str(bundle)],
        check=True,
        env=env,
        capture_output=True,
        text=True,
    )

    rules_src = bundle / "rules"
    maps_src = bundle / "mappings"
    if rules_src.is_dir():
        rules_dest.mkdir(parents=True, exist_ok=True)
        for sub in rules_src.iterdir():
            target = rules_dest / sub.name
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
            shutil.copytree(sub, target)
    if maps_src.is_dir():
        mappings_dest.mkdir(parents=True, exist_ok=True)
        for item in maps_src.iterdir():
            target = mappings_dest / item.name
            if item.is_dir():
                if target.exists():
                    shutil.rmtree(target, ignore_errors=True)
                shutil.copytree(item, target)
            else:
                shutil.copy2(item, target)

    count = count_rule_files(rules_dest)
    map_count = (
        sum(1 for _ in mappings_dest.glob("*.yml"))
        + sum(1 for _ in mappings_dest.glob("*.yaml"))
        if mappings_dest.is_dir()
        else 0
    )
    return {
        "ref": branch,
        "rule_count": count,
        "mapping_count": map_count,
    }
