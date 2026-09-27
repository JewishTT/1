# A8prep — Ownership Map + Rebuilt Phase DAG

**Feature**: `021-entity-relation-extraction-finalization`
**Job**: A8prep (conflict prevention). **Scope**: *where* changes land and *in what order*.
**Out of scope**: requirement content. Seven sibling agents own content; this document owns
placement, numbering, order and gates.
**Authority order**: `input.md` (the brief) → `spec.md` → `plan.md` / `data-model.md` /
`tasks.md` / `checklists/requirements.md`. Where this document and the brief differ, the brief
wins and the difference is reported, not silently resolved.

---

## 0. Measured file state (read 2026-09-27, repo root `C:\Users\tim\Desktop\COGNITIVE\1`)

Line numbers in this document are **1-indexed total lines, blank lines included**, exactly as
produced by reading the file. Where a tool reports a different number it is counting non-blank
lines; both are given so an integrator can tell which convention a patch was generated against.

| File | Total lines | Non-blank | Blank | Stated in the task brief | Verdict |
|---|---|---|---|---|---|
| `spec.md` | **936** | 806 | 130 | ~913 | **mismatch** |
| `data-model.md` | **303** | 239 | 64 | ~285 | **mismatch** |
| `plan.md` | **236** | 198 | 38 | ~245 | **mismatch** |
| `tasks.md` | **281** | 204 | 77 | ~282 | **mismatch (off by one)** |
| `checklists/requirements.md` | **158** | 130 | 28 | ~158 | match |
| `input.md` (reference) | **4898** | 3411 | 1487 | "3411 lines" at `spec.md:16`, `plan.md:99` | **count defect** — see HS-7 |

**Consequence**: any repair patch authored against the brief's stated lengths is off by up to
23 lines and will apply to the wrong range. A7b's checker MUST validate every patch hunk header
against this table before applying it.

### Agents and their deliverables

| Id | Band name | Owns (content) | Writes |
|---|---|---|---|
| A1 | constitution | Constitution check table, supersession rule, `InvestigationWorkflow` contract, dead-code dispositions, ADR A–K, FR-101…FR-129 | `repair/A1-constitution-investigation.md` |
| A2 | identity | `PredicateSignature` v2, `RoleBinding` v2, `normalize_voice()`, `canonical_participant_ordering()`, corrected identity rule, SC-001 proof, N5 removal from identity | `repair/A2-identity-subsystem.md` |
| A4b | mapping | `PredicateMappingCandidate`, `AMBIGUOUS`/`CONFLICTING` as one hypothesis, `TypeSignal`/`TypeMapping`, `OntologyPack` disposition | `repair/A4b-mapping-layer.md` |
| A5 | types | §8 type vocabulary, `TypeHypothesis` one-hypothesis correction, `TypeSignal` producers, 9 missing SCs | `repair/A5-type-vocabulary.md` |
| A6 | triage | FR triage of the 52 orphans, renumbering plan, traceability matrix, count-claim fixes | `repair/A6-fr-triage.md` |
| A7 | migration | migration `021` incl. dropping the obsolete CHECK constraints | `repair/A7-migration-021.md` |
| A7b | checker | the machine reference-integrity checker | `repair/A7b-reference-integrity-checker.md` |
| A8prep | **placement** | this document: O1 ownership, O2 FR allocation, O3 DAG, O4 model diagram, O5 integration, O6 gates | this file |
| A8 | audit | runs O6 last | — |

---

# O1 — Line-range ownership map

**Rule O1.0 (single-owner partition).** Every current line of every file below appears in exactly
one row. Exactly one owner is named per row, or the row is `UNCHANGED`. No range appears twice.
An agent that needs a line it does not own files a *conflict note* (O2 Rule 2); it does not edit.

**Rule O1.1 (bottom-up application).** Within a file, apply owners' patches in the order
A1 → A2 → A4b → A5 → A7 → A6 → A7b, and **within one owner's patch, apply hunks bottom-up**
(descending start line). Bottom-up makes every preceding hunk's line numbers still valid, so the
table below remains authoritative throughout the whole application. This is what makes the
integration in O5 mechanical.

**Rule O1.2 (append-only zones).** Ranges marked `APPEND@<line>` are the *only* places an agent
may add lines. Nothing in an append zone may be edited or reordered, and append zones are
single-writer unless the row says otherwise.

**Rule O1.3 (new files).** `tasks.md` is owned in its entirety by A8prep (this document) — see
O1.4. This removes a whole class of collisions.

## O1.1 `spec.md` (936 lines)

| Lines | Content (verified at these lines) | Owner | Note |
|---|---|---|---|
| 1–14 | Title, branch, `Created`, `Status: Draft`, `Base`, `Predecessor`, `Input` digest | **A1** | A1 stamps revision id + status |
| 15–31 | Brief-digest blockquote: "3411 lines, all 115 sections", the five-questions paragraph, §101/§109/FR-075/FR-076/SC-001…SC-003 pointers | **A1** | **HS-7**: the `3411` here is input.md's *non-blank* count; real total is 4898 |
| 32–41 | `---`, `## Context`, 019 summary, "Its known defects" | UNCHANGED | |
| 42–55 | Defect table, 11 brief-derived rows (incl. line 49 `SignalKind`, line 47 CHECK constraints) | UNCHANGED | **HS-2**: admissible single-line edits by A5 (line 49 only) and A7 (line 47 only) |
| 56–79 | Defect table, 24 code-audit rows (incl. 63/64/65 persistence, 76/77 verifier + claim id) | UNCHANGED | **HS-8**: admissible single-line edits by A7 (63, 64, 65) and A1 (76, 77) |
| 80–87 | "Two of these are **not** defects and must not be 'fixed'" — `producer_ref` stays; the name `RelationSignal` is right | **A1** | dead-code disposition |
| 88–91 | separators + `## User Scenarios & Testing` | UNCHANGED | |
| 92–123 | **US1** — unknown relation survives (independent test asserts one `logical_candidate_id`, two `candidate_id`s) | **A2** | |
| 124–148 | **US2** — active/passive are one relation | **A2** | SC-001 lives here |
| 149–177 | **US3** — a producer cannot invent a mention | UNCHANGED | no repair agent owns mention binding (O2 `RESERVED-P3`) |
| 178–204 | **US4** — "Apple" is three things (`TypeHypothesis` competing) | **A5** | |
| 205–228 | **US5** — three producers, one hypothesis, no dedup | **A2** | producer-identity clause is identity, not mapping |
| 229–249 | **US6** — a denial is evidence | **A4b** | polarity → mapping-state reading |
| 250–271 | **US7** — an n-ary event keeps its shape | **A4b** | |
| 272–299 | **US8** — store, read back, replay | **A7** | |
| 300–327 | **US9** — the graph shows the world, not the extraction | **A1** | |
| 328–351 | Edge Cases (10 bullets) | UNCHANGED | line 340–341 `AMBIGUOUS`/`CONFLICTING` is A4b's subject but no edit is needed |
| 352–356 | `## Requirements`, `### Functional Requirements` | **A6** | |
| 357–373 | `#### Constitutional invariants` — INV-001…INV-005 | **A1** | |
| 374–399 | `### Identity` — FR-001…FR-007 | **A2** | **HS-3**: FR-003/FR-004 |
| 400–430 | `### Relation signal` — FR-008…FR-015 | **A2** | **HS-3**: FR-013/FR-014 co-claimed by A4b |
| 431–445 | `### Mention binding` — FR-016…FR-020 | UNCHANGED | `RESERVED-P3` |
| 446–463 | `### Predicate and claim boundary` — FR-021…FR-024 | **A4b** | |
| 464–481 | `### Assembly` — FR-025…FR-028 | **A4b** | **HS-1**: FR-028 |
| 482–542 | `### Types` — FR-029…FR-039a | **A5** | |
| 543–598 | `### Producers` — FR-040…FR-054 | **A4b** | producer↔mapping boundary |
| 599–611 | `### Lifecycle` — FR-055…FR-058 | **A1** | |
| 612–632 | `### Persistence` — FR-059…FR-062 | **A7** | |
| 633–660 | `### Projection` — FR-063…FR-070 | **A1** | |
| 661–680 | `### Boundedness and determinism` — FR-071…FR-074 | **A1** | |
| 681–712 | `### Verification` — FR-075…FR-081 | **A6** | **HS-5**: line 699 FR-079 says "Four named mutations" and then lists **six** |
| 713–716 | `### Verified 019 defects` intro | **A6** | |
| 717–723 | FR-085 (`signal_refs` canonicalisation), FR-086 (`to_dict`/`from_dict`) | **A2** | |
| 724–730 | FR-087, FR-088 (persistence columns) | **A7** | |
| 731–735 | FR-089 (signal `_material`) | **A2** | |
| 736–741 | FR-090 (no majority vote) | **A4b** | |
| 742–744 | FR-091 (one signal→candidate path) | **A4b** | |
| 745–750 | FR-092 (lifecycle split) | **A1** | |
| 751–755 | FR-093 (`pairs_considered` real) | **A6** | last-resort owner, O2 Rule 5 |
| 756–760 | FR-094 (no fabricated participant) | **A6** | last-resort owner |
| 761–764 | FR-095 (no silent structural data loss) | **A6** | last-resort owner |
| 765–769 | FR-096 (temporal path reachable) | **A7** | |
| 770–772 | FR-097 (migration 021) | **A7** | |
| 773–777 | FR-098 (partition verifier) | **A2** | |
| 778–780 | FR-099 (claim self-verify) | **A2** | |
| 781–789 | FR-100 (production wiring) | **A1** | |
| 790–795 | `### Production reachability, as measured` intro | **A1** | |
| 796–812 | reachability table, 13 rows (809 `InvestigationWorkflow`, 810 CI) | **A1** | A1 re-measures all rows at revision HEAD |
| 813 | blank | UNCHANGED | |
| 814–818 | **FR-082** (stop conditions) — *out of numeric order, sits after FR-100* | **A1** | **G2.4 violation** today; A6 relocates, A1 owns text |
| 819–821 | `### Specification deliverables` heading | **A1** | |
| 822–836 | FR-083 (ship the directory + ADR A–K), FR-084 (completion report vocabulary) | **A1** | |
| 837 | `### Key Entities` heading | **A6** | |
| 838–839 | blank | UNCHANGED | |
| 840–841 | `RelationParticipant` | **A2** | |
| 842–844 | `PredicateSignature` | **A2** | |
| 845–846 | `PredicateHypothesis` | **A4b** | |
| 847–848 | `TypeHypothesis` | **A5** | |
| 849–850 | `TypeSignal` | **A5** | **HS-4**: absent from `data-model.md` |
| 851–852 | `TypeMapping` | **A4b** | **HS-4**: absent from `data-model.md` |
| 853 | `CoreTypePack` | **A5** | name mismatch with `data-model.md:299` `TypeVocabulary` |
| 854–855 | `RelationSignal` | **A2** | |
| 856–857 | `RelationCandidate` | **A2** | |
| 858 | `RelationEvidenceView` | **A1** | projection band |
| 859–860 | `MentionOccurrenceIndex` | UNCHANGED | **HS-9**: `data-model.md:215` says `MentionIndex` |
| 861 | blank | UNCHANGED | |
| 862–867 | `## Success Criteria`, `### Measurable Outcomes` | **A6** | |
| 868–903 | SC-001…SC-016 (16 entries) | **A6** | **HS-6**: A5 adds SCs — see merge rule |
| **APPEND@903** | *(before `### Constitutional non-goals` at 905)* — A5 appends its 9 missing SCs here | **A5** | **HS-6** |
| 904–916 | `### Constitutional non-goals` (4 bullets) | **A1** | |
| 917–931 | `## Assumptions` — 019-at-HEAD, `core:*` ownership, operator registry, parser, migration numbering | UNCHANGED | |
| 932–936 | Assumptions: migration numbering, PostgreSQL-unreachable reporting | **A7** | |

**Admissible single-line carve-outs inside `UNCHANGED` ranges** (each is a named line, not a band;
no other line of that range may be touched):

| Line | Text (abridged) | Sole admissible editor |
|---|---|---|
| 47 | `relation_surface != '' OR relation_ref IS NOT NULL` … migration 020 CHECKs | **A7** (records the DROP) |
| 49 | the 13-member `SignalKind` row | **A5** (type/signal vocabulary row) |
| 63 | `relation_candidate` has no `signal_refs`/`direction`/`confidence` | **A7** |
| 64 | `RelationClaim.candidate_id` has no column | **A7** |
| 65 | `alternative_refs` / `mapping_evidence_refs` have no column | **A7** |
| 76 | `verify_candidate_material_partition()` exported, never called | **A2** |
| 77 | `RelationClaim` does not self-verify | **A2** |
| 809 | `workflows/investigation.py` unregistered | **A1** |
| 810 | CI `.github/` does not exist | **A1** |

## O1.2 `data-model.md` (303 lines)

