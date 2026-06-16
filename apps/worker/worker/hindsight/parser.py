"""Parse Hindsight JSONL output into ForensicFlow timeline events."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worker.util.pg_sanitize import sanitize_for_postgres, sanitize_text

# Cap browser rows per profile for responsive ingest (full JSONL kept on disk under _ff_parsed)


def _parse_datetime(value: str | None) -> datetime | None:
    if not value or not str(value).strip():
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _event_type_from_data_type(data_type: str) -> str:
    dt = (data_type or "").lower()
    if "page_visited" in dt or "media_playback" in dt:
        return "browser.visit"
    if "file_downloaded" in dt:
        return "browser.download"
    if "cookie" in dt:
        return "browser.cookie"
    if "bookmark" in dt:
        return "browser.bookmark"
    if "login_item" in dt:
        return "browser.credential"
    if "autofill" in dt:
        return "browser.autofill"
    # Storage types must be matched before the generic "session" branch:
    # "session_storage" contains the substring "session".
    if (
        "local_storage" in dt
        or "session_storage" in dt
        or "extension_storage" in dt
        or "indexeddb" in dt
        or "file_system" in dt
    ):
        return "browser.storage"
    if "session" in dt:
        return "browser.session"
    if "extension" in dt:
        return "browser.extension"
    if "cache" in dt:
        return "browser.cache"
    if "preferences" in dt or "site_setting" in dt:
        return "browser.preference"
    return "browser.artifact"


def _summary_from_record(record: dict[str, Any]) -> str:
    message = record.get("message")
    if isinstance(message, str) and message.strip():
        return sanitize_text(message.strip()[:2000])
    url = record.get("url")
    title = record.get("title")
    if url and title:
        return sanitize_text(f"{url} ({title})"[:2000])
    if url:
        return sanitize_text(str(url)[:2000])
    data_type = record.get("data_type") or record.get("row_type") or "browser artifact"
    return sanitize_text(str(data_type)[:2000])


def parse_hindsight_jsonl(
    jsonl_path: Path,
    evidence_source_id: str,
    *,
    profile_hint: str | None = None,
) -> list[dict[str, Any]]:
    """Convert Hindsight JSONL lines to timeline event dicts."""
    events: list[dict[str, Any]] = []
    if not jsonl_path.is_file():
        return events

    profile_label = profile_hint or jsonl_path.stem

    with jsonl_path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(record, dict):
                continue

            ts = _parse_datetime(
                record.get("datetime") or record.get("timestamp") or record.get("visit_time")
            )
            if ts is None:
                ts = datetime(1970, 1, 1, tzinfo=timezone.utc)

            data_type = str(record.get("data_type") or "")
            event_type = _event_type_from_data_type(data_type)
            data = sanitize_for_postgres(dict(record))
            data["browser_profile"] = profile_label
            data["hindsight_data_type"] = data_type or None

            events.append(
                {
                    "evidence_source_id": evidence_source_id,
                    "timestamp_utc": ts,
                    "event_type": event_type,
                    "summary": _summary_from_record(record),
                    "artifact_type": "browser",
                    "original_source": str(jsonl_path),
                    "data": data,
                    "entity_refs": [],
                }
            )

    return events
