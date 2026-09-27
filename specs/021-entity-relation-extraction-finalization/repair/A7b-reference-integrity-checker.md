# A7b — Reference Integrity Checker

**Job**: A machine gate so that a phantom reference like `FR-103` can never pass a review
again.

**Deliverables**

| File | Purpose |
|---|---|
| `repair/tools/reference_check.py` | the checker (2 586 lines, standard library only) |
| `repair/tools/test_reference_check.py` | 71 pytest tests for the checker itself (882 lines) |

Nothing else was touched. `spec.md`, `plan.md`, `data-model.md`, `tasks.md`,
`checklists/requirements.md`, `research.md`, `input.md` and every `apps/` file are byte-identical
to the state this job received them in.

---

## 1. Design

### 1.1 Why this is a separate tool and not a test

A test asserts the *code* is right. This asserts the *documents agree with each other*. It
has to be a standalone script because:

- it must run on broken markdown, where a markdown-aware test fixture would itself fail to
  parse and take the report down with it;
- it must be runnable by a repair pass that is not allowed to touch product code;
- its output is a *report for a human*, with per-check totals a reviewer can diff between
  passes, not an assertion.

### 1.2 Artefact set

| Role | Files |
|---|---|
| **scanned** (citations are extracted from these) | `spec.md`, `tasks.md`, `plan.md`, `research.md`, `data-model.md`, `checklists/requirements.md` |
| **authority** (referenced, never scanned) | `input.md` — the governing brief; its numbered headings are the only valid `§N` targets |
| **optional** (`--all-artefacts`) | `phase0-results.md` — a prior *review report*, not a spec artefact. It quotes the phantom ids it is complaining about, so scanning it by default would double-count them. See §5.3 for the numbers with it included. |
| **constitution** (auto-discovered) | `.specify/memory/constitution.md`, found by walking up from the feature directory |

Any other file can be added with `--artefact <relpath>`.

### 1.3 Pipeline

```
bytes ──► read_artefact()      undecodable / missing / empty  ──► finding, never exception
      ──► parse_definitions()  spec.md  - **FR-nnn**: / **SC-nnn**: / **INV-nnn**:  (+ occurrence list
                                 so a requirement defined twice stays visible)
      ──► parse_tasks()        tasks.md  - [ ] Tnnn
      ──► parse_checklist()    header-driven: a row is a gate row when its table declares a Task column
      ──► parse_input_sections()  input.md numbered headings; lettered subsections become *hints*,
                                    never valid citation targets
      ──► collect_references() per-token file:line index, deduplicated
      ──► collect_sections()   §N, §N–§M ranges, and §N-k phase qualifiers (base only)
      ──► 25 checks, each wrapped in try/except → check-crashed finding
      ──► summarize()          per-check-ID totals → text | JSON
```

Three design decisions worth naming:

1. **Fenced code blocks are skipped** by the heading walker and the task parser, so a
   `` ``` `` block containing `- [ ] T001` or `# 4. FOO` cannot invent a definition or a
   section.
2. **`§110-8` is a phase qualifier, not a range.** The trailing number is smaller than the
   base, so only §110 is validated and §8 is *not* marked as cited. This bug existed in an
   earlier revision of the tool and it silently hid §8 from `RI-08b`; the test
   `test_phantom_section_is_not_synthesised_from_an_unnumbered_subsection` and the manual
   cross-check below are what caught it.
3. **A definition's body is its whole bullet, continuation lines included, stopping at the
   next definition or heading.** Count-claim rules resolve their context to that body rather
   than to a ±N line window, which is what keeps one claim from being counted seven times.

### 1.4 Robustness

Every failure mode is a finding, not a traceback:

| Input | Result |
|---|---|
| missing file | `RI-00-INPUT / missing` (FAIL) |
| non-UTF-8 bytes | `RI-00-INPUT / unreadable`, text decoded with `errors="replace"` |
| empty file | `RI-00-INPUT / empty` |
| a check that raises | `RI-00-INPUT / check-crashed` (FAIL) with the exception type |
| a Windows cp1251 console | stdout/stderr reconfigured to UTF-8 with `errors="replace"` |
| a corrupt `--compare` baseline | `comparison.error` in the payload; the run still completes |

All six are covered by tests. `ruff check` is clean on both files under the repo's own
`ruff.toml` (`E,F,I,B,UP`, line-length 100).

