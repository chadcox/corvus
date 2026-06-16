import re
import uuid
from typing import Any

# EZ Tools / Windows artifact field names → entity type
ENTITY_FIELDS: dict[str, str] = {
    "UserName": "User",
    "TargetUserName": "User",
    "SubjectUserName": "User",
    "AccountName": "User",
    "User": "User",
    "ProcessName": "Process",
    "Image": "Process",
    "ParentProcessName": "Process",
    "NewProcessName": "Process",
    "FullPath": "File",
    "TargetFilename": "File",
    "FileName": "File",
    "Path": "File",
    "Computer": "Host",
    "Hostname": "Host",
    "MachineName": "Host",
    "ComputerName": "Host",
    "IpAddress": "IpAddress",
    "SourceIp": "IpAddress",
    "DestinationIp": "IpAddress",
    "DestIp": "IpAddress",
    "SourceAddress": "IpAddress",
    "DestinationAddress": "IpAddress",
}

# Fields whose values are Windows paths (KAPE CopyLog, MFT, etc.)
PATH_ENTITY_FIELDS = (
    "SourceFile",
    "DestinationFile",
    "FullPath",
    "TargetFilename",
    "FileName",
    "Path",
)

_WIN_USER_PATH_RE = re.compile(r"(?:^|[\\/])Users[\\/]([^\\/]+)", re.IGNORECASE)
_SKIP_PROFILE_DIRS = frozenset(
    {
        "public",
        "default",
        "default user",
        "all users",
        "defaultaccount",
        "wdagutilityaccount",
    }
)

_IP_RE = re.compile(
    r"^(?:(?:25[0-5]|2[0-4]\d|[01]?\d?\d)\.){3}"
    r"(?:25[0-5]|2[0-4]\d|[01]?\d?\d)$"
)

_SKIP_VALUES = frozenset({"", "-", "N/A", "null", "None", "(null)"})


def _normalize_value(value: str) -> str | None:
    value = value.strip()
    if not value or value in _SKIP_VALUES:
        return None
    return value


def _is_valid_ip(value: str) -> bool:
    if value.startswith("::ffff:"):
        value = value[7:]
    return bool(_IP_RE.match(value))


def _normalize_path(path: str) -> str:
    return path.strip().replace("\\", "/")


def _entities_from_windows_path(path: str) -> list[tuple[str, str]]:
    """Extract User / File / Process entities from a Windows file path."""
    path = _normalize_value(path)
    if not path:
        return []

    found: list[tuple[str, str]] = []
    display_path = _normalize_path(path)[:512]
    found.append(("File", display_path))

    user_match = _WIN_USER_PATH_RE.search(path)
    if user_match:
        profile = user_match.group(1).strip()
        if profile.lower() not in _SKIP_PROFILE_DIRS:
            found.append(("User", profile))

    basename = path.replace("\\", "/").rsplit("/", 1)[-1]
    if basename.lower().endswith(".exe") and _normalize_value(basename):
        found.append(("Process", basename))

    return found


def _link_entity(
    key_to_entity: dict[tuple[str, str], dict[str, Any]],
    entity_type: str,
    display_name: str,
    evidence_source_id: str,
    source_field: str,
    refs: list[str],
    seen_refs: set[str],
) -> None:
    if entity_type == "IpAddress" and not _is_valid_ip(display_name):
        return

    key = (entity_type, display_name.lower())
    if key not in key_to_entity:
        entity_id = str(uuid.uuid4())
        key_to_entity[key] = {
            "id": entity_id,
            "evidence_source_id": evidence_source_id,
            "entity_type": entity_type,
            "display_name": display_name[:512],
            "attributes": {"source_field": source_field},
        }

    entity_id = key_to_entity[key]["id"]
    if entity_id not in seen_refs:
        seen_refs.add(entity_id)
        refs.append(entity_id)


def extract_entities_from_events(
    events: list[dict[str, Any]],
    evidence_source_id: str,
) -> list[dict[str, Any]]:
    """Derive deduplicated entities and link entity_refs on each event."""
    key_to_entity: dict[tuple[str, str], dict[str, Any]] = {}

    for event in events:
        data = event.get("data") or {}
        if not isinstance(data, dict):
            event["entity_refs"] = []
            continue

        refs: list[str] = []
        seen_refs: set[str] = set()

        for field, entity_type in ENTITY_FIELDS.items():
            raw = data.get(field)
            if raw is None:
                continue
            display_name = _normalize_value(str(raw))
            if not display_name:
                continue
            _link_entity(
                key_to_entity,
                entity_type,
                display_name,
                evidence_source_id,
                field,
                refs,
                seen_refs,
            )

        for field in PATH_ENTITY_FIELDS:
            raw = data.get(field)
            if raw is None:
                continue
            for entity_type, display_name in _entities_from_windows_path(str(raw)):
                _link_entity(
                    key_to_entity,
                    entity_type,
                    display_name,
                    evidence_source_id,
                    field,
                    refs,
                    seen_refs,
                )

        event["entity_refs"] = refs

    return list(key_to_entity.values())
