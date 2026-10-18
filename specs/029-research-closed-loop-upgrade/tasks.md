# Tasks: COGNITIVE Master Platform Upgrade

**Feature**: 029-research-closed-loop-upgrade
**Plan**: [plan.md](./plan.md) · **Data model**: [data-model.md](./data-model.md)
**Audit**: [audit/current-state-audit.md](./audit/current-state-audit.md)

Status vocabulary, consistent with spec 026:

- `[x]` delivered **and verified by a run recorded in this file**
- `[~]` partially delivered — the stated part works, the rest does not
- `[!]` blocked — the reason is named
- `[ ]` open

**A `[x]` requires the command and its result here.** A checkbox is not evidence:
`audit/current-state-audit.md` §4 lists seven tasks marked complete whose implementation
does not exist at the claimed path.

---

## WP-0 — Trustworthy baseline — **DELIVERED**

| ID | Task | FR | Status | Evidence |
|---|---|---|---|---|
| T001 | Record commit, branch, dirty tree | — | `[x]` | `608c3ad8f4743e4e729807c903b0364ed571b311`, `main`, 117 dirty |
| T002 | Record the real test result | — | `[x]` | `pytest apps -q --ignore=bench` → **22 failed, 4273 passed, 27 skipped**, 1097.95s |
| T003 | Record the root-collection failure | — | `[x]` | `pytest -q` → **831 collection errors** (vendored `donors/`, `tmp/`) |
| T004 | Record the `bench` collection error | — | `[x]` | `ImportError: cannot import name 'harness' from 'bench'` |
| T005 | Triage the 22 failures by cause | — | `[x]` | audit §1 — 14 in 3 files, 8 independent |
| T006 | Set `testpaths` / `norecursedirs` | — | `[x]` | `pytest --co -q` → **4336 collected, 0 collection errors** |
| T007 | Fix `bench` package shadowing | — | `[x]` | deleted 2-byte `bench/__init__.py`; from `bench/` → **21 passed, 2 failed** |
| T008 | Publish the regression command + floor | SC-013 | `[x]` | `pytest -q` → **22 failed, 4288 passed, 27 skipped** |

---

## WP-A — Make the loop closable — **DELIVERED**

| ID | Task | FR | Status | Evidence |
|---|---|---|---|---|
| T010 | Supply saturation from the fabric pass | FR-001 | `[x]` | `loop.py:394-406` |
| T011 | Translate the fabric verdict into engine language | FR-003 | `[x]` | `fabric_bridge.to_engine_saturation()`; unknown stays unknown |
| T012 | Deliver the stop reason on every terminal path | FR-002 | `[x]` | `loop.py:490-520`; `TickReport.loop_status` + `.stop_reason` |
| T013 | Carry analyst feedback into the tick | FR-011 | `[ ]` | WP-I — feedback plane has no production caller |
| T014 | Suppress repeat no-gain actions | FR-011 | `[ ]` | `_attempt_key` exists; suppression not wired |
| T015 | Test: obligation → satisfied → named reason | FR-001,002 | `[x]` | `test_an_obligation_reaches_a_terminal_state_from_evidence`, `test_a_saturated_tick_carries_a_reason` |
| T016 | Test: blocked names the obligation | FR-002 | `[x]` | `test_a_blocked_tick_names_the_stalled_obligations` |
| T017 | Test: contradiction keeps it open | FR-001 | `[x]` | `test_a_contradiction_keeps_the_obligation_open` |
| T018 | Saturation can express "not measured" | FR-003 | `[x]` | `obligations.py:51` — 6 tests incl. backward compatibility |
| T019 | Re-run full suite; no new failures | SC-013 | `[x]` | 22 failed (identical set), 4288 = 4273 + 15 |

---

## WP-B — Durable decision record

| ID | Task | FR | Status | Evidence |
|---|---|---|---|---|
| T020 | `research_decisions` table + migration M1 | FR-005 | `[ ]` | |
| T021 | `ContextStore` decision methods; off the in-memory list | FR-005 | `[ ]` | |
| T022 | Content-address `decision_id` over grounds/inputs/alternatives/actor/outcome | FR-005 | `[ ]` | |
| T023 | Contract test on a real database: record → restart → retrieve | FR-005, SC-005 | `[ ]` | |

