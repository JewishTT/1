# Tasks: Closed Research Loop with Versioned Evidence Contracts

**Feature**: 028-closed-research-loop
**Plan**: [plan.md](./plan.md) · **Data model**: [data-model.md](./data-model.md)
**Audit**: [audit/current-state-audit.md](./audit/current-state-audit.md)

Status vocabulary, consistent with spec 026:

- `[x]` delivered **and verified by a run recorded in this file**
- `[~]` partially delivered — the stated part works, the rest does not
- `[!]` blocked — the reason is named
- `[ ]` open

**A `[x]` requires the command and its result in this file. A task list entry is not
evidence.** This is `FR-049`, and it exists because the audit found seven tasks
marked complete whose implementation does not exist at the claimed path.

---

## WP-0 — Trustworthy baseline (blocking)

| ID | Task | Status | Evidence |
|---|---|---|---|
| T001 | Record commit, branch, dirty-tree state | `[x]` | `608c3ad8f4743e4e729807c903b0364ed571b311`, `main`, 117 dirty entries |
| T002 | Record the real test result | `[x]` | `pytest apps -q --ignore=bench` → **22 failed, 4273 passed, 27 skipped**, 1097.95s |
| T003 | Record the root-collection failure | `[x]` | `pytest -q` → **831 collection errors** (vendored `donors/`, `tmp/`; no `testpaths`) |
| T004 | Record the `bench` collection error | `[x]` | `bench/tests/test_harness.py` → `ImportError: cannot import name 'harness' from 'bench'` |
| T005 | Triage the 22 failures by cause | `[x]` | `audit/current-state-audit.md` §1 — 14 in 3 files, 8 independent |
| T006 | Set `testpaths` so vendored trees are not collected | `[x]` | `pytest --co -q` → **4336 collected, 0 collection errors** |
| T007 | Fix `bench` package shadowing | `[x]` | deleted the 2-byte `bench/__init__.py`; `pytest` from `bench/` → **21 passed, 2 failed** |
| T008 | Publish the single regression command + floor | `[x]` | `pytest -q` → **22 failed, 4288 passed, 27 skipped**; see `quickstart.md` |

---

## WP-A — Make the loop closable

| ID | Task | Status | Evidence |
|---|---|---|---|
| T010 | Supply saturation from the fabric's completeness assessment on the live path | `[x]` | `context_engine/loop.py:394-406` — `to_engine_saturation` feeds `_reevaluate` |
| T011 | Convert the fabric's saturation verdict into an engine-readable state | `[x]` | `context_engine/fabric_bridge.py` `to_engine_saturation()`; unknown stays unknown |
| T012 | Deliver the termination reason to the caller on every path | `[x]` | `loop.py:490-520` `_stop_reason`; `TickReport.loop_status` + `.stop_reason` |
| T013 | Carry analyst feedback into the tick | `[ ]` | WP-H — the feedback plane has no production caller |
| T014 | Suppress a repeat action that produced no gain until a stated condition changes | `[ ]` | WP-A second half — `_attempt_key` exists, suppression is not wired |
| T015 | Integration test: obligation open → satisfied → loop stops with a named reason | `[x]` | `test_an_obligation_reaches_a_terminal_state_from_evidence`, `test_a_saturated_tick_carries_a_reason` |
| T016 | Test: blocked obligation names the missing capability | `[x]` | `test_a_blocked_tick_names_the_stalled_obligations` |
| T017 | Test: contradiction keeps the obligation open | `[x]` | `test_a_contradiction_keeps_the_obligation_open` |
| T018 | Engine saturation can express "not measured" | `[x]` | `obligations.py:51` — `coverage_known`, `marginal_gain_known`; 6 tests incl. backward compat |
| T019 | Re-run the full suite; confirm no new failures | `[x]` | 22 failed (identical set), 4288 passed = 4273 + 15 new |

---

## WP-B — Durable decision record

