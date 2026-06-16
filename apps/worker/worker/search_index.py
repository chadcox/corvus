from __future__ import annotations

import hashlib
import re
from typing import Any
from uuid import UUID

from worker.config import settings

try:
    from opensearchpy import OpenSearch, helpers
except ImportError:  # pragma: no cover - dependency exists in container builds
    OpenSearch = None  # type: ignore[assignment]
    helpers = None  # type: ignore[assignment]


TIMELINE_INDEX = "timeline"
FILESYSTEM_INDEX = "filesystem"
ENTITIES_INDEX = "entities"

_HASH_KEYS = ("sha256", "SHA256", "Hash", "hash", "MD5", "md5", "SHA1", "sha1")
_TEXT_KEYS = (
    "Message",
    "Description",
    "CommandLine",
    "ParentCommandLine",
    "Image",
    "NewProcessName",
    "TargetFilename",
    "ObjectName",
    "FullPath",
    "SourceFile",
    "DestinationFile",
    "url",
    "title",
    "host",
    "domain",
    "UserName",
    "TargetUserName",
    "Computer",
    "Channel",
    "Provider",
)
_IP_RE = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")


def enabled() -> bool:
    return settings.search_backend.lower() == "opensearch" and OpenSearch is not None


def index_name(kind: str) -> str:
    return f"{settings.opensearch_index_prefix}-{kind}-v1"


def client() -> OpenSearch | None:
    if not enabled():
        return None
    return OpenSearch(
        hosts=[settings.opensearch_url],
        use_ssl=settings.opensearch_url.startswith("https://"),
        verify_certs=False,
        timeout=30,
        max_retries=2,
        retry_on_timeout=True,
    )


def _settings() -> dict[str, Any]:
    return {
        "number_of_shards": 1,
        "number_of_replicas": 0,
        "refresh_interval": "10s",
        "analysis": {
            "analyzer": {
                "path_analyzer": {"tokenizer": "path_hierarchy"},
                "lower_keyword": {"tokenizer": "keyword", "filter": ["lowercase"]},
            },
            "normalizer": {
                "lowercase_normalizer": {"type": "custom", "filter": ["lowercase"]}
            },
        },
    }


def _timeline_mapping() -> dict[str, Any]:
    return {
        "dynamic": "true",
        "properties": {
            "doc_type": {"type": "keyword"},
            "case_id": {"type": "keyword"},
            "evidence_source_id": {"type": "keyword"},
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
            "all_text": {"type": "text"},
        },
    }


def _filesystem_mapping() -> dict[str, Any]:
    return {
        "properties": {
            "doc_type": {"type": "keyword"},
            "case_id": {"type": "keyword"},
            "evidence_source_id": {"type": "keyword"},
            "node_id": {"type": "keyword"},
            "full_path": {
                "type": "wildcard",
                "fields": {"path": {"type": "text", "analyzer": "path_analyzer"}},
            },
            "name": {"type": "text", "fields": {"wildcard": {"type": "wildcard"}}},
            "size": {"type": "long"},
            "is_directory": {"type": "boolean"},
            "is_deleted": {"type": "boolean"},
            "all_text": {"type": "text"},
        }
    }


def _entities_mapping() -> dict[str, Any]:
    return {
        "dynamic": "true",
        "properties": {
            "doc_type": {"type": "keyword"},
            "case_id": {"type": "keyword"},
            "evidence_source_id": {"type": "keyword"},
            "entity_id": {"type": "keyword"},
            "entity_type": {"type": "keyword"},
            "display_name": {
                "type": "text",
                "fields": {"keyword": {"type": "keyword"}, "wildcard": {"type": "wildcard"}},
            },
            "all_text": {"type": "text"},
        },
    }