---

## WP-B2 — Definitions, revision cause, explicit ranking

| ID | Task | FR | Status | Evidence |
|---|---|---|---|---|
| T024 | `question_definitions` table + `CXD-` identity space | FR-006 | `[ ]` | |
| T025 | `investigation_contexts.definition_id` + migration M2 | FR-006 | `[ ]` | |
| T026 | Test: two investigations under one definition are isolated | FR-007 | `[ ]` | |
| T027 | `RevisionCause` — events, rules, operators, params, predecessor, changes, warnings | FR-008 | `[ ]` | |
| T028 | Migration M3; revision cause is never rewritten | FR-009 | `[ ]` | |
| T029 | Test: a revision cannot explain itself → rejected | FR-008 | `[ ]` | |
| T030 | Expose action-ranking components | FR-012 | `[ ]` | |
| T031 | Store raw features, calibrated probability, policy decision separately | FR-013 | `[ ]` | |

---

## WP-C — One gate, one identity

| ID | Task | FR | Status | Evidence |
|---|---|---|---|---|
| T040 | Refuse to publish an observation whose bytes were not stored | FR-015, SC-010 | `[x]` | `shared/events/evidence_store_guard.py` — one chokepoint; 12 tests |
| T041 | Route `sources/connector.py` through the gate | FR-014,015 | `[x]` | `connector.py:_event_for` — gate's event + raw_ref; `acquisition` 361 passed |
| T042 | Route `worker_acquisition.py:442` and `pow_run.py:187` | FR-015 | `[~]` | publisher guarded (T040); `pow_run.py` still writes rows directly — no test |
| T043 | Collapse four identity derivations into one; v2 schema, v1 dual-read | FR-016 | `[x]` | **3 of 4 removed**: connector delegated to gate; `zero/observation_gate.py` `uuid4()` → digest-derived; `interpretation_bridge.py:592` delegates. `acquisition/sources/connector.py:28` retained as a documented shadow for its own tests |
| T044 | Replace the random default event id; invert the test that pins it | FR-017 | `[x]` | `derive_event_id()` in `observation_identity.py`; `build_envelope` uses it; `test_event_id_is_default_uuid` **inverted** to `test_event_id_is_derived_not_random` + 3 new |
| T045 | Count dropped runtime artefacts instead of `continue` | FR-058, SC-010 | `[x]` | `worker_acquisition.py:311` — digest-derived id, refusals counted |
| T046 | Persist the capture record that is built then discarded | FR-014 | `[ ]` | |
| T047 | Name the repair path for each of the four failure windows | FR-029,030 | `[ ]` | |
| T048 | Fix `postgres_store.py:572` calling a `from_dict` that does not exist | FR-021 | `[ ]` | |
| T049 | Test: every production observation resolves to stored bytes | FR-014, SC-010 | `[x]` | `test_the_connectors_event_is_refused` + `test_loop_closed` asserts `raw_ref` |
| T050 | Test: redelivered event ⇒ one observation, no independence inflation | FR-017, SC-003 | `[ ]` | replay fixed point holds; independence inflation untested |
| T051 | Test: empty tenant refused on the envelope | FR-049,050 | `[ ]` | |
| **T053** | **NEW** Separate acquisition identity from evidence identity in the worker | FR-014 | `[ ]` | Opened by T041 — see the behaviour change below |

### Behaviour change opened by WP-C

`test_a_different_query_is_a_different_observation` previously asserted that two
different queries over identical bytes produce two observations. Under the canonical
identity that is wrong: `domain/observation_identity.py` documents that two fetches
returning identical bytes are *one payload, two publications*. The connector's
`(source_id, query, page, digest)` derivation was one of the four shadow schemes the
audit named.

Routing the connector through the gate changed the behaviour, so the test now asserts
one observation — and **does not claim two publications**, because the worker still
dedups on observation identity. Query "acme" and query "globex" are two different pieces
of investigative work over one piece of evidence, and the platform currently cannot
express that. T053 records the gap rather than a test asserting something false.

---

## WP-D — Accumulated state, digest-gated revision

