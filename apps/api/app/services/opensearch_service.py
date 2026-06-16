from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Entity, FilesystemNode, TimelineEvent
from ff_core.schemas import EntityRead, FilesystemNodeRead, GlobalSearchResult, TimelineEventRead

try:
    from opensearchpy import OpenSearch, helpers
except ImportError:  # pragma: no cover - dependency exists in container builds
    OpenSearch = None  # type: ignore[assignment]
    helpers = None  # type: ignore[assignment]


TIMELINE_INDEX = "timeline"
FILESYSTEM_INDEX = "filesystem"
ENTITIES_INDEX = "entities"

HASH_RE = re.compile(r"^[a-fA-F0-9]{32}$|^[a-fA-F0-9]{40}$|^[a-fA-F0-9]{64}$")
IP_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")


def search_enabled() -> bool:
    return settings.search_backend.lower() == "opensearch" and OpenSearch is not None


def index_name(kind: str) -> str:
    return f"{settings.opensearch_index_prefix}-{kind}-v1"


def get_client() -> OpenSearch | None:
    if not search_enabled():
        return None
    return OpenSearch(
        hosts=[settings.opensearch_url],
        use_ssl=settings.opensearch_url.startswith("https://"),
        verify_certs=False,
        timeout=5,
        max_retries=1,
        retry_on_timeout=True,
    )


def ping() -> bool:
    client = get_client()
    if client is None:
        return False
    return bool(client.ping())


def _index_settings() -> dict[str, Any]:
    return {
        "number_of_shards": 1,
        "number_of_replicas": 0,
        "refresh_interval": "10s",
        "analysis": {
            "analyzer": {"path_analyzer": {"tokenizer": "path_hierarchy"}},
            "normalizer": {
                "lowercase_normalizer": {"type": "custom", "filter": ["lowercase"]}
            },
        },
    }


def _mappings(kind: str) -> dict[str, Any]:
    common = {
        "doc_type": {"type": "keyword"},
        "case_id": {"type": "keyword"},
        "evidence_source_id": {"type": "keyword"},
        "all_text": {"type": "text"},
    }
    if kind == TIMELINE_INDEX:
        common.update(
            {
                "event_id": {"type": "keyword"},
                "timestamp_utc": {"type": "date"},
                "event_type": {"type": "keyword"},
                "artifact_type": {"type": "keyword"},
                "summary": {"type": "text", "fields": {"wildcard": {"type": "wildcard"}}},
                "original_source": {
                    "type": "text",
                    "analyzer": "path_analyzer",
                    "fields": {"wildcard": {"type": "wildcard"}},
                },
                "message": {"type": "text"},
                "command_line": {"type": "text", "fields": {"wildcard": {"type": "wildcard"}}},
                "url": {"type": "wildcard"},
                "domain": {"type": "keyword", "normalizer": "lowercase_normalizer"},
                "ip": {"type": "ip"},
                "hash_sha256": {"type": "keyword"},
                "hash_sha1": {"type": "keyword"},
                "hash_md5": {"type": "keyword"},
                "registry_key": {"type": "wildcard"},
                "registry_value": {"type": "text", "fields": {"wildcard": {"type": "wildcard"}}},
                "user": {"type": "keyword", "normalizer": "lowercase_normalizer"},
                "host": {"type": "keyword", "normalizer": "lowercase_normalizer"},
                "entity_refs": {"type": "keyword"},
                "detection_rule_ids": {"type": "keyword"},
            }
        )
    elif kind == FILESYSTEM_INDEX:
        common.update(
            {
                "node_id": {"type": "keyword"},
                "full_path": {
                    "type": "wildcard",
                    "fields": {"path": {"type": "text", "analyzer": "path_analyzer"}},
                },
                "name": {"type": "text", "fields": {"wildcard": {"type": "wildcard"}}},
                "size": {"type": "long"},
                "is_directory": {"type": "boolean"},
                "is_deleted": {"type": "boolean"},
            }
        )
    elif kind == ENTITIES_INDEX:
        common.update(
            {
                "entity_id": {"type": "keyword"},
                "entity_type": {"type": "keyword"},
                "display_name": {
                    "type": "text",
                    "fields": {"keyword": {"type": "keyword"}, "wildcard": {"type": "wildcard"}},
                },
            }
        )
    return {"dynamic": "true", "properties": common}


def ensure_indices(client: OpenSearch) -> None:
    for kind in (TIMELINE_INDEX, FILESYSTEM_INDEX, ENTITIES_INDEX):
        name = index_name(kind)
        if not client.indices.exists(index=name):
            client.indices.create(
                index=name,
                body={"settings": _index_settings(), "mappings": _mappings(kind)},
            )


def delete_source_docs(source_id: UUID) -> None:
    client = get_client()
    if client is None:
        return
    for kind in (TIMELINE_INDEX, FILESYSTEM_INDEX, ENTITIES_INDEX):
        name = index_name(kind)
        if not client.indices.exists(index=name):
            continue
        client.delete_by_query(
            index=name,
            body={"query": {"term": {"evidence_source_id": str(source_id)}}},
            conflicts="proceed",
            refresh=True,
            request_timeout=60,
        )


