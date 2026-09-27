# Implementation Plan: 021-entity-relation-extraction-finalization

**Branch**: `021-entity-relation-extraction-finalization` | **Date**: 2026-09-27 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/021-entity-relation-extraction-finalization/spec.md`
(102 functional requirements, 5 constitutional invariants, 16 measurable outcomes, 9 user
stories). The unabridged user brief is `input.md` in this directory and governs over this
document wherever the two appear to differ.

## Summary

Turn 019's *raw surface string is logical identity* into a durable hypothesis-and-evidence
substrate, and repair the 20+ defects the code audit found while doing so.

The technical approach: **structural `PredicateSignature` as the identity carrier.**
`RelationSignal` becomes natively n-ary with a variadic participant list and a real polarity
field, declares a normalised `PredicateSignature` (normalised predicate, arity, role names,
argument shape, direction, polarity) alongside the raw surface it observed, and derives
`logical_candidate_id` from the signature instead of the surface. `relation_surface` becomes
pure evidence/revision material. Mention binding moves to a pre-resolution mention index so
producers cite real `MN-…` ids and a mention is never confused with an entity. The type layer
gains a bounded, versioned foundational vocabulary (`core:*`, `value:*`) plus a first-class
multi-hypothesis `TypeHypothesis` with a controlled vocabulary for the type space, while the
relation space stays open — an unrecognised predicate stays `UNKNOWN` forever rather than
being dropped. Persistence gains real columns (signature, signal refs, direction, polarity,
`candidate_id`) via migration `021` on top of the forward-only `020`, and the whole lifecycle
gets wired into the live `interpret_warc_capture` path so that "production code" is a
verified claim rather than an assumption.

**Non-goal carried from the brief**: no giant relation ontology, no majority voting, no
mention × mention sweep, no producer that emits a claim or an edge.

## Technical Context

**Language/Version**: Python >= 3.11 (`requires-python = ">=3.11"`, ruff `target-version = "py311"`,
`line-length = 100`)

**Primary Dependencies**: `cognitive-shared` (workspace), `fastapi>=0.111`, `uvicorn[standard]>=0.30`,
`alembic>=1.13`, `httpx>=0.27`, `temporalio>=1.4`, `neo4j>=5.21`, `clickhouse-connect>=0.7`,
`orjson>=3.10`. Test/dev: `pytest>=8.2`, `pytest-asyncio>=0.23` (`asyncio_mode = "auto"`),
`ruff>=0.5`. Build: `hatchling`. Workspace manager: `uv` (11 members, installed editable, so
cross-app imports like `from extractors.registry import …` resolve from any project).

**Storage**: PostgreSQL via SQLAlchemy 2.0 declarative (`mapped_column` + `__table_args__`),
migrated by Alembic. Graph projection has `InMemoryGraphStore` (the only wired one),
`Neo4jGraphStore` (unwired, and it does not import the driver) and `RebuildableGraphStore`
(unwired replay/snapshot store). Also available: ClickHouse, OpenSearch, Kafka, Temporal,
Redis via `apps/deploy/docker-compose.yml`. **Live PostgreSQL is not reachable in this
environment**, so DB work is verified offline (ORM/DDL parity + in-memory round trip) and any
live round trip is reported as `verified only offline`.

**Testing**: `pytest` with per-app projects and `markers = ["contract","integration","unit"]`.
Canonical command form (`docs/CONTRIBUTING.md:37`): `uv run --project apps/<app> pytest apps/<app>/tests -q`.
There is **no CI** (`.github/` does not exist), no Makefile, no tox/nox, and no test-runner
script — the gate is run by hand.

**Target Platform**: Linux server / Docker; Windows dev host (current environment is win32,
`pwsh`).

**Project Type**: multi-app Python workspace (FastAPI service + Temporal worker + libraries).

**Performance Goals**: bounded neighbourhood only — no global O(N²) mention sweep; a producer
that enumerates pairs MUST report a real count and MUST stay under its declared
`max_pairs_considered`.

**Constraints**: determinism under replay (content-addressed ids re-derived, never trusted);
tenant isolation; lossless persistence (a digest may identify data but must never be the only
copy); raw predicate surface is evidence, never logical identity; no `ENT-`/`RES-` literals in
producer code; no `TYPE_CHECKING` except in type positions.

**Scale/Scope**: 020 created 3 tables; 021 adds migration `021` plus new columns and new
domain types. 9 user stories, 102 FRs, 16 SCs. Corpus target: 8 golden end-to-end HTML cases
(§109) + the §82/§83 type and relation case sets.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Gate | Status at plan time |
|---|---|---|
| I-2 `Mention != Candidate != Entity != …` (7 distinct levels) | No type may collapse two levels; `candidate_status` MUST NOT become a `rank()` | **PASS with work** — the levels exist, but `metadata.py` uses a *property name* as a participant and producers fabricate mention ids, which merges "mention" with "field name" |
| I-3 `Assertion != truth` | Unknown must be a retained state, never a drop | **PASS** — `PredicateResolutionState.UNKNOWN` exists and is retained; `material_requires_resolved_predicate` is the correct CD-6 line |
| I-4 `Graph != source of truth`; projection-first | `GraphEdge`/`HyperEdge` MUST be derivable only from admitted claims | **PASS** — `GraphProjectionBridge` is typed `claim: RelationClaim` with no overload, so a candidate or signal cannot be projected even by mistake |
| III projection-first; graph is a projection | Projection MUST be rebuildable from stores | **GAP** — `RebuildableGraphStore` has no production caller; no repository writes the 020 tables at all, so "rebuildable" is currently unproven |
| VI determinism | Content-addressed ids re-derived, never trusted; no result may depend on dict iteration order | **GAP** — `signal_refs` is identity material but never sorted, so `candidate_id` depends on caller order; determinism survives only because `assembly.py:338` sorts by hand |
| IV tenancy | No cross-tenant writes or reads | **PASS** — assemblable and `run_producer` both refuse cross-tenant output |
| "Constitution supersedes all other practices" | Any requirement in this plan that conflicts loses | **PASS** — the brief's §45 (no majority vote) and the constitution agree; where the brief's docstrings disagree with behaviour, behaviour wins and the docstring is corrected |

**Re-check after Phase 1 design**: confirm the `PredicateSignature` in the data model keeps
exactly two identity terms (structural signature + participant identity) and does not
reintroduce a surface-dependent term.

## Project Structure

### Documentation (this feature)

```text
specs/021-entity-relation-extraction-finalization/
├── input.md            # the user's unabridged brief (3411 lines, §0–§114) — source of truth
├── spec.md             # 102 FR / 16 SC / 5 INV / 9 stories, fully traceable to §0–§114
├── plan.md             # this file
├── tasks.md            # Phase 2 output (/speckit.tasks) — NOT yet created
├── research.md         # Phase 0 output — NOT yet created
├── data-model.md       # Phase 1 output — NOT yet created
├── quickstart.md       # Phase 1 output — NOT yet created
├── contracts/          # Phase 1 output — NOT yet created
├── checklists/
│   └── requirements.md # gate checklist — NOT yet created
└── adr/                # decisions A–K from §100 — NOT yet created
```

### Source Code (repository root)

```text
apps/
├── shared/                          # value types + contracts (cognitive-shared)
│   ├── domain/
│   │   ├── relation_candidate.py    # 26 fields; logical id keyed on relation_surface; no to_dict
│   │   ├── predicate_hypothesis.py  # 4 states; no PredicateSignature
│   │   ├── predicate_signature.py   # NEW — structural normalised identity
│   │   ├── relation_signal_parts.py # NEW — Participant tuple, SignalAspect split
│   │   ├── relation_claim_material.py
│   │   ├── relation_claim.py        # 31 fields; does not self-verify its id
│   │   ├── relation_identity.py     # canonical_material / digest128 / logical_material
│   │   ├── evidence_lineage.py      # 9 HopKinds; CANDIDATE absent from backward chain
│   │   └── temporal_observation.py
│   ├── semantic/
│   │   ├── blocking.py              # thin TypeHypothesis today
│   │   ├── contracts.py             # RelationRef, TypeAssertion; no domain/range
│   │   ├── vocabularies.py          # type vocabulary / mapping architecture
│   │   ├── type_vocabulary.py       # NEW — bounded versioned core:*/value:* pack
│   │   └── operators.py             # known operators, explicitly not a closed universe
│   └── tests/{constitution,contract,integration,unit}/   # 43 files
├── interpretation/
│   ├── extractors/
│   │   ├── types.py                 # TypedMention.kind: str — the only type surface today
│   │   ├── relations.py             # RelationalReading.to_candidate(): dead 2nd path
│   │   ├── registry.py
│   │   └── signals/
│   │       ├── signal.py            # binary; SignalKind overloads; asserts_something
│   │       ├── protocol.py          # run_producer, _stamp, assert_bounded
│   │       ├── lexical.py           # synthetic surface:* refs; dead MAX_PAIRS_CONSIDERED
│   │       ├── links.py             # anchor:*/href:*; pairs_considered = scanned//16
│   │       ├── tables.py            # TableExtractor + ListExtractor; zip(strict=False)
│   │       └── metadata.py          # attribute:*/jsonld:* subjects; document:current
│   ├── mention_index.py             # NEW — pre-resolution mention binding seam
│   └── tests/{contract,unit}/       # 12 files
├── control-plane/
│   ├── semantic_path/
│   │   ├── assembly.py              # _arity_of majority vote; reading_key; no production caller
│   │   ├── execution.py             # 14 stages, no production caller
│   │   ├── corpus.py, corpus_cases.py, signal_corpus.py
│   │   └── record_corpus.py
│   ├── services/
│   │   ├── capture_interpretation.py# THE production seam (FR-100)
│   │   ├── entity_pipeline.py
│   │   ├── cc_cursor_materialization.py
│   │   ├── layer0_pipeline.py       # InterpretHook seam, unwired
│   │   └── search_backends.py       # holds the process-wide InMemoryGraphStore
│   ├── workflows/
│   │   ├── temporal_materialization.py # live Temporal workflow
│   │   ├── investigation.py         # unregistered, calls 2 non-existent activities
│   │   └── worker.py
│   ├── db/
│   │   ├── schema.py                # 020 tables; missing signal_refs/direction/polarity/candidate_id
│   │   ├── relation_claim_store.py  # SqlRelationClaimStore, 0 importers, NotImplementedError paths
│   │   ├── relation_signal_store.py # NEW — no repository exists for the 020 tables
│   │   └── migrations/versions/020_universal_relation_extraction.py  # HEAD, forward-only
│   ├── api/routes/                  # 24 modules, ~122 routes
│   └── tests/{unit,integration}/    # 40 files
├── projection/
│   ├── graph/
│   │   ├── abstraction.py           # GraphNode/Edge/HyperEdge, InMemoryGraphStore
│   │   ├── neo4j.py                 # Neo4jGraphStore — never imports the driver
│   │   ├── snapshot.py              # RebuildableGraphStore — unwired
│   │   └── relation_store.py        # GraphProjectionBridge — unwired
│   └── tests/                       # 17 files
├── acquisition/
│   ├── stream.py                    # capture_with_observations(): 0 callers
│   ├── adapters/{sec_edgar,common_crawl}.py  # both implement to_temporal_observations
│   └── tests/                       # 19+ files
├── admission/  science/  zero/  bulk-ingestion/  feedback/     # zero importers of extractors
├── deploy/docker-compose.yml        # infrastructure only; no app or test services
└── webapp/                          # vite; out of scope for this feature
```

**Structure Decision**: the existing 11-app `uv` workspace is kept exactly as it is. This
feature adds no new app and no new top-level directory. New code lands in the app that
already owns the concern — domain value types in `apps/shared/domain` and
`apps/shared/semantic`, extraction in `apps/interpretation`, lifecycle and persistence in
`apps/control-plane`, graph projection in `apps/projection`, acquisition wiring in
`apps/acquisition`. The only structural addition inside an app is a small number of new
modules (`predicate_signature.py`, `type_vocabulary.py`, `mention_index.py`,
`relation_signal_store.py`) plus `contracts/` and `checklists/` under the feature directory.
Justification for not introducing a new app: the concern is already split across exactly the
apps that own each stage, and the constitution's layering is a *dependency* rule
(`interpretation` must not import `admission`/`projection`), which the current workspace
already enforces by declaration — a new app would add a boundary without adding a constraint.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No constitutional violations are being accepted. Two items are recorded because they look
like violations and are not:

| Item | Why it looks like a violation | Why it is not |
|---|---|---|
| `RelationSignal._material()` keeps `producer_ref` | It means two producers reading one structure get different `signal_id`s, contradicting three docstrings | I-3: corroboration counting needs producer identity. The docstrings are wrong, the behaviour is right. The *new* defect — `extra`/arity being excluded — is fixed separately under FR-089 |
| Bounded `core:*`/`value:*` type vocabulary, open relation space | A closed type list could read as a fixed ontology | §104 asks for exactly this asymmetry, and `FR-034` makes the vocabulary a blocking/mapping/validation instrument rather than an extraction gate — an unknown type stays `UNKNOWN` |

Two genuine risks are tracked instead of justified away:

| Risk | Detail | Mitigation |
|---|---|---|
| "Complete" could be claimed on a test-only harness | The 019 lifecycle has **no production caller**; `ExecutionRequest.producers` is never assigned; `lexical_signals` has never run | FR-100 makes the live `interpret_warc_capture` seam mandatory, and FR-084 forbids completion claims that rest on the corpus harness |
| The boundedness guarantee is currently unmeasured | Two producers fabricate `pairs_considered` and the third always reports `0`, so `max_pairs_considered` is policed against an invented number or not policed at all | FR-093 requires a real count or a stated `0`, and makes the ceiling live |

## Phase 0 research — status

`research.md` and `data-model.md` are written. Decisions recorded there: parser choice (R-001),
signature-as-identity (R-002), bounded type vocabulary / open relation space (R-003),
production wiring seam (R-004), migration `021` (R-005), graph backend scope (R-006).

Seven questions remain deliberately open (`research.md` R-007): Q1 normalisation rule set,
Q2 controlled vocabulary, Q3 neighbourhood scope, Q4 n-ary identity shape, Q5 import direction,
Q6 binding-point choice, Q7 temporal-observation repository. Each blocks a specific task and
has a stated default in `tasks.md`, so none of them blocks starting Phase 0.

## Still owed before the §100 deliverables gate

- `contracts/` — the producer protocol, the mention-index contract and the store contract
- `checklists/requirements.md` — the 102-FR verification map (T004)
- `quickstart.md` — the commands that actually work
- `adr/` — decisions A–K

