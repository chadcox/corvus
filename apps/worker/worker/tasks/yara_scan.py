"""Celery task: scan evidence files with YARA and store findings as detections."""

from __future__ import annotations

import concurrent.futures
import json
import os
import re
from collections import defaultdict
from pathlib import Path
from uuid import UUID

import yara
from sqlalchemy import text

from worker.celery_app import celery_app
from worker.config import settings
from worker.db import get_session

_MAX_WORKERS = max(1, min(8, (os.cpu_count() or 4)))
_YARA_EXTERNALS_DEFAULTS = {
    "filepath": "",
    "filename": "",
    "extension": "",
    "filetype": "",
}
_YARA_UNDEFINED_EXTERNAL_RE = re.compile(r'undefined identifier "([^"]+)"')

_SIGMA_INSERT = text(
    """
    INSERT INTO sigma_detections
    (id, evidence_source_id, engine, rule_id, title, level, description, rule_definition, tags, match_count, sample_event_ids)
    VALUES
    (gen_random_uuid(), :evidence_source_id, 'yara', :rule_id, :title, :level, :description, :rule_definition,
     CAST(:tags AS jsonb), :match_count, CAST(:sample_event_ids AS jsonb))
    ON CONFLICT (evidence_source_id, engine, rule_id) DO UPDATE SET
        title = EXCLUDED.title,
        level = EXCLUDED.level,
        description = EXCLUDED.description,
        rule_definition = EXCLUDED.rule_definition,
        tags = EXCLUDED.tags,
        match_count = EXCLUDED.match_count,
        sample_event_ids = EXCLUDED.sample_event_ids
"""
)


def _iter_files(root: Path):
    for dirpath, _dirnames, filenames in os.walk(root):
        base = Path(dirpath)
        for filename in filenames:
            yield base / filename


