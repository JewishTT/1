# Tasks — Feature 034 Person Research Case

Rule: every item starts unchecked. Mark complete only when production reachability, relevant tests and evidence for the exact SHA are recorded. File existence, mocked integration and skipped tests do not qualify. Status values PASS, BLOCKED, NOT_RUN and FAIL must be explicit in the release record.

## W0 — Baseline, ownership and security
- [ ] 034-T001 Record exact base SHA, dependency/toolchain versions, service profile and clean/dirty state.
- [ ] 034-T002 Run and record root, control-plane, frontend, Rust, migration and collection baselines separately.
- [ ] 034-T003 Trace one permitted live public record through task → connector → ArtifactSink → Observation/outbox → parser → claim → report; record all IDs and raw digest.
- [ ] 034-T004 Produce canonical owner/writer map for case, context revisions, obligations, tasks, captures, observations, claims, identities, relation claims, projections and reports.
- [ ] 034-T005 Inventory source definitions, add-ons, Common Crawl/Wayback/WARC, federated search, uploads, donor code, licences/terms, runtime caller and disable path.
- [ ] 034-T006 Re-run security audit: authentication, tenant boundaries, SSRF/DNS/redirects, body/archive limits, prompt injection, retention and secrets.
- [ ] 034-T007 Record machine-model, migration, package, health, metrics, DLQ and production-reachability gaps.
- [ ] 034-T008 Assign every baseline gate PASS/BLOCKED/NOT_RUN with owner and evidence; do not build around unresolved canonical ownership.

## W1 — Contracts and policy
- [ ] 034-T009 Record an ADR mapping ResearchCase to one canonical Investigation and defining the single writer for lifecycle and scope.
- [ ] 034-T010 Reconcile Features 024/030/032/033; prohibit a second resolver, context engine, event envelope or canonical evidence store.
- [ ] 034-T011 Add versioned case/context/artifact/invariant/relation/task/outcome/claim/report contracts and round-trip tests.
- [ ] 034-T012 Define canonical serialization and digest rules; preserve unknown values and evidence lineage.
- [ ] 034-T013 Add source-policy and capability-manifest validation with deny-by-default behavior for unknown terms/access/license/runtime.
- [ ] 034-T014 Define coverage and absence states so no result is not silently turned into a factual negative.
- [ ] 034-T015 Add required schema through owned migrations; test fresh install, supported upgrade and downgrade/rollback.
- [ ] 034-T016 Record decision owners and release-blocking ambiguities in decision-register.md.

## W2 — Case and UI workflow
- [ ] 034-T017 Create a draft case bound to verified principal, tenant, scope and canonical investigation; creation has no network effects.
- [ ] 034-T018 Implement append-only context amendments with parent revision, actor, rationale and digest.
- [ ] 034-T019 Implement scope revision and stale-task cancellation; relevant scope/policy/context changes require re-approval.
- [ ] 034-T020 Store static uploads/references through ArtifactSink with digest, media type, tenant and retention metadata.
- [ ] 034-T021 Represent dynamic invariants as unresolved anchors until canonical admission; do not auto-promote user claims.
- [ ] 034-T022 Implement typed relation proposals with participants, polarity, temporal bounds and evidence refs.
- [ ] 034-T023 Bind approval to verified approver, authority reference, scope/context/policy/budget digests, expiry and revocation.
- [ ] 034-T024 Test every new route and artifact operation for cross-tenant access and non-enumerating 404 behavior.

## W3 — Planner and acquisition
- [ ] 034-T025 Implement policy-first capability selection; unknown source/contact/access class denies dispatch.
- [ ] 034-T026 Compile natural language into a schema-checked proposal, then canonical grammar AST; preserve ambiguity and unsupported questions.
- [ ] 034-T027 Produce side-effect-free plans with obligations, permitted source choices, exclusions, assumptions, budget and digest.
- [ ] 034-T028 Persist durable task state, lease/deadline, idempotency key and scope/policy/context/approval digests.
- [ ] 034-T029 Prove every promoted runtime writes through ArtifactSink and ObservationGate/outbox; document/disable bypass paths.
- [ ] 034-T030 Enforce SSRF/private-IP/DNS-rebinding/redirect controls and streamed byte, MIME, archive, decompression, CPU and time limits.
- [ ] 034-T031 Reconcile crashes between raw-object persistence, Capture/Observation placement and event publish idempotently.
- [ ] 034-T032 Prove retries/replay do not duplicate observations, coverage, independence, claims or costs.
- [ ] 034-T033 Replace seeded/process-local DLQ records with durable quarantine and typed outcomes.
- [ ] 034-T034 Reserve budgets before dispatch; enforce request, byte, record, token, retry and runtime limits.
- [ ] 034-T035 Make pause/resume/cancel/revoke durable and revalidate scope/policy before every dispatch.
- [ ] 034-T036 Promote at least two independently sourced official public-record source families with observed live captures and recorded terms.