def _text_blob(values: list[Any]) -> str:
    return " ".join(str(v) for v in values if v not in (None, ""))[:20000]


def _timeline_doc(row: TimelineEvent, case_id: UUID) -> dict[str, Any]:
    data = row.data or {}
    hits = row.sigma_hits or []
    doc = {
        "doc_type": TIMELINE_INDEX,
        "case_id": str(case_id),
        "evidence_source_id": str(row.evidence_source_id),
        "event_id": str(row.id),
        "timestamp_utc": row.timestamp_utc.isoformat(),
        "event_type": row.event_type,
        "artifact_type": row.artifact_type,
        "summary": row.summary,
        "original_source": row.original_source,
        "message": data.get("Message") or data.get("Description"),
        "command_line": data.get("CommandLine") or data.get("ParentCommandLine"),
        "url": data.get("url") or data.get("URL"),
        "domain": str(data.get("domain") or data.get("Domain") or "").lower() or None,
        "registry_key": data.get("KeyPath") or data.get("RegistryKey") or data.get("key_path"),
        "registry_value": data.get("Value") or data.get("ValueData") or data.get("registry_value"),
        "user": str(data.get("UserName") or data.get("TargetUserName") or "").lower() or None,
        "host": str(data.get("host") or data.get("Host") or data.get("Computer") or "").lower() or None,
        "entity_refs": row.entity_refs or [],
        "detection_rule_ids": [hit.get("rule_id") for hit in hits if hit.get("rule_id")],
        "all_text": _text_blob([row.summary, row.event_type, row.artifact_type, row.original_source, data]),
    }
    for key, target in (("sha256", "hash_sha256"), ("SHA256", "hash_sha256"), ("md5", "hash_md5"), ("MD5", "hash_md5"), ("sha1", "hash_sha1"), ("SHA1", "hash_sha1")):
        if data.get(key):
            doc[target] = str(data[key]).lower()
    return {k: v for k, v in doc.items() if v not in (None, "")}


def _filesystem_doc(row: FilesystemNode, case_id: UUID) -> dict[str, Any]:
    return {
        "doc_type": FILESYSTEM_INDEX,
        "case_id": str(case_id),
        "evidence_source_id": str(row.evidence_source_id),
        "node_id": str(row.id),
        "full_path": row.full_path,
        "name": row.name,
        "size": row.size,
        "is_directory": row.is_directory,
        "is_deleted": row.is_deleted,
        "all_text": _text_blob([row.full_path, row.name]),
    }


def _entity_doc(row: Entity, case_id: UUID) -> dict[str, Any]:
    return {
        "doc_type": ENTITIES_INDEX,
        "case_id": str(case_id),
        "evidence_source_id": str(row.evidence_source_id),
        "entity_id": str(row.id),
        "entity_type": row.entity_type,
        "display_name": row.display_name,
        "all_text": _text_blob([row.entity_type, row.display_name, row.attributes]),
    }


def reindex_source(db: Session, *, case_id: UUID, source_id: UUID) -> dict[str, int]:
    client = get_client()
    if client is None or helpers is None:
        return {"timeline": 0, "filesystem": 0, "entities": 0}
    ensure_indices(client)
    delete_source_docs(source_id)

    counts = {"timeline": 0, "filesystem": 0, "entities": 0}
    actions: list[dict[str, Any]] = []

    def flush() -> None:
        if actions:
            helpers.bulk(client, actions, chunk_size=2000, request_timeout=60)
            actions.clear()

    for row in db.query(TimelineEvent).filter(TimelineEvent.evidence_source_id == source_id).yield_per(2000):
        actions.append(
            {
                "_op_type": "index",
                "_index": index_name(TIMELINE_INDEX),
                "_id": f"timeline:{row.id}",
                "_source": _timeline_doc(row, case_id),
            }
        )
        counts["timeline"] += 1
        if len(actions) >= 2000:
            flush()
    for row in db.query(FilesystemNode).filter(FilesystemNode.evidence_source_id == source_id).yield_per(2000):
        actions.append(
            {
                "_op_type": "index",
                "_index": index_name(FILESYSTEM_INDEX),
                "_id": f"filesystem:{row.id}",
                "_source": _filesystem_doc(row, case_id),
            }
        )
        counts["filesystem"] += 1
        if len(actions) >= 2000:
            flush()
    for row in db.query(Entity).filter(Entity.evidence_source_id == source_id).yield_per(2000):
        actions.append(
            {
                "_op_type": "index",
                "_index": index_name(ENTITIES_INDEX),
                "_id": f"entity:{row.id}",
                "_source": _entity_doc(row, case_id),
            }
        )
        counts["entities"] += 1
        if len(actions) >= 2000:
            flush()
    flush()
    return counts


def _base_filters(case_id: UUID, source_id: UUID | None) -> list[dict]:
    filters: list[dict] = [{"term": {"case_id": str(case_id)}}]
    if source_id:
        filters.append({"term": {"evidence_source_id": str(source_id)}})
    return filters


