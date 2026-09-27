# Phase 0 Results and Review-Gate Verdict: 021-entity-relation-extraction-finalization

**Date**: 2026-09-27 | **HEAD**: `0056665 fixing extraction` | **Repo root**: `C:\Users\tim\Desktop\COGNITIVE\1`

---

## 1. T001 — Baseline, measured (not inherited)

All numbers from the previous report are **confirmed** by fresh runs. But the baseline is
**weaker than the totals suggest**, and that matters more than the confirmation.

| Suite | Result | Notes |
|---|---|---|
| `apps/shared` | **14 failed, 571 passed, 8 skipped** | 593 collected |
| `apps/control-plane` | **2 failed, 356 passed, 9 skipped** | both `test_donor_api` |
| `apps/interpretation` | **185 passed** | — |
| `apps/projection` | **189 passed, 1 skipped** | 190 collected |
| `apps/admission` | **96 passed** | — |
| `apps/acquisition` | **126 passed, 10 skipped** | all skips `minio unavailable` |
| `apps/science` | **164 passed** | — |
| `apps/zero` | **121 passed** | — |
| `apps/feedback` | **18 passed, 2 skipped** | skips `postgres unavailable` |
| `apps/bulk-ingestion` | **10 passed, 2 skipped** | skips `minio unavailable` |
| `bench` | **23 passed** | — |

### 1.1 The 16 known failures, itemised

**`apps/control-plane` (2)** — both `tests/integration/test_donor_api.py::TestDonorPatternApi`:
1. `test_entity_timeline_carries_observed_at` — timeline `observed_at` differs from the
   hardcoded literal. Fails in isolation, so it is a genuine fixture/serialisation mismatch.
   The sibling `test_entity_view_projects_identity_invariant` passes on the same literal, so
   the invariant projection and the timeline disagree about the timestamp.
2. `test_entity_can_be_created_as_dynamic_invariant` — the endpoint now returns `202 Accepted`;
   the test still asserts `200`.

**`apps/shared` (14)** — **3 are environment, not code**:
- `test_kafka_list_topics`, `test_redpanda_list_topics`,
  `test_minio_put_get_delete_content_addressed_probe` — Docker is down
  (`docker version` → cannot connect to `npipe:////./pipe/dockerDesktopLinuxEngine`).

**11 are genuine code failures**: 8 in `test_evidence_context.py`, 1 in
`test_evidence_lineage.py` (`test_t062_the_api_path_is_reachable_in_both_directions`), 2 in
`websearch/test_websearch.py`.

### 1.2 What the skips hide

**14 tests never executed and reported nothing.** They self-skipped instead of failing:

- 10 in `acquisition` (MinIO absent)
- 2 in `feedback` (Postgres absent)
- 2 in `bulk-ingestion` (MinIO absent)
- 1 in `projection` — `test_tantivy_backend.py` does a module-level
  `pytest.importorskip("tantivy")`, so the **entire file's** assertions about tenant
  isolation, idempotent writes and provenance enforcement never run
- 7 in `control-plane` need a live PostgreSQL/dev stack

**Consequence for this feature.** A green run proves `558 of 572` for the small apps, not 572.
The honest baseline line is:

> **16 failing tests, of which 3 are environment-caused; 22 additional tests never executed
> because their infrastructure is absent.**

Therefore: any DB-dependent verification in Phase 9 is `verified only offline`, and if Docker
is ever started the shared baseline changes to roughly **11 failed, 571 passed, 3 skipped**.
Re-baseline before trusting any comparison.

---

## 2. T002 — Alembic head: **CONFIRMED**

`alembic heads` → `020_universal_relation_extraction (head)`. Single linear chain
`None → 014 → 015 → 016 → 017 → 018 → 019 → 020`, no branches, no successor. Alembic 1.19.2.

`020` is committed in `0056665` and its working-tree copy is byte-identical.

`020`'s `downgrade()` raises `NotImplementedError`, and its docstring names the remedy
explicitly:

