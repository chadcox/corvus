"""Run Sigma rules against timeline events during ingest."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any
from uuid import UUID

from worker.config import settings
from worker.sigma.loader import SigmaRule, load_sigma_rules_cached
from worker.sigma.matcher import (
    LEVEL_RANK,
    CompiledSigmaRule,
    compiled_rule_matches_event,
    compile_sigma_rules,
    normalize_event_fields,
)

MAX_MATCHES_PER_RULE = 200
MAX_RULES_TO_STORE = 500
_COMPILED_RULES_CACHE: dict[int, list[CompiledSigmaRule]] = {}


def _rules_root() -> Path:
    return Path(getattr(settings, "sigma_rules_root", "/opt/sigma/rules"))


def _compiled_rules(rules: list[SigmaRule]) -> list[CompiledSigmaRule]:
    cache_key = id(rules)
    cached = _COMPILED_RULES_CACHE.get(cache_key)
    if cached is not None:
        return cached
    compiled = compile_sigma_rules(rules)
    _COMPILED_RULES_CACHE.clear()
    _COMPILED_RULES_CACHE[cache_key] = compiled
    return compiled


def _field_services(fields: dict[str, str]) -> set[str]:
    channel = fields.get("channel", "").lower()
    services: set[str] = set()
    for service in ("security", "system", "application", "powershell", "sysmon"):
        if service in channel:
            services.add(service)
    return services


def _field_categories(fields: dict[str, str]) -> set[str]:
    categories: set[str] = set()
    if fields.get("eventid") in ("4688", "1", "592") or fields.get("image") or fields.get("commandline"):
        categories.add("process_creation")
    if fields.get("targetfilename") or fields.get("objectname"):
        categories.add("file")
    if fields.get("sourceip") or fields.get("destinationip") or fields.get("ipaddress"):
        categories.add("network_connection")
    return categories


def _build_rule_indexes(
    rules: list[CompiledSigmaRule],
) -> tuple[
    dict[str, list[CompiledSigmaRule]],
    dict[str, list[CompiledSigmaRule]],
    dict[str, list[CompiledSigmaRule]],
    list[CompiledSigmaRule],
]:
    by_event_id: dict[str, list[CompiledSigmaRule]] = defaultdict(list)
    by_service: dict[str, list[CompiledSigmaRule]] = defaultdict(list)
    by_category: dict[str, list[CompiledSigmaRule]] = defaultdict(list)
    fallback: list[CompiledSigmaRule] = []

    for rule in rules:
        if rule.required_event_ids:
            for event_id in rule.required_event_ids:
                by_event_id[event_id].append(rule)
        elif rule.service:
            by_service[rule.service].append(rule)
        elif rule.category:
            by_category[rule.category].append(rule)
        else:
            fallback.append(rule)

    return by_event_id, by_service, by_category, fallback


def _candidate_rules(
    fields: dict[str, str],
    by_event_id: dict[str, list[CompiledSigmaRule]],
    by_service: dict[str, list[CompiledSigmaRule]],
    by_category: dict[str, list[CompiledSigmaRule]],
    fallback: list[CompiledSigmaRule],
) -> list[CompiledSigmaRule]:
    candidates: list[CompiledSigmaRule] = []
    seen: set[str] = set()

    def extend(rules: list[CompiledSigmaRule]) -> None:
        for rule in rules:
            rule_id = rule.rule.rule_id
            if rule_id not in seen:
                seen.add(rule_id)
                candidates.append(rule)

    event_id = fields.get("eventid")
    if event_id:
        extend(by_event_id.get(event_id, []))
    for service in _field_services(fields):
        extend(by_service.get(service, []))
    for category in _field_categories(fields):
        extend(by_category.get(category, []))
    extend(fallback)
    return candidates


def evaluate_sigma_rules(
    events: list[dict[str, Any]],
    evidence_source_id: str | UUID,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Annotate events with sigma_hits; return aggregated detection rows for DB."""
    rules = load_sigma_rules_cached(_rules_root())
    if not rules or not events:
        return [], events

    compiled_rules = _compiled_rules(rules)
    if not compiled_rules:
        return [], events

    indexed: list[tuple[dict[str, Any], dict[str, str]]] = []

    for ev in events:
        fields = normalize_event_fields(ev.get("data") or {})
        if fields.get("eventid") or fields.get("channel") or fields.get("image"):
            indexed.append((ev, fields))

    if not indexed:
        return [], events

    rule_match_events: dict[str, list[str]] = defaultdict(list)
    rule_meta: dict[str, SigmaRule] = {r.rule_id: r for r in rules}
    by_event_id, by_service, by_category, fallback = _build_rule_indexes(compiled_rules)

    for ev, fields in indexed:
        for rule in _candidate_rules(fields, by_event_id, by_service, by_category, fallback):
            rule_id = rule.rule.rule_id
            if len(rule_match_events.get(rule_id, [])) >= MAX_MATCHES_PER_RULE:
                continue
            if compiled_rule_matches_event(rule, fields):
                hit = {
                    "rule_id": rule_id,
                    "title": rule.rule.title,
                    "level": rule.rule.level,
                    "engine": "sigma",
                }
                ev.setdefault("sigma_hits", []).append(hit)
                ev_id = ev.get("id")
                if ev_id:
                    rule_match_events[rule_id].append(str(ev_id))

    detections: list[dict[str, Any]] = []
    eid = str(evidence_source_id)

    sorted_rule_ids = sorted(
        rule_match_events.keys(),
        key=lambda rid: (
            -LEVEL_RANK.get(rule_meta[rid].level, 0),
            -len(rule_match_events[rid]),
            rule_meta[rid].title,
        ),
    )[:MAX_RULES_TO_STORE]

    for rule_id in sorted_rule_ids:
        rule = rule_meta[rule_id]
        detections.append(
            {
                "evidence_source_id": eid,
                "engine": "sigma",
                "rule_id": rule_id,
                "title": rule.title,
                "level": rule.level,
                "description": rule.description[:4000],
                "tags": rule.tags,
                "match_count": len(rule_match_events[rule_id]),
                "sample_event_ids": [x for x in rule_match_events[rule_id] if x][:20],
            }
        )

    return detections, events
