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

---

# 7. Extension — five governance checks (tool v1.1.0)

*Appended. Nothing above this line was edited.*

This is a **mechanical tooling extension**. A7b is the machine arbiter, not a conceptual
author: it may add checks, it may not decide what any requirement means. The five checks
below are transcribed from `repair/ARBITRATION.md` §2, §3, §1 and §10 — the rules are the
arbitration record's, the matching is the tool's.

## 7.1 What was added, and what was not touched

| New check id | Rule source | Severity | Corpus | Real run |
|---|---|---|---|---|
| `TOMBSTONED-FR-REF` | `ARBITRATION.md` §2 | **FAIL** | the six scanned spec artefacts | **10 FAIL**, 1 INFO |
| `FR-NAMESPACE-COLLISION` | `ARBITRATION.md` §1 | **FAIL** | `spec.md` + every `repair/*.md` | **21 FAIL**, 1 INFO |
| `EPISTEMIC-AXIS-CONFLATION` | `ARBITRATION.md` §3 | **FAIL** | `spec.md`, `tasks.md`, every `repair/*.md` | **7 FAIL**, 1 INFO |
| `COUNT-PRECISION` | `ARBITRATION.md` §10 | **WARN** | everything (`spec` artefacts + `phase0-results.md` + `repair/*.md`) | **6 WARN**, 8 INFO |
| `GHOST-SUFFIX` | `ARBITRATION.md` §1 folds + `A6` §2.3 | **WARN** | everything | **2 WARN** over 41 citations, 1 INFO |

**30 check ids** now, up from 25. New totals: **198 FAIL, 40 WARN, 42 INFO**, exit 1
(was 160 / 32 / 30).

### The no-regression evidence, stated as a measurement

| Assertion | How it was checked | Result |
|---|---|---|
| No existing check changed behaviour | `--json` before vs after, every `RI-*` finding compared as `(check_id, code, sorted locations)` | **222 = 222, identical** |
| No existing check's counts moved | per-check FAIL/WARN/INFO diff over all 25 `RI-*` ids | **no row changed** |
| All pre-existing tests still pass | `pytest …/test_reference_check.py -q` | **71 passed** (suite now **106 passed**) |
| The anti-"always red" control still holds | `test_synthetic_consistent_feature_dir_has_zero_failures` | 0 FAIL, exit 0 |
| Every new id appears in the summary | `test_every_new_check_id_appears_in_the_summary_of_a_clean_run` | 5/5 |
| New ids are silent on a clean directory | `test_every_new_check_is_silent_on_a_clean_feature_dir_with_repair_docs` | 0 FAIL, 0 WARN |
| Malformed markdown is a finding, not an exception | `test_malformed_repair_documents_are_findings_not_exceptions`, `test_new_checks_survive_a_non_utf8_repair_document` | no `check-crashed` |
| `ruff check` on both files | repo `ruff.toml` (`E,F,I,B,UP`, line-length 100) | All checks passed |

The mechanism that keeps this honest is structural: `repair/*.md` is a **new corpus**
(`Context.repair` / `Context.governance()`) that no `RI-*` check reads. Adding a corpus is
additive by construction — the only way to change an existing finding would be to edit
`SCANNED_ARTEFACTS`, and nothing did.

## 7.2 `TOMBSTONED-FR-REF` — FAIL, 10 findings

**Rule** (`ARBITRATION.md` §2, `TOMBSTONED_FR_MUST_HAVE_ZERO_NORMATIVE_REFERENCES`): a
tombstone exists for historical traceability only; no artefact may cite a tombstoned FR as a
live normative requirement target. A citation that carries a deprecation marker on the same
line is history and is not a violation.

The tombstone set and each id's replacement target are one module-level constant,
`TOMBSTONED_FRS` — the check reads nothing else to learn them:

```python
TOMBSTONED_FRS = {"FR-034a": "INV-002", "FR-058": "INV-004", "FR-070": "design note",
                  "FR-079": "FR-078", "FR-080": "FR-072"}
```

Accepted deprecation markers (`DEPRECATION_MARKERS`): `tombstone`, `deprecated`,
`absorb*`, `merged into`, `merge target`, `merged away`, `see ADR`, `superseded`,
`folded into`, `no longer normative`. Kept small and literal on purpose — a broad marker
would silently un-break the check.

Real run — **5 normative definitions and 5 normative citations, 0 exempted**:

```
FAIL tombstoned-fr-defined-normative: spec.md:514 defines FR-034a …  Replacement target: INV-002
FAIL tombstoned-fr-defined-normative: spec.md:610 defines FR-058 …   Replacement target: INV-004
FAIL tombstoned-fr-defined-normative: spec.md:656 defines FR-070 …   Replacement target: design note
FAIL tombstoned-fr-defined-normative: spec.md:699 defines FR-079 …   Replacement target: FR-078
FAIL tombstoned-fr-defined-normative: spec.md:704 defines FR-080 …   Replacement target: FR-072
FAIL tombstoned-fr-cited-normative:   research.md:143 cites FR-034a … Replacement target: INV-002
FAIL tombstoned-fr-cited-normative:   tasks.md:54   cites FR-034a …   Replacement target: INV-002
FAIL tombstoned-fr-cited-normative:   tasks.md:69   cites FR-070  …   Replacement target: design note
FAIL tombstoned-fr-cited-normative:   tasks.md:143  cites FR-058  …   Replacement target: INV-004
FAIL tombstoned-fr-cited-normative:   tasks.md:177  cites FR-079  …   Replacement target: FR-078
INFO tombstone-summary: 5 tombstoned ids … 10 live normative reference(s), 0 exempted
```

The five task citations are exactly the mis-citations `A6-fr-triage.md` §4 already names,
and the five definitions are the ids the arbitration record says are absorbed:

```
tasks.md:54   T016 -> FR-034a      spec.md:514  - **FR-034a**: Type and relation policy ...
tasks.md:69   T021 -> FR-070       spec.md:610  - **FR-058**: A `GraphEdge` or `HyperEdge` ...
tasks.md:143  T045 -> FR-058       spec.md:656  - **FR-070**: RDF-compatible shape ...
tasks.md:177  T059 -> FR-079       spec.md:699  - **FR-079**: Four named mutations ...
                                       spec.md:704  - **FR-080**: The extraction layer ...
```

`ARBITRATION.md` §2's own instruction — write `**FR-058**: *merged into `INV-004`*` — is the
shape that would pass: it carries a marker.

**Design decision, stated because it is a decision:** a *definition* of a tombstoned id is
reported, not only a citation. `spec.md:610` is not a reference to `FR-058`; it is the
requirement itself, and a tombstone that still carries a normative body has not been
tombstoned. It gets its own code (`tombstoned-fr-defined-normative` vs
`tombstoned-fr-cited-normative`) so the two are separable in a triage pass.

## 7.3 `FR-NAMESPACE-COLLISION` — FAIL, 21 findings

**Rule** (`ARBITRATION.md` §1, gate 1: *collision = 0*): no two distinct FR definitions may
share an id, and no FR number may be claimed by two owners. Scanned: `spec.md` and every
`repair/*.md`.

A **definition site** in a repair document is a bold title line that opens with the FR id,
closes the bold span on the same line, and is followed by nothing but an optional
dash-separated gloss:

```
**FR-101 — `PredicateSignature` field set and exclusions.**
**FR-101 (NEW) - the §8 entity extractor expansion, absent from every artefact**
**FR-014 (REWRITE)**
```

with the requirement text as the block beneath it. Two shapes are deliberately **not**
definitions, and both exclusions are tested:

| Not a definition | Why | Test |
|---|---|---|
| A fenced code block | `A7-migration-021.md` quotes old requirement text under `**FR-059, old (`:614-616`), verbatim:**` inside a ```` ``` ```` fence. A quotation is a citation of the past, not a second claim on the number. | `test_a_quoted_old_fr_in_a_fence_is_not_a_second_owner` |
| `**FR-001–FR-100 are NOT renumbered.**` | an id continuing into a range is a range claim, not an `FR-001` | `test_a_bold_fr_range_is_not_a_definition` |

A second site whose text is identical after normalisation is reported INFO
(`fr-redefined-identically`), not FAIL: a quotation that changes nothing is a restatement.

### The two predicted collisions — confirmed

```
FAIL fr-namespace-collision: FR-101 is defined twice with different requirement text
     (repair-vs-repair):
     repair/A2-identity-subsystem.md:1363  "**FR-101 - `PredicateSignature` field set and
       exclusions.**" -> "System MUST provide a deterministic frozen `PredicateSignature`
       carrying exactly `language`, `predicate_lemma`, …"
     repair/A6-fr-triage.md:479            "**FR-101 (NEW) - the §8 entity extractor
       expansion, absent from every artefact**" -> "The deterministic entity extraction layer
       MUST be completed around the atomic type vocabulary, extending existing extractors …"

FAIL fr-namespace-collision: FR-102 is defined twice with different requirement text
     (repair-vs-repair):
     repair/A2-identity-subsystem.md:1388  "**FR-102 - `normalize_voice` is a specified
       deterministic algorithm.**"
     repair/A6-fr-triage.md:507            "**FR-102 (NEW) - the meta-rule that closes D9
       permanently**"
```

`FR-101` and `FR-102` are each defined twice with completely different subjects, exactly as
predicted, and `ARBITRATION.md` §1 has already voided both ("as invented by **both** A2 and
A6 are void"). Both texts and both `file:line` locations are in every finding's `data.sites`.

### The other 19, and why they are also FAIL

19 collisions are `spec-vs-repair`: an FR number that `spec.md` defines and that A6's §2.4
also defines, with different text.

| id | `spec.md` | `repair/A6-fr-triage.md` | id | `spec.md` | `repair/A6-fr-triage.md` |
|---|---|---|---|---|---|
| FR-002 | 381 | 267 | FR-062 | 627 | 393 |
| FR-011 | 414 | 278 | FR-074 | 677 | 405 |
| FR-012 | 418 | 290 | FR-083 | 822 | 417 |
| FR-013 | 421 | 300 | FR-084 | 832 | 433 |
| FR-014 | 425 | 312 | FR-086 | 721 | 445 |
| FR-015 | 427 | 320 | FR-092 | 745 | 454 |
| FR-018 | 438 | 331 | FR-095 | 761 | 466 |
| FR-020 | 443 | 342 | FR-055 | 601 | 368 |
| FR-043 | 557 | 350 | FR-061 | 622 | 380 |
| FR-045 | 565 | 359 | | | |

Every one of the 19 A6 sites is a `**(REWRITE)**` block: a *proposed replacement body* for an
id `spec.md` already owns. The rule as written — "an FR number that appears as a definition
in a repair document AND is defined in `spec.md` with different text" — makes each of them a
FAIL, and that is what the tool reports. I am not deciding that they are wrong; I am
recording that the namespace has two texts per number until a triage pass accepts or rejects
each rewrite. The discriminator is mechanical, not editorial, and is in `data.kinds`:

| `data.kinds` | count | meaning |
|---|---|---|
| `new-requirement` + `redefinition` | 2 | **FR-101, FR-102** — a genuine two-agent collision, no `spec.md` owner at all |
| `canonical-definition` + `rewrite-proposal` | 19 | `spec.md` owns the number; A6 proposes different text for it |

A triage pass can therefore retire the 19 by accepting or rejecting the rewrite, and the 2 by
allocating A8prep's numbers — without re-reading any text.

`FR-104`, `FR-105`, `FR-106` are also defined only in A2 and are correctly **not** reported:
one owner each, so no collision.

## 7.4 `EPISTEMIC-AXIS-CONFLATION` — FAIL, 7 findings

**Rule** (`ARBITRATION.md` §3): the three axes are never mixed.

| State | Lives on | Means |
|---|---|---|
| `PredicateHypothesis.resolution_state = CONFLICTING` | the hypothesis | incompatible **semantic** readings |
| `RelationCandidate.assembly_state` (**NEW enum**) | the candidate | incompatible **structural** readings — arity, direction, polarity, role slots |
| `CandidateStatus.CONTRADICTED` | the candidate | the **assertion itself is denied** |

A prose unit (one table row, one list item, or one paragraph — fenced code excluded) that
associates a structural-disagreement term with `CONTRADICTED` is FAIL. A *sentence* carrying
a prohibition marker (`forbidden`, `never`, `must not`, `rather than`, …) is stating the
rule, not breaking it, and is counted separately.

Real run — **7 sentences route a structural disagreement into the denial state**:

```
FAIL repair/A6-fr-triage.md:187        | FR-090 | Conflict over arity/direction/polarity/roles
                                       yields `CONTRADICTED` with both readings; …
FAIL spec.md:737                       - **FR-090**: A conflict over arity, direction, polarity
                                       or role bindings MUST yield `CandidateStatus.CONTRADICTED`
                                       with both readings preserved, …
FAIL tasks.md:128                      - [ ] T040 … A conflict over arity, direction, polarity or
                                       roles MUST yield `CandidateStatus.CONTRADICTED` …
FAIL repair/A4b-mapping-layer.md:940   "That case is `FR-090`'s `CandidateStatus.CONTRADICTED`
                                       with both readings preserved, at the candidate layer"
FAIL repair/A4b-mapping-layer.md:1661  "A disagreement that is **structural** - arity,
                                       direction, polarity or role bindings over the same
                                       mentions - is not representable as one hypothesis and
                                       MUST yield `FR-090`'s `CandidateStatus.CONTRADICTED`"
FAIL repair/A4b-mapping-layer.md:2326  | **Q4** … which disagreements are hypothesis-level
                                       `CONFLICTING` and which are FR-090 candidate-level
                                       `CONTRADICTED`? |  split on the layer: … structural
                                       disagreement → candidate
FAIL repair/A8prep-ownership-and-dag.md:683  (E5.2) A conflict over arity, direction, polarity
                                       or roles yields `CandidateStatus.CONTRADICTED` …