| ID | Task | Status | Evidence |
|---|---|---|---|
| T020 | `research_decisions` table + migration M1 | `[ ]` | |
| T021 | `ContextStore` decision methods; `DecisionRecorder` off the in-memory list | `[ ]` | |
| T022 | Content-address `decision_id` over grounds/inputs/alternatives/actor/outcome | `[ ]` | |
| T023 | Contract test on a real database: record → restart → retrieve → compare | `[ ]` | |

---

## WP-C — One gate, one identity, atomic enough to be honest

| ID | Task | Status | Evidence |
|---|---|---|---|
| T030 | Route the three bypassing producers through the gate | `[ ]` | |
| T031 | Refuse to publish an observation whose bytes were not stored | `[ ]` | |
| T032 | Collapse four identity derivations into one; v2 schema; v1 dual-read | `[ ]` | |
| T033 | Replace the random default event id; invert the test that pins it | `[ ]` | |
| T034 | Count and surface dropped runtime artefacts instead of `continue` | `[ ]` | |
| T035 | Persist the capture record instead of discarding it | `[ ]` | |
| T036 | Document the four failure windows and their repair paths | `[ ]` | |
| T037 | Test: every production observation resolves to stored bytes | `[ ]` | |
| T038 | Test: redelivered event ⇒ one logical observation, no independence inflation | `[ ]` | |
| T039 | Test: tenant-empty refusal on the envelope | `[ ]` | |

---

## WP-D — Accumulated state, digest-gated revision

| ID | Task | Status | Evidence |
|---|---|---|---|
| T040 | Wire the incremental reducer into the live materialization path | `[ ]` | |
| T041 | Retire unconditional revision minting per sweep | `[ ]` | |
| T042 | Make `CURRENT` a distinct query; expose `INTERVAL` alongside `AS_OF` | `[ ]` | |
| T043 | Fixture test: current / as-of / interval all differ | `[ ]` | |
| T044 | Test: a late-arriving record does not rewrite the as-of past | `[ ]` | |
| T045 | Test: restart reproduces the accumulated digest exactly | `[ ]` | |

---

## WP-E — Admission without uncalibrated auto-merge

| ID | Task | Status | Evidence |
|---|---|---|---|
| T050 | Refuse auto-merge when `calibration_id` is null | `[ ]` | |
| T051 | Replace hostname corroboration with dependency groups at the live call site | `[ ]` | |
| T052 | Give the zero-layer matcher accept/reject/defer; stop defaulting threshold to zero | `[ ]` | |
| T053 | Test: copies of one source do not raise the independence count | `[ ]` | |
| T054 | Test: merge with a null calibration routes to review, never to merge | `[ ]` | |

---

## WP-F — Spans that survive to the finding

| ID | Task | Status | Evidence |
|---|---|---|---|
| T060 | Typed `Locator`; `UNKNOWN` preserved | `[ ]` | |
| T061 | Split the overloaded positional field; dual-read legacy rows | `[ ]` | |
| T062 | Carry the locator through the resolution layer | `[ ]` | |
| T063 | Provenance completeness gate on findings | `[ ]` | |
| T064 | Test: ungrounded findings are marked unsupported, never presented as grounded | `[ ]` | |
| T065 | Test: a table cell in a fixture resolves to its exact byte range | `[ ]` | |
| T066 | Test: locators of different kinds are never conflated | `[ ]` | |

---

## WP-G — Projections that are real

| ID | Task | Status | Evidence |
|---|---|---|---|
| T070 | `ProjectionContract` as enforced data for every projection | `[ ]` | |
| T071 | Rebuild-to-identical-digest test per projection claiming a rebuild path | `[ ]` | |
| T072 | Refuse unimplemented retrieval modes with a named refusal | `[ ]` | |
| T073 | Decide topological analysis: wire a consumer, or mark experimental + kill switch | `[ ]` | |
| T074 | Decide spatial: there is no geometry; do not advertise a map | `[ ]` | |
| T075 | Test: projection failure leaves evidence untouched | `[ ]` | |