> *"Rolling back is a forward operation: add revision 021 that states what the schema becomes
> instead."*

**Correction to my own plan.** I described `020` as forward-only as a *fact I verified*. It is
a fact — but the reason it is forward-only is a **constitutional argument**, not a technical
limitation: dropping `relation_candidate` "would be the only operation in the platform able to
remove a consideration, on the strength of a schema version number". `021` inherits that
obligation: it must not drop what `020` was created to protect.

---

## 3. T003 — Parser determinism: the stated worry was misplaced

**Both parsers are byte-reproducible.** Two separate process invocations, and runs under
`PYTHONHASHSEED=0` and `12345`, produced identical digests (`2157C0CE…`). The threat is not
nondeterminism.

**The real threat is parser-dependent DOM shape.** Measured divergence on a fixed fixture:

| Case | `selectolax` | `bs4`/lxml | Consequence |
|---|---|---|---|
| Mis-nested `<b><i>…</b>…</i>` | **invents a second `<i>`** as a sibling of `<b>` | discards the stray close tag; `italic` becomes bare text in `<p>` | a producer keying on tag structure yields different output for the same bytes |
| `<table><tr>` with bare `<tr>` | **silently injects `<tbody>`** (72 nodes vs 70) | keeps `<tr>` directly | a selector `table > tr` works under bs4 and **returns nothing** under selectolax |
| Unclosed `<td>` | auto-closes; both `b1`/`b2` preserved | identical | cell-text extraction is safe |
| Ragged row (1 cell vs 3 header) | kept unpadded | kept unpadded | a positional join will misalign or raise — **must be handled explicitly** |
| `rel="nofollow"` | `"nofollow"` (str) | `["nofollow"]` (list) | any digest must normalise attribute value types |

Two further facts Phase 6 needs:
- **`selectolax` `Node.text` is a method, not a property.** `node.text` returns a bound method.
- **`apps/interpretation/parsers/html_full.py` uses neither DOM nor regex** — it delegates to
  `trafilatura` (lxml-based) and recovers offsets by a 4-token `str.find` probe, which is a
  *heuristic*, not a source position. Any change to how segments are produced **moves these
  offsets and therefore shifts any golden corpus that records them.**
- `selectolax` is already in production use at `apps/interpretation/parsers/structured.py:16`.

**Correction to my own research.md.** I wrote that parser choice was "forced" toward
`selectolax`. The measurement shows the forcing is weaker than I stated: both parsers are
deterministic, and the real argument is the `<tbody>` injection and the existing
`structured.py` precedent — not determinism.

---

## 4. Review gates: **FAIL** (three independent reviews)

All three adversarial reviews returned a fail verdict against my own artefacts.

### 4.1 Mechanical defects