```

**The named offender is confirmed, and it is not alone.** `ARBITRATION.md` §3 names A6
("**A6 is forbidden** from turning structural disagreement into `CONTRADICTED`"), and
`A6-fr-triage.md:187` is exactly that — carried into `spec.md:737` (FR-090's own text) and
`tasks.md:128` (T040), and independently restated by A4b twice and by A8prep once. The
defect is in the requirement, not only in the triage report, so editing A6 alone would not
clear it.

1 sentence (`ARBITRATION.md:65`/`:73-75`, plus the §13 change-log line) mentions both terms
while prohibiting the conflation, and is counted as `prohibition_restatements`, not FAIL.

## 7.5 `COUNT-PRECISION` — WARN, 6 findings

**Rule** (`ARBITRATION.md` §10): four numbers, one job each, never interchangeable.

| Number | Counts |
|---|---|
| **31** | foundational entity types (`core:*`) — measured, not 32 |
| **13** | value types (`value:*`) |
| **7** | §8 extraction families / subsections |
| **~4** | new instrument modules actually added |

Two reportable shapes, transcribed literally from the rule:

```
shape 1   32  +  (foundational | atomic | entity | value | type)? + types|classes|extractors|items|families
shape 2   (all )?seven[_ -]+classes        in a §8 / entity-extractor context
```

The correct phrase for shape 2 is *extraction families* or *§8 subsections*. A unit
carrying a refutation marker (`corrected`, `miscount`, `misreading`, `renamed`,
`does not exist`, `nowhere writes`, `not 32`, …) is stating the correction and is reported
INFO — otherwise the arbitration record, whose job is to *fix* the number, would be reported
as breaking the rule.

Real run — **6 live conflations**:

```
WARN count-32-as-entity-types  phase0-results.md:135            '32 type classes'
WARN count-32-as-entity-types  repair/A5-type-vocabulary.md:2079 '32 type classes'
WARN count-32-as-entity-types  repair/A6-fr-triage.md:802       '32-item'
WARN count-seven-classes       repair/A6-fr-triage.md:483       'all seven classes'
WARN count-seven-classes       repair/A6-fr-triage.md:672       'all_seven_classes'
WARN count-seven-classes       repair/A6-fr-triage.md:703       'all_seven_classes'
```

7 more occurrences of the same phrases are reported INFO `count-refutation`, including
`ARBITRATION.md:239`, `:242` and `:302` — the passages that *correct* the number.

### Honest accounting of the three named offenders

| Named | Confirmed? | Where |
|---|---|---|
| the D7 row in `phase0-results.md` | ✅ yes | `phase0-results.md:135` — D7's own text (quoted below). A5 re-quotes the same row verbatim at `A5-type-vocabulary.md:2079`, which is the second WARN. |
| the §8 entity-extractor task/test name | ✅ yes | the name itself, at `A6-fr-triage.md:672` and `:703` (the task rows), plus the requirement body they wrap at `A6-fr-triage.md:483` — all three quoted below. |
| `repair/A5-type-vocabulary.md`'s `SC-026` | ⚠️ **not as written** | A5's `SC-026` block at `:1437` says "every one of the *seven §8 sub-sections*" — that is the **permitted** phrase, and the check does not flag it. `ARBITRATION.md:242` names `SC-026` for renaming because of the test name it mandates, and that test name **is** caught. A5's own shape-1 phrases (`:648`, `:1821`, `:2075`, `:32`) are all inside passages that refute the number, so they are INFO, not WARN. |

The offending text, quoted:

```
phase0-results.md:135   Yet FR-030 mandates 32 type classes with no producer obligation
A6-fr-triage.md:483     > producers/readers for all seven classes of §8:
A6-fr-triage.md:672     | **FR-101** (new) | T114 (P2) | `test_entity_extractor_covers_all_seven_classes` | R-101 |
A5-type-vocabulary.md:1437  - **SC-026**: The §82 entity-type corpus runs green with every one of the
                            seven §8 sub-sections covered — person, organization, URL/domain/…
```

I report the mismatch rather than widening the pattern to manufacture a hit: naming a §8
sub-section count is not the vocabulary error the rule forbids, and a checker that flagged
it would be flagging the correction.

## 7.6 `GHOST-SUFFIX` — WARN, 2 findings over 41 citations

**Rule** (`ARBITRATION.md` §1 folds, `A6` §2.3): the two letter-suffixed ids

```
FR-034a        FR-039a
```

are a transitional device. A letter suffix forces every id regex to accept two styles and
leaves the namespace speaking two languages at once. WARN, not FAIL: each is currently
defined exactly once, so nothing dangles yet.

A **fenced code block is quotation**, on the same rule `FR-NAMESPACE-COLLISION` uses. That
removes two of the citations the first cut counted: `A2-identity-subsystem.md:1274` and
`A5-type-vocabulary.md:1796` are both inside ```` ``` ```` blocks quoting the requirement
under discussion, and a quotation is not a second place the requirement lives — the same
reasoning §5.3 already applies to `phase0-results.md`.

Real run (numbers in §7.9) — a citation on a deprecation-marked line is history too:

```
WARN suffixed-fr-citation  FR-034a  23 citations across 9 files
WARN suffixed-fr-citation  FR-039a  18 citations across 5 files
INFO ghost-suffix-summary  41 live normative citation(s); 3 on a deprecation-marked line and
                           2 more inside fenced blocks, so read as quotation
```

Aggregated per id rather than per id-per-file (the first cut produced 15 findings for 2 ids);
every individual `file:line` is still a location on the finding, so no citation is lost.
The heaviest sites are `A6-fr-triage.md` (8 + 6), `A8prep-ownership-and-dag.md` (4 + 8) and
`ARBITRATION.md` (3 + 1).

**Self-reference, disclosed.** This report is inside the corpus it measures, and it
contributes exactly 2 of the 41 — the two pre-existing lines in §2 that state the id-regex
rule. Every phrase this section needs to quote is inside a fenced block, so the tool reads
it as quotation rather than as a claim. A report that documents a defect cannot also be
free of it; folding the two ids is what clears the count.

## 7.7 Tests added — 35, suite 71 → 106

| Group | Tests | Proves |
|---|---|---|
| Tombstones | 5 | the set equals `ARBITRATION.md` §2; a citation fails and names its replacement; a *definition* fails under its own code; a deprecation-marked line is history (0 blocking); clean input is silent |
| FR namespace | 6 | two repair docs colliding (positive); a repair doc redefining a `spec.md` FR (positive); identical text is INFO not FAIL; a fenced verbatim quote is not a second owner; a bold id-range is not a definition; clean input is silent |
| Epistemic axes | 5 | a structural conflict routed to the denial state fails; *prohibiting* the conflation is not a finding; a semantic conflict alone is not a finding; a denial without a structural term is not a finding; clean input is silent |
| Count precision | 6 | both shapes 1 and 2 warn, in prose and in a test name; the four authority numbers are clean; a correction is INFO not WARN; clean input is silent |
| Ghost suffixes | 4 | a live citation warns with a per-file breakdown; a deprecation-marked line is history; unsuffixed ids are not ghosts; clean input is silent |
| Cross-cutting | 4 | all five silent on a clean dir *with* `repair/` docs; all five present in the summary; malformed `repair/*.md` (unclosed fence, truncated bold, empty file) is a finding not an exception; a non-UTF-8 `repair/*.md` is a finding not an exception |
| Real-artefact tripwires | 5 | the tombstone gate is red; the two `A6`-invented ids are still defined twice in A2+A6; A6 still routes a structural conflict to the denial state; the D7 miscount and the seven-classes phrase are still present; the ghosts are still cited |

Each tripwire **skips when its defect is repaired**, like the existing ones — the suite goes
green as the artefacts are fixed and stops protecting a defect the moment it is gone.

## 7.8 Limits added by this extension

1. **A repair-document "definition" is a shape, not an intent.** The check recognises a bold
   title line. A repair document that claims an FR number in some other shape (a table row, a
   heading, a `> **FR-030**:` blockquote body) is not seen as a second owner. A5's
   `FR-030` restatement at `:880` is the live example: it is a full re-statement of the
   requirement text and the check does not report it.
2. **`EPISTEMIC-AXIS-CONFLATION` needs the structural term in the same *unit*.** A line that
   routes a conflict to the denial state with no arity / direction / polarity / role wording is
   ambiguous between a structural and a semantic conflict, so the check does not report it.
   `A6-fr-triage.md:743` is exactly such a line — "Conflict → the denial state, both readings
   kept", alongside `AMBIGUOUS` and with no structural term.
3. **`COUNT-PRECISION` matches two literal shapes**, not a general numeric authority.
   "30 entity types" or "8 extraction families" are not detected; only the conflation forms
   the arbitration record names. `AUTHORITY_NUMBERS` carries all four numbers for the report,
   but only the two shapes above are enforced.
4. **The refutation markers are a judgement call.** A repair document that refutes a bad
   number without any of the marker phrases will be reported as making the claim. Every such
   hit is quoted in the finding, so the reader can dismiss it in one glance.
5. **`GHOST-SUFFIX` counts the report that documents it.** See §7.6; the count cannot reach 0
   while the suffixed ids appear in prose, which is the point of folding them.
6. **Every phrase quoted above is inside a fenced block on purpose.** A fenced block is
   quoted material to all five checks, so this section documents findings without asserting
   them. That is a convention, not a guarantee: a future edit that restates a trigger phrase
   in prose will add a finding to this file, and that is the correct outcome.

## 7.9 The self-citations, itemised

Measured on the revision that contains this section, `GHOST-SUFFIX` and `COUNT-PRECISION`
both point at `repair/A7b-reference-integrity-checker.md` itself:

| Check | This file's contribution | Why |
|---|---|---|
| `GHOST-SUFFIX` | **2** of 41 — the pre-existing §2 rule text, which names the suffixed id twice | unavoidable: §2 documents the id regex, and the regex is the thing that must accept the suffix |
| `COUNT-PRECISION` | 0 | every shape quoted in §7.5 is inside a fenced block |
| `EPISTEMIC-AXIS-CONFLATION` | 0 | every quoted instruction in §7.4 is inside a fenced block |
| `FR-NAMESPACE-COLLISION` | 0 | every quoted definition title in §7.3 is inside a fenced block |
| `TOMBSTONED-FR-REF` | 0 | the tombstone set and its replacements are inside a fenced block, and the check does not read `repair/*.md` at all |

**Totals: 198 FAIL, 40 WARN, 42 INFO, exit 1** — of which **38 FAIL** (10 + 21 + 7) and
**8 WARN** (6 + 2) are the five new checks; the other 160 / 32 / 30 are exactly the run in
§3.1, unchanged. The per-check table at the end of the tool's own report is the authority;
this section quotes it.


---

# 8. Extension - three false-positive fixes (tool v1.2.0)

Three rules were pressuring correct documents into incorrect shapes. Each fix is stated as
*rule before* / *rule after*, with the measurement that proves the fix does not cost
detection power. No severity changed. No check was added or removed. No `.md` artefact was
edited.

## 8.0 A measurement caveat, stated first

The `.md` artefacts were being edited by another process throughout this pass. `spec.md` and
`checklists/requirements.md` changed between two consecutive tool invocations, and the live
total FAIL was observed at **254, 213, 455, 352 and 144** across five successive runs of the
same command while this file was being written. **A per-check delta between two different
document states therefore measures the document, not the tool.**

So the numbers below come from a **frozen snapshot** of the whole feature directory, with the
*old* rules and the *new* rules run in one process against those byte-identical files. That is
the only comparison that attributes a finding to a rule. Where a live-run number is quoted it
is labelled as such.

| Snapshot file | SHA-256 (first 16) | bytes |
|---|---|---|
| `input.md` | `8E591907E31805EA` | 73230 |
| `spec.md` | `D5F1E0C02BCD3764` | 157578 |
| `tasks.md` | `F02C49DF7C183049` | 74964 |
| `plan.md` | `41BCAE398CC50E34` | 91358 |
| `research.md` | `36D27BF6D749884B` | 14628 |
| `data-model.md` | `AA041E5E793FB6F7` | 155291 |
| `checklists/requirements.md` | `0392493FBADFED14` | 71789 |
| `phase0-results.md` | `19C20B49798CBF78` | 15509 |
| `repair/A1-constitution-investigation.md` | `8040F68BECCB2ADA` | 136373 |
| `repair/A2-identity-subsystem.md` | `280F7D75E7BBE2F5` | 137266 |
| `repair/A4b-mapping-layer.md` | `1FA7EBBFBAA5DF15` | 148617 |
| `repair/A5-type-vocabulary.md` | `2BB79CC7757FE165` | 124693 |
| `repair/A6-fr-triage.md` | `D305321E75DAE722` | 116770 |
| `repair/A7-migration-021.md` | `390F9369C446AA82` | 139730 |
| `repair/A7b-reference-integrity-checker.md` | `68172E8C0AB80334` | 53342 |
| `repair/A8prep-ownership-and-dag.md` | `55AB4AD1A0AACFD0` | 106382 |
| `repair/ARBITRATION.md` | `DF34F481C2EA3B6A` | 18033 |

The stated baseline **168 FAIL, 32 WARN, 57 INFO, exit 1, 30 check ids** was reproduced
exactly on the live directory at the start of this pass, before any edit.

## 8.1 FP-1 - `RI-10-FORBIDDEN` / `nested-hypothesis` decided on type shape, not field name

### The defect

`TypeHypothesis.hypothesis_state` is a **required** field: brief §6 lists it in the block
`input.md:465-492` and enumerates its six states immediately below. The old rule matched *any*
field whose **name** contained `hypothes` inside a `class *Hypothesis`, so it fired on a scalar
state field. Worse, a spec integrator answered by splitting `TypeHypothesis` across two
```python fences (`data-model.md:1443-1450` and `1454-1464`), with the prose "and the eight
defaulted fields, on the same dataclass:" between them. The split is independently correct
frozen-dataclass ordering hygiene and independently wrong document design, and it exists only
because of this regex. A linter that reshapes documents is broken.

### Rule, before

```python
cls = re.match(r"\s*class\s+(\w*Hypothesis\w*)\s*[:(]", line)
if cls:
    current = cls.group(1)
if not in_code or not current.endswith("Hypothesis"):
    continue
m = re.match(r"\s*(\w*hypothes\w*)\s*:", line, re.I)      # <- the whole rule
if m:
    yield _f(..., "nested-hypothesis", ...)