---

## WP-H — Close the loop from analyst review

| ID | Task | Status | Evidence |
|---|---|---|---|
| T080 | Wire the feedback plane to the tick | `[ ]` | |
| T081 | Record review actions as history; never overwrite raw | `[ ]` | |
| T082 | Surface unknown / uncovered / blocked / conflicting in the analyst view | `[ ]` | |
| T083 | Test: analyst review changes the next proposed action | `[ ]` | |

---

## WP-I — Open world

| ID | Task | Status | Evidence |
|---|---|---|---|
| T090 | Unknown predicate survives persistence → API → projection, flagged | `[ ]` | |
| T091 | Discarding requires a recorded versioned policy decision | `[ ]` | |
| T092 | Test for T090 and T091 | `[ ]` | |

---

## WP-J — Evidence of work

| ID | Task | Status | Evidence |
|---|---|---|---|
| T100 | Audit document with the declared/implemented/tested/wired/proven table | `[x]` | `audit/current-state-audit.md` — 27 capabilities classified |
| T101 | Donor matrix with verified verdicts and exact revisions | `[x]` | `donors/donor-matrix.md` — 45 names; **9 do not resolve**, 6 ambiguous, 6 licence-blocked |
| T102 | Decision records for every gate changed | `[ ]` | — no constitution-level gate was changed by WP-0/WP-A; the additive `*_known` fields are documented in `data-model.md` §4 |
| T103 | Benchmark suite: document intelligence, identity ambiguity, correlated evidence, temporal reversal, contradiction/unknown, closed loop, rebuild/restart, retrieval comparison | `[~]` | **closed loop** done (WP-A, 15 tests). The other 7 scenarios not built. |
| T104 | Recorded raw measurements + reproducible commands | `[~]` | `quickstart.md` records every run. No retrieval/false-merge/cost measurement exists. |
| T105 | Reconcile the stale documents named in the audit | `[ ]` | 5 documents listed in `audit/current-state-audit.md` §4 — **not started** |
| T106 | Final report: what changed, what was measured, what remains | `[x]` | session report; `audit/current-state-audit.md` §5 and §6 |

---

## Execution order and why

```
WP-0 ──► WP-A ──► WP-B ──► WP-C ──► WP-D ──► WP-E ──► WP-F ──► WP-G ──► WP-H ──► WP-I ──► WP-J
        │        │        │        │        │        │        │
        └────────┴────────┴────────┴────────┴────────┴────────┘
                          every vertical must reach a passing test
                          before the next one starts
```

WP-A is first because the loop that cannot close is the defect that makes every other
capability unmeasurable. WP-C precedes WP-F because spans are worthless while identity
and the gate are unsound. WP-E precedes any resolution donor. WP-G precedes any
retrieval donor.

**Deliberately not started, and why**: no donor integration task appears above.
The audit's evidence is that the platform's central invariants — one gate, one
identity, an accumulated state, a groundable chain — are currently violated by the
platform's own code. Adding producers multiplies the violation. `donors/donor-matrix.md`
records the verification; integration waits until the invariants hold.

---

## The one executable vertical right now

**T010 → T011 → T012 → T015. Done.** The saturation basis is now the measured one, the
loop reaches a terminal state, and the reason reaches the caller. 15 tests, zero
regressions, one command.

## The next executable vertical

**WP-C: one gate, one identity.** `T030` → `T031` → `T032`.

Three producers currently publish observations the platform cannot resolve to bytes,
and four identity schemes disagree about what an observation is — one of them a random
UUID. Until that is fixed, any donor that adds a producer (Docling, GROBID, Redpanda
Connect, Browsertrix) multiplies a violation that already has three instances.

Start with `T031`: refuse to publish an observation whose bytes were not stored. That
single check closes the `sources/connector.py:161` hole, which is the worst of the
three, and it is a small, independently testable change.