# Data Model: Donor Code Integration

**Date**: 2026-09-08 | **Feature**: [spec.md](spec.md)

## Scope

This document describes the three adapted donor-derived entities introduced by
track 003. Each entity carries an **attribution header** in its implementing
module (source repo, license, commit-ish, what-changed) per **FR-001**.

## 1. CorrelationNode [D] `pg` + `graph`

From OpenOSINT `openosint/correlation.py` → adapted as
`apps/shared/donor/correlation_graph.py`.

| field | type | notes |
|---|---|---|
| `node_key` | str | deterministic id (e.g. `cand:ENT-2001`). |
| `kind` | CorrelationKind | enum: `candidate`, `entity`, `value` (renamed from `EntityType`). |
| `label` | str | display label. |
| `observations` | set[str] | set of observation ids (renamed from `source_tools`). |
| `candidates` | list[str] | candidate ids this node aggregates. |

**Adaptation notes**: `EntityType`/`Entity`/`Relationship` → `CorrelationKind`/`CorrelationNode`/`CorrelationLink`; `source_tools` → `observations` (set of observation refs); `EntityGraph` → `CorrelationGraph`.

## 2. CorrelationLink [D] `pg` + `graph`

From OpenOSINT correlation edge → adapted in same module.

| field | type | notes |
|---|---|---|
| `link_key` | str | deterministic id (sorted pair of node keys + kind). |
| `source` / `target` | str | node keys. |
| `kind` | str | e.g. `possible_match`. |
| `raw_pair_score` | float | blocking/pairwise score. |
| `collective_score` | float | propagated score (nullable). |
| `reasons` | list[str] | blocking keys used. |
| `observations` | set[str] | edge-level observation refs. |

## 3. CorrelationGraph [D] `graph` (projection only)

In-memory graph built from `CorrelationLink` rows. Supports:
`add_node`, `add_link`, `merge`, `neighbors`, `to_dict`, `to_json`,
`to_graphml`, `to_mermaid`, `summary` (deterministic node/edge counts).

**Invariant**: graph is a **projection artifact** (I-4); the durable store is
`CorrelationEdge` in PostgreSQL (see `specs/002-donor-pattern-integration/data-model.md`).

## 4. Statement [D] `pg` + `os`

From FollowTheMoney `ftm/statement/statement.py` → adapted as
`apps/shared/donor/statement.py`.

| field | type | notes |
|---|---|---|
| `statement_id` | str | `ST-` prefixed, deterministic per extraction. |
| `entity_id` | str | canonical Entity id. |
| `schema_name` | str | registry key. |
| `dataset_id` | str | provenance boundary (required, FR-001). |
| `original_value` | str | immutable original (I-1). |
| `extraction_version` | str | required. |
| `lang` | str | optional language hint. |
| `ext` | str | optional external id suffix. |
| `valid_from` / `valid_until` | datetime | optional temporal validity. |
| `first_seen` / `last_seen` | datetime | observation window. |
| `provenance` | dict | producer, observation_id, tenant_id. |

**Key method**: `make_key()` — deterministic sha1 over
`dataset_id.entity_id.schema_name.original_value[@lang][.ext]`.

**Validation**: `dataset_id`, `extraction_version`, `original_value` required
(StatementProvenanceError if missing).

## 5. EvidenceItem [D] `s3` + `pg`

From NetForensicAI `netforensicai/core/evidence.py` → adapted as
`apps/shared/donor/evidence.py`.

| field | type | notes |
|---|---|---|
| `evidence_id` | str | `EV-` prefixed, auto-incrementing. |
| `investigation_id` | str | case-scoped (renamed from `case`). |
| `observation_id` | str | anchor to immutable observation (I-1). |
| `stored_file_path` | str | content-addressed path under `s3://evidence/...`. |
| `content_hash` | str | streaming SHA-256 of stored copy. |
| `manifest` | dict | metadata + refs, persisted as `manifest.json`. |
| `created_at` | datetime | timestamp. |

**EvidenceVault** methods: `add(investigation_id, source_path)` → ingest +
manifest; `load(evidence_id)` → returns EvidenceItem if hash verifies;
`list(investigation_id)` → items (skips corrupt manifest); `verify(evidence_id)`
→ bool (streaming sha256 check).

**Invariant**: stored copy is **read-only**; tampering detected by hash mismatch.

## Relationships summary

```text
Statement 1—1 Assertion (extends)
Statement dataset_id → Observation dataset_id (provenance boundary)
CorrelationNode ← CorrelationLink (source/target, non-merging)
CorrelationLink observations → Observation.observation_id
EvidenceItem observation_id → Observation.observation_id
EvidenceItem investigation_id → Investigation.investigation_id
```

## Validation rules

- **FR-001**: Every adapted module carries an attribution header.
- **FR-002**: `dataset_id` + `extraction_version` + `original_value` required on
  every Statement.
- **FR-004**: `CorrelationEdge` never auto-merges; merge only via admitted
  assertion.
- **FR-009**: `EvidenceVault` stored copy is read-only; hash verified on every
  load.
