# Implementation Plan: COGNITIVE Global Platform Upgrade — Engineering Execution Programme

**Branch**: `032-global-upgrade-execution` | **Date**: 2026-10-19 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/032-global-upgrade-execution/spec.md`, whose Appendix A is the owner's v1.0 blueprint reproduced verbatim.

**Note**: This plan is the execution strategy for the programme. It does not restate the Context Engine design — that belongs to Feature `030-global-platform-upgrade` — and it does not re-derive what the blueprint already states. It maps the blueprint's WP0–WP12 onto this repository's real module layout, states the sequencing constraints, and names the seams where a defect costs the most.

## Summary

The v1.0 blueprint asks for one thing above all others: **eliminate competing authorities and then prove one path end to end.** Its ten non-negotiable decisions are all variants of that demand, and its WP0 gate exists because an engineer cannot remove a competing writer it has not found.

The technical approach is therefore subtractive before it is additive:

1. **WP0 first, as a gate.** Produce the capability matrix, the canonical-owner map and the competing-writer list from the executing commit. Nothing architectural merges before sign-off.
2. **Collapse the evidence seam.** Every executor family routes through `apps/acquisition/artifact_sink.py` and `apps/shared/events/observation_gate.py`. Bypass publishers are removed, not deprecated.
3. **Make spans first-class through the whole interpretation chain.** `EvidenceSpanRef` with `selector_semantics_version` travels from parser to finding; `apps/shared/contracts` hosts the typed contract and every producer is repaired at the boundary.
4. **Make identity and conflict decisions append-only.** Resolution and conflict produce proposals; admission commits decisions. The invariant reducer in `apps/shared/domain/graph_invariant.py` consumes the accepted stream.
5. **Prove the kernel loop without donors**, then promote donor verticals one at a time behind the §8.7 gate.
6. **Close with a clean-stack validation report** whose `NOT_RUN` and `BLOCKED` rows are as visible as its `PASS` rows.

Everything else in the blueprint — retrieval economics, projection manifests, storage profiles, scale profiles — hangs off those six steps in the order the blueprint gives them.

## Technical Context

**Language/Version**: Python 3.11 (services, contracts, operators); Rust (worker crates under the acquisition/dispatch path); TypeScript/React (webapp); PowerShell and Bash for Spec Kit and release scripts. Detected from the existing tree; no new language is introduced by this feature.

**Primary Dependencies**: the repository's existing stack — FastAPI-style control-plane routers under `apps/control-plane/api`, SQLAlchemy/`apps/control-plane/db`, PostgreSQL, S3/MinIO object storage, a Kafka-compatible broker with a transactional outbox, OpenSearch/BM25, ClickHouse, Redis, Temporal, and a Neo4j-compatible graph projection where `GraphProjection` is actually wired. Optional: pgvector or Qdrant after benchmark. Donor adapters may add pinned third-party libraries behind `OperatorResult`, never as a parallel platform.

**Storage**: one canonical owner per object class. PostgreSQL for operational state, frontier, capture/observation metadata, claim/decision/context revisions, identity decisions and the outbox; S3/MinIO for immutable raw artifacts; PostgreSQL as the claim/event canonical store with the broker as transport only; OpenSearch for lexical retrieval; ClickHouse for metrics. Every projection carries a `ProjectionManifest`.

**Testing**: `pytest` (unit, contract, integration) with the repository's `conftest.py`; contract tests against the typed boundaries in `apps/shared/contracts`; integration tests against PostgreSQL and the object store; the ten golden end-to-end cases as a dedicated suite; the security corpus as a dedicated suite; replay/idempotency tests as a dedicated suite. No test is accepted as proof of `LIVE_PROVEN`; that status requires a production call path and a measured benchmark.

**Target Platform**: the existing deployment under `apps/deploy`; Linux containers for services; the Windows operator workstation only for development and the Spec Kit toolchain.

**Project Type**: multi-service platform — acquisition, interpretation, admission, projection, control plane, web application, science, plus an isolated spec-ops profile.

**Performance Goals**: **deliberately unset.** The blueprint forbids setting p50/p95 or concurrency targets before the §11.3 measurements exist (§11.3, FR-057). WP0 records the measured baseline; targets are set only from it, and a target without a measurement is `null` with a named reason.

**Constraints**: no new graph or vector store without benchmark and rollback (§8.6, §13); no donor writing canonical stores (§8.7); no raw content in event payloads or logs where a digest suffices (§13); no LLM output treated as source evidence (§13); no bypass of login, CAPTCHA, paywall or anti-bot controls (§3.4); the fetch boundary enforces scheme allowlist, DNS validation, redirect-hop validation, size and archive-bomb limits (§3.4); no automatic person-data collection beyond explicitly permitted scope (§10, §13).

**Scale/Scope**: 146 catalogued source definitions (per the blueprint's catalogue audit — to be verified in WP0), eight executor families, the eleven donor catalogues `docs/architecture/donors/00–10`, and a WP0–WP12 programme. The blueprint's "100M edges" figure is a benchmark scenario, not a measurement or a guarantee (§11.3).

## Constitution Check

*GATE: must pass before WP0 execution; re-checked at the end of every WP.*

The project constitution lives at `.specify/memory/constitution.md`. The blueprint's WP1 asks that it be ratified as an *engineering* constitution rather than an agent-behaviour document; until that ratification lands, this plan applies the constitution as written and records any divergence rather than mutating it silently.

| Gate | Source | How this plan satisfies it | Failure mode it prevents |
|---|---|---|---|
| **G1 — One canonical owner per object** | Constitution; blueprint §0.1, §2, FR-006 | WP0 produces the owner map; WP4 removes bypass publishers; every projection gets a manifest | Two writers, two truths, unreconcilable state |
| **G2 — Evidence before claim** | Constitution; §0.3, §4.2, FR-016 | Typed spans from parser to finding; partial/unresolved instead of synthetic offsets | Grounded-looking findings with no source |
| **G3 — Append-only decisions** | Constitution; §0.4, §0.5, §6.5, FR-028, FR-034 | Resolution and identity decisions append with reasons; nothing is deleted | Silent history rewriting |
| **G4 — Honest ignorance** | Constitution; §0.3, §9.4, §11.2, FR-012, FR-052 | Closed outcome vocabulary; stop reports; `BOTH` distinct from low confidence | Confident narrator with no evidence |
| **G5 — No donor as a platform** | Constitution; §0.9, §8.1, §8.7, FR-040 | `donors/registry.yaml`, the ten-condition promotion gate, kill switch | A second canonical store arriving via a dependency |
| **G6 — Measured, not asserted** | Constitution; §11.2, §11.3, FR-056, FR-057 | Benchmarks print corpus, versions, exit status and `null` for unavailable measures; no target before measurement | Fabricated capability and performance claims |
| **G7 — Isolate untrusted execution** | Constitution; §3.4, §13, §29 | Scheme/DNS/redirect controls, isolated worker profiles, no ambient write privilege | SSRF, rebinding, archive bombs, privilege escape |
| **G8 — Reproducibility** | Constitution; §11.2, §11.3, FR-056 | Operator/model/policy fingerprints on every derived artifact; replay parity on digests | Unreproducible intelligence output |

**Result**: PASS on all gates. No complexity exception is requested. WP1's anticipated ADRs are the vehicle for any future exception; an exception without an ADR is not permitted.

## Overlap with Feature 030

`030-global-platform-upgrade` owns the Context Engine design, the Research Obligation model and the
closed-loop kernel narrative. This feature owns the *execution contract* around them. The split is:

| Topic | Authoritative feature | This feature's role |
|---|---|---|
| Context Definition / revision / branch semantics | 030 | binds it as a dependency of the loop proof (FR-046, FR-047) |
| Research Obligation lifecycle and satisfaction | 030 | requires the stop-report evidence (FR-048–FR-053) |
| ArtifactSink / Observation Gate contract | **032** | the single seam every executor must cross (FR-001–FR-005) |
| Evidence spans through the interpretation chain | **032** | FR-016–FR-018 plus WP5 |
| Conflict / identity authority | **032** | FR-026–FR-035 plus WP4, WP8 |
| Donor registry and promotion gate | **032** | FR-038–FR-045 plus WP0, WP11 |
| Storage ownership and projection manifests | **032** | FR-006, FR-007 plus WP7 |
| Golden suite and mandatory assertions | **032** | FR-055, FR-056 plus WP12 |
| Programme sequence WP0–WP12 | **032** | FR-058 |

Where both features state an obligation, the stricter wording governs and the difference is recorded
in the WP report rather than reconciled by editing either spec.

## Project Structure

### Documentation (this feature)

```text
specs/032-global-upgrade-execution/
├── spec.md              # this feature's specification + Appendix A (verbatim v1.0 blueprint)
├── plan.md              # this file
├── tasks.md             # phased execution plan (WP0–WP12, US1–US9)
├── data-model.md        # the contracts the programme must converge on
├── quickstart.md        # how to verify the programme's claims
├── checklists/
│   └── requirements.md  # spec-quality gate
├── contracts/
│   ├── README.md        # contract index and precedence
│   ├── evidence-seam.md # ArtifactSink / Observation / Capture / Locator
│   ├── acquisition-task.md
│   ├── operator-result.md
│   ├── evidence-span.md
│   ├── conflict-record.md
│   ├── resolution-decision.md
│   ├── research-obligation.md
│   ├── projection-manifest.md
│   └── donor-registry.md
└── benchmarks/          # WP0 and WP11 measurement records (created by WP0)
```

### Source Code (repository root)

```text
apps/
├── acquisition/            # executors, artifact_sink.py, fetch boundary
├── bulk-ingestion/         # Common Crawl / Wayback / WARC / dataset profiles
├── interpretation/         # parsers, extractors, normalizers, OperatorResult producers
├── admission/              # decision commit path: claims, identity, conflicts
├── projection/             # rebuildable serving projections + manifests
├── control-plane/
│   ├── context_engine/     # the research kernel (design owned by Feature 030)
│   ├── api/                # typed routers
│   └── db/                 # migrations and canonical relational state
├── shared/
│   ├── contracts/          # typed cross-layer contracts (OperatorResult, EvidenceSpanRef, ...)
│   ├── events/             # observation_gate.py, canonical envelopes, outbox
│   └── domain/             # graph_invariant.py and the invariants reducer
├── science/                # derived analytical features
├── specops/                # isolated lab profile (never in the routine path)
└── webapp/                 # analyst surfaces

