# ADR-0004: OpenSearch as search/indexing backend

Status: Accepted
Date: 2026-09-07

## Context

Projected, immutable observations and entities must be searchable across many
fields (free text, normalized forms, transliteration variants, entities) with
per-tenant isolation and rebuildable indexes (I-12).

## Decision

Use **OpenSearch** as the search/indexing backend.

## Rationale

- Full-text + faceted + aggregations on projected observations/entities.
- Per-tenant index aliases (T061) give fail-closed isolation.
- Rebuildable from Kafka event history (I-12): a search projection can be
  re-materialized without cross-writes.
- Mature operational tooling and multi-region deployment (FR-030).
- Chosen over Elasticsearch for the OSS license posture per governance.

## Consequences

- Search index is a derived projection, never the source of truth.
- Index aliases + mapping must be versioned and GitOps-managed.
- Requires careful index lifecycle (refresh, rollover, replica).