| Lines | Content | Owner | Note |
|---|---|---|---|
| 1–13 | header, provenance, **"The seven levels are never collapsed (I-2)"** + the 9-node chain (10–11) | **A1** | **HS-10**: says *seven*, lists *nine*; INV-001 lists *eight*; the approved diagram has *twelve* |
| 14 | `---` | UNCHANGED | |
| 15–63 | `## 1. PredicateSignature` — field list (21–31), "what it does NOT carry" table (33–41), N1–N6 (44–51), the N5 paragraph (53–57), the unknown example (59–62) | **A2** | **HS-11**: A4b also wants line 38 (`relation_ref` is "a later, versioned step") |
| **APPEND@62** | A4b appends `### 1.1 Mapping interface` — a *new* subsection; must not edit 33–41 | **A4b** | **HS-11** |
| 64–65 | `---` | UNCHANGED | |
| 66–119 | `## 2. RelationSignal` — `RelationParticipant` (72–77), `RelationSignal` (79–89), `SignalKind` split table (91–108), `_material` change (109–118) | **A2** | |
| 120–165 | `## 3. RelationCandidate` — field list (123–134), identity rule (136–145), the two consequences (147–153), `signal_refs` (155–158), `to_dict`/`from_dict` (160–163) | **A2** | **HS-12**: lines 128–129 are the *mapping* half (`relation_ref`, `predicate_hypothesis`) — A4b owns 128–129 only |
| **APPEND@163** | A4b appends `### 3.1 Predicate mapping candidates` | **A4b** | |
| 166–185 | `## 4. PredicateHypothesis` — the 4-state paragraph (168–170), field table (172–179), "signature is not stored here" (181–184) | **A4b** | |
| 186–190 | persistence change for `alternative_refs` / `mapping_evidence_refs` | **A7** | |
| 191–192 | `---` | UNCHANGED | |
| 193–211 | `## 5. Polarity, DirectionHypothesis, Arity` — `Polarity` (195–200), direction (202–206), arity (208–209) | **A2** | |
| 212–213 | `---`, `## 6.` heading | **A6** | section renumbering if A5 inserts a section |
| 214 | `## 6. Mention index and type layer` heading | **A5** | |
| 215–221 | `MentionIndex` (NEW) — the pre-resolution binding seam | UNCHANGED | **HS-9**: rename to `MentionOccurrenceIndex` is an A5 edit of line 215 only |
| 222–243 | `TypedMention` / `TypeHypothesis` (222–235), bounded vocabulary (237–243) | **A5** | **HS-4**: A5 appends `TypeSignal` + `TypeMapping` here; A4b appends `TypeMapping` only |
| **APPEND@242** | A5 appends the `TypeSignal` rows — **applied first** | **A5** | |
| **APPEND@242** | A4b appends the `TypeMapping` rows — **applied second** | **A4b** | |
| 244–245 | `---` | UNCHANGED | |
| 246–268 | `## 7. Persistence mapping (migration 021)` — the column table (251–256), parity (258), the three unwritten tables (260–266) | **A7** | |
| 269–286 | `## 8. Graph projection` — bridge shape (272–276), the two gaps (278–283) | **A1** | |
| 287–290 | `## 9. Entity summary` heading + table header | **A1** | A1 owns the final ordering/format pass |
| 291–303 | 13 entity rows, banded below (O1.2a) | see O1.2a | **HS-13** |
| **APPEND@303** | single append anchor for all new entity rows, appended in the fixed order A2 → A4b → A5 → A7 | *by the owning agent, at its own anchor* | **HS-13** |

### O1.2a `data-model.md` §9 entity-summary row ownership (lines 291–303)

| Line | Entity | Owner |
|---|---|---|
| 291 | `PredicateSignature` | **A2** |
| 292 | `Polarity` | **A2** |
| 293 | `RelationParticipant` | **A2** |
| 294 | `RelationSignal` | **A2** |
| 295 | `PredicateHypothesis` | **A4b** |
| 296 | `RelationCandidate` | **A2** |
| 297 | `TypeHypothesis` | **A5** |
| 298 | `MentionIndex` | UNCHANGED (rename by A5 per HS-9) |
| 299 | `TypeVocabulary` (`core:*`/`value:*`) | **A5** |
| 300 | `RelationClaimMaterial` | UNCHANGED |
| 301 | `RelationClaim` | **A2** |
| 302 | `GraphEdge`/`HyperEdge` | **A1** |
| 303 | `SourceTemporalObservation` | **A7** |

**Reserved append rows (in this order, one owner each):**

| Order | New row | Owner | Reserved for |
|---|---|---|---|
| 1 | `RoleBinding` | A2 | `RoleBinding` v2 |
| 2 | `PredicateMappingCandidate` | A4b | the mapping hypothesis |
| 3 | `TypeSignal` | A5 | |
| 4 | `TypeMapping` | A4b | |
| 5 | `MentionOccurrenceIndex` | A5 | the HS-9 rename |
| 6 | `ValidationReport` | A1 | **status `NEEDS-SPEC`** until Phase 6 |
| 7 | `AdmissionDecision` | A1 | **status `NEEDS-SPEC`** until Phase 6 |
| 8 | `EntityResolution` / `SemanticRegime` gate | A1 | DM-5 annotation |
| 9 | `WorldLine` | A1 | DM-10 omission |
| 10 | `RelationEvidenceView` | A1 | DM-6 / projection band |

**HS-13 merge rule (deterministic, binding).** The table body is *row-addressed, not
range-addressed*: each agent may modify exactly the rows it owns and may append only at
`APPEND@303`, in the reserved order above. The integrator MUST reject any patch that reorders,
reformats, re-wraps, or re-pads an existing row, and MUST reject any row edit outside the
owning agent's line. Rationale: a 13-row markdown table is the single most contended region of
the revision, and prose reflow is how two agents end up owning the same line.

## O1.3 `plan.md` (236 lines)

| Lines | Content | Owner | Note |
|---|---|---|---|
| 1–5 | header, Input pointer | **A1** | |
| 6–8 | "102 functional requirements, 5 constitutional invariants, 16 measurable outcomes, 9 user stories" | **A6** | count-claim owner |
| 9 | brief-governs sentence | UNCHANGED | |
| 10–14 | `## Summary` — the "turn raw surface into a substrate" framing | **A1** | |
| 15–21 | technical approach: `PredicateSignature` as identity carrier, n-ary `RelationSignal`, mention index | **A2** | |
| 22–24 | the type layer: bounded `core:*`/`value:*` vocabulary + multi-hypothesis `TypeHypothesis` | **A5** | **HS-15** |
| 25–28 | persistence columns via migration `021`; lifecycle wired into the live path | **A2** | identity carrier is the subject; A7 may file a note on the `021` clause only |
| 29–32 | non-goal + `## Technical Context` | **A1** | |
| 33–70 | language, deps, storage, testing, platform, performance, constraints | UNCHANGED | |
| 71–73 | "020 created 3 tables … 9 user stories, 102 FRs, 16 SCs" | **A6** | count-claim owner |
| 74 | `## Constitution Check` heading | **A1** | |
| 75–92 | the constitution check table (79–87) + the post-design re-check note (89–91) | **A1** | |
| 93–111 | `## Project Structure` / `### Documentation` tree — **every artefact is marked "NOT yet created"** although all exist | **A1** | staleness fix + revision stamp |
| 112–117 | `### Source Code` tree head, `shared/domain/` | UNCHANGED | |
| 118–123 | per-file annotations: "26 fields", "4 states", "31 fields" | **A6** | stale field counts |
| 124–199 | rest of the source tree | UNCHANGED | |
| 200–218 | `## Complexity Tracking` — 2 justified items + 2 risks | **A1** | |
| 219–229 | `## Phase 0 research — status` | UNCHANGED | |
| 230–236 | `## Still owed before the §100 deliverables gate` | **A1** | A1 owns ADR A–K + `contracts/` |

## O1.4 `tasks.md` (281 lines) — **A8prep owns 100% of this file**

| Lines | Content | Owner |
|---|---|---|
| 1–14 | header, authority note (§110), format note | **A8prep** |
| 15–27 | `## Phase 0: Baseline` — T001–T004 | **A8prep** |
| 28–43 | `## Phase 1` — T005–T010 | **A8prep** |
| 44–59 | `## Phase 2` — T011–T016 | **A8prep** |
| 60–74 | `## Phase 3` — T017–T021 | **A8prep** |
| 75–90 | `## Phase 4` — T022–T027 | **A8prep** |
| 91–105 | `## Phase 5` — T028–T032 | **A8prep** |
| 106–121 | `## Phase 6` — T033–T038 | **A8prep** |
| 122–136 | `## Phase 7` — T039–T043 | **A8prep** |
| 137–153 | `## Phase 8` — T044–T050 | **A8prep** |
| 154–170 | `## Phase 9` — T051–T057 | **A8prep** |
| 171–185 | `## Phase 10` — T058–T062 | **A8prep** |
| 186–200 | `## Phase 11` — T063–T067 | **A8prep** |
| 201–216 | `## Phase 12` — T068–T074 | **A8prep** |
| 217–251 | `## Dependencies & execution order` (chain diagram 219–245, overlap note 247–250) | **A8prep** — **replaced by O3** |
| 252–259 | `## MVP` (`0 → 1 → 2 → 5`) | **A8prep** — **corrected by O3 D1** |
| 260–271 | `## Open questions blocking specific tasks` | **A8prep** — **corrected by O3 D11** |
| 272–281 | `## Notes` | **A8prep** |

**A8prep carve-out for A6**: A6 may not edit `tasks.md`. A6's renumbering changes FR *citations*
inside task text; A6 publishes an `FR old→new` table, and A8prep (or the integrator) applies the
citation substitution mechanically, so no two agents write the same line.

**A8prep carve-out for A7b**: A7b may add a `FILES:` line to each task (O3 D4) but may not
reword a task, move a task, or change a `[P]` marker. Those are A8prep's.

## O1.5 `checklists/requirements.md` (158 lines)

| Lines | Content | Owner |
|---|---|---|
| 1–13 | header, gate, verification key, hard rule (16 baseline failures) | **A6** |
| 14–26 | `## A. Constitutional invariants` — A1…A7 | **A1** |
| 27–40 | `## B. Identity and the signature` — B1…B9 | **A2** |
| 41–52 | `## C. RelationSignal structure` — C1…C7 | **A2** |
| 53–66 | `## D. Producers and mention binding` — D1…D9 | **A4b** |
| 67–78 | `## E. Assembly` — E1…E7 | **A4b** |
| 79–90 | `## F. Types` — F1…F7 | **A5** |
| 91–101 | `## G. Lifecycle` — G1…G6 | **A1** |
| 102–117 | `## H. Persistence` — H1…H11 | **A7** |
| 118–127 | `## I. Projection` — I1…I5 | **A1** |
| 128–146 | `## J. Corpus, mutations, regression, wiring` — J1…J14 | **A6** |
| **APPEND@116** | *(inside `## H`, after H11)* A7 appends the constraint-DROP items | **A7** |
| **APPEND@145** | *(inside `## J`, after J14)* A7b appends the reference-integrity items | **A7b** |
| 147–158 | `## Sign-off conditions` (5 conditions) | **A6** |

## O1.6 Contested hot spots — index

