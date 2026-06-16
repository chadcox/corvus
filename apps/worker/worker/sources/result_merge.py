from typing import Any


def empty_result() -> dict[str, Any]:
    return {
        "timeline_events": [],
        "filesystem_nodes": [],
        "entities": [],
        "relations": [],
        "ingest_notes": [],
    }


def merge_results(primary: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    for key in ("timeline_events", "filesystem_nodes", "entities", "relations", "ingest_notes"):
        primary.setdefault(key, [])
        primary[key].extend(extra.get(key) or [])
    return primary
