"""Summarize timeline events for Sigma matching (ingest notes / self-test)."""

from __future__ import annotations

from typing import Any

from worker.sigma.matcher import normalize_event_fields


def is_sigma_eligible_event(data: dict[str, Any]) -> bool:
    fields = normalize_event_fields(data)
    return bool(fields.get("eventid") or fields.get("channel") or fields.get("image"))


def summarize_sigma_inputs(events: list[dict[str, Any]]) -> dict[str, int]:
    """Count event categories relevant to Sigma."""
    total = len(events)
    copylog = sum(1 for ev in events if ev.get("event_type") == "kape.collection")
    eligible = sum(1 for ev in events if is_sigma_eligible_event(ev.get("data") or {}))
    return {
        "total": total,
        "copylog": copylog,
        "sigma_eligible": eligible,
        "other": total - copylog - eligible,
    }