## W4 — Parsing and evidence
- [ ] 034-T037 Wire the parser registry to actual durable task outcomes with deterministic media-type selection.
- [ ] 034-T038 Build a versioned parser corpus for HTML, PDF, text and other enabled formats; mark unsupported formats honestly.
- [ ] 034-T039 Add mature parser providers only when a measured corpus gap justifies them; pin versions, licences, isolation and rollback.
- [ ] 034-T040 Validate EvidenceSpanRef against stored original bytes, exact digest and parser/version selector.
- [ ] 034-T041 Emit mention-bound public/professional claim candidates with source, observation, time and extractor refs.
- [ ] 034-T042 Preserve raw and normalized values, aliases, locale, transformation version and uncertainty.
- [ ] 034-T043 Use model-assisted parsing only through the existing Model Gateway; validate schemas and evidence spans, never permit model writes to canonical truth.
- [ ] 034-T044 Test prompt injection, malformed documents, fabricated citations, parser crashes and exact-span round trips.

## W5 — Resolution and relations
- [ ] 034-T045 Verify and pin Splink 5 API/dependency/licence; implement and test the v5 adapter.
- [ ] 034-T046 Wire the adapter into the production composition root and prove no handwritten resolver fallback for this vertical.
- [ ] 034-T047 Detect blocking overflow before truncation; expose overflow and unprocessed candidate counts.
- [ ] 034-T048 Version comparison features and missingness semantics; a name, URL, score or graph proximity cannot commit identity.
- [ ] 034-T049 Route possible_match through canonical review/admission; preserve accept/reject/uncertain and reversibility.
- [ ] 034-T050 Make relation-claim persistence production-reachable and retain claim/evidence lineage.
- [ ] 034-T051 Test real-record name collisions, transliteration, conflicting identifiers and non-transitive merge hazards.
- [ ] 034-T052 Test typed predicates, unknown relations, polarity, participants and temporal qualifiers.

## W6 — Bitemporality and feedback loop
- [ ] 034-T053 Verify separate published/valid/observed/captured/ingested/processed clocks and use migrations for missing fields.
- [ ] 034-T054 Implement CURRENT, AS_OF and INTERVAL semantics across storage, API and UI.
- [ ] 034-T055 Compute source-root independence before corroboration/saturation; unknown dependency remains unknown.
- [ ] 034-T056 Implement typed coverage, no-result and qualified-absence states based on declared detection power.
- [ ] 034-T057 Feed conflicts and coverage changes into the existing context/fabric and durable obligations.
- [ ] 034-T058 Execute at least two persisted CognitiveLoop ticks using real service-backed outcomes.
- [ ] 034-T059 Prove the second tick changes a revision, obligation and eligible next action; persist decision trace and stop reason.
- [ ] 034-T060 Add evidence-linked abduction/ACH proposals with alternatives and discriminating queries; no direct truth/identity writes.

## W7/W8 — Projections, workspace and report
- [ ] 034-T061 Verify production callers and canonical inputs for search, graph, timeline and coverage projections.
- [ ] 034-T062 Store projection input cuts/watermarks, operator/schema versions, parameters, digest and staleness.
- [ ] 034-T063 Delete/rebuild projections and prove equivalent fingerprints; outage cannot corrupt canonical evidence.
- [ ] 034-T064 Build bounded case graph/timeline with evidence-linked relation claims and temporal axes.
- [ ] 034-T065 Expose network-science/TDA as derived signals only; structural scores cannot create facts or merges.
- [ ] 034-T066 Implement analyst workspace for approval, live board, evidence inspector, review, graph/timeline, coverage and hypothesis alternatives.
- [ ] 034-T067 Build CompletionReport from canonical findings/claims/obligations and actual queried sources; every factual assertion resolves to evidence.
- [ ] 034-T068 Implement durable retention/export/deletion with dry-run manifest and post-action verification across raw and derived stores.

## W9 — Final conformance
- [ ] 034-T069 Run production-boundary SSRF, archive bomb, prompt injection, parser isolation and secret-leak tests.
- [ ] 034-T070 Run cross-tenant tests for API, cursors, graphs, background tasks, exports and retention.
- [ ] 034-T071 Replace hard-coded readiness/metrics/DLQ responses with measured operational state for the promoted path.
- [ ] 034-T072 Record runtime/SLO/cost baselines from real source-backed runs; do not predeclare performance targets without measurements.
- [ ] 034-T073 Complete SBOM, source terms, donor/model version, licence, kill switch and rollback records.
- [ ] 034-T074 Execute all mandatory acceptance cases on a clean profile and exact SHA; attach commands, exit status and reports.
- [ ] 034-T075 Test source disable, policy revocation, replay, raw/outbox reconciliation, projection rebuild and retention propagation.
- [ ] 034-T076 Publish verdict; any mandatory BLOCKED, NOT_RUN, FAIL or skipped prerequisite excludes production-ready status.

## Status vocabulary

- PASS: condition executed and evidence attached for exact SHA.
- BLOCKED: precondition, authority, service or dependency prevents execution.
- NOT_RUN: not executed; reason, owner and next action are stated.
- FAIL: executed condition did not pass.

All checkboxes remain unchecked until evidence is recorded.
