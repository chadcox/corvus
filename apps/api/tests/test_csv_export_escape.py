from __future__ import annotations

import csv
import io
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.auth.service import get_current_user
from app.config import settings
from app.database import get_db
from app.main import app
from app.models import EvidenceFileHash, EvidenceSource, TimelineEvent
from app.util.csv_export import escape_csv_cell, escape_csv_row, is_formula_like


TIMELINE_HEADER = [
    "timestamp_utc",
    "event_type",
    "summary",
    "artifact_type",
    "original_source",
]
HASH_HEADER = ["path", "sha256", "sha1", "md5", "size_bytes", "computed_at"]


@dataclass
class FakeUser:
    id: str = "test-user"
    username: str = "analyst"
    role: str = "analyst"
    is_active: bool = True


class FakeQuery:
    def __init__(self, rows: list[Any]):
        self.rows = rows

    def filter(self, *_args, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def with_entities(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def first(self):
        return self.rows[0] if self.rows else None

    def yield_per(self, *_args, **_kwargs):
        return iter(self.rows)


class FakeDb:
    """Routes ``db.query(...)`` by the owning model of the first argument."""

    def __init__(self, source: EvidenceSource, rows_by_model: dict[Any, list[Any]]):
        self.source = source
        self.rows_by_model = rows_by_model

    def query(self, *entities):
        first = entities[0]
        model = getattr(first, "class_", first)
        if model is EvidenceSource:
            return FakeQuery([self.source])
        return FakeQuery(self.rows_by_model.get(model, []))


def _source(case_id: uuid.UUID, source_id: uuid.UUID) -> EvidenceSource:
    return EvidenceSource(
        id=source_id,
        case_id=case_id,
        hostname="WKS-042",
        collector="import",
        source_type="endpoint",
        platform="windows",
        package_path="/data/evidence/package.zip",
        status="completed",
    )


def _get(url: str, db: FakeDb):
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: FakeUser()
    try:
        return TestClient(app).get(url)
    finally:
        app.dependency_overrides.clear()


HOSTILE = '=cmd|\' /C calc\'!A0'


def _csv_rows(response) -> list[list[str]]:
    return list(csv.reader(io.StringIO(response.text, newline="")))


def _assert_quote_all_output(response) -> list[list[str]]:
    """Parse the response and verify its canonical all-quoted serialization."""
    rows = _csv_rows(response)
    expected = io.StringIO(newline="")
    csv.writer(expected, quoting=csv.QUOTE_ALL).writerows(rows)
    assert response.text == expected.getvalue()
    return rows


def _timeline_export(summary: str, original_source: str = "Security.evtx"):
    case_id, source_id = uuid.uuid4(), uuid.uuid4()
    event = TimelineEvent(
        id=uuid.uuid4(),
        evidence_source_id=source_id,
        timestamp_utc=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
        event_type="process.create",
        summary=summary,
        artifact_type="evtx",
        original_source=original_source,
    )
    db = FakeDb(_source(case_id, source_id), {TimelineEvent: [event]})
    return _get(f"/api/v1/cases/{case_id}/sources/{source_id}/timeline/export", db)


def _hash_export(relative_path: str):
    case_id, source_id = uuid.uuid4(), uuid.uuid4()
    row = EvidenceFileHash(
        id=uuid.uuid4(),
        evidence_source_id=source_id,
        relative_path=relative_path,
        sha256="a" * 64,
        sha1="b" * 40,
        md5="c" * 32,
        file_size=1024,
        computed_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
    )
    db = FakeDb(_source(case_id, source_id), {EvidenceFileHash: [row]})
    return _get(f"/api/v1/cases/{case_id}/evidence/{source_id}/hashes/export", db)


# --- helper unit behavior -------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        "=1+1",
        "+1+1",
        "-1+1cmd",
        "@SUM(A1)",
        '=cmd|\' /C calc\'!A0',
        "\t=1+1",
        "\r=1+1",
        "\n=1+1",
        "＝1+1",
        "＋1+1",
        "－1+1cmd",
        "＠SUM(A1)",
    ],
)
def test_formula_like_values_are_prefixed(value: str):
    assert is_formula_like(value) is True
    assert escape_csv_cell(value) == "'" + value


@pytest.mark.parametrize(
    "value",
    [
        "",
        "powershell.exe launched",
        "C:\\Windows\\System32\\cmd.exe",
        "-12",
        "-12.5",
        "+3",
        "-1.2e9",
        "2026-01-02T03:04:05+00:00",
    ],
)
def test_benign_values_are_untouched(value: str):
    assert is_formula_like(value) is False
    assert escape_csv_cell(value) == value