```

Two extra weaknesses in the same eight lines, both fixed:

* `current` was only re-anchored by a `*Hypothesis*` class, so a field of a **non**-hypothesis
  class appearing later in the same fence was attributed to the earlier hypothesis class.
* entering a fence reset `current` and closing one did not, so the two-fence split silently
  detached the defaulted half of the class from its own name.

### Rule, after

The violation is epistemic - a hypothesis that contains a **set** of hypotheses - so it is
decided on the field's **type shape** and only then on its name (`field_nests_hypotheses`):

1. `hypothesis_state` is exempt **by name** (`HYPOTHESIS_STATE_FIELDS`);
2. any `*HypothesisState` / `*HypothesisStatus` / `*HypothesisMode` / `*HypothesisKind` /
   `*HypothesisVerdict` / `*HypothesisPhase` / `*HypothesisClass` annotation is a scalar and is
   exempt **by type**, so the two exemptions are independent and neither alone can be lost;
3. a **collection** annotation whose element type is a `*Hypothesis` fires -
   `hypotheses: tuple[TypeHypothesis, ...]`, `alternatives: Sequence[DirectionHypothesis]`,
   `peers: frozenset[PredicateHypothesis]`, `hypothesis_set: HypothesisSet`;
4. a **collection** annotation under a field name containing `hypotheses` fires regardless of
   element type - `hypotheses: tuple[str, ...]` is a set of hypotheses whatever the element is;
5. a scalar is not nesting. `evidence_refs: tuple[str, ...]` and
   `mapping_candidates: tuple[TypeMappingCandidate, ...]` are legal; so is
   `hypothesis_state: HypothesisState`.

Deliberately **out of scope, and now said so in the check's own rule text**: a field typed as a
*plain* `*Hypothesis` and not a collection (`parent: TypeHypothesis | None`). That is a real
nesting, but the brief for this fix specified a collection, so it is documented rather than
silently unhandled.

Also fixed: **any** `class` line now re-anchors the container, so a following non-hypothesis
class's fields are never attributed to an earlier hypothesis class.

### The measurement that matters

`data-model.md` with the two fences **merged back into one** - i.e. the workaround undone - old
rule against new rule:

```
OLD  FAIL  nested-hypothesis  data-model.md:1450 nests a hypothesis inside `TypeHypothesis` (field `hypothesis_state`)
NEW  FAIL  vocabulary-without-producer  44 vocabulary terms are mandated by [...]      <- the unrelated real defect, unchanged
```

`nested-hypothesis` 1 → 0. The unrelated `RI-10` FAIL is byte-identical on both sides, so the
fix bought the false positive and nothing else. On the snapshot **as it stands** (fences still
split) the check is 0 FAIL for this code on both old and new rules - which is precisely why the
merged-fence test had to be written, and why it is now a test.

## 8.2 FP-2 - `RI-08-SEC-CITE` resolves three namespaces, not one

### The defect

In the feature artefacts `§N` is *supposed* to mean a numbered section of `input.md`, whose
namespace is `§0`…`§114`. But every feature artefact numbers **itself** the same way, and a
bare intra-document cross-reference such as `§1.5` was being reported as a phantom input.md
section. `data-model.md` therefore renumbers its own cross-references as `part N` - a
convention nobody chose - and that rewrite is what put the phantoms there in the first place.
Measured: the workaround is **97** `part N` tokens in `data-model.md`, and writing them back as
`§N` produces **67** `RI-08-SEC-CITE` FAILs under the old rule, **0** under the new one.

### Rule, before

```python
known = set(ctx.sections)          # input.md's numbered headings, and nothing else
...
if ep not in known:                # one namespace
    yield _f(..., "section-phantom", f"cites §{ep}, which is not a numbered heading in input.md")
```

### Rule, after

A reference resolves if it names a heading in **any** of three namespaces, and is a phantom only
if it names a heading in none:

1. **`input.md`** - the brief. Unchanged, and still the only authority for an integer that
   belongs to no artefact: `§99` in a document that has no `## 99.` is a FAIL.
2. **the artefact the reference appears in** - parsed by the *same* parser
   (`parse_numbered_headings`, extracted from `parse_input_sections`, which is now a one-line
   delegate), including its unnumbered letter subsections. `§1.5` against `### 1.5` in the same
   file is that file's own cross-reference. This is the fix the brief asked for.
3. **the file the reference names** - `` `repair/A6-fr-triage.md` §2.5 `` is a claim about that
   document. The nearest file reference to the left **on the same line** wins, and only if no
   `;`, `|` or sentence-ending `.` separates them, so a table cell cannot misattribute it. The
   target file is read on demand and cached; this does **not** widen what the check scans.

Power deliberately given up, and reported rather than hidden: an **integer** belongs to
input.md's namespace, so an integer that resolves *only* against the citing artefact is
genuinely ambiguous. It is no longer a FAIL; it is reported INFO as
`sec-cite-intra-doc-integer`, naming the artefact and the section, so a reader can adjudicate.
On the snapshot this INFO fires 0 times, because `input.md` numbers every integer `0`…`114`
with no gaps and `data-model.md`'s own integers are a subset.

Power **kept**, and tested:

* `§1B` - a fabricated sub-section label. `input.md` §1 has unnumbered subsections A and B, so
  `§1B` is not a section. Still FAIL, and the message still names the real subsection
  (`test_phantom_section_citation_fails_and_names_the_intended_subsection`).
* a **decimal that resolves nowhere** - `§1.9` against a document with no `### 1.9` - is still
  FAIL. The fix is not "decimals are always fine".
* an **integer in no file** - still FAIL (`test_genuinely_nonexistent_integer_section_still_fails`).
* a **named file that does not have the section** - still FAIL
  (`test_a_section_the_named_file_does_not_have_still_fails`).
* `§1.5` resolving against `input.md` itself (its only dotted key is `4.1`) - unchanged.

## 8.3 FP-3 - `RI-09-COUNT` does not read a `§N-§M` range as a claimed count

### The defect

`FR-078` says *"The six §94-§99 mutations are manifest entries 7-12"*. `_COUNT_NOUN_RE` matched
the range's **upper endpoint** as the number and the noun `mutations` as the unit, and the
checker reported *"claims '99 mutations' but the number of MUTATION sections in input.md §94-§99
is 6"*. A range endpoint is a section label, not a population.

### Rule, before

Every `<integer> <count-noun>` pair in an artefact was treated as a claimed count, wherever the
integer sat.

### Rule, after

`SECTION_RANGE_SPAN_RE` locates the character span of every `§A-§B` / `§A-B` / `§A-§B.C` range
(the second `§` optional, decimals included) once per artefact, and
`_in_section_range(spans, m)` suppresses a count match whose own characters fall inside one.
Suppression is **per integer**, never per line: `"8 mutations from §2-§7 MUST each fail; the
pack has 3 members"` still fails, because `8` is not an endpoint.

A suppressed match is not silently dropped - it is reported INFO as `count-range-endpoint`,
naming the line and stating that the range itself is still verified by the mutation-range rule.
Applied uniformly to all three count shapes (`N lines`, `N sections`, `N <noun>`), because
"ignore integers that are part of a range" is a property of the number, not of the noun.

### What still fires, measured

| Real claim | Shape | Result |
|---|---|---|
| `"≥ 20"` invariants vs the 18 enumerated by the mutation harness | `SC-015` | still FAIL (`test_minimum_count_claim_still_fails`, 20 vs 5 enumerated) |
| `"Four named mutations"` vs six listed items | `FR-079` | still FAIL (`test_number_word_count_claim_still_fails`, 4 vs 6) |
| `"17 mutations from §94-§101"` | checklist + tasks | still FAIL (`test_a_count_claim_beside_a_section_range_still_fails`) |
| `"32 type classes"` | `COUNT-PRECISION` | untouched by this change; 3 `count-32-as-entity-types` WARNs on the live run |
| `§94-§101` spanning 2 non-mutation sections | `mutation-range-not-mutation` | untouched; still FAIL |
| `"3411 lines"` | `count-line-mismatch` | untouched; still FAIL |

## 8.4 The attributable delta, measured

Old rules vs new rules, one process, byte-identical snapshot (§8.0):

```
OLD  460 FAIL, 29 WARN, 64 INFO      exit 1
NEW  454 FAIL, 29 WARN, 65 INFO      exit 1
```

| Check | FAIL old | FAIL new | INFO old | INFO new | What moved |
|---|---|---|---|---|---|
| `RI-08-SEC-CITE` | 6 | **1** | 0 | 0 | −5 FAIL: 4 intra-document, 1 named-file |
| `RI-09-COUNT` | 1 | **0** | 26 | **27** | −1 FAIL, +1 INFO (`count-range-endpoint`) |
| all other 28 ids | — | — | — | — | **finding sets byte-identical** |

The 28 unchanged check ids are the no-regression evidence: the fix touched three rules and
nothing else.

### The frozen snapshot's own report, check by check

`spec-dir` = the hashed snapshot of §8.0, `--json`, exit 1:

```
verdict: 454 FAIL, 29 WARN, 65 INFO
```

| Check | FAIL | WARN | INFO | | Check | FAIL | WARN | INFO |
|---|---|---|---|---|---|---|---|---|
| `RI-00-INPUT` | 0 | **1** | 0 | | `RI-09-COUNT` | **0** | 0 | 27 |
| `RI-01-FR-DEF` | 3 | 0 | 0 | | `RI-10-FORBIDDEN` | 1 | 0 | 0 |
| `RI-01b-FR-SHAPE` | 0 | 0 | 0 | | `RI-11-CONST` | 0 | 0 | 0 |
| `RI-02-TASK-REF` | 72 | 0 | 0 | | `RI-11b-RESEARCH` | 0 | 0 | 0 |
| `RI-03-FR-ORPHAN` | 0 | 0 | 1 | | `RI-12-STALE` | 0 | 0 | 0 |
| `RI-03b-FR-UNCITED` | 0 | 0 | 0 | | `TOMBSTONED-FR-REF` | 1 | 0 | 1 |
| `RI-03c-FR-COLUMN` | 0 | 0 | 1 | | `FR-NAMESPACE-COLLISION` | 4 | 0 | 18 |
| `RI-04-TASK-FR` | 0 | 0 | 0 | | `EPISTEMIC-AXIS-CONFLATION` | 6 | 0 | 1 |
| `RI-04b-ROW-TASK` | 250 | 0 | 0 | | `COUNT-PRECISION` | 0 | 7 | 11 |
| `RI-04c-ROW-FR` | 0 | 0 | 0 | | `GHOST-SUFFIX` | 0 | 2 | 1 |
| `RI-04d-FR-OWNER` | 1 | 1 | 0 | | | | | |
| `RI-05-MISCITE` | 0 | 18 | 1 | | | | | |
| `RI-05b-INVERSE-CITE` | 0 | 0 | 0 | | | | | |
| `RI-06-TASK-ORDER` | 100 | 0 | 0 | | | | | |
| `RI-06b-FR-ORDER` | 15 | 0 | 0 | | | | | |
| `RI-07-SC-COVER` | 0 | 0 | 1 | | | | | |
| `RI-07b-INV-COVER` | 0 | 0 | 1 | | | | |
| `RI-07c-ID-SHAPE` | 0 | 0 | 0 | | | | |
| `RI-08-SEC-CITE` | **1** | 0 | 0 | | | | | |
| `RI-08b-SEC-UNCITED` | 0 | 0 | 1 | | | | | |

The one `RI-00-INPUT` WARN is `constitution-missing`: the snapshot sits outside the repository,
so `find_constitution` finds no `.specify/memory/constitution.md` and `RI-11-CONST` contributes
0. On the live directory both resolve and the constitution is found.

### The live directory, and why its numbers are not published here

The live run is quoted only as an observation with a timestamp, because it is not
reproducible: between two invocations one minute apart during this pass the live totals were

```
20:57   352 FAIL, 35 WARN, 65 INFO      exit 1
21:04   144 FAIL, 45 WARN, 68 INFO      exit 1
```

with `RI-02-TASK-REF` going 41 → 4 and `RI-04b-ROW-TASK` 177 → 0 in that interval. A per-check
delta between two live states measures the document, not the tool. The only live numbers in
this section that carry information about the *tool* are the three fixes, and those are the
frozen-snapshot rows above.


## 8.5 Tests added - 17 test functions, 33 collected items; suite 106 → 139

| Group | Test | Proves |
|---|---|---|
| FP-1 | `test_hypothesis_state_field_is_legal_and_does_not_fail_the_gate` | the brief §6 scalar does not fail |
| FP-1 | `test_field_nests_hypotheses_is_decided_on_type_shape` (16 cases) | the whole rule as one truth table, including `tuple[str, ...] \| None` |
| FP-1 | `test_a_real_container_of_hypotheses_still_fails_the_gate` | **blind-spot control**: 4 real containers → 4 FAILs, exit 1 |
| FP-1 | `test_a_container_of_hypotheses_on_a_non_hypothesis_class_is_not_nesting` | `TypedMention.type_hypotheses` stays legal |
| FP-1 | `test_real_data_model_needs_no_two_fence_split_to_pass` | **the real document, fences merged back**, no `nested-hypothesis` |
| FP-2 | `test_intra_document_decimal_section_reference_is_not_an_input_md_phantom` | the fix |
| FP-2 | `test_a_decimal_that_resolves_nowhere_is_still_a_phantom` | **blind-spot control** |
| FP-2 | `test_genuinely_nonexistent_integer_section_still_fails` | **blind-spot control**, exit 1 |
| FP-2 | `test_a_section_reference_naming_its_own_file_resolves_against_that_file` | named-file resolution |
| FP-2 | `test_a_section_the_named_file_does_not_have_still_fails` | **blind-spot control** on the new authority |
| FP-2 | `test_integer_that_resolves_only_inside_the_citing_artefact_is_info_not_silent` | the given-up power is visible |
| FP-2 | `test_real_data_model_needs_no_part_n_convention_to_pass` | **the real document, `part N` → `§N`**, clean; + `§430` still FAIL |
| FP-3 | `test_section_range_endpoint_is_not_read_as_a_count_claim` | the fix, 7 mutations not claimed |
| FP-3 | `test_a_count_claim_beside_a_section_range_still_fails` | **blind-spot control**: 17 mutations from a range |
| FP-3 | `test_number_word_count_claim_still_fails` | the `"Four"` vs six defect |
| FP-3 | `test_minimum_count_claim_still_fails` | the `"≥ 20"` vs enumerated defect |
| FP-3 | `test_section_range_without_a_second_section_mark_is_still_a_range` | `§2-7` is a range too |
| FP-3 | `test_a_plain_number_next_to_a_section_range_is_still_a_count_claim` | suppression is per integer, not per line |
| + | `merge_split_class_fences`, `fence_containing`, `fence_spans`, `clone_real_feature` | the transformations the two real-document tests need |