| Id | Location | Contending agents | Rule |
|---|---|---|---|
| HS-1 | `spec.md:374–399` FR-003/FR-004 vs `spec.md:464–481` FR-028 | A2, A4b | **O2 Rule 3** — lower band normative |
| HS-2 | `spec.md:42–55` defect rows 47, 49 | A7, A5 | line-scoped carve-out (O1.1) |
| HS-3 | `spec.md:400–430` FR-013/FR-014 | A2, A4b | A2 owns 400–430; A4b may only add a cross-reference sentence at `APPEND@430` |
| HS-4 | `spec.md:847–853` Key Entities vs `data-model.md:222–243` §6 and §9 | A5, A4b | row-addressed (§9 rule) + append-anchor order A5→A4b |
| HS-5 | `spec.md:699–703` FR-079 "Four named mutations" then lists six | A6 | A6 owns; A2/A4b file notes |
| HS-6 | `spec.md:868–903` SC list (A6) vs A5's 9 new SCs | A6, A5 | `APPEND@903`, single anchor, A6 re-indexes afterwards in its own band |
| HS-7 | `spec.md:16`, `plan.md:99` "input.md 3411 lines" | A6 | A6 owns both lines |
| HS-8 | `spec.md:56–79` rows 63/64/65/76/77 | A7, A2 | line-scoped carve-out |
| HS-9 | `data-model.md:215` `MentionIndex` vs `spec.md:438`/`spec.md:859` `MentionOccurrenceIndex` vs diagram `MentionBinding` | A5 | canonical name `MentionOccurrenceIndex`; A5 edits 215 + 298 and appends the renamed row |
| HS-10 | `data-model.md:9` "seven levels" vs `data-model.md:10–11` (9 nodes) vs `spec.md:359` INV-001 (8 types) vs diagram (12 nodes) | A1, A6 | A1 owns 1–13 and INV-001; A6 owns the count-claim side; one count, restated without a number where possible |
| HS-11 | `data-model.md:15–63` §1 (A2 field list vs A4b's mapping paragraph) | A2, A4b | **A2 owns the field list and the "does NOT carry" table 33–41; A4b owns only a new `### 1.1` at `APPEND@62`; the integrator must not let either rewrite the other's text** |
| HS-12 | `data-model.md:123–134` §3 field list (signature half vs mapping half) | A2, A4b | A2 owns 123–127 + 132–134; A4b owns 128–129 only |
| HS-13 | `data-model.md:287–303` §9 entity summary | all five | row-addressed partition (O1.2a) + ordered append anchor |
| HS-14 | `checklists/requirements.md:1–13` (A6 renumber) vs `:102–117` (A7 DROP items) | A6, A7 | A6 owns 1–13; A7 appends at `APPEND@116` inside its own section; no range is shared |
| HS-15 | `plan.md:15–28` (A2's approach) vs `plan.md:22–24` (A5's type layer) | A2, A5 | line-scoped split at 22–24 |
| HS-16 | `plan.md:6–8` / `:71–73` / `:118–123` count claims vs the real counts | A6 | A6 owns all three |

## O1.7 The four named hot spots, resolved explicitly

**(a) `data-model.md` §1 — `PredicateSignature`.** A2 rewrites the signature (adds `RoleBinding`
v2, `normalize_voice()`, `canonical_participant_ordering()`, drops N5 from the identity path).
A4b removes N5 from the identity path *and* owns `PredicateMappingCandidate`.
*Merge rule:* A2 owns `data-model.md:15–63` in full, including the N5 row (line 50) and the N5
paragraph (lines 53–57) — A2's brief assigns it there. A4b owns **only** a new
`### 1.1 Mapping interface` subsection at `APPEND@62`, which MUST restate rather than restyle: it
may name `relation_ref` and `PredicateMappingCandidate`, and it MUST NOT alter the field list
(21–31) or the "does NOT carry" table (33–41). The integrator MUST reject any A4b hunk whose
context lines touch 21–41.

**(b) `spec.md` FR-003/FR-004 (A2) vs FR-021/FR-028 (A4b).** A2 owns 374–399; A4b owns 446–481.
*Merge rule:* FR-002 (`spec.md:381`, A2) is the **normative identity-term list**. FR-028
(`spec.md:478`, A4b) describes mapping-state conflict. They are different questions, so there is
no content collision — but there is an *apparent* one: FR-002 puts `polarity` and the signature
in identity, while FR-028's `AMBIGUOUS` looks like an identity term. A4b MUST add one clause to
FR-028 stating that `AMBIGUOUS`/`CONFLICTING` are **mapping states on `PredicateHypothesis`, not
identity terms on `PredicateSignature`**, and cite FR-002. A2 MUST NOT edit FR-028. Direction of
conformity is one-way: **lower band normative** (O2 Rule 3).

**(c) `data-model.md` §6 (A5) vs §9 entity summary (all agents).** *Merge rule:* §6 is a
**narrative section** owned by A5 (222–243) with two ordered append anchors (`TypeSignal` by A5
first, `TypeMapping` by A4b second). §9 is a **row table** governed by the row-addressed
partition in O1.2a plus the ordered `APPEND@303`. An entity MUST have exactly one §6 narrative
home (its own agent) and exactly one §9 row (same agent), and the two MUST agree on `Status` and
`Identity key`. A7b asserts the join: for every `## n.` section of `data-model.md` and every §9
row, the entity name appears in both, or is explicitly marked `narrative-only` / `table-only`.

**(d) `checklists/requirements.md` (A6 renumbers, A7 adds constraint-DROP items).** *Merge rule:*
A6 owns 1–13 only; it does **not** renumber rows. A7's DROP items append at `APPEND@116` inside
`## H` (A7's own section). Therefore no line is ever shared, and the "renumber" never touches the
rows A7 is appending to. A6's renumbering affects the FR citations; the checklist currently cites
an FR exactly **once** (line 11, `FR-081`), so the collision surface is one line. A7b asserts:
every row's `Task` cell matches `^T\d{3}(, T\d{3})*$` against `tasks.md` — which today fails with
**9** violations (O3 D5).

---

# O2 — FR-number allocation map

## O2.1 The measured starting point

| Fact | Value | Where measured |
|---|---|---|
| FR definitions in `spec.md` | **102** | `grep -c '^- \*\*FR-' spec.md` |
| Numeric FR ids | **100** — `FR-001`…`FR-100`, **no gaps** | min 1, max 100, 0 missing |
| Sub-numbered ids | **2** — `FR-034a` (line 514), `FR-039a` (line 538) | |
| `FR-101` exists? | **no** — nothing is numbered 101 or above | |
| `FR-082` placement | line **814**, i.e. **after** `FR-100` at line 781 — out of numeric order | |
| INV definitions | 5 (lines 359, 363, 367, 369, 371) | |
| SC definitions | 16 (lines 868…903, contiguous) | |
| FRs referenced by ≥1 *other* document | **51 of 102** | |
| **Orphan FRs** (defined in `spec.md`, referenced by no other of `tasks.md` / `plan.md` / `data-model.md` / `checklists/requirements.md` / `research.md`) | **52** | list below |
| `tasks.md` task definitions | 74, `T001`…`T074`, **no gaps** | |
| **Phantom task ids** (referenced, never defined) | **9** across 6 base tasks | O3 D5 |

The 52 orphans (exactly 52, confirming A6's brief):
`FR-001, 002, 003, 004, 009, 010, 018, 019, 023, 024, 028, 035, 036, 037, 038, 039, 039a, 040,
041, 042, 043, 044, 045, 046, 048, 049, 050, 051, 052, 053, 054, 055, 056, 061, 062, 063, 064,
065, 066, 067, 068, 069, 071, 072, 073, 074, 075, 076, 077, 078, 080, 083`

## O2.2 The key finding: **FR-001…FR-100 needs no renumbering**

All 100 numeric ids are present and gap-free. Therefore A6's "renumbering plan" is **not** a
renumbering. It is:

1. **Fold** `FR-034a` → into `FR-035` as a sentence (or keep as a permanent sub-label, in which
   case G2.2's uniqueness rule must permit `[a-z]` suffixes — recommended, because a sub-label
   that has to be folded loses its stable citation at `spec.md:514`).
2. **Fold** `FR-039a` → into `FR-040` on the same terms.
3. **Relocate** `FR-082` (line 814) to sit after `FR-081` — a *move*, not a renumber.
4. **Append** `FR-101`…`FR-129` (A1's band).

Net effect: **51 of 102 FR numbers never change.** A6 publishes a 51-entry no-op table, a
2-entry fold table and a 1-entry move table. This is what makes parallel FR work safe: no agent
can collide on a number, because no number moves.

## O2.3 The allocation map (binding)

Target space: **`FR-001`…`FR-129`**. Every range is disjoint. Two bands per agent is permitted;
**overlap is not**.

| Range | Slots | Owner | Subject | Current ids here |
|---|---|---|---|---|
| `FR-001`–`FR-007` | 7 | **A2** | Identity: logical id, `PredicateSignature`, normalisation, signal id, two-level partition | 001–007 |
| `FR-008`–`FR-015` | 8 | **A2** | Relation signal: participants, participant fields, required dims, kinds, aspects, surface-optional, observational basis, polarity | 008–015 |
| `FR-085`–`FR-089` | 5 | **A2** | `signal_refs` canonicalisation, `to_dict`/`from_dict`, signal `_material`, partition verifier, claim self-verify | 085, 086, 089, 098, 099 |
| `FR-016`–`FR-020` | 5 | **RESERVED-P3** | Mention binding, `MentionOccurrenceIndex`, deferred participant refs, producer import ban | 016–020 |
| `FR-021`–`FR-028` | 8 | **A4b** | Predicate/claim boundary, assembly, `AMBIGUOUS`/`CONFLICTING` as one mapping hypothesis | 021–028 |
| `FR-029`–`FR-039a` | 11 | **A5** | Type pack, value types, `TypeHypothesis`, hierarchy, `TypeSignal`, `TypeMapping`, type pipeline, context, mutual hinting | 029–039a |
| `FR-040`–`FR-054` | 15 | **A4b** | Producer families, producer↔mapping boundary, `RELATION_CUES`, parser provenance, structural/link/reference/table/list/metadata/attribute/temporal/event/co-occurrence/semantic producers | 040–054 |
| `FR-090`–`FR-091` | 2 | **A4b** | No majority vote; one signal→candidate path | 090, 091 |
| `FR-055`–`FR-058` | 4 | **A1** | Lifecycle stage order, claim lifecycle, `material` as a real stage product, edge only after claim | 055–058 |
| `FR-059`–`FR-062` | 4 | **A7** | Store seams, exact reconstruction, normal acquisition path for temporal observations, migration rules | 059–062 |
| `FR-063`–`FR-070` | 8 | **A1** | Projection, hypothesis/evidence view, navigability, edge metadata, RDF sidecar | 063–070 |
| `FR-071`–`FR-074` | 4 | **A1** | Boundedness, producer counters, determinism, no hidden semantic gate | 071–074 |
| `FR-075`–`FR-081` | 7 | **A6** | Corpora, mutation harness, named mutations, performance, regression | 075–081 |
| `FR-082`–`FR-084` | 3 | **A1** | Stop conditions, §100 deliverables, completion-report vocabulary | 082–084 |
| `FR-092` | 1 | **A1** | Lifecycle split; `ValidationReport` retained and surfaced | 092 |
| `FR-093`–`FR-095` | 3 | **A6** | `pairs_considered` real, no fabricated participant, no silent structural data loss | 093–095 |
| `FR-096`–`FR-097` | 2 | **A7** | Temporal path reachable; migration `021` | 096, 097 |
| `FR-100` | 1 | **A1** | Production wiring of the semantic path | 100 |
| `FR-101`–`FR-109` | 9 | **A1** | **NEW** — constitution check table, supersession rule, `InvestigationWorkflow` contract, dead-code dispositions, ADR A–K, reachability re-measurement, completion criteria | new |
| `FR-110`–`FR-112` | 3 | **A5** | **NEW** — the 9 missing success criteria need normative parents (type-vocabulary completeness, value/entity separation, unmapped-type retention, revision-not-replacement, context consumption, mutual hinting) | new |
| `FR-113`–`FR-114` | 2 | **A7** | **NEW** — the obsolete CHECK constraints from `020` MUST be dropped by `021`; ORM/migration parity extended to the dropped constraints | new |
| `FR-115` | 1 | **A7b** | **NEW** — the reference-integrity checker MUST run as a gate and MUST exit non-zero on any G-assertion in O6 | new |
| `FR-116`–`FR-129` | 14 | **RESERVED-FUTURE** | **MUST remain unused** until the next feature | — |

**Slot arithmetic** (must balance; A7b asserts): `102 existing − 2 folded (FR-034a, FR-039a) = 100`
in `FR-001`–`FR-100`; `+ 9 (A1) + 3 (A5) + 2 (A7) + 1 (A7b) = 15` new in `FR-101`–`FR-115`;
`+ 14 reserved` in `FR-116`–`FR-129`; `100 + 15 + 14 = 129`.

**A1 allocates its own band once and publishes the sub-allocation above as binding.** A5, A7 and
A7b do not negotiate with A1 for numbers; they take the sub-ranges named here or file a conflict
note under O2 Rule 2.

## O2.4 The contested-FR rule set

**Rule 1 — band ownership.** The agent owning the band owns the FR's *normative text*. No other
agent edits it, ever, for any reason.

**Rule 2 — conflict notes, not edits.** Any agent may file a *conflict note* against an FR
outside its band, in its own `repair/A*.md`, in the form
`CONFLICT-NOTE: FR-0xx — <claim> — <proposed conforming text>`. Notes are resolved by the band
owner in the same integration pass, or escalated under Rule 6. A note is not a licence to edit.

**Rule 3 — lower band is normative (one-way conformity).** When two FRs in *different* bands
constrain the same field or the same identity term, the **lower-numbered** band's text is
normative and the higher-numbered band's text is amended **by its own owner** to conform. It is
never the other way round. Worked cases:

- `FR-002` (A2, 381) vs `FR-028` (A4b, 478) → **A2 normative**; A4b amends FR-028 to declare
  `AMBIGUOUS`/`CONFLICTING` as mapping states, not identity terms.
- `FR-003` (A2, 383) vs `FR-021` (A4b, 448) → **A2 normative** on the signature's field list; A4b
  amends FR-021 to cite `FR-003` rather than restate the fields.
- `FR-004` (A2, 387) vs `FR-021` (A4b, 448) → **A2 normative** on normalisation; `owns`/`controls`/
  `manages` stay distinct and A4b may not introduce an equivalence FR-004 forbids.
- `FR-011`/`FR-012` (A2, 414/418) vs `FR-015` (A2, 427) → same band, A2 decides internally.
- `FR-029`–`FR-031` (A5, 484–496) vs `FR-021` (A4b, 448) → different bands, different subjects
  (type space vs relation space). §104 forbids conflating them; no conformity needed, but A4b
  MUST cite `FR-034a` whenever a mapping touches the type pack, and A5 MUST NOT write a relation
  requirement.

**Rule 4 — one enumeration, one owner.** If two FRs in different bands both enumerate the *same*
field list, only the **lower-numbered** band carries the enumeration; the higher band cites it. No
arbitration needed. (Example: `PredicateSignature`'s fields are enumerated in `FR-003` (A2);
`data-model.md:21–31` and `FR-021` may cite, not copy.)

**Rule 5 — last-resort ownership.** An FR that no agent claims is owned by **A6**, who must
either assign it to a band or mark it `DEFERRED` with a reason. A6 never writes its *content*; it
routes. Today this applies to `FR-093`–`FR-095` (producer honesty), which A6 holds.

**Rule 6 — arbitration ladder.** For a *true* contradiction where neither band cites the other and
Rule 3 does not resolve it:

1. **Band owner** decides, if both FRs are in the same band.
2. **A6** decides, if the contradiction is about numbering, traceability, citation or placement.
   A6 records the decision in `repair/integration-decisions.md` citing the rule applied. A6 does
   not rewrite; it routes the instruction to the band owner.
3. **A8** decides, at final audit, for anything still open. A8 records it in the same file.
4. **The user** decides, and only the user, if resolving the contradiction would change what a
   requirement *means*. No agent and no auditor may do that.

**Rule 7 — no silent dual-keeping.** When two bands assert incompatible `MUST`s, keeping both
with a "see also" is **forbidden**. A normative contradiction is resolved to exactly one `MUST`.
The losing text moves to a `## Superseded` note naming the superseding FR, the deciding rule, and
the deciding agent. This is the supersession rule A1 publishes, and A7b asserts that every
`## Superseded` note names all three.

**Rule 8 — orphan closure is mandatory.** Every FR in `FR-001`–`FR-100` must be cited by at least
one of `tasks.md`, `checklists/requirements.md`, `data-model.md` at revision exit (**G2.5**).
52 fail today. Each band owner closes their own:

| Owner | Orphan ids to close |
|---|---|
| A2 | 001, 002, 003, 004, 009, 010, 019 |
| A4b | 023, 024, 028, 035, 036, 040, 041, 042, 043, 044, 045, 046, 048, 049, 050, 051, 052, 053, 054 |
| A5 | 037, 038, 039, 039a |
| A7 | 061, 062 |
| A1 | 055, 056, 063, 064, 065, 066, 067, 068, 069, 071, 072, 073, 074, 083 |
| A6 | 018, 075, 076, 077, 078, 080 |

`FR-018` is in the `RESERVED-P3` band but A6 carries the citation, because no implementation agent
owns mention binding.

---

# O3 — The rebuilt phase DAG

## O3.1 The mandated structure, and its mapping onto §110

`input.md` §110 (`input.md:4618–4664`) fixes **12** phases. The user mandates **10**. The brief
is authoritative, so the reconciliation is: **the 10-phase structure is a regrouping; no §110 phase
may be dropped.** The mapping table below is the proof, and A7b asserts it (G7.2).

| User phase | Absorbs §110 phase(s) | §110 text | Complete? |
|---|---|---|---|
| **0** Spec / Constitution / Traceability | *(none — new gate)* | — | new, additive |
| **1** Identity + PredicateSignature + RoleSignature | §110-1, §110-5 | "identity/domain contract cleanup" (4625–4626); "predicate signature + candidate identity correction" (4637–4638) | merged, 2 of 12 |
| **2** Type vocabulary + TypeHypothesis substrate | §110-2, §110-3 (first half) | "atomic entity type vocabulary" (4628–4629); "type hypothesis + mention binding" (4631–4632) | 2, splits 3 |
| **3** Mention binding / occurrence index | §110-3 (second half) | same | completes §110-3 |
| **4** Signal contract + producers | §110-4, §110-6 | "RelationSignal structural contract" (4634–4635); "producer corrections" (4640–4641) | 2 of 12 |
| **5** Candidate assembly | §110-7 | "assembly / conflict semantics" (4643–4644) | 1 |
| **6** Claim material / validation / admission | §110-8 (first half) | "real execution lifecycle" (4646–4647) | splits 8 |
| **7** InvestigationWorkflow production wiring | §110-8 (second half) + §101/§108/§114 | — | completes §110-8 |
| **8** Graph projection | §110-9 (substrate only), §110-10 | "durable persistence + replay" (4649–4650); "graph projection verification" (4652–4653) | 2, splits §110-9 |
| **9** Replay / determinism / golden corpus | §110-9 (proof half), §110-11, §110-12 | "golden corpus + mutation tests" (4655–4656); "benchmark + regression" (4658–4659) | 3 |

§110 coverage: 1→P1, 2→P2, 3→P2+P3, 4→P4, 5→P1, 6→P4, 7→P5, 8→P6+P7, 9→P8+P9, 10→P8,
11→P9, 12→P9. **12 of 12 covered, none skipped.**

## O3.2 Conflicts between the mandated structure and §110

**C-1 — PHASE 0 does not exist in §110.** §110 phase 1 is *code* ("identity/domain contract
cleanup"). The user's PHASE 0 is a *spec gate*. **Not a conflict of substance** — it is Phase −1
relative to §110, and §110's "do not start by adding dozens of extraction rules / first make the
substrate correct" (`input.md:4662–4664`) endorses it. *Resolution:* label PHASE 0 a **gate**; it
produces no production code and no test; it is the O5 integration plus A7b green.

**C-2 — PHASE 1 merges §110-1 with §110-5 across three intervening phases.** §110 deliberately
orders identity cleanup (1) *before* the signature (5), with 2/3/4 in between. The user places
them together. **Genuine conflict with §110.** It is also the direct cause of DAG defect D2 (the
"temporary fallback" at `tasks.md:34`). *Resolution, and this is the load-bearing one:* split
PHASE 1 internally into **1a** (§110-1, identity cleanup) and **1b** (§110-5, signature +
`RoleBinding` + candidate identity), with **1a committable and green on its own**. Phase 1 as a
whole has one entry condition and one exit condition; 1a/1b are the commit boundary. This
satisfies §110 (1 precedes 5 in the commit history) and the user (one phase named "Identity +
PredicateSignature + RoleSignature"). **The split is mandatory, not optional — G7.4 fails without
it** (see C-3).

**C-3 — the user's PHASE 4 omits §110-5.** §110-5 (signature + candidate identity) sits *between*
§110-4 (signal contract) and §110-6 (producer corrections). In the user's order the signature
lands in PHASE 1 and producers are converted in PHASE 4, so nothing is skipped — but only because
C-2's split is applied. Without it, §110-5 is genuinely skipped and PHASE 4's producers cannot
emit a signature.

**C-4 — PHASE 8 (projection) precedes PHASE 9 (persistence + replay), inverting §110.**
`input.md:4652` puts projection at 10, after persistence at 9; `tasks.md:174` itself says Phase 10
"Depends on Phase 9 (a rebuild needs a store to rebuild from)". **Genuine ordering inversion in
the mandated structure.** *Resolution without reordering:* **split §110-9.** The persistence
*substrate* (migration `021`, ORM parity, the relation store's writer and reader) is an **entry
condition of PHASE 8** — tasks T051–T054 execute as PHASE 8's entry gate and belong to PHASE 8.
The *proof* (build→store→read round trips, replay, corpus, mutations, regression, benchmark) is
PHASE 9. §110-9 is thereby satisfied (persistence exists before projection is verified) and the
user's 8-before-9 order is preserved. **G7.5** asserts the hoist.

**C-5 — PHASE 7 has no §110 counterpart.** §110 has no production-wiring phase. The user's
PHASE 7 is sourced from §101 (recommended final domain model, `input.md:4024`), §108 (acceptance
criteria, `input.md:4355`) and §114 (deliverables, `input.md:4867`). **Additive, not a conflict** —
but it MUST be recorded as a §110 deviation with the authorising § (G7.3).

**C-6 — §110-3 is split across PHASE 2 and PHASE 3.** A split, not a skip. §110-3's own text is
"type hypothesis + mention binding" — two subjects, so the split is faithful.

**C-7 — §110-8 is split across PHASE 6 and PHASE 7.** A split, not a skip.

**C-8 — §110-12 has no home in the user's list.** It is absorbed into PHASE 9, whose subject
("replay / determinism") is where the regression re-run and the boundedness benchmark belong.
*Note:* this makes the Phase-0 baseline freeze (T001) a **repeated** obligation — it must be
re-run at Phase 9's entry, not only at Phase 0. **G9.8** asserts the two-run presence.

## O3.3 The DAG, phase by phase

Notation: `→` hard edge (a phase cannot start until the predecessor's exit holds). `⇢` soft edge
(overlap permitted, different files). `∥` intra-phase parallelism, allowed only where O3 D4's
file-disjointness check passes.

```text
S-0 ──▶ P0 ──▶ P1a ──▶ P1b ──▶ P2 ──▶ P3 ──▶ P4a ──▶ P4b ──▶ P4c ──▶ P5 ──▶ P6 ──▶ P7 ──▶ P8 ──▶ P9
                                    ╰──── P2 ⇢ P3   (different files: type_vocabulary.py / mention_index.py)
```

### PHASE 0 — Spec / Constitution / Traceability  *(gate, no production code)*

| | |
|---|---|
| **Entry** | All seven `repair/A*.md` files exist and are non-empty. The five target files are still byte-identical to the state measured in §0 of this document. |
| **Exit (machine-checkable)** | (E0.1) O5 applied with zero rejected hunks. (E0.2) `repair/integration-decisions.md` exists with one entry per O2 Rule 6 escalation, or is explicitly empty. (E0.3) A7b's checker exits 0 on every assertion in O6. (E0.4) The O1 ownership table has zero uncovered lines in all five files. (E0.5) `checklists/requirements.md` section A has zero `☐`, because A1 closed them. |
| **FRs closed** | `FR-101`–`FR-109` (A1), `FR-115` (A7b) |
| **Tasks** | `S001` apply A1's patch; `S002` apply A2's; `S003` apply A4b's; `S004` apply A5's; `S005` apply A7's; `S006` apply A6's renumbering; `S007` run A7b; `S008` resolve conflict notes in band-owner order. (`S`-series, so the `T`-series stays reserved for implementation.) |
| **Must not** | Touch `input.md`, `research.md`, `phase0-results.md`, or any production code. |

### PHASE 1 — Identity + PredicateSignature + RoleSignature  *(§110-1 + §110-5)*

**1a — identity cleanup (§110-1)**

| | |
|---|---|
| **Entry** | P0 exit; T001 baseline frozen and written down (`tasks.md:19`); `020_universal_relation_extraction.py` confirmed as Alembic head and forward-only (T002). |
| **Exit (machine-checkable)** | (E1a.1) `signal_refs` is sorted/deduped on construction — two candidates, same signals, different input order ⇒ same `candidate_id` (T005). (E1a.2) `verify_candidate_material_partition()` is either called and green or deleted; `CANDIDATE_LOGICAL_MATERIAL_FIELDS` names the field the code emits (T008). (E1a.3) `RelationClaim` re-derives and raises on a forged `relation_id` (T009). (E1a.4) `valid_from`/`valid_to` are removed or read — `grep -c 'valid_from' relation_identity.py` = 0, or the parameter is load-bearing (T010). (E1a.5) All six 019 suites hold baseline: shared 14 failed, control-plane 2 failed, the other four unchanged. |

**1b — signature + candidate identity (§110-5)**

| | |
|---|---|
| **Entry** | 1a exit **and** `predicate_signature.py` exists with `content_key()` and one test per normalisation rule (T011). |
| **Exit (machine-checkable)** | (E1b.1) N1–N6 each have a named test; **N5 is absent from identity material** and its absence is asserted by a test, not by a comment. (E1b.2) `logical_candidate_id` is derived by a function with no `relation_surface` term and no call-site sort: `grep -n 'relation_surface' logical_material` returns nothing. (E1b.3) **SC-001**: `"John acquired Acme."` and `"Acme was acquired by John."` produce one `logical_candidate_id`, two `signal_id`s, two `relation_surface`s, two `candidate_id`s — *derived*, not fixture-pinned (a test that pins both fixtures to one id is itself a mutation that MUST fail, per `spec.md:690` FR-077). (E1b.4) **SC-007**: `works for` / `founded` / `owns` over one pair ⇒ three logical hypotheses. (E1b.5) **SC-002** (§90, end to end): signal → candidate → preserved surface → normalised predicate → signature → `relation_ref=None` → `UNKNOWN` → no claim → no edge, and every evidence item is still retrievable. (E1b.6) `to_dict`/`from_dict` round-trips the full field list (T007). (E1b.7) `RoleBinding` and `canonical_participant_ordering()` have named tests; Q4 (role bindings vs positional) is recorded as an ADR (T014). |

| | |
|---|---|
| **FRs closed** | `FR-001`–`FR-007`, `FR-085`, `FR-086`, `FR-089`, `FR-098`, `FR-099` |
| **Tasks** | 1a: T005, T008, T009, T010. 1b: T011, T015, T014, **T006′ (rewritten, see D2)**, T007, T029, T030, T032. |
| **Files** | 1a: `apps/shared/domain/relation_candidate.py`, `relation_identity.py`, `relation_claim.py`. 1b: `apps/shared/domain/predicate_signature.py` (new), `relation_candidate.py`, `apps/control-plane/semantic_path/assembly.py` (T029 only — identity derivation, not grouping; grouping is Phase 5). |

### PHASE 2 — Type vocabulary + TypeHypothesis substrate  *(§110-2 + §110-3a)*

| | |
|---|---|
| **Entry** | 1b exit. T016 and T017 touch different files, so 2a ∥ 2b. |
| **Exit (machine-checkable)** | (E2.1) `type_vocabulary.py` provides a versioned bounded pack with `core:*` and `value:*` and the hierarchy `core:Organization → industry:Bank → industry:CommercialBank`, loadable with a pinned `version`. (E2.2) An unmapped type yields `UNKNOWN` and is **retained**: no `continue` inside a type branch. (E2.3) **"Apple" retains ≥ 3 `TypeHypothesis` values and selects none.** (E2.4) An ontology match never becomes automatic truth: a test constructs a `core:*` match and asserts no `TypeAssertion` is produced without a mapping record. (E2.5) `schema:Person` produces a `TypeSignal` with `source_vocab`, `surface`, `mapping_candidates` and **not** a `TypeAssertion`. (E2.6) A `TypeMapping` retains subject type, object type, predicate, mapping set, mapping version, confidence, creator/operator and evidence, and a non-equivalence match is recordable as such. (E2.7) The type pipeline runs `Observation → Mention → TypeSignal → TypeHypothesis → SemanticRegime → TypeAssertion`, and a later `INFERRED` status is a **new revision** — a test writes revision 1, then revision 2, and asserts both are readable. (E2.8) **A5's 9 missing SCs** are each traceable to one of E2.1–E2.7. (E2.9) `OntologyPack.relations` stays inert: `grep -rn 'allows_relation' apps/` = 0 non-test hits. |
| **FRs closed** | `FR-029`–`FR-039a`, `FR-110`–`FR-112` |
| **Tasks** | T016, T017, T018, **T075** (`TypeSignal` with mapping candidates), **T076** (`TypeMapping`, SSSOM-compatible), **T077** (type pipeline + revision), **T078** (context consumption: title, heading, DOM parent, table heading, neighbour, URL/domain, metadata, language), **T079** (FR-039a mutual hinting, hints-not-truth). |
| **Files** | `apps/shared/semantic/type_vocabulary.py` (new), `blocking.py`, `contracts.py`, `vocabularies.py`, `apps/interpretation/extractors/types.py`. |
| **∥ / conflict** | T016 ∥ T017 only. T078 and T079 touch `blocking.py` and are sequential after T017. |

### PHASE 3 — Mention binding / occurrence index  *(§110-3b)*

| | |
|---|---|
| **Entry** | 2 exit. ⇢ may start alongside Phase 2's last task (different files). |
| **Exit (machine-checkable)** | (E3.1) `MentionOccurrenceIndex` resolves deterministically on capture, segment, offset/span, normalised surface and extractor occurrence, and yields a real `MENTION-…` **without** resolving to an entity. (E3.2) The 12 fabrication prefixes return **zero** hits in production producer code — enumerated at `data-model.md:218–220`. (E3.3) Every `participant.mention_ref` emitted by any producer resolves in the index — asserted by iterating every producer's real output, not by inspection. (E3.4) A structural producer observing a non-mention records the raw structural slot and emits a **typed, deferred** participant ref; it mints nothing. (E3.5) No producer contains an `ENT-` or `RES-` literal. (E3.6) §96's mutation (`surface:person:john`) **fails** its named test. (E3.7) `Neighbourhood` carries a real scope, not a substring-tested `precision` string. |
| **FRs closed** | `FR-016`–`FR-020` (band `RESERVED-P3`; A6 carries the citation, O2 Rule 8) |
| **Tasks** | T019, T020, T021, **T080** (deferred participant ref type), **T081** (producer import ban + `TYPE_CHECKING` check). |
| **Files** | `apps/interpretation/mention_index.py` (new), `extractors/signals/protocol.py`, the scope wiring in `apps/control-plane/semantic_path/execution.py`. |

### PHASE 4 — Signal contract + producers  *(§110-4 + §110-6)* — **the phase that must be split**

| | |
|---|---|
| **Why 4a/4b/4c** | Measured: `RelationSignal(` has **7** non-test construction sites — `execution.py:2824`, `signal_corpus.py:117`, `lexical.py:169`, `links.py:209`, `metadata.py:397`, `tables.py:165`, `tables.py:261` — and `SignalKind.<member>` has **12** references outside the enum declaration: `assembly.py:219`; `execution.py:1060, 2772, 2827`; `signal_corpus.py:112, 275, 311, 334, 336, 354, 364`; plus `signal.py:394` (own file). Five of the seven sites are producers (Phase-6 work), one is the lifecycle (Phase-8 work), one is the corpus (Phase-11 work). A single Phase-4 commit breaks three later phases and cannot be green, violating `tasks.md:275` ("never bundle a phase boundary"). |

**4a — additive (green)**

| | |
|---|---|
| **Entry** | 1b exit. |
| **Exit** | (E4a.1) `RelationSignal` gains `participants: tuple[RelationParticipant, ...]`, `polarity`, and per-participant `argument_shape` as **new** fields, with `subject_mention_ref`/`object_mention_ref` surviving as **derived compatibility accessors**. (E4a.2) All 7 construction sites still run unchanged. (E4a.3) All 6 019 suites hold baseline. (E4a.4) `signal_asserts_nothing` is replaced: a `CO_OCCURRENCE` may have an empty surface and a `None` signature; a signal with empty surface, no signature, and a kind that *does* assert a predicate is still refused. (E4a.5) `_material()` gains `predicate_signature`, `polarity`, declared `arity` and `role_names` **additively** — `producer_ref` retained, and the three wrong `signal_id` docstrings corrected. |

**4b — producers (green)**

| | |
|---|---|
| **Entry** | 4a exit. |
| **Exit** | (E4b.1) All 5 producers resolve real mention refs. (E4b.2) `metadata.py` deletes the `attribute:*` / `jsonld:*` property-name subjects; `document:current` is gone, replaced by a required `document_ref`; 64-char truncation is replaced by a full content address. (E4b.3) `tables.py`: `zip(..., strict=False)` is strict; a width-mismatched row emits a note or a signal; a heuristic header choice is not published as `precision="exact"`. (E4b.4) `links.py`: one signal per anchor with an honest independence identity; `pairs_considered` is a real count. (E4b.5) `lexical.py`: `surface:role:*` is gone; `MAX_PAIRS_CONSIDERED` is live or deleted. (E4b.6) A `CO_OCCURRENCE` producer and a coreference producer exist; proximity with no predicate words is representable. (E4b.7) `grep` for the 12 prefixes returns 0 (E3.2 re-asserted post-conversion). (E4b.8) A new producer is registered — so `extractors/registry.py` is edited **once, by T037**, and no other producer task touches it. |

**4c — the deletions (green in its own commit)**

| | |
|---|---|
| **Entry** | 4b exit. |
| **Exit** | (E4c.1) The two hard-coded scalars are removed. (E4c.2) `NEGATION`, `QUANTITY`, `COREFERENCE` are removed from `SignalKind`; `TEMPORAL` is **not** added. (E4c.3) `assembly.py:219`, `execution.py:2827` and the 6 `signal_corpus.py` references are migrated **in the same commit** — this is the T082/T083 fix. (E4c.4) `grep -rn 'SignalKind\.\(NEGATION\|QUANTITY\|COREFERENCE\|TEMPORAL\)' apps/ --include=*.py` = 0 non-test hits. (E4c.5) §88's n-ary sale passes end to end. (E4c.6) All 6 019 suites hold baseline. |
| **FRs closed** | `FR-008`–`FR-015` |
| **Tasks** | 4a: **T022a**, T025, T026, T027. 4b: T033, T034, T035, T036, T037, T038. 4c: **T022b**, T023, T024, **T082**, **T083**. |
| **Files** | 4a: `extractors/signals/signal.py`, new `apps/shared/domain/relation_participant.py`, new `apps/shared/domain/polarity.py`. 4b: `lexical.py`, `links.py`, `tables.py`, `metadata.py`, `registry.py`. 4c: `signal.py`, `semantic_path/assembly.py`, `execution.py`, `signal_corpus.py`. |

### PHASE 5 — Candidate assembly  *(§110-7)*

| | |
|---|---|
| **Entry** | 4c exit. ⇢ assembly may be written against the T031 signature contract while 4b is still converting, but **may not be merged** until 4c exit (T082 also edits `assembly.py`). |
| **Exit (machine-checkable)** | (E5.1) `_arity_of` has no majority vote and no alphabetical tie-break, and its annotation is `-> RelationArityMode`. (E5.2) A conflict over arity, direction, polarity or roles yields `CandidateStatus.CONTRADICTED` with **both** readings preserved and appears in `AssemblyReport` as a conflict. (E5.3) A declared `NARY` schema is never downgraded to `DIRECTED`; losing a vote never drops role bindings. (E5.4) Three producers over one pair ⇒ one logical candidate, three `signal_id`s (**SC-005**); the same producer reading the same structure twice ⇒ one `signal_id`. (E5.5) Equal endpoints do not merge (**SC-007**). (E5.6) `RelationalReading.to_candidate()` is deleted or reduced to a call into the assembler; exactly one implementation exists. (E5.7) §95's mutation **fails**. (E5.8) §43/§44: lexical + table + metadata over one participant configuration ⇒ one logical candidate with many signals; a different reading ⇒ a different one. (E5.9) Two signals agreeing on surface with different `relation_ref`s ⇒ one logical hypothesis with `AMBIGUOUS` and neither interpretation overwritten; genuine disagreement ⇒ `CONFLICTING` with both preserved. (E5.10) `PredicateHypothesis` has a **real** `normalized_form` normaliser, and `relation_ref=None` with a full signature is legal and is the norm. |
| **FRs closed** | `FR-021`–`FR-028`, `FR-090`, `FR-091` |
| **Tasks** | T028, T039, T040, T041, T042, T043, **T084** (`PredicateMappingCandidate`; `AMBIGUOUS`/`CONFLICTING` as one hypothesis), **T085** (`OntologyPack` disposition). |
| **Files** | `apps/shared/domain/predicate_hypothesis.py`, `semantic_path/assembly.py`, `apps/interpretation/extractors/relations.py`. |

### PHASE 6 — Claim material / validation / admission  *(§110-8a)*

| | |
|---|---|
| **Entry** | 5 exit. |
| **Exit (machine-checkable)** | (E6.1) Materialisation, validation, admission and projection are separately observable: `ExecutionStage` order is asserted against `STAGE_ORDER` and the assertion is a test. (E6.2) The `ValidationReport` that gated admission is retained on the result and is readable after the run — not a discarded local. (E6.3) The post-admission re-validation is removed or justified in writing with a named §. (E6.4) **The admission decision gates the store write:** a test forces `materialisable = False` and asserts **no row** is written; then forces `True` and asserts one row. (E6.5) Production writes are not doubled to demonstrate idempotency. (E6.6) `ExecutionResult` exposes `material` as a real stage product. (E6.7) No `GraphEdge`/`HyperEdge` exists before a `RelationClaim`. (E6.8) Q5 (producer ↔ lifecycle import direction) is recorded as an ADR. |
| **FRs closed** | `FR-055`–`FR-058`, `FR-092` |
| **Tasks** | T044, T045, T046, T047, **T048 (corrected scope — D6)**, T049, **T086** (surface the `ValidationReport`), **T087** (stage-order assertion). |
| **Files** | `apps/control-plane/semantic_path/execution.py` — **all eight tasks touch this one file, therefore none may carry `[P]`** (D4). |

### PHASE 7 — InvestigationWorkflow production wiring  *(§110-8b, §101/§108/§114 — C-5)*

| | |
|---|---|
| **Entry** | 6 exit. |
| **Exit (machine-checkable)** | (E7.1) A live `POST /api/v1/entities` produces signals → candidates → claims → edges with **real** mention ids — asserted by a test that reads the ids, not by a log line. (E7.2) `ExecutionRequest.producers` is non-empty on every run; `run_producer` iterates more than zero times, asserted by a counter. (E7.3) `lexical_signals` has a production caller — a non-test importer exists. (E7.4) `InvestigationWorkflow` is **dispositioned**: wired, wired-by-contract, or removed — and the `spec.md:809` reachability row says the same thing. (E7.5) Every row of the `spec.md:796–810` reachability table is **re-measured** at the revision's HEAD; a row that says "none" names its disposition. (E7.6) No producer imports a graph, claim, admission or projection symbol (**SC-011**). (E7.7) §101's architecture is present in **production** code, not only in the corpus harness. |
| **FRs closed** | `FR-100`; `FR-101`–`FR-109` are closed at spec level in P0 and *proven* here |
| **Tasks** | T050, T068, T069, **T088** (`InvestigationWorkflow` contract + disposition), **T089** (reachability re-measurement), **T090** (the `execution.py:2827` `SignalKind.SCHEMA` construction site). |

### PHASE 8 — Graph projection  *(§110-9 substrate + §110-10 — C-4)*

| | |
|---|---|
| **Entry** | 7 exit **and** the persistence substrate complete: migration `021` applied, ORM/migration parity test green, and `relation_signal` / `relation_candidate` / `source_temporal_observation` each have a repository, a writer and a reader. **This is the C-4 split: T051–T054 execute as Phase 8's entry gate and belong to PHASE 8.** |
| **Exit (machine-checkable)** | (E8.1) `GraphProjectionBridge` is typed `claim: RelationClaim` with no overload, and a test attempts to project a candidate and a signal and **fails**. (E8.2) `properties` carries `direction` and `polarity`, and neither enters edge identity — a test asserts two claims differing only in `confidence` produce one edge id. (E8.3) `DIRECTED` never reorders endpoints; `UNDIRECTED` reorders **only** when the admitted contract declares symmetry. (E8.4) `NARY` projects to `HyperEdge`; any derived binary edge names its source claim. (E8.5) Rebuild: write claims → project → rebuild via `RebuildableGraphStore` → compare, and `RebuildableGraphStore` has at least one non-test caller. (E8.6) The round trip `edge → claim → candidate → signals → observations → source` and back reaches every edge that source fed (**SC-013**). (E8.7) An unadmitted candidate is served by a separate hypothesis/evidence view; `GraphEdge` is not reused. (E8.8) An unknown predicate stays unknown in the graph — the graph does not invent a type. (E8.9) The production default is still `InMemoryGraphStore`; switching to `Neo4jGraphStore` remains explicitly out of scope. |
| **FRs closed** | `FR-063`–`FR-070`, `FR-059`, `FR-060`, `FR-062`, `FR-113` |
| **Tasks** | Entry gate: T051, T052, T053, T054, T055. Body: T058, T059, T060, T061, T062, **T091** (rebuild path wiring), **T092** (hypothesis/evidence view). |

### PHASE 9 — Replay / determinism / golden corpus  *(§110-9 proof + §110-11 + §110-12)*

| | |
|---|---|
| **Entry** | 8 exit **and** the Phase-0 baseline is re-read (C-8: §110-12 makes the baseline a repeated obligation, not a one-off). |
| **Exit (machine-checkable)** | (E9.1) **SC-010**: run → log → replay → replay yields identical `signal_id`, `candidate_id`, material, claim and edge ids, in a **second process** (not a second call). (E9.2) No `uuid4` / `datetime.now` / `time.time` / `random` in the identity paths. (E9.3) `signal_refs` order-independence is asserted without any call-site sort. (E9.4) Every new substrate object has a build → store → read test asserting the **full field list**, not a summary string. (E9.5) Every producer reports `characters_scanned`, `candidate_pairs_considered`, `structural_nodes_considered`, `signals_emitted`; a producer that enumerates no pairs reports `0` **with a stated reason**; `max_pairs_considered` is a live ceiling a real violation can exceed. (E9.6) The golden corpus contains the **six** §70 end-to-end HTML cases, the **§82** type surfaces (26 named + the 5 ambiguous), and the **§83** relation sets (9 text + 3 event + 10 structural + 1 unknown + the ambiguous and conflicting rules) — recorded in a per-case manifest whose counts are asserted against this sentence, which closes the "18+ / 8 / 6" contradiction. (E9.7) §109's eight cases A–H each map to ≥1 manifest entry, with the mapping recorded; the 2 non-HTML-executable cases are recorded as such, not silently dropped. (E9.8) Every mutation fails **for the right reason** — the assertion is on the failure, not on the failure's existence. (E9.9) **SC-015**: the harness breaks ≥ 20 distinct invariants across entity, relation and projection layers with a named test for each, and the actual count is asserted and the prose matches it. (E9.10) **SC-016**: no suite exceeds its Phase-0 count; the 16 baseline failures are individually classified baseline / new / fixed / flaky. (E9.11) Boundedness benchmark: signal throughput per document, assembly time, projection time, locality-window cost — proving no O(N²) mention sweep. (E9.12) `ruff check` clean on all changed paths. (E9.13) `contracts/`, ADR A–K and `quickstart.md` exist. (E9.14) The completion report uses only `implemented` / `verified` / `verified only offline` / `known limitation` / `deferred`. |
| **FRs closed** | `FR-075`–`FR-081`, `FR-061`, `FR-093`–`FR-097`, `FR-084` |
| **Tasks** | T056, T057, T063, T064, T065, T066, T067, T070, T071, T072, T073, T074, **T093** (golden manifest with asserted counts), **T094** (mutation reason-assertion harness). |

## O3.4 DAG defect register (the fixes)

### D1 — the `0→1→2→5` MVP skips Phase 4

**Evidence.** `tasks.md:254`: *"The smallest defensible increment is **Phases 0 → 1 → 2 → 5**"*.
`tasks.md:94` states Phase 5 *"Depends on Phase 4 (the signal must be able to carry the
signature)"*, and T031 (Phase 5) carries the signature signal → candidate, which requires the
Phase-4 signal shape. **The declared MVP traverses a phase it claims not to need.**

**Fix.** The MVP becomes **`S-0 → P0 → P1`**, i.e. Phase 0 then Phase 1 (1a then 1b). It delivers
**US1 and US2 only** — which is what `tasks.md:254` already claims ("delivers User Story 1 alone")
and is achievable: a relation nobody has a name for survives intact, and active/passive
realisations collapse to one logical id. Phase 4 is not skipped *by the DAG*; the MVP simply stops
before it. See D8 for the story-set contradiction that the current MVP text also has.

### D2 — T006's backwards edge to T020

**Evidence.** `tasks.md:34` (a **Phase 1** task) reads: *"key logical identity on the signature
**(T020)** with a temporary fallback"*. T020 is `tasks.md:68`, a **Phase 3** task ("Wire the
mention index into the extraction scope"). The task that actually creates the signature is
**T011** (`tasks.md:49`, Phase 2). Two defects in one line: a phase inversion *and* a
misidentified dependency.

**Fix.**
1. **Delete T006 as written.** The "temporary fallback" is the defect FR-001/FR-005 forbid: a
   fallback in identity material is a second identity term, and a reader cannot tell which one is
   live. Re-create it as **Phase 1b**, depending on **T011**, with the fallback removed:
   `T006′ [US2] Remove relation_surface from _logical_material(); key logical identity on the
   signature produced by T011. No fallback. Add the failing-then-passing test: active and passive
   realisations share one logical_candidate_id. (FR-005, FR-007) | FILES: …`
2. T020 stays in Phase 3 and no Phase 1 task may reference it.
3. **G3.6/G3.7 enforce it**: no task may reference a task in a later phase. Today this fails on
   exactly this edge.

### D3 — Phase 4 cannot be committed green

**Evidence** (measured, not asserted):

*7 non-test `RelationSignal(` construction sites:*

| Site | Owning phase today |
|---|---|
| `apps/interpretation/extractors/signals/lexical.py:169` | 6 |
| `apps/interpretation/extractors/signals/links.py:209` | 6 |
| `apps/interpretation/extractors/signals/tables.py:165` | 6 |
| `apps/interpretation/extractors/signals/tables.py:261` | 6 |
| `apps/interpretation/extractors/signals/metadata.py:397` | 6 |
| `apps/control-plane/semantic_path/execution.py:2824` | 8 |
| `apps/control-plane/semantic_path/signal_corpus.py:117` | 11 |

*12 `SignalKind.<member>` references outside the enum declaration:*
`assembly.py:219`; `execution.py:1060, 2772, 2827`; `signal_corpus.py:112, 275, 311, 334, 336,
354, 364`; `signal.py:394` (own file).

**Consequence.** `tasks.md:275` says *"never bundle a phase boundary"*. A Phase-4 commit that
removes the two scalars and three enum members breaks 7 call sites in three later phases, so the
Phase-4 boundary is red, so the rule is violated, so the phase cannot be committed as written.

**Fix.** The 4a/4b/4c split in O3.3. **4a is additive and green** (new fields + derived
compatibility accessors + additive `_material()`), **4b converts the 5 producers**, and **4c
performs the deletions and carries its own two call-site migrations** (T082 for `assembly.py:219`;
T083 for `execution.py:2827` and the 6 `signal_corpus.py` references). Each of 4a/4b/4c is
separately committable and green, so no phase boundary is bundled and no boundary is red. The
compatibility accessors are removed **in 4c, in the same commit as the scalars**, never before.

### D4 — `[P]` tasks that share files or read each other's output

**Evidence and fixes.** `[P]` is defined at `tasks.md:11` as *"different files, no dependency"*.
Each of the following violates one half of that definition.

| Pair / group | Shared surface | Violation | Fix |
|---|---|---|---|
| **T048 ↔ T044–T047** | all five edit `apps/control-plane/semantic_path/execution.py` (T044 `_claim_step`, T045 post-admission re-validation, T046 `_store_step`, T047 write doubling, T048 step docstrings) | same file | **Remove `[P]` from T048.** Sequence T044 → T045 → T046 → T047 → T048. T048 is last because it corrects docstrings the other four change. |
| **T001 ↔ T004** | both write `specs/021-.../checklists/requirements.md` (T001 "Record exact pass/fail/skip counts in …requirements.md"; T004 "Create … requirements.md") | same file, both Phase 0 | **T001 records into `repair/baseline-021.md`** (a new file, A8prep-owned); **T004 creates `checklists/requirements.md` and imports the counts from `repair/baseline-021.md`**. T001 runs first, T004 second, neither with `[P]`. |
| **T012 ↔ T013** | both land in `apps/shared/domain/` with **no filename given** — `[P]` is unfalsifiable | undefined file | Give each an explicit path: T012 → `apps/shared/domain/polarity.py`, T013 → `apps/shared/domain/relation_participant.py`. `[P]` becomes checkable, and is then correct (both are new files). |
| **T033–T037** | files differ, but all five must construct the same restructured `RelationSignal`, and T037 must **register** new producers in `apps/interpretation/extractors/registry.py` | shared file (`registry.py`) + dependency | T033–T036 keep `[P]` (four distinct producer files). **T037 loses `[P]`** and is sequenced after T033–T036, because it is the only editor of `registry.py`. |
| **T065** | replay harness; reads every id produced by T051–T057 | dependency | **Remove `[P]`.** T065 follows Phase 8. |
| **T067** | boundedness report; reads the counters T033–T036 emit | dependency | **Remove `[P]`.** T067 follows T033–T036. |
| **T072** | `ruff check` over all changed paths | reads every other task's files | **Remove `[P]`**; a linter is a **gate**, not a parallel task. Move it to the end of its phase. |

**Structural fix (prevents recurrence).** Every task gains a machine-checked `FILES:` line listing
its exact write set, e.g. `T005 [US1] … | FILES: apps/shared/domain/relation_candidate.py`.
A7b's checker gains assertion **G3.5**: *for every phase, no two `[P]` tasks have an intersecting
`FILES:` set, and no `[P]` task's `FILES:` set is read by another task in the same phase.* Today
**6 groups** violate this (T048; T001/T004; T012/T013; T037; T065; T067) plus T072.

### D5 — phantom task ids

**Evidence.** Measured: `tasks.md` defines `T001`…`T074` with **no gaps**. Referenced but never
defined: **9 ids across 6 base tasks** — not 5.

| Phantom id | Referenced at | Real task it means |
|---|---|---|
| `T007c` | `checklists/requirements.md:60, 61` (D4, D5 rows) | **T035** (metadata producer, `document:current`) |
| `T007f` | `checklists/requirements.md:25, 57, 58` (A7, D1, D2 rows) | **T038** (cross-producer assertion) + **T081** (import ban) |
| `T009f` | `tasks.md:268` (Q5) | **T049** (Q5, import direction) |
| `T010d` | `tasks.md:270` (Q7) | **T054** (repository for the three 020 tables) |
| `T010f` | `tasks.md:270` (Q7) | **T056** (normal acquisition path) |
| `T011a` | `checklists/requirements.md:21` (A3) | **T058** (bridge typed claim-only) |
| `T011c` | `checklists/requirements.md:24` (A6) | **T060** (rebuildability) |
| `T012d` | `checklists/requirements.md:59, 65, 72, 85, 116` (D3, D9, E2, F3, H11) | **T066** (the mutation suite) |
| `T013a` | `tasks.md:269` (Q6) | **T068** (`interpret_warc_capture` is the live path) |

**Fix.** Every reference is rewritten to the real id above. `T012d` is the important one: five
checklist rows depend on a "mutation task" that does not exist, so five mutation requirements
currently have **no owner**. **G3.2** and **G3.3** make sub-lettered ids impossible: every
`T`-token in any of the five files must match a `^- \[ \] T\d{3}$` heading in `tasks.md`.

### D6 — T048's understatement

**Evidence.** `tasks.md:146` reads: *"T048 [P] [US8] Fix the docstrings that say 'thirteen steps'
— there are fourteen."* Measured in `apps/control-plane/semantic_path/execution.py` (3360 lines):

| Claim | Measured truth |
|---|---|
| "the docstrings that say *thirteen steps*" | **5 sites in 4 files**: `execution.py:16` ("`STAGE_ORDER` names thirteen steps"), `execution.py:302` ("The fourteen steps" — the file **contradicts itself**), `semantic_path/corpus.py:8`, `semantic_path/corpus_cases.py:5`, and `migrations/versions/020_universal_relation_extraction.py:94` ("The thirteen signal kinds" — a **different** thirteen, `SignalKind` members, which Phase 4 changes for a different reason) |
| (unstated) how many step-numbered docstrings | **28**, in two parallel 14-step ladders: `execution.py:685–1206` and `execution.py:2094–3275`. Plus 11 lowercase prose "step N" cross-references = **39** mentions total. Not ~35 docstrings. |
| (unstated) ladder integrity | **"Step 9" appears 3×** — `execution.py:1106`, `3136`, `3179` (not twice). Ladder 2 has **no "Step 10"**: `3179 "Step 9 - ask the operator's own view"` is followed by `3194 "Step 11 - write through the real relation store"`. Ladder 1 *does* have one (`1135`). |
| (unstated) non-integer steps | **"Step 6b" appears twice** — `execution.py:1053` and `2764` — and it is *labelled* `6b` but sits outside the integer sequence in both ladders, between Step 6 and Step 7. |
| (unstated) a worse defect | Ladder 1 is **out of order**: Step 7 (`1021`), Step 6b (`1053`), Step 9 (`1106`), Step 10 (`1135`), Step 8 (`1149`). This directly contradicts `execution.py:302–305`, which claims the declaration order is the point and that `STAGE_ORDER` "is derived from the declaration order so the two cannot drift apart". They have drifted. |

**Fix.** T048 is rewritten to enumerate its full scope: 28 step-numbered docstrings in two
ladders, 5 "thirteen" sites in 4 files (including the `020` migration comment, which is a
different thirteen), the 3× "Step 9", the missing "Step 10" in ladder 2, the two "Step 6b"
labels, and the ladder-1 declaration-order inversion with its `STAGE_ORDER` contradiction. T048
also **loses `[P]`** (D4) and becomes the last task of Phase 6. T048's *acceptance* is E6.1: the
step numbers in both ladders are `1..14` in declaration order, asserted by a test, so the defect
cannot recur.

### D7 — the dependency diagram is a chain that contradicts its own overlap note *(found)*

**Evidence.** `tasks.md:219–245` draws a strict vertical chain, then `tasks.md:247–250` says
*"Phases 6 and 7 may overlap … Phases 2 and 3 are likewise partly parallel"*. A chain is a total
order; the text asserts a partial order. **Fix.** Replace the ASCII chain with an **edge list** (the
`→`/`⇢` notation in O3.3), which is both machine-checkable (G3.6, G3.7) and honest about the
parallelism.

### D8 — the MVP contradicts its own phase tags *(found)*

**Evidence.** `tasks.md:254` claims the `0→1→2→5` path "delivers User Story 1 alone", but
`tasks.md:30` (Phase 1) = US1, US2, US8; `tasks.md:46` (Phase 2) = US1, US7; `tasks.md:93`
(Phase 5) = US1, US2, US5, US6. The path carries **five** stories. **Fix.** The MVP is Phase 0 +
Phase 1 (D1) and names US1 + US2, which is what the prose intended and what Phase 1's own story
tags support. **G3.10** asserts the MVP is a prefix of the phase order and that its named story
set equals the union of its phases' story tags.

### D9 — mutation and golden-case counts are mutually contradictory *(found)*

**Evidence.**

| Claim | Location | Reality |
|---|---|---|
| "the 17 mutations from §84–§101" | `tasks.md:188` | §84–§101 contains **6** named mutations (§94–§99) plus 4 test sections (§84, §85, §86, §87) and §93's harness groups (entity 6 / relation 8 / projection 4 = **18**). "17" matches nothing. |
| "17 mutations from §94–§101" | `checklists/requirements.md:135` | §94–§101 = **6** named + §101. |
| "Four named mutations … : (§94); (§95); (§96); (§97); (§98); (§99)" | `spec.md:699–703` (FR-079) | says **four**, lists **six**. |
| "breaks ≥ 20 distinct invariants" | `spec.md:901` (SC-015) | §93 lists 6+8+4 = 18 field groups; "≥20" is unsourced. |
| "18+ golden cases" | `tasks.md:197` | unsourced. |
| "The 8 golden end-to-end HTML cases" | `tasks.md:188` | §70 has **6** examples; §109 has **8** cases. |
| "the six end-to-end HTML cases of §70" | `tasks.md:191` | correct — and it contradicts the line above it. |
| §82 corpus size | `input.md:3463–3490` | **26** named surfaces + 5 ambiguous names (`Apple` overlaps) |
| §83 corpus size | `input.md:3523–3577` | **23** explicit + 2 rule-based (ambiguous, conflicting) |

**Fix (A6 owns all eight; E9.6–E9.7 enforce).** Adopt a **golden manifest** — one row per case
with its §-source and its §70/§109 mapping — and derive every count from it. Reconcile
`spec.md:699` to six named mutations; set SC-015's floor to the measured number of distinct
invariants the harness breaks; replace "18+" and "17" with manifest-derived counts; and state once
that §70 supplies 6 executable cases which are the executable form of §109's 8 conceptual cases,
naming which 2 of the 8 are not HTML-executable and why.

### D10 — T004's deliverable does not match what it says *(found)*

**Evidence.** `tasks.md:22`: *"Create `checklists/requirements.md` … mapped to the 102 FRs, and
mark each item's verification method."* The file it produced (`checklists/requirements.md`) cites
an FR **exactly once** — line 11, `FR-081` — and its `Method` column uses a 5-letter key
(`T`/`I`/`M`/`B`/`P`, line 7) that is never expanded. The traceability map T004 promised does not
exist. **Fix.** T004's text is corrected to *"…mapped to the task that verifies each item"*, and
the **102-FR verification map becomes a separate A6 deliverable** (the traceability matrix), which
is what closes the 52 orphans under O2 Rule 8. The `Method` key is expanded to a table.

### D11 — the open-questions table points at phantoms *(found)*

**Evidence.** `tasks.md:262–270`: Q5 → `T009f`, Q6 → `T013a`, Q7 → `T010d`, `T010f` — **all four
are phantoms** (D5). Q1 → T011/T015/T028 (real), Q2 → T016 (real), Q3 → T021 (real), Q4 → T014
(real). **Fix.** Remap per D5: Q5 → T049, Q6 → T068, Q7 → T054 + T056. **G3.2** catches this class
automatically.

### D12 — the MVP's "worth building and stopping there" is unearned as written *(found)*

**Evidence.** `tasks.md:256–258` argues the MVP is "the constitutional heart". With the
`0→1→2→5` path that is true but incoherent (D1, D8). **Fix.** With the MVP narrowed to Phase 0 +
Phase 1 the argument holds *and* is checkable: E1b.3 (SC-001 derived, not fixture-pinned) and
E1b.5 (SC-002 end to end) are exactly the two proofs that justify stopping.

---

# O4 — The 10-phase spec model diagram, and where `data-model.md` disagrees

## O4.1 The mandated architecture

```text
Observation
    │
    ▼
MentionBinding                     [stage]  ── via MentionOccurrenceIndex  [structure]
    │
    ├──▶ TypeSignal ──▶ TypeHypothesis ──▶ TypeAssertion   ⟳ revisions   (terminates; DM-6)
    │
    └──▶ RelationSignal ──declared by──▶ PredicateSignature
                 │                        │
                 │                        ▼
                 └──────────────▶ RelationCandidate ◀── ONE structural identity (signature)
                                          │           ◀── ONE semantic interpretation
                                          │                 (relation_ref, PredicateMappingCandidate,
                                          │                  vocabulary links)
                                          ▼
                                     ClaimMaterial   ── gated by: entity_resolution satisfied,
                                          │              semantic_regime bound          (DM-5)
                                          ▼
                                     ValidationReport
                                          │
                                          ▼
                                     AdmissionDecision
                                          │
                                          ▼
                                     RelationClaim
                                          ├──▶ GraphEdge
                                          ├──▶ HyperEdge
                                          └──▶ WorldLine                                (DM-10)
```

`RelationCandidate` split, restated:

| Half | Owns | Never carries |
|---|---|---|
| **Structural identity** | `PredicateSignature` (normalised predicate, arity, `RoleBinding`/role names, argument shape, direction, polarity) | surface, `relation_ref`, confidence, any entity id |
| **Semantic interpretation** | `relation_ref`, the `PredicateMappingCandidate` set, vocabulary links, mapping evidence | any contribution to `logical_candidate_id` |

## O4.2 Disagreements found in `data-model.md`

| Id | Disagreement | Evidence | Owner | Resolution |
|---|---|---|---|---|
| **DM-1** | **Four names for one thing.** The diagram says `MentionBinding`; `data-model.md:215` says `MentionIndex`; `spec.md:438` (FR-018) and `spec.md:859–860` say `MentionOccurrenceIndex`; `input.md:1565` titles the section "Introduce MentionBinding" and `input.md:1570` names the structure `MentionOccurrenceIndex`. | measured | **A5** | Canonical **structure** name = `MentionOccurrenceIndex` (two documents agree, one dissents). `MentionBinding` = the **stage**. A5 edits `data-model.md:215` and `:298` to `MentionOccurrenceIndex` and records the stage/structure distinction. No other agent may introduce a fourth spelling. |
| **DM-2** | **`TypeSignal` and `TypeMapping` are absent from `data-model.md` entirely.** Both are Key Entities (`spec.md:849–852`) and both are in the diagram; both appear in FR-035/FR-036. `data-model.md` §6 covers `TypeHypothesis` and the vocabulary and stops. | `data-model.md:222–243`; §9 rows 291–303 | **A5** (`TypeSignal`) + **A4b** (`TypeMapping`) | Ordered appends per HS-4 / HS-13. **G4.4** asserts every Key Entity has a §9 row. |
| **DM-3** | **`ValidationReport` and `AdmissionDecision` are first-class in the diagram and absent from `data-model.md`.** `spec.md:746` (FR-092) names `ValidationReport`; `tasks.md:144` names `decision.materialisable`. Neither has a §9 row or any field list. | §9 rows 291–303 | **A1** | Two §9 rows at reserved order 6–7, each carrying `Status = NEEDS-SPEC` and a pointer to Phase 6. A `NEEDS-SPEC` row is a promise, not a specification: A7b flags it at gate time and the completion report lists it as `deferred`, never as `implemented`. |
| **DM-4** | **The diagram draws `RelationSignal → PredicateSignature` as a *stage* edge; `data-model.md:84` makes it a *field*.** | `data-model.md:84`; FR-087 (`spec.md:724–727`) | **A2** (annotates) | Not a structural disagreement — a labelling one, and it changes where persistence lands. FR-087 (A7's band) already settles it as columns on `relation_signal`, i.e. a field. **Resolution:** the edge is annotated *"declared by, not produced as a separate stage"*, and the legend says so. Otherwise a reader looks for a `PredicateSignature` store row keyed by a signal and finds none. |
| **DM-5** | **The diagram omits `ENTITY RESOLUTION` and `SEMANTIC REGIME`, which §101 places between `RELATION CANDIDATE` and `CLAIM MATERIAL`.** | `input.md:4077–4082`; FR-024 (`spec.md:459`) requires participants be *resolved*; FR-056 (`spec.md:605`) forbids resolution being part of the *claim lifecycle* | **A1** | A real compression, not a skip. **Resolution:** the `RelationCandidate → ClaimMaterial` edge is annotated with both required conditions as **gates on the edge**, not as nodes, because FR-056 forbids making resolution a lifecycle stage. A reader who misses this builds a candidate→material path that bypasses the regime — the exact §66 failure FR-022 forbids. §6 reserved row 8 carries the gate annotation. |
| **DM-6** | **The brace in the diagram invites reading the type branch as feeding the relation branch.** §101 has them as siblings off `MENTION OCCURRENCES`; the type branch terminates at `TYPE ASSERTIONS`. | `input.md:4037–4044` | **A5** | No disagreement with §101, but a misreading risk that is *constitutional*. FR-039a (`spec.md:538`) requires the two to be **mutually consumable as hints**; FR-054 (`spec.md:595`) forbids an ontology match becoming truth. **Resolution:** the diagram is annotated that no `TypeAssertion → RelationCandidate` edge exists, and the legend states that cross-consumption is a *hint channel*, not a flow edge. |
| **DM-7** | **`relation_ref` is declared on two types.** `data-model.md:128` (`RelationCandidate.relation_ref`) and `data-model.md:176` (`PredicateHypothesis.relation_ref`). Two sources of truth for the mapping. | measured; §9 rows 295 and 296 | **A4b** (owns 128–129 and §4) | The diagram's split puts the mapping wholly on the **interpretation** side, singularly. **Resolution:** A4b declares `PredicateHypothesis.relation_ref` authoritative and `RelationCandidate.relation_ref` a **derived projection**, or the reverse — A4b's choice — and states which, in one line, at `data-model.md:123–134` and `:172–179`. **G4.5** fails until exactly one is authoritative. |
| **DM-8** | **Four different counts of the same structure.** `data-model.md:9` says "The **seven** levels"; `data-model.md:10–11` lists **9** nodes; `spec.md:359` INV-001 enumerates **8** types; the approved diagram has **12** named nodes. | measured | **A1** (the constitutional statement) + **A6** (the count claims) | One count, one place. **Resolution:** INV-001 and `data-model.md:9` are restated as *"these types remain distinct"* with the count **removed from the invariant** and carried once in a single table whose row count equals the diagram's node count. A structural invariant with a number in it is a number that will drift. **G4.2** asserts equality. |
| **DM-9** | **The diagram's short names do not match the code types.** `ClaimMaterial` vs `RelationClaimMaterial` (`data-model.md:300`); `MentionBinding` vs `MentionOccurrenceIndex`; `TypeSignal`/`TypeMapping` absent entirely. | measured | **A6** (legend) | Acceptable **only** with a legend. A7b resolves every diagram node name against the legend; an unresolved name is a gate failure (G4.1). Without the legend, 4 of 12 nodes are dangling. |
| **DM-10** | **`WORLDLINE` is missing from the diagram.** §101 shows it as a third projection (`input.md:4098`) and FR-055 (`spec.md:601–604`) names it as a lifecycle stage. | measured | **A1** | Add `→ WorldLine` as a third projection, or record explicitly that it is out of the diagram's scope. **Silent omission is not permitted** — it is the same class of defect as the count disagreements the feature exists to remove. |
| **DM-11** | **The diagram's `GraphEdge/HyperEdge` is downstream of `RelationClaim` — correct, and it agrees with `data-model.md:272–276`.** | measured | — | **No disagreement. Recorded because O4 must state what was checked and agreed, or a reader cannot distinguish "checked and fine" from "not checked".** `data-model.md:280–283`'s Neo4j exclusion is consistent with the diagram and with research R-006. |
| **DM-12** | **`TypeAssertion` is terminal in the diagram, so the diagram hides revision.** FR-037 (`spec.md:528`) requires all prior states retained and a later `INFERRED` status to be a **new revision**, not a replacement. | measured | **A5** | The node is annotated `⟳ revisions`. The diagram is a *stage* diagram and may show the current state; it may not imply finality. |

**Count: 12 items examined, 11 disagreements (DM-1…DM-10, DM-12), 1 clean (DM-11).**

---

# O5 — The integration procedure

Ordered, mechanical, reversible. Every step is one commit.

## S0 — Freeze

Assert: no agent has edited `spec.md`, `data-model.md`, `plan.md`, `tasks.md` or
`checklists/requirements.md`; all seven `repair/A*.md` files exist and are non-empty; the five
files are byte-identical to the §0 state table of this document. **A7b's checker runs on the
unmodified tree and its failure list is recorded** — without a pre-repair baseline, no repair can
be shown to have fixed anything.

## S1 — Freeze the patches

Each agent's output becomes an immutable patch against the *original* files, in
`repair/patches/`. Patches are never re-authored by the integrator. A patch that fails to apply
goes back to its agent.

## S2 — Validate patch geometry

Before applying anything, A7b checks each patch's hunk headers against the §0 length table.
**A patch authored against the brief's stated lengths (913 / 285 / 245 / 282 / 158) is rejected** —
it is off by up to 23 lines and would land on the wrong range.

## S3 — Apply in dependency order, not author order

```text
A1 → A2 → A4b → A5 → A7 → A6 → A7b
```

**A6 goes last because it is the only agent that rewrites FR citations inside other agents'
bands.** Applied earlier, it guarantees collisions. A7b goes last because it is the checker.

Within each file, apply that agent's hunks **bottom-up** (descending start line) — O1 Rule O1.1.
This is what keeps the O1 table authoritative for the whole run.

## S4 — Ownership assertion (mechanical, before any human reads)

A7b asserts **G1.2**: for every range in the O1 table, the number of agents whose patch touches it
is **≤ 1**. A violation aborts the integration and the offending patch is returned to its author.
This is the assertion that makes "zero overlapping edits" a fact rather than an intention.

## S5 — Semantic conflict notes (O2 Rule 2), in band-owner order

Collect every `CONFLICT-NOTE:` from the seven repair files. For each, route it to the **band
owner** of the cited FR. The band owner emits a conforming edit inside its own band. Notes the
band owner disputes escalate under O2 Rule 6.

## S6 — Contradiction resolution (O2 Rule 6 ladder)

| Situation | Resolver | Action |
|---|---|---|
| Two bands assert incompatible `MUST`s, neither cites the other | **A6** (mechanics) | Decide by Rule 3 (lower band normative) or Rule 4 (one enumeration). Record in `repair/integration-decisions.md` with the rule cited. Route the edit to the higher band's owner. |
| Same band, internal contradiction | **band owner** | Fix inside the band. |
| Numbering / traceability / placement collision | **A6** | Fix. A6 routes; A6 does not rewrite another agent's text. |
| Cross-band contradiction not settled by Rules 3–5 | **A8**, at final audit | Record; if it would change a requirement's *meaning*, escalate to the user. |
| Would change what a requirement means | **the user** | No agent and no auditor may do this. |
| Two agents need the *same line* | **never resolved — G1.2 aborts** | Return the patch. The O1 table exists precisely so this cannot happen. |

**Never permitted**: keeping both `MUST`s with "see also" (O2 Rule 7); silent majority-winner
selection; a merge that leaves the loser unlabelled. A losing normative statement moves to a
`## Superseded` note naming the superseding FR, the deciding rule, and the deciding agent.

## S7 — Post-apply verification

Run A7b's checker over the integrated tree. Every assertion in **O6** must pass. Record the output
verbatim in `repair/integration-decisions.md`.

## S8 — Human read of exactly three things

Everything else is machine-checked. A human reads: (a) the diffs at the **hot spots** (O1.6) — 16
locations, ~40 lines; (b) the **FR allocation table** (O2.3) against the numbers actually used in
the text; (c) the **diagram** (O4.1) against `data-model.md`. Three reads, and every other byte is
covered by an assertion.

## S9 — Publish

Emit: revision id; the applied-patch manifest (7 patches + 7 application commits); the checker
output; the decision log. The revision is then handed to A8 for the O6 gate.

**Rollback.** Every step is one commit and every patch is an immutable artefact, so a bad
integration is reverted and re-applied in a different order **without re-running any agent**. That
property is the reason for the freeze in S0 and the patch discipline in S1.

---

# O6 — Gate criteria for the final audit

Objective, complete, and machine-checkable wherever the check can be. **Any assertion failing ⇒
the revision is NOT PASS.** A8 records the failing ids; there is no partial pass.

## G1 — Ownership and geometry

| Id | Assertion | Check |
|---|---|---|
| G1.1 | Every line of all five files is covered by exactly one O1 range | coverage set == `{1..len}` per file, no overlap |
| G1.2 | No two agents touched the same O1 range | per-range patch-touch count ≤ 1 |
| G1.3 | No patch edited a range marked `UNCHANGED` | diff hunks ∩ UNCHANGED ranges = ∅, except the 9 named carve-out lines |
| G1.4 | Every append landed at its declared anchor, in the reserved order | per-anchor sequence check |
| G1.5 | All seven `repair/A*.md` exist, are non-empty, and are referenced from the revision | existence + non-empty + grep |
| G1.6 | `tasks.md` was written only by A8prep | no patch from A1/A2/A4b/A5/A6/A7/A7b touches `tasks.md` |

## G2 — Numbering and traceability

| Id | Assertion | Check |
|---|---|---|
| G2.1 | FR ids are unique | `set(ids) == len(ids)` |
| G2.2 | Every FR id matches `^FR-[0-9]{3}[a-z]?$` | regex over `spec.md` |
| G2.3 | Each agent's band (O2.3) is **contiguous in document order** | line numbers of a band's ids strictly increasing |
| G2.4 | `FR-082` sits numerically between `FR-081` and `FR-083` in document order (today: **fails** — `FR-082` is at line 814, `FR-100` at 781) | line-order check |
| G2.5 | **Every FR in `FR-001`–`FR-100` is cited by ≥1 of `tasks.md` / `checklists/requirements.md` / `data-model.md`** (today: **52 fail**) | set difference |
| G2.6 | Every FR carries ≥1 `§`-reference into `input.md` | regex + G5.5 |
| G2.7 | Every FR appears in A6's traceability matrix with an owning phase and a verifying task | matrix completeness |
| G2.8 | Every SC is referenced by ≥1 task id **that exists in `tasks.md`** | join |
| G2.9 | Every INV is traceable to ≥1 test id and ≥1 § | join |
| G2.10 | Count claims equal measured reality: FR / INV / SC / story / corpus counts are identical in `spec.md`, `plan.md:6–8`, `plan.md:71–73`, `tasks.md:22`, `checklists/requirements.md` and FR-075/FR-076 | 6-way numeric agreement |
| G2.11 | `FR-116`–`FR-129` are **unused** — a used reserved slot is a silent scope expansion | absence check |
| G2.12 | Every `## Superseded` note names the superseding FR, the deciding rule and the deciding agent | 3-field presence |
| G2.13 | `input.md` is byte-identical to the brief — it is the authority and is never edited | hash |

## G3 — Task graph

| Id | Assertion | Check |
|---|---|---|
| G3.1 | Every `- [ ] T\d{3}` in `tasks.md` is unique and within `T001`–`T094` | uniqueness + range |
| G3.2 | Every `T`-token in any of the five files matches a defined task (today: **9 violations**) | set difference |
| G3.3 | No `T\d{3}[a-z]` sub-id exists anywhere (today: **9 violations**) | regex = ∅ |
| G3.4 | Every task carries a `FILES:` line listing its exact write set (today: **0** do) | presence + parse |
| G3.5 | **No two `[P]` tasks in the same phase have intersecting `FILES:` sets, and no `[P]` task's write set is read by another task in the same phase** (today: **6 groups** violate) | set intersection over each phase |
| G3.6 | No task references a task in a later phase (today: **1 violation**, T006 → T020) | phase comparison over the reference graph |
| G3.7 | The phase graph is a DAG: no cycle | topological sort |
| G3.8 | Phases 0…9 are present with no gap | enumeration |
| G3.9 | Every phase states an entry and an exit condition, and every exit condition is a machine command or a named test id | form check |
| G3.10 | The MVP is a prefix of the phase order and its named story set equals the union of its phases' story tags (today: **fails**) | set equality |
| G3.11 | The §110 → 10-phase mapping table is present and every §110 phase 1…12 is mapped (today: 12/12) | coverage |
| G3.12 | Every deviation from §110 names the § that authorises it (C-5's PHASE 7) | presence |
| G3.13 | Every FR in every phase's "FRs closed" list is in the phase owner's band (O2.3) | band membership |

## G4 — Data model vs the diagram

| Id | Assertion | Check |
|---|---|---|
| G4.1 | Every node name in the diagram resolves through the legend to a code type or a stage name (today: 4 dangling) | resolution |
| G4.2 | The level count in `data-model.md:9`, in INV-001 and in the diagram are **equal** (today: 7 / 8 / 12) | numeric equality |
| G4.3 | No concept has two names across the five files (today: `MentionIndex`/`MentionOccurrenceIndex`/`MentionBinding`; `ClaimMaterial`/`RelationClaimMaterial`; `CoreTypePack`/`TypeVocabulary`) | alias extraction + collision |
| G4.4 | Every Key Entity has a §9 row (today: `TypeSignal`, `TypeMapping` missing) | join |
| G4.5 | Exactly one type declares each duplicated field authoritative (today: `relation_ref` on two types) | uniqueness on (field, authoritative) |
| G4.6 | Every §9 row has `Status ∈ {NEW, CHANGED, EXTENDED, unchanged, REMOVED, NEEDS-SPEC}`, and every `NEEDS-SPEC` row appears in the completion report as `deferred` | enum + join |
| G4.7 | Every `## n.` section's entities and the §9 rows agree on `Status` and `Identity key` | join + field equality |
| G4.8 | No diagram edge contradicts a `MUST` in the FRs (DM-5, DM-6) | edge-list review against the FR text |
| G4.9 | Every diagram node marked `NEEDS-SPEC` has a named owning phase | presence |

## G5 — Reference integrity (A7b's core)

| Id | Assertion | Check |
|---|---|---|
| G5.1 | Every relative markdown link in the five files resolves | link check |
| G5.2 | Every file path named in the five files exists, or is declared `NEW` with an owning task | existence + declaration |
| G5.3 | Every `path.py:NNN` line reference points to an existing line **and** that line still says what the claim says | parse + content assertion |
| G5.4 | No undefined FR / SC / INV / T / ADR-letter reference anywhere | set difference |
| G5.5 | Every `§N` reference into `input.md` resolves to a real section in `0..114` | heading set |
| G5.6 | Every type name and enum member named in the five files exists at HEAD, or is declared `NEW` with an owning task | symbol existence |
| G5.7 | The 12 fabrication prefixes enumerated at `data-model.md:218–220` match the list the checker greps for | list equality |
| G5.8 | ADR letters A–K each have a record (11 records) | presence + completeness |
| G5.9 | `contracts/` exists and declares the producer protocol, the mention-index contract and the store contract | presence |
| G5.10 | The checker itself exits non-zero on a deliberately injected violation | self-test |

## G6 — Constitutional

| Id | Assertion | Check |
|---|---|---|
| G6.1 | INV-001…005 each trace to ≥1 test and ≥1 § | join |
| G6.2 | The constitution check table has a status and a re-check for every principle, and the supersession rule states which document wins | completeness |
| G6.3 | `InvestigationWorkflow` has a recorded disposition, and the `spec.md:809` reachability row agrees with it | agreement |
| G6.4 | No requirement permits majority-vote resolution — every `majority` occurrence is inside a prohibition | context regex |
| G6.5 | No requirement makes a vocabulary match a gate | context regex |
| G6.6 | No requirement permits an edge not derived from an admitted `RelationClaim` | context regex |
| G6.7 | No requirement permits a producer to import a graph/claim/admission/projection symbol, or to contain `ENT-`/`RES-` | context regex |
| G6.8 | The distinct-type invariant appears once, with one count (G4.2) | uniqueness |

## G7 — Phase gate coherence

| Id | Assertion | Check |
|---|---|---|
| G7.1 | Every phase 1…9 exit condition is satisfied by a named test that exists in `tasks.md` | join |
| G7.2 | The 10-phase structure covers all 12 §110 phases (today: 12/12) | coverage |
| G7.3 | Every §110 deviation is recorded with its authorising § | presence |
| G7.4 | **C-2's split exists** — Phase 1 has both 1a and 1b, and 1a is committable alone (today: absent) | structure |
| G7.5 | **C-4's split exists** — the persistence substrate is Phase 8's entry condition, and no Phase 8 task depends on a Phase 9 task (today: `tasks.md:174` makes projection depend on persistence) | edge-direction check |
| G7.6 | Every E-assertion listed in O3.3 maps to ≥1 task | join |
| G7.7 | The 7 broken construction sites and 12 enum references each have an owning task (T033–T037, T082, T083, T090) | join against the measured site list |

## G8 — Persistence and migration (A7's band)

| Id | Assertion | Check |
|---|---|---|
| G8.1 | `020_universal_relation_extraction.py` is byte-identical to HEAD | hash |
| G8.2 | `021` exists, is forward-only, and its `downgrade()` raises `NotImplementedError` | existence + `raise` check |
| G8.3 | `021` is the Alembic head | `alembic heads` |
| G8.4 | The ORM/migration parity test exists and is named in `tasks.md` | join |
| G8.5 | Every column in `021` appears in the ORM and every ORM column in `021`, with no delta | set equality both ways |
| G8.6 | The obsolete CHECK constraints inherited from `020` are named in the spec **and** dropped by `021` | name-in-spec ∧ `DROP CONSTRAINT` in the migration |
| G8.7 | Every column that participates in an id has a column in its table | rule check over the identity functions |
| G8.8 | No digest is the only copy of any field (FR-060) | field-level check on `alternative_refs` / `mapping_evidence_refs` / `normalized_form` / `signal_refs` |

## G9 — Honesty

| Id | Assertion | Check |
|---|---|---|
| G9.1 | The 16 baseline failures are itemised and unchanged; no suite exceeds its Phase-0 count | counts |
| G9.2 | The completion report uses **only** the five permitted status words | vocabulary check |
| G9.3 | Every `verified` claim names a test; every offline-only claim says so | join |
| G9.4 | No completion claim rests on the corpus harness alone | FR-084 check |
| G9.5 | Every row of the reachability table is re-measured at the revision's HEAD; a row saying "none" names a disposition | freshness |
| G9.6 | SC-015's stated floor equals the number of invariants the harness actually breaks, with a named test for each (today: "≥ 20" vs §93's 18 field groups) | measured vs prose |
| G9.7 | Every mutation fails **for the right reason** — the assertion is on the failure, not on the failure's existence | harness design check |
| G9.8 | The baseline was re-run at Phase 9's entry, not only at Phase 0 (C-8) | two-run presence |

---

## O6.1 Assertion count and current expected failures

**Total machine-checkable assertions: 87** (G1: 6, G2: 13, G3: 13, G4: 9, G5: 10, G6: 8, G7: 7,
G8: 8, G9: 8).

**Assertions that fail against the revision as it stands today** (each is a defect already
assigned an owner):

| Assertion | Measured failure | Owner |
|---|---|---|
| G2.3 / G2.4 | `FR-082` is at line 814, after `FR-100` at 781 | A6 |
| G2.5 | **52** orphan FRs | A6 + every band owner (O2 Rule 8) |
| G2.8 | 5 checklist rows depend on the phantom `T012d` | A6 → T066 |
| G2.10 | `input.md` is 4898 lines but `spec.md:16` and `plan.md:99` say 3411; `spec.md:699` says "Four named mutations" and lists six; §110-12's count has no home | A6 |
| G3.2 / G3.3 | **9** phantom task ids | A8prep |
| G3.4 | **0** tasks carry a `FILES:` line | A7b |
| G3.5 | **6** `[P]` groups share files or read each other, plus T072 | A8prep |
| G3.6 | **1** backwards edge (T006 → T020) | A8prep |
| G3.9 | No task carries an entry/exit condition; no phase states one | A8prep |
| G3.10 | The MVP names US1 but its phases carry US1, US2, US5, US6, US7 | A8prep |
| G4.1 | **4** dangling diagram names | A6 |
| G4.2 | level counts 7 / 8 / 12 | A1 + A6 |
| G4.3 | **3** alias collisions | A5 (×2), A6 (×1) |
| G4.4 | **2** Key Entities with no §9 row | A5, A4b |
| G4.5 | `relation_ref` authoritative on two types | A4b |
| G6.8 | the distinct-type invariant is stated with a count in 2 places, with 2 values | A1 |
| G7.4 | C-2's 1a/1b split is absent | A8prep |
| G7.5 | C-4's persistence hoist is absent | A8prep |
| G7.7 | the 7 sites and 12 enum references have no owning task | A8prep |
| G9.6 | SC-015's "≥ 20" vs §93's 18 field groups; "17 mutations" vs 6 named | A6 |
| G9.8 | the baseline is run once (T001), not re-run at Phase 9's entry | A8prep |

---

## A8prep deliverables checklist

| Deliverable | Section | Status |
|---|---|---|
| O1 line-range ownership map, 5 files, every line assigned once or `UNCHANGED` | O1.1–O1.5 | complete |
| Contested hot spots + deterministic merge rules | O1.6–O1.7 | complete — 16 hot spots (HS-1…HS-16), 13 append anchors, 9 line-scoped carve-outs |
| O2 FR-number allocation map, non-overlapping, with the contested-FR rule set | O2.2–O2.4 | complete — 129 slots, 8 bands, 8 rules, 1 arbitration ladder, 52-orphan closure table |
| O3 rebuilt 10-phase DAG, verified against §110, conflicts reported | O3.1–O3.3 | complete — 10 phases, 12/12 §110 covered, 8 conflicts (C-1…C-8) |
| O3 DAG defect fixes (6 named + 6 found) | O3.4 (D1–D12) | complete — all 12 with measured evidence and a fix |
| O4 the model diagram + every `data-model.md` disagreement | O4.1–O4.2 | complete — 12 items examined, 11 disagreements, 1 clean |
| O5 the integration procedure | O5 (S0–S9) | complete — ordered, mechanical, reversible, with the O2 Rule 6 ladder |
| O6 the gate criteria | O6 (G1–G9) | complete — 87 assertions, 21 currently failing, each with a named owner |



