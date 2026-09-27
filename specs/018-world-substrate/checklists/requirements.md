# Requirements Checklist: World Substrate Closure

**Feature**: `018-world-substrate` · **Spec**: `spec.md` · **Status**: reviewed 2026-09-27

## Spec quality

- [x] FR-001…FR-005 — Durable identity and resolution (P0)
- [x] FR-006…FR-009 — Capture and acquisition lineage (P0)
- [x] FR-010…FR-013 — build / validate / admit split (P0)
- [x] FR-014…FR-016 — Real semantic regime (P0)
- [x] FR-017…FR-019 — Relation-aware extraction (P1)
- [x] FR-020…FR-023 — Corpus, replay, benchmark (P1)

## Defects grounded in the code, not in architecture

- [x] D1 — anchor is a caller obligation; `entities` has no anchor and no resolution ref
- [x] D2 — `RES-` decision exists only in memory, never persisted
- [x] D3 — `Capture` requires `fetched_at`; `CaptureObservation` has none
- [x] D4 — crawl-index `observed_at` standing in for a fetch time
- [x] D5 — `to_claim` fuses build and admit; validator sees only admitted claims
- [x] D6 — `regime_id` persisted in no table; `regime_unevaluated` on every run
- [x] D7 — cue rule lives in the orchestrator; corpus uncommitted

## Success criteria

- [x] SC-0 — non-regression with today's green baseline
- [x] SC-1 — identity survives a discarded caller scope
- [x] SC-2 — full resolution history, including ambiguous/unresolved decisions
- [x] SC-3 — `RES-` durable, append-only, re-derivable
- [x] SC-4 — four separate time values; no index timestamp as fetch time
- [x] SC-5 — orchestrator no longer fabricates a capture id
- [x] SC-6 — unadmitted material is validatable
- [x] SC-7 — three distinct operations, no shared name
- [x] SC-8 — regime resolves from storage; `regime_unevaluated` not on the golden path
- [x] SC-9 — relation-aware extraction, no cue rule in the orchestrator
- [x] SC-10 — no extractor can mark a reading SUPPORTED
- [x] SC-11 — corpus committed, byte-identical across processes
- [x] SC-12 — replay is a fixed point
- [x] SC-13 — corpus covers the graded paths
- [x] SC-14 — both "why was this accepted" chains reconstruct

## Scope guard

- [x] Contextual modelling explicitly deferred, with the reason stated
- [x] Resolution algorithm declared closed — not reimplemented
- [x] `entities.entity_type` not rewritten; its relationship to type layers made explicit
- [x] No new semantic adapters, vocabularies, profiles or ontology backends
- [x] No scale/throughput claim (FR-022 proves a fixed point; a benchmark is later)

## Feasibility

- [x] Resolution logic already exists and is proven — this feature persists and separates it
- [x] `Capture` type already exists and is content-addressed
- [x] `LayeredValidator`, `MaterialisationDecision` and graded verdicts already exist
- [x] In-memory implementations suffice for replay; no live infra required
- [x] Every FR verifiable without Kafka, Neo4j, MinIO or PostgreSQL

## Constitution

- [x] Gate stated: FR-001 / SC-1 are load-bearing; a caller-forgettable value is a substrate failure
- [x] All eight principles marked PASS with reasoning
- [x] Principle V given a concrete teeth: an index timestamp is never promoted to a fetch time

## Honesty check

- [x] No success criterion asserts a scale claim
- [x] Corpus expectations' brittleness raised as an open question, not silently decided
- [x] The absence of committed tests is recorded as debt (open question 5), not glossed