Every new test reads a *copy*. `data-model.md` is not edited by any test.

```
112 passed, 6 failed, 21 skipped      (139 collected: 106 + 33)
```

The 6 failures are pre-existing and are not caused by this change. They are hard-coded
expectations pinned to document line numbers and to a document population that the concurrent
repair has moved:

| Failing test | Pinned to | Verdict |
|---|---|---|
| `test_claim_window_prefers_the_definition_body_and_stops_at_the_next_one` | `SC-015`'s body text | document moved |
| `test_line_of_maps_offsets_to_one_based_lines` | `spec.md` line 376 | document moved |
| `test_harness_field_count_matches_the_enumerated_list` | `{"FR-078": 18}` | FR-078 rewritten |
| `test_tripwire_constitution_cd_labels_are_phantoms` | `{CD-6, CD-7}` | repaired |
| `test_tripwire_tombstone_gate_is_red_today` | `tasks.md:143`, `spec.md:514` | document moved |
| `test_tripwire_a6_routes_structural_conflict_into_contradicted` | `spec.md:737`, `tasks.md:128` | document moved |

All 6 involve no function this change touched: `_claim_window`, `_line_of`,
`_harness_field_counts`, `RI-11-CONST`, `TOMBSTONED-FR-REF` and
`EPISTEMIC-AXIS-CONFLATION` are byte-identical old-vs-new in the §8.4 measurement. 7 of them
failed before this pass; `test_tripwire_orphan_fr_set` has since retired itself (its
`skip_if_repaired`-style guard fired, which is the tripwire design working).

The 21 skips are all `skip_if_repaired` / `if not fails: skip` tripwires whose defect token the
concurrent repair has already removed - `§1B`, `3411 lines`, `"Four named mutations"`, the
`≥ 20` / 18 contradiction, `"seven levels"`, `T007c`/`T007f`/`T011a`/`T011c`, the missing FR
column, `"17 mutations"`, the phantom `CD-n` labels, the principle mis-cites, the stale
`NOT yet created` claims. The anti-"always red" control is untouched and still green: the
synthetic self-consistent feature directory is 0 FAIL / exit 0, and all 30 check ids appear in
the summary as `ran, no findings`.

## 8.6 Limits added by this extension

* **An integer `§N` that resolves only inside the citing artefact is no longer a FAIL.** It is
  an INFO. A document with `## 42.` that cites `§42` meaning `input.md` §42, in a brief that has
  no §42, would be missed. The INFO names both files so the ambiguity is reviewable, and this
  is the only detection power the three fixes give up.
* **A dotted token that resolves nowhere is still a FAIL.** The brief's phrasing ("a decimal like
  `§1.5` ... should not be reported") was read as *resolve it against the artefact* rather than
  *never report decimals*, because the unconditional reading would let a dangling `§99.7`
  through. This is an interpretive call and is flagged as one.
* **A reference written as an abbreviated document name is not resolved.** On an earlier
  snapshot `tasks.md` carried three references of the form `A6 §5.2` / `A6 §5.3(d)`, which name
  `repair/A6-fr-triage.md` §5.2 and §5.3 - sections that exist. RI-08 reported them, and still
  does. Resolving `A6` to `repair/A6-fr-triage.md` by stem prefix is a heuristic over a naming
  convention that is still in flux, and a heuristic is how a linter becomes wrong; it was not
  added. The change that would cover it is one predicate in `_governing_file`: also accept a
  left-hand token matching `A\d+[a-z]?` when exactly one `repair/<token>-*.md` exists. Flagged
  for a decision, not taken.
* **A scalar field typed as a plain `*Hypothesis` is not nesting** (§8.1). Documented in the
  check's rule text so it is a stated scope, not a silent hole.
* **The named-file authority reads one file on demand** per distinct path. A file that is
  missing or unreadable resolves to nothing, so a reference into it is reported - the safe
  direction.



# 9. Extension - contiguity and tombstone classification (tool v1.3.0)

Two rules were wrong about the documents rather than about the authors. One assumed a plan
begins at `T001`; the other could not tell a *tombstone record* from a *requirement*. Both are
stated below as *rule before* / *rule after*, with the blind-spot controls that keep each fix
from costing detection power, the attributable delta measured on a frozen snapshot, and an
itemised account of **every finding that disappeared** and why. No severity changed. No check was
added or removed. No `.md` artefact other than this file was edited.

## 9.0 A measurement caveat, stated first, because it recurred

The `.md` artefacts were again being edited by another process throughout this pass, and this
time the edits landed *inside* the measurement window:

| Time (2026-09-27) | `spec.md` | `plan.md` | `research.md` | Observation |
|---|---|---|---|---|
| 20:30 | 157 578 B | 91 358 B | 14 628 B | the state the brief describes |
| 21:04:01 | 161 512 B | 91 358 B | 14 638 B | mid-rewrite |
| 21:04:48 | 160 888 B | 94 139 B | 14 638 B | torn intermediate state |
| 21:05:27 | 163 462 B | 94 139 B | 14 638 B | settled for this pass |

`tasks.md` did **not** move at any point in this pass (74 954 B, mtime 20:30:07), which is why
the `RI-06` half of the delta below is directly re-runnable rather than inferred.

Two consequences, both stated rather than papered over:

1. **The attributed delta is measured on a frozen snapshot.** The whole feature directory was
   copied once and both the pre-fix and post-fix tool were run in one process against those
   byte-identical files. That is the only comparison that attributes a finding to a rule.
2. **A first attempt at that A/B produced a wrong answer and was thrown away.** The
   pre-fix tool was reconstructed by reverse-applying the edits; the first reconstruction left
   `yield` outside the `if fr not in index:` guard, so it emitted a finding for *every* cited FR
   and reported `RI-01-FR-DEF 155 → 2` - a catastrophic-looking silent weakening that was in fact
   a broken baseline. The reconstruction was fixed and the 155 became 6. **A delta measured
   against an unreconstructed baseline proves nothing**, and this one nearly did.

The stated baseline **135 FAIL, 45 WARN, 68 INFO, exit 1, 30 check ids** was reproduced exactly
on the live directory at the start of this pass, before any edit, and is the basis of §9.4.

| Snapshot file (this pass) | SHA-256 (first 16) | bytes |
|---|---|---|
| `input.md` | `8E591907E31805EA` | 73230 |
| `spec.md` | `2561EDF325051AB0` | 163462 |
| `tasks.md` | `8484E6B13F2CC2A8` | 74954 |
| `plan.md` | `58D7FE1170B5C63E` | 94139 |
| `research.md` | `F68032657EB8A2F9` | 14638 |
| `data-model.md` | `AA041E5E793FB6F7` | 155291 |
| `checklists/requirements.md` | `0392493FBADFED14` | 71789 |
| `phase0-results.md` | `19C20B49798CBF78` | 15509 |
| `repair/A1-constitution-investigation.md` | `8040F68BECCB2ADA` | 136373 |
| `repair/A2-identity-subsystem.md` | `280F7D75E7BBE2F5` | 137266 |
| `repair/A4b-mapping-layer.md` | `1FA7EBBFBAA5DF15` | 148617 |
| `repair/A5-type-vocabulary.md` | `2BB79CC7757FE165` | 124693 |
| `repair/A6-fr-triage.md` | `D305321E75DAE722` | 116770 |
| `repair/A7-migration-021.md` | `390F9369C446AA82` | 139730 |
| `repair/A7b-reference-integrity-checker.md` | `7E22F507660FB4C1` | 74171 |
| `repair/A8prep-ownership-and-dag.md` | `55AB4AD1A0AACFD0` | 106382 |
| `repair/ARBITRATION.md` | `DF34F481C2EA3B6A` | 18033 |
| `.specify/memory/constitution.md` | `CE7549540FA45543` | 2346 |

## 9.1 FIX 1 - `RI-06-TASK-ORDER` contiguity is judged against the range the plan declares

### The defect

The integrated plan is `T101…T194`: 94 ids, ascending, no hole, no duplicate, no suffix. The
rule derived its expected set from `1`:

```python
expected = list(range(1, max(numbers) + 1))          # <- the whole bug
missing  = sorted(set(expected) - set(numbers))
```

`max(numbers)` is 194, so `T001`…`T100` were each reported as a missing task: **100 FAIL findings
on a plan with no gap in it.** Contiguity is a property of the range a plan *declares*, not of an
assumed origin.

### Rule, before

```python
if numbers:
    expected = list(range(1, max(numbers) + 1))
    missing = sorted(set(expected) - set(numbers))
    out_of_order = sorted({b for a, b in zip(numbers, numbers[1:], strict=False) if b <= a})
    for n in missing:
        yield _f(..., "task-gap", f"T{n:03d} is missing from tasks.md", [tasks.name], missing=n)
    ...
    if not missing and not out_of_order:
        yield _ok(..., "task-order-ok", f"task ids are contiguous and ascending: "
                                        f"T{numbers[0]:03d}..T{numbers[-1]:03d} ...")
```

### Rule, after

```python
if numbers:
    floor, ceiling = min(numbers), max(numbers)
    declared = list(range(floor, ceiling + 1))
    missing = sorted(set(declared) - set(numbers))
    ...
    for n in missing:
        yield _f(..., "task-gap",
                 f"T{n:03d} is missing from tasks.md: the declared range "
                 f"T{floor:03d}..T{ceiling:03d} is not contiguous",
                 [tasks.name], missing=n, declared_range=f"T{floor:03d}..T{ceiling:03d}",
                 declared_first=floor, declared_last=ceiling)
```

The floor comes from the file, so a hole **anywhere inside** `T101…T194` is still a hole, and
the finding still names the **actual missing number** (`data["missing"] = 150`), never a count.
`data` also carries the declared range so a reader can see the frame the gap was judged against.
The empty set is still handled by the pre-existing `if numbers:` guard and the single-task case
degenerates cleanly to a one-element range.

### What still fires, measured

| Input | Before | After |
|---|---|---|
| `T101…T194`, no gap | 100 FAIL | **0 FAIL**, 1 INFO `task-order-ok` (declared `T101..T194`, 94 ids) |
| `T101…T194` minus `T150` | 100 FAIL | **1 FAIL** `task-gap`, `missing=150` |
| `T101…T105` with a duplicated `T150` | 100 FAIL + dup | **1 FAIL** `task-duplicate` + gap |
| `T101, T102, T105, T103, T104` | 100 FAIL | **1 FAIL** `task-out-of-order` `number=103` |
| `T101…T104` plus `T104b` | 100 FAIL | **1 FAIL** `task-letter-suffix` |
| one task, `T101` | 100 FAIL | **0 FAIL**, 1 INFO |
| no tasks at all | 0 FAIL | **0 FAIL**, no exception |

## 9.2 FIX 2 - a tombstone record is not a live requirement

### The defect

`spec.md` retires a requirement by writing a record in the slot. At the start of this pass there
were four such rows:

```text
- **FR-058**: *tombstone — merged into `INV-004`; see the deleted-ids table in
  `repair/A6-fr-triage.md`. ... This slot carries no normative requirement and MUST NOT be
  cited as a live target.* (§108)
```

`DEF_RE` matches `**FR-nnn**:` in the bullet prefix, so the parser read each of those rows as a
**requirement definition**, and the row then propagated: it counted as a live definition, it was
eligible to be an orphan, and (once the live-definition population is separated) a citation of it
would have been reported as *undefined*.

### Rule, before

```python
m = DEF_RE.match(line)          # '- **FR-058**: *tombstone - ...'  -> a Definition
...
index = ctx.def_index()         # every matched row is a live requirement
for fr in sorted(cited):
    if fr not in index:         # a tombstone is either "defined" or "undefined": never right
        yield _f(..., "fr-undefined", f"{fr} is cited but never defined in spec.md")
frs = [d.ident for d in ctx.defs if d.ident.startswith("FR-")]   # tombstones counted as FRs
```

### Rule, after

The parser classifies. `parse_definitions` sets `Definition.tombstone`, and the checks that
decide whether an id is a *requirement* use `Context.live_defs` / `live_index()`:

```python
TOMBSTONE_RECORD_MARKERS = ("tombstone", "deprecated", "merged into", "absorbed into",
                            "folded into", "superseded by", "see adr")
TOMBSTONE_RECORD_RE = re.compile(
    r"^[\s*_`>–—(\[]*"
    r"(?:\b(?:FR|SC|INV)-\d+[A-Za-z]?\b[\s*_`>–—(\[]*)*"
    r"(?:" + "|".join(re.escape(m) for m in TOMBSTONE_RECORD_MARKERS) + r")\b",
    re.IGNORECASE,
)
```

Case-insensitive, as specified, and tolerant of the markdown decoration a record is written with
(`*tombstone — …`) and of a redundant self-naming token (`` `FR-058` tombstone — … ``).

**`RI-01-FR-DEF`** now (a) resolves citations against `live_index()` and (b) does not report a
tombstoned id as an undefined-reference target at all:

```python
index = ctx.live_index()
dead  = ctx.tombstone_ids
for fr in sorted(cited):
    if fr in index or fr in dead:
        continue
    yield _f(..., "fr-undefined", ...)
