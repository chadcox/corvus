"""Remove characters PostgreSQL text/jsonb cannot store."""

from __future__ import annotations

from typing import Any

# NUL in JSON strings breaks psycopg → jsonb casts (UntranslatableCharacter).
_NUL = "\x00"
_BOM = "\ufeff"


def sanitize_text(value: str) -> str:
    if not value:
        return value
    return value.replace(_NUL, "").replace(_BOM, "")


def sanitize_key(key: str) -> str:
    return sanitize_text(key).lstrip(_BOM)


def sanitize_for_postgres(value: Any) -> Any:
    """Recursively clean strings for Postgres text and JSONB columns."""
    if value is None:
        return None
    if isinstance(value, str):
        return sanitize_text(value)
    if isinstance(value, bytes):
        return sanitize_text(value.decode("utf-8", errors="replace"))
    if isinstance(value, dict):
        return {
            sanitize_key(k) if isinstance(k, str) else k: sanitize_for_postgres(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [sanitize_for_postgres(item) for item in value]
    if isinstance(value, tuple):
        return tuple(sanitize_for_postgres(item) for item in value)
    return value
