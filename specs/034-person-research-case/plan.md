# Implementation plan — Feature 034 Person Research Case

Status: execution plan; tasks remain unchecked until code, tests and service-backed evidence exist.
Normative parent: spec.md. This plan extends existing canonical owners and does not introduce another context engine, resolver, evidence store or event envelope.

## Delivery rule

A feature is not production-ready because a class, route, YAML entry or unit test exists. Promotion requires a caller reachable from the production composition root, durable state where required, contract tests, service-backed integration evidence and an auditable rollback path. Live-source success must use actual source bytes and be reproducible from recorded capture manifests. Missing services and skipped tests are NOT_RUN or BLOCKED, never PASS.

## Ordered work waves

### W0 — Baseline, ownership and security gate
Record the exact starting SHA and executable test baseline; map every canonical entity, event and writer; inventory source definitions, upstream dependencies, licences and runtime callers; reproduce security and operational gaps. Do not expand collection until authentication, tenant isolation, SSRF/egress and evidence durability have a tested disposition.

Exit evidence: baseline.md, owner-writer map, dependency/SBOM inventory, generated platform audit, machine-gap output, and an explicit PASS/BLOCKED/NOT_RUN per gate.

### W1 — Canonical contracts and policy
Reconcile Features 024, 030, 032 and 033. Bind ResearchCase to one canonical Investigation and scope/context revision history. Define versioned source policy and capability manifest with fail-closed defaults, source/terms/access restrictions, expiry, budget, retention and kill switch. Reuse the existing EventEnvelope, EvidenceSpanRef, canonical resolution/admission and CompletionReport contracts.

Exit evidence: ADRs, schema-validation tests, compatibility tests and migration plan.

### W2 — Case draft, context revision and approval
Create/update draft cases without network effects. Store append-only context amendments, static artifact refs and dynamic invariant anchors separately. Approval is bound to tenant, actor, authority, exact scope/context/policy/budget digest and expiry. Every scope-affecting change invalidates stale tasks and requires re-approval.

Exit evidence: API/UI tests for create → amend → revise → approve, concurrency conflicts, revocation and tenant isolation.

### W3 — Policy-first planning and raw-first acquisition
Compile questions into schema-checked proposals and canonical grammar/AST. Plan only sources allowed by case policy and technical readiness. Reserve budget before dispatch. Persist task state, idempotency, scope/policy digests and outcomes. All workers return through ArtifactSink → durable raw object → Capture/Observation → transactional outbox. Enforce network, redirect, streaming, decompression, archive and CPU/time limits at every hop.

Exit evidence: service-backed acquisition and crash/retry reconciliation using at least one real, permitted source; no fake event or process-local record may count as success.

### W4 — Interpretation and evidence spans
Route captured bytes through the existing parser registry and production extraction lane. Store exact raw digest, parser/extractor version, transformation manifest and span coordinates. Emit mention-bound claims as candidates; no parser or model directly admits truth. Mature external parsers may be integrated only with pinned versions, licence review, isolation and rollback.

Exit evidence: corpus-driven span round-trip tests across enabled media types, malformed input tests and source-to-claim lineage.

### W5 — Resolution, review and relation claims
Use the existing canonical resolver/admission owner. Validate and wire the pinned Splink 5 adapter; do not fall back to a handwritten pairwise resolver for this vertical. Candidate overflow is observable and cannot be silently truncated. possible_match remains a review proposal. Typed relation claims retain participants, predicate, polarity, valid time and evidence references.

Exit evidence: collision, transliteration, missing-data, anti-transitive-merge and concurrent-review tests; durable relation-claim path reachable in production.

### W6 — Bitemporal context and durable closed loop
Keep published, valid, observed, captured, ingested and processed time distinct. Implement CURRENT, AS_OF and INTERVAL semantics through the canonical context/fabric. Independence precedes saturation. New evidence must update durable obligations and change the next eligible task across at least two persisted CognitiveLoop ticks; no separate person-specific loop is allowed.

Exit evidence: late-arriving evidence, contradiction, qualified absence, replay and two-tick service-backed tests.

### W7 — Rebuildable projections and analytics
Wire search, graph, timeline, coverage, network-science and TDA through explicit capability manifests. Derived outputs include input watermarks/cut, versions, parameters and digest. Projections cannot write canonical identity or claims. Unsupported providers remain explicit capability gaps rather than custom miniature replacements.

Exit evidence: delete/rebuild equivalence and projection-outage recovery from canonical state.

### W8 — Analyst workspace, reports and retention
Provide case setup and approval, live activity, evidence notebook, claim/entity review, temporal timeline, relation graph, coverage, competing hypotheses and report preview. Every presented finding resolves to stored evidence spans. Reports disclose actual queried sources, unsupported capabilities, conflicts, outages, costs and unresolved obligations. Retention/export/delete runs as durable workflows across raw and derived objects with verification.

Exit evidence: UI navigation and accessibility tests, citation-resolution tests, tenant-scoped export and retention verification.

### W9 — Release conformance
Run the complete acceptance matrix against a clean deployment profile and exact SHA. Capture commands, exit status, test reports, dependency versions, migration results, actual source URLs and raw digests. No mandatory FAIL, BLOCKED, NOT_RUN, missing service or skipped test may be represented as PASS.

## Rollback and promotion

Every source family, model provider, parser and projection provider has a kill switch, pinned immutable version, licence/terms record, observable readiness, rollback path and canonical-write boundary. Promotion is per capability, not global. Existing observations remain immutable; correction/replay produces versioned interpretations and rebuildable projections.

## Out of scope for the first vertical release

Do not promise exhaustive information about any person. Do not bypass access controls or infer hidden account identities, credentials, private contact or movement history. Start with approved public professional and official records, then expand only after each source family passes its own policy, technical and conformance gates.
