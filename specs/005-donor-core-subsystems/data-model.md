# Data Model: Donor Core Subsystems

**Date**: 2026-09-08 | **Feature**: [spec.md](spec.md)

## 1. Knowledge Statement (canonical, FollowTheMoney-pattern)

The single model parsers, interpolation, admission and resolution share. Lives in
`apps/shared/domain/`.

| Field | Type | Notes |
|-------|------|-------|
| `statement_id` | str | `ST-` prefixed, deterministic per extraction. |
| `entity_id` | str | canonical Entity id (`E-` prefixed after resolution; candidate-bound before). |
| `schema_name` | str | registry key; unknown → `UnknownSchemaError`. |
| `properties` | dict[str, list[Property]] | typed, schema-validated. |
| `dataset_id` | str | provenance boundary (required, FR-001). |
| `original_value` | str | immutable original (I-1). |
| `extraction_version` | str | required. |
| `valid_from` / `valid_until` | datetime \| None | temporal validity; both None = no claim. |
| `first_seen` / `last_seen` | datetime | observation window. |
| `provenance` | dict | producer, observation_id, tenant_id. |
| `claimed` | bool | default True (I-3: assertion ≠ truth). |

State/validation: missing `dataset_id`/`extraction_version`/`original_value` →
`StatementProvenanceError` (existing invariant); `schema_name` must resolve in the schema registry.

## 2. Entity / Property / Schema Registry

| Model | Fields |
|-------|--------|
| `Entity` | `entity_id`, `schema_name`, `properties: dict[str, list[Property]]`, `dataset_id`, `first_seen/last_seen`. |
| `Property` | `name`, `type` (registry-validated), `value`, `original_value`, `confidence?`. |
| `SchemaRegistry` | `schemas: dict[schema_name, SchemaDefinition]`; `register()`, `resolve()`, `validate_entity()`. |

Relationships: Entity is referenced by Statement (`entity_id`); Statement groups Properties;
SchemaRegistry validates both (spec FR-004).

## 3. Resolution Candidate (OpenOSINT-pattern, meets spec FR-006)

| Field | Type | Notes |
|-------|------|-------|
| `pair_key` | str | deterministic (sorted entity id tuple). |
| `candidate_a` / `candidate_b` | str | entity/candidate ids. |
| `score_vector` | dict[str, float] | per-signal scores from resolver. |
| `collective_score` | float | from collective layer. |
| `evidence_links` | list[EvidenceLink] | existing evidence linking. |
| `review_state` | enum | `open \| accepted \| rejected \| reversed`. |
| `decision_revision` | list[ReviewRecord] | append-only decisions. |

Merge is recorded as a **resolution link** (`ResolutionRecord`: `merged_pair_key`,
`canonical_entity_id`, `retained_entity_ids`, timestamps) — original entities are never deleted
(`reverse()` creates a new record, does not delete). Both create `resolution.*` envelopes.

## 4. Evidence Manifest (NetForensicAI-pattern, spec FR-009)

Immutable chain, append-only:

```
Finding (kind, value, offset, meta)
  └─ Evidence (evidence_id, finding refs, observation_id, raw_sha256)
       └─ Observation (observation_id, created_at, tenant_id)
            └─ Raw Object (key s3://knowledge/raw/{prefix}/{sha256})
```

`EvidenceManifest` bundles findings for one observation; emits `evidence.manifest_created`
(payload carries refs + sha256 only, never raw blobs — I-5).

## 5. Acquisition Connector Module (SpiderFoot-pattern, spec FR-010)

| Field / Method | Notes |
|----------------|-------|
| `name`, `capabilities()`, `content_types` | registration/declaration. |
| `run(task) -> events` | emits events onto the task's shared channel; bounded thread pool. |
| `stop()` | prompt clean shutdown; fault isolated per-module (quarantine). |
| `normalize_event(ev)` | collapses values via `shared/donor/target.py` to canonical targets. |

## 6. Investigation Monitor (investigator-pattern)

Additions to `Investigation`:

| Field | Notes |
|-------|-------|
| `monitor: dict[counter, int]` | `items_examined`, `evidence_ingested`, `candidates_resolved`, `findings_created`. |
| `update_counter(name, delta)` | atomic, per-investigation. |
| terminal-state guard | late events after COMPLETED are parked to dead-letter (`governance.quarantined`), never mutate state. |
| `snapshot()` | persisted final summary on close (I-12 replay). |

## 7. Review Model & Timeline (UI, vitni-pattern)

Pure logic in `apps/webapp/src/lib/donor/review.ts`:

| Model | Fields / Behavior |
|-------|-------------------|
| `DerivedReviewAssertion` | base reviewable item + `subjectLabel`, `sourceTitle`, `supportingSourceCount`, `corroborationCount`, `evidenceStatus: none\|single\|multiple`, `conflictStatus: none\|conflict`, `valueSummary`. |
| `ReviewFilters` | `query`, `reviewState: all\|<state>`, `evidence: all\|none\|weak`, `confidence`, `sort: unreviewed_first\|newest\|oldest\|weakest_evidence`. |
| `DerivedNodeReviewStatus` | per-subject `reviewTone: clear\|needs_review\|conflict`, `evidenceTone: supported\|gap`. |
| Functions | `buildDerivedReviewAssertions`, `filterReviewAssertions`, `buildNodeReviewStatusMap`, `getAdjacentReviewAssertionId`, `getNextUnreviewedAssertionId`. |

Deterministic (stableSerialize for corroboration/conflict grouping); unknown review
states fall through to safe defaults (spec US6 scenarios).

## State transitions

```
Investigation: DRAFT → PLANNING → RUNNING ⇄ PAUSED → COMPLETED → ARCHIVED
Resolution Candidate: open → accepted | rejected; accepted → reversed (append-only)
Parser Registry: probe(can_parse) → register/parse → Finding|quarantine
Connector Module: registered → running → stopped | faulted → quarantine
```