donors/
├── registry.yaml           # WP0 reconciliation target
└── <vendored donors>/

docs/architecture/donors/   # 00–10 catalogues to reconcile
tests/
├── contract/               # typed boundary tests
├── integration/            # store + broker + object-store tests
├── golden/                 # the ten §11.1 cases
├── security/               # the §11.1(9) corpus
└── replay/                 # idempotency and rebuild parity
```

**Structure Decision**: the existing multi-service layout is kept. The programme adds contract
modules and test suites inside the current packages rather than introducing a new top-level service;
the only new top-level directories are `donors/registry.yaml` and the test suites. No new service is
justified by the blueprint, and decision §0.8 forbids adding a store or service because it "sounds
more scalable".

## Delivery sequence and dependency constraints

The blueprint's WP order is the plan's order, with the hard constraints made explicit:

| WP | Delivers | Hard precondition | Blocking failure mode |
|---|---|---|---|
| **WP0** | capability matrix, owner map, competing writers, donor registry, measured baseline | none | any architectural change before sign-off |
| **WP1** | constitution ratification, ADRs | WP0 | an undocumented decision becoming load-bearing |
| **WP2** | `OperatorResult`, `EvidenceSpanRef`, stage outcome/error taxonomy, canonical serialisation/digests, projection manifest, obligation/action/decision and context-revision contracts | WP1 | contracts that cannot express `unsupported` or partial |
| **WP3** | deterministic invariant/worldline reduction; bitemporal semantics across storage/query/API | WP2 | revision churn, cold-fold mismatch, `now()` substitution |
| **WP4** | one Gate, durable identity, admission boundaries; bypass publishers removed | WP2, WP3 | a second observation writer |
| **WP5** | typed spans preserved to findings | WP2, WP4 | synthetic offsets, broken citations |
| **WP6** | capability/runtime registry, output contracts, resource envelope, failure taxonomy | WP2 | adapters bypassing stores |
| **WP7** | real projections with manifests, offsets, freshness, tested rebuild | WP4, WP5 | stale projection satisfying an obligation |
| **WP8** | open-world semantics, conflicts, dynamic ontology | WP2, WP5, WP6 | `BOTH` collapsed into a score |
| **WP9** | retrieval/frontier economics on a frozen judged set | WP6, WP7 | vector store adopted on vibes |
| **WP10** | kernel loop end-to-end, two persisted iterations, stop report, restart proof | WP3, WP4, WP7, WP8 | closure on an empty queue |
| **WP11** | donor verticals promoted one at a time | WP4, WP5, WP8, WP9 | donor becoming a parallel platform |
| **WP12** | operations, security, migration, release evidence | all | release on documented intent |

**P0 work order within the programme** (blueprint §12) is reproduced as the task ordering inside
`tasks.md`, so that a partial programme is still a correct programme.

## Risks and their mitigations

| Risk | Why it is live here | Mitigation |
|---|---|---|
| WP0 becomes a documentation exercise that never gates | the repository is large and the blueprint's capability claims are unverified | WP0 sign-off is a checklist gate with named owners; `tasks.md` makes WP1+ tasks blocked on T0xx completion |
| The span repair is done at the display layer | it is cheaper than repairing every producer | FR-016/FR-018 require the typed span at the producer; a display-layer offset is treated as a test failure, not a shim |
| Identity/conflict work regresses into score-driven merging | donor libraries encourage exactly that | FR-027, FR-033, FR-034 and the transitive-merge trap in the test corpus |
| A donor is promoted by adding a call site | the promotion gate is easy to skip under delivery pressure | FR-040 and the registry's ten conditions; the disable test is part of the golden suite |
| Performance targets get set from intuition | the blueprint's own scale language invites it | FR-057 forbids a target before measurement; unavailable measures are `null` with a reason |
| The clean-stack proof never runs because the dev stack is always dirty | it is the last WP | the golden suite is designed to run on a disposable stack from WP4 onward, not only at WP12 |

## Complexity Tracking

No constitution violation is requested. The programme removes complexity (competing writers,
duplicate publication paths, parallel authorities) rather than adding it; the one apparent addition —
a typed contract layer and the donor registry — is the mechanism by which the removals are enforced.