| # | Finding | Evidence |
|---|---|---|
| D1 | **52 of 102 FRs have no implementing task and no checklist item** | measured by set difference |
| D2 | **`FR-103` is cited by 4 places and does not exist** | it is brief §103 "DO NOT CREATE A FOURTH EPISTEMIC LEVEL", misread as an FR |
| D3 | **18 of 50 FR citations point at an unrelated FR** | e.g. T011 `PredicateSignature` cites FR-020 ("producers import no graph symbol") |
| D4 | **The checklist cites 5 task IDs that do not exist** — `T007c`, `T007f`, `T011a`, `T011c`, `T012d` | the entire mutation apparatus and the graph-projection invariant are gated on phantoms |
| D5 | **The checklist maps zero of the 102 FRs** — it has no FR column and cites only FR-081 and FR-082 | T004 required an FR map; it was not delivered |
| D6 | **`SC-001`, the feature's headline success criterion, has no enabling requirement** | nothing obliges the producer to voice-normalise role bindings or canonically order participants, so active/passive collapse is not achievable by any task |
| D7 | **§8 (entity extractor expansion, 170 lines, 7 mandatory sub-sections) is dropped entirely** | `Cyrillic`, `github.com`, `CVE`, `persons.py` appear zero times in every artefact. Yet FR-030 mandates 32 type classes with no producer obligation |
| D8 | **29 of §108's 47 acceptance bullets have no success criterion** | all 9 entity-substrate bullets, all 5 lifecycle bullets, all 4 boundedness bullets |
| D9 | **Three of eight hard prohibitions have no enforcing test** | §72's O(N²) mutation, §74's six-symbol import test, §30's parser-free baseline |
| D10 | **`input.md` is 4898 lines, not the 3411 the spec header claims** | the "all 115 sections cited" traceability claim rests on a mis-measured file and a `§N` string-match, which passes citation without content |
| D11 | **1006 inline `FR-0xx` citations exist in the code**, in 019-era numbering, unreconciled | a reader following any code comment lands on the wrong requirement |
| D12 | **The MVP is unbuildable** — Phases 0→1→2→5 skips Phase 4, which Phase 5 requires | `tasks.md` self-contradiction |
| D13 | **T006 (Phase 1) depends on T020 (Phase 3), a backwards edge** | T020 is mention-index wiring; the intended task is T029 (Phase 5) |
| D14 | **T023 cites FR-011 in order to violate it** | FR-011 mandates a `TEMPORAL` member; T023 forbids it |
| D15 | **§110's Phase 2 is "atomic entity type vocabulary"**, but tasks.md Phase 2 is `PredicateSignature`/`Polarity`/`RelationParticipant`, all of which §110 puts in Phase 5 | 4 of 12 phases are silently narrowed |
| D16 | **Phase 4 cannot be committed green** — T022 breaks 7 construction sites and T023 breaks 12 enum references across Phases 6, 7, 8, 11 | while `tasks.md` says "never bundle a phase boundary" |

### 4.2 Factual errors in my artefacts

| # | Where | What I claimed | Reality |
|---|---|---|---|
| E1 | `data-model.md` N5 | `owns ≡ controls` as the worked synonym example | **forbidden by FR-004, by §20, by `US2` Acceptance 3, and by constitution INV-3.** The signature's `normalized_predicate` is the predicate term of `logical_candidate_id`, so a synonym table is an identity authority |
| E2 | `data-model.md` / T013 | `role: str` free text inside `logical_candidate_id` | **relocates the exact defect the feature exists to destroy.** `purchaser` vs `buyer` forks the logical id |
| E3 | `data-model.md` §6 / T017 | `TypeHypothesis` redefined as a container of `TypeCandidate`s | a new epistemic level, contradicting §103's nested-value-object list (which names four types and pointedly not this one) |
| E4 | `data-model.md` | "seven levels are never collapsed" then lists **nine** | arithmetic error in the document's own header |
| E5 | `data-model.md` N5 fallback | "`AMBIGUOUS`" = two signatures | FR-028 requires **one** logical hypothesis with alternatives. Two signatures = two candidates |
| E6 | T025 / spec.md:47 | replace the function `signal_asserts_nothing` | it is a **string error code**, raised from `__post_init__` at `signal.py:344` |
| E7 | T034 / spec.md:72 | `is_exhaustive` reads `"exact"` | it tests for **`"exhaustive"`**. The premise is false; the real defect is only the human-readable string |
| E8 | spec.md / data-model.md | `assembly.py:338` is the hand-sort | it is **`:253`**. `:338` is inside `_arity_of` |
| E9 | T010 | `valid_from`/`valid_to` "passed by both callers" | `relation_candidate.py:1132` does **not** pass them; the omission is also documented as deliberate at `relation_identity.py:171` |
| E10 | T007 | round-trip `direction`, `polarity`, `alternative_refs`, `mapping_evidence_refs` as candidate fields | **none of the four is a `RelationCandidate` field**; FR-088 says they do not exist yet |
| E11 | T019 | mention id minted on `(segment, kind, value, start, end, extractor)` | **omits `capture`**, which FR-018 requires — two captures of one segment collide onto one mention id |
| E12 | spec.md:810 | "§1B" exists | no such section; §1 has unnumbered subsections A and B |
| E13 | `data-model.md` | "fails the constitution's determinism requirement (VI)" | **there is no Principle VI determinism requirement.** VI is *Process-Centric* |
| E14 | `plan.md` Constitution Check | row "VI determinism" | cites VI, which is Process-Centric |
| E15 | `plan.md` Constitution Check | row "IV tenancy" | tenancy is **VII** (Security-First); IV is "No Single Store / Graph / Score". Inherited from the code's own mis-cite at `protocol.py:299` |

