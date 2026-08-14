"""Offset pagination and exact totals for the entity catalog.

These run against the configured Postgres (the compose stack in CI) because the
behaviour under test is database ordering: entity JSONB `entity_refs` matching
and tie-broken sorts cannot be exercised by a fake session. Every fixture body
runs inside a transaction that is rolled back, so no rows survive the test.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth.service import get_current_user
from app.database import engine, get_db
from app.main import app
from app.models import Case, Entity, EvidenceSource, TimelineEvent


@dataclass
class FakeUser:
    id: str = "test-user"
    username: str = "analyst"
    role: str = "analyst"
    is_active: bool = True


@pytest.fixture(scope="module")
def connection():
    try:
        conn = engine.connect()
        migrated = inspect(conn).has_table("entities")
    except SQLAlchemyError as exc:  # no database in this environment
        pytest.skip(f"Postgres unavailable: {exc}")
    if not migrated:
        conn.close()
        pytest.skip("Postgres reachable but not migrated")
    conn.rollback()  # release the transaction the inspection autobegan
    yield conn
    conn.close()


@pytest.fixture
def db(connection):
    outer = connection.begin()
    session = Session(bind=connection)
    try:
        yield session
    finally:
        session.close()
        outer.rollback()


def _source(db: Session, case: Case, hostname: str) -> EvidenceSource:
    source = EvidenceSource(
        id=uuid.uuid4(),
        case_id=case.id,
        hostname=hostname,
        package_path=f"/data/evidence/{hostname}.zip",
        status="completed",
    )
    db.add(source)
    return source


def _entity(db: Session, source: EvidenceSource, entity_type: str, name: str) -> Entity:
    entity = Entity(
        id=uuid.uuid4(),
        evidence_source_id=source.id,
        entity_type=entity_type,
        display_name=name,
        attributes={},
    )
    db.add(entity)
    return entity


def _event(
    db: Session,
    source: EvidenceSource,
    when: datetime,
    summary: str,
    refs: list[str],
) -> TimelineEvent:
    event = TimelineEvent(
        id=uuid.uuid4(),
        evidence_source_id=source.id,
        timestamp_utc=when,
        event_type="logon",
        summary=summary,
        data={},
        entity_refs=refs,
        sigma_hits=[],
    )
    db.add(event)
    return event


T1 = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
T2 = datetime(2026, 1, 1, 1, 0, 0, tzinfo=UTC)


@pytest.fixture
def fixture_data(db: Session):
    case = Case(id=uuid.uuid4(), name="Pagination case")
    db.add(case)
    source = _source(db, case, "WKS-A")
    other = _source(db, case, "WKS-B")
    db.flush()

    # 11 entities in the source under test, including a four-row tie on
    # (entity_type, display_name) that only `id` can order deterministically.
    for name in ("alpha.txt", "zeta.txt"):
        _entity(db, source, "File", name)
    for _ in range(4):
        _entity(db, source, "File", "dup.txt")
    for _ in range(2):
        _entity(db, source, "Process", "svchost.exe")
    _entity(db, source, "User", "analyst")
    _entity(db, source, "User", "SVCHOST-user")
    target = _entity(db, source, "Host", "target-host")

    # Rows in the sibling source that sort first and match the same filters.
    _entity(db, other, "File", "aaa-first.txt")
    _entity(db, other, "Process", "svchost.exe")

    db.flush()
    ref = [str(target.id)]
    for index in range(3):
        _event(db, source, T1, f"same-timestamp {index}", ref)
    for index in range(3):
        _event(db, source, T2, f"later {index}", ref)
    _event(db, source, T1, "unrelated", [])
    _event(db, other, T1, "other source", ref)
    _event(db, other, T2, "other source later", ref)
    db.flush()

    return {"case": case, "source": source, "other": other, "target": target}


@pytest.fixture
def client(db: Session):
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: FakeUser()
    # Not a context manager: the lifespan hook would run migrations.
    yield TestClient(app)
    app.dependency_overrides.clear()


def _url(data, suffix: str = "") -> str:
    case_id = data["case"].id
    source_id = data["source"].id
    return f"/api/v1/cases/{case_id}/sources/{source_id}/entities{suffix}"


def _ids(response) -> list[str]:
    assert response.status_code == 200, response.text
    return [row["id"] for row in response.json()]


def test_entity_pages_cover_every_row_once_in_reference_order(client, fixture_data):
    reference = _ids(client.get(_url(fixture_data), params={"limit": 1000}))
    assert len(reference) == 11

    paged: list[str] = []
    for offset in range(0, 12, 3):
        paged.extend(_ids(client.get(_url(fixture_data), params={"limit": 3, "offset": offset})))

    assert paged == reference
    assert len(set(paged)) == len(paged)


def test_identical_names_keep_a_stable_page_boundary(client, fixture_data):
    # The four "dup.txt" rows straddle a page edge at limit=3; without the id
    # tiebreak the same row could appear on both pages or be skipped.
    first = _ids(client.get(_url(fixture_data), params={"limit": 3, "offset": 0}))
    second = _ids(client.get(_url(fixture_data), params={"limit": 3, "offset": 3}))
    repeat_first = _ids(client.get(_url(fixture_data), params={"limit": 3, "offset": 0}))

    assert first == repeat_first
    assert set(first).isdisjoint(second)

    ordered = client.get(_url(fixture_data), params={"limit": 1000}).json()
    assert [row["id"] for row in ordered][:3] == first
    assert [row["id"] for row in ordered][3:6] == second

    dup_ids = [uuid.UUID(row["id"]) for row in ordered if row["display_name"] == "dup.txt"]
    assert len(dup_ids) == 4
    assert dup_ids == sorted(dup_ids)


def test_offsets_at_and_past_the_end_are_empty_or_the_last_row(client, fixture_data):
    total = client.get(_url(fixture_data, "/count")).json()["count"]
    assert total == 11

    last = _ids(client.get(_url(fixture_data), params={"limit": 200, "offset": total - 1}))
    reference = _ids(client.get(_url(fixture_data), params={"limit": 1000}))
    assert last == reference[-1:]

    assert _ids(client.get(_url(fixture_data), params={"offset": total})) == []
    assert _ids(client.get(_url(fixture_data), params={"offset": total + 500})) == []


def test_counts_match_filtered_pages(client, fixture_data):
    reference = _ids(client.get(_url(fixture_data), params={"limit": 1000}))

    for params, expected in (
        ({}, 11),
        ({"entity_type": "File"}, 6),
        ({"q": "svchost"}, 3),
        ({"entity_type": "User", "q": "svchost"}, 1),
        ({"q": "no-such-entity"}, 0),
        ({"ids": reference[:2]}, 2),
    ):
        count = client.get(_url(fixture_data, "/count"), params=params)
        assert count.status_code == 200, count.text
        assert count.json() == {"count": expected}, params
        rows = _ids(client.get(_url(fixture_data), params={**params, "limit": 1000}))
        assert len(rows) == expected, params


def test_filtered_listing_pages_independently_of_the_unfiltered_total(client, fixture_data):
    params = {"entity_type": "File"}
    reference = _ids(client.get(_url(fixture_data), params={**params, "limit": 1000}))
    assert len(reference) == 6

    paged = _ids(client.get(_url(fixture_data), params={**params, "limit": 4, "offset": 0}))
    paged += _ids(client.get(_url(fixture_data), params={**params, "limit": 4, "offset": 4}))
    assert paged == reference


def test_pagination_never_leaks_rows_from_a_sibling_source(client, fixture_data, db):
    other_ids = [
        str(row.id)
        for row in db.query(Entity)
        .filter(Entity.evidence_source_id == fixture_data["other"].id)
        .all()
    ]
    assert other_ids

    everything = _ids(client.get(_url(fixture_data), params={"limit": 1000}))
    assert set(everything).isdisjoint(other_ids)

    # An explicit id filter for the sibling's rows must not resolve them either.
    assert _ids(client.get(_url(fixture_data), params={"ids": other_ids})) == []
    assert client.get(_url(fixture_data, "/count"), params={"ids": other_ids}).json() == {
        "count": 0
    }
    assert client.get(_url(fixture_data, "/count"), params={"q": "svchost"}).json() == {
        "count": 3
    }


def test_entity_timeline_pages_are_stable_across_identical_timestamps(client, fixture_data):
    entity_id = fixture_data["target"].id
    suffix = f"/{entity_id}/timeline"

    total = client.get(_url(fixture_data, f"{suffix}/count"))
    assert total.status_code == 200, total.text
    # Two of the source's events do not reference the entity, and the sibling
    # source's two referencing events belong to another host.
    assert total.json() == {"count": 6}

    reference = _ids(client.get(_url(fixture_data, suffix), params={"limit": 500}))
    assert len(reference) == 6

    paged: list[str] = []
    for offset in range(0, 8, 2):
        paged.extend(_ids(client.get(_url(fixture_data, suffix), params={"limit": 2, "offset": offset})))

    assert paged == reference
    assert len(set(paged)) == 6

    events = client.get(_url(fixture_data, suffix), params={"limit": 500}).json()
    assert [e["timestamp_utc"] for e in events] == sorted(e["timestamp_utc"] for e in events)


def test_entity_timeline_rejects_entities_outside_the_source(client, fixture_data, db):
    foreign = (
        db.query(Entity)
        .filter(Entity.evidence_source_id == fixture_data["other"].id)
        .first()
    )
    for suffix in (f"/{foreign.id}/timeline", f"/{foreign.id}/timeline/count"):
        assert client.get(_url(fixture_data, suffix)).status_code == 404
    unknown = uuid.uuid4()
    assert client.get(_url(fixture_data, f"/{unknown}/timeline")).status_code == 404
    assert client.get(_url(fixture_data, f"/{unknown}/timeline/count")).status_code == 404


def test_pagination_arguments_are_validated(client, fixture_data):
    entity_id = fixture_data["target"].id
    # limit=0 was accepted by both legacy endpoints and remains a useful way
    # for existing callers to request no rows without materializing a page.
    assert _ids(client.get(_url(fixture_data), params={"limit": 0})) == []
    assert _ids(
        client.get(_url(fixture_data, f"/{entity_id}/timeline"), params={"limit": 0})
    ) == []

    for params in ({"offset": -1}, {"limit": -1}, {"limit": 1001}):
        assert client.get(_url(fixture_data), params=params).status_code == 422
    for params in ({"offset": -1}, {"limit": -1}, {"limit": 501}):
        response = client.get(_url(fixture_data, f"/{entity_id}/timeline"), params=params)
        assert response.status_code == 422


def test_unknown_source_is_rejected_before_paging(client, fixture_data):
    case_id = fixture_data["case"].id
    missing = uuid.uuid4()
    base = f"/api/v1/cases/{case_id}/sources/{missing}/entities"
    assert client.get(base).status_code == 404
    assert client.get(f"{base}/count").status_code == 404