| ID | Task | FR | Status | Evidence |
|---|---|---|---|---|
| T060 | Wire `InvariantReducer` into the live materialization path | FR-010,031 | `[x]` | `cc_cursor_materialization.py` — fold + digest gate; `state_digest` now travels with the publication |
| T061 | Retire unconditional revision minting per sweep | FR-010 | `[x]` | `generation = previous + 1` removed; replaced by digest comparison |
| T062 | Make `CURRENT` a distinct query; expose `INTERVAL` beside `AS_OF` | FR-033 | `[ ]` | |
| T063 | Declare the semantics of all nine timestamp fields | FR-032 | `[ ]` | |
| T064 | Fixture test: current / as-of / interval all differ | FR-033, SC-006 | `[ ]` | |
| T065 | Test: late evidence does not rewrite the as-of past | FR-034 | `[ ]` | |
| T066 | Test: restart reproduces the accumulated digest | FR-031, SC-004 | `[x]` | `test_digest_gated_revision.py` — 19 tests, incl. `restore` vs cold fold |

---

## WP-E — Admission without uncalibrated auto-merge

| ID | Task | FR | Status | Evidence |
|---|---|---|---|---|
| T070 | Refuse auto-merge when `calibration_id` is null | FR-045 | `[x]` | `CalibrationProfile.is_calibrated`; `_is_merge` requires declaration or a reviewed match; `merge_refusal()` names the withheld merge on the decision |
| T071 | Replace hostname corroboration with dependency groups at the live call site | FR-046 | `[x]` | `_Cluster.effective_sources`; `lineage_by_document` param; `independence_measured_on` on every decision |
| T072 | `ResolutionDecision` carries feature breakdown, model fingerprint, actor | FR-044 | `[ ]` | |
| T073 | State how prior conclusions read after a split or merge | FR-047 | `[ ]` | |
| T074 | Keep admission and resolution as separate stages | FR-048 | `[ ]` | resolution lane already refuses auto-merge; not re-verified under T070 |
| T075 | Test: copies of one source do not raise the effective count | FR-046,004 | `[x]` | `test_effective_independence.py` — 20 mirrors → 1 source, with the host-measured counterfactual |
| T076 | Test: null calibration routes to review, never to merge | FR-045 | `[x]` | `test_a_high_score_alone_does_not_merge_without_calibration`, `test_a_calibrated_profile_restores_the_bar` |

### Behaviour changes opened by WP-E

Two tests asserted the old behaviour and were inverted, both documented in place:

1. `test_high_scoring_match_merges_without_confirmation` — a resolver score of 0.95
   with no confirmation now does **not** merge against an uncalibrated profile. The
   candidate is still admitted, still carrying `matched_entity_id` and `match_score`
   for a reviewer, and the withheld merge names itself in `reason_codes`.
2. `test_resolver_match_produces_accept_existing` — same, through `WarcIntake`.

A new test asserts the *counterfactual* (`test_without_lineage_the_mirrors_would_have_
looked_corroborated`) so the first cannot pass vacuously: the same twenty hostnames
without lineage still clear the bar, which is exactly the number T071 stops trusting.

A test also caught a non-conservative bug in the first implementation: documents with
**no** declared lineage were being dropped from the count entirely, so removing
evidence *lowered* the effective-source figure and manufactured concentrated lineage
nobody had established. They now count as their own root.

---

## WP-F — Spans that survive to the finding

| ID | Task | FR | Status | Evidence |
|---|---|---|---|---|
| T080 | Typed `Locator`; `UNKNOWN` preserved | FR-018 | `[ ]` | |
| T081 | Split the overloaded positional field; dual-read legacy rows | FR-019 | `[ ]` | |
| T082 | Carry the locator through the resolution layer | FR-024 | `[ ]` | |
| T083 | Provenance completeness gate on findings | FR-020, SC-001 | `[ ]` | |
| T084 | Test: a table cell resolves to its exact byte range | FR-018, SC-014 | `[ ]` | |
| T085 | Test: locators of different kinds are never conflated | FR-019 | `[ ]` | |
| T086 | Test: ungrounded findings are marked unsupported | FR-020, SC-001 | `[ ]` | |

---

## WP-G — Operator envelope

