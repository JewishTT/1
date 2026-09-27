# Implementation Plan: World Substrate Closure

**Feature**: `018-world-substrate` · **Spec**: `spec.md` · **Status**: planned 2026-09-27

## Summary

The resolution algorithm is closed and correct. This plan makes its state durable, separates the claim
lifecycle, supplies the missing regime input, closes acquisition at the bottom of the chain behind a
stream-agnostic seam, and turns the golden path into working functionality that runs over real data.

Governing constraint, per the architect: **optimise for the efficiency of everything computed downstream**.
That decides schema shape (read paths first), seam shape (one contract, no per-stream shortcuts), and the
corpus (record the output of working code, do not add a parallel test suite).

## Technical Context

**What exists and is reused, not rewritten**:
- `apps/shared/semantic/resolution.py` — `MentionResolver`, `ResolutionScope`/`EntityAnchor`, `ResolutionDecision` (`RES-`), `logical_entity_ref` (`ENT-`). Stateless, terminating, alias-aware after the fix.
- `apps/shared/domain/capture.py` — `Capture` (`CAP-`), `CaptureContractError`, `payload_key`, `InMemoryCaptureRegistry`. Content-addressed, tenant-scoped, `UNBATCHED_INGEST_BATCH` sentinel.
- `apps/shared/domain/evidence_lineage.py` — `EvidenceGraph.forward()` starts at any node; `backward()` unchanged.
- `apps/shared/semantic/validation.py` — `LayeredValidator`, `decide_materialisation`, `MaterialisationDecision`.
- `apps/shared/domain/relation_candidate.py` — `RelationCandidate` (`CAND-`/`CNDR-`), `to_claim`.
- `apps/control-plane/semantic_path/execution.py` — 13-stage orchestrator, `golden_request()`, `run_golden_path()`.
- `apps/control-plane/db/schema.py` — 49 tables, forward-only migrations to `018_semantic_fabric`.

**What is missing, precisely**:
- `entities` (`entity_id`, `entity_type`, `canonical_name`) has no anchor and no resolution reference. `entity_versions` chains versions but not identity.
- `regime_id` is in no table.
- `apps/acquisition/cc_extract.py::CaptureObservation` = `url`, `observed_at` (crawl-index time), `status`, `digest`, `crawl`, `subset`, `warc_filename`, `offset`, `length`, `warc_record_id`. **No `fetched_at`.** Dedup key is `(digest, observed_at)`.
- `RelationClaimService` lives in `apps/projection/graph/relation_store.py:210`.
- The cue-keyed org rule lives inside `semantic_path/execution.py`, not in the extraction package.

**Migration numbering**: this feature's migration is `019`, since `018_semantic_fabric` exists. Feature
numbering and migration numbering are independent namespaces and the collision is intentional-looking but
harmless; say so in the migration header.

## Decisions

- **D1 — `entity_identity` and `resolution_decision` are separate tables, indexed for the two read paths.**
  `entity_identity(entity_id PK, tenant_id, anchor_mention_id, anchor_observation_id, anchor_capture_id, created_by_resolution)` with UNIQUE on `(tenant_id, anchor_mention_id)` — the hot path during resolution is "does this mention already anchor an entity?", and uniqueness is what makes the anchor write-once structurally rather than by convention. Plus index on `(tenant_id, entity_id)` for reconstruction. `resolution_decision(resolution_decision_id PK …)` append-only, index on `(tenant_id, entity_ref, decided_at)` for ordered history.
- **D2 — `CaptureTimeBasis` is an enum on the record, not a nullable column.** `FETCH`, `INDEX_OBSERVATION`, `PUBLICATION`, `DERIVED`, `ABSENT`. A null `fetched_at` cannot distinguish "unknown" from "not yet written"; the basis can.
- **D3 — The claim lifecycle splits into `build` / `validate` / `admit` over one material value.** `RelationClaimMaterial` is the unadmitted, self-consistent value carrying its own derived ids. `LayeredValidator` accepts material. Only `admit` commits. `to_claim()` is retained as a deprecated composition of the three so no caller breaks, and marked as such.
- **D4 — The acquisition seam is a `StreamAdapter` protocol producing `Capture` records, plus a `DataStream` registry row that states the stream's temporality.** A stream that cannot state which axes it supplies is not registrable (FR-026). Common Crawl becomes its first adapter; one further non-API stream is attached to exercise the seam (FR-027).
- **D5 — The corpus is data plus a runner, living beside the code, and the runner is also the demonstration.** No test directory. It runs the real path over real sentences and writes the full trace; comparing two runs is the invariance check (FR-021).

## Project Structure

```
apps/shared/domain/
├── capture.py                  (exists) + time basis
├── entity_identity.py          NEW  EntityIdentity, write-once anchor, AnchorConflict
└── relation_claim_material.py  NEW  unadmitted material + build/validate/admit

apps/shared/semantic/
├── resolution.py               (exists) + decision serialisation
└── regime_store.py             NEW  durable regime substrate

apps/acquisition/
├── stream.py                   NEW  StreamAdapter protocol, DataStream registry
├── adapters/
│   ├── common_crawl.py         NEW  first adapter (moves cc_extract's shape onto the seam)
│   └── <second stream>         NEW  exercises the seam (FR-027)
└── cc_extract.py               (existing; adapted, not rewritten)

apps/control-plane/db/
├── schema.py                   + entity_identity, resolution_decision, semantic_regime,
│                                captures, ingest_batches, data_stream
└── migrations/versions/019_world_substrate.py   NEW

apps/control-plane/semantic_path/
├── execution.py                13 stages; regime + capture + lifecycle wiring
└── corpus.py                   NEW  deterministic corpus: cases, runner, invariance
```

## Complexity Tracking

| Component | Risk | Mitigation |
|---|---|---|
| Anchor write-once | **High** — a partial write leaves an entity unanchored | UNIQUE `(tenant, anchor_mention)` + a typed `AnchorConflict` raised on rebind |
| Lifecycle split | **High** — `to_claim` is called by the orchestrator and by the 016 suites | `to_claim` kept as a thin deprecated composition; both suites stay green |
| `fetched_at` for CC | **High** — the index genuinely lacks it | `CaptureTimeBasis.INDEX_OBSERVATION` + `ABSENT` fetch time; never substituted |
| Regime persistence | Medium — `regime_id` appears nowhere today | one table + column on `candidates`/`relation_claim`; parity-checked |
| Second stream adapter | Medium — unknown source shape | adapter must map onto the six axes or be rejected at registration |
| Corpus | Low | data-driven; runner is the same code the orchestrator runs |