def _extract_rule_blocks(content: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for match in re.finditer(r"\brule\s+([A-Za-z0-9_]+)[^{]*\{", content):
        name = match.group(1)
        start = match.start()
        brace_start = content.find("{", match.end() - 1)
        if brace_start < 0:
            continue
        depth = 0
        end = -1
        for idx in range(brace_start, len(content)):
            ch = content[idx]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = idx + 1
                    break
        if end > start:
            out[name] = content[start:end].strip()
    return out


def _build_rule_definition_index(rule_files: dict[str, str]) -> dict[str, str]:
    defs: dict[str, str] = {}
    for path_str in rule_files.values():
        try:
            content = Path(path_str).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        defs.update(_extract_rule_blocks(content))
    return defs


def _compile_rules() -> tuple[yara.Rules, dict[str, str]]:
    rules_root = Path(settings.yara_rules_root)
    if not rules_root.is_dir():
        raise RuntimeError(f"YARA rules root not found: {rules_root}")
    rule_files: dict[str, str] = {}
    for path in rules_root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in (".yar", ".yara"):
            continue
        pstr = str(path).lower()
        if "/deprecated/" in pstr or "/deprecated-rules/" in pstr:
            continue
        rule_files[str(len(rule_files))] = str(path)
    if not rule_files:
        raise RuntimeError(f"No YARA rules found in {rules_root}")
    rule_definitions = _build_rule_definition_index(rule_files)
    externals = dict(_YARA_EXTERNALS_DEFAULTS)
    for _ in range(64):
        try:
            return yara.compile(filepaths=rule_files, externals=externals), rule_definitions
        except yara.SyntaxError as exc:
            msg = str(exc)
            match = _YARA_UNDEFINED_EXTERNAL_RE.search(msg)
            if not match:
                raise
            identifier = match.group(1).strip()
            if not identifier or identifier in externals:
                raise
            externals[identifier] = ""
    raise RuntimeError("YARA compile failed after resolving external identifiers")


def _match_externals(path: Path) -> dict[str, str]:
    return {
        "filepath": str(path),
        "filename": path.name,
        "extension": path.suffix.lstrip(".").lower(),
        "filetype": "",
    }


@celery_app.task(name="worker.tasks.yara_scan.scan_evidence_with_yara", bind=True)
def scan_evidence_with_yara(self, source_id: str) -> dict:
    session = get_session()
    sid = UUID(source_id)
    try:
        row = session.execute(
            text("SELECT package_path FROM evidence_sources WHERE id = :id"),
            {"id": str(sid)},
        ).fetchone()
        if not row:
            return {"error": "source not found"}
        package_dir = Path(row[0])
        if not package_dir.is_dir():
            package_dir = Path(settings.evidence_root) / package_dir
        if not package_dir.is_dir():
            return {"error": "package directory not found"}

        rules, rule_definitions = _compile_rules()
        max_file_bytes = max(1, int(settings.yara_scan_max_file_bytes))
        max_matches = max(1, int(settings.yara_scan_max_matches))
        findings: dict[str, dict] = defaultdict(
            lambda: {"count": 0, "title": "", "level": "medium", "tags": [], "files": []}
        )

        def _scan_file(path: Path):
            try:
                if not path.is_file():
                    return []
                if path.stat().st_size > max_file_bytes:
                    return []
                return rules.match(str(path), timeout=30, externals=_match_externals(path))
            except Exception:
                return []

        files_scanned = 0
        total_matches = 0
        futures: dict[concurrent.futures.Future, Path] = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
            for path in _iter_files(package_dir):
                futures[pool.submit(_scan_file, path)] = path
            for future in concurrent.futures.as_completed(futures):
                path = futures[future]
                matches = future.result()
                files_scanned += 1
                if files_scanned % 200 == 0:
                    self.update_state(state="PROGRESS", meta={"scanned_files": files_scanned})
                for match in matches:
                    key = str(match.rule)
                    meta = match.meta or {}
                    hit = findings[key]
                    hit["count"] += 1
                    total_matches += 1
                    if not hit["title"]:
                        hit["title"] = str(meta.get("description") or match.rule)
                    if hit["level"] == "medium":
                        lvl = str(meta.get("level") or meta.get("severity") or "").strip().lower()
                        if lvl in {"critical", "high", "medium", "low", "informational"}:
                            hit["level"] = lvl
                    if not hit["tags"] and match.tags:
                        hit["tags"] = [str(t) for t in match.tags[:10]]
                    rel = str(path.relative_to(package_dir)).replace("\\", "/")
                    if rel not in hit["files"] and len(hit["files"]) < 20:
                        hit["files"].append(rel)
                    if total_matches >= max_matches:
                        break
                if total_matches >= max_matches:
                    break

        session.execute(
            text(
                "DELETE FROM sigma_detections WHERE evidence_source_id = :sid AND engine = 'yara'"
            ),
            {"sid": str(sid)},
        )
        rows = []
        for rule_id, hit in findings.items():
            sample_files = hit["files"][:5]
            desc = (
                f"Matched in {hit['count']} file(s). Sample paths: " + ", ".join(sample_files)
                if sample_files
                else f"Matched in {hit['count']} file(s)."
            )
            rows.append(
                {
                    "evidence_source_id": str(sid),
                    "rule_id": rule_id[:128],
                    "title": str(hit["title"] or rule_id)[:512],
                    "level": str(hit["level"])[:32],
                    "description": desc[:4000],
                    "rule_definition": rule_definitions.get(rule_id, "")[:16000] or None,
                    "tags": json.dumps(hit["tags"]),
                    "match_count": int(hit["count"]),
                    "sample_event_ids": json.dumps(sample_files),
                }
            )
        if rows:
            session.execute(_SIGMA_INSERT, rows)
        session.execute(
            text(
                """
                UPDATE evidence_sources
                SET yara_status = 'complete', yara_match_count = :matches, yara_file_count = :files
                WHERE id = :id
                """
            ),
            {"matches": len(rows), "files": files_scanned, "id": str(sid)},
        )
        session.commit()
        return {"rules_matched": len(rows), "files_scanned": files_scanned}
    except Exception:
        session.rollback()
        session.execute(
            text("UPDATE evidence_sources SET yara_status = 'failed' WHERE id = :id"),
            {"id": str(sid)},
        )
        session.commit()
        raise
    finally:
        session.close()