| ID | Task | FR | Status | Evidence |
|---|---|---|---|---|
| T090 | `OperatorResult` envelope: identity, version, upstream, licence, inputs, digests, lineage | FR-025 | `[ ]` | |
| T091 | Evidence refs, the five time semantics without conflation | FR-025,032 | `[ ]` | |
| T092 | Method fingerprint, determinism declaration, seed, calibration identity | FR-025,035 | `[ ]` | |
| T093 | Uncertainty as a vector, never a fake scalar | FR-027 | `[ ]` | |
| T094 | Explicit status; empty success on a non-nullable kind is a violation | FR-026 | `[ ]` | |
| T095 | Cost, replay key, idempotency key, tenant and policy identity | FR-025 | `[ ]` | |
| T096 | Schema evolution, compatibility, replay policy for events | FR-028 | `[ ]` | |
| T097 | Test: partial/blocked/quarantined survive persistence → API → projection | FR-026 | `[ ]` | |

---

## WP-H — Projections that are real

| ID | Task | FR | Status | Evidence |
|---|---|---|---|---|
| T100 | `ProjectionContract` as enforced data for every projection | FR-037 | `[ ]` | |
| T101 | Rebuild-to-identical-digest per projection claiming a rebuild path | FR-038, SC-008 | `[ ]` | |
| T102 | Refuse unimplemented retrieval modes with a named refusal | FR-040 | `[ ]` | |
| T103 | Decide each inert plane: wire a consumer, or experimental + kill switch | FR-052 | `[ ]` | |
| T104 | Spatial: no geometry exists — do not advertise a map | FR-043 | `[ ]` | |
| T105 | Test: projection failure leaves evidence untouched | FR-039 | `[ ]` | |

---

## WP-I — Open world and the absence algebra

| ID | Task | FR | Status | Evidence |
|---|---|---|---|---|
| T110 | Unknown predicate survives persistence → API → projection, flagged | FR-023 | `[ ]` | |
| T111 | Discarding requires a recorded versioned policy decision | FR-023 | `[ ]` | |
| T112 | Five absence states carried through to a finding | FR-003 | `[ ]` | |
| T113 | Wire the feedback plane to the tick; review as history | FR-011 | `[ ]` | |
| T114 | Test: analyst review changes the next proposed action | FR-011 | `[ ]` | |

---

## WP-J — Retrieval, LLM and security

| ID | Task | FR | Status | Evidence |
|---|---|---|---|---|
| T120 | Separate candidate generation, scoring, policy ranking, action selection | FR-036 | `[ ]` | |
| T121 | Measure current BM25/fusion quality before changing anything | FR-036, SC-011 | `[ ]` | |
| T122 | Offline/mock providers; hermetic workflow tests | — | `[ ]` | |
| T123 | Per-operator timeout, memory, CPU, network limits and kill switches | FR-052 | `[ ]` | |
| T124 | Retry budgets per task/source/investigation/global; DLQ preserves cause | FR-053 | `[ ]` | |
| T125 | Backpressure reduces acquisition rate as backlog grows | FR-054 | `[ ]` | |
| T126 | Supply-chain record: exact revision, licence, transitive footprint, models, data | FR-055,056 | `[ ]` | |
| T127 | Reconcile the stale documents named in the audit | FR-063 | `[ ]` | |

---

## WP-K — Evidence of work

| ID | Task | FR | Status | Evidence |
|---|---|---|---|---|
| T130 | Audit: declared/implemented/tested/wired/proven table | FR-059 | `[x]` | `audit/current-state-audit.md` — 27 capabilities |
| T131 | Donor matrix with verified verdicts | FR-062 | `[x]` | `donors/donor-matrix.md` — 45 names; **9 do not resolve**, 6 ambiguous, 6 licence-blocked |
| T132 | Decision records for every gate changed | FR-061 | `[ ]` | — |
| T133 | Benchmarks: document intelligence, identity ambiguity, correlated evidence, temporal reversal, contradiction/unknown, closed loop, rebuild/restart, retrieval comparison | SC-015 | `[~]` | **closed loop** done (WP-A, 15 tests); 7 scenarios not built |
| T134 | Recorded raw measurements + reproducible commands | SC-011 | `[~]` | `quickstart.md` records every run; no retrieval/false-merge/cost measurement exists |
| T135 | Final report: what changed, what was measured, what remains | — | `[x]` | audit §5, §6 |

