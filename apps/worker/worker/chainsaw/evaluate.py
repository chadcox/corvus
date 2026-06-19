"""Map Chainsaw hunt output to Corvus detections and timeline hits."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any
from uuid import UUID

from worker.chainsaw.hunt import (
    collect_evtx_for_hunt,
    hit_correlation_keys,
    hit_engine,
    hit_level,
    hit_rule_id,
    hit_title,
    run_chainsaw_hunt_parallel,
)
from worker.sigma.matcher import LEVEL_RANK, normalize_event_fields


def _build_event_index(
    events: list[dict[str, Any]],
) -> tuple[list[tuple[dict[str, Any], dict[str, str]]], dict[tuple[str, str, str], list[str]]]:
    indexed: list[tuple[dict[str, Any], dict[str, str]]] = []
    by_key: dict[tuple[str, str, str], list[str]] = defaultdict(list)

    for ev in events:
        fields = normalize_event_fields(ev.get("data") or {})
        if not (fields.get("eventid") or fields.get("channel")):
            continue
        indexed.append((ev, fields))
        eid = fields.get("eventid", "")
        rid = fields.get("recordnumber") or fields.get("eventrecordid") or ""
        host = (fields.get("computer") or "").lower()
        if eid:
            by_key[(eid, rid, host)].append(str(ev.get("id", "")))
            if rid:
                by_key[(eid, rid, "")].append(str(ev.get("id", "")))

    return indexed, by_key


def _match_event_ids(
    hit: dict[str, Any],
    by_key: dict[tuple[str, str, str], list[str]],
) -> list[str]:
    eid, rid, host = hit_correlation_keys(hit)
    if not eid:
        return []
    ids = list(by_key.get((eid, rid, host), []))
    if not ids and rid:
        ids = list(by_key.get((eid, rid, ""), []))
    if not ids:
        ids = list(by_key.get((eid, "", host), []))
    if not ids:
        ids = list(by_key.get((eid, "", ""), []))
    seen: set[str] = set()
    out: list[str] = []
    for ev_id in ids:
        if ev_id and ev_id not in seen:
            seen.add(ev_id)
            out.append(ev_id)
    return out[:20]


def evaluate_chainsaw_hunt(
    package_dir: Any,
    events: list[dict[str, Any]],
    evidence_source_id: str | UUID,
    *,
    evtx_files: list[Path] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Run Chainsaw on package EVTX files; annotate events and return detection rows.

    Returns (detection_rows, updated_events). Engine is ``sigma`` or ``chainsaw`` per hit.
    """
    package_dir = Path(package_dir)
    evtx_files = evtx_files if evtx_files is not None else collect_evtx_for_hunt(package_dir)
    if not evtx_files:
        return [], events

    hits = run_chainsaw_hunt_parallel(evtx_files)
    if not hits:
        return [], events

    _, by_key = _build_event_index(events)
    events_by_id = {str(ev.get("id")): ev for ev in events if ev.get("id")}
    rule_events: dict[str, list[str]] = defaultdict(list)
    rule_meta: dict[str, dict[str, Any]] = {}

    for hit in hits:
        engine = hit_engine(hit)
        rule_id = hit_rule_id(hit)
        title = hit_title(hit)
        level = hit_level(hit)
        group = hit.get("group") or hit.get("Group") or ("Sigma" if engine == "sigma" else "Chainsaw")
        tags = hit.get("tags") if isinstance(hit.get("tags"), list) else []
        if engine == "sigma":
            tags = [str(t) for t in tags if t]
            description = f"Sigma rule via Chainsaw ({group})"
        else:
            tags = ["chainsaw", str(group).lower().replace(" ", "-")]
            description = f"Chainsaw rule ({group})"
        rule_meta[rule_id] = {
            "title": title,
            "level": level,
            "description": description,
            "tags": tags,
            "engine": engine,
        }

        matched_ids = _match_event_ids(hit, by_key)
        for ev_id in matched_ids:
            if ev_id not in rule_events[rule_id]:
                rule_events[rule_id].append(ev_id)

        if not matched_ids:
            continue

        hit_ref = {
            "rule_id": rule_id,
            "title": title,
            "level": level,
            "engine": engine,
        }
        for ev_id in matched_ids:
            ev = events_by_id.get(ev_id)
            if ev is not None:
                ev.setdefault("sigma_hits", []).append(hit_ref)

    eid = str(evidence_source_id)
    detections: list[dict[str, Any]] = []
    sorted_rules = sorted(
        rule_events.keys(),
        key=lambda rid: (
            -LEVEL_RANK.get(rule_meta[rid]["level"], 0),
            -len(rule_events[rid]),
            rule_meta[rid]["title"],
        ),
    )[:500]

    for rule_id in sorted_rules:
        meta = rule_meta[rule_id]
        detections.append(
            {
                "evidence_source_id": eid,
                "engine": meta["engine"],
                "rule_id": rule_id,
                "title": meta["title"],
                "level": meta["level"],
                "description": meta["description"][:4000],
                "tags": meta["tags"],
                "match_count": len(rule_events[rule_id]),
                "sample_event_ids": rule_events[rule_id][:20],
            }
        )

    return detections, events