---

## 2. CHECKS — every check ID, its rule, and its severity

Severity meanings: **FAIL** blocks the gate (exit 1). **WARN** is advisory and never
non-zero. **INFO** is a review prompt, including the "this claim verified" receipts.

| Check ID | Rule | Default severity |
|---|---|---|
| **RI-00-INPUT** | Every scanned and authority file exists, decodes as UTF-8 and is non-empty. A missing constitution is WARN (the check then cannot run in that workspace). | FAIL / WARN |
| **RI-01-FR-DEF** | Every `FR-nnn` / `FR-034a` token in any artefact resolves to exactly one `- **FR-nnn**:` definition in `spec.md`. Cited-but-undefined and defined-twice are both FAIL. | FAIL |
| **RI-01b-FR-SHAPE** | One base id may carry at most one letter suffix (`FR-034` + `FR-034a` is fine; two suffixes on one base is not). An unpadded `FR-34` is WARN — it can never match a definition. | FAIL / WARN |
| **RI-02-TASK-REF** | Every `Tnnn[a-z]` token cited anywhere resolves to a `- [ ] Tnnn` bullet. **A task bullet's own id is a definition, not a citation**; every other line in `tasks.md` — prose, the dependency graph, the open-questions table — *is* a citation. | FAIL |
| **RI-03-FR-ORPHAN** | An FR is an ORPHAN when `spec.md` defines it and neither `tasks.md` nor `checklists/requirements.md` references it. | FAIL |
| **RI-03b-FR-UNCITED** | Stricter: the FR is cited by *no* artefact at all — unreferenced prose wearing a requirement id. | FAIL |
| **RI-03c-FR-COLUMN** | The checklist declares an FR/requirement column and maps ≥ 1 FR. Reported as a distinct finding from the orphan count, per the brief. | FAIL |
| **RI-04-TASK-FR** | Every task cites ≥ 1 FR. A task with none cannot be traced to a requirement, so nothing can fail if it is wrong. | FAIL |
| **RI-04b-ROW-TASK** | Every checklist row names ≥ 1 task that exists in `tasks.md`. Free text (`existing suites`) is a FAIL: it cannot be run. | FAIL |
| **RI-04c-ROW-FR** | Every checklist row names ≥ 1 FR, reported per row plus one aggregate. | FAIL |
| **RI-04d-FR-OWNER** | Zero owner → FAIL (per-FR expansion of the orphan set, individually actionable). Two or more owners → WARN (no single blast radius). | FAIL / WARN |
| **RI-05-MISCITE** | Heuristic. An FR citation is SUSPECT when the citing line and the cited FR share **no** meaningful term. Terms = code spans, dotted paths, snake_case and CamelCase identifiers, ALL-CAPS enum members; FR/SC/INV/T/§ tokens are stripped first so a shared *reference* is never mistaken for shared *subject matter*; normative words (`MUST`, `only`, …) are stoplisted so they cannot manufacture agreement. Ranked, never a hard failure. | WARN |
| **RI-05b-INVERSE-CITE** | A citing line that forbids **adding** a member the cited FR places in a MUST-contain clause. Scoped to additive prohibitions on purpose: "Remove `NEGATION` from `SignalKind`" against an FR that mandates membership is a legitimate refactor of existing code, and flagging it would invert the check. | WARN |
| **RI-06-TASK-ORDER** | Task ids contiguous, ascending, and unsuffixed. A letter-suffixed id is by definition not in the file's definition set. | FAIL |
| **RI-06b-FR-ORDER** | FR numbers strictly increase **within** each requirement subsection, and across the document in file order. A gap, a rewind, or an FR bullet that dangles after a table (so it is grouped with nothing) is FAIL. | FAIL |
| **RI-07-SC-COVER** | Every `SC-nnn` is named by ≥ 1 checklist row. | FAIL |
| **RI-07b-INV-COVER** | Every `INV-nnn` is named by ≥ 1 checklist row. | FAIL |
| **RI-07c-ID-SHAPE** | An SC/INV citation that is not zero-padded to three digits (`INV-3`) will never match a canonical id — a silent phantom. | WARN |
| **RI-08-SEC-CITE** | Every `§N` cited in the six artefacts resolves to a numbered heading in `input.md`. Ranges are checked at both endpoints; `§N-k` at its base only. A missing target that matches an unnumbered subsection gets a hint naming the subsection the author probably meant. | FAIL |
| **RI-08b-SEC-UNCITED** | The reverse direction: `input.md` sections no artefact cites. | INFO |
| **RI-09-COUNT** | Prose count claims recomputed from the artefacts. See §2.1. A recomputable claim that disagrees is FAIL; a claim this checker has no counter for is INFO `count-unverifiable` or `count-section-scoped`, so the gap is visible rather than silent. | FAIL |
| **RI-10-FORBIDDEN** | Three shapes a repair pass must never reintroduce: (a) a synonym/equivalence rule inside the data-model's identity path, (b) a hypothesis nested inside a hypothesis, (c) a `core:*`/`value:*` vocabulary with no producer obligation anywhere. | FAIL |
| **RI-11-CONST** | A `CD-n` domain-invariant label that exists nowhere in the constitution is a phantom (the constitution's Domain Invariants are an *unlabelled* numbered list) → FAIL. A roman-numeral principle followed by a topic word must share a content word with that principle's real title → WARN. | FAIL / WARN |
| **RI-11b-RESEARCH** | Every `R-nnn` resolves to a `## R-nnn.` heading in `research.md`. | FAIL |
| **RI-12-STALE** | A line claiming a path is `NOT yet created` while the path exists → FAIL. A claim whose path genuinely does not exist is INFO `stale-claim-consistent` (the claim is true today). | FAIL |

### 2.1 The `RI-09-COUNT` counters

| Claim shape | Counter | Verified example |
|---|---|---|
| `N lines` next to a named artefact | `len(text.splitlines())` of that file | `3411` vs **4898** |
| `N lines` scoped to `§M` | heading-to-heading span, reported both ways | INFO, convention undefined |
| `N sections` next to `input.md` | numbered top-level headings | `115` ✓ |
| `N FRs` / `functional requirements` / `requirements` | FR definitions in `spec.md` | `102` ✓ |
| `N SCs` / `measurable outcome` | SC definitions | `16` ✓ |
| `N INV` / `constitutional invariant` | INV definitions | `5` ✓ |
| `N user stories` / `N stories` | `### User Story N` headings | `9` ✓ |
| `N members` | enum code spans in the declaring sentence; else the first column of the table directly below | `13` ✓ (twice) |
| `N levels` | items in the adjacent `→` chain, newline-joined | `seven` vs **9** |
| `N mutations` | MUTATION-titled sections inside the cited `§A–§B`, else the `§` refs in the same claim | `17` vs **6**; `Four` vs **6** |
| `≥ N invariants` near "mutation/harness/break" | comma-separated items in the harness FR's parenthesised field lists | `20` vs **18** |
| `N prefixes` | synthetic ref prefixes listed in `data-model.md` | 12 |
| `§A–§B` used as a mutation range | sections in range whose title is not a mutation section | `§100`, `§101` |

Two claims are deliberately *not* checked and are reported as unverifiable instead:
`SqlRelationClaimStore` "(558 lines)" in three places (a claim about `apps/`, not about the
artefact set) and "26 fields" / "31 fields" / "43 files" (claims about `apps/` source, which
this tool does not read). Saying so is more useful than guessing.

---

## 3. The real run

```
> .venv\Scripts\python.exe specs/021-entity-relation-extraction-finalization/repair\tools\reference_check.py
```

```
====================================================================================================
REFERENCE INTEGRITY CHECK  —  C:\Users\tim\Desktop\COGNITIVE\1\specs\021-entity-relation-extraction-finalization
tool v1.0.0   scanned: spec.md, tasks.md, plan.md, research.md, data-model.md, checklists/requirements.md
authority: input.md   constitution: found
====================================================================================================
verdict: 160 FAIL, 32 WARN, 30 INFO
```

**exit code 1.** 1 306 lines of report; `--json` is 107 KB of machine-readable payload with
the same numbers.

### 3.1 Per-check totals (this is the progress metric)

```
check id               FAIL   WARN   INFO   total   default severity
RI-00-INPUT               0      0      0       0   FAIL   (ran, no findings)
RI-01-FR-DEF              1      0      0       1   FAIL
RI-01b-FR-SHAPE           0      0      1       1   FAIL   (no FAIL)
RI-02-TASK-REF            9      0      0       9   FAIL
RI-03-FR-ORPHAN           1      0      0       1   FAIL
RI-03b-FR-UNCITED         0      0      0       0   FAIL   (ran, no findings)
RI-03c-FR-COLUMN          1      0      0       1   FAIL
RI-04-TASK-FR            23      0      0      23   FAIL
RI-04b-ROW-TASK          13      0      0      13   FAIL
RI-04c-ROW-FR            83      0      0      83   FAIL
RI-04d-FR-OWNER           1      1      0       2   WARN
RI-05-MISCITE             0     28      1      29   WARN   (no FAIL)
RI-05b-INVERSE-CITE       0      1      0       1   WARN   (no FAIL)
RI-06-TASK-ORDER          0      0      1       1   FAIL   (no FAIL)
RI-06b-FR-ORDER           3      0      0       3   FAIL
RI-07-SC-COVER            1      0      0       1   FAIL
RI-07b-INV-COVER          1      0      0       1   FAIL
RI-07c-ID-SHAPE           0      0      0       0   WARN   (ran, no findings)
RI-08-SEC-CITE            1      0      0       1   FAIL
RI-08b-SEC-UNCITED        0      0      1       1   INFO   (no FAIL)
RI-09-COUNT              10      0     23      33   FAIL
RI-10-FORBIDDEN           5      0      0       5   FAIL
RI-11-CONST               3      2      0       5   FAIL
RI-11b-RESEARCH           0      0      0       0   FAIL   (ran, no findings)
RI-12-STALE               4      0      3       7   FAIL
TOTAL                   160     32     30     222
----------------------------------------------------------------------------------------------------
exit: 1
```

25 distinct FAIL codes, 160 findings. **Checks that came back with no findings at all (4):**
RI-00-INPUT, RI-03b-FR-UNCITED, RI-07c-ID-SHAPE, RI-11b-RESEARCH. **A further 5 ran and
produced no FAIL:** RI-01b, RI-05, RI-05b, RI-06, RI-08b.

### 3.2 Every requested defect, with the real number

| Brief item | Required | Measured | Status |
|---|---|---|---|
| `FR-103` cited but undefined | caught | **1** phantom FR, **6** citations in 3 files | ✅ |
| `T007c`, `T007f`, `T011a`, `T011c`, `T012d` | caught | all 5 caught, **12** checklist rows gated on them | ✅ |
| orphan FRs | 52 | **52** of 102 | ✅ exact |
| checklist has no FR column | distinct finding | 1 (`columns found: #, item, method, state, task`) | ✅ |
| task ids contiguous/ascending, unsuffixed | verified | T001..T074, 74 ids, 0 gaps, 0 reorderings | ✅ **passes** |
| `§1B` does not exist | caught | 1, with the `B. Relation interpretation` hint | ✅ |
| `input.md` is 4898 not 3411 | caught | **2** claims, both wrong, in `spec.md:16` and `plan.md:99` | ✅ |
| `FR-079` says "Four", lists six | caught | 4 vs **6** | ✅ |
| `SC-015` ≥20, `FR-078` 18 | caught | 20 vs **18** | ✅ |
| "17 mutations from §94–§101" | caught | 17 vs **6**; plus 3 wrong mutation ranges | ✅ |
| synonym table in identity / nested hypothesis / vocabulary with no producer | caught | 3 + 1 + 1 | ✅ |

### 3.3 Findings not on the brief's list

1. **4 more phantom task ids, all in `tasks.md` itself.** `T009f`, `T010d`, `T010f`, `T013a`
   appear in the "Open questions blocking specific tasks" table (`tasks.md:268–270`). Total
   phantom tasks: **9**, not 5. These are invisible to a checker that only reads the
   checklist — the tool found them only after I changed `RI-02` to treat non-bullet lines in
   `tasks.md` as citations.
2. **`plan.md` lies about four of its own artefacts.** Lines 102–104 say `tasks.md`,
   `research.md` and `data-model.md` are "NOT yet created"; line 108 says
   `requirements.md` is (by bare basename, resolving to `checklists/requirements.md`). All
   four exist. The three "true" claims on the same listing (`quickstart.md`, `contracts/`,
   `adr/`) are reported INFO so the check does not merely look for things to complain about.
3. **Phantom constitutional labels: `CD-6` ×2, `CD-7` ×1.** The constitution's Domain
   Invariants are an unlabelled 1–12 list; there is no `CD-n` namespace at all.
4. **Two mis-cited principles.** `plan.md:85` labels Principle VI "determinism" (VI is
   *Process-Centric*); `plan.md:86` labels Principle IV "tenancy" (IV is *No Single Store /
   Graph / Score*; tenancy is under VII). This matters because the plan's own gate table
   marks these rows PASS.
5. **`FR-082` is defined out of order and grouped with nothing.** It appears at `spec.md:814`
   after `FR-100` — an 18-number rewind — and its bullet *dangles after the
   "Production reachability" table*, so it is not grouped with any other requirement. Two
   independent `RI-06b` codes: `fr-non-monotonic-document-order` and
   `fr-dangles-after-table`. (I first tried to detect this from heading ancestry; this
   document mixes `###` and `####` so `### Identity` is a sibling of
   `### Functional Requirements`, and the ancestry rule flagged all 102 FRs. The
   nowshipped rule asks what is directly above the bullet, which is determinate.)
6. **Gap in document order: FR-082, FR-083, FR-084 appear nowhere between FR-081 and
   FR-085.** They are defined later, out of sequence.
7. **`§8` and `§11` of the brief are cited by nothing.** §8 is the entity-extractor expansion
   (170 lines, 7 mandatory sub-sections); `Cyrillic`, `CVE`, `persons.py` and `github.com`
   appear **0 times** across all six artefacts, independently confirmed by grep. FR-030
   mandates 32 `core:*` classes and no requirement obliges any producer to emit any of them
   (`RI-10` names 39 vocabulary terms across FR-030/031/034/036 with an empty
   `producer_obligation_frs` set).
8. **23 of 74 tasks cite no FR at all**, including T001 (the blocking baseline), T004 (which
   is the task that was supposed to create the FR-mapped checklist and did not), T032, T054,
   T058, T060, T062, T063 and T066.
9. **82 of 82 checklist rows cite no FR.** Combined with finding 7, T004's deliverable was
   not produced in any form.
10. **Checklist row A5 ("Tenancy: no cross-tenant write or read") cites `existing suites`** —
    a text phrase, not a runnable task. 13 rows total gate on something that is not a task.
11. **14 FRs have more than one task owner** (`FR-025` has three: T031, T041, T043), so a
    change to them has no single blast radius. WARN by design.
12. **16 of 16 success criteria and 5 of 5 constitutional invariants are referenced by no
    checklist row.** The checklist cannot fail on any of them.
13. **15 count claims in the artefacts verify correctly and 8 are reported as unverifiable**
    rather than guessed at: 14 `count-ok` (`102 FRs` ×2, `102 functional requirements`,
    `16 measurable outcomes`, `16 SCs`, `5 INV`, `5 constitutional invariant`, `9 user stories`
    ×2, `9 stories`, `13 members` ×2) and 1 `count-section-ok` (`115 sections`). The 8
    unverifiable ones are the `apps/` claims and the section-scoped "170 lines". A checker
    that only ever complains is not measuring; these receipts are the evidence that it is.

### 3.4 `RI-05-MISCITE`: ranked, heuristic, 28 suspects

`28 of 86 judgeable FR citations share no meaningful term with the FR they cite; 58 share at
least one; 22 were not judgeable (too few terms on one side).`

Top of the list, in rank order:

```
tasks.md:65  cites FR-031   (15 task terms vs 15 FR terms, 0 shared)
tasks.md:49  cites FR-020   (12 vs 3)   <- T011 PredicateSignature vs "Producers MUST import
                                                  no graph, claim, admission or projection symbol"
tasks.md:50  cites FR-021   (12 vs 28)
plan.md:216  cites FR-084   (11 vs 8)
tasks.md:51  cites FR-022   (11 vs 3)
tasks.md:34  cites FR-005   (9 vs 5)    T006 active/passive identity vs the signature-derivation FR
tasks.md:34  cites FR-007   (9 vs 2)
tasks.md:67  cites FR-034   (7 vs 7)    T019 mention index vs the type-space-hierarchy FR
tasks.md:99  cites FR-025   (9 vs 3)    T032 the §90 unknown case vs the assembly-grouping FR
tasks.md:159 cites FR-097   (9 vs 2)    T051 migration 021 vs the migration requirement
```

**Honest accounting of the delta.** The brief cites "18 known bad citations" out of 50.
I measure 28 out of 86. The denominators differ, so the numbers are not comparable: I scan
all six artefacts and count *occurrences*, not distinct pairs, and my term set is stricter
(identifier-shaped terms only, with reference ids and normative words removed). The
`tasks.md:49 → FR-020` case the brief names is the **second-highest** suspect here, so the
named defect is caught. The extra suspects are T032→FR-025, T051→FR-097 and
T019→FR-034, which the brief does not list. I am not claiming all 28 are wrong; this is a
triage list, which is why it is WARN.

### 3.5 `RI-10-FORBIDDEN`: the three forbidden shapes

```
FAIL synonym-in-identity: data-model.md:50  — N5 synonym row: `owns` ≡ `controls`
FAIL synonym-in-identity: data-model.md:53  — "a versioned, sourced synonym table is a claim
                                           about equivalence"
FAIL synonym-in-identity: data-model.md:54  — same paragraph
FAIL nested-hypothesis:   data-model.md:228 — TypeHypothesis.hypotheses: tuple[TypeCandidate, ...]
FAIL vocabulary-without-producer: 39 terms in FR-030/031/034/036, no producer obligation anywhere
```

---

## 4. Tests

`71 passed` — `.venv\Scripts\python.exe -m pytest specs/.../repair/tools/test_reference_check.py -q`

| Group | Tests | What it proves |
|---|---|---|
| 1. Fails on broken input | 17 | the checker goes red, per defect class, and `main()` returns 1 |
| 2. Malformed input is a finding | 5 | no exception escapes any check |
| 3. **Does not fail on consistent input** | 3 | a synthetic self-consistent feature directory produces **0 FAIL** and exit 0 — the anti-"always red" control |
| 4. Parsers and heuristics | 12 | term extraction, must-literals, claim windows, offset→line, harness count, mutation registry, dangling-FR |
| 5. Real-artefact tripwires | 25 | every named defect, asserted **only while its token is still present** |
| 6. CLI contract | 9 | JSON shape, `--warn-only`, `--only`, `--compare`, corrupt baseline, bad check id, missing dir, report contents, cp1251 console |
| | **71** | |

### 4.1 The headline test

`test_phantom_fr_and_phantom_task_fail_the_gate` builds a synthetic feature directory in
which `tasks.md` cites `FR-103` and a checklist row cites task `T009`, neither of which
exists anywhere, and asserts:

```python
assert "RI-01-FR-DEF" in check_ids   and "FR-103" in by_code["fr-undefined"]
assert "RI-02-TASK-REF" in check_ids and "T009"  in by_code["task-phantom"]
assert "RI-04b-ROW-TASK" in check_ids and rows == {"A2"}      # the row gating on nothing
assert rc.main(["--spec-dir", str(spec_dir)]) == 1           # non-zero on broken input
assert rc.main(["--spec-dir", str(spec_dir), "--warn-only"]) == 0
```

### 4.2 The anti-"always red" control

`test_synthetic_consistent_feature_dir_has_zero_failures` builds a feature directory that
satisfies every rule — 3 FRs all owned by exactly one task each, a checklist with a real FR
column, correct count claims, no stale claims, valid `§` targets — and asserts:

```python
assert fails == []                                # not a single FAIL
assert rc.main(["--spec-dir", str(spec_dir)]) == 0
```

`test_every_check_id_is_reported_as_ran_even_when_clean` additionally asserts that all 25
check IDs appear in the summary, so a check that silently stopped running cannot hide.

### 4.3 Tripwires retire themselves

Every real-artefact test is guarded by `skip_if_repaired(artefact, token)`. If a repair pass
removes `FR-103` from `tasks.md`, that test *skips* with "defect has been repaired" rather
than failing. The suite therefore stays green as the artefacts are fixed, and stops
protecting a defect the moment it is gone. `test_the_real_artefact_set_fails_the_gate_today`
skips once the set passes every FAIL check.

---

## 5. Usage

### 5.1 The gate

```powershell
# the gate: non-zero on any FAIL finding
.\.venv\Scripts\python.exe specs\021-entity-relation-extraction-finalization\repair\tools\reference_check.py
if ($LASTEXITCODE -ne 0) { throw "reference-integrity gate failed" }

# a repair-in-progress pass: report, never block
.\.venv\Scripts\python.exe specs\021-entity-relation-extraction-finalization\repair\tools\reference_check.py --warn-only

# machine-readable, for a CI artefact
.\.venv\Scripts\python.exe specs\021-entity-relation-extraction-finalization\repair\tools\reference_check.py --json > reference-check.json

# measure progress against the previous pass
.\.venv\Scripts\python.exe specs\021-entity-relation-extraction-finalization\repair\tools\reference_check.py --compare reference-check.json

# triage one check while repairing it
.\.venv\Scripts\python.exe specs\021-entity-relation-extraction-finalization\repair\tools\reference_check.py --only RI-02-TASK-REF --only RI-04b-ROW-TASK

# show the receipts (the claims this run verified) as well as the failures
.\.venv\Scripts\python.exe specs\021-entity-relation-extraction-finalization\repair\tools\reference_check.py --show-ok

# also scan the prior review report
.\.venv\Scripts\python.exe specs\021-entity-relation-extraction-finalization\repair\tools\reference_check.py --all-artefacts
```

Exit codes: `0` no FAIL (or `--warn-only`), `1` FAIL findings present, `2` could not run.
Path auto-discovery walks up from the tool to the first directory holding `spec.md` and
`input.md`; override with `--spec-dir`.

### 5.2 Wiring it into a pass

The intended loop is: snapshot `--json` at the start of a repair pass, run `--warn-only`
during the work, then run with `--compare` at the end. The per-check-ID totals in §3.1 are
the progress metric: `RI-03-FR-ORPHAN` going 1 → 0 and `RI-02-TASK-REF` going 9 → 0 is the
whole gate, and nothing else needs to move for the feature to be reference-clean.

### 5.3 The `--all-artefacts` pass

Including `phase0-results.md` (162 FAIL / 40 WARN / 36 INFO) adds:

- `RI-07c-ID-SHAPE` 0 → 3 WARNs: the report writes `INV-1` and `INV-3` unpadded, which
  cannot match `INV-001`/`INV-003`;
- `RI-08-SEC-CITE` 1 → 2, because the report also quotes `§1B`;
- `RI-09-COUNT` 10 → 11 FAIL, 23 → 29 INFO, because the report itself contains the
  miscounts it is describing ("§8 … 170 lines", "`input.md` is 4898 lines, not the 3411 …");
- `RI-05-MISCITE` 28 → 31 suspects, from the report's own quotations;
- `RI-11-CONST` gains 2 more principle-miscite WARNs, because the report says
  "Principle II VI" while discussing the same two mis-cited rows;
- `RI-01-FR-DEF` shows 7 citations of `FR-103` instead of 6, and the fourth citing file
  `phase0-results.md`.

**FAIL counts are otherwise unchanged**, because a quotation is not a second definition.
Left out of the default set deliberately: a report that quotes a defect is not a second
place the defect lives.

---

## 6. Known limits of this checker

Stated so nobody mistakes silence for soundness.

1. **Heuristics are heuristics.** `RI-05` and `RI-05b` are WARN and their thresholds are
   judgement calls. `RI-05b` only looks at additive prohibitions, so a task that *removes* a
   member an FR mandates is not flagged (deliberate: see §2).
2. **Count claims about `apps/` code are not checked.** "26 fields", "558 lines",
   "43 files" are reported `count-unverifiable` rather than guessed at.
3. **Section-scoped line counts** ("§8 is 170 lines") are reported INFO with both
   conventions, because whether the heading line counts is undefined.
4. **`input.md` is trusted as a section registry.** A citation is validated against its
   *headings*, not against whether the section's content was honoured. `RI-08b` and the
   `RI-10` vocabulary check are the two places that surface content-level drops, and both
   are coarse.
5. **`RI-10`'s vocabulary rule is textual.** It asks whether any requirement containing a
   `core:*` term also carries a normative producer/extractor obligation. It cannot tell a
   real producer obligation from an incidental mention of the word "producer".
6. **Task-to-requirement semantics are not judged.** Whether T032's text actually
   implements the FR it cites is `RI-05`'s job and only by term overlap.
7. **Only one constitution is known.** `RI-11` reads `.specify/memory/constitution.md`. A
   workspace without one reports WARN and `RI-11` does not run.
8. **`--compare` reads one baseline file.** No history is kept; store the JSON per pass if
   you want a trend.
