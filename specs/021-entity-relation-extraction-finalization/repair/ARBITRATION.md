# Integration Arbitration Record — feature 021

**Authority**: this document. **Date**: 2026-09-27 | **Predecessor wave**: `8e3ab478` (8 repair documents)
**Status**: binding on the canonical revision. A repair document that contradicts this record is wrong.

This record resolves the conflicts that arose *between* the eight independent repair documents.
It does not reopen the repairs themselves. Where a repair document and this record disagree,
this record wins; the integrator applies this record and notes the override in the change log.

---

## §0 — Ownership of the canonical revision

| Concern | Sole owner | Others must not |
|---|---|---|
| Global FR numbering | **A8prep** allocation map | invent an FR number locally |
| Phase DAG, phase splits | **A8prep** | propose an alternative split |
| Identity subsystem | **A2** | redefine signature fields, voice normalisation, ordering |
| Mapping semantics | **A4b** | create a second mapping model |
| Type vocabulary, `TypeHypothesis`, `TypeSignal` | **A5** | add a second hypothesis container |
| Migration / schema | **A7** | add columns outside `021` |
| Constitution, lifecycle, provenance boundaries | **A1** | re-judge constitutional compliance |
| FR triage, traceability, acceptance criteria | **A6** | re-triage an FR another owner claimed |
| Machine verification | **A7b** | author normative content |

**A7b is the machine arbiter, not a conceptual author.** It may add checks; it may not decide
what a requirement means.

---

## §1 — FR namespace (gate 1: collision = 0)

**FR-001…FR-100 are NOT renumbered.** The allocation map in `A8prep-ownership-and-dag.md` O2
governs. Confirmed by measurement: all 100 numeric ids are present with zero gaps, so there is
nothing to renumber. The map reduces to 2 folds (`FR-034a`→`FR-035` slot, `FR-039a`→`FR-040`
slot), 1 move (`FR-082`, currently stranded at line 814 after `FR-100` at 781) and 29 appends.

**Consequences of the collision, resolved:**

- `FR-101`/`FR-102` as invented by **both** A2 and A6 are void. A6's §8 extractor FR and A2's
  `PredicateSignature` FR take their **A8prep-allocated** numbers.
- **A2 deliberately skipped FR-103** because it was a live phantom. That instinct was correct and
  the allocation map honours it: no agent may claim `FR-103` until the checker reports it clean.
- Any repair document citing a number outside its allocated band is a defect, not a preference.

---

## §2 — Tombstones (gate 2: zero normative references)

`FR-034a` is **absorbed into `INV-002`** and tombstoned. A tombstone exists for historical
traceability only.

**Rule `TOMBSTONED_FR_MUST_HAVE_ZERO_NORMATIVE_REFERENCES`**: no artefact may cite a tombstoned
FR as a live requirement target. Every such citation is rewritten to `INV-002` or to the
surviving FR that carries the obligation. A8prep's instruction that A4b "should reference
FR-034a" is **overridden**.

Tombstone set, per A6: `FR-058`→`INV-004`, `FR-079`→`FR-078`, `FR-080`→`FR-072`,
`FR-070`→design note, `FR-034a`→`INV-002`.

---

## §3 — `CONFLICTING` vs `CONTRADICTED` (three distinct things, never mixed)

**A6 is forbidden from turning structural disagreement into `CONTRADICTED`.**

| State | Lives on | Means | Trigger |
|---|---|---|---|
| `PredicateHypothesis.resolution_state = CONFLICTING` | the hypothesis | incompatible **semantic** readings of the same structure | two regimes/operators map one signature incompatibly |
| `RelationCandidate.assembly_state` (**NEW**) | the candidate | incompatible **structural** readings of one participant configuration | producers disagree on arity, direction, polarity or role slots |
| `CandidateStatus.CONTRADICTED` | the candidate | the **assertion itself is denied** | a positive reading versus an explicit denial/contradiction |

`CandidateStatus` must not become a dumping ground for the epistemic space again. A structural
conflict that is *not* a denial yields `assembly_state = CONFLICTING`, never
`candidate_status = CONTRADICTED`.

```python
class CandidateAssemblyState(StrEnum):   # NEW, distinct from CandidateStatus
    CONSISTENT = "consistent"
    AMBIGUOUS  = "ambiguous"
    CONFLICTING = "conflicting"
```

**Resolves A2 Q4** (which A4b could not close alone): predicate-level conflict and
candidate-level structural conflict are different axes and are never collapsed.

---

## §4 — `TEMPORAL` (gate 3: one answer)

