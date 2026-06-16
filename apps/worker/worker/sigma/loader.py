"""Load Sigma YAML rules from disk."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from worker.config import settings
from worker.sigma.dfir_filter import is_dfir_relevant

SUPPORTED_PRODUCTS = frozenset({"windows", "windows"})
_RULES_CACHE: dict[tuple[str, str], tuple[tuple[int, int], list["SigmaRule"]]] = {}


@dataclass
class SigmaRule:
    path: Path
    title: str
    rule_id: str
    level: str
    description: str
    tags: list[str]
    logsource: dict[str, Any]
    detection: dict[str, Any]
    status: str = "experimental"

    @property
    def is_windows(self) -> bool:
        product = str(self.logsource.get("product") or "").lower()
        return product in ("windows", "")


def _parse_rule(path: Path, raw: dict[str, Any]) -> SigmaRule | None:
    detection = raw.get("detection")
    if not isinstance(detection, dict) or not detection:
        return None
    title = raw.get("title")
    if not title:
        return None
    rule_id = str(raw.get("id") or path.stem)
    logsource = raw.get("logsource") if isinstance(raw.get("logsource"), dict) else {}
    return SigmaRule(
        path=path,
        title=str(title),
        rule_id=rule_id,
        level=str(raw.get("level") or "medium").lower(),
        description=str(raw.get("description") or ""),
        tags=[str(t) for t in (raw.get("tags") or []) if t],
        logsource=logsource,
        detection=detection,
        status=str(raw.get("status") or "experimental").lower(),
    )


def load_sigma_rules(rules_root: Path, *, profile: str | None = None) -> list[SigmaRule]:
    """Load parseable Windows-oriented Sigma rules from rules_root."""
    if not rules_root.is_dir():
        return []

    profile = (profile or getattr(settings, "sigma_profile", "dfir") or "dfir").lower()

    rules: list[SigmaRule] = []
    for path in sorted(rules_root.rglob("*.yml")) + sorted(rules_root.rglob("*.yaml")):
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, yaml.YAMLError):
            continue
        if not isinstance(raw, dict):
            continue
        rule = _parse_rule(path, raw)
        if not rule or not rule.is_windows:
            continue
        if profile == "dfir" and not is_dfir_relevant(
            rel_path=_relative_path(rule.path, rules_root),
            level=rule.level,
            status=rule.status,
        ):
            continue
        rules.append(rule)
    return rules


def load_sigma_rules_cached(rules_root: Path, *, profile: str | None = None) -> list[SigmaRule]:
    """Load Sigma rules with per-process cache invalidated by rule file mtimes."""
    if not rules_root.is_dir():
        return []

    profile = (profile or getattr(settings, "sigma_profile", "dfir") or "dfir").lower()
    key = (str(rules_root.resolve()), profile)
    signature = _rules_signature(rules_root)
    cached = _RULES_CACHE.get(key)
    if cached and cached[0] == signature:
        return cached[1]

    rules = load_sigma_rules(rules_root, profile=profile)
    _RULES_CACHE[key] = (signature, rules)
    return rules


def clear_sigma_rules_cache() -> None:
    _RULES_CACHE.clear()


def _rules_signature(rules_root: Path) -> tuple[int, int]:
    newest = 0
    count = 0
    for pattern in ("*.yml", "*.yaml"):
        for path in rules_root.rglob(pattern):
            try:
                stat = path.stat()
            except OSError:
                continue
            count += 1
            newest = max(newest, stat.st_mtime_ns)
    return newest, count


def _relative_path(path: Path, rules_root: Path) -> str:
    try:
        return str(path.relative_to(rules_root)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")