```

**`RI-03-FR-ORPHAN`**, **`RI-03b-FR-UNCITED`** and **`RI-04d-FR-OWNER`** iterate
`ctx.live_defs` instead of `ctx.defs`. Those three were not named in the brief; the extension is
justified in §9.5 and has **zero** effect on any measured run.

### The narrowing, and why it was necessary

The brief says "a definition whose **body carries** a tombstone marker". Implemented literally -
searching the whole body - the rule misclassifies **three live requirements** in this very
corpus:

| Row | Live requirement | Marker found, and where |
|---|---|---|
| `FR-035` | "External vocabularies … MUST produce a `TypeSignal`" | a `*Tombstone `FR-034a` - folded into this slot*` footnote in a **later paragraph** |
| `FR-040` | the `SignalKind` member list | a `*Tombstone `FR-039a` - folded into this slot*` footnote in a **later paragraph** |
| `FR-164` | the workflow stage order | "MUST NOT be **folded into** another stage", mid-sentence |

Classifying any of those as a tombstone would delete a real requirement from the definition
population, silently exempt its id from `RI-01-FR-DEF`, and — because the id would then also
enter the tombstone universe of §9.3 — turn **every live citation of it** into a
`tombstoned-fr-cited-normative` FAIL. So the marker must be what the body **opens** with. On the
real corpus the leading-clause rule finds exactly the four records and nothing else, and both
shapes are now pinned as tests in both directions.

### What still fires, measured

| Input | Expected | Result |
|---|---|---|
| tombstone row present, id never cited | 0 FAIL | 0 FAIL; `RI-03` INFO names the record and the row count |
| tombstone row + a real orphan `FR-005` | orphan FAIL | `RI-03-FR-ORPHAN` FAIL `["FR-005"]`, `total_frs=4`, `definition_rows=5` |
| tombstone row + **live** citation of `FR-058` | `TOMBSTONED-FR-REF` FAIL | FAIL `tombstoned-fr-cited-normative`, `replacement=INV-004`; `RI-01-FR-DEF` silent |
| tombstone row + citation of `FR-103` (never defined anywhere) | `RI-01-FR-DEF` FAIL | FAIL `fr-undefined` `FR-103` |
| both defects in one task line | two FAILs, on two checks | `RI-01` → `["FR-103"]`; `TOMBSTONED-FR-REF` → `["FR-058"]` |
| live FR that footnotes a tombstone (`FR-035` shape) | stays a live definition | `FR-005`/`FR-006` in `live_index()`, `tombstone` records `set()` |
| two records for one id | still a defect | `RI-01-FR-DEF` FAIL `fr-defined-twice` |
| a record for an id **outside** the arbitration map, cited live | must not go invisible | `FR-004` enters the tombstone universe, `TOMBSTONED-FR-REF` FAIL, exit 1 |
| a live requirement written beside a record | unaffected | `FR-005` live, `RI-01`/`RI-03`/`RI-03b` all clean |

## 9.3 The hole FIX 2 would have opened, and the one change this made to `TOMBSTONED-FR-REF`

Excluding a record from the live-definition population while leaving its id out of the tombstone
universe would make a **live citation of that id invisible to every check**: `RI-01-FR-DEF` no
longer reports it as undefined, and `TOMBSTONED-FR-REF` would not know the id exists. That is
precisely the "do not let the new classification hide a real dangling reference" failure mode, so
the tombstone universe is now derived rather than hard-coded:

```python
def tombstones(self) -> dict[str, str]:
    out = dict(TOMBSTONED_FRS)
    for d in self.def_occurrences:
        if d.tombstone:
            out.setdefault(d.ident, "the tombstone record in spec.md")
    return out
```

This is the **only** behavioural change made to `TOMBSTONED-FR-REF`, and it is an *extension* of
its id set, never a narrowing:

* the **line test is byte-identical** — a deprecation-marked line is history, anything else is a
  live normative target, and the FAIL / exemption logic is untouched;
* on the measured snapshot `tombstones()` returns exactly the same five ids as
  `TOMBSTONED_FRS`, so the summary text and the finding set are unchanged (0 findings added, 0
  removed);
* a record row can never *add* a FAIL, because a record's own line necessarily carries one of the
  parser's markers, and every parser marker is also a `DEPRECATION_MARKERS` entry. That invariant
  is asserted as a test rather than assumed: if it were ever violated, classifying a row would
  manufacture a `tombstoned-fr-defined-normative` FAIL out of a record.

**An interpretive call, flagged as one.** The brief also says `TOMBSTONED-FR-REF` "must still
fire on any live normative citation of a tombstoned id, **with or without a deprecation marker on
the citing line**". Read with the rule's own long-standing exemption, a marked line is by
definition *not* a live normative citation — that exemption is load-bearing in the other
direction and is asserted by a passing test
(`test_tombstoned_fr_cited_inside_a_deprecation_note_is_history_not_a_violation`). I therefore
left it alone rather than deleting a passing test, and I am reporting the residue instead of
quietly picking a reading:

> **Pre-existing limitation, not introduced here and not fixed here.** The exemption is
> *line-level*, so a line that mentions the tombstone in passing **and** normatively requires it
> is exempt. `"- [ ] T143 Implement the merged-into FR-058 obligation. (FR-058)"` would not be
> reported. Narrowing the exemption to "a marked line that states no obligation" is a real
> improvement and is **not** authorised by this brief, which said that rule is unchanged.

If you want the literal reading of that sentence, the change is one predicate in
`check_tombstoned_fr_refs` and it will flip exactly one currently-passing test. That is your
call, not mine.

## 9.4 The attributable delta, measured

Old rules vs new rules, one process, byte-identical snapshot (§9.0):

```
BEFORE  146 FAIL, 48 WARN, 69 INFO      exit 1     30 check ids
AFTER    42 FAIL, 48 WARN, 70 INFO      exit 1     30 check ids
```

| Check | FAIL before | FAIL after | WARN | INFO before | INFO after | What moved |
|---|---|---|---|---|---|---|
| `RI-01-FR-DEF` | 6 | **2** | 0 | 0 | 0 | −4 FAIL: the four retired ids |
| `RI-06-TASK-ORDER` | 100 | **0** | 0 | 0 | **1** | −100 FAIL, +1 INFO `task-order-ok` |
| all other 28 ids | — | — | — | — | — | **finding sets byte-identical** |

The 28 unchanged check ids are the no-regression evidence: the fix touched two rules and nothing
else. The two that changed are the two that were wrong.

### The state the brief describes

The brief's numbers were reproduced exactly at the start of this pass, before any edit:

```
135 FAIL, 45 WARN, 68 INFO      exit 1, 30 check ids
```

The fix's effect on **that** state is a pure subtraction plus one addition, and both halves are
independently verified rather than inferred:

```
34 FAIL, 45 WARN, 69 INFO       exit 1, 30 check ids
```

| Check | before F/W/I | after F/W/I | why |
|---|---|---|---|
| `RI-01-FR-DEF` | 2/0/0 | **1/0/0** | `FR-103` stays; `FR-034a` moves to `TOMBSTONED-FR-REF` |
| `RI-06-TASK-ORDER` | 100/0/0 | **0/0/1** | verified directly against the byte-identical `tasks.md` |
| `RI-03-FR-ORPHAN` | 0/0/1 | 0/0/1 | same count; message now distinguishes 153 rows from 149 live FRs |
| the other 27 ids | — | — | unchanged |

`RI-06-TASK-ORDER` was re-run on the live `tasks.md` in isolation, which is safe because that file
never moved during this pass:

```
[RI-06-TASK-ORDER] this run: FAIL=0 WARN=0 INFO=1
  INFO task-order-ok: task ids are contiguous and ascending across the declared range T101..T194
  (94 ids, 0 gaps, 0 reorderings)
```

The `FR-034a` half is unconditional — the id is in `TOMBSTONED_FRS`, so the skip does not depend
on the document at all — and is pinned by a synthetic test.

### The live directory, and why its numbers are a snapshot in time

```
21:19   37 FAIL, 43 WARN, 73 INFO      exit 1, 30 check ids
```

These are **not** comparable to the 135/45/68 above, because the corpus was repaired underneath
this pass. Since 20:30 the integrator has removed the `FR-103` citations (all three
`test_tripwire_phantom_fr_103` cases now skip), the four phantom task ids (`RI-02-TASK-REF` is
now 0 FAIL), the last unmarked tombstone citation, and the `spec.md` epistemic conflation.
**`RI-01-FR-DEF` is now 0 FAIL and `RI-02-TASK-REF` is now 0 FAIL on the live directory** — that
is the document being repaired, not this tool. `RI-08-SEC-CITE` still fires on `§34a`, now at
`spec.md:851` after the document moved; `RI-10-FORBIDDEN`, `RI-11-CONST` (`CD-6`),
`FR-NAMESPACE-COLLISION` and `COUNT-PRECISION` are all still firing at the same or comparable
strength.

One live FAIL is new since 20:30 and is **not** this change's, which is worth showing rather than
leaving for someone else to discover:

```
RI-09-COUNT FAIL checklists/requirements.md:37 claims '153 FRs' but the number of
                      FR definitions in spec.md is 149