**`TEMPORAL` is KEPT as a `SignalKind`.** A8prep's "`TEMPORAL` not added" is **overridden**; A7's
position governs and A8prep's 4c adapts.

The distinction is load-bearing:

```text
SignalKind.TEMPORAL  →  "this signal is based on a temporal observation"   (channel)
SourceTemporalObservation / temporal_evidence  →  the temporal facts       (content)
```

`TEMPORAL` is **not** a container of time and carries no temporal payload. It states the
*provenance channel*; the facts live in `SourceTemporalObservation`, which is exactly the
division that keeps `SignalKind` from becoming "an unstructured dumping ground" (§15).

`ck_relation_signal_kind`'s whitelist in `021` therefore **includes** `TEMPORAL`, and A7's
pre-flight for that constraint narrows-with-refusal rather than rewriting it (Principle I).

---

## §5 — Phase DAG (gate 3, second half)

**A8prep owns the DAG.** A6's `4A/4B` is superseded by the single three-way split, which
reflects three genuinely independent risk surfaces rather than a convenient number:

```text
P0  spec / constitution / traceability
P1  identity + PredicateSignature + RoleSignature
P2  type vocabulary + TypeHypothesis substrate
P3  mention binding / occurrence index
P4A additive structural contract          (additive only — committable green)
P4B producer migration                    (7 construction sites, one commit)
P4C enum / lifecycle / corpus cleanup     (deletions + CHECK-constraint drops)
P5  candidate assembly
P6  claim material / validation / admission
P7  InvestigationWorkflow production wiring
P8  graph projection
P9  replay / determinism / golden corpus
```

**One notation only.** `4A/4B/4C` and `4a/4b/4c` must not both appear anywhere.

`P4A` is additive-only precisely so the sequence stays committable: it introduces the variadic
`participants` field and `SignalBasis` **without** removing the binary columns or the
`SignalKind` members. `P4B` migrates the 7 producer construction sites. `P4C` performs the
deletions and drops the obsolete CHECK constraints. This is why the measured breakage is
**2 breaking lines**, not 12 — A8prep's measurement supersedes the earlier figure.

---

## §6 — n-ary persistence (gate 4: lossless, in 021, no split to 022)

**A7's "no participants column in 021, n-ary to 022" is REJECTED.** After P4A the canonical
domain object is n-ary; a persistence layer that cannot hold it losslessly violates the
feature's own `build → store → read → identical object` obligation and breaks User Story 7.

`021` therefore adds, to **both** `relation_signal` and `relation_candidate`:

```text
participants  JSONB NOT NULL      typed structured field, canonical serialisation
```

It is **not** `extra`. `extra` is an untyped escape hatch and reusing it would reproduce the
defect that made n-ary unrepresentable. The canonical serialisation is defined by the identity
subsystem's participant ordering, so a stored `participants` round-trips to an identical
in-memory object and re-derives an identical `signal_id` / `logical_candidate_id`.

`subject_mention_ref` / `object_mention_ref` are **retained as compatibility accessors for
binary records** and become derived from `participants[0]` / `participants[1]`. They are never
a second source of truth.

**No artificial feature split, and no deferral to `022`.**

---

## §7 — `TypeSignal` provenance semantics

`source_vocab` is an **external vocabulary reference or `null`**. It answers *"whose semantic
system said this"*. `producer_ref` / `producer_version` are independent coordinates answering
*"which instrument did we extract it with"*.

```text
schema.org statement   source_vocab = "schema.org"   producer_ref = "jsonld-parser"  version = 1.8.2
regex CVE detector     source_vocab = null           producer_ref = "cve-detector"   version = 3.1.0
```

**No synthetic vocabularies.** `local`, `internal`, `regex`, `ner` MUST NOT be introduced to
avoid a `null`. A detector that reads no external vocabulary has `source_vocab = null`, and the
§8 families that legitimately have no vocabulary (regex, NER, markup) are legal because of it.
This closes A5's OQ-A5-6 as a decision, not an open question. A5's own withdrawn
`TypeSignalSource` enum stays withdrawn: it duplicated `source_vocab` + `producer_ref`.

---

## §8 — Naming: one name per thing

| Concept | Name | Kind |
|---|---|---|
| the pipeline stage | `MENTION_BINDING` | stage |
| the artefact | `MentionOccurrenceIndex` | structure |
| the id form | `MN-…` | id |

`MentionBinding` is **not** a third data-model object. `MentionOccurrenceIndex` is canonical.
This supersedes A8prep's finding that the concept had three names.

