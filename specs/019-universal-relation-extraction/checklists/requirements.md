# Requirements Checklist: Universal Relation Extraction

**Feature**: `019-universal-relation-extraction` · **Spec**: `spec.md` · **Status**: reviewed 2026-09-27
**Verified against**: `HEAD 81d810795ab1cf24e03931cb7ccc40915c6f296d`

## Defects confirmed by reading the code, not inherited

- [x] D1 — `execution.py:2707` `with_status(CandidateStatus.SUPPORTED)`, `:2747` `to_claim()`; fused path is live
- [x] D2 — no `relation_candidate` table in any migration; generic `candidates` lacks every hypothesis field
- [x] D2b — `candidates.candidate_id VARCHAR(36)` cannot hold a 37-char `CNDR-` id
- [x] D3 — `BACKWARD_CHAIN` and `FORWARD_CHAIN` are different node sets in one unmarked vocabulary
- [x] D4 — `Capture` has no `published_at`; EDGAR declares it supplied and drops it
- [x] D5 — `RELATION_CUES` is the only relation producer; no signal registry, no assembler
- [x] D6 — no representation for a relation of unknown type

## Lifecycle (A)

- [x] FR-001 — executable path is `build → validate → admit`
- [x] FR-002 — `SUPPORTED` has one documented meaning, decided not left ambiguous
- [x] FR-003 — extraction cannot produce an admissible status by construction
- [x] FR-004 — deprecated fused path is legacy-only and marked
- [x] FR-005 — validator examines unconfident material; only admission commits

## Candidate durability (B)

- [x] FR-006 — durable substrate, `CAND-`/`CNDR-`, all hypothesis fields
- [x] FR-007 — "which hypotheses were produced" is answerable
- [x] FR-008 — append-only; ambiguous and rejected persist
- [x] FR-009 — generic `candidates` explicitly not treated as this substrate
- [x] FR-010 — tenant-scoped, fail-closed

## Lineage separation (C)

- [x] FR-011 — evidence vs derivation distinguishable in the model
- [x] FR-012 — `CANDIDATE` not added to the evidence chain for symmetry
- [x] FR-013 — both chains separately queryable and separately correct
- [x] FR-014 — existing traversals keep documented behaviour, or the break is stated

## Acquisition envelope (D)

- [x] FR-015 — `Capture` stays an acquisition fact
- [x] FR-016 — source-declared temporal facts get their own representation
- [x] FR-017 — no seventh temporal axis
- [x] FR-018 — EDGAR's acceptance instant retained, loss observable

## RelationSignal (E)

- [x] FR-019 — signal value with the full field set
- [x] FR-020 — signal is structurally not a candidate/claim/edge
- [x] FR-021 — fixed extensible signal-kind vocabulary
- [x] FR-022 — single `RelationSignalExtractor` contract
- [x] FR-023 — cue reader is one lexical producer, not a precondition
- [x] FR-024 — unknown relation type constructible and survivable
- [x] FR-025 — every producer is mention-level, no entity ids

## Producers (F)

- [x] FR-026 — at least one structurally different producer beyond lexical
- [x] FR-027 — link/reference signals assert structure, not semantics
- [x] FR-028 — table/list signals carry a surface relation
- [x] FR-029 — metadata reaches the same contract
- [x] FR-030 — event-shaped n-ary hypothesis representable
- [x] FR-031 — attribute/value signal without entity assumption

## Assembly (G)

- [x] FR-032 — signals → candidates, origin preserved
- [x] FR-033 — aggregation without signal loss
- [x] FR-034 — conflicting signals → competing persisted hypotheses
- [x] FR-035 — confidence never becomes truth
- [x] FR-036 — assembly creates no claim, resolution or edge

## Identity (H)

- [x] FR-037 — two levels only, no third hierarchy
- [x] FR-038 — extractor/regime/temporal/evidence changes visible on the revision
- [x] FR-039 — different shape or participants do not collapse
- [x] FR-040 — surface form does not determine hypothesis identity

## Boundedness (I)

- [x] FR-041 — named deterministic neighbourhoods, no document-wide pairs
- [x] FR-042 — the seven minimum bounds
- [x] FR-043 — every signal records its neighbourhood
- [x] FR-044 — generate wide within bounds, then block hard
- [x] FR-045 — no blanket `related_to` for co-occurrence

## Boundaries (J)

- [x] FR-046 — projection boundary machine-checkable
- [x] FR-047 — search/expansion hypothesis stays out of extraction
- [x] FR-048 — registry is an accelerator, never a gate

## Determinism (K)

- [x] FR-049 — cross-process identical ids
- [x] FR-050 — replay is a byte-identical fixed point
- [x] FR-051 — no clock, randomness or dict-order dependence

## Scope guard

- [x] No global ontology, no mandatory relation registry
- [x] No `extractor → GraphEdge`
- [x] No `ontology miss → drop relation`
- [x] No `one mention = one entity`
- [x] No `SUPPORTED` as a technical pre-claim flag
- [x] No all-mentions × all-mentions
- [x] No 500 branches in one extractor
- [x] No blanket `related_to` for co-occurrence
- [x] No context engine inside a relation extractor
- [x] No abstraction layer added for terminology alone

## Boundary contradictions recorded, not worked around

- [x] 1 — `Capture` cannot hold source temporal facts; new object required
- [x] 2 — `VARCHAR(36)` vs a 37-char id; schema change required
- [x] 3 — `SUPPORTED` load-bearing in `RelationCandidateSet.supported` and `to_claim`
- [x] 4 — `forward()` derives from `FORWARD_CHAIN`; splitting changes it
- [x] 5 — `RelationCandidate` requires a `RelationRef`; unknown relation unconstructible

## Success criteria

- [x] SC-A…SC-L — one FR group each, mapped
- [x] SC-M — non-regression baseline recorded from the verified run

## Honesty check

- [x] No SC asserts a scale or throughput claim
- [x] The sharpest contradiction (unknown relation vs required `RelationRef`) is the stated gate
- [x] Constitutional tests are invariant-only, not coverage
- [x] Every defect cites a file, line or field verified in this session
