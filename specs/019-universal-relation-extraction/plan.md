# Implementation Plan: Universal Relation Extraction

**Feature**: `019-universal-relation-extraction` · **Spec**: `spec.md`
**Status**: planned 2026-09-27 · **Base**: `HEAD 81d8107`

## Summary

Seven constitutional decisions (CD-1…CD-7) are fixed, so this is a build plan rather than an
investigation. The shape of the work: **cut the five contract wounds the previous features
left open, then put the universal signal substrate on top of the healed contracts** — not the
other way round, which is what the mandate requires.

The invariant everything serves is CD-7: *semantic incompleteness must not reduce structural
observability*. A relation the platform cannot name must still arrive with both participants,
their roles, a direction, a trigger, a structural context, a source, an observation, temporal
clues, signal provenance, and every alternative reading.

## Technical Context

**Verified, not assumed.** Each of these was read in this session:

- `execution.py:2707` `with_status(CandidateStatus.SUPPORTED)`, `:2747` `to_claim()`.
- No `relation_candidate` table in any migration. `candidates.candidate_id VARCHAR(36)`;
  `CAND-`/`CNDR-` are 37 chars.
- `Capture` fields: `capture_id, tenant_id, source_id, source_family, target_uri, locator,
  content_digest, content_length, media_type, fetched_at, time_basis, transport,
  ingest_batch_id, ingest_attempt, recorded_by`. **No `published_at`.**
- `EdgarFullIndexAdapter` declares `published_at supplied=True source_field="date filed"`,
  then builds `fetched_at=None, time_basis=CaptureTimeBasis.PUBLICATION`.
- `evidence_lineage.py` has `BACKWARD_CHAIN` (no `CANDIDATE`) and `FORWARD_CHAIN` (with it),
  unmarked; `forward()` derives its steps from `FORWARD_CHAIN`.
- `RELATION_CUES` in `apps/interpretation/extractors/relations.py` is the only relation
  producer. No `RelationSignal`, no protocol, no assembler anywhere.
- `RelationCandidateSet.supported` (`relation_candidate.py:1423`) filters on `SUPPORTED`;
  `to_claim` raises `CandidateNotAdmissible` without it.

**Reused, not rewritten:** `RelationCandidate` (already two-level, `CAND-`/`CNDR-`),
`RelationClaimMaterial.build/validate/admit`, `LayeredValidator`, `Capture` + its
content-addressed discipline, `digest128`, the stream seam (`StreamAdapter`/`StreamRegistry`),
and the corpus runner with its per-layer invariance and replay.

## Decisions

- **D1 — Order of work is contract-healing first.** CD-6 changes `RelationCandidate`; CD-1
  changes the lifecycle that consumes it. Doing either after the signal substrate would mean
  rebuilding the substrate against moved types.
- **D2 — `PredicateHypothesis` is a new value in `domain`, not in `semantic`.** It describes a
  *predicate*'s epistemic state, and `semantic.contracts` already owns the three-name boundary
  the core domain may see. `RelationCandidate` is in `domain`, so the type it gains must be too.
- **D3 — `relation_ref` becomes `RelationRef | None` on `RelationCandidate`, required on
  `RelationClaimMaterial` and `RelationClaim`.** The boundary is the *type*, not a runtime check:
  material and claim have no field to put `None` in.
- **D4 — Signals get their own module under `interpretation/extractors/signals/`,** and the
  adapter protocol lives beside the value. Producer code stays out of `domain`.
- **D5 — Lineage split is additive.** `EVIDENCE_BACKWARD_CHAIN` and
  `DERIVATION_FORWARD_CHAIN` replace the ambiguous names as the source of truth; `BACKWARD_CHAIN`
  and `FORWARD_CHAIN` stay as aliases so nothing breaks, and `forward()` keeps its sequence
  because that sequence is the derivation one it already computed.
- **D6 — One migration, `020`,** carrying `relation_candidate`, `relation_signal`,
  `source_temporal_observation`, and the `VARCHAR(64)` widening sweep CD-3 demands. Forward-only,
  `downgrade()` raises, offline DDL parity proven as 018/019 did.
- **D7 — Constitutional tests go in a new `tests/constitution/`** package, because they are not
  feature tests: they encode the platform's invariants and must not be deleted with a feature.
  The corpus stays the integration oracle and keeps no tests.

## Project Structure

```
apps/shared/domain/
├── predicate_hypothesis.py   NEW  PredicateHypothesis, PredicateResolutionState
├── relation_candidate.py     MOD  relation_ref optional; predicate_hypothesis field
├── relation_claim_material.py MOD  relation_ref REQUIRED (no field to put None in)
├── relation_claim.py          MOD  candidate_id already added; relation_ref stays required
└── evidence_lineage.py        MOD  EVIDENCE_/DERIVATION_ chains, aliases, trace()

apps/interpretation/extractors/
├── signals/
│   ├── __init__.py          NEW
│   ├── signal.py            NEW  RelationSignal, SignalKind, DirectionHypothesis
│   ├── protocol.py          NEW  RelationSignalExtractor, Neighbourhood
│   ├── lexical.py           NEW  the existing cue reader, projected as a LEXICAL producer
│   ├── links.py             NEW  LINK/REFERENCE producer
│   ├── tables.py            NEW  TABLE/LIST producer
│   └── metadata.py          NEW  METADATA producer
└── relations.py              KEEP  primitive, not the extension point any more

apps/control-plane/semantic_path/
├── assembly.py              NEW  RelationSignalAssembler -> RelationCandidate
├── execution.py              MOD  real lifecycle, signals, assembly
└── corpus_cases.py           MOD  expanded corpus
    corpus.py                 MOD  trace() reporting, signal layers

apps/control-plane/db/
├── schema.py                 MOD  3 new tables + widening sweep
└── migrations/versions/020_universal_relation_extraction.py   NEW

apps/acquisition/
└── adapters/sec_edgar.py     MOD  emit SourceTemporalObservation instead of dropping it

apps/shared/tests/constitution/   NEW  invariant tests (9, per spec)
```

## Complexity Tracking

| Component | Risk | Mitigation |
|---|---|---|
| `relation_ref` optional on candidate | **High** — every reader of `candidate.relation_ref` must handle absence | grep the whole repo for readers; the type change finds them |
| `to_claim` losing the `SUPPORTED` guard | **High** — 016's suites assert the raise | keep the raise for *legacy* callers only; new lifecycle does not go through it; suites stay green |
| Id widening sweep | **High** — foreign keys and unique constraints in 019/016 reference `candidate_id` | offline DDL parity plus an explicit reference enumeration before the migration is written |
| Lineage split | Medium — `forward()` derives from `FORWARD_CHAIN` | aliases preserved, sequence unchanged (D5) |
| `SourceTemporalObservation` | Medium — the EDGAR instant has no home today | new object, and its absence is assertable (FR-018) |
| Signal substrate | Medium — new module, no integration risk yet | built on healed contracts, wired last |
| Assembly semantics | Medium — aggregation rules are genuinely ambiguous | OQ3 (hypothesis with no signals) resolved before assembly is written |
