import csv
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worker.util.pg_sanitize import sanitize_for_postgres, sanitize_text

# Common EZ Tools / KAPE CSV timestamp column names
TIMESTAMP_COLUMNS = (
    "Timestamp",
    "CopiedTimestamp",
    "Created0x10",
    "Created0x30",
    "CreatedOnUtc",
    "LastModified0x10",
    "LastModified0x30",
    "ModifiedOnUtc",
    "LastAccess0x10",
    "LastAccessedOnUtc",
    "UtcTimeCreated",
    "TimeCreated",
    "EventTime",
)

# KAPE CopyLog can be 80k+ file rows; cap for responsive ingest (Disk view has full tree)
MAX_KAPE_COLLECTION_EVENTS = 10_000


def _normalize_timestamp(value: str) -> str:
    """Trim .NET 7-digit fractional seconds to 6 for Python strptime."""
    value = value.strip().replace(" UTC", "").replace("Z", "")
    match = re.match(r"^(.+\.\d{6})\d+(.*)$", value)
    if match:
        return match.group(1) + match.group(2)
    return value


def _parse_timestamp(value: str) -> datetime | None:
    if not value or not value.strip():
        return None
    value = _normalize_timestamp(value)
    try:
        iso = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        pass
    formats = (
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%m/%d/%Y %H:%M:%S",
    )
    for fmt in formats:
        try:
            dt = datetime.strptime(value, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None


def _pick_timestamp(row: dict[str, str]) -> datetime | None:
    for col in TIMESTAMP_COLUMNS:
        if col in row and row[col]:
            ts = _parse_timestamp(row[col])
            if ts:
                return ts
    for key, val in row.items():
        if "time" in key.lower() or "date" in key.lower():
            ts = _parse_timestamp(val)
            if ts:
                return ts
    return None


def _summary_from_row(row: dict[str, str], source: str) -> str:
    if row.get("SourceFile") and "CopyLog" in source:
        size = row.get("FileSize")
        suffix = f" ({size} bytes)" if size else ""
        return f"Collected: {row['SourceFile']}{suffix}"[:2000]

    event_id = row.get("EventId") or row.get("EventID")
    description = row.get("Description") or row.get("Message")
    user = row.get("UserName") or row.get("TargetUserName")
    channel = row.get("Channel")

    if event_id and description:
        parts = [f"Event {event_id}: {description}"]
        if user:
            parts.append(user)
        if channel:
            parts.append(f"[{channel}]")
        return " — ".join(parts)

    for key in ("Description", "Message", "FullPath", "TargetFilename", "UserName", "EventId"):
        if row.get(key):
            return f"{key}: {row[key]}"
    non_empty = [f"{k}={v}" for k, v in list(row.items())[:4] if v]
    return f"{source} — " + (", ".join(non_empty) if non_empty else "event")


def _artifact_label(csv_path: Path) -> str:
    """Classify parsed CSV output for filtering (timeline, MFT view, etc.)."""
    stem = csv_path.stem.lower()
    path_lower = csv_path.as_posix().lower()
    if "mft" in stem or "/mft/" in path_lower or "mftecmd" in path_lower:
        return "mft"
    if "evtx" in path_lower or stem.endswith(".evtx"):
        return "evtx"
    if "prefetch" in path_lower or stem.endswith(".pf"):
        return "prefetch"
    if "registry" in path_lower or "recmd" in path_lower:
        return "registry"
    return csv_path.stem[:64]


def parse_csv_to_events(
    csv_path: Path,
    evidence_source_id: str,
) -> tuple[list[dict[str, Any]], str | None]:
    """Map EZ Tools / KAPE CSV rows to timeline event dicts.

    Returns (events, optional_note) when collection logs are capped.
    """
    events: list[dict[str, Any]] = []
    artifact = _artifact_label(csv_path)
    is_copylog = "CopyLog" in csv_path.name
    note: str | None = None

    with csv_path.open(newline="", encoding="utf-8-sig", errors="replace") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return events, note

        for i, row in enumerate(reader):
            row = {sanitize_text(k): sanitize_text(v) if v is not None else v for k, v in row.items()}
            if is_copylog and len(events) >= MAX_KAPE_COLLECTION_EVENTS:
                note = (
                    f"CopyLog capped at {MAX_KAPE_COLLECTION_EVENTS} collection events "
                    f"(use Disk view for full file tree)"
                )
                break
            ts = _pick_timestamp(row)
            if not ts:
                continue
            if is_copylog:
                event_type = "kape.collection"
                payload = sanitize_for_postgres(
                    {
                        k: row[k]
                        for k in ("SourceFile", "DestinationFile", "FileSize", "CopiedTimestamp")
                        if row.get(k)
                    }
                )
            else:
                event_type = row.get("EventType") or row.get("EventId") or artifact
                payload = sanitize_for_postgres(dict(row))
            events.append(
                {
                    "evidence_source_id": evidence_source_id,
                    "timestamp_utc": ts,
                    "event_type": str(event_type)[:128],
                    "summary": _summary_from_row(row, csv_path.name)[:2000],
                    "artifact_type": artifact[:64],
                    "original_source": str(csv_path),
                    "data": payload,
                    "entity_refs": [],
                }
            )
            if i > 500_000:
                break

    return events, note
