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


# Upper bounds used to infer the unit of a bare numeric epoch. Each bound is
# the value that unit reaches around the year 5138, so a realistic forensic
# timestamp in one unit can never be mistaken for the next unit up.
_EPOCH_SECONDS_MAX = 10**11
_EPOCH_MILLISECONDS_MAX = 10**14
_EPOCH_MICROSECONDS_MAX = 10**17

# 100-nanosecond intervals between 1601-01-01 (FILETIME/WebKit epoch) and
# 1970-01-01 (POSIX epoch).
_FILETIME_EPOCH_DELTA = 116_444_736_000_000_000

# Plaso serialises dfDateTime values as nested objects tagged with the class
# that defines their epoch and unit, e.g.
# ``{"__class_name__": "Filetime", "timestamp": 129638643088953339}``.
_PLASO_DATE_TIME_SCALES: dict[str, tuple[float, int]] = {
    # class name -> (units per second, epoch offset in those units)
    "Filetime": (10_000_000, _FILETIME_EPOCH_DELTA),
    "WebKitTime": (1_000_000, 11_644_473_600_000_000),
    "PosixTime": (1, 0),
    "PosixTimeInMilliseconds": (1_000, 0),
    "PosixTimeInMicroseconds": (1_000_000, 0),
    "PosixTimeInNanoSeconds": (1_000_000_000, 0),
    "JavaTime": (1_000, 0),
}


def _from_epoch_seconds(seconds: float) -> datetime | None:
    try:
        return datetime.fromtimestamp(seconds, tz=timezone.utc)
    except (OSError, OverflowError, ValueError):
        return None


def _coerce_numeric_timestamp(value: int | float) -> datetime | None:
    """Interpret a bare number as a POSIX epoch, inferring its unit by scale."""
    magnitude = abs(value)
    if magnitude < _EPOCH_SECONDS_MAX:
        divisor = 1
    elif magnitude < _EPOCH_MILLISECONDS_MAX:
        divisor = 1_000
    elif magnitude < _EPOCH_MICROSECONDS_MAX:
        divisor = 1_000_000
    else:
        divisor = 1_000_000_000
    return _from_epoch_seconds(value / divisor)


def _coerce_plaso_date_time(value: dict[str, Any]) -> datetime | None:
    """Decode a Plaso/dfDateTime ``DateTimeValues`` object.

    Unknown classes return ``None`` so the caller can fall back to another
    field rather than inventing a date from an unrecognised epoch.
    """
    raw = value.get("timestamp")
    if not isinstance(raw, (int, float)) or isinstance(raw, bool):
        # Some classes (TimeElements) carry an ISO string instead.
        text = value.get("string") or value.get("time_string")
        return _parse_timestamp(str(text)) if text else None
    scale = _PLASO_DATE_TIME_SCALES.get(str(value.get("__class_name__")))
    if scale is None:
        return None
    units_per_second, epoch_offset = scale
    return _from_epoch_seconds((raw - epoch_offset) / units_per_second)


def _coerce_timestamp(value: Any) -> datetime | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, dict):
        return _coerce_plaso_date_time(value)
    if isinstance(value, (int, float)):
        return _coerce_numeric_timestamp(value)
    return _parse_timestamp(str(value))


def _first_value(row: dict[str, Any], keys: tuple[str, ...]) -> Any:
    lower_to_key = {str(k).lower(): k for k in row}
    for key in keys:
        actual = lower_to_key.get(key.lower())
        if actual is not None and row.get(actual) not in (None, ""):
            return row[actual]
    return None


def _pick_timestamp(row: dict[str, Any]) -> datetime | None:
    # Try every preferred key, not just the first one present: a row can carry
    # a rich-but-undecodable value (Plaso's ``date_time`` object) alongside a
    # plain epoch in a lower-priority field.
    lower_to_key = {str(k).lower(): k for k in row}
    for key in TIMESTAMP_KEYS:
        actual = lower_to_key.get(key.lower())
        if actual is None or row.get(actual) in (None, ""):
            continue
        ts = _coerce_timestamp(row[actual])
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