```

`spec.md` lost four definition rows during the rewrite while that prose claim still says 153.
`RI-09-COUNT`'s FR basis is `len([d for d in ctx.defs ...])` — **definition rows**, not live
requirements — and `ctx.defs` is deliberately left holding every row (§9.5), so the pre-fix tool
reports this finding **identically**:

```
PREFIX: RI-09 fr_count basis = 149   ->  count-mismatch  153 vs 149
NEW:    RI-09 fr_count basis = 149   ->  count-mismatch  153 vs 149
```

Had `RI-09-COUNT` been switched to the live-definition population along with `RI-03`, this
finding would have read 153 against 145 and the number in the report would have been
indistinguishable from the real defect. Keeping the two populations distinct is what makes the
difference auditable.

## 9.5 Every finding that disappeared, itemised

**105 findings disappeared and 2 appeared** on the frozen snapshot. Nothing else moved.

| # | Disappeared finding | Count | Verdict |
|---|---|---|---|
| 1 | `RI-06-TASK-ORDER` / `task-gap` / `T001 … T100 is missing from tasks.md` | **100** | **true false positive.** The plan declares `T101…T194`; those 100 ids are not in its range and never were. Each was individually wrong, and each named a task that nobody intended to write. |
| 2 | `RI-01-FR-DEF` / `fr-undefined` / `FR-058 is cited but never defined` | 1 | **true false positive, wrong check.** `FR-058` is retired by `repair/ARBITRATION.md` §2. All four of its citations in the corpus carry an explicit history marker (`` `FR-058` tombstoned: merged into `INV-004` ``), so "never defined" was a true statement about the wrong question. |
| 3 | same, `FR-070` | 1 | as #2 |
| 4 | same, `FR-079` | 1 | as #2 |
| 5 | same, `FR-080` | 1 | as #2 |
| 6 | `RI-03-FR-ORPHAN` / `no-orphans` INFO, *text changed* | 1 | **not a defect, a re-worded receipt.** Same check, same severity, same meaning; the message now says "149 live FRs (of 149 rows) … 0 tombstone record(s) in spec.md and 5 further id(s) named by ARBITRATION §2 are excluded". Count unchanged at 1. |

Appeared:

| Finding | Verdict |
|---|---|
| `RI-06-TASK-ORDER` / `task-order-ok` INFO | the positive receipt for a clean declared range; this is the check now *measuring* rather than complaining |
| `RI-03-FR-ORPHAN` / `no-orphans` INFO, new text | as #6 |

**Nothing is labelled "rule weakened by mistake".** Specifically, the four `fr-undefined`
disappearances are the *only* place where a FAIL was removed by FIX 2, and each one is
individually accounted for: the id is in `ARBITRATION` §2's tombstone set, and
`TOMBSTONED-FR-REF` — which is the check that owns this class of defect and which names the
replacement target — still runs over the same ids. On the measured snapshot it reported 1 FAIL
before and 1 FAIL after, on the same finding, and the §9.3 extension guarantees it will report a
live citation of a record that is not in the hard-coded map. The gate was not weakened; the
misfiled copy of the report was removed.

### Detection power explicitly given up

One property, and it is written down as a test so it cannot be forgotten:

> **The floor of a plan can no longer be validated.** The old rule anchored every plan at
> `T001`, so a plan whose *first* id is not the id it should have started at was detectable.
> The new rule takes the floor from the file, so `T103, T104, T105` is clean whether or not
> `T101` and `T102` were meant to exist. Asserted verbatim in
> `test_the_floor_itself_can_never_be_validated_and_is_not_claimed`, alongside the control that
> a hole at the floor of the *declared* range (`T103, T105, T106` → `T104`) is still a FAIL.
>
> Closing it needs an external anchor — a plan that declares its own range, or a feature-number
> derived first-id convention. That is a change to the plan format, not to the checker.

Two further narrowings, both named:

* **A leading-clause tombstone marker, not any marker in the body** (§9.2). A live requirement
  whose body *begins* with "deprecated" or "tombstone" and then states an obligation would be
  misread. No such requirement exists in this corpus; the boundary is pinned from both sides.
* **A repair document's bold-titled FR is not classified as a record.** `FR-NAMESPACE-COLLISION`
  parses `repair/*.md` with a separate parser that this change deliberately does not touch, so a
  tombstone record written there still counts as a definition site. Changing it would have moved
  that check's findings, and the brief requires `FR-NAMESPACE-COLLISION` to keep firing.

## 9.6 The named real defects, re-verified after the change

Every defect the brief requires to keep firing, checked on the frozen snapshot, `BEFORE` vs
`AFTER`:

| Required to keep firing | BEFORE | AFTER | Held |
|---|---|---|---|
| `FR-103` phantom | FAIL | FAIL | yes |
| phantom task `T001` | *see note* | *see note* | — |
| phantom task `T002` | *see note* | *see note* | — |
| phantom task `T014` | *see note* | *see note* | — |
| phantom task `T019` | *see note* | *see note* | — |
| `EPISTEMIC-AXIS-CONFLATION` on `spec.md` | 5 FAIL | 5 FAIL | yes (repaired by the integrator at 21:12; the check is untouched) |
| `FR-NAMESPACE-COLLISION` | 5 FAIL | 5 FAIL | yes |
| `COUNT-PRECISION` on "seven classes" | 3 WARN | 3 WARN | yes |
| `RI-08-SEC-CITE` on `§34a` | 1 FAIL | 1 FAIL | yes (`spec.md:783` on the snapshot, `spec.md:851` live) |

*Note on the phantom tasks.* On the state the brief describes, `T001`/`T002`/`T014`/`T019` are
reported by `RI-02-TASK-REF` as 4 FAILs, and `RI-02-TASK-REF` is **byte-identical** before and
after in the §9.4 measurement. They do not appear in the frozen-snapshot table because the
integrator repaired them between 20:30 and the snapshot, which is why the current live run shows
`RI-02-TASK-REF 0`. The requirement that they must keep firing is a property of the tool, and
`test_phantom_fr_and_phantom_task_fail_the_gate` plus the five `test_tripwire_phantom_task_ids_*`
cases hold it. Nothing in this change touches `TASK_TOKEN_RE`, `RI-02-TASK-REF` or
`check_task_refs`.

`EPISTEMIC-AXIS-CONFLATION`'s `spec.md` finding was at `spec.md:732` on the frozen snapshot and
was repaired by the integrator at 21:12, so the live run no longer shows it (5 FAILs, all in
`repair/`). The check is byte-identical either way. `RI-08-SEC-CITE`'s `§34a` FAIL survives the
rewrite and is at `spec.md:851` live, `spec.md:783` on the snapshot.

## 9.7 Tests — suite 139 → 187 collected; **6 failed → 0 failed**

```
before:  112 passed,  6 failed, 21 skipped      (139 collected)
after:   164 passed,  0 failed, 23 skipped      (187 collected)
```

`ruff check` (`E,F,I,B,UP`, line-length 100) passes on both files.

### The five pre-existing failures, what each was pinned to, and where it now points

None was deleted or loosened. Each was re-pointed at a stable anchor, and each new form still
fails if the property it guards regresses.

| Was failing | Was pinned to | Cause | Now anchored on | Still fails if |
|---|---|---|---|---|
| `test_claim_window_prefers_the_definition_body_and_stops_at_the_next_one` | the literal prose of `SC-015`'s body | the integration rewrote `SC-015` | the parsed `SC-015` definition itself: `window == sc15.body`, plus the neighbouring `SC-015`/`SC-014` ids absent, plus a line outside any definition getting the *paragraph* window instead | `_claim_window` widens its context, or stops at a definition boundary |
| `test_line_of_maps_offsets_to_one_based_lines` | `spec.md` line **376** for `FR-001` (now 397, and the document has grown further) | 21 lines inserted above | the `FR-001` **definition row**: the char-offset search and the line-walking parser must agree on its line, plus the first-line and last-line ends | the two offset→line implementations disagree, or `FR-001` stops being a definition row |
| `test_harness_field_count_matches_the_enumerated_list` | the literal `{"FR-078": 18}` | the §93 manifest obligation left `FR-078`; the counter now reads `FR-131` (and mis-parses a `D2.4)` fragment of a §-locator — a **pre-existing** bug in `_harness_field_counts`, not touched here) | **split in two**: (a) the contract — the counter's keys are exactly the definition rows whose body carries the `MUST break` clause, every value positive, and at least one such row exists; (b) the arithmetic, pinned exactly (`6`, then `7` when a field is added, `{}` for a clause with no enumeration) on a **synthetic** `FR-003` the integration cannot move | a `MUST break` FR is miscounted, or the keys drift from the clause |
| `test_tripwire_constitution_cd_labels_are_phantoms` | the exact set `{CD-6, CD-7}` | `CD-7` was repaired, so only `CD-6` remains and the equality broke | the **constitution**, which is the actual invariant: it contains no `CD-n` label at all, every reported label is drawn from the set this corpus has ever invented (a new one still fails the test), and each is genuinely absent from the constitution | the constitution starts labelling its invariants, or a new phantom label appears |
| `test_tripwire_tombstone_gate_is_red_today` | the pairs `("FR-058","tasks.md:143")` and `("FR-034a","spec.md:514")` | the integration rewrote both lines *and* moved the live citation to `research.md:143` | an **independent re-derivation** of the expected set from the documents — a second, literal implementation of `ARBITRATION` §2 — compared for **exact set equality** with what the check reports, plus per-finding structural assertions and a cross-check that `RI-01-FR-DEF` never claims a tombstoned id | the gate over- or under-reports against its own rule |
| `test_tripwire_a6_routes_structural_conflict_into_contradicted` | `spec.md:737`, `tasks.md:128`, `repair/A6-fr-triage.md:187` | the integration moved all three and repaired the `spec.md` one entirely | the **rule**: every reported unit really does pair a structural term with `CONTRADICTED`, never states a prohibition, is FAIL, and its prose unit is locatable in the file it names; the check's declared scope (`spec.md` + `tasks.md`) is asserted separately from its findings, plus a companion that the corpus is still red somewhere | the check reports a prohibition as a violation, or reports a unit that lacks one of the two halves |

Two of these deserve a note beyond the table:

* The tombstone tripwire is now **skipped** on the live corpus, because the integrator has
  removed the last unmarked tombstone citation. The skip message says exactly that. The test is
  not vacuous-by-construction: it becomes active again the moment a marked citation is dropped.
* The epistemic tripwire was **split** rather than re-pointed, because its original assertion
  ("`spec.md` still carries the conflation") is a statement about a defect the integrator has now
  repaired. Asserting it would have meant keeping a red test forever, or weakening the assertion
  to nothing. The rule-level test and the "still red somewhere" test are separate, and the
  second retires itself when the corpus is clean.

### Tests added — 24 new functions, 48 new collected items

| Group | Test | Proves |
|---|---|---|
| FIX 1 | `test_required_regression_a_plan_above_T001_with_no_gap_is_clean` | **the required regression**: `T101…T194` → 0 FAIL/WARN, one `task-order-ok`, declared range in the data, exit 0 |
| FIX 1 | `test_required_regression_a_hole_inside_the_declared_range_still_fails` | **the required regression, other half**: `T101…T194` minus `T150` → 1 FAIL, `missing=150`, the actual number not a count, exit 1 |
| FIX 1 | `test_a_duplicate_task_id_still_fails` | **blind-spot control** |
| FIX 1 | `test_an_out_of_order_task_still_fails` | **blind-spot control**: `T101, T102, T105, T103, T104` → FAIL `number=103` |
| FIX 1 | `test_a_letter_suffixed_task_id_still_fails_inside_a_high_range` | **blind-spot control** |
| FIX 1 | `test_a_single_task_and_an_empty_task_list_do_not_raise` | the degenerate shapes, no `check-crashed` |
| FIX 1 | `test_the_declared_range_is_derived_from_the_file_not_assumed` | the rule as arithmetic: `T401…T405` and `T001…T005` both clean |
| FIX 1 | `test_a_mixed_range_below_its_own_floor_is_reported_as_two_gaps` | a 4-wide hole names **every** missing number, with the declared range attached |
| FIX 1 | `test_the_floor_itself_can_never_be_validated_and_is_not_claimed` | **the given-up power, asserted** (§9.5) |
| FIX 1 | `test_the_real_tasks_md_is_contiguous_across_its_own_range` | **the real plan**, re-pointed at its declared range |
| FIX 1 | `test_tripwire_the_real_tasks_md_has_no_gaps_in_its_own_range` | the real plan, ascending, no duplicates, 0 FAIL/WARN, and still offset from `T001` |
| FIX 2 | `test_a_tombstone_row_is_not_a_requirement_definition` | classified as a record; still a definition **row**; not a live definition |
| FIX 2 | `test_a_tombstone_is_not_an_orphan` | `RI-03` + `RI-03b` clean; the record is named separately from the row count |
| FIX 2 | `test_a_genuine_orphan_next_to_a_tombstone_is_still_reported` | **blind-spot control** |
| FIX 2 | `test_a_tombstone_row_is_not_reported_as_an_undefined_reference` | the fix |
| FIX 2 | `test_a_live_citation_of_a_tombstoned_id_still_fails` | **required**: `TOMBSTONED-FR-REF` FAIL with the replacement target; `RI-01-FR-DEF` silent; exit 1 |
| FIX 2 | `test_a_genuinely_undefined_id_still_fails_the_definition_check` | **required**: `FR-103` still FAILs `RI-01-FR-DEF`, and `TOMBSTONED-FR-REF` does not claim it |
| FIX 2 | `test_an_undefined_id_next_to_a_live_citation_of_a_tombstone_reports_both` | both defects, each on the check that owns it |
| FIX 2 | `test_every_accepted_marker_opens_a_tombstone_record` (14 cases) | the whole marker list, case-insensitive, in three decorations |
| FIX 2 | `test_a_live_requirement_that_merely_mentions_a_marker_stays_live` (6 cases) | **the narrowing, pinned**: the `FR-035` / `FR-040` / `FR-164` shapes |
| FIX 2 | `test_a_live_fr_that_footnotes_a_tombstone_is_still_a_definition_target` | the same, end to end, with a non-vacuous `FR-103` control |
| FIX 2 | `test_a_tombstone_record_is_never_a_live_normative_definition` | **the safety invariant of §9.3**: every parser marker is also a `DEPRECATION_MARKERS` entry |
| FIX 2 | `test_a_tombstone_record_outside_the_arbitration_map_is_still_gated` | **the anti-hole control** of §9.3 |
| FIX 2 | `test_a_live_requirement_written_beside_a_record_is_not_swallowed` | a record does not take a neighbouring live FR with it |
| FIX 2 | `test_a_tombstone_record_does_not_duplicate_under_its_own_id` | the duplicate rule still sees two records for one id |
| FIX 2 | `test_the_real_spec_md_tombstone_records_are_recognised_as_records` | **the real document**, anchored on shape, not line numbers |
| §9.3 | `test_tripwire_tombstone_gate_reports_exactly_the_live_references` | the gate vs an independent re-derivation, exact set equality |
| §9.3 | `test_tripwire_a_retired_id_is_cited_live_somewhere` | the gate is red today, retiring itself when repaired |
| §9.6 | `test_tripwire_every_reported_conflation_really_is_one` | the epistemic rule, line-number free |
| §9.6 | `test_tripwire_a_conflation_is_still_live_somewhere` | the corpus is red today, retiring itself when clean |
| §8.5 | `test_harness_field_count_keys_are_exactly_the_frs_that_state_the_obligation`, `test_harness_field_count_counts_the_enumerated_fields_of_a_must_break_fr` | the re-pointed counter, contract and arithmetic |

### The anti-"always red" control, re-verified

```
FAIL: 0  WARN: 1 (constitution-missing, the temp dir has no .specify/)  INFO: 19
exit code: 0
check ids in summary: 30 of 30
every id present: True     every id ran: True     all reported clean: True
```

The same directory with one hole punched into its own declared range goes red
(`RI-06` FAIL `missing=150`, exit 1), so the control is measuring, not idling. `RI-03b-FR-UNCITED`
and `RI-12-STALE` report no findings on this corpus either; that is the synthetic fixture's
content, not a check that stopped running — both appear in the summary as `ran, no findings` and
both are exercised by their own tests.

## 9.8 Two pre-existing weaknesses found, reported, deliberately not fixed

Found while measuring. Both are outside this brief; both would *add* findings if fixed, which is
why they are flagged rather than taken.

1. **`RI-03b-FR-UNCITED` cannot fire.** It asks whether a defined FR "is cited by no artefact at
   all", but it collects citations from every scanned artefact **including `spec.md`**, and an
   FR's own definition row is itself a citation of that FR. The check is therefore unsatisfiable
   on any corpus. It has produced 0 findings on every state measured in this pass, including the
   one where 153 FRs were live. FIX 2 changed which population it iterates (`live_defs` instead
   of `defs`), which is correct but does not make the rule satisfiable. The fix is to exclude the
   FR's own definition site from the citation set.
2. **`_harness_field_counts` mis-parses a §-locator.** It counts comma-separated pieces of every
   parenthesised group in a `MUST break` FR, and `cleaned.startswith("§")` only rejects the
   *first* piece of `(§19, §22, §23, §104; A4b D2.3, D2.4)` — so `D2.4)` is counted as a field.
   That is where the current `{'FR-131': 1}` comes from. It feeds `RI-09-COUNT`'s `invariants`
   counter, so any artefact claiming "N invariants" in a mutation/`break` context is compared
   against 1 and would be a false FAIL. It produces no finding today, so changing it would alter
   `RI-09-COUNT`'s counter basis for no measured gain. Left alone and named.

## 9.9 Files touched by this pass

* `repair/tools/reference_check.py` — `TOOL_VERSION` 1.2.0 → 1.3.0; `RI-06-TASK-ORDER`;
  `Definition.tombstone`; `TOMBSTONE_RECORD_MARKERS` / `TOMBSTONE_RECORD_RE` /
  `is_tombstone_record`; `parse_definitions`; `Context.tombstone_ids` / `live_defs` /
  `live_index()` / `tombstones()`; `build_context`; `check_fr_definitions`;
  `check_fr_orphans`; `check_fr_uncited_anywhere`; `check_fr_owners`;
  `check_tombstoned_fr_refs`; six `CheckSpec.rule` strings.
* `repair/tools/test_reference_check.py` — 24 new test functions, 5 pre-existing failures
  re-pointed, 2 tripwires split.
* `repair/A7b-reference-integrity-checker.md` — this section, appended.

No severity was changed. No check id was added, removed or reordered. No dependency was added;
the standard library only. No `.md` artefact other than this file was edited, and no `apps/` code
was touched.


---

# 10. Tooling scoping fixes (three named rules)

Three rules, each with a stated reason. `TOOL_VERSION` 1.3.0 -> 1.4.0. Appended; nothing
above this line was edited.

Each rule is recorded here with the reason it exists, the rule used to draw its boundary, and
the power it gives up. The power given up is stated in the same place as the rule, because a
scoping decision whose cost is only written down somewhere else is a scoping decision nobody
can audit.

## 10.1 `RI-06b-FR-ORDER` must not read a retired id as a gap

**Reason.** `spec.md` §"Tombstone record" retires `FR-058`, `FR-070`, `FR-079` and `FR-080`
in a *record table*, deliberately not in definition form, so a retired id has no
`- **FR-nnn**:` row. The contiguity walk reads the definition index, so each retired id looks
like a hole between two live numbers. Six tombstones times the neighbours they sit between was
19 FAIL findings asserting, in effect, "un-retire this id".

**Rule.** A gap is decided against the *requirement sequence*, not against the local interval:
a number is a gap only when it is neither defined anywhere in `spec.md` nor tombstoned.
Implemented as `_recorded_fr_numbers()` = `FR-` numbers in `ctx.defs` ∪ `_fr_number(t)` for
every id in `ctx.tombstone_ids`, and `_sequence_gaps(lo, hi, recorded)`.

**Kept intact.** The rewind arms (`fr-non-monotonic`, `fr-non-monotonic-document-order`) and
`fr-dangles-after-table` are untouched; a rewind is not a gap. `check_rows_cite_fr`'s
`row-cites-unknown-fr` is a different check and untouched.

**Power given up, named.** A requirement number allocated to a *different section* than its
neighbours is no longer reported by the contiguity arm. `spec.md` interleaves its canonical
requirement sections with per-workstream allocation bands, so this is a real class of defect.
It is now reported by the rewind arm instead (an interleaved document rewinds by construction),
and `RI-01-FR-DEF` / `RI-03c-FR-COLUMN` still police the mapping. `test_a_number_defined_in_another_section_is_not_a_gap`
asserts the trade explicitly rather than leaving it implicit.

## 10.2 `repair/*.md` is a historical record, not normative content

**Reason.** A repair document records the state of its subject *at the moment it was written*.
`A4b` routed a structural conflict into `CandidateStatus.CONTRADICTED`; `A6` wrote "all seven
classes of §8". Both were correct for their moment and both were superseded by
`ARBITRATION.md` §3 and §10. Linting them as normative is a category error: it demands
rewriting history to satisfy a later decision, and no edit to a signed record can make it
agree with a ruling that did not exist when it was written.

**Rule - the line drawn.** A finding is demoted when, and only when, **its subject is the
content of the sentence**: what the document asserts to be true about the design. A finding is
never demoted when **its subject is a reference the document makes**: whether an id it points
at resolves.

The distinction is not "old file versus new file". A repair document that says "seven classes"
is stating what the brief said in September - superseded, reportable, not gating. A repair
document that says "`FR-103` is the requirement for X" is claiming a number in a namespace,
and whether that number exists is a fact no arbitration can change retroactively. History can
record a superseded opinion. It cannot make a number appear.

In one sentence: **demote when the finding would be repaired by changing what the document
says; keep FAIL when the finding would be repaired only by changing what some other document
is obliged to define.**

**Exempt set** (`NORMATIVE_LINT_CHECKS`, a named constant, not a heuristic):
`EPISTEMIC-AXIS-CONFLATION` (§3), `FR-NAMESPACE-COLLISION` (§1/§14), `COUNT-PRECISION` (§10),
`RI-10-FORBIDDEN` (§10, §14 rule 4). Not exempt, with reasons on the record in
`REFERENCE_INTEGRITY_NOT_EXEMPT`: `RI-01-FR-DEF`, `RI-02-TASK-REF`, `RI-06b-FR-ORDER`,
`RI-08-SEC-CITE`, `RI-09-COUNT`, `RI-11-CONST`, `RI-11b-RESEARCH`, `TOMBSTONED-FR-REF`, and
`GHOST-SUFFIX`. `GHOST-SUFFIX` is namespace hygiene over *citations*, so by the rule above it
would qualify; it is left at WARN anyway, so the exemption would buy nothing, and widening the
exempt set is the move this design refuses to make silently.

**Not silenced.** Every finding that would have fired is still emitted, at INFO, under the one
greppable code `historical-divergence`, naming the artefact, the code and severity it would
have had, its original message verbatim, and the `ARBITRATION.md` section that superseded it
(`SUPERSEDING_AUTHORITY`). One `historical-divergence-summary` INFO per run states how many
were demoted and from which checks, so the aggregate is auditable too.

**Mechanism.** `demote_historical()` runs as a single pass over the whole result set inside
`run_checks`, not as an `if` at each yield site. A new yield site in any exempt check therefore
cannot forget the exemption. A finding that is already INFO is left byte-identical, and a
finding that names no `repair/` site is never demoted - absence of evidence is not evidence of
history, so the exemption can never be inferred from a finding that forgot to say where it was.

**Reference integrity inside `repair/` - the blind spot this closes.** `RI-01-FR-DEF` and
`RI-02-TASK-REF` previously did not read `repair/` at all, so *every* reference in the
governance corpus was invisible. They now do, split by what the citing line **is**
(`Context.repair_claims`): a definition site - a `- **FR-nnn**:` row, a bold-titled requirement
claim, or a `- [ ] Tnnn` bullet, outside any fence - is a claim on the namespace and FAILs
(`fr-undefined-in-repair`, `task-phantom-in-repair`); any other mention is narrative of an
earlier numbering and is aggregated into one `repair-historical-reference-summary` INFO. A
fenced block is quotation and is never a claim, on the rule `FR-NAMESPACE-COLLISION` already
uses. An id embedded in a longer identifier (`CHK-FR-01` contains `FR-01`) is not a reference
and is not reported.

**On the brief's `FR-103` example, stated plainly.** `ARBITRATION.md` §1 names `FR-103` as the
number no agent may claim, and A1 proposes it - but A1 proposes it inside a ```` ```markdown ````
fence, i.e. as quoted proposed text, so under the fence rule it is a quotation and is counted,
not gated. The rule fires on A2's `**FR-104 - ...**` and A6's `**FR-101 (NEW) - ...**`, which
are live bold-titled claims in prose. The rule is the same in both cases; the corpus instances
differ because one of them is quoted and the other is not. Named here rather than papered over.

**Power given up, named.** Two things. (a) A `repair/` document's *content* claims no longer
gate, so a real normative error written into a repair document after the arbitration record
will be reported at INFO and will not turn the gate red - the integrator must read the
`historical-divergence` findings. That is the intended trade and it is the whole of the rule.
(b) `RI-01-FR-DEF` / `RI-02-TASK-REF` now read 9 more files per run, so their cost and their
finding count both rose; the counts are aggregated deliberately, because 519 historical task
mentions reported as 519 findings would bury the five that matter.

## 10.3 The `core:*` / `value:*` vocabulary must be *owned*, not per-term backed

**Reason.** The rule counted 44 terms and demanded a producer for each, so it demanded the
exact opposite of `ARBITRATION.md` §10 and §14 rule 4, which decide in terms that "a type in
the vocabulary != the system must have a dedicated extractor for it, and its absence != a
refusal". A rule that fights a binding decision is a bug in the rule, not in the document.

**Rule.** The unit of judgement is the vocabulary, not the term. An owner exists when a live
FR (a) enumerates a `core:*`/`value:*` term, or an enumerator delegates to it by name;
(b) states an obligation (`MUST` / `required` / `obliges`); and (c) bounds that obligation to
something other than the length of the list. Delegation must be an explicit deferral clause -
an obligation noun, a deferral predicate and the FR id in one sentence - so a number mentioned
in a renumbering footnote is not mistaken for a delegation.

**Three shapes still FAIL, owner or not**, because an owner cannot repair them:
`vocabulary-completeness-asserted` (membership asserted to entail production),
`vocabulary-used-as-gate` (membership decides admission), `vocabulary-unowned` (nothing states
and bounds an obligation at all).

**Measured on the corpus.** 44 terms, enumerators `FR-030` / `FR-031` / `FR-135`, owners
`FR-030` (enumerates) and `FR-179` (`FR-030` delegates to it by name) - the two the brief
names. Reported as `vocabulary-owned` INFO, which states explicitly that per-term backing is
not checked and why.

**Power given up, named.** The rule no longer has any opinion about a term that has no
producer. That is the brief's explicit instruction and it is a real loss: a vocabulary that
lists a type nobody will ever extract is now invisible to this check, and nothing else in the
registry looks at per-term producer coverage. Accepted deliberately, and named here.

## 10.4 Defects this pass found and did not fix

1. **`FR-039a` is not in the checker's tombstone universe.** `spec.md`'s record table lists six
   retirements; `TOMBSTONED_FRS` carries five. `Context.tombstones()` also learns definition-row
   records, and the table is not in definition form, so nothing learns the sixth. A live
   citation of `FR-039a` is therefore reported by nobody. **Not fixed here**: adding it changes
   the tombstone universe, which is `ARBITRATION.md` §2's to set, and it would turn any live
   citation into a FAIL - a change to a check this brief did not name. `GHOST-SUFFIX` already
   WARNs that `FR-039a` is still cited in 17 places, so the id is not invisible; it is
   *ungated*. Named, not silently left.
2. **`RI-06b-FR-ORDER`'s remaining 15 FAILs are not tombstone artefacts.** Six are
   `fr-non-monotonic-document-order` rewinds caused by the section/band interleaving, and nine
   are contiguity gaps naming the 27 numbers that no artefact defines and no record retires
   (`FR-101…FR-109`, `FR-116…FR-129`, `FR-138`, `FR-139`, `FR-159`, `FR-160`) - which
   `ARBITRATION.md` §14 declares VOID / RESERVED and leaves empty on purpose. FIX 1 removes the
   tombstone false positives and sharpens the rest; it does not and cannot make this check
   green, because the corpus genuinely leaves 27 numbers unaccounted for.
3. **`_harness_field_counts` still mis-parses a `§`-locator** (carried over from §9.8, still
   open).
4. **`RI-03b-FR-UNCITED` still cannot fire** (carried over from §9.8, still open).

## 10.5 Files touched by this pass

* `repair/tools/reference_check.py` - `TOOL_VERSION` 1.3.0 -> 1.4.0. Rewritten:
  `check_fr_order`, `check_fr_definitions`, `check_task_refs`,
  `_forbidden_vocabulary_without_producer`. Added: `demote_historical`, `is_historical_site`,
  `_finding_sites`, `NORMATIVE_LINT_CHECKS`, `SUPERSEDING_AUTHORITY`,
  `REFERENCE_INTEGRITY_NOT_EXEMPT`, `HISTORICAL_CODE`, `Context.repair_claims`,
  `_split_repair_references`, `_standalone_id`, `_historical_mentions_note`,
  `_recorded_fr_numbers`, `_sequence_gaps`, `_fr_number`, `_fmt_fr_list`, `defn_line`,
  `_vocabulary_terms`, `_vocabulary_owners`, `_deferral_targets`, `_states_a_non_count_bound`,
  `_clauses`, `_flatten`, and the `_VOCAB_*` / `_BOUND_*` / `_COMPLETENESS*` / `_DEFERRAL_*` /
  `_OBLIGATION_RE` patterns. Seven `CheckSpec.rule` strings. `run_checks` gained one pass.
  One incidental fix: `FR-NAMESPACE-COLLISION`'s `data["shape"]` said `spec-vs-repair` for a
  pair of two `spec.md` sites, which sent a reader looking for a repair document that was not
  in the pair; it now distinguishes `repair-vs-repair` / `spec-vs-repair` / `spec-vs-spec`.
* `repair/tools/test_reference_check.py` - 226 collected / 200 passed / 0 failed / 26 skipped,
  from 187 / 164 / 0 / 23. **39 new test functions**, 2 renamed, 7 pre-existing tests
  re-pointed at the new behaviour (each naming in its docstring the behaviour it used to
  pin). Test functions: 115 -> 183 against the last commit; the extra committed-to-working
  delta belongs to the tombstone pass recorded in section 9, not to this one.
* `repair/A7b-reference-integrity-checker.md` - this section, appended.

No check id was added, removed or reordered; all 30 are present in the summary of every run.
No declared severity was changed. No dependency was added; the standard library only. No `.md`
artefact other than this file was edited, and no `apps/` code was touched.

---

## 11. Coverage, not density: the `FR-` numbering rule is rewritten (four mechanical fixes)

This section is appended, not merged: everything above is the record of what the checker was, and
this is the record of what it now is. The four fixes below are the ones §10.5 could not close.

### 11.1 FIX 1 — `RI-06b-FR-ORDER` now asks "is every number accounted for?" instead of "are these
numbers adjacent?"

§10.5 item 2 recorded the diagnosis and declined the fix: 15 FAIL findings, of which 6 were
document-order rewinds and 9 were contiguity gaps naming 27 numbers that `ARBITRATION.md` §14
declares VOID / RESERVED and leaves empty on purpose. The rule could not tell a *deliberately
reserved* number from an *accidentally missing* one, because there was no third category to put
the first in — and that is the same blind spot that let `FR-103` be cited as a live requirement
for as long as it was.

The rule is now **coverage with three admitted categories**:

```text
every FR number is DEFINED  or  TOMBSTONED  or  RESERVED
```

* **DEFINED** — a live `- **FR-nnn**:` row anywhere in `spec.md`. `spec.md` interleaves its
  canonical sections with per-workstream allocation bands, so "not in this interval" was never the
  same claim as "absent from the document".
* **TOMBSTONED** — unchanged: `spec.md`'s record table plus `ARBITRATION.md` §2's map.
* **RESERVED** — new, and **parsed from `spec.md`**, never hard-coded here. The tool reads one
  machine-readable line inside the existing reserved-number-space blockquote:

  ```text
  `RESERVED-FR: 101-109, 116-129, 159-160`
  ```

  Four properties of that decision, each pinned by a test:

  1. **Parsed, not hard-coded.** `test_the_reservation_is_parsed_from_spec_md_and_not_hard_coded`
     asserts the parsed ranges equal `((101,109),(116,129),(159,160))` *and* that the declaration
     line is where `spec.md` says it is. A literal in the tool would fail this.
  2. **No block means no exemption.** A document that declares nothing exempts nothing, reported
     as INFO `no-reservation-declared`. Declaring a reservation is opt-in.
  3. **An unreadable reservation is FAIL and exempts *nothing*.** Two blocks, no declaration line,
     two declaration lines, an unparseable range, `lo > hi`, overlapping ranges, an empty
     declaration — all FAIL, all with an empty reserved set. This is the direction that matters: a
     partially-read reservation that quietly exempted half of what it read would turn a parsing
     bug into a green gate. Five parametrisations pin it.
  4. **Machine/prose drift is FAIL.** Every range the `RESERVED-FR:` line declares must also appear
     as a range in the block's own prose, so the machine view and the human statement cannot
     diverge in silence.

**Severity, arm by arm.** Only one arm of this check FAILs now, and it is the coverage arm:

| arm | was | is | why |
|---|---|---|---|
| `fr-gap` (unaccounted number, one per number) | FAIL, per *interval* | **FAIL** | the rule. Unchanged in severity, rewritten in *meaning*: it now fires on a number that is DEFINED by nothing, TOMBSTONED by nothing and RESERVED by nothing, wherever it is noticed, exactly once. |
| `fr-gap-in-section` (a section's own list skips numbers) | was `fr-gap` at FAIL | **INFO**, new code | placement by subject section is a legitimate authoring choice, not a defect. The interval is still reported, split into defined-elsewhere / tombstoned / reserved / unaccounted. |
| `fr-gap-document-order` | FAIL | **INFO** | as above, at document-order granularity. |
| `fr-non-monotonic-document-order` (document-order rewind) | FAIL | **INFO** | as above. `spec.md` defines `FR-174…178` in the identity section and `FR-179/180` in the §8 section, so the file cannot read as one ascending run and is not trying to. |
| `fr-non-monotonic` (rewind **within one** section) | FAIL | **FAIL** | *unchanged, deliberately.* A rewind inside a single requirement list is a list whose own numbering contradicts itself, and subject-section placement does not explain it. It fires 0 times today, so keeping it costs nothing and the two rewind arms cannot be swapped by accident. |
| `fr-dangles-after-table` | FAIL | **FAIL** | unchanged. |
| `reservation-declaration-unreadable` | — | **FAIL** | new; see (3) above. |
| `no-reservation-declared` / `reservation-declared` / `fr-sequence-ok` | — | **INFO** | new/rewritten; the walk reports that it ran and what it decided. |

**`FR-159` / `FR-160` — added to the declared reservation, and why that is not a loosening.**
`spec.md` already recorded the decision in prose at the "measured divergence from §14's table"
paragraph: §14 gives A7 the range `150`–`160` and counts 11, A7 authors 9, `spec.md` defines all 9,
so the occupied part is `150`–`158` and "the last two slots of §14's range name no requirement
anywhere", unfilled because §14 rule 1 forbids minting a number. FIX 1 promotes that already-stated
decision into the machine-readable declaration, so the emptiness reads as a decision rather than a
hole. Nothing was invented; the prose was already there and the checker simply could not see it.

**`FR-138` / `FR-139` — left FAILING, on purpose.** These sit in the seam between A4b's band
(`FR-130…FR-137`) and A5's (`FR-140…FR-149`). §14 allocates that seam to nobody, `spec.md` defines
neither, no record retires either, and the reservation block does not claim them. Under the old
density rule they were invisible: two entries inside a 30-number document-order gap whose other 28
members were reserved, so nothing isolated them. The new coverage arm isolates them, and they are
the check's remaining 2 FAIL. **They are not reserved away.** Declaring a gap on purpose is an
authoring decision that belongs in `spec.md`; making it inside the checker to reach a green gate
would be the tool inventing an intent the document does not record — which is the same failure, one
level up, as the hard-coded list FIX 1 removed. Closing them means either authoring `FR-138`/`139`
or declaring them reserved in `spec.md`; both are the spec owner's calls, not the checker's.

`test_the_real_spec_leaves_exactly_two_unaccounted_numbers_and_they_are_reported` pins
`unaccounted == [138, 139]` on the real corpus, so this hole cannot be quietly forgotten.

### 11.2 FIX 2 — five labels in `repair/`, and the rule that makes them mean something

`A2` and `A6` were both written before §14 reassigned the `FR-1xx` band, so each carries bold title
rows for local numbers that no live requirement defines. Label-only, nothing else touched — these
are signed historical records:

| record | local | canonical | authority |
|---|---|---|---|
| `repair/A2-identity-subsystem.md` | `FR-101` | `FR-174` | §14 rule 2 + title match in `spec.md:507` |
| `repair/A2-identity-subsystem.md` | `FR-102` | `FR-175` | §14 rule 2 + `spec.md:535` |
| `repair/A2-identity-subsystem.md` | `FR-104` | **`FR-176`** | §14 rule 2 + `spec.md:569` |
| `repair/A2-identity-subsystem.md` | `FR-105` | `FR-177` | §14 rule 2 + `spec.md:598` |
| `repair/A2-identity-subsystem.md` | `FR-106` | `FR-178` | §14 rule 2 + `spec.md:630` |
| `repair/A6-fr-triage.md` | `FR-101` | `FR-179` | §14 rule 2 + `spec.md:1108` |
| `repair/A6-fr-triage.md` | `FR-102` | `FR-180` | §14 rule 2 + `spec.md:1485` |

Shape: `**FR-104** (superseded local numbering → ARBITRATION §14 → **FR-176**) — <title>`. The
requirement bodies, the test methods and the "Independently testable because" lines are unchanged.

**`FR-104` maps to `FR-176`, not `FR-174`.** The brief's worked example said `**FR-174**`; §14 rule
2 gives the band as a whole ("A2's `FR-101/102/104/105/106` **become** `FR-174…FR-178`"), so the
positional reading of the example contradicts the band, and the titles settle it independently:
A2's `FR-104` is "Canonical participant ordering is a specified deterministic algorithm" and
`spec.md:569`'s `FR-176` carries that exact title. Writing `FR-174` would have pointed a reader at
the `PredicateSignature` field-set requirement instead. Corrected rather than copied.

**The label is a rule, not a regex accident.** `REPAIR_FR_SUPERSEDED_RE` recognises the form and
`parse_repair_definitions` explicitly skips it, so the exemption does not depend on the
parenthesised gloss happening to fail the dash-gloss test. Three new FAIL arms check the label is
*true*, because otherwise `**FR-nnn** (superseded … → **FR-mmm**)` would be a way to retire any
number without saying where the content went — a checker that certified that would be worse than
useless:

* `supersession-pointer-unresolved` — the canonical number is not a live requirement.
* `supersession-of-a-live-fr` — the local number *is* live; a record cannot supersede a number in
  force.
* `supersession-disagreement` — one document points one local number at two canonical numbers.
  **Scoped per document on purpose**: §1 records that "`FR-101`/`FR-102` as invented by **both** A2
  and A6 are void", so cross-document reuse is the normal shape here and a global reading would
  report the very collision §14 exists to resolve. The reuse is surfaced in the INFO summary's
  `reused_local_numbers` instead of being reported as a defect.

### 11.3 FIX 3 — `R070`: a non-goal does not carry a normative requirement

`checklists/requirements.md` row `R070` cited no FR, `FR-070` is tombstoned, and no live requirement
states the RDF/SHACL non-goal. No FR was minted — §14 rule 1 forbids it, and a non-goal is a
prohibition that constructs no acceptance criterion, so there is nothing for a requirement row to be
*about*.

* `spec.md`'s existing constitutional non-goals bullet (§80, §81) is **completed**: it now carries
  the two §81 sentences the old text omitted ("the extraction substrate is never moved into SHACL",
  "shape validation is not the semantic substrate") and names itself as the constitutional home of
  the tombstoned `FR-070`.
* The `R070` table row is **replaced by a pointer** below the table, naming that bullet, `T193` and
  the `repair/A6-fr-triage.md` design note. It is deliberately not a row: a row in that table
  asserts that one `FR-` requirement is what makes the item true, and none does.
* The section 2.15 preamble and the row-count self-measurement were corrected with the numbers the
  parser actually reports: **230** rows, of which **152** in sub-section 2 (was 231 / 153).
* `RI-04c-ROW-FR` is **untouched**; its teeth are re-pinned by
  `test_a_checklist_row_citing_no_fr_is_still_a_failure`, which withdraws a row's FR cell and
  asserts both `row-without-fr` and `row-without-fr-total` still fire.

### 11.4 FIX 4 — `FR-039a` is no longer ungated, and the next omission is caught

§10.5 item 1 recorded `FR-039a` as visible (`GHOST-SUFFIX` WARNs 17 live citations) but ungated:
`spec.md`'s record table lists **six** retirements, `TOMBSTONED_FRS` had **five**. The table is
deliberately not in requirement-definition form, so the definition parser cannot read it, and
`RI-01-FR-DEF` *drops* tombstoned ids from its cited-but-undefined population — so the id was
defined nowhere, exempt from the check that would have said so, and owned by no other.

* `ARBITRATION.md` §2's set is now six, matching `spec.md`, with the "six, not five" paragraph
  written out so the next reader knows the count is load-bearing.
* `TOMBSTONED_FRS` gains `"FR-039a": "FR-040"`.
* **New, and the actual root cause closed:** `spec_tombstone_record_ids()` reads the record
  *table* — found by its `tombstoned id` header column, not by searching prose — and
  `tombstone-record-unregistered` is FAIL for any id the table names and the map omits. So the
  `FR-039a` hole cannot recur silently, and the parser gap that allowed it is named in the rule
  text rather than left as a comment.

**Successor disagreement, reported and not resolved.** `spec.md:403` and `ARBITRATION.md` §1/§2 all
give `FR-039a`'s successor as the `FR-040` slot; `tasks.md:942` says "folded into `FR-112`".
`FR-112` is a live requirement about type resolution over a bounded neighbourhood, so the two
statements are not describing the same obligation and one is wrong. `tasks.md` is not a file this
pass owns and is untouched. The disagreement is recorded in `ARBITRATION.md` §2 with the reasoning,
naming the owner of `tasks.md` as the party who settles it. The successor string in
`TOMBSTONED_FRS` is `FR-040` because that is what both files this pass owns say.

### 11.5 What this pass gives up, named

1. **Document-order monotonicity no longer gates.** 6 FAIL findings on the real corpus, all of
   them `spec.md` placing a band in its subject section. The arm still fires, at INFO, with both
   endpoints and the rewind size. A document that genuinely garbles its own FR sequence is now a
   WARN-free INFO rather than a red gate.
2. **Adjacency between two requirements in one list no longer gates.** 9 FAIL findings on the real
   corpus, reporting 27 numbers that §14 declares reserved. `fr-gap-in-section` retains the
   observation at INFO.
3. **A reserved number is exempt from *nothing* that matters.** The exemption is absence only;
   citation is still FAIL under `RI-01-FR-DEF`, and the superseded-label exemption is conditional
   on the pointer resolving.
4. **A reservation that cannot be parsed now blocks the gate** where it previously could not
   exist. That is new FAIL surface, in exchange for the tool never guessing which numbers are
   reserved.

### 11.6 Files touched by this pass

* `repair/tools/reference_check.py` — `TOOL_VERSION` 1.4.0 -> 1.5.0. `check_fr_order` rewritten;
  `check_fr_definitions` gained the supersession-pointer pass; `check_tombstoned_fr_refs` gained
  the record-table cross-check. Added: `Reservation`, `parse_fr_reservation`, `_blockquote_runs`,
  `RESERVATION_BLOCK_MARKER_RE`, `RESERVATION_DECL_RE`, `RESERVED_RANGE_PIECE_RE`,
  `PROSE_RANGE_RE`, `_QUOTED_LINE_RE`, `_accounted_fr_numbers`, `_unaccounted_fr_numbers`,
  `_interval_breakdown`, `_fmt_fr_list`, `RepairSupersession`, `REPAIR_FR_SUPERSEDED_RE`,
  `parse_repair_supersessions`, `_check_supersession_pointers`, `spec_tombstone_record_ids`,
  `TOMBSTONE_TABLE_HEADER_RE`, `TOMBSTONE_CELL_RE`, `_check_tombstone_records_registered`,
  `_info`, and `Context.reservation`. Three `CheckSpec.rule`/`title` strings rewritten
  (`RI-06b-FR-ORDER`, `RI-01-FR-DEF`, `TOMBSTONED-FR-REF`). `fr-gap-in-section`,
  `reservation-declared`, `no-reservation-declared`, `reservation-declaration-unreadable`,
  `supersession-summary`, `supersession-pointer-unresolved`, `supersession-of-a-live-fr`,
  `supersession-disagreement`, `tombstone-record-unregistered` and
  `tombstone-record-cross-check` are new finding codes. `fr-gap` keeps its code and its severity
  and changes its meaning; `fr-gap-document-order` and `fr-non-monotonic-document-order` keep
  their codes and change severity.
* `repair/tools/test_reference_check.py` — 247 collected / 221 passed / 0 failed / 26 skipped,
  from 226 / 200 / 0 / 26. **21 new test functions**, 7 pre-existing tests re-pointed at the new
  behaviour (each naming in its docstring the behaviour it used to pin, and the
  `test_a_number_defined_in_another_section_is_not_a_gap` / `test_rewind_and_dangling_arms…`
  docstrings stating the given-up power as an assertion). The four properties FIX 1 requires —
  sparse-but-declared, undeclared, reserved-but-cited, document-order-rewind — are pinned by
  `test_a_sparse_sequence_that_is_declared_reserved_has_zero_failures`,
  `test_an_undeclared_sparse_sequence_still_fails`,
  `test_a_reserved_number_that_is_cited_still_fails_the_definition_check` and
  `test_a_document_order_rewind_is_info_not_fail`.
* `spec.md` — the reserved-number-space block gains the third range and the `RESERVED-FR:`
  declaration; the `FR-070` constitutional non-goal is completed. No requirement row added,
  removed, renumbered or reworded.
* `checklists/requirements.md` — the `R070` row becomes a pointer; two self-counts corrected.
* `repair/ARBITRATION.md` — §2's tombstone set goes to six, plus the two explanatory paragraphs.
* `repair/A2-identity-subsystem.md`, `repair/A6-fr-triage.md` — five label edits, nothing else.
* `repair/A7b-reference-integrity-checker.md` — this section, appended.

No check id was added, removed or reordered; all 30 are present in the summary of every run, and
the anti-always-red control (`test_three_fixes_together_stay_green_on_a_self_consistent_directory`:
0 FAIL, exit 0, all 30 ids present) is green. No `apps/` code, no `tasks.md`, no `data-model.md`,
no `plan.md`, no `input.md`.