# Implementation Plan: Donor Core Subsystems

**Branch**: `005-donor-core-subsystems` | **Date**: 2026-09-08 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/005-donor-core-subsystems/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command; its definition describes the execution workflow.

## Summary

Integrate five real donor subsystems into the executable path of COGNITIVE (not benchmarks),
each sourced from a single donor and rewritten to the platform's event-driven architecture:

1. **Knowledge Model** (FollowTheMoney MIT) — canonical `Entity` / `Property` / `Statement` +
   schema registry with provenance, dataset, and temporal validity in `apps/shared/domain`.
   Becomes the single model the pipeline stages share; `admission/engine/assertions.py` is adapted
   to consume it (its internal `Statement` becomes the shared one).
2. **Resolution with human review** (OpenOSINT MIT) — reviewable `Candidate` pairs with
   deterministic keys, score vectors, evidence links and non-destructive merge/reverse records,
   wired through existing `admission/resolution/*` and `control-plane/services/review.py`.
3. **Parser + evidence-manifest subsystem** (NetForensicAI MIT) — harden the existing
   `interpretation/parsers/registry.py` `can_parse`/`parse` contract and add an immutable
   **Evidence Manifest** chain `Finding → Evidence → Observation → Raw` (sha256), with
   size/time sandbox limits and quarantine on hostile/unparseable input.
4. **Connector module registry** (SpiderFoot MIT, logic layer) — module lifecycle
   (register / scan / stop) with a bounded thread pool and a shared event channel, normalized
   to observations via `shared/donor/target.py` (already ported), behind the
   `AcquisitionWorker` contract (Constitution V).
5. **Investigation state + monitoring** (investigator MIT) — add monitor counters and a
   hardened state/lifecycle to `control-plane/domain/investigation.py` with atomic updates and
   late-event dead-letter parking.
6. **Review queue & timeline UI** (vitni Apache-2.0; PANO CC BY-NC-4.0 as pattern-only
   reference) — port vitni's review model pure into `apps/webapp/src/lib/donor/review.ts`,
   wire a review queue + subject status badges into the webapp views, and document PANO UX
   patterns in `contracts/ux-reference.md` (never copied).

## Technical Context

**Language/Version**: Python (repository uv workspace; apps `shared` / `admission` / `interpretation` / `acquisition` / `control-plane` deps), TypeScript/React webapp (`apps/webapp`) — IN scope this track (vitni review-model port + PANO UX reference). The kafSIEM Go event-envelope backend stays deferred (per spec Assumptions).

**Primary Dependencies**: None new. Adapted donor modules must use stdlib + already-wired deps only (spec FR-002). Existing in-repo helpers used: `events.kafka.build_envelope`, `events.topics.topic_for` / `EVENT_CATALOG`, `shared/domain` invariant exceptions, `storage.s3`, `acquisition` worker contracts.

**Storage**: Hermetic in-memory stores currently stand in for Postgres (`control-plane/db/schema.py`); raw objects content-addressed via `storage/s3.py` (sha256) — the evidence manifest chains to it.

**Testing**: `uv run --project apps/{shared,admission,bench} pytest` from repo root; webapp `npm test` + `npx tsc -b` (touched only if webapp consumer added — none this track). Ruff: `uvx ruff check <paths>`. Regression gates: shared ≥144, admission ≥41, bench ≥20, webapp ≥43.

**Target Platform**: Linux container deploy; dev on Windows (pwsh). Python ≥3.12 features OK (stdlib only).

**Project Type**: Multi-application Python monorepo (shared packages + FastAPI control plane + acquisition/interpretation/admission services).

**Performance Goals**: Deterministic and idempotent processing (I-11); non-destructive operations; atomic per-investigation counter updates; bounded connector thread pools.

**Constraints**:
- stdlib-only donor ports; no new runtime dependencies (FR-002).
- License gate: never copy reNgine (GPLv3), PANO (CC BY-NC-4.0), kipi (empty); pattern-only reuse, documented per module (FR-005).
- Event-driven: every persisted artifact emits an envelope (`statement.created`, `review.recorded`, `resolution.*`, `connector.status_changed`, `investigation.*`) — refs not blobs (I-5), rebuildable projections (I-12).
- Sandboxed parsers (size/time/depth) + quarantine of malformed/hostile input (VII).
- Benchmark-harness-only integration is NOT a valid consumer (FR-008).

**Scale/Scope**: 5 subsystems across shared/admission/interpretation/acquisition/control-plane; ~5 donor-sourced modules + ~5 adaptation touch points + tests. UI track deferred.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Invariant | Status | How this plan honors it |
|-----------|--------|-------------------------|
| I-1 Observation immutable | OK | Evidence Manifest is append-only; findings chain to immutable raw sha256, never mutate it. |
| I-2 Mention != Candidate != Entity | OK | Candidates are reviewable pairs; accepted candidates record a resolution link, never an auto-merge (spec FR-006). |
| I-3 Assertion != truth | OK | Statements/claims keep the `claimed` flag + provenance; extraction never asserts identity as fact. |
| I-5 No blobs on Kafka | OK | All new events carry refs/manifest chain, payloads are dict JSON, no raw content. |
| I-12 Projections rebuildable | OK | Every write emits an envelope so projections replay (statement.created, review.recorded, resolution events). |
| V Plugability by contract | OK | Parser recorder (`can_parse`/`parse`) and connector module registry sit behind existing contracts; no vendor class in domain logic. |
| VII Security-first | OK | Parsers/connectors sandboxed with size/time limits; unknown formats quarantined (spec FR-009/FR-010). |

## Project Structure

### Documentation (this feature)

```text
specs/005-donor-core-subsystems/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
apps/shared/
├── domain/                          # Canonical knowledge model (this track)
│   ├── entity.py                    # FTM-ported: Entity + Property + SchemaRegistry subset
│   ├── statement.py                 # STM: Statement w/ dataset_id, extraction_version, original_value, temporal, provenance
│   └── __init__.py                  # invariants (existing) unchanged
├── donor/                           # existing ports (target.py, temporal.py, ...) unchanged
└── events/                          # topic_for/EVENT_CATALOG gains resolution.candidate_created etc. (small)

apps/admission/
├── engine/assertions.py             # ADAPT: use shared.domain.Statement (delete local dup)
├── resolution/
│   ├── candidate.py                 # NEW OpenOSINT-ported: Candidate (pair key, score vector, evidence links, review state)
│   ├── resolver.py / collective.py  # ADAPT: emit Candidates + resolution events, export merge records
└── evidence/independence.py         # unchanged (consumes manifests)

apps/interpretation/
├── parsers/registry.py              # HARDEN: size/time/depth limits; unknown-format quarantine
├── evidence/manifest.py             # NEW NetForensicAI-ported: EvidenceManifest chain + Finding
└── pipeline.py                      # ADAPT: parsers emit Statements via shared.domain + manifests

apps/acquisition/
├── registry.py                      # NEW SpiderFoot-ported: ConnectorModule lifecycle (register/scan/stop), bounded pool, event channel
└── (worker-http / worker-browser)   # ADAPT (thin): normalize connector events through shared/donor/target.py

apps/control-plane/
├── domain/investigation.py          # ADAPT: + MonitorCounters, late-event parking (dead-letter)
├── services/review.py               # ADAPT: wire ReviewTargetType.CANDIDATE resolution records
└── workflows/investigation.py       # ADAPT: emit monitor/state events

apps/webapp/
├── src/lib/donor/review.ts          # NEW vitni-ported: review model (derive/filter/sort/node-status)
├── src/lib/donor/review.test.ts     # NEWS vitest
└── src/containers + components      # ADAPT: review queue wiring (Investigation/Entity views, LineageWalker badges)
```

**Structure Decision**: The monorepo layout is preserved; each donor subsystem lands as one cohesive
module set in its home app, with the canonical model centralized in `apps/shared/domain` so all
consumers (parsers, admission, resolution, connectors, control plane) share one source of truth.
No new project/package is introduced (no Constitution violation).

## Complexity Tracking

> No Constitution violations — the Complexity Tracking table is intentionally empty.