# Research: Donor Core Subsystems

**Date**: 2026-09-08 | **Feature**: [spec.md](spec.md)

Phase 0 artifacts resolving plan Technical Context unknowns and donor-extraction risks.

## 1. FollowTheMoney knowledge model — scope of the port

- **Decision**: Port a minimal, stdlib-only subset of the FTM model: `Entity` (schema_name + id),
  `Property` (typed, schema-validated, first-class), schema registry keyed by `schema_name`
  mapping to property sets, and retain the platform's existing `Statement` semantics.
- **Rationale**: The existing `apps/shared/events/ontology_pack.py` (OntologyPackRegistry) already
  provides schema-pack vocabulary; the platform's `Statement` (in `engine/assertions.py`) already
  models FTM provenance fields (dataset_id, extraction_version, original_value, valid_from/until).
  What is missing is a canonical `Entity`/`Property` model in `shared/domain` that parsers and
  interpolation consumers produce through — the audit confirmed the model is scattered.
- **Alternatives considered**: Full FTM dependency pulled in — rejected: banal/rigour/semhash and
  `model.py`'s registry machinery are far beyond the needs and would violate FR-002 (no new deps).
  Keeping model local to admission — rejected: that is exactly the scattering the user brief asks
  to eliminate.

## 2. OpenOSINT resolution — non-destructive human review

- **Decision**: Materialize resolution as reviewable `Candidate` records (deterministic pair key,
  score vector, evidence links, review state `open/accept/reject/reverse`) and record merges as
  persisted resolution links (both source entities stay queryable), reusing the existing
  `admission/resolution/{blocking,resolver,collective}.py` stack and `control-plane/services/review.py`
  (ReviewTargetType.CANDIDATE already exists).
- **Rationale**: ReviewRecord in `review.py` is already append-immutable and emits `review.recorded`;
  adding a candidate object + non-destructive merge record on top reuses the tested plumbing and
  satisfies spec FR-006. Rejection must be preserved with reasons so recomputation at equal evidence
  does not re-propose (dead-letter / quarantine semantics).
- **Alternatives considered**: Auto-merge on score threshold — rejected: violates I-2
  ("Mention != Candidate != Entity") and the Constitution's stated identity rule.
  Rewriting resolution from scratch in shared/domain — rejected: the admission stack is the
  correct home and already covered by 41 passing tests.

## 3. NetForensicAI parser contract + evidence manifest

- **Decision**: Keep the existing `ParserAdapter` `can_parse`/`parse` protocol in
  `interpretation/parsers/registry.py` (already NetForensicAI-pattern, tested in
  `test_parser_adapter.py`), add hard sandbox limits (size / time / depth) plus a new
  `interpretation/evidence/manifest.py` producing an immutable chain
  `Finding → Evidence → Observation → Raw(sha256)`.
- **Rationale**: `ParserRegistry.parse_artifact` already returns deterministic `Finding` objects;
  the gap is the evidence chain and hard limits. The manifest directly satisfies spec FR-009 and
  the Evidence-First Constitution rule (II) — every finding must trace to source.
- **Alternatives considered**: Wrapping NetForensicAI wholesale — rejected: it drags in its own
  evidence store/runtime; only the manifest/finding shape is extracted (per user's
  "no Frankenstein" rule). Parsing inline without limits — rejected: violates Constitution VII.

## 4. SpiderFoot connector module registry

- **Decision**: Port the SpiderFoot module lifecycle shape (capabilities + event output +
  run/stop with a bounded thread pool) as `apps/acquisition/registry.py` behind the existing
  `AcquisitionWorker` contract; events normalize through the already-ported `shared/donor/target.py`.
- **Rationale**: Constitution V requires application code to touch only contracts; the SpiderFoot
  module interface (`sfEvent`, module run/stop, capability scan) is the proven pattern for a
  swappable connector ecosystem and is MIT-clean. Target normalization already exists from track 004,
  so connector events can collapse to canonical targets without new code.
- **Alternatives considered**: Porting SpiderFoot's full framework — rejected: heavy, and contrary
  to taking one coherent subsystem (the module lifecycle) rather than the whole platform.

## 5. investigator monitor/state

- **Decision**: Extract the monitor/state slice (≈subset of `src/investigator.py` cycle: states,
  counters, atomic updates, terminal-state late-event parking) into `control-plane/domain/
  investigation.py` additions — a statemachine + telemetry over the existing statemachine.
- **Rationale**: The existing `Investigation` statemachine (DRAFT→PLANNING→RUNNING→PAUSED→
  COMPLETED→ARCHIVED) is structurally sound; what it lacks is monitoring counters and
  dead-letter for late events, which the audit ranked as the lowest-risk stdlib port. Keeps
  control-plane tests green.
- **Alternatives considered**: Full investigator CLI port — rejected: CI/task tooling is out of
  scope for the platform control plane.

## Cross-cutting decisions

- **Event catalog**: extend `events/topics.py` with `resolution.candidate_created`,
  `resolution.candidate_decided`, `evidence.manifest_created` (refs-only payloads, I-5).
- **Attribution**: each adapted module gets a header (source repo, license, commit-ish, change
  note) per FR-001; license gate re-verified in the review gate.
- **Consumer proof (FR-008)**: each subsystem must be grep-referenced by an executable consumer —
  parsers→pipeline.py, resolution→collective.py/export, review→investigation API, connectors→
  worker delegation, investigation→workflows.