**`relation_ref` has exactly one authority**: `PredicateHypothesis.relation_ref` is
authoritative. `RelationCandidate.relation_ref` becomes a **derived** property, for
compatibility with the existing surface area only. Two stored sources of truth for one
reference is precisely the semantic minefield that produces `candidate.relation_ref = A` against
`predicate_hypothesis.relation_ref = B`.

---

## §9 — Evidence lineage ≠ derivation lineage (gate 5)

Fully separated, permanently. A candidate and a signal may be *connected to* the evidence graph,
but they **never become evidence** because derivation passes through them.

```text
EVIDENCE lineage      edge → claim → evidence → observation → capture/raw → source
DERIVATION lineage    edge → claim → candidate → signal → observation
```

Consequences, all binding:

- `evidence_lineage.py` needs **two distinct hop vocabularies**, not one `HopKind` used for both.
  `HopKind` today has **no `SIGNAL` member at all**, so `SC-013` as written was unreachable in
  *both* directions. A1's insight is adopted: the fix is a type-vocabulary defect, not tuple
  ordering, and merely adding `CANDIDATE` to the backward chain would not have fixed it.
- `INV-005` stands: a candidate is derivation, never evidence. `SC-013` is **reformulated as a
  provenance round-trip**, not as an attempt to seat the candidate inside a constitutional
  warrant chain.
- Constitution Principle II (Evidence-First) is satisfied by the *evidence* chain above and is
  not weakened by the candidate's absence from it.

---

## §10 — §8 wording: four different numbers, stated precisely

The repair set had one number doing four jobs. Fix the vocabulary so it cannot be misread again:

| Number | What it counts |
|---|---|
| **31** | foundational entity types (`core:*`) — measured, not 32 |
| **13** | value types (`value:*`) |
| **7** | §8 extraction families / subsections |
| **~4** | new instrument modules actually added |

A5 is the source of the correction: the enumeration in `FR-030` is **31**. The "32" originated
as a miscount in `phase0-results.md` D7 and propagated into the "32 extractors" reading. Both
are corrected.

**`SC-026` and `test_entity_extractor_covers_all_seven_classes` MUST be renamed.** "Seven
classes" is wrong — there are 31 entity classes and 7 extraction families. The word must be
*extraction families* or *§8 subsections*, never *classes*. This is a vocabulary bug that would
otherwise become a 32-extractor mandate within two weeks.

Note also `core:Coordinate` (entity) and `value:Coordinate` (value) are the same label in two
namespaces. Both stay; `kind` becomes a **required, non-defaulted** discriminator field.

---

## §11 — `SC-001`: proven as an algorithm, not yet as a production path (gate 6)

A2's honest position is adopted verbatim and is **not** papered over.

- `SC-001` is **computable**: `normalize_voice()` → canonical argument slots → canonical
  participant ordering → identical `logical_candidate_id` for active and passive realisations.
  A2 supplies the 11-line derivation.
- `SC-001` is **not yet reachable**, because no syntactic producer exists.
- Therefore `SC-001` carries a **`xfail(strict=True)`** marker **now**. Strict is mandatory: it
  makes an accidental pass an error rather than a silent success.
- **A named task owns the transition `xfail → green`**, and that task is the syntactic producer
  per A2's construction table (V0–V6, the 10-row construction coverage from brief §29 — not
  §22, which A2 corrected).
- No implementation wave may report `SC-001` as passing while the marker is still `xfail`.

---

## §12 — Gate conditions for declaring the canonical revision PASS

All must hold, and all must be **machine-verifiable wherever possible**:

| # | Condition | Verified by |
|---|---|---|
| G1 | FR namespace collision = 0 | checker RI-01/RI-02 |
| G2 | Zero normative references to tombstoned FRs | checker `TOMBSTONED_FR_*` (new) |
| G3 | `TEMPORAL` and the Phase-4 model have exactly one answer | checker RI-09 count checks + manual |
| G4 | n-ary `participants` has a lossless, typed persistence representation in `021` | A7 DDL + round-trip test |
| G5 | Evidence lineage ≠ derivation lineage, two hop vocabularies | A1/A2 + `evidence_lineage.py` test |
| G6 | `SC-001` carries `xfail(strict=True)` and a named task owns the transition | checker + `tasks.md` |

Plus the standing gates: the checker's overall verdict must reach **0 FAIL** on the canonical
revision, with every one of the 25+ check ids present in the summary so a check that silently
stopped running cannot hide.

---

## §13 — Change log for the integrator

Every override this record applies, to be recorded when the canonical revision is built:

1. A2's and A6's `FR-101`/`FR-102` both void; replaced by the A8prep allocation.
2. A8prep's "A4b should reference `FR-034a`" **overridden** — tombstone has zero normative refs.
3. A6's structural-conflict → `CONTRADICTED` **forbidden**; new `CandidateAssemblyState`.
4. A8prep's "TEMPORAL not added" **overridden** — TEMPORAL kept as a channel.
5. A6's `4A/4B` superseded by A8prep's `4A/4B/4C`; one notation only.
6. A5's OQ-A5-6 **closed**: `source_vocab = external | null`, no synthetic vocabularies.
7. `MentionBinding` fixed as a stage, not a third object.
8. `PredicateHypothesis.relation_ref` is the sole authority; candidate's becomes derived.
9. A7's "participants in 022" **rejected**; typed `participants` JSONB goes in `021`.
10. A8prep's "12 enum references" corrected to **2 breaking lines** (this is why 4A/4B/4C is green).
11. "32 types" corrected to **31**; "seven classes" renamed to "seven extraction families".
12. `A5` OQ-A5-6 withdrawn-as-open; A2 Q4 closed by §3.

---

## §14 — DEFINITIVE FR ALLOCATION (supersedes §1's deferred instruction)

**§1's instruction was unsatisfiable and is withdrawn.** It said every agent's new FRs "take
their A8prep-allocated numbers", but A8prep O2.3 allocated **no band at all to A2 or A6** and
**only 6 usable slots to A1's 13 requirements**. Measured result: **41 FR numbers were cited
but never defined** — `101–109`, `116`, `129–160`. That is the integration blocker, and it is
arithmetic, not conceptual.

### Allocation

| Owner | Band | Count | Covers |
|---|---|---|---|
| A7b | `FR-115` | 1 | reference integrity — **already applied** |
| — | `FR-101…FR-109` | — | **VOID / RESERVED.** `101`/`102` collided (A2 vs A6) and are void; `103` is the historical phantom; `104–109` never allocated. **Nothing may claim these.** |
| — | `FR-116…FR-129` | 14 | **RESERVED, unused.** Deliberately empty so a later wave has room without colliding. |
| A4b | `FR-130…FR-137` | 8 | mapping layer. Agent's own band, **kept as-is** |
| A5 | `FR-140…FR-149` | 10 | type vocabulary + §8 extraction families. Agent's `158`/`159` **fold into this band** — they collided with A7's |
| A7 | `FR-150…FR-160` | 11 | migration / schema. Agent's band, **kept as-is** |
| A1 | `FR-161…FR-173` | 13 | constitution / lifecycle / provenance |
| A2 | `FR-174…FR-178` | 5 | identity subsystem |
| A6 | `FR-179…FR-180` | 2 | §8 extractor families FR + the prohibition-coverage meta-rule |

Total: **49 new normative FRs**, plus the 4 tombstones and 5 already-live `FR-110…FR-115`.

### Binding rules

1. **No agent may invent an FR number.** If a requirement has no band slot, it is reported, not
   numbered. This is the rule that makes `FR-103` unrepeatable.
2. **The band is the contract.** A2's `FR-101/102/104/105/106` **become** `FR-174…FR-178`.
   A6's `FR-101/102` **become** `FR-179/180`. A1's `FR-101…FR-113` **become** `FR-161…FR-173`.
   A5's `FR-158/159` **become** `FR-148/149`. A4b's and A7's numbers do not move.
3. `FR-110…FR-114` (A5, A7, A7b) stay as applied. If A5's `FR-111/112` and A7's `FR-113`
   duplicate an A5/A7 `140…`/`150…` subject, the **`110…` number is the survivor** and the
   `140…`/`150…` slot goes to a requirement the applied one does not cover. No subject may
   appear twice under two numbers.
4. **The `A5`/`A6` split**: A6's `FR-179` is the §8 obligation A5's `FR-030`/`FR-031` was
   *provisionally* carrying (the spec integrator folded it there to clear a FAIL — that was a
   deviation and is now unwound). The vocabulary is what `FR-140…149` defines; the *obligation
   to produce evidence for it* is `FR-179`. Both are needed; they are different claims.
5. The `[INTERFACE]` items A6 flagged remain undecided and are **not** numbered: the
   `MENTION-` vs `MN-` prefix, and the three conflicting `RelationParticipant` field lists.
   ARBITRATION §8 settles the id form as `MN-`; the field list belongs to A2's band.
6. Every one of the 49 must be applied to `spec.md` verbatim from its owner's repair document.
   "Not applied" is a gate failure, not an acceptable outcome with a note attached.