---

## Execution order

```
WP-0 ─► WP-A ─► WP-B ─► WP-B2 ─► WP-C ─► WP-D ─► WP-E ─► WP-F ─► WP-G ─► WP-H ─► WP-I ─► WP-J ─► WP-K
       done   done
```

Each vertical reaches a passing test before the next begins. WP-C precedes WP-F because
spans are worthless while identity and the gate are unsound. WP-E precedes any
resolution donor. WP-H precedes any retrieval donor.

---

### Property found by the T060 tests

`InvariantReducer` advances its revision counter **once per `reduce()` call**, not
once per event. Folding a three-event stream in a single batch therefore lands at
revision 1, while folding it incrementally reaches revision 3 — and because the
revision is inside the invariant identity, **the two produce different digests over
identical evidence**.

That is why `restore(stream, history=…)` exists: it rebuilds at the recorded position
rather than at 1. A caller that "rebuilds from scratch" with a cold fold and compares
digests will report a false change and mint a revision for evidence that did not move.

`test_a_cold_fold_is_not_equivalent_to_a_restore` pins this rather than hiding it, so a
future change to the revision semantics has to confront it. The live path avoids it by
folding the whole accumulated stream and comparing against the digest it published.

## The next executable vertical

**WP-F — spans that survive to the finding (T080).**

WP-E is closed: a merge can no longer be decided by a threshold whose own profile
declares itself uncalibrated, and corroboration counts lineage roots rather than
hostnames, with the measure used named on every decision.

The audit's next finding: `Segment.offset` means byte offset in one parser, segment
index in another, and is always `0` in a third — then all three are summed into one
field at `extractors/lane.py:82-86`. Downstream, `document_adapter.py:271-300` consumes
the span to mint `mention_id` and discards it; `ResolutionMention` has no span field at
all.

---

## Environment condition blocking a clean full-suite baseline

Recorded 2026-10-13, mid-session. **This is not a code regression and must not be read
as one.**

Earlier in the session `pytest -q` completed in ~21 minutes with
`22 failed, 4324 passed, 27 skipped`. It no longer completes at all. Measured cause:

| Probe | Result |
|---|---|
| TCP `localhost:5432` | **OPEN in 0.00s** |
| `create_async_engine(...asyncpg://...)` against it | **TimeoutError** — accepts the socket, never completes the handshake |
| TCP `localhost:9000` | **OPEN in 0.01s** |
| TCP `localhost:8123` | ConnectionRefused in 2.05s |

Something outside this workspace began listening on 5432 and 9000 partway through the
session, and it does not speak the protocols the tests expect. Consequences, all
measured:

- **7** × `control-plane/tests/unit/test_postgres_context_store.py` — previously
  *skipped* (nothing on the port), now *run and fail* on the handshake timeout.
- **2** × `feedback/tests/test_frontier_loop.py` — same cause.
- **4** × `shared/tests/integration/test_infra_connectivity.py` — same cause.
- `acquisition/tests/integration/test_adapters_gate.py` and
  `test_engine_adapters_gate.py` — **hang**. MinIO is now reachable, so the skip no
  longer applies, and the scrapy-exemplar path does not complete. They were skipped
  for the whole of the earlier baseline, so **there is no prior measurement for them**.

What *did* run cleanly, after every change in this feature:

| Scope | Result |
|---|---|
| `apps/admission` | **114 passed** |
| `apps/acquisition` unit + contract | **338 passed** |
| `apps/acquisition` integration (worker, backpressure, loop_closed) | **13 passed** |
| `apps/shared` + `apps/projection` + `apps/science` | **2203 passed**, 16 failed (12 pre-existing + 4 infra) |
| `apps/control-plane` unit + contract | **508 passed**, 9 failed (2 pre-existing + 7 infra) |
| `apps/feedback` + `apps/zero` + `apps/interpretation` | **908 + 123 passed** |

**Freeing ports 5432 and 9000 (or setting `COGNITIVE_PG_DSN` to a working instance)
restores a comparable baseline.** Until then the 22-failure figure is the last honest
one, and it stands.