### 4.3 Constitutional defects in the gate itself

| # | Finding |
|---|---|
| K1 | **`plan.md`'s Constitution Check omits 5 of the 7 Core Principles** — I, II, V, VI, VII have no row. It mis-cites 2 of the 7 it has |
| K2 | **The gate marks `PASS` on the supersession clause that `plan.md` itself inverts.** The constitution says "Constitution supersedes all other practices". `plan.md` and `spec.md` both state the brief "governs over this document". The worked example given for `PASS` (§45) is a case where they *agree* |
| K3 | **Principle VI (Process-Centric) has no counterpart in the brief, so the constitution plainly wins** — yet the plan wires the **entity** pipeline (`POST /api/v1/entities`) while the constitutionally-named `InvestigationWorkflow` is unregistered and calls two activities that exist nowhere. The plan routes around the conflict without recording it |
| K4 | **Governance: "Compliance is verified on every PR/review"** — there is no CI, and the plan accepts a manual gate for a 74-task constitutional change |
| K5 | **Governance requires an ADR for architectural changes including "entity resolution"** — the N5 synonym table is entity-resolution-grade, creates no ADR, and has no slot in `FR-083`'s A–K list |
| K6 | **Migration `021` is specified to ADD columns only.** It must also **DROP** `ck_relation_signal_asserts_something` and `ck_relation_candidate_asserts_something`, which enforce `relation_surface <> '' OR relation_ref IS NOT NULL` — the constraint `FR-013` says MUST be replaced — and must update `ck_relation_signal_kind`'s whitelist for the removed `SignalKind` members. No artefact says so, so `SC-012` is unachievable as planned |
| K7 | **Evidence-First is violated and the plan prints the defect in its own structure listing**: `evidence_lineage.py`'s `EVIDENCE_BACKWARD_CHAIN` has no `CANDIDATE` and no `ENTITY` hop, while `US9` promises to walk an edge to its source |

### 4.4 What is correct and needs no change

- The brief's §20 vs constitution INV-3 alignment on "no semantic equivalence by similarity" —
  the plan's *gate* was right to be suspicious, its *design* was not.
- The bounded `core:*`/`value:*` vocabulary as a mapping instrument and never a gate:
  **constitutionally sound and well-argued** (`FR-034a`, `INV-002`, `data-model.md` §6).
- `GraphProjectionBridge` typed `claim: RelationClaim` with no overload — the constitution
  holds at the type level, and T058 correctly locks it.
- `relation_surface` demoted to evidence while staying a durable `Text` column: correct, and
  consistent with Principle II and INV-1.
- The "verified / verified only offline / known limitation / deferred" reporting discipline.
- Migration discipline: `021` on top of a forward-only `020`, with parity test-enforced.

---

## 5. Verdict

**Implementation must not start.** The review-spec, review-plan and review-tasks gates all
fail, and two of the failures are constitutional rather than cosmetic:

1. `SC-001` — the reason this feature exists — is **unachievable by any task in the file**,
   because role-binding normalisation and canonical participant ordering are specified nowhere.
2. The plan **subordinates the brief to itself in a way the constitution forbids**, and its own
   gate row for that clause is marked `PASS` on a worked example where they agree.

Correcting these is not a patch. It requires deciding scope on at least six open questions, so
the fixes are enumerated in the report rather than applied unilaterally.