def test_non_text_cells_pass_through_unchanged():
    assert escape_csv_cell(1024) == 1024
    assert escape_csv_cell(None) is None


def test_escaping_can_be_disabled():
    assert escape_csv_cell("=1+1", enabled=False) == "=1+1"
    assert escape_csv_row(["=1+1", "@x"], enabled=False) == ["=1+1", "@x"]


def test_escape_row_handles_mixed_cells():
    assert escape_csv_row(["=1+1", "ok", 7, None]) == ["'=1+1", "ok", 7, None]


# --- endpoint behavior ----------------------------------------------------


def test_timeline_export_neutralizes_formula_cells():
    response = _timeline_export(HOSTILE, original_source="@evil.evtx")
    assert response.status_code == 200, response.text
    rows = _assert_quote_all_output(response)
    assert rows[0] == TIMELINE_HEADER
    assert rows[1][2] == "'" + HOSTILE
    assert rows[1][4] == "'@evil.evtx"


@pytest.mark.parametrize("prefix", ["＝", "＋", "－", "＠"])
def test_timeline_export_neutralizes_full_width_formula_prefixes(prefix: str):
    response = _timeline_export(prefix + "SUM(A1)")
    assert response.status_code == 200, response.text
    rows = _assert_quote_all_output(response)
    assert rows[1][2] == "'" + prefix + "SUM(A1)"


def test_timeline_export_quotes_semicolon_locale_formula_suffix():
    value = "benign prefix;=HYPERLINK(https://example.invalid)"
    response = _timeline_export(value)
    assert response.status_code == 200, response.text
    rows = _assert_quote_all_output(response)
    assert rows[1][2] == value
    assert f'"{value}"' in response.text


def test_timeline_export_preserves_benign_summary_and_headers():
    response = _timeline_export("powershell.exe launched")
    assert response.status_code == 200, response.text
    rows = _assert_quote_all_output(response)
    assert rows[0] == TIMELINE_HEADER
    assert rows[1] == [
        "2026-01-02T03:04:05+00:00",
        "process.create",
        "powershell.exe launched",
        "evtx",
        "Security.evtx",
    ]
    assert response.headers["content-type"].startswith("text/csv")
    assert response.headers["content-disposition"] == 'attachment; filename="timeline-WKS-042.csv"'


def test_hash_export_neutralizes_formula_path():
    response = _hash_export("=HYPERLINK(\"http://x\",\"click\")")
    assert response.status_code == 200, response.text
    rows = _assert_quote_all_output(response)
    assert rows[0] == HASH_HEADER
    assert rows[1][0] == "'=HYPERLINK(\"http://x\",\"click\")"
    assert response.headers["content-type"].startswith("text/csv")
    assert response.headers["content-disposition"] == (
        'attachment; filename="file-hashes-WKS-042.csv"'
    )


def test_hash_export_quotes_semicolon_locale_formula_suffix():
    value = "Users/analyst/report.docx;=HYPERLINK(https://example.invalid)"
    response = _hash_export(value)
    assert response.status_code == 200, response.text
    rows = _assert_quote_all_output(response)
    assert rows[1][0] == value
    assert f'"{value}"' in response.text


def test_hash_export_preserves_benign_row():
    response = _hash_export("Users/analyst/report.docx")
    assert response.status_code == 200, response.text
    rows = _assert_quote_all_output(response)
    assert rows[0] == HASH_HEADER
    assert rows[1] == [
        "Users/analyst/report.docx",
        "a" * 64,
        "b" * 40,
        "c" * 32,
        "1024",
        "2026-01-02T03:04:05+00:00",
    ]


@pytest.mark.parametrize("export", [_timeline_export, _hash_export], ids=["timeline", "hashes"])
def test_exports_stay_streaming_responses(export):
    response = export("powershell.exe launched")
    assert response.status_code == 200, response.text
    assert "content-length" not in response.headers


def test_toggle_disables_escaping(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "csv_export_formula_escape", False)
    response = _timeline_export(HOSTILE)
    assert response.status_code == 200, response.text
    rows = _csv_rows(response)
    assert rows[0] == TIMELINE_HEADER
    assert rows[1][2] == HOSTILE
    assert not response.text.startswith('"timestamp_utc"')