def _query_for(q: str) -> dict:
    term = q.strip()
    lower = term.lower()
    exact_fields = [
        "event_id",
        "node_id",
        "entity_id",
        "hash_sha256",
        "hash_md5",
        "hash_sha1",
        "domain",
        "host",
        "user",
        "event_type",
        "artifact_type",
    ]
    should: list[dict] = [
        {
            "multi_match": {
                "query": term,
                "fields": [
                    "summary^4",
                    "display_name^4",
                    "full_path^4",
                    "name^3",
                    "message^3",
                    "command_line^3",
                    "url^3",
                    "registry_key^3",
                    "registry_value^2",
                    "all_text",
                ],
                "type": "best_fields",
                "operator": "and",
            }
        },
        {
            "simple_query_string": {
                "query": term,
                "fields": ["summary^3", "all_text", "full_path", "url", "registry_key"],
                "default_operator": "and",
            }
        },
    ]
    should.extend({"term": {field: lower}} for field in exact_fields)
    if HASH_RE.match(term):
        should.extend(
            [
                {"term": {"hash_sha256": lower}},
                {"term": {"hash_sha1": lower}},
                {"term": {"hash_md5": lower}},
            ]
        )
    if IP_RE.match(term):
        should.append({"term": {"ip": term}})
    if "/" in term or "\\" in term or ":" in term:
        should.extend(
            [
                {"wildcard": {"full_path": {"value": f"*{lower}*", "case_insensitive": True}}},
                {"wildcard": {"original_source": {"value": f"*{lower}*", "case_insensitive": True}}},
                {"wildcard": {"registry_key": {"value": f"*{lower}*", "case_insensitive": True}}},
            ]
        )
    if "." in term:
        should.extend(
            [
                {"term": {"domain": lower}},
                {"wildcard": {"url": {"value": f"*{lower}*", "case_insensitive": True}}},
            ]
        )
    return {"bool": {"should": should, "minimum_should_match": 1}}


def _ordered_by_ids(rows: Iterable, ids: list[str]) -> list:
    order = {value: idx for idx, value in enumerate(ids)}
    return sorted(rows, key=lambda row: order.get(str(row.id), len(order)))


def opensearch_global_search(
    db: Session,
    *,
    case_id: UUID,
    source_id: UUID,
    q: str,
    limit: int,
) -> GlobalSearchResult | None:
    client = get_client()
    if client is None:
        return None
    index_names = [index_name(TIMELINE_INDEX), index_name(FILESYSTEM_INDEX), index_name(ENTITIES_INDEX)]
    if not any(client.indices.exists(index=name) for name in index_names):
        return None

    query = {
        "bool": {
            "filter": _base_filters(case_id, source_id),
            "must": [_query_for(q)],
        }
    }
    try:
        response = client.search(
            index=index_names,
            body={
                "query": query,
                "size": limit * 3,
                "_source": ["doc_type", "event_id", "node_id", "entity_id"],
                "sort": [{"_score": "desc"}, {"timestamp_utc": {"order": "asc", "unmapped_type": "date"}}],
            },
            ignore_unavailable=True,
        )
    except Exception:
        return None

    timeline_ids: list[str] = []
    filesystem_ids: list[str] = []
    entity_ids: list[str] = []
    for hit in response.get("hits", {}).get("hits", []):
        source = hit.get("_source") or {}
        doc_type = source.get("doc_type")
        if doc_type == TIMELINE_INDEX and source.get("event_id"):
            timeline_ids.append(source["event_id"])
        elif doc_type == FILESYSTEM_INDEX and source.get("node_id"):
            filesystem_ids.append(source["node_id"])
        elif doc_type == ENTITIES_INDEX and source.get("entity_id"):
            entity_ids.append(source["entity_id"])

    timeline_ids = timeline_ids[:limit]
    filesystem_ids = filesystem_ids[:limit]
    entity_ids = entity_ids[:limit]

    timeline = []
    if timeline_ids:
        rows = (
            db.query(TimelineEvent)
            .filter(
                TimelineEvent.evidence_source_id == source_id,
                TimelineEvent.id.in_([UUID(value) for value in timeline_ids]),
            )
            .all()
        )
        timeline = _ordered_by_ids(rows, timeline_ids)

    filesystem = []
    if filesystem_ids:
        rows = (
            db.query(FilesystemNode)
            .filter(
                FilesystemNode.evidence_source_id == source_id,
                FilesystemNode.id.in_([UUID(value) for value in filesystem_ids]),
            )
            .all()
        )
        filesystem = _ordered_by_ids(rows, filesystem_ids)

    entities = []
    if entity_ids:
        rows = (
            db.query(Entity)
            .filter(
                Entity.evidence_source_id == source_id,
                Entity.id.in_([UUID(value) for value in entity_ids]),
            )
            .all()
        )
        entities = _ordered_by_ids(rows, entity_ids)

    return GlobalSearchResult(
        query=q,
        timeline=[TimelineEventRead.model_validate(row) for row in timeline],
        filesystem=[FilesystemNodeRead.model_validate(row) for row in filesystem],
        entities=[EntityRead.model_validate(row) for row in entities],
        total=len(timeline) + len(filesystem) + len(entities),
    )
