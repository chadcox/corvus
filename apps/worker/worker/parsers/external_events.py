import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worker.parsers.csv_events import _parse_timestamp
from worker.util.pg_sanitize import sanitize_for_postgres, sanitize_text


TIMESTAMP_KEYS = (
    "datetime",
    "date_time",
    "timestamp",
    "timestamp_utc",
    "time",
    "event_time",
    "created",
    "created_time",
    "created_at",
    "last_modified",
    "modified",
    "accessed",
)

SUMMARY_KEYS = (
    "message",
    "display_name",
    "description",
    "summary",
    "event",
    "name",
    "path",
    "file_path",
    "url",
    "query",
)

ARTIFACT_KEYS = (
    "data_type",
    "parser",
    "plugin",
    "artifact",
    "artifact_type",
    "source",
    "module",
)


def _coerce_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if value > 10_000_000_000_000_000:
            value = value / 1_000_000
        elif value > 10_000_000_000:
            value = value / 1000
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None
    return _parse_timestamp(str(value))


def _first_value(row: dict[str, Any], keys: tuple[str, ...]) -> Any:
    lower_to_key = {str(k).lower(): k for k in row}
    for key in keys:
        actual = lower_to_key.get(key.lower())
        if actual is not None and row.get(actual) not in (None, ""):
            return row[actual]
    return None


def _pick_timestamp(row: dict[str, Any]) -> datetime | None:
    value = _first_value(row, TIMESTAMP_KEYS)
    if value is not None:
        ts = _coerce_timestamp(value)
        if ts:
            return ts
    for key, value in row.items():
        lower = str(key).lower()
        if "time" in lower or "date" in lower:
            ts = _coerce_timestamp(value)
            if ts:
                return ts
    return None


def _summary(row: dict[str, Any], source_name: str) -> str:
    value = _first_value(row, SUMMARY_KEYS)
    if value not in (None, ""):
        return sanitize_text(str(value))[:2000]
    parts = [f"{k}={v}" for k, v in list(row.items())[:5] if v not in (None, "")]
    return sanitize_text(f"{source_name}: " + (", ".join(parts) if parts else "event"))[:2000]


def _artifact(row: dict[str, Any], source_name: str) -> str:
    value = _first_value(row, ARTIFACT_KEYS)
    if value not in (None, ""):
        return sanitize_text(str(value))[:64]
    return sanitize_text(Path(source_name).stem)[:64]


def _event_type(row: dict[str, Any], artifact: str) -> str:
    value = _first_value(row, ("event_type", "event_id", "type", "activity", "action"))
    if value not in (None, ""):
        return sanitize_text(str(value))[:128]
    return artifact[:128]


def row_to_timeline_event(
    row: dict[str, Any],
    evidence_source_id: str,
    *,
    source_name: str,
    tool: str,
) -> dict[str, Any] | None:
    ts = _pick_timestamp(row)
    if not ts:
        return None
    artifact = _artifact(row, source_name)
    payload = sanitize_for_postgres(dict(row))
    payload.setdefault("_ff_tool", tool)
    return {
        "evidence_source_id": evidence_source_id,
        "timestamp_utc": ts,
        "event_type": _event_type(row, artifact),
        "summary": _summary(row, source_name),
        "artifact_type": artifact,
        "original_source": source_name,
        "data": payload,
        "entity_refs": [],
    }


def parse_jsonl_to_events(path: Path, evidence_source_id: str, *, tool: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue
            event = row_to_timeline_event(
                row,
                evidence_source_id,
                source_name=str(path),
                tool=tool,
            )
            if event:
                events.append(event)
    return events


def parse_json_to_events(path: Path, evidence_source_id: str, *, tool: str) -> list[dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(data, dict):
        rows = data.get("rows") or data.get("events") or data.get("results") or [data]
    elif isinstance(data, list):
        rows = data
    else:
        rows = []
    events: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        event = row_to_timeline_event(
            row,
            evidence_source_id,
            source_name=str(path),
            tool=tool,
        )
        if event:
            events.append(event)
    return events


def parse_csv_like_to_events(path: Path, evidence_source_id: str, *, tool: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
    with path.open("r", newline="", encoding="utf-8-sig", errors="replace") as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        if not reader.fieldnames:
            return events
        for row in reader:
            event = row_to_timeline_event(
                {sanitize_text(k): sanitize_text(v) if v is not None else v for k, v in row.items()},
                evidence_source_id,
                source_name=str(path),
                tool=tool,
            )
            if event:
                events.append(event)
    return events


def parse_tool_outputs(root: Path, evidence_source_id: str, *, tool: str) -> list[dict[str, Any]]:
    if not root.exists():
        return []
    events: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        lower = path.name.lower()
        if lower.endswith((".jsonl", ".jsonlines", ".ndjson")):
            events.extend(parse_jsonl_to_events(path, evidence_source_id, tool=tool))
        elif lower.endswith(".json"):
            events.extend(parse_json_to_events(path, evidence_source_id, tool=tool))
        elif lower.endswith((".csv", ".tsv")):
            events.extend(parse_csv_like_to_events(path, evidence_source_id, tool=tool))
    return events
