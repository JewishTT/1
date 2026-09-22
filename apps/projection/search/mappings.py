"""Declarative search-projection mappings (FR-012, ADR-0004/0019).

Mappings are versioned, in-repo and reproducible: the same file produces the
same index config on every environment. Physical index ids are tenant-scoped;
queries go through a tenant alias so cross-tenant reads cannot happen.
"""

from __future__ import annotations

from typing import Any

INDEX_VERSION = "v1"

#: Canonical projected document kinds (search projector output).
DOC_KINDS: tuple[str, ...] = (
    "observations",
    "documents",
    "mentions",
    "candidates",
    "entities",
    "assertions",
    "findings",
)

#: Field templates shared by every kind; kind-specific fields are appended.
_COMMON_FIELDS: list[dict[str, Any]] = [
    {"name": "doc_id", "type": "text", "tokenizer": "raw", "fast": True},
    {"name": "tenant_id", "type": "text", "tokenizer": "raw", "fast": True},
    {"name": "kind", "type": "text", "tokenizer": "raw", "fast": True},
    {"name": "text", "type": "text", "tokenizer": "default", "record": "position"},
    {"name": "produced_at", "type": "datetime", "fast": True},
]

_KIND_FIELDS: dict[str, list[dict[str, Any]]] = {
    "observations": [
        {"name": "observation_id", "type": "text", "tokenizer": "raw", "fast": True},
        {"name": "raw_ref", "type": "text", "tokenizer": "raw"},
        {"name": "content_hash", "type": "text", "tokenizer": "raw", "fast": True},
        {"name": "status", "type": "text", "tokenizer": "raw", "fast": True},
    ],
    "documents": [
        {"name": "observation_id", "type": "text", "tokenizer": "raw", "fast": True},
        {"name": "uri", "type": "text", "tokenizer": "raw", "fast": True},
        {"name": "content_type", "type": "text", "tokenizer": "raw"},
    ],
    "mentions": [
        {"name": "mention_id", "type": "text", "tokenizer": "raw", "fast": True},
        {"name": "observation_id", "type": "text", "tokenizer": "raw", "fast": True},
        {"name": "mention_kind", "type": "text", "tokenizer": "raw", "fast": True},
        {"name": "value", "type": "text", "tokenizer": "default"},
    ],
    "candidates": [
        {"name": "candidate_id", "type": "text", "tokenizer": "raw", "fast": True},
        {"name": "observation_id", "type": "text", "tokenizer": "raw", "fast": True},
        {"name": "value", "type": "text", "tokenizer": "default"},
    ],
    "entities": [
        {"name": "entity_id", "type": "text", "tokenizer": "raw", "fast": True},
        {"name": "name", "type": "text", "tokenizer": "default"},
        {"name": "aliases", "type": "text", "tokenizer": "default"},
    ],
    "assertions": [
        {"name": "assertion_id", "type": "text", "tokenizer": "raw", "fast": True},
        {"name": "entity_id", "type": "text", "tokenizer": "raw", "fast": True},
        {"name": "predicate", "type": "text", "tokenizer": "raw", "fast": True},
        {"name": "object_value", "type": "text", "tokenizer": "default"},
    ],
    "findings": [
        {"name": "finding_id", "type": "text", "tokenizer": "raw", "fast": True},
        {"name": "entity_id", "type": "text", "tokenizer": "raw", "fast": True},
    ],
}


def physical_index_name(kind: str, tenant: str) -> str:
    """Tenant-scoped physical index id (fail-closed isolation)."""
    if kind not in DOC_KINDS:
        raise ValueError(f"unknown document kind: {kind}")
    if not tenant:
        raise ValueError("tenant is required for index naming")
    return f"{kind}-{INDEX_VERSION}-{tenant}"


def alias_name(kind: str, tenant: str) -> str:
    """Tenant alias queries resolve through (ADR-0004)."""
    if kind not in DOC_KINDS:
        raise ValueError(f"unknown document kind: {kind}")
    if not tenant:
        raise ValueError("tenant is required for alias naming")
    return f"{kind}-{tenant}"


def doc_mapping(kind: str) -> dict[str, Any]:
    """Full doc mapping for a document kind (deterministic ordering)."""
    if kind not in DOC_KINDS:
        raise ValueError(f"unknown document kind: {kind}")
    fields = list(_COMMON_FIELDS) + list(_KIND_FIELDS.get(kind, []))
    fields.sort(key=lambda field: field["name"])
    return {
        "field_mappings": fields,
        "mode": "dynamic",
        "timestamp_field": "produced_at",
    }


def index_config(
    kind: str,
    *,
    tenant: str,
    kafka_topic: str = "search.projected",
    s3_bucket: str = "quickwit-indexes",
    bootstrap_servers: str = "kafka:9092",
) -> dict[str, Any]:
    """Quickwit index config: Kafka-native ingest, index on object storage.

    This is the declarative artifact the deployment applies (FR-008/FR-012):
    ingestion is Kafka-native, storage is object-storage-first, and the index
    remains a rebuildable projection (Constitution III).
    """
    if kind not in DOC_KINDS:
        raise ValueError(f"unknown document kind: {kind}")
    physical = physical_index_name(kind, tenant)
    return {
        "version": INDEX_VERSION,
        "index_id": physical,
        "index_uri": f"s3://{s3_bucket}/{physical}",
        "doc_mapping": doc_mapping(kind),
        "indexing_settings": {
            "commit_timeout_secs": 30,
            "resources": {"heap_size": "512M"},
        },
        "search_settings": {"default_search_fields": ["text", "value", "name"]},
        "retention": {"retention_period": "90 days"},
        "sources": [
            {
                "source_id": f"kafka-{physical}",
                "source_type": "kafka",
                "params": {
                    "topic": kafka_topic,
                    "client_params": {
                        "bootstrap.servers": bootstrap_servers,
                        "group.id": f"quickwit-{physical}",
                    },
                    "enable_backfill_mode": True,
                },
                "transform": [
                    {
                        "params": {
                            "type": "json",
                            "filter": (
                                f'tenant_id == "{tenant}" && kind == "{kind}"'
                            ),
                        }
                    }
                ],
            }
        ],
    }


def all_index_configs(
    *,
    tenant: str,
    kafka_topic: str = "search.projected",
    s3_bucket: str = "quickwit-indexes",
    bootstrap_servers: str = "kafka:9092",
) -> list[dict[str, Any]]:
    """Every index config for one tenant — the deployment applies this list."""
    return [
        index_config(
            kind,
            tenant=tenant,
            kafka_topic=kafka_topic,
            s3_bucket=s3_bucket,
            bootstrap_servers=bootstrap_servers,
        )
        for kind in DOC_KINDS
    ]