def ensure_indices(os: OpenSearch) -> None:
    mappings = {
        TIMELINE_INDEX: _timeline_mapping(),
        FILESYSTEM_INDEX: _filesystem_mapping(),
        ENTITIES_INDEX: _entities_mapping(),
    }
    for kind, mapping in mappings.items():
        name = index_name(kind)
        if not os.indices.exists(index=name):
            os.indices.create(index=name, body={"settings": _settings(), "mappings": mapping})


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _hash_fields(data: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key in _HASH_KEYS:
        value = data.get(key)
        if not value:
            continue
        lowered = str(value).lower()
        if len(lowered) == 64:
            out["hash_sha256"] = lowered
        elif len(lowered) == 40:
            out["hash_sha1"] = lowered
        elif len(lowered) == 32:
            out["hash_md5"] = lowered
    return out


def _clean_ip(value: str | None) -> str | None:
    if not value:
        return None
    match = _IP_RE.search(value)
    if not match:
        return None
    parts = match.group(0).split(".")
    if all(0 <= int(part) <= 255 for part in parts):
        return match.group(0)
    return None


def _text_blob(values: list[Any]) -> str:
    parts = [str(value) for value in values if value not in (None, "")]
    return " ".join(parts)[:20000]


def timeline_doc(event: dict[str, Any], *, case_id: UUID, source_id: UUID) -> dict[str, Any]:
    data = event.get("data") or {}
    sigma_hits = event.get("sigma_hits") or []
    command_line = data.get("CommandLine") or data.get("ParentCommandLine")
    url = data.get("url") or data.get("URL")
    host = data.get("host") or data.get("Host") or data.get("Computer")
    user = data.get("UserName") or data.get("TargetUserName") or data.get("SubjectUserName")
    domain = data.get("domain") or data.get("Domain")
    registry_key = data.get("KeyPath") or data.get("RegistryKey") or data.get("key_path")
    registry_value = data.get("Value") or data.get("ValueData") or data.get("registry_value")
    message = data.get("Message") or data.get("Description")
    text_values = [event.get("summary"), event.get("event_type"), event.get("artifact_type")]
    text_values.extend(data.get(key) for key in _TEXT_KEYS)
    doc = {
        "doc_type": TIMELINE_INDEX,
        "case_id": str(case_id),
        "evidence_source_id": str(source_id),
        "event_id": str(event["id"]),
        "timestamp_utc": _iso(event.get("timestamp_utc")),
        "event_type": str(event.get("event_type") or ""),
        "artifact_type": event.get("artifact_type"),
        "summary": event.get("summary"),
        "original_source": event.get("original_source"),
        "message": message,
        "command_line": command_line,
        "url": url,
        "domain": str(domain).lower() if domain else None,
        "ip": _clean_ip(str(data.get("IpAddress") or data.get("SourceIp") or "")),
        "registry_key": registry_key,
        "registry_value": registry_value,
        "user": str(user).lower() if user else None,
        "host": str(host).lower() if host else None,
        "entity_refs": event.get("entity_refs") or [],
        "detection_rule_ids": [hit.get("rule_id") for hit in sigma_hits if hit.get("rule_id")],
        "all_text": _text_blob(text_values),
    }
    doc.update(_hash_fields(data))
    return {k: v for k, v in doc.items() if v not in (None, "")}


def filesystem_doc(node: dict[str, Any], *, case_id: UUID, source_id: UUID) -> dict[str, Any]:
    return {
        "doc_type": FILESYSTEM_INDEX,
        "case_id": str(case_id),
        "evidence_source_id": str(source_id),
        "node_id": str(node["id"]),
        "full_path": node.get("full_path"),
        "name": node.get("name"),
        "size": node.get("size"),
        "is_directory": bool(node.get("is_directory")),
        "is_deleted": bool(node.get("is_deleted", False)),
        "all_text": _text_blob([node.get("full_path"), node.get("name")]),
    }


def entity_doc(entity: dict[str, Any], *, case_id: UUID, source_id: UUID) -> dict[str, Any]:
    attributes = entity.get("attributes") or {}
    return {
        "doc_type": ENTITIES_INDEX,
        "case_id": str(case_id),
        "evidence_source_id": str(source_id),
        "entity_id": str(entity["id"]),
        "entity_type": entity.get("entity_type"),
        "display_name": entity.get("display_name"),
        "all_text": _text_blob([entity.get("entity_type"), entity.get("display_name"), attributes]),
    }


def _bulk(os: OpenSearch, actions: list[dict[str, Any]]) -> None:
    if actions and helpers is not None:
        helpers.bulk(os, actions, chunk_size=2000, request_timeout=60)


def index_source(
    *,
    case_id: UUID,
    source_id: UUID,
    events: list[dict[str, Any]],
    filesystem_nodes: list[dict[str, Any]],
    entities: list[dict[str, Any]],
) -> None:
    os = client()
    if os is None:
        return
    ensure_indices(os)
    actions: list[dict[str, Any]] = []
    for event in events:
        actions.append(
            {
                "_op_type": "index",
                "_index": index_name(TIMELINE_INDEX),
                "_id": f"timeline:{event['id']}",
                "_source": timeline_doc(event, case_id=case_id, source_id=source_id),
            }
        )
    for node in filesystem_nodes:
        actions.append(
            {
                "_op_type": "index",
                "_index": index_name(FILESYSTEM_INDEX),
                "_id": f"filesystem:{node['id']}",
                "_source": filesystem_doc(node, case_id=case_id, source_id=source_id),
            }
        )
    for entity in entities:
        actions.append(
            {
                "_op_type": "index",
                "_index": index_name(ENTITIES_INDEX),
                "_id": f"entity:{entity['id']}",
                "_source": entity_doc(entity, case_id=case_id, source_id=source_id),
            }
        )
    _bulk(os, actions)


def delete_source_docs(source_id: UUID) -> None:
    os = client()
    if os is None:
        return
    for kind in (TIMELINE_INDEX, FILESYSTEM_INDEX, ENTITIES_INDEX):
        name = index_name(kind)
        if not os.indices.exists(index=name):
            continue
        os.delete_by_query(
            index=name,
            body={"query": {"term": {"evidence_source_id": str(source_id)}}},
            conflicts="proceed",
            refresh=True,
            request_timeout=60,
        )
