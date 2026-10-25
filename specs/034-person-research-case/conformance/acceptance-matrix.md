# Feature 034 — acceptance matrix

This matrix is mandatory for promotion. Every row needs an executed result, exact SHA, command, exit status and retained evidence. Tests with mocks may validate an isolated contract but cannot satisfy service-backed end-to-end rows. Any skipped prerequisite is NOT_RUN, not PASS.

| ID | Area | Scenario | Required assertion |
|---|---|---|---|
| C034-001 | Baseline | Run tests, migrations and platform model at exact SHA | Failures and skips are classified; no historical count is reused as current evidence |
| C034-002 | Authentication | Missing, malformed, unsigned, expired, wrong issuer/audience and cross-tenant credentials against every case route | Denied unless a verified principal and tenant claim are supplied |
| C034-003 | Authority | Create draft; plan/run before approval; mutate scope after approval; revoke queued work | No network before approval; stale work cancels; revocation blocks dispatch |
| C034-004 | Context | Create case, append amendment, revise and replay context | Immutable revisions have parent and digest; replay is deterministic; one context engine only |
| C034-005 | Entity kinds | Add a dynamic invariant and static artifact plus typed relation | Separate lifecycles; raw artifact remains immutable; relation is evidence-backed |
| C034-006 | NL planner | Clear, ambiguous, unsupported, contradictory and out-of-scope requests | Canonical AST and ambiguity returned; denied/unsupported request never dispatches |
| C034-007 | Policy/capabilities | Disable provider, remove all eligible providers, submit unknown/unreviewed source policy | Denied source does not dispatch; a durable capability gap is reported |
| C034-008 | Budgets | Exhaust request, byte, record, CPU, model-token, runtime and retry budget | Reservation precedes dispatch; hard stop is durable and bounded |
| C034-009 | SSRF/egress | Loopback, private/link-local IP, DNS rebinding and redirect-to-private | Every hop denied; no protected egress occurs |
| C034-010 | Stream/archive | Oversized/chunked response, gzip bomb, recursive archive and parser timeout/crash | Limits enforced before unbounded expansion; failure is auditable |
| C034-011 | Raw-first | Crash between object write, Capture/Observation and outbox publish | No published observation without durable raw bytes; recovery is idempotent |
| C034-012 | Replay | Repeat same task/event or replay from stored offset | No duplicate evidence, coverage, identity revisions or cost learning |
| C034-013 | Evidence spans | Extract from live captured HTML/PDF and compare selectors/digests to original bytes | Every admitted claim resolves to exact source span and correct raw digest |
| C034-014 | Prompt injection | Captured body instructs model to alter scope, call tools or reveal secrets | Source is untrusted data; model cannot gain authority or write canonical state |
| C034-015 | Resolution collision | Real public records share names or have close transliteration | Candidate remains possible_match until evidence and canonical admission justify decision |
| C034-016 | Blocking overflow | Heavy bucket and missing/unavailable Splink provider | No silent truncation; counts visible; readiness blocks incompatible adapter |
| C034-017 | Review | Accept, reject, uncertain, reopen, merge/split with concurrent reviewers | Append-only decision lineage and explicit conflict; identity changes only via canonical admission |
| C034-018 | Bitemporality | Late capture describes earlier valid interval; query CURRENT/AS_OF/INTERVAL | Knowledge time and valid time remain distinct; later evidence does not rewrite past AS_OF |
| C034-019 | Epistemics | NEITHER, TRUE_ONLY, FALSE_ONLY, BOTH, unsupported, unavailable and zero results | States round-trip without collapsing; absence requires declared detection power |
| C034-020 | Source lineage | Primary statement plus syndications/mirrors | Root lineage/dependency group persists; copies do not count as independent corroboration |
| C034-021 | Relations | Positive, negative and contested typed relations over time | Predicate/direction/participants/polarity/time/evidence persist, including unknown predicates |
| C034-022 | Closed loop | Two or more durable CognitiveLoop ticks using real source outcome | First result creates conflict/coverage obligation; next tick changes action based on persisted state |
| C034-023 | Projections | Delete and rebuild search/graph/timeline from canonical state | Equivalent fingerprints for same input cut/build; projection cannot mutate canonical claims |
| C034-024 | UI/report | Navigate report assertion to evidence inspector, timeline, graph and coverage | No untraceable finding; conflicts, uncertainty and blockers visible |
| C034-025 | Tenant isolation | Cross-tenant IDs, cursors, graph edges, downloads, report exports and background tasks | Deny without revealing object existence |
| C034-026 | Retention | Expire case and run scoped export/retention/deletion | Policy applied to raw and derived stores; outcome is auditable and no false erasure claim |
| C034-027 | Packaging/migrations | Install wheel/container from clean checkout and migrate empty/existing supported DB | Installed modules match intended composition; migration chain works without runtime create_all substitute |
| C034-028 | Live end-to-end | Clean profile with PostgreSQL, Redpanda, object store, Temporal and required projections; use at least two independent live official sources | Real case reaches evidence-backed claim and report without mocks; actual bytes, URLs and digests retained |
| C034-029 | Conformance report | Execute all mandatory rows | Every result has evidence; no FAIL/BLOCKED/NOT_RUN/skipped service is reported as production-ready |

## Required live-record scenarios

1. Capture a real official public-professional record, persist original bytes and digest, extract one claim with an exact span, and navigate from report to source.
2. Compare two real distinct public records with colliding names and preserve the distinct candidates until an admission decision.
3. Capture two real official versions or dated records that show a temporal change or conflict; query knowledge time and valid time independently.
4. Process an official public disclosure/register record where available, preserve the fields actually published and never infer unavailable values.
5. Run a dedicated unsafe-source fault injection for private-address redirect or compression limit; block egress and retain a failure record.
6. Record a real no-result response as a bounded outcome, not as a claim that no such information exists.

## External integration promotion

Before a library/source/model becomes enabled: pin immutable release/commit; verify code and separate assets/data licences; record SBOM; review security and data/write boundaries; add contract tests; configure kill switch and rollback; measure benefit on a versioned corpus. A README, dependency pin or unit test alone does not prove production integration.
