# A7 — Migration `021`: DDL, constraint replacement, tests, downgrade

**Job**: A7 — MIGRATION 021
**Feature**: 021-entity-relation-extraction-finalization
**Repo root**: `C:\Users\tim\Desktop\COGNITIVE\1` (not the parent directory)
**Date**: 2026-09-27 | **HEAD**: `0056665`
**Files written by this job**: this file only. No existing file was edited. No migration was
run and no database was contacted.

Ten decisions follow (D1–D10), each grounded in quoted source.

---

## 0. Scope, and the finding that reorganises the job

The finding that drives all ten decisions is **K6**, and D1/D2 restate it precisely because
the artefacts state it loosely.

`phase0-results.md` §4.3 K6, verbatim:

> **Migration `021` is specified to ADD columns only.** It must also **DROP**
> `ck_relation_signal_asserts_something` and `ck_relation_candidate_asserts_something`,
> which enforce `relation_surface <> '' OR relation_ref IS NOT NULL` — the constraint
> `FR-013` says MUST be replaced — and must update `ck_relation_signal_kind`'s whitelist
> for the removed `SignalKind` members. No artefact says so, so `SC-012` is unachievable as
> planned

K6 is correct. Three things about it need sharpening before it can be scheduled, and all
three change the work:

1. **"ADD columns only" is false in a second way nobody has recorded.** `SC-012` requires a
   co-occurrence signal to be *assemblable*. A candidate assembled only from co-occurrence
   signals has an empty `relation_surface`, no `relation_ref` and — per `data-model.md` §3,
   `predicate_signature: PredicateSignature | None` — no signature. Under
   `ck_relation_candidate_asserts_something` such a candidate is **also unstorable**. The
   candidate-side constraint blocks `SC-012` just as much as the signal-side one, and the
   two replacement rules are **not the same rule** (D2).
2. **"the same predicate" describes today, not the replacement.** The two constraints do
   carry the same text at `020_universal_relation_extraction.py:157-158`, but a signal has a
   `signal_kind` and a candidate has none, so no single replacement predicate can serve
   both (D2.2, D2.3).
3. **A fourth operation is required that K6 does not name: a new column.**
   `020`'s `ck_relation_signal_asserts_something` cannot be replaced by a rule about
   "observational basis" unless the basis is *nameable*, and no column records it. Brief
   §16 (`input.md:1119-1137`) requires "every signal must have an explicit observational
   basis" and names the vocabulary. `021` must therefore **add `observational_basis`**, whose
   domain type does not exist. K6 lists three constraint operations; there are four schema
   operations, and one of them is a column no artefact mentions.

**Where I disagree with the job's framing.** The brief for this job says the two
constraints "enforce the same predicate" and asks for "the replacement" (singular). I
specify **two different replacement rules** and justify the divergence in D2. Any
implementation that writes one predicate into both tables is wrong, and `FR-013`'s own
wording is about the *signal* only (`spec.md:421-424`); the candidate rule has to be
derived, not copied.

---

## 1. Evidence base

| Source | Used for |
|---|---|
| `apps/control-plane/db/migrations/versions/020_universal_relation_extraction.py` (407 lines) | D1–D4, D8 |
| `apps/control-plane/db/schema.py` (2523 lines) | D1, D3, D5 |
| `apps/control-plane/db/relation_claim_store.py` (558 lines) | D5 |
| `apps/control-plane/tests/unit/test_migration_020_universal_relation.py` (326 lines) | D6 |
| `apps/control-plane/tests/unit/test_migration_forward_only.py` (140 lines) | D6, D7 |
| `apps/control-plane/tests/integration/test_orm_migration_parity.py` (117 lines) | D6 |
| `specs/021-…/spec.md` | FR-059/060/062/087/088/097, `SC-012` |
| `specs/021-…/data-model.md` §2, §3, §5, §7 | D1, D3, D10 |
| `specs/021-…/research.md` R-005 | D5, D6, D10 |
| `specs/021-…/phase0-results.md` §2, §4.3 K6 | D1, D8 |
| `specs/021-…/checklists/requirements.md` H1–H11, C2 | D3, D9, D10 |
| `input.md` §13, §15, §16, §40, §58, §59, §62, §91 | D2, D5, D6 |
| `.specify/memory/constitution.md` I, II, VII, Additional Constraints, Governance | D4, D7 |

### 1.1 Verified facts used

- **Head**: no file in `versions/` declares `down_revision = "020_…"`. The chain is
  `None → 014 → 015 → 016 → 017 → 018 → 019 → 020`, single head `020`.
- **`020` MUST NOT be edited.** Its refusal (`020:376-407`), verbatim:
  > "So a downgrade would be the only operation in the platform able to remove a
  > consideration, on the strength of a schema version number. That is worse than having no
  > reverse at all. **Rolling back is a forward operation: add revision 021 that states what
  > the schema becomes instead.**"
- **`020`'s constraints**, verbatim from `020:153-158`:
  ```python
  #: The one direction a stated-predicate check may refuse. A reading may name an operator
  #: and no surface; it may not be a surface with nothing saying whether it resolved. The
  #: reverse - a row asserting no predicate at all - is refused by the value type, and the
  #: database's job is only to catch a loader that skipped it.
  _CANDIDATE_ASSERTS = "relation_surface <> '' OR relation_ref IS NOT NULL"
  _SIGNAL_ASSERTS = "relation_surface <> '' OR relation_ref IS NOT NULL"
  ```
  applied at `020:268` (`ck_relation_signal_asserts_something`) and `020:334`
  (`ck_relation_candidate_asserts_something`).
- **`020`'s kind whitelist**, `020:103-117`, 13 literals, applied at `020:276`
  (`ck_relation_signal_kind`).
- **`020`'s justification for re-asserting Python refusals in DDL**, `020:144-147`, verbatim:
  > "the duplication is the point: a constraint that exists only in Python is a constraint a
  > ``COPY`` walks straight past."
- **ORM/migration duplication is deliberate**, `schema.py:13-22`, verbatim:
  > "This is the opposite stance from ``db/migrations/versions/020_universal_relation_extraction.py``,
  > and the difference is deliberate rather than inconsistent: *application* code should
  > follow the value type, because when the value type gains a member the fresh-install path
  > must gain the CHECK with it or the two install paths diverge. A *migration* must not
  > import it, because a revision that reads a value type changes meaning when somebody edits
  > that type, and a database that already ran the revision cannot be re-run. So the
  > literals live in the migration and the references live here, and
  > `tests/unit/test_migration_020_universal_relation.py` asserts the two agree - which is
  > the only way a deliberate duplication stays honest."
- **`relation_claim` has no verdict column.** `schema.py:1169-1229` is the full column set;
  `CLAIM_JSONB_COLUMNS` (`relation_claim_store.py:27-35`) is the exhaustive set of its JSONB
  columns. `relation_claim_revision` (`schema.py:1240-1254`) has no JSONB at all.
- **`validation_findings` has no relation/candidate column** — `schema.py:1550-1567`; the
  only subject pointer is `assertion_ref: Mapped[str] = mapped_column(String(64))`.
- **`RelationClaim.candidate_id` already exists in the domain and is identity-bearing**:
  `domain/relation_claim.py:199` (`candidate_id: str = ""`) and it is in `_material()` at
  `domain/relation_claim.py:411`, therefore inside `content_hash` (`:297-304`).
- **`RelationSignal` has `direction` but no `polarity`** (`extractors/signals/signal.py:290`);
  **`RelationCandidate` has neither** (`domain/relation_candidate.py:586-661`).
- **`PredicateSignature`, `Polarity`, `SignalBasis`, `RelationParticipant` do not exist in
  the code at all.** `Polarity` and `PredicateSignature` are declared NEW in
  `data-model.md` §1/§5; `SignalBasis` is named by **no** artefact.
- **`020`'s digest** (newline-normalised, as `test_migration_forward_only.py:53-60` does):
  `068c6fc3378ceeee3f9bdf5bb348b620a6dcfe80227c959f79e3792d8024f0a8` for
  `020_universal_relation_extraction.py`, computed at HEAD `0056665` for this job.

---

## D1 — The complete `021` DDL

### D1.0 Shape of the revision

```text
revision       = "021_relation_extraction_finalization"
down_revision = "020_universal_relation_extraction"
file           = apps/control-plane/db/migrations/versions/021_relation_extraction_finalization.py
```

**`021` creates no table.** It is: **23 added columns, 6 added indexes, 3 replaced CHECK
constraints, 0 new tables, 0 backfills, 0 row-editing operations.** A new table is required
only under D5 option (a2), which I recommend deferring. Stating this explicitly matters
because every artefact currently says "adds", implying a shape nobody has checked.

Ordering inside `upgrade()`, following `016_relation_evidence_graph.py`'s stated discipline
("create tables, add columns, backfill, then create indexes. **No index is ever built
against a column that does not exist yet**"):

```python
def upgrade() -> None:
    _add_relation_signal_columns()      # 9 columns
    _replace_signal_constraints()       # DROP 2, CREATE 4  (needs observational_basis)
    _add_relation_candidate_columns()   # 11 columns
    _replace_candidate_constraint()     # DROP 1, CREATE 3
    _add_relation_claim_columns()       # 2 columns
    _add_validation_finding_column()    # 1 column  (D5.4)
    _add_indexes()                      # 6 indexes, all after their columns exist
```

**42 `op.` calls in total: 23 `add_column`, 3 `drop_constraint`, 7
`create_check_constraint`, 6 `create_index`, and `downgrade()`'s bare `raise`.** The full
operation-by-operation table is §4.

Every `op.add_column` is called with **no extra keyword arguments**. This is worth stating
because the instinct imported from `020` is wrong: `020`'s `existing_type=` appears on
`op.alter_column` (`020:177-183`), and `Operations.add_column` does **not** accept
`existing_type` / `existing_nullable` — those are `alter_column` parameters. Passing them to
`add_column` is a `TypeError` at migration time, not a style question. `021` adds no
`alter_column` call at all, so the question does not arise. P3 asserts the documented
signature is used.

### D1.1 `relation_signal` — 9 added columns

| # | Column | Type | Null | Server default | Classification |
|---|---|---|---|---|---|
| 1 | `predicate_signature_key` | `sa.String(64)` | nullable | **none** | **identity-bearing** — the presence marker, and the term a candidate's signature match is keyed on |
| 2 | `predicate_normalized` | `sa.Text()` | nullable | **none** | **identity-bearing** — component of the signature |
| 3 | `predicate_arity` | `sa.Integer()` | nullable | **none** | **identity-bearing** — declared argument count |
| 4 | `predicate_roles` | `postgresql.JSONB(astext_type=sa.Text())` | nullable | **none** | **identity-bearing** |
| 5 | `predicate_argument_shapes` | `postgresql.JSONB(astext_type=sa.Text())` | nullable | **none** | **identity-bearing** |
| 6 | `predicate_polarity` | `sa.String(16)` | nullable | **none** | **identity-bearing** — asserted/denied/uncertain |
| 7 | `predicate_alternatives` | `postgresql.JSONB(astext_type=sa.Text())` | nullable | **none** | **revision material** — inside `PredicateHypothesis.content_key` (`domain/predicate_hypothesis.py:273-284`) |
| 8 | `predicate_mapping_evidence` | `postgresql.JSONB(astext_type=sa.Text())` | nullable | **none** | **revision material** — same |
| 9 | `observational_basis` | `sa.String(24)` | nullable | **none** | **basis attestation** — the subject of the replaced constraint |

```python
_SIGNAL_COLUMNS: tuple[tuple[str, object], ...] = (
    ("predicate_signature_key",     sa.String(64)),
    ("predicate_normalized",        sa.Text()),
    ("predicate_arity",             sa.Integer()),
    ("predicate_roles",             postgresql.JSONB(astext_type=sa.Text())),
    ("predicate_argument_shapes",   postgresql.JSONB(astext_type=sa.Text())),
    ("predicate_polarity",          sa.String(16)),
    ("predicate_alternatives",      postgresql.JSONB(astext_type=sa.Text())),
    ("predicate_mapping_evidence",  postgresql.JSONB(astext_type=sa.Text())),
    ("observational_basis",         sa.String(24)),
)

def _add_relation_signal_columns() -> None:
    for name, type_ in _SIGNAL_COLUMNS:
        # No ``existing_type``: that is an ``alter_column`` parameter and
        # ``Operations.add_column`` does not accept it. 021 issues no alter_column.
        op.add_column("relation_signal", sa.Column(name, type_, nullable=True))
```

Justifications, column by column, because a width without a reason is a decision nobody can
re-check (the standard `020` sets for `_ID_WIDTH` at `020:79-84`):

- **`predicate_signature_key` = 64.** The value is `content_key(...)` =
  `digest128(...)` = **32 lowercase hex characters** (`domain/relation_identity.py:115-117`).
  64 is the platform's digest-column width (`020:84`), used verbatim at `020:247`. Reason
  quoted from `020:79-84`:
  > "64 rather than 37 because a column sized to today's exact address is a column that has to
  > be migrated the first time a digest gets wider or a prefix gets a character, and a
  > migration is a place where somebody can be wrong. A too-wide column costs a few bytes a
  > row; a too-narrow one silently corrupts an address."
- **`predicate_normalized` = `Text`, not `String(n)`.** It is identity material, and a
  too-narrow identity column silently corrupts an address — the failure `020:79-84` names.
  `020`'s precedent for the raw form is `relation_surface: sa.Text()` (`020:246`); the
  normalised form must be at least as safe as the raw one. No index is required on it (D4).
- **`predicate_arity` nullable, no default.** It must be nullable because the
  whole-or-absent rule (D2.3) requires *all* signature components to be null together; a
  `NOT NULL` column with `server_default="0"` cannot be. It needs no default because
  `ADD COLUMN … NULL` without a default is the only form that requires no backfill.
- **The four JSONB columns use `astext_type=sa.Text()`.** `020` uses
  `postgresql.JSONB(astext_type=sa.Text())` wherever it declares JSONB (`020:254-258`) while
  `schema.py:2397` declares bare `JSONB`. The `astext_type` affects the compiled
  `CreateTable`, so a parity test comparing `_type_signature` would otherwise report a
  difference. **The ORM side must be aligned in the same commit as 021** — see D6.5. Role
  names and argument shapes are **ordered** (their length equals `predicate_arity`), so they
  are JSONB arrays, not sets: order is identity.
- **`predicate_polarity` = `String(16)`.** Members `asserted` (8), `denied` (5),
  `uncertain` (9). Matches the terse width of `predicate_state: sa.String(16)` (`020:248`).
- **`observational_basis` = `String(24)`.** Longest member is `predicate_text` /
  `metadata_field` (14 characters). 24 matches `temporal_axis` / `basis` (`020:192,196`).

**`predicate_direction` is deliberately NOT added to `relation_signal`.** `data-model.md` §7
lists it, and it would duplicate the existing `direction: sa.String(24)` column (`020:244`),
which is `NOT NULL` and already carries a closed-vocabulary CHECK (`020:277-279`,
`schema.py:2442`). Two columns for one fact are two columns that can disagree, and a
disagreement here is undetectable. The signature's direction **is**
`relation_signal.direction`; the DDL therefore adds no direction column, and the
whole-or-absent CHECK exempts it. Disagreement with `data-model.md` §7 line 253; replacement
text in D10.1.

### D1.2 `relation_candidate` — 11 added columns

| # | Column | Type | Null | Server default | Classification |
|---|---|---|---|---|---|
| 1 | `predicate_signature_key` | `sa.String(64)` | nullable | none | **identity-bearing** — the replacement for `relation_surface` in `logical_candidate_id` |
| 2 | `predicate_normalized` | `sa.Text()` | nullable | none | **identity-bearing** |
| 3 | `predicate_arity` | `sa.Integer()` | nullable | none | **identity-bearing** |
| 4 | `predicate_roles` | `postgresql.JSONB(astext_type=sa.Text())` | nullable | none | **identity-bearing** |
| 5 | `predicate_argument_shapes` | `postgresql.JSONB(astext_type=sa.Text())` | nullable | none | **identity-bearing** |
| 6 | `direction` | `sa.String(24)` | nullable | none | **identity-bearing** — serves **both** FR-088's `direction` and the signature's direction; one column, not two |
| 7 | `polarity` | `sa.String(16)` | nullable | none | **identity-bearing** — serves **both** FR-088's `polarity` and the signature's polarity |
| 8 | `confidence` | `sa.Float()` | **NOT NULL** | `sa.text("0.5")` | **mutable projection field** — never identity |
| 9 | `signal_refs` | `postgresql.JSONB(astext_type=sa.Text())` | nullable | none | **revision material** — FR-085: canonicalised, and inside `candidate_id` |
| 10 | `predicate_alternatives` | `postgresql.JSONB(astext_type=sa.Text())` | nullable | none | **revision material** |
| 11 | `predicate_mapping_evidence` | `postgresql.JSONB(astext_type=sa.Text())` | nullable | none | **revision material** |

- **`direction` and `polarity` are nullable**, unlike `relation_signal.direction`
  (`020:244`, NOT NULL). A candidate's signature is optional (`data-model.md` §3), so a
  candidate with no signature has no direction and no polarity, and a `NOT NULL` column would
  force a fabricated `ambiguous` into an unsigned row. `data-model.md` §5 records the same
  fact from the other side:
  > "`polarity` is not a column on any table (it is a derived local in `assembly.py` only). A
  > negated candidate and an asserting candidate over the same pair are currently
  > indistinguishable after a round trip."
- **`confidence` defaults to `0.5`, not `0`.** `relation_signal.producer_confidence` defaults
  to `0` (`020:260`) because a producer's confidence starts at nothing. A **candidate's**
  confidence defaults to `domain.temporal_worldline.DEFAULT_CONFIDENCE = 0.5`
  (`domain/temporal_worldline.py:39`, consumed at `domain/relation_candidate.py:653`), and
  I-3 ("unknown != certain") forbids a defaulted `0`. It is also `relation_claim.confidence`'s
  twin, which already defaults to `0.5` (`schema.py:1196`).
- **`signal_refs` is JSONB**, matching `observation_refs`/`evidence_refs` on the same table
  (`020:317-318`, `schema.py:2305-2306`), not a native `ARRAY`. A third ref-list in a
  different type on one row is a reader's problem. **Cost, stated honestly:** a JSONB list is
  not indexable for containment without `btree_gin` (D4.3), whereas an `ARRAY` would be. The
  reason I still choose JSONB is that D4.3 shows the containment lookup is not the read that
  matters.
- **`signal_refs` is revision material, and that is currently unstated.** At HEAD
  `domain/relation_candidate.py:625` declares the field and `_material()` (`:1180-1205`) does
  **not** include it — and neither does `CANDIDATE_LOGICAL_MATERIAL_FIELDS` (`:513-523`), so
  it is in *neither* set. FR-085 requires canonicalisation; where it lands in the material
  split is the identity repair job's decision, and `021` must record the answer in its
  docstring, because a column that is identity-bearing in the code and absent from the row is
  FR-088's "No field that participates in an id may be absent from the row" being violated
  silently.
- **No `participants` column, and no change to `subject_mention_ref`/`object_mention_ref` or
  to `ck_relation_candidate_distinct`** (`020:331-333`). Deferred to `022`, for a
  constitutional reason rather than convenience: brief §13 makes `participants` canonical,
  but the existing CHECK and `ix_relation_candidate_pair` are defined over the binary shape,
  and *widening* them means rewriting rows that hold observations. Principle I
  (`.specify/memory/constitution.md:6`):
  > "Every observation is immutable once recorded. … Nothing downstream may edit an
  > observation."

  So `022` **adds** `participants` and retires the binary CHECKs forward, leaving the binary
  columns in place as the compatibility accessors §13 permits. `021` states this deferral in
  its docstring so the omission reads as a decision — `016`'s stated standard: "Sections 2 and
  3 are recorded no-ops rather than dropped, so a reader of the file … can see that 'nothing
  to add' is a decision and not an omission."

### D1.3 `relation_claim` — 2 added columns

| # | Column | Type | Null | Server default | Classification |
|---|---|---|---|---|---|
| 1 | `candidate_id` | `sa.String(64)` | **NOT NULL** | `""` | **identity-bearing** — already inside `_material()`, therefore inside `content_hash` |
| 2 | `validation_record` | `postgresql.JSONB(astext_type=sa.Text())` | nullable | **none** | **decision metadata** — deliberately *outside* `_material()` (D5.1) |

```python
op.add_column(
    "relation_claim",
    sa.Column("candidate_id", sa.String(64), nullable=False, server_default=""),
)
op.add_column(
    "relation_claim",
    sa.Column("validation_record", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
)
```

- **`candidate_id` is NOT NULL with `server_default=""`, and that is the *faithful* choice,
  not the "silent substitution" `schema.py:1211-1219` warns about.** The domain declares
  `candidate_id: str = ""` (`domain/relation_claim.py:199`) — `""` is the type's own way of
  saying "no originating candidate was stated", so a server default of `''` reproduces the
  type rather than inventing a value. The asymmetry `schema.py:1211-1219` records is about
  `regime_id`, which is NOT NULL **and has no default**, because a claim there is *always*
  built from a candidate:
  > "NOT NULL and with **no** server default, which is the one asymmetry with
  > `candidates.regime_id` in this revision and is deliberate on both sides. … a default
  > would let a claim that named no regime be stored as though it had, which is the silent
  > substitution FR-016 forbids."

  For `candidate_id` the honest pairing is the opposite one, and `''` is distinguishable from
  a real id in a way a fabricated id is not.
- **Width 64**, for the same measurement `020:31-43` records: `CNDR-` + 32 hex = 37
  characters, which overflows `VARCHAR(36)`. `020` already took the measurement; `021` reuses
  it rather than deriving a narrower number.
- **No CHECK on `relation_claim.candidate_id`.** `candidate_id <> ''` is not a constitutional
  invariant, and `input.md:2823` says: "add explicit CHECKs only where they encode
  constitutional invariants". Stated as a test instead (D6.3, R7).
- **`validation_record` is NOT in `_material()`, and a test must assert it stays out**
  (D6.3, R8). The verdict is written *after* the claim exists; if it entered `content_hash`
  then recording a verdict would mint a new `relation_id` and silently fork the revision
  chain — precisely the substitution `schema.py:1211-1219` describes for a defaulted regime.

### D1.4 `validation_findings` — 1 added column (D5.4)

| # | Column | Type | Null | Server default | Classification |
|---|---|---|---|---|---|
| 1 | `candidate_id` | `sa.String(64)` | nullable | **none** | **attachment** — the subject pointer when a finding is about a candidate rather than an assertion |

`validation_findings.assertion_ref` is `NOT NULL` with **no default** (`018:192`,
`schema.py:1554`), so a candidate-stage finding cannot be routed through it without
fabricating a value. Nullable, no default, no CHECK.

### D1.5 Domain-type dependencies — the ordering that must be fixed

`021` cannot be written before the value types exist, and the reason is the *ORM* path, not
the migration path. The migration writes literals (correctly — `020:66-69`: "Written as a
literal rather than imported, because a migration that reads a value type is a migration
whose meaning changes when that type is edited"); the ORM imports the enum
(`schema.py:23-27`). A CHECK written against an enum that does not exist cannot be mirrored,
and a column whose writer does not exist produces exactly the defect this feature exists to
fix, quoted from `spec.md:803`:

> | `relation_signal` / `relation_candidate` / `source_temporal_observation` | **no repository, writer or reader at all** | The three tables 020 created are written by nothing |

**`021` that adds 23 columns no code writes reproduces that defect at a larger scale.** So
the ordering is a hard dependency, not a preference:

| Column(s) | Requires | Exists at HEAD? | Blocking task |
|---|---|---|---|
| 1–6 on both tables | `domain.PredicateSignature` (`data-model.md` §1) | **no** | identity-types job (T006/T029) |
| 6–7, `predicate_polarity` | `Polarity` (`data-model.md` §5) | **no** | polarity job (T024) |
| 9 `observational_basis` | **`SignalBasis` — named by no artefact** | **no** | **new; must be created by this repair** |
| `direction`/`polarity` on `relation_candidate` | `RelationCandidate.direction`, `.polarity` **fields** | **no** — absent from `domain/relation_candidate.py:586-661` | candidate job (T005/T006) |
| `signal_refs` | FR-085 canonicalisation on construction | field exists (`relation_candidate.py:625`); canonicalisation does not | T005 |
| `relation_claim.candidate_id` | store writes/reads it | domain field **exists** and is in `_material()` (`:199`, `:411`) | T052 (store only) |
| `predicate_alternatives`, `predicate_mapping_evidence` | `PredicateHypothesis.alternative_refs` / `.mapping_evidence_refs` | **fields exist** (`domain/predicate_hypothesis.py:141,143`); no columns | T053 |
| participants | `RelationParticipant` (`data-model.md` §2) | **no** | **deferred to 022** (D1.2) |

**`SignalBasis` is the ordering defect this job found.** It is a new closed vocabulary of 9
members taken verbatim from `input.md:1125-1137`; it is the subject of a replacement CHECK
that FR-013/FR-014 require; and **no artefact mentions it**. Task T051 must move after the
signal-contract tasks, and `spec.md` must gain the requirement (D9, FR-151).

---

## D2 — Constraints to DROP, with replacement

### D2.1 The three constraints, exactly as they exist

| Table | Name | Declared at | Exact SQL text |
|---|---|---|---|
| `relation_signal` | `ck_relation_signal_asserts_something` | `020:268` | `relation_surface <> '' OR relation_ref IS NOT NULL` |
| `relation_candidate` | `ck_relation_candidate_asserts_something` | `020:334` | `relation_surface <> '' OR relation_ref IS NOT NULL` |
| `relation_signal` | `ck_relation_signal_kind` | `020:276` | `signal_kind IN ('lexical', 'link', 'reference', 'table', 'list', 'metadata', 'attribute', 'hierarchy', 'schema', 'co_occurrence', 'coreference', 'quantity', 'negation')` |

(`_in()` at `020:161-164` renders a whitelist as `column IN ('a', 'b', …)`.)

### D2.2 The brief's basis, quoted

`input.md:1111-1137` (§16), verbatim:

> Therefore remove any database/domain invariant of:
>
> ```text
> relation_surface != "" OR relation_ref != NULL
> ```
>
> when it makes CO_OCCURRENCE structurally impossible.
>
> Replace it with:
>
> ```text
> every signal must have an explicit observational basis
> ```
>
> The basis may be:
>
> ```text
> predicate text
> DOM relation
> table slot
> hyperlink
> citation
> proximity
> metadata field
> event frame
> attribute key
> ```
>
> Unknown relation semantics are valid.

`input.md:2113-2135` (§40), verbatim:

> Never convert:
>
> ```text
> CO_OCCURRENCE
> ```
>
> to:
>
> ```text
> related_to
> ```
>
> automatically.
> …
> It is not an asserted relation.

`input.md:930-948` (§13), verbatim:

> Legacy properties:
>
> ```python
> subject_mention_ref
> object_mention_ref
> ```
>
> may remain as compatibility accessors for binary relations, but must be derived from
> participants.

**§13 is why the candidate rule cannot reuse the signal rule.** A signal is an observation
and has a channel; a candidate is an assembled reading and has no channel. Any replacement
mentioning `co_occurrence` is unrepresentable on `relation_candidate`.

### D2.3 The three DROP + CREATE pairs, verbatim

**All three DROPs use `op.drop_constraint`, not raw `op.execute`.** `drop_constraint` is
recorded in the Alembic operation log and is checkable by the offline recorder
(D6.1, P7/P8); an `op.execute` string is opaque to any offline parity assertion. `020` uses
no raw `op.execute`, and keeping that property is what lets the whole revision be verified
offline.

```python
# ---- relation_signal ------------------------------------------------------------------

#: The nine bases §16 names, written out rather than imported, for the reason
#: ``020_universal_relation_extraction.py:66-69`` gives.
_OBSERVATIONAL_BASES_021 = (
    "predicate_text",
    "dom_relation",
    "table_slot",
    "hyperlink",
    "citation",
    "proximity",
    "metadata_field",
    "event_frame",
    "attribute_key",
)

#: Four independent grounds. The second and third are the old predicate verbatim, which is
#: what makes this a strict superset and therefore safe against every stored row.
_SIGNAL_ASSERTS_SOMETHING_021 = (
    "observational_basis IS NOT NULL"
    " OR relation_surface <> ''"
    " OR relation_ref IS NOT NULL"
)

#: The narrowing rule. It bites only when the basis is *predicate text*, so a signal whose
#: basis is proximity, a table slot or a hyperlink may have an empty surface.
_SIGNAL_BASIS_PREDICATE_021 = (
    "observational_basis IS DISTINCT FROM 'predicate_text'"
    " OR relation_surface <> ''"
    " OR relation_ref IS NOT NULL"
)

#: The closed vocabulary, nullable-tolerant. A NULL basis is a row written before 021 and is
#: legal, so the membership test is conditional on presence.
_SIGNAL_BASIS_VOCABULARY_021 = (
    "observational_basis IS NULL OR "
    + _in("observational_basis", _OBSERVATIONAL_BASES_021)
)


def _replace_signal_constraints() -> None:
    op.drop_constraint(
        "ck_relation_signal_asserts_something", "relation_signal", type_="check"
    )
    op.create_check_constraint(
        "ck_relation_signal_asserts_something",
        "relation_signal",
        _SIGNAL_ASSERTS_SOMETHING_021,
    )
    op.create_check_constraint(
        "ck_relation_signal_predicate_text_basis",
        "relation_signal",
        _SIGNAL_BASIS_PREDICATE_021,
    )
    op.create_check_constraint(
        "ck_relation_signal_observational_basis",
        "relation_signal",
        _SIGNAL_BASIS_VOCABULARY_021,
    )
    op.create_check_constraint(
        "ck_relation_signal_signature_whole",
        "relation_signal",
        _SIGNAL_SIGNATURE_WHOLE_021,
    )
```

```python
# ---- relation_candidate ----------------------------------------------------------------

#: Four grounds: the two the old check had, verbatim, plus the signature and the observation
#: set. A candidate assembled from co-occurrence signals alone has neither a surface nor a
#: ref, and is exactly what SC-012 says must be assemblable.
_CANDIDATE_ASSERTS_SOMETHING_021 = (
    "relation_surface <> ''"
    " OR relation_ref IS NOT NULL"
    " OR predicate_signature_key IS NOT NULL"
    " OR (signal_refs IS NOT NULL AND jsonb_array_length(signal_refs) > 0)"
)

#: A signature is present or wholly absent. There is no half-written signature, and
#: ``direction`` is exempt because it is the one component already NOT NULL on this table.
_CANDIDATE_SIGNATURE_WHOLE_021 = (
    "(predicate_signature_key IS NULL) ="
    " (predicate_normalized IS NULL AND predicate_arity IS NULL"
    "  AND predicate_roles IS NULL AND predicate_argument_shapes IS NULL"
    "  AND direction IS NULL AND polarity IS NULL)"
)

#: The same rule on the signal side, minus ``direction``.
_SIGNAL_SIGNATURE_WHOLE_021 = (
    "(predicate_signature_key IS NULL) ="
    " (predicate_normalized IS NULL AND predicate_arity IS NULL"
    "  AND predicate_roles IS NULL AND predicate_argument_shapes IS NULL"
    "  AND predicate_polarity IS NULL)"
)


#: The four direction hypotheses, re-declared rather than imported, for the same reason the
#: bases are. ``021`` must assert in its own test that these equal both ``020._DIRECTIONS``
#: and ``DirectionHypothesis``; a re-declaration is a duplication that can rot, and the test
#: is what stops it.
_DIRECTIONS = (
    "subject_to_object",
    "object_to_subject",
    "undirected",
    "ambiguous",
)

#: The three polarities, written out. The narrowing rule is conditional on non-null because
#: a candidate's signature is optional (data-model.md §3), so both columns are nullable and
#: the vocabulary is asserted only when a value is present.
_POLARITIES = ("asserted", "denied", "uncertain")

_CANDIDATE_DIRECTION_VOCABULARY = (
    "direction IS NULL OR " + _in("direction", _DIRECTIONS)
)
_CANDIDATE_POLARITY_VOCABULARY = (
    "polarity IS NULL OR " + _in("polarity", _POLARITIES)
)


def _replace_candidate_constraint() -> None:
    op.drop_constraint(
        "ck_relation_candidate_asserts_something", "relation_candidate", type_="check"
    )
    op.create_check_constraint(
        "ck_relation_candidate_asserts_something",
        "relation_candidate",
        _CANDIDATE_ASSERTS_SOMETHING_021,
    )
    op.create_check_constraint(
        "ck_relation_candidate_signature_whole",
        "relation_candidate",
        _CANDIDATE_SIGNATURE_WHOLE_021,
    )
    op.create_check_constraint(
        "ck_relation_candidate_direction",
        "relation_candidate",
        _CANDIDATE_DIRECTION_VOCABULARY,
    )
    op.create_check_constraint(
        "ck_relation_candidate_polarity",
        "relation_candidate",
        _CANDIDATE_POLARITY_VOCABULARY,
    )
```

**Why the two vocabulary CHECKs are added and not left to the value types.** The closed
vocabulary is re-asserted for `020`'s stated reason (`020:144-147`): "a constraint that exists
only in Python is a constraint a ``COPY`` walks straight past." The signal side already has
this treatment for four vocabularies (`ck_relation_signal_kind`, `_direction`,
`_predicate_state`, plus 020's candidate-side `_status`/`_arity`/`_predicate_state`), and a
new vocabulary on the candidate side that has no CHECK would be the first asymmetry in the
schema. **These are vocabulary checks, not new business rules**, so they do not breach
`input.md:2823`.

**Why the whole-or-absent rule is admissible under `input.md:2823`** ("add explicit CHECKs
only where they encode constitutional invariants"). A half-written signature is not a
business rule; it is a corrupt row. Its two halves name one object, and a reader finding
`predicate_arity = 3` with no normalised predicate would be reading a fact that cannot exist.
This is the same class as `020`'s temporal pair (`020:144-151`):

> "The pair is what makes a stated emptiness a stated emptiness: a row with ``basis='absent'``
> and no value is a source that had no such date, which is different from a row nobody has
> finished writing."

On the candidate side it is load-bearing twice over: `predicate_signature_key` participates in
`logical_candidate_id` after `021`, so a half-present signature has an id that cannot be
re-derived — which Principle II (`.specify/memory/constitution.md:9`) forbids:

> "Any knowledge must trace fully: Finding → Analytical/Topological Feature → Graph/Assertion
> → Evidence → Observation → Raw Object → Source."

### D2.4 The safety property, stated exactly — including where it does not hold

This is the claim that makes `021` a "preserve data" migration, and it is **true for two of
the three replacements and false for the third**:

| Constraint | Old | New | Superset? | Consequence |
|---|---|---|---|---|
| `ck_relation_signal_asserts_something` | `A ∨ B` | `basis ∨ A ∨ B` | **yes** | no stored row can become invalid |
| `ck_relation_candidate_asserts_something` | `A ∨ B` | `A ∨ B ∨ C ∨ D` | **yes** | no stored row can become invalid |
| `ck_relation_signal_kind` | `kind ∈ 13` | `kind ∈ 15` | **NO — it narrows** | **an existing row with `negation`, `quantity` or `coreference` makes the `ADD CONSTRAINT` fail** |

The third case needs a documented pre-flight, and `021` must carry it in its docstring:

```sql
-- Pre-flight, run by an operator before `alembic upgrade head` reaches 021.
-- A non-zero row count means this database holds signal kinds the 021 whitelist removes and
-- the migration will refuse. That refusal is correct and must not be worked around by
-- rewriting rows: these are observations, and Principle I forbids editing one.
SELECT signal_kind, count(*)
  FROM relation_signal
 WHERE signal_kind IN ('negation', 'quantity', 'coreference')
 GROUP BY signal_kind;
```

**What `021` must NOT do to make that query return zero.** It must not `UPDATE
relation_signal SET signal_kind = …`, must not `DELETE` the rows, and must not add a
transitional whitelist admitting all three. All three mutate or re-label an observation. The
measured situation is benign and must be stated as measured, not assumed: **no `INSERT` into
`relation_signal` exists anywhere in `apps/`, `bench/` or `tools/`** (`data-model.md:260-262`,
`spec.md:803`), so in every database this repository can produce the query returns zero rows.
The pre-flight exists for a database somebody populated by other means, and its cost is one
query.

**The alternative, if the pre-flight is non-empty, is a forward revision and not a
workaround:** `022` re-adds the three kinds as *aspect* columns (FR-012's `SignalAspect`) and
only then narrows the whitelist. Recorded as a deferred item (D9, FR-152).

### D2.5 The rule the replacements must NOT re-introduce

`input.md:1081-1099` (§16), verbatim:

> A co-occurrence signal may honestly have no predicate words.
> …
> ```text
> John Smith
> Acme Corporation
> ```
>
> appearing together can yield:
>
> ```text
> signal_kind = CO_OCCURRENCE
> relation_surface = ""
> ```
>
> This is valid.

Checked against the replacements above:

| Candidate phrasing | Verdict |
|---|---|
| `signal_kind = 'co_occurrence' OR …` | **rejected** — makes the *kind* the escape hatch, so `co_occurrence` becomes a licence to assert nothing, and it is unrepresentable on `relation_candidate` |
| `observational_basis <> ''` (NOT NULL, no legacy branch) | **rejected** — would refuse every row written before `021`; `021` must preserve data |
| `relation_surface <> '' OR relation_ref IS NOT NULL OR predicate_signature_key IS NOT NULL OR signal_refs non-empty` | **adopted on the candidate side** — never requires a named predicate |
| `observational_basis IS NOT NULL OR <old predicate>`, plus the predicate-text narrowing rule | **adopted on the signal side** — the basis is *named*, and naming `predicate_text` is what obliges a surface; naming `proximity` is what permits its absence |

A named test asserts the negative (D9, FR-150): the replacement text must not contain the
literal `co_occurrence` at all, and must not treat `relation_surface <> ''` as its only route
to validity.

---

## D3 — `ck_relation_signal_kind` and the new `SignalKind`

### D3.1 The contradiction, stated

| Source | `TEMPORAL` | `NEGATION`/`QUANTITY`/`COREFERENCE` |
|---|---|---|
| `spec.md:414-417` **FR-011** | "`SignalKind` **MUST contain at least** … `EVENT`, **`TEMPORAL`**, … `SEMANTIC`" | "`COREFERENCE`, `SCHEMA`, `QUANTITY`, `NEGATION` **MAY remain**, but MUST NOT substitute for a mandatory channel" |
| `data-model.md:101-103` | "There is **no** `TEMPORAL` member today; … The brief names one, the code does not have it, and **it must not be added as a kind**." | "**removed**" |
| `checklists/requirements.md:46` **C2** | "…**no `TEMPORAL` added**" | same as data-model |
| `phase0-results.md:143` **D14** | "T023 cites FR-011 **in order to violate it** — FR-011 mandates a `TEMPORAL` member; T023 forbids it" | — |

### D3.2 The resolution, and why

**I adopt the reading that `TEMPORAL` IS a member and `COREFERENCE`/`QUANTITY`/`NEGATION`
are NOT.** Four reasons, in order of weight:

1. **A `MUST` in the spec outranks an inspection row in a checklist.** FR-011 is Phase 0
   output derived from the brief's own §15; C2 is a Phase 2 row whose method is `I`
   (inspection of the actual file). A checklist row cannot repeal an FR; it can only record a
   disagreement. C2 currently records one without resolving it, which is the D14 defect.
2. **`data-model.md`'s own reason for excluding `TEMPORAL` is about storage, not capability**,
   verbatim at `data-model.md:101-103`:
   > "There is no `TEMPORAL` member today; temporal information already lives in
   > `stated_axes` (`TemporalAxis`) and `SourceTemporalObservation`."

   That is a statement about *where the facts are recorded*, and it is correct — `020` created
   `source_temporal_observation` for exactly that (`020:186-233`) and
   `relation_signal.stated_axes` already exists (`020:257`). It is not a statement that a
   producer may not *notice* time. A producer reading "was founded in Delaware in 1998" and
   emitting a signal whose channel is the temporal construction has a channel; with no word
   for it in the vocabulary the producer must either mis-file it under `lexical` or drop it.
   Both are worse than adding the member.
3. **The asymmetry that made `NEGATION` a kind is removed by `Polarity`; the asymmetry that
   would make `TEMPORAL` one is not.** `schema.py:2432-2436` argues, verbatim:
   > "`negation` being here is load-bearing: without it, 'Acme did not acquire Beta' is
   > either dropped - losing an observed fact - or recorded as an acquisition, which is a lie
   > with a schema."

   That argument is *discharged* by FR-015's `polarity` column, which is why `NEGATION` can
   leave the vocabulary. The same argument applied to `TEMPORAL` ("a founding date would be
   dropped") is **not** discharged: `stated_axes` records *which axes a source stated*, not
   *that a temporal construction is the channel that noticed the relation*. So `TEMPORAL`
   stays and `NEGATION` goes. That is a principled split, not a compromise.
4. **Excluding a member the brief names is the failure mode the whole feature is built
   against.** The brief's governing demand (`input.md:1139`) is "Unknown relation semantics
   are valid", and the platform's stated failure is narrowing a vocabulary until a real
   observation has no home. `data-model.md:105-107` makes the counter-argument for the four
   removed kinds:
   > "Note the four kinds that no producer emits today — `CO_OCCURRENCE`, `COREFERENCE`,
   > `QUANTITY`, `NEGATION` — are exactly the ones being dissolved into fields. A vocabulary
   > that only names things nobody produces, and names them wrongly, is the defect."

   `TEMPORAL` is a kind a producer *does* emit, so that argument does not reach it.

**The residual risk of this reading, stated honestly.** Adding `TEMPORAL` while `Polarity` is
a *column* recreates a version of the ambiguity FR-012 names: an aspect (compounding the
temporal frame) could be recorded as a channel. Two mitigations, both mandatory: (a) `021`
adds **no** `TEMPORAL`-specific column — temporal *facts* stay in
`source_temporal_observation`/`stated_axes` and are referenced, never copied; (b) the
`SignalAspect` split FR-012 asks for is recorded as deferred (D9, FR-152) and `021`'s
docstring states that a `TEMPORAL` signal must carry a `stated_axes` or `temporal_evidence`
reference, so the kind is a channel and never a container.

**`SCHEMA` vs `SEMANTIC`, and `HIERARCHY` vs `STRUCTURAL` — two real ambiguities, resolved
narrowly and flagged.** FR-011 mandates `SEMANTIC` and `STRUCTURAL` while permitting `SCHEMA`
and `HIERARCHY` to remain, and the four are near-synonyms at HEAD: `signal.py:91-92`
documents `HIERARCHY` as "containment by position: a section inside a document, a row inside
a table, a page inside a site" and `SCHEMA` as "a typed slot: an RDF or JSON-LD property
whose presence is the relation". The split I adopt, to be written into `signal.py`'s
docstrings by the signal-contract task:

- `STRUCTURAL` = a **document-structure-derived** channel that is *not* containment (a
  definition-list term/definition pair, an `aria-describedby`/`rel=next` sibling, a
  heading-tree step). `HIERARCHY` stays **containment specifically**.
- `SEMANTIC` = a channel reading an **asserted meaning from a controlled vocabulary**
  (`sameAs`, `knows`, a JSON-LD `@type` relationship). `SCHEMA` stays **the typed slot
  itself** — the property's presence, regardless of whether it means anything the platform
  can resolve.

**These are my definitions, not the brief's.** They are in the disagreements register (§5) for
the brief owner. If either split is rejected, one of the four members must be dropped and
FR-011 amended; it cannot be left as two names for one channel.

### D3.3 The new whitelist — 15 members

```python
#: The signal kinds 021 admits, written out rather than imported, for the reason
#: ``020_universal_relation_extraction.py:94-102`` gives: a migration that reads a value type
#: is a migration whose meaning changes when that type is edited.
#:
#: 020 listed thirteen and 021 lists fifteen. Five are added - ``syntactic``,
#: ``structural``, ``event``, ``semantic`` and ``temporal`` - because FR-011 requires them
#: and no channel existed for a parsed frame, a non-containment document structure, an event
#: frame, an asserted controlled-vocabulary meaning, or a temporal construction. Three are
#: removed - ``coreference``, ``quantity`` and ``negation`` - because each was an orthogonal
#: aspect wearing a channel's name: a coreference is a relation between mention refs rather
#: than an observation channel, a quantity is an argument shape on a participant, and a
#: negation is a polarity. 020's own docstring for ``negation`` argued the opposite, and that
#: argument is now discharged by the ``predicate_polarity`` column, which is where a denial
#: belongs.
_SIGNAL_KINDS = (
    "lexical",
    "syntactic",
    "structural",
    "event",
    "semantic",
    "temporal",
    "link",
    "reference",
    "table",
    "list",
    "metadata",
    "attribute",
    "hierarchy",
    "schema",
    "co_occurrence",
)
```

Arithmetic, asserted by test: `13 − 3 (removed) + 5 (added) = 15`.

**The removal is a narrowing.** D2.4 covers the operational consequence: a
`negation`/`quantity`/`coreference` row makes the `ADD CONSTRAINT` fail, and the migration
refuses rather than rewriting. The `schema.py:2432-2436` comment that defends `negation`
becomes **false** and must be rewritten in the same commit — a stale comment defending a
member the CHECK no longer admits is exactly the "disabled verifier whose comment asserts it
passes" failure `FR-098` names. Replacement text in D10.5.

### D3.4 The parity hazard, named precisely

The hazard is **not** that `020`'s test breaks. It does not, and the precision matters:
`test_migration_020_universal_relation.py:321-326` loads **020's module by path** and asserts
`len(module._SIGNAL_KINDS) == 13`. `021` does not change `020`'s file, so that assertion keeps
passing forever. It is not drift detection.

The real hazard is that **two tests assert two different truths about "the signal kinds" and
neither compares either to the code**:

- `020`'s test: `020` has 13 — a fact about a frozen file.
- `021`'s test: `021` has 15 — a fact about a new file.
- `schema.py:2437`: `_in("signal_kind", SignalKind)` — reads the **enum**, so the
  fresh-install path follows the code automatically, with no test in the loop.

`schema.py:13-22` says the literals and the references "are asserted to agree". **They are
not asserted to agree — each is asserted only about itself.** The mechanism that actually
closes the loop compares to the **live enum**, not to a count:

```python
def test_the_whitelist_is_exactly_the_live_signal_kind(self) -> None:
    from extractors.signals.signal import SignalKind
    assert tuple(module._SIGNAL_KINDS) == tuple(k.value for k in SignalKind)
```

The same comparison is required for `021`'s `_POLARITIES` against `Polarity`, for
`_OBSERVATIONAL_BASES_021` against `SignalBasis`, and for `_DIRECTIONS` against **both**
`020._DIRECTIONS` and `DirectionHypothesis` — the last because `021` re-declares the
direction literals rather than importing them, and a re-declaration is a duplication that can
rot. Loading `020` by path to read `_DIRECTIONS` is done exactly the way
`test_migration_020_universal_relation.py:109-114` loads its own migration.

---

## D4 — Indexes

### D4.1 The required set — 6 new indexes

All six lead with `tenant_id`. Constitution VII (`.specify/memory/constitution.md:24`),
verbatim:

> "Mandatory: SSRF protection, DNS-rebinding protection, sandboxed parsers, browser
> isolation, network egress policy, CPU/memory/timeout/size limits, archive-depth and
> file-count limits, **tenant isolation at every level**, RBAC, audit logs, secret isolation."

| # | Index | Table | Columns | Why it is required |
|---|---|---|---|---|
| 1 | `ix_relation_candidate_object` | `relation_candidate` | `tenant_id, object_mention_ref` | `ix_relation_candidate_pair` (`020:357-360`) is `(tenant_id, subject, object)`; a btree serves **prefix** queries only, so an object-side participant lookup has **no index at all**. `020` is not wrong here — a binary relation is read by its subject — but brief §13 makes participants variadic and in arbitrary order, so an assembly query legitimately arrives from the object end. |
| 2 | `ix_relation_signal_object` | `relation_signal` | `tenant_id, object_mention_ref` | The identical asymmetry on the signal side, for the same reason. |
| 3 | `ix_relation_claim_candidate` | `relation_claim` | `tenant_id, candidate_id` | FR-088 adds `candidate_id`; FR-068 requires the reverse navigation (`claim → candidate`, and for the projection, every claim a candidate produced). A column that is inside `content_hash` (`domain/relation_claim.py:411`) and unindexed is a full scan on the one read FR-068 mandates. |
| 4 | `ix_relation_candidate_status` | `relation_candidate` | `tenant_id, candidate_status, logical_candidate_id` | `.specify/memory/constitution.md:65`: "**rejected candidates are never auto-deleted (replay/re-evaluation supported)**". A preserved rejection that cannot be *found* is not preserved. `logical_candidate_id` is the third column so "every reading of a hypothesis, by disposition" is one index range. |
| 5 | `ix_relation_candidate_signature` | `relation_candidate` | `tenant_id, predicate_signature_key` | "Which readings agree on this predicate" is the blocking/dedup question the signature exists to answer, and it is a cross-candidate read. |
| 6 | `ix_validation_finding_candidate` | `validation_findings` | `tenant_id, candidate_id` | Pairs with D1.4. Without it the new column is write-only — the same defect as a table with no reader. Mirrors the existing `ix_validation_finding_assertion` (`schema.py:1573`) exactly. |

```python
def _add_indexes() -> None:
    op.create_index("ix_relation_candidate_object", "relation_candidate",
                    ["tenant_id", "object_mention_ref"])
    op.create_index("ix_relation_signal_object", "relation_signal",
                    ["tenant_id", "object_mention_ref"])
    op.create_index("ix_relation_claim_candidate", "relation_claim",
                    ["tenant_id", "candidate_id"])
    op.create_index("ix_relation_candidate_status", "relation_candidate",
                    ["tenant_id", "candidate_status", "logical_candidate_id"])
    op.create_index("ix_relation_candidate_signature", "relation_candidate",
                    ["tenant_id", "predicate_signature_key"])
    op.create_index("ix_validation_finding_candidate", "validation_findings",
                    ["tenant_id", "candidate_id"])
```

**Tenant-prefix discipline, as a rule rather than a coincidence.** Every index `021` creates
lists `tenant_id` first, with no exception, and no new index is created without it. This is
not a fresh obligation: it is what `020` did in all eleven of its `create_index` calls
(`020:219-233, 284-292, 350-366`), and what `018`'s header states (`schema.py:1341-1344`):

> "Every table carries ``tenant_id`` NOT NULL with a check that it is not the empty string.
> There is deliberately no nullable or global tenant: a semantic term is a reading of one
> tenant's data, and a row readable by every tenant would leak what instruments that tenant
> had (constitution IV, fail-closed)."

A test asserts it mechanically (D9, FR-154, `test_every_index_021_adds_leads_with_tenant_id`).

**No unique index is created by `021`**, for `016`'s stated reason — "no unique index is
created while rows that would collide inside it are still unbackfilled" — and there is no
backfill, so there is nothing to collide.

### D4.2 Deferred indexes (named, not created)

- `ix_relation_signal_signature` on `(tenant_id, predicate_signature_key)` — useful once a
  producer writes signals; required by no FR read. Defer.
- `ix_relation_claim_verdict` — **deliberately not created.** `validation_record` is JSONB and
  `non_valid()` filters in Python (D5.3). The in-repo precedent is
  `SqlRelationClaimStore.by_participant` (`relation_claim_store.py:424-441`), verbatim:
  > "``role_bindings`` is JSONB, so the rule is applied to the reconstructed claims rather
  > than pushed into the query."

  `checksum()` (`relation_claim_store.py:455-460`) is the second precedent: a tenant-wide
  ordered scan, digested. The honest cost is in D4.3.

### D4.3 `by_signal` — the one real gap in `020`'s index set, and why no index fixes it

`input.md:2716-2727` (§59) requires `by_signal` on all three stores. Mapped honestly against
`020`'s eleven existing indexes:

| Operation | `relation_signal` | `relation_candidate` | `source_temporal_observation` |
|---|---|---|---|
| `write` | n/a | n/a | n/a |
| `get` | PK `signal_id` | PK `candidate_id` (+ `uq_relation_candidate_address` as a tenant-prefixed left prefix) | PK `observation_id` |
| `by_tenant` | `ix_relation_signal_tenant` ✅ | `ix_relation_candidate_tenant` ✅ | `ix_temporal_observation_tenant` ✅ |
| `by_logical_id` | **N/A** — no logical id; nearest equivalent `ix_relation_signal_producer`, which is also FR-034's independence read ✅ | `ix_relation_candidate_logical` ✅ | **N/A** — no logical id; nearest equivalent `ix_temporal_observation_capture` ✅ |
| `by_pair` | `ix_relation_signal_pair` ✅ | `ix_relation_candidate_pair` ✅ **(subject side only → NEW #1)** | **N/A** — no participants; nearest equivalent `ix_temporal_observation_axis` ✅ |
| `by_signal` | PK `signal_id` ✅ | **NO INDEX — see below** | **N/A** |
| `checksum/replay` | ordered tenant scan, per the `checksum()` precedent | ordered tenant scan | ordered tenant scan |

**The gap, stated exactly.** `by_signal(signal_id)` on the candidate side means "which
candidates cite this signal". With `signal_refs` as JSONB the query is a containment test
(`signal_refs @> '["SIG-…"]'::jsonb`), and no plain btree serves it. Three options:

| Option | Cost | Verdict |
|---|---|---|
| (i) single-column `GIN (signal_refs)` | Not tenant-prefixed. Every query still filters `tenant_id`, so no leak occurs — but VII says "tenant isolation at every level", and a non-prefixed index on a multi-tenant table is the level where it is not structural. | **rejected** |
| (ii) `op.execute("CREATE EXTENSION IF NOT EXISTS btree_gin")` then `GIN (tenant_id, signal_refs)` | Makes `tenant_id` a GIN key, so containment is tenant-scoped structurally. Cost: `CREATE EXTENSION` in a migration needs superuser, and this repository declares no extension anywhere. It is a privilege escalation a persistence revision has not earned, and it makes the dev and production roles differ. | **rejected**, recorded as a follow-up decision |
| (iii) **no index; filter in Python over the tenant's candidates** | The lookup scans one tenant's candidates. | **recommended** |

**Why (iii) is the honest recommendation and not a dodge.** The read that actually matters is
the *forward* one — "which signals back this candidate" — and that is served by reading one
row by primary key. The reverse ("which candidates cite this signal") is a question the
assembler already holds the answer to in memory, because it just built those candidates from
exactly those signals; a durable re-derivation re-derives a fact that `signal_refs` *is*. And
the cost is bounded the way that matters: one tenant's candidate set, not the table — the same
shape `by_participant` already ships in production code (`relation_claim_store.py:432-441`,
with no `role_bindings` index on `relation_claim` either, and none proposed).

**This is a real limitation and must be reported as one**, not as a design win: `by_signal` is
O(candidates in tenant) and would need option (ii) to become O(log n). Recorded in D9 (FR-154)
as a `known limitation` with option (ii) as the named upgrade, so the cost is visible at the
gate.

---

## D5 — The `SqlRelationClaimStore` verdict home

### D5.0 The fact that decides most of this

`relation_claim_store.py:241-247`, verbatim:

```python
raise NotImplementedError(
    "no JSONB column exists to persist a ValidationResult: relation_claim has only its "
    f"own structural JSONB columns ({', '.join(sorted(CLAIM_JSONB_COLUMNS))}) and "
    "relation_claim_revision has none; migration 016 needs "
    "relation_claim.validation_record JSONB (or relation_claim_revision.payload JSONB) "
    "before a non-VALID verdict can be preserved and replayed (FR-050)"
)
```

and `_validation_column()` (`relation_claim_store.py:219-247`) **scans the live ORM metadata**
for the first JSONB column on `relation_claim` that is not in `CLAIM_JSONB_COLUMNS`:

```python
for model, owned in ((RelationClaimRow, CLAIM_JSONB_COLUMNS), (RelationClaimRevisionRow, None)):
    for column in model.__table__.columns:
        if isinstance(column.type, JSONB) and column.name not in (owned or ()):
            return model, column.name
```

**Therefore adding `relation_claim.validation_record JSONB` makes the 558-line store work
with no code change at all.** This is the decisive fact and it changes the shape of the
decision: the question is not "how do we make the store work" but "which of three home shapes
do we want", and the minimum one is free.

**Two consequences that constrain the DDL and are in no artefact:**

1. `CLAIM_JSONB_COLUMNS` (`relation_claim_store.py:27-35`) is the set of *owned structural*
   columns and **must not gain `validation_record`** — it is the exclusion list, and adding
   the verdict column to it would keep the store refusing.
2. `021` **must not add any other JSONB column to `relation_claim`.** The lookup returns the
   *first* match in declaration order, so a later JSONB column on `relation_claim` — a
   plausible future "claim annotations" or "lineage blob" — would be picked up instead, and
   the verdict would be written into the wrong column, silently. `021`'s docstring must state
   this as a standing constraint, and a test must assert it (D9, FR-153,
   `test_relation_claim_carries_exactly_one_foreign_jsonb_column`).

### D5.1 Option (a1) — `relation_claim.validation_record JSONB` — **RECOMMENDED**

| Consequence | Detail |
|---|---|
| Store code change | **none**; `_validation_column()` starts resolving |
| `NotImplementedError` | gone from both `record_validation` and `non_valid` |
| Data preserved | yes — the verdict is written **in place**, no claim deleted or downgraded, which is what the method's own docstring claims (`relation_claim_store.py:471-473`: "A claim is never deleted or downgraded to hide a verdict: the rejection is preserved in place.") |
| Tenant scoping | inherited; the column lives on a table with `tenant_id` (016) and the store's `_verdict_query` filters on it (`:524-538`) |
| **Cost 1** | **One verdict per claim revision.** A second validation of the same `relation_id` overwrites the first. |
| **Cost 2** | It is the only `UPDATE` in this schema family (D7.2) |
| **Cost 3** | It must be kept out of `_material()`; a future edit that adds it would make recording a verdict mint a new `relation_id` |

Cost 1 is the real one, and it is acceptable **only because it is declared**: one claim
revision is validated once, in the `VALIDATION` stage, before admission (`spec.md:601-604`,
FR-055's stage list). Re-validation is explicitly being *removed* by FR-092, not enabled. So
one verdict per revision matches the lifecycle, and the honest statement is: "declared
single-verdict-per-revision; N verdicts require the (a2) shape."

### D5.2 Option (a2) — a new `relation_claim_validation` table — correct, deferred

```text
relation_claim_validation
  validation_row_id    String(96)  PK
  tenant_id            String(36)  NOT NULL, CHECK tenant_id <> ''
  relation_id          String(64)  NOT NULL
  logical_relation_id  String(64)  NOT NULL
  revision_number      Integer     NOT NULL
  verdict              String(16)  NOT NULL
  recorded_at          timestamptz NOT NULL DEFAULT now()
  record               JSONB       NOT NULL
indexes: (tenant_id, relation_id), (tenant_id, verdict),
         (tenant_id, relation_id, revision_number)
```

Better on every axis: append-only (Principle I), N verdicts per revision, tenant-prefixed
indexes on all three reads, and `recorded_at` a first-class column rather than a key inside a
blob.

Why deferred anyway: it requires **editing the store** — `_validation_column()` knows two
models, `_verdict_query` branches on two — and the store has **zero importers**
(`spec.md:802`), so the edit is safe but the *benefit* is unobservable until something calls
it. Shipping a third model, a new table and three indexes in a revision whose other job is
constraint replacement would make `021` do two unrelated things, and a revision that does two
unrelated things is a revision nobody can review. **Recommendation: record (a2) as the correct
long-term shape with a named trigger** — the trigger is the first second validation of the
same `relation_id`, or the first non-test importer of the store (D9, FR-153).

### D5.3 Option (b) — leave the store unusable — **rejected, and here is what it costs**

`record_validation` and `non_valid` keep raising `NotImplementedError`, 558 lines stay with
zero importers, and the costs are concrete:

1. **FR-050's replay queue does not exist.** `non_valid` is "the replay queue: every claim
   whose recorded verdict is not `VALID`" (`relation_claim_store.py:491`). With no home there
   is no queue, and constitution Governance (`.specify/memory/constitution.md:73`) requires:
   > "Rejected analysis outputs (admission rejections, TDA signals) are preserved with
   > decision, reasons, score vectors, versions, and timestamps for replay."

   A verdict that cannot be stored is a verdict that cannot be replayed — a direct
   constitutional miss, not a deferred nicety.
2. **`SC-011`/`FR-050` cannot be reported as anything but `deferred`**, and J13's sign-off
   (`checklists/requirements.md:144`) would have to carry it.
3. **The refusal is a lie by omission once `021` exists.** `_validation_column()` looks the
   column up *at runtime*; the day any other JSONB column lands on `relation_claim` for an
   unrelated reason, the store starts writing verdicts into it **without a line of code
   changing** (D5.0, consequence 2). Option (b) is therefore not a stable state — it is a
   latent corruption with a fuse.
4. **It costs nothing to avoid.** `021` is already the revision that must touch
   `relation_claim` (FR-088's `candidate_id`), so the column costs one `op.add_column` and
   zero new files.

### D5.4 `validation_findings` — the premise is partly overstated, and the residue is one column

**Where I disagree with the job's framing.** The brief for D5 says "`validation_findings` has
no `relation_id`/`candidate_id` column, **so a relation validation finding has nowhere to
attach**." The first clause is true; the inference is too strong.

A finding **about a claim** attaches today, with no schema change:

- `validation_findings.assertion_ref` is `String(64) NOT NULL` (`018:192`).
- A claim's `relation_id` is a 64-character content address (`domain/relation_claim.py:167`).
- `ix_validation_finding_assertion` is `(tenant_id, assertion_ref)` (`schema.py:1573`).
- `stage` (`String(24)`, `018:194`) already says which lifecycle stage produced it.

So "what did validation say about this relation" is already one indexed read, provided the
finding's subject is a claim. That covers the `VALIDATION` stage of `RelationClaim` and is
exactly the case FR-050 is about.

**What genuinely has nowhere to attach is a candidate-stage finding.** A `CNDR-` id is not
an `assertion_ref` in the semantic-fabric sense, `assertion_ref` is `NOT NULL` with no
default, and FR-067 requires:

> "An explicit hypothesis/evidence view MUST serve extracted-but-unadmitted relations."

A hypothesis that has not been admitted is precisely what a candidate-stage finding is about,
and it must be attachable for that view to be answerable. Hence **exactly one column,
`validation_findings.candidate_id String(64) NULL`** (D1.4) and **one index** (D4.1 #6).

**The one discipline this imposes:** a candidate-stage finding writes `candidate_id` and
leaves `assertion_ref` to be filled with the *claim* the finding would block — or, when there
is no claim, `021` cannot help and the finding must be refused rather than fabricated. Stated
as a named test (D9, FR-156,
`test_a_candidate_stage_finding_never_fabricates_an_assertion_ref`).

---

## D6 — Parity, invariant and round-trip tests, without a live database

### D6.1 The parity test — `tests/unit/test_migration_021_relation_finalization.py`

Modelled on `test_migration_020_universal_relation.py`, with **three deliberate departures**,
each because the 020 model does not test the thing `021` must guarantee.

**Departure 1 — the recorder must capture added columns and constraints.**
`_OpRecorder` (`020-test:81-106`) records `create_table`, `create_index` and `alter_column`
only. `021`'s content is `add_column` + `drop_constraint` + `create_check_constraint`, so the
recorder gains:

```python
    def add_column(self, table, column, **kwargs):
        # kwargs are recorded whole so P3 can assert they are empty: Operations.add_column
        # accepts no existing_type / existing_nullable, and those are alter_column arguments.
        self.added.append((table, column.name, column, dict(kwargs)))
        self.operations.append(("add_column", f"{table}.{column.name}"))

    def drop_constraint(self, name, table, **kwargs):
        self.dropped.append((name, table, kwargs.get("type_")))
        self.operations.append(("drop_constraint", f"{table}.{name}"))

    def create_check_constraint(self, name, table, condition, **kwargs):
        self.checks.append((name, table, condition))
        self.operations.append(("create_check_constraint", f"{table}.{name}"))
```

**Departure 2 — CHECK comparison must be on text, not names.** The 020 model compares
`{c.name for c in table.constraints if isinstance(c, sa.CheckConstraint)}` (`020-test:157-158`)
— **names only**. A whitelist that changes in one install path and not the other is therefore
**invisible to the existing test class**, because the name `ck_relation_signal_kind` is
identical on both sides either way. This is the most important gap in the 020 model for
021's purpose. The 021 test adds:

```python
def _check_text(table: sa.Table) -> dict[str, str]:
    return {
        c.name: " ".join(str(c.sqltext).split())
        for c in table.constraints
        if isinstance(c, sa.CheckConstraint) and c.name
    }
```

and compares the full mapping for all four touched tables.

**Departure 3 — the cross-revision vocabulary assertion** (D3.4), because the 020 model's
`== 13` is a fact about a frozen file and detects nothing.

| # | Test | Asserts |
|---|---|---|
| P1 | `test_the_revision_chains_onto_020` | `down_revision == "020_universal_relation_extraction"`, `revision == "021_relation_extraction_finalization"` |
| P2 | `test_exactly_twenty_three_columns_are_added` | 9 + 11 + 2 + 1 = 23 — a tripwire for an accidental column |
| P3 | `test_add_column_is_called_with_the_documented_signature` | `Operations.add_column` accepts no `existing_type` / `existing_nullable`; those are `alter_column` parameters (`020:177-183` uses them correctly there). Passing them to `add_column` is a `TypeError` at migration time. `021` issues no `alter_column`, so the recorder must see `add_column` calls with empty kwargs |
| P4 | `test_each_table_gains_exactly_the_columns_this_spec_lists` | per-table sets, not just the total |
| P5 | `test_the_columns_agree_with_the_orm` | the 020 comparison (`:190-212`) extended to `add_column`: name set, `_type_signature`, `nullable`, `_default_text` |
| P6 | `test_the_check_constraints_agree_with_the_orm_by_text` | **Departure 2** |
| P7 | `test_the_two_asserting_constraints_are_dropped_by_name` | `("ck_relation_signal_asserts_something", "relation_signal", "check")` and `("ck_relation_candidate_asserts_something", "relation_candidate", "check")` in `recorder.dropped` |
| P8 | `test_the_kind_constraint_is_dropped_and_recreated` | the third DROP, same form, plus the new whitelist text |
| P9 | `test_no_check_is_dropped_outside_the_three_named` | an unnamed drop is an unreviewed weakening |
| P10 | `test_each_replacement_is_a_strict_superset_of_the_check_it_replaces` | the D2.4 claim, asserted structurally: the old disjuncts appear verbatim in the new text, and the third replacement is asserted to **narrow**, with a comment saying so |
| P11 | `test_the_replacement_never_mentions_co_occurrence` | D2.5's negative — the escape hatch is a *basis*, not a kind |
| P12 | `test_no_table_and_no_column_is_dropped` | the 020 model at `:181-184`, extended so `drop_constraint` is the only destructive op recorded |
| P13 | `test_no_statement_would_edit_a_row` | the recorded SQL/text contains no `UPDATE `, `DELETE ` or `TRUNCATE` (D7.2) |
| P14 | `test_the_whitelist_is_exactly_the_live_signal_kind` | **Departure 3** |
| P15 | `test_the_polarities_are_exactly_the_live_polarity` | same, for `Polarity` |
| P16 | `test_the_observational_bases_are_exactly_the_live_signal_basis` | same, for `SignalBasis`; and the 9 members equal the 9 names in `input.md:1125-1137` |
| P17 | `test_the_directions_agree_with_020_and_with_the_live_enum` | 021 re-declares `_DIRECTIONS`; both comparisons |
| P18 | `test_020_still_lists_exactly_thirteen_and_021_lists_fifteen` | the *pair* is the drift detector |
| P19 | `test_the_migration_imports_no_value_type` | `020-test:321-325` extended: no `from extractors`, no `from domain`, no `from semantic` |
| P20 | `test_every_index_021_adds_leads_with_tenant_id` | D4.1 |
| P21 | `test_the_index_names_and_column_lists_match_the_orm` | the 020 model at `:190-198` extended to indexes |
| P22 | `test_every_added_column_lands_on_a_table_that_already_carries_a_fail_closed_tenant` | `tenant_id` NOT NULL + `tenant_id <> ''` on all four tables |
| P23 | `test_no_new_table_is_created` | a stray `create_table` is an unreviewed structural change |
| P24 | `test_downgrade_refuses_before_emitting_any_operation` | D8 — stronger than 020's model, which checks only the message |
| P25 | `test_the_refusal_names_what_would_be_lost` | the 020 model at `:292-299` |
| P26 | `test_the_migration_file_states_the_kind_narrowing_preflight` | D2.4's `SELECT` is in the docstring, so a deployer reads it in review |
| P27 | `test_the_deferred_participants_widening_is_recorded` | 022's deferral is in 021's docstring, so the omission reads as a decision |

### D6.2 Schema invariant tests — FR-062 requires them and they are **unscheduled**

**This is a gap, not merely an omission in ordering.** `input.md:2827-2833` asks for three
artefacts:

```text
migration parity tests
schema invariants
round-trip tests if PostgreSQL available
```

and `checklists/requirements.md` section H has H7 ("ORM/migration parity test-enforced for
`021`") and H9 (the round trip) but **no row for "schema invariants" and no task**. New
checklist row H15 (D10.6).

These are structural assertions over `Base.metadata` and are **fully offline**:

| # | Test | Invariant |
|---|---|---|
| I1 | `test_every_table_in_the_orm_declares_tenant_id_not_null` | no nullable or global tenant anywhere (`schema.py:1341-1344`) |
| I2 | `test_every_table_checks_tenant_id_is_not_the_empty_string` | `''` is not a tenant (`020:44-46`) |
| I3 | `test_no_table_declares_a_foreign_key` | the 015/016/018/019 stance (`schema.py:1604-1615`): "Adding an FK here would be a schema decision this feature has not earned." |
| I4 | `test_no_digest_or_created_at_column_appears_in_a_unique_index` | `created_at` is a fact of the writing, not of the event (`schema.py:1616-1623`) |
| I5 | `test_every_check_constraint_is_a_tenant_check_a_vocabulary_check_or_a_declared_invariant` | a new CHECK must be classifiable or it is an unexamined rule |
| I6 | `test_neither_relation_signal_nor_relation_candidate_requires_a_named_predicate` | the D2.5 negative, over ORM metadata rather than migration text |
| I7 | `test_relation_signal_declares_no_column_that_a_producer_must_not_set` | 019's deliberate absence (`schema.py:2363-2366`): "A signal has no entity, no relation status and no admission verdict, and the absence of those columns is the point" — the `predicate_*` columns must not smuggle one back |
| I8 | `test_every_index_name_is_unique_across_the_orm` | a duplicate index name is a `create_all` failure on one path only |

### D6.3 Round-trip tests

`input.md:3760-3785` (§91), verbatim:

> For every new substrate object:
>
> ```text
> build → store → read
> ```
>
> must preserve: IDs, alternatives, signals, provenance, type hypotheses, predicate
> signature, temporal evidence, tenant, context, regime
>
> Do not reduce it to a summary string.

**Split by what is provable offline**, because this is where the "verified" / "verified only
offline" line falls:

| Test | Offline? | Note |
|---|---|---|
| R1 `test_the_signature_survives_a_domain_round_trip_field_by_field` | **yes** | `PredicateSignature.to_dict()`/`from_dict()` over all 7 fields |
| R2 `test_a_signal_round_trips_with_an_empty_surface_and_a_named_basis` | **yes** | `SC-012`'s **constructible** clause |
| R3 `test_a_candidate_assembled_only_from_co_occurrences_is_storable_by_the_row_builder` | **yes** | the row builder emits `relation_surface=''`, `predicate_signature_key=None`, `signal_refs=[…]` — the four disjuncts of the new candidate CHECK are all present. `SC-012`'s **persistable** clause at the mapping layer |
| R4 `test_the_store_writes_and_reads_every_added_column` | **yes** | over the row builder plus a fake session; asserts the 23 columns, not a summary |
| R5 `test_the_verdict_home_resolves_without_a_database` | **yes** | `assert _validation_column() == (RelationClaimRow, "validation_record")`. **`_validation_column()` reads `__table__.columns` — pure metadata — so the disappearance of `NotImplementedError` is provable offline.** The highest-value offline test in this job |
| R6 `test_record_validation_then_non_valid_returns_the_rejected_claim` | **partly** | needs a session; offline only as far as R5 |
| R7 `test_a_claim_whose_candidate_id_is_empty_round_trips_as_empty` | **yes** | the D1.3 `''` pairing |
| R8 `test_the_verdict_column_is_not_identity_material` | **yes** | `content_hash` unchanged before and after a verdict is attached |
| R9 `test_a_co_occurrence_signal_is_accepted_by_the_database` | **NO — live only** | a real `INSERT`. The one behavioural claim `SC-012` needs that offline cannot reach. `input.md:2832` says "round-trip tests **if PostgreSQL available**", so the brief anticipates exactly this |
| R10 `test_the_full_store_round_trip_in_a_real_database` | **NO — live only** | `input.md:2832` again |

### D6.4 What cannot be verified offline, and what the report must say

**Cannot be verified without a live PostgreSQL**, as a list rather than a hedge:

1. That PostgreSQL accepts the DDL at all — a syntax or type error in any of the 23
   `add_column` calls, or in a CHECK.
2. That `ADD CONSTRAINT` for the new kind whitelist **succeeds** on a database holding
   legacy `negation`/`quantity`/`coreference` rows (D2.4). Offline we can prove the whitelist
   is right; we cannot prove no row falls outside it.
3. That `jsonb_array_length(signal_refs)` compiles and behaves as assumed inside a CHECK.
4. That `IS DISTINCT FROM` is accepted in the `predicate_text` narrowing rule. It is standard
   PostgreSQL, but it is not portable and the offline test only sees the text.
5. `op.add_column … nullable=False, server_default=""` on `relation_claim` against a table
   that may have rows.
6. That the six new indexes are actually used. There is no `EXPLAIN`, so "this index is
   required" is an argument, not a measurement. Stated as an argument in D4.1.
7. `alembic upgrade head` end to end, and `alembic heads` reporting a single head.
8. `compare_metadata` autogenerate reporting no drift —
   `test_orm_migration_parity.py:112-114` **skips** without a database.
9. R6, R9, R10.

**What the report must say, verbatim (FR-084 discipline, `research.md:210-212`):**

> "**Live PostgreSQL is not reachable in this environment.** All DB verification is therefore
> offline: ORM/DDL parity, in-memory round trip, and migration text assertions. Anything
> needing a live round trip is reported `verified only offline` and never as `verified`
> (FR-084)."

For migration `021` specifically, the report MUST additionally carry the nine items above as
an explicit **"not verified"** list, and MUST split `SC-012` into three clauses with three
verdicts: **constructible `verified`, assemblable `verified`, persistable `verified only
offline`**. Reporting `SC-012` as a single `verified` is the dishonest form, and it is what
the current artefacts would produce.

### D6.5 Drift detection, mechanically

**Mechanism 1 is the important one and it is currently missing.**

1. **`OWNED_TABLES` must gain 020's three tables.**
   `test_orm_migration_parity.py:69-86` lists 15 tables and **none of `relation_signal`,
   `relation_candidate` or `source_temporal_observation` is among them.** So the *only* live
   drift check in the repository does not cover the three tables `020` created, let alone
   `021`'s 23 columns. The module's own docstring states the standard, verbatim (`:41-47`):
   > "It has to be in here: this is the only check that the column the ORM declares is the
   > column the migration adds, so leaving the table out means a drift in it — a renamed
   > column, a dropped NOT NULL, a different server default — is invisible to CI, and a
   > missing provenance column surfaces weeks later as an audit question with no answer."

   Add all three. This is a **test file**, not a released migration, so editing it is allowed.
2. **`relation_claim` needs a *narrow* live assertion, not table membership.** The module's
   docstring (`:57-68`) explains why `relation_claim` is excluded: 016 created
   `relation_claim.created_at` without `nullable=False` while the ORM declares a
   non-optional `Mapped[datetime]`, and adding the table "would make this check fail on a
   drift that has been there since 016". That reasoning is sound and this job does not disturb
   it. Instead add one **live, column-scoped** assertion for exactly the four columns `021`
   adds to `relation_claim` plus the one on `validation_findings`, comparing `compare_type` /
   `nullable` / `server_default` for a named column list. This gets `021`'s columns under the
   live check without inheriting 016's known divergence.
3. **Pin `020` by digest.** `test_migration_forward_only.py:29-33` pins **only** `014`:
   ```python
   RELEASED_DIGESTS: dict[str, str] = {
       "014_temporal_materialization.py": (
           "27b606f3b5458bdac33e64351a5509389ccc808cede244f29539cdf40f55a09b"
       ),
   }
   ```
   So "020 MUST NOT be edited" is prose in five artefacts and **enforced by nothing**. Add,
   computed with the module's own newline-normalised SHA-256 (`:53-60`):
   ```python
   "020_universal_relation_extraction.py": (
       "068c6fc3378ceeee3f9bdf5bb348b620a6dcfe80227c959f79e3792d8024f0a8"
   ),
   ```
   Verified at HEAD `0056665` for this job. Pin `018` and `019` in the same change if their
   digests can be computed; the mechanism is the point, not the count.
4. **The 021 test's own cross-path comparisons** (P5, P6, P21, and the D3.4 cross-revision
   pair) are the offline substitute for (1) and (2) while no database exists. They are
   weaker — they compare the DDL *as written* to the ORM, not the DDL *as applied* — and the
   report must say so rather than let them stand in for the live check.
5. **One pre-existing divergence the 021 test will surface and must resolve:**
   `020` declares JSONB as `postgresql.JSONB(astext_type=sa.Text())` (`020:254-258`) and
   `schema.py` declares bare `JSONB` (`:2397`, `:1562`). The 020 test's `_type_signature`
   (`:131-143`) falls through to `(type(type_).__name__, None)` for both, so it reported
   `("JSONB", None)` on both paths and the `astext_type` difference was invisible. `021`'s
   test compares `isinstance(type_, postgresql.JSONB)` and then
   `type_.astext_type`, which **will fail on the existing tables**. Resolution: align
   `schema.py` to `JSONB(astext_type=Text())` in the same commit as `021` (or drop
   `astext_type` from `021`'s own columns, consistently). Leaving the mismatch is not an
   option, because the new columns must be declared the same way in both paths.

---

## D7 — Tenant scoping and immutability

### D7.1 Tenant scoping

**Structurally.** All 23 added columns land on tables that already carry `tenant_id NOT NULL`
plus a `tenant_id <> ''` CHECK — `relation_signal` and `relation_candidate` from
`020:267`/`020:327`, `relation_claim` from 016, `validation_findings` from `018:191-202`
(`ck_validation_finding_tenant`, `schema.py:1569`). `021` creates no table, so it introduces
no new tenant surface. Every one of the six new indexes leads with `tenant_id` (D4.1). **`021`
adds no global/shared row and no nullable tenant.**

**In the store.** The 23 columns are only half the tenant question; the other half is whether
the new reads filter. Required mechanically rather than by review: a test that parses the new
store module's `select(` call sites and asserts **every** one carries a `tenant_id`
predicate, on the pattern of `by_participant` (`relation_claim_store.py:432-433`) and
`_verdict_query` (`:529`, `:534`). D9, FR-155,
`test_no_query_in_the_new_store_omits_a_tenant_predicate`.

`021` does not make the store tenant-safe; it makes the store *usable*, and the store's
tenant discipline is FR-048 and the store's own claim (`:299-306`): "Every query filters on an
explicit ``tenant_id``, so a cross-tenant read returns nothing rather than another tenant's
row (FR-048)." That claim is currently **unverified**, because the store has zero importers.
Reported as such.

### D7.2 Immutability

`input.md:2825` (verbatim): "**never drop historical semantic observations**".

`.specify/memory/constitution.md:6` (Principle I), verbatim:

> "Every observation is immutable once recorded. Raw objects are stored content-addressable
> (s3://knowledge/raw/{prefix}/{sha256}) and remain available independently of any downstream
> projection. **Nothing downstream may edit an observation.**"

`.specify/memory/constitution.md:65` (Additional Constraints), verbatim:

> "**Dead letter / quarantine** for malformed data, repeated parser failures, policy
> uncertainty, resource abuse, unsupported formats; **rejected candidates are never
> auto-deleted (replay/re-evaluation supported)**."

How `021` guarantees all three, given that it *drops three constraints* — which is the point
a reviewer will challenge:

1. **Dropping a CHECK drops a rule, not a row.** `DROP CONSTRAINT` on a check constraint
   removes a predicate from the table's validation and removes nothing else: no row is
   deleted, no value altered, no observation rewritten. This distinction is what the whole
   §16 change turns on, and it must be stated in `021`'s docstring in those words.
2. **`021` emits no `UPDATE`, no `DELETE`, no `TRUNCATE`, no `drop_table`, no `drop_column`.**
   Asserted by P12 and P13 over the recorded operation stream and the file's SQL text. The
   only `DROP`s in `021` are three `drop_constraint(..., type_="check")` calls.
3. **The narrowing in D2.4 is refused, not worked around.** The temptation is to `UPDATE` a
   legacy `negation` row into `lexical` so the whitelist applies. That is forbidden by (1),
   and `021` instead aborts with a documented pre-flight. **The migration failing is the
   correct outcome**; the alternative is silent corruption of a record of what was seen.
4. **Exactly one `UPDATE` is permitted anywhere in this schema family**, and `021` does not
   issue it: `SqlRelationClaimStore.record_validation` writing `validation_record`
   (`relation_claim_store.py:487`). The justification is real: a claim revision is **not an
   observation** — Principle I binds observations — and a verdict *about* an immutable claim is
   a separate fact appended in place, carrying its own `recorded_at` (`:271`). It touches no
   column in `content_hash`, which R8 asserts. The requirement being honoured is
   `.specify/memory/constitution.md:73`: "Rejected analysis outputs … are preserved with
   decision, reasons, score vectors, versions, and timestamps for replay."
5. **"Rejected candidates are never auto-deleted"** is guaranteed *structurally* by `021`
   adding `ix_relation_candidate_status` (D4.1 #4) and by the new store having **no delete
   path at all**. Asserted mechanically: `test_the_new_store_exposes_no_delete`
   (`not hasattr(store, "delete")`, plus a source scan for `delete(` / `DELETE ` against the
   three 020 tables). A preserved rejection must be *findable* — that is D4.1 #4's reason,
   and findability is what replay and re-evaluation need.
6. **`SC-012` and immutability do not conflict**, and the reason is worth recording: `021`
   *widens* what is storable (two disjuncts added per table) and *narrows* only the kind
   vocabulary, with a refusal rather than a rewrite. The net effect on stored history is
   **strictly additive**.

---

## D8 — `downgrade()`

### D8.1 The decision

**`021.downgrade()` refuses, unconditionally, before emitting any operation.** Not
selectively, and not partially.

```python
def downgrade() -> None:
    """Refuse. 021 widens what may be recorded and narrows one vocabulary; neither is
    reversible without destroying a record of what was seen.

    020's refusal is a constitutional argument rather than a technical limitation
    (``phase0-results.md`` §2 says so explicitly), and 021 inherits it. Dropping the
    signature columns is the sharpest case: ``predicate_signature_key`` is the term that
    replaces ``relation_surface`` in ``logical_candidate_id``, so a ``relation_candidate`` row
    that survived the drop would keep its id and lose the material that id was derived from.
    That is worse than losing the row, because the row still looks intact - a reader could
    not detect the loss, and Principle II ("Any knowledge must trace fully") would be
    unsatisfiable rather than visibly broken.

    ``relation_claim.candidate_id`` is the same case one level up: it is in
    ``RelationClaim._material()`` and therefore in ``content_hash``, so dropping it makes
    every stored claim's content hash unverifiable. ``validation_record`` cannot be dropped
    either, because a verdict is a preserved rejection and the constitution requires rejected
    analysis outputs to be kept for replay.

    The indexes are the one part that *is* mechanically reversible, and they are still not
    dropped: a downgrade that drops the indexes and then raises leaves a database matching no
    revision at all, which is strictly worse than an honest refusal and leaves Alembic's
    version table disagreeing with the schema. Partial execution is the failure mode here,
    not partial destructiveness.

    Rolling back is a forward operation. Add revision 022 that states what the schema becomes
    instead.
    """
    raise NotImplementedError(
        "021_relation_extraction_finalization is forward-only: predicate_signature_key and "
        "predicate_normalized are identity material for logical_candidate_id, "
        "relation_claim.candidate_id is inside content_hash, and validation_record is a "
        "preserved verdict - dropping any of them leaves stored rows that still look intact "
        "while the material their identity was derived from is gone. The three replaced CHECK "
        "constraints are replaced rather than deleted for the same reason in reverse: the old "
        "rule is a record of what the platform once believed was storable. Add a forward "
        "revision instead."
    )
```

### D8.2 Why "refuse selectively" was considered and rejected

The tempting middle option is: drop the six indexes (lossless, recreatable) and refuse the
rest. Rejected for one reason, and it is a good one:

**A partially-applied downgrade produces a schema that matches no revision.** Alembic's
`downgrade` either completes and stamps the version, or raises and leaves it. Dropping six
indexes and *then* raising means the version table still says `021` while the index set is
020's-plus-columns-minus-indexes — a state neither install path can produce and no test can
reconstruct. The operator's next action is a manual repair. An unconditional refusal leaves a
database that is exactly at `021`, a state the operator understands and `alembic current`
reports truthfully.

The same argument generalises to `020`'s own reasoning, and it is worth noting that `020` never
contemplated a partial downgrade either — its `downgrade()` is a bare `raise` (`:400-407`).
**Consistency with the revision being stacked on is itself a review criterion:** a `021` whose
downgrade is subtler than `020`'s invites the question of which of the two is the real policy.

### D8.3 The refusal must be testable *before* the raise

The 020 test only checks the message (`020-test:286-290`). That is not enough for `021`, whose
refusal is specifically "no operation is emitted". P24 asserts the property the 020 model
misses:

```python
def test_downgrade_refuses_before_emitting_any_operation() -> None:
    module = _load_migration()
    recorder = _OpRecorder()
    module.op = recorder
    with pytest.raises(NotImplementedError):
        module.downgrade()
    assert recorder.operations == [], (
        "downgrade() must refuse before touching anything: a partial downgrade leaves a "
        "schema that matches no revision"
    )
```

---

## D9 — New FR text, verbatim, from `FR-150`

Appended to `spec.md` in the "Verified 019 defects requiring substrate work" section, after
`FR-100`. The `101`–`149` range is owned by other repair jobs.

---

- **FR-150**: `021` MUST drop `ck_relation_signal_asserts_something` and
  `ck_relation_candidate_asserts_something` and replace both. The replacement on
  `relation_signal` MUST be
  `observational_basis IS NOT NULL OR relation_surface <> '' OR relation_ref IS NOT NULL`,
  together with `ck_relation_signal_predicate_text_basis`
  (`observational_basis IS DISTINCT FROM 'predicate_text' OR relation_surface <> '' OR relation_ref IS NOT NULL`)
  and `ck_relation_signal_observational_basis` (a closed vocabulary of the nine bases named by
  §16). The replacement on `relation_candidate` MUST be
  `relation_surface <> '' OR relation_ref IS NOT NULL OR predicate_signature_key IS NOT NULL OR (signal_refs IS NOT NULL AND jsonb_array_length(signal_refs) > 0)`.
  The two rules MUST differ: a signal has an observation channel and a candidate has none, so
  no single predicate can serve both. Neither replacement MUST require a named predicate, and
  neither MUST contain the literal `co_occurrence`. Each replacement MUST be a strict superset
  of the constraint it replaces, so that no stored row can become invalid. (§16, §40, §13)
  *Tests:* `test_the_two_asserting_constraints_are_dropped_by_name`,
  `test_each_replacement_is_a_strict_superset_of_the_check_it_replaces`,
  `test_the_replacement_never_mentions_co_occurrence`,
  `test_the_replacement_never_requires_a_named_predicate`.
- **FR-151**: `021` MUST add `relation_signal.observational_basis String(24) NULL` and the
  domain type `SignalBasis` with exactly the nine members §16 names, and the signature
  components MUST be wholly present or wholly absent
  (`ck_relation_signal_signature_whole`, `ck_relation_candidate_signature_whole`), with
  `direction` exempt on the candidate side because it is already `NOT NULL`. A half-written
  signature MUST NOT be storable, because a signature present in part cannot yield the
  `logical_candidate_id` that claims to be derived from it. (§16, §18, §62)
  *Tests:* `test_the_observational_bases_are_exactly_the_live_signal_basis`,
  `test_a_half_written_signature_is_refused_by_the_recorded_check_text`.
- **FR-152**: `ck_relation_signal_kind` MUST be dropped and recreated over a whitelist of
  exactly fifteen members: `lexical`, `syntactic`, `structural`, `event`, `semantic`,
  `temporal`, `link`, `reference`, `table`, `list`, `metadata`, `attribute`, `hierarchy`,
  `schema`, `co_occurrence`. `coreference`, `quantity` and `negation` MUST be removed, and
  `020`'s list of thirteen MUST remain unchanged in `020`'s file. `SignalAspect`, moving
  `NEGATION`, `TEMPORAL`, `QUANTITY`, `COREFERENCE` and `UNCERTAINTY` out of `SignalKind`
  entirely, MAY be a later forward revision and MUST NOT be taken in `021`. Because the
  replacement narrows rather than widens, `021` MUST document a pre-flight `SELECT` that
  reports rows carrying a removed kind, MUST refuse rather than rewrite them, and MUST NOT
  issue an `UPDATE`, a `DELETE` or a transitional whitelist to make the constraint apply.
  (§15, §16, §62)
  *Tests:* `test_the_kind_constraint_is_dropped_and_recreated`,
  `test_the_whitelist_is_exactly_the_live_signal_kind`,
  `test_the_whitelist_lists_exactly_fifteen_members`,
  `test_020_still_lists_exactly_thirteen_and_021_lists_fifteen`,
  `test_the_migration_file_states_the_kind_narrowing_preflight`.
- **FR-153**: A durable home for a `ValidationResult` MUST exist, and it MUST be
  `relation_claim.validation_record JSONB NULL`. `SqlRelationClaimStore.record_validation` and
  `SqlRelationClaimStore.non_valid` MUST stop raising `NotImplementedError` as a consequence,
  and `CLAIM_JSONB_COLUMNS` MUST NOT gain the column, because it is the exclusion list the
  resolution scans against. `relation_claim` MUST NOT gain any other JSONB column while the
  resolution returns the first match in declaration order, or a verdict will be written into
  an unrelated column without a line of code changing. The column MUST be excluded from
  `RelationClaim._material()`, so that recording a verdict does not mint a new `relation_id`.
  One verdict per claim revision is declared sufficient, because the lifecycle validates once
  before admission; a second validation of the same `relation_id`, or the first non-test
  importer of the store, MUST trigger a forward revision adding an append-only
  `relation_claim_validation` table. (§59, §60, §62, §91)
  *Tests:* `test_the_verdict_home_resolves_without_a_database`,
  `test_relation_claim_carries_exactly_one_foreign_jsonb_column`,
  `test_the_verdict_column_is_not_identity_material`,
  `test_the_verdict_column_is_not_in_the_owned_jsonb_set`.
- **FR-154**: `021` MUST add `ix_relation_candidate_object`, `ix_relation_signal_object`,
  `ix_relation_claim_candidate`, `ix_relation_candidate_status`,
  `ix_relation_candidate_signature` and `ix_validation_finding_candidate`, and every index
  it creates MUST lead with `tenant_id`. `by_signal` on the candidate side MUST be served by a
  filter over the tenant's candidates and NOT by an index, because no plain btree serves JSONB
  containment and a tenant-prefixed GIN would require a `btree_gin` extension this repository
  does not declare; the resulting O(candidates in tenant) cost MUST be reported as a known
  limitation, not presented as a design win. (§59, §62)
  *Tests:* `test_every_index_021_adds_leads_with_tenant_id`,
  `test_the_index_names_and_column_lists_match_the_orm`,
  `test_no_index_021_adds_is_built_without_a_tenant_prefix`.
- **FR-155**: `021` MUST be tenant-scoped and MUST NOT drop a historical semantic observation.
  It MUST emit no `UPDATE`, `DELETE`, `TRUNCATE`, `drop_table` or `drop_column`; its only `DROP`
  operations MUST be `drop_constraint(..., type_="check")`, which removes a rule and not a row.
  Every column it adds MUST land on a table that already carries `tenant_id NOT NULL` with a
  `tenant_id <> ''` CHECK, and `021` MUST create no table, no global row and no nullable
  tenant. Every query in the new store MUST filter on an explicit `tenant_id`. `020` MUST be
  pinned by content digest so that "020 MUST NOT be edited" is enforced rather than asserted,
  and `relation_signal`, `relation_candidate` and `source_temporal_observation` MUST be added
  to the live `OWNED_TABLES` drift check, which today omits all three. (§62, constitution I and
  VII)
  *Tests:* `test_no_statement_would_edit_a_row`,
  `test_no_table_and_no_column_is_dropped`,
  `test_no_check_is_dropped_outside_the_three_named`,
  `test_every_added_column_lands_on_a_table_that_already_carries_a_fail_closed_tenant`,
  `test_no_new_table_is_created`,
  `test_no_query_in_the_new_store_omits_a_tenant_predicate`,
  `test_020_is_pinned_by_digest`.
- **FR-156**: `validation_findings` MUST gain `candidate_id String(64) NULL` and
  `ix_validation_finding_candidate (tenant_id, candidate_id)`, so that a finding about an
  unadmitted candidate has somewhere to attach, and a candidate-stage finding MUST NOT
  fabricate an `assertion_ref` to satisfy its `NOT NULL`. A finding about a **claim** MUST
  continue to attach through the existing `assertion_ref` plus
  `ix_validation_finding_assertion`, and that path MUST NOT be duplicated by a second column.
  (§56, §59, §62)
  *Tests:* `test_a_candidate_stage_finding_never_fabricates_an_assertion_ref`,
  `test_a_claim_stage_finding_attaches_through_assertion_ref`.
- **FR-157**: `021.downgrade()` MUST raise `NotImplementedError` **before emitting any
  operation**, and MUST NOT drop even the lossless indexes, because a downgrade that drops
  some objects and then refuses leaves a database matching no revision. The refusal MUST name
  `predicate_signature_key`, `predicate_normalized`, `relation_claim.candidate_id` and
  `validation_record` as the four things that cannot be reversed, on the grounds that
  `predicate_signature_key` is the term `logical_candidate_id` is derived from and
  `relation_claim.candidate_id` is inside `content_hash`, so dropping either leaves stored
  rows that still look intact while the material their identity came from is gone. Rolling back
  remains a forward operation. (§62)
  *Tests:* `test_downgrade_refuses_before_emitting_any_operation`,
  `test_the_refusal_names_what_would_be_lost`.
- **FR-158**: ORM/migration parity, schema invariant and round-trip tests MUST exist for `021`
  and MUST compare CHECK constraints **by text and not only by name**, because a vocabulary
  that changes on one install path and not the other leaves the constraint *names* identical
  and is therefore invisible to a name-only comparison. The parity test MUST compare each
  vocabulary literal against the **live value type** and not against a count. Offline
  verification MAY prove: the recorded operation stream, per-column agreement of name, type,
  nullability and server default, check text, index lists, the whitelist against the enum, the
  absence of any row-editing statement, the downgrade refusal, domain `to_dict`/`from_dict`
  round trips, the row-builder output, and that a verdict home resolves from ORM metadata
  alone. It MUST NOT be reported as verified, and MUST be reported separately, anything
  requiring a live PostgreSQL: that the DDL is accepted; that the narrowed kind whitelist
  applies to a database holding legacy removed kinds; that `jsonb_array_length` and
  `IS DISTINCT FROM` behave as assumed inside a CHECK; that `alembic upgrade head` reaches a
  single head; that the new indexes are used; and any real store round trip. `SC-012` MUST be
  reported clause by clause — constructible `verified`, assemblable `verified`, persistable
  `verified only offline` — and never as a single `verified`. (§62, §91, §114)
  *Tests:* `test_the_columns_agree_with_the_orm`,
  `test_the_check_constraints_agree_with_the_orm_by_text`,
  `test_the_signature_survives_a_domain_round_trip_field_by_field`,
  `test_a_candidate_assembled_only_from_co_occurrences_is_storable_by_the_row_builder`,
  `test_a_co_occurrence_signal_is_accepted_by_the_database` *(live; skipped without
  PostgreSQL)*.

---

## D10 — Artefact line ranges that must change

Exact old text, exact new text. Line numbers are HEAD `0056665`.

### D10.1 `data-model.md` §7 (lines 246–266)

**Old (`:246-258`), verbatim:**

```
## 7. Persistence mapping (migration `021`)

`020_universal_relation_extraction` is the current Alembic head and is forward-only
(`downgrade()` raises `NotImplementedError`). `020` is not edited. `021` adds:

| Table | Added columns | FR |
|---|---|---|
| `relation_signal` | `predicate_normalized`, `predicate_arity`, `predicate_roles`, `predicate_argument_shapes`, `predicate_direction`, `predicate_polarity`, `predicate_alternatives`, `predicate_mapping_evidence` | FR-087 |
| `relation_candidate` | same signature set, plus `signal_refs`, `direction`, `polarity`, `confidence`, `predicate_alternatives`, `predicate_mapping_evidence` | FR-087, FR-088 |
| `relation_claim` | `candidate_id` | FR-088 |
| `source_temporal_observation` | a repository, writer and reader — the table has **none** today | FR-096 |

ORM/migration parity is test-enforced for `020` and MUST stay enforced for `021`.
```

**New:**

```
## 7. Persistence mapping (migration `021`)

`020_universal_relation_extraction` is the current Alembic head and is forward-only
(`downgrade()` raises `NotImplementedError`). `020` is not edited. `021` **adds 23 columns,
adds 6 indexes, creates no table, backfills nothing, and replaces three CHECK constraints.**

**`021` is not additive-only.** `020` carries three constraints that forbid the feature's own
headline behaviour, and because `020` is immutable they can only be changed forward:

| Constraint | Table | Old text | Operation in `021` |
|---|---|---|---|
| `ck_relation_signal_asserts_something` | `relation_signal` | `relation_surface <> '' OR relation_ref IS NOT NULL` | DROP, replaced by the observational-basis rule (§16) |
| `ck_relation_candidate_asserts_something` | `relation_candidate` | `relation_surface <> '' OR relation_ref IS NOT NULL` | DROP, replaced by the four-ground rule; **the two replacements differ**, because a signal has an observation channel and a candidate has none |
| `ck_relation_signal_kind` | `relation_signal` | a whitelist of 13 literals | DROP, recreated over 15 literals (3 removed, 5 added) |

The first two replacements are each a **strict superset** of the constraint they replace, so
no stored row can become invalid. The third **narrows**, so `021` documents a pre-flight
`SELECT` for rows carrying a removed kind and refuses rather than rewriting them: those rows
are observations, and Principle I forbids editing one.

### 7.1 Added columns

| Table | Added columns | Null | Class | FR |
|---|---|---|---|---|
| `relation_signal` | `predicate_signature_key`, `predicate_normalized`, `predicate_arity`, `predicate_roles`, `predicate_argument_shapes`, `predicate_polarity`, `predicate_alternatives`, `predicate_mapping_evidence`, `observational_basis` | all NULL, no default | 6 identity-bearing, 2 revision material, 1 basis attestation | FR-087, FR-150, FR-151 |
| `relation_candidate` | `predicate_signature_key`, `predicate_normalized`, `predicate_arity`, `predicate_roles`, `predicate_argument_shapes`, `direction`, `polarity`, `signal_refs`, `predicate_alternatives`, `predicate_mapping_evidence`, `confidence` | all NULL except `confidence` (NOT NULL, default `0.5`) | 7 identity-bearing, 3 revision material, 1 mutable projection | FR-087, FR-088 |
| `relation_claim` | `candidate_id` (NOT NULL, default `''`), `validation_record` (JSONB, NULL) | — | `candidate_id` identity-bearing and **already inside `content_hash`**; `validation_record` decision metadata, **deliberately outside it** | FR-088, FR-153 |
| `validation_findings` | `candidate_id` (NULL) | — | attachment for a candidate-stage finding | FR-156 |
| `source_temporal_observation` | none — a repository, writer and reader, which the table has **none** of today | — | — | FR-096 |

**Two columns the previous table listed are gone, deliberately.** `predicate_direction` is
**not** added to `relation_signal`, because `relation_signal.direction` already exists, is
`NOT NULL`, and already carries a closed-vocabulary CHECK: a second direction column is a
second column that can disagree with the first. On `relation_candidate` the signature's
direction and polarity are added **once each**, under the names FR-088 requires (`direction`,
`polarity`); `predicate_direction` and `predicate_polarity` are not added there either.

**`observational_basis` is new to this document.** It is the column that makes "every signal
MUST have an explicit observational basis" (§16) expressible as a constraint, and it needs a
domain type `SignalBasis` carrying exactly the nine bases §16 names. **No artefact mentions
either.** T051 cannot be ordered before the signal-contract work.

**Deferred to `022`, recorded here so the omission reads as a decision:** brief §13's n-ary
`participants`. `020`'s `ck_relation_candidate_distinct` and `ix_relation_candidate_pair` are
defined over the binary shape, and widening them means rewriting rows that hold observations,
which Principle I forbids. `022` **adds** `participants` and retires the binary CHECKs
forward, leaving `subject_mention_ref`/`object_mention_ref` in place as the compatibility
accessors §13 permits.

ORM/migration parity is test-enforced for `020` and MUST stay enforced for `021` — **and the
parity test MUST compare CHECK constraints by text, not only by name**, because a vocabulary
that changes on one install path and not the other leaves the names identical.
```

**Old (`:260-266`), verbatim:**

```
**Today, three tables are written by nothing.** No `INSERT` for `relation_signal`,
`relation_candidate` or `source_temporal_observation` exists anywhere in `apps/`, `bench/` or
`tools/`. `SqlRelationClaimStore` (558 lines) has zero importers, and its
`record_validation`/`non_valid` raise `NotImplementedError` because migration 016 never created
a home for a verdict. Persistence is the largest single block of work in this feature and the
one where "verified" and "verified only offline" will differ, because live PostgreSQL is not
reachable in this environment.
```

**New** — the first sentence stays verbatim (it is still true); the rest is replaced, because
the verdict-home half is now a decision rather than an open problem, and because the sentence
as written omits the failure mode that actually bites:

```
**Today, three tables are written by nothing.** No `INSERT` for `relation_signal`,
`relation_candidate` or `source_temporal_observation` exists anywhere in `apps/`, `bench/` or
`tools/`. Persistence is therefore the largest single block of work in this feature — and
**`021` that adds 23 columns no code writes reproduces the defect it was created to fix**, so
the migration MUST be ordered after the value types it stores (`PredicateSignature`,
`Polarity`, `SignalBasis`) and after the domain fields it mirrors.

`SqlRelationClaimStore` (558 lines) has zero importers. Its `record_validation`/`non_valid`
raise `NotImplementedError` because migration 016 never created a home for a verdict, and the
store names the column it wants in the error message itself. `021` creates that home forward
(`relation_claim.validation_record`); the store's own `_validation_column()` resolves it from
ORM metadata, so **the disappearance of `NotImplementedError` is provable without a
database**. Leaving it unfixed is not a stable state: the resolution scans for the first
non-owned JSONB column, so the day any other JSONB column lands on `relation_claim` the
verdict is written into it with no code change. See FR-153.

Persistence is the one area where "verified" and "verified only offline" differ, because live
PostgreSQL is not reachable in this environment — see FR-158 for the exact clause-by-clause
split, including `SC-012`.
```

### D10.2 `research.md` R-005 (lines 187–212)

**Old (`:196-208`), verbatim:**

```
`021` adds, per FR-087/FR-088/FR-096: `predicate_signature` columns on `relation_signal` and
`relation_candidate` (normalised form, arity, role names, argument shape, direction, polarity);
`signal_refs`, `direction`, `polarity`, `confidence` on `relation_candidate`; `candidate_id` on
`relation_claim`; structured columns for `PredicateHypothesis.alternative_refs` and
`mapping_evidence_refs`; and a repository/writer/reader for `relation_signal`,
`relation_candidate` and `source_temporal_observation`, which today have **no repository
class at all** — no `INSERT` for any of the three exists anywhere in `apps/`, `bench/` or
`tools/`.

`SqlRelationClaimStore` (558 lines) has zero importers and its `record_validation`/`non_valid`
raise `NotImplementedError` because migration 016 never created a JSONB home for a verdict.
`021` must either give the verdict a home or that store stays unusable — recorded as a real
decision, not an oversight.
```

**New:**

```
`021` adds, per FR-087/FR-088/FR-096: the `predicate_signature` column set on
`relation_signal` and `relation_candidate` (key, normalised form, arity, role names, argument
shape, polarity — **direction and polarity are added once each on the candidate, under the
names FR-088 requires, and are not duplicated**; the signal's direction is the column that
already exists); `signal_refs`, `direction`, `polarity`, `confidence` on `relation_candidate`;
`candidate_id` on `relation_claim`; `candidate_id` on `validation_findings`;
`observational_basis` on `relation_signal`; structured columns for
`PredicateHypothesis.alternative_refs` and `mapping_evidence_refs`; and a
repository/writer/reader for `relation_signal`, `relation_candidate` and
`source_temporal_observation`, which today have **no repository class at all** — no `INSERT`
for any of the three exists anywhere in `apps/`, `bench/` or `tools/`.

**`021` is not additive-only, and R-005 did not say so.** `020` carries three constraints
that forbid the feature's own headline behaviour, and `020` is immutable and forward-only, so
the only available remedy is a forward revision:

* `ck_relation_signal_asserts_something` and `ck_relation_candidate_asserts_something` both
  enforce `relation_surface <> '' OR relation_ref IS NOT NULL`. `SC-012` requires a
  co-occurrence signal to be constructible, **persistable and assemblable** — and an
  assembled candidate made only of co-occurrence signals is refused by the *candidate* check
  as much as the signal is by its own. Both MUST be dropped and replaced, and the replacements
  **differ**: a signal has a `signal_kind` and a candidate has none. Each replacement is a
  strict superset of what it replaces, so no stored row can become invalid.
* `ck_relation_signal_kind` whitelists 13 literals. Three are removed
  (`coreference`/`quantity`/`negation`) and five added (`syntactic`/`structural`/`event`/
  `semantic`/`temporal`), giving 15. This one **narrows**, so `021` documents a pre-flight
  `SELECT` and refuses rather than rewriting a stored row — those rows are observations, and
  Principle I forbids editing one.

**The `TEMPORAL` contradiction, resolved.** FR-011 says `SignalKind` MUST contain `TEMPORAL`;
`data-model.md` §2 and checklist C2 say it must not be added. This research adopts **FR-011**:
a `MUST` derived from the brief's own §15 outranks a Phase 2 inspection row, and
`data-model.md`'s stated reason for exclusion is about *where temporal facts are stored*
(`stated_axes`, `source_temporal_observation` — both already exist), not about whether a
producer may notice time as a channel. The argument that made `NEGATION` a kind is
**discharged** by the new `predicate_polarity` column, which is why `NEGATION` leaves the
vocabulary; the parallel argument for `TEMPORAL` is not discharged, so `TEMPORAL` stays. A
`TEMPORAL` signal must carry a `stated_axes` or `temporal_evidence` reference, so the kind is a
channel and never a container. The residual aspect ambiguity is FR-012's `SignalAspect` and is
deferred to a later forward revision, not smuggled into `021`.

**Ordering, which R-005 did not state.** `021` cannot be written before `PredicateSignature`,
`Polarity` and `SignalBasis` exist. The ORM path imports the value type (`schema.py:23-27`)
and the migration path writes literals (`020:66-69`); a CHECK written against an enum that
does not exist cannot be mirrored, and 23 columns with no writer reproduce the exact defect
this feature exists to remove. `SignalBasis` is new to this repair: nine members, verbatim
from §16, and named by no artefact until now.

**Verdict home, decided rather than deferred.** `021` adds
`relation_claim.validation_record JSONB NULL`. The store's `_validation_column()` resolves a
verdict home by scanning ORM metadata for the first non-owned JSONB column, and its own
`NotImplementedError` message names this column — so the 558-line store becomes usable with
**no code change**, and the refusal disappears, provably, **without a database**. Leaving it
unfixed is not a stable state: a later JSONB column on `relation_claim` would capture the
verdict silently. One verdict per claim revision is declared sufficient because the lifecycle
validates once before admission; an append-only `relation_claim_validation` table is recorded
as the correct long-term shape, triggered by a second validation of the same `relation_id` or
the store's first non-test importer.

`by_signal` on the candidate side is **not indexed**, and the reason is a real limitation
rather than a design win: `signal_refs` is JSONB, no plain btree serves containment, and a
tenant-prefixed GIN would need a `btree_gin` extension this repository does not declare. The
lookup is a filter over the tenant's candidates, on the same pattern as the shipped
`by_participant`, and is reported as O(candidates in tenant).

**Live PostgreSQL is not reachable in this environment.** All DB verification is therefore
offline: ORM/DDL parity, in-memory round trip, and migration text assertions. Anything needing
a live round trip is reported `verified only offline` and never as `verified` (FR-084). For
`021` the offline/online split is enumerated item by item in FR-158, and `SC-012` is reported
clause by clause rather than as one verdict.
```

### D10.3 `spec.md` — FR-059, FR-060, FR-062, FR-087, FR-088, FR-097

**FR-059, old (`:614-616`), verbatim:**

```
- **FR-059**: Durable store seams MUST exist for `RelationSignal`, `RelationCandidate` and
  `SourceTemporalObservation` with `write`, `get`, `by_tenant`, `by_logical_id`, `by_pair`,
  `by_signal` and checksum/replay support where architecturally appropriate. (§59)
```

**New:**

```
- **FR-059**: Durable store seams MUST exist for `RelationSignal`, `RelationCandidate` and
  `SourceTemporalObservation` with `write`, `get`, `by_tenant`, `by_logical_id`, `by_pair`,
  `by_signal` and checksum/replay support where architecturally appropriate. `by_signal` on
  the candidate side MAY be served by a filter over the tenant's candidates rather than an
  index, because `signal_refs` is JSONB, no plain btree serves containment, and a
  tenant-prefixed GIN would require a `btree_gin` extension this repository does not declare;
  where it is, the O(candidates in tenant) cost MUST be reported as a known limitation.
  `by_logical_id` is not architecturally appropriate for `RelationSignal` or
  `SourceTemporalObservation`, which have no logical id, and their nearest equivalents —
  `ix_relation_signal_producer` and `ix_temporal_observation_capture` — already exist.
  (§59, §154)
```

**FR-060, old (`:617-621`), verbatim:**

```
- **FR-060**: Every store MUST reconstruct the exact domain object. A round trip MUST
  preserve ids, alternatives, signals, provenance, type hypotheses, predicate signature,
  temporal evidence, tenant, context and regime. A digest may identify data; a digest MUST
  NOT be the only copy required for reconstruction. Every new substrate object MUST have a
  build → store → read test asserting that list, not a summary string. (§59, §60, §91)
```

**New** — one clause is needed, because `predicate_signature_key` is exactly a digest and
FR-087 requires the components beside it:

```
- **FR-060**: Every store MUST reconstruct the exact domain object. A round trip MUST
  preserve ids, alternatives, signals, provenance, type hypotheses, predicate signature,
  temporal evidence, tenant, context and regime. A digest may identify data; a digest MUST
  NOT be the only copy required for reconstruction. Where the identity carrier is a digest —
  `predicate_signature_key` — the components it summarises MUST be stored in their own columns
  beside it, so that `SC-008` is answerable by reading the row rather than by re-deriving a
  hash. Every new substrate object MUST have a build → store → read test asserting that list,
  not a summary string. (§59, §60, §91)
```

**FR-062, old (`:627-631`), verbatim:**

```
- **FR-062**: A new forward-only migration MUST be created if required. Applied migrations
  MUST NOT be modified. It MUST preserve data, be tenant-scoped, add CHECKs only for
  constitutional invariants, keep ORM/migration parity, and never drop historical semantic
  observations. Migration parity tests, schema invariant tests and round-trip tests MUST be
  created. (§62)
```

**New:**

```
- **FR-062**: A new forward-only migration MUST be created if required. Applied migrations
  MUST NOT be modified. It MUST preserve data, be tenant-scoped, add CHECKs only for
  constitutional invariants, keep ORM/migration parity, and never drop historical semantic
  observations. Migration parity tests, schema invariant tests and round-trip tests MUST be
  created. Migration parity tests MUST compare CHECK constraints by text and not only by
  name, because a vocabulary that changes on one install path and not the other leaves the
  constraint names identical; and they MUST compare each vocabulary literal against the live
  value type rather than against a count. "Preserve data" MUST be argued per constraint: a
  replacement that is a strict superset of what it replaces cannot invalidate a stored row,
  and a replacement that **narrows** MUST be paired with a documented pre-flight and a refusal
  rather than a rewrite. A forward-only migration MUST NOT partially downgrade — its
  `downgrade()` MUST refuse before emitting any operation, including the lossless operations —
  because a partially applied downgrade leaves a schema matching no revision.
  (§62, §150, §152, §157, §158)
```

**FR-087, old (`:724-727`), verbatim:**

```
- **FR-087**: A `predicate_signature` MUST be persisted in its own columns on both
  `relation_signal` and `relation_candidate` — normalised form, arity, role names, argument
  shape, direction and polarity — so that candidate identity no longer depends on a raw
  surface string and `PredicateHypothesis` is not stored as an opaque digest. (§59, §60, §91)
```

**New:**

```
- **FR-087**: A `predicate_signature` MUST be persisted in its own columns on both
  `relation_signal` and `relation_candidate` — normalised form, arity, role names, argument
  shape, direction and polarity — so that candidate identity no longer depends on a raw
  surface string and `PredicateHypothesis` is not stored as an opaque digest. The signature's
  direction and polarity MUST each be stored **once**: on `relation_signal` the existing
  `direction` column carries the direction, and on `relation_candidate` the columns are named
  `direction` and `polarity` per FR-088. A second column for a fact that already has one is a
  column that can disagree with it. The components MUST be wholly present or wholly absent, and
  a digest of the signature MUST be stored beside them, never instead of them.
  (§59, §60, §91, §150, §151)
```

**FR-088, old (`:728-730`), verbatim:**

```
- **FR-088**: `relation_candidate` MUST gain columns for `signal_refs`, `direction`, `polarity`
  and `confidence`; `relation_claim` MUST gain `candidate_id`; and the store MUST write and
  read all of them. No field that participates in an id may be absent from the row. (§60, §91)
```

**New:**

```
- **FR-088**: `relation_candidate` MUST gain columns for `signal_refs`, `direction`, `polarity`
  and `confidence`; `relation_claim` MUST gain `candidate_id`; and the store MUST write and
  read all of them. No field that participates in an id may be absent from the row.
  `relation_claim.candidate_id` is already a domain field and is already inside
  `RelationClaim._material()` and therefore inside `content_hash`, so the column restores a
  fact the identity already depends on, and dropping it would make every stored claim's hash
  unverifiable. It is `NOT NULL` with a server default of `''` because `''` is the domain
  type's own way of stating that no candidate was named — not a fabricated value. The
  `direction` and `polarity` columns are nullable, because a candidate's signature is
  optional and a `NOT NULL` column would force a fabricated `ambiguous` into an unsigned row.
  (§60, §91, §157)
```

**FR-097, old (`:770-772`), verbatim:**

```
- **FR-097**: Migration `021` MUST be added on top of `020`, which is the current Alembic head
  and is forward-only. `020` MUST NOT be edited. `021` MUST add every column FR-087/FR-088
  require, and ORM/migration parity MUST stay test-enforced.
```

**New:**

```
- **FR-097**: Migration `021` MUST be added on top of `020`, which is the current Alembic head
  and is forward-only. `020` MUST NOT be edited. `021` MUST add every column FR-087/FR-088
  require, and ORM/migration parity MUST stay test-enforced. `021` is **not additive-only**:
  it MUST also drop and replace `ck_relation_signal_asserts_something`,
  `ck_relation_candidate_asserts_something` and `ck_relation_signal_kind`, because `020` is
  immutable and its constraints otherwise forbid `SC-012`. "020 MUST NOT be edited" MUST be
  enforced by pinning `020`'s content digest in `test_migration_forward_only.py`, which today
  pins only `014`; and `relation_signal`, `relation_candidate` and
  `source_temporal_observation` MUST be added to the live `OWNED_TABLES` drift check in
  `test_orm_migration_parity.py`, which today omits all three, so no live check covers the
  tables `020` created. `021` MUST NOT be committed before the value types it stores exist.
```

### D10.4 `spec.md` — `SC-012` (lines 895–896)

**Old, verbatim:**

```
- **SC-012**: A co-occurrence signal with an empty `relation_surface` is constructible,
  persistable and assemblable.
```

**New:**

```
- **SC-012**: A co-occurrence signal with an empty `relation_surface` is constructible,
  persistable and assemblable; and a candidate assembled only from co-occurrence signals is
  itself storable, because it states its basis through `signal_refs` rather than through a named
  predicate. The three clauses MUST be reported **separately** — constructible and assemblable
  are provable offline, persistable is not — and `SC-012` MUST NOT be reported as a single
  `verified` while live PostgreSQL is unreachable. (§16, §150)
```

The added sentence is the half nobody had written: **the candidate side is the binding half,
because `assemblable` is what `021` actually had to unblock.**

### D10.5 `db/schema.py` — the `negation` comment (`:2432-2437`)

Not a spec artefact, but a code comment `021` makes false, and `FR-098` names the failure mode
of leaving it.

**Old, verbatim:**

```python
        # The kinds are the platform's whole capacity for noticing a relation, so they are
        # stated in the schema where a reviewer reads them rather than derived from
        # somewhere it would look incidental. `negation` being here is load-bearing:
        # without it, "Acme did not acquire Beta" is either dropped - losing an observed
        # fact - or recorded as an acquisition, which is a lie with a schema.
        CheckConstraint(_in("signal_kind", SignalKind), name="ck_relation_signal_kind"),
```

**New:**

```python
        # The kinds are the platform's whole capacity for noticing a relation, so they are
        # stated in the schema where a reviewer reads them rather than derived from
        # somewhere it would look incidental. `negation` was here because "Acme did not
        # acquire Beta" would otherwise be either dropped - losing an observed fact - or
        # recorded as an acquisition, which is a lie with a schema. Migration 021 removes it,
        # because that argument is now discharged by a column: a denial is
        # `predicate_polarity = 'denied'`, which is a fact about the reading rather than a
        # separate channel pretending to be one.
        CheckConstraint(_in("signal_kind", SignalKind), name="ck_relation_signal_kind"),
```

### D10.6 `checklists/requirements.md` — H1–H11, plus the missing rows

H1–H11 are **kept**, with these edits. Method key (`:7-8`): `T` automated test, `I`
inspection, `M` mutation, `B` baseline, `P` production proof.

| # | Old text | New text |
|---|---|---|
| H1 | `` Migration `021` added on top of the forward-only `020`; `020` unedited `` | `` Migration `021` added on top of the forward-only `020`; `020` unedited **and pinned by content digest**, so the rule is enforced rather than asserted `` |
| H2 | `` `predicate_signature` columns on `relation_signal` and `relation_candidate` `` | `` `predicate_signature` columns on `relation_signal` and `relation_candidate`, **whole-or-absent**, with **no** `predicate_direction` on `relation_signal` — the existing `direction` column carries it `` |
| H3 | `` `signal_refs`, `direction`, `polarity`, `confidence` on `relation_candidate` `` | unchanged, plus: `confidence` defaults to `0.5`, matching `DEFAULT_CONFIDENCE`, not `0` |
| H4 | `` `candidate_id` on `relation_claim`, written and read by the store `` | unchanged, plus: `NOT NULL DEFAULT ''`, mirroring the domain field, which is already inside `content_hash` |
| H5 | `` `alternative_refs` and `mapping_evidence_refs` have real columns `` | unchanged |
| H6 | unchanged | unchanged |
| H7 | `` ORM/migration parity test-enforced for `021` `` | `` ORM/migration parity test-enforced for `021`, **comparing CHECK constraints by text and each vocabulary against the live enum**, not by name and not by count `` |
| H8 | unchanged | unchanged |
| H9 | `` Build → store → read test asserts the full field list per type `` | unchanged |
| H10 | unchanged | unchanged, plus: the `SC-012` split — constructible/assemblable `verified`, persistable `verified only offline` |
| H11 | unchanged | unchanged |

**New rows — the constraint DROPs and the operations K6 identified, none of which has a
checklist item today:**

| # | Item | Method | Task | State |
|---|---|---|---|---|
| H12 | `ck_relation_signal_asserts_something` and `ck_relation_candidate_asserts_something` are **dropped** and replaced, with the two replacements **differing** | T | T051 | ☐ |
| H13 | Neither replacement requires a named predicate, and neither mentions `co_occurrence`; each is a **strict superset** of the constraint it replaces | T | T051 | ☐ |
| H14 | `ck_relation_signal_kind` is dropped and recreated over **15** members; `020` still lists **13**; the narrowing is paired with a documented pre-flight that **refuses** rather than rewriting | T, I | T051 | ☐ |
| H15 | **Schema invariant tests** exist over `Base.metadata` — tenant NOT NULL + non-empty, no FK, no digest/`created_at` in a unique index, no constraint requiring a named predicate | T | T051 | ☐ |
| H16 | `relation_claim.validation_record` exists; `_validation_column()` resolves it **without a database**; `CLAIM_JSONB_COLUMNS` does not own it; no other JSONB column is added to `relation_claim` | T | T051, T052 | ☐ |
| H17 | `validation_findings.candidate_id` exists with its index, and a candidate-stage finding never fabricates an `assertion_ref` | T | T051 | ☐ |
| H18 | Every index `021` adds leads with `tenant_id`; `by_signal` is served without an index and its cost is reported as a known limitation | T, I | T051, T054 | ☐ |
| H19 | `021` emits no `UPDATE`/`DELETE`/`TRUNCATE`/`drop_table`/`drop_column`; its only `DROP`s are the three named CHECKs | T | T051 | ☐ |
| H20 | `020` is pinned by digest in `test_migration_forward_only.py`; the three 020 tables are in `OWNED_TABLES` | T | T051 | ☐ |
| H21 | `021.downgrade()` refuses **before emitting any operation** | T | T051 | ☐ |

**Also amend checklist C2** (`:46`), whose second clause contradicts FR-011:

| # | Old text | New text |
|---|---|---|
| C2 | `` `SignalKind` carries observation channels only; no `NEGATION`/`QUANTITY`/`COREFERENCE`; no `TEMPORAL` added `` | `` `SignalKind` carries observation channels only; no `NEGATION`/`QUANTITY`/`COREFERENCE`; **`TEMPORAL` added** per FR-011, and `SEMANTIC`/`STRUCTURAL`/`SYNTACTIC`/`EVENT` added with it; a `TEMPORAL` signal carries a `stated_axes` or `temporal_evidence` reference `` |

---

## 2. Task ordering this repair forces

The current task list has the migration in Phase 9 (T051–T053) and the value types earlier,
but the dependency is not expressed, and two dependencies are missing entirely.

| Order | Task | Must finish before |
|---|---|---|
| 1 | `SignalBasis` enum (9 members, `input.md:1125-1137`) — **new, no artefact names it** | any 021 CHECK work |
| 2 | `Polarity` enum + `relation_signal.polarity` field (T024) | `predicate_polarity` column and its CHECK |
| 3 | `PredicateSignature` + normalisation (T006/T029) | the whole `predicate_*` column set |
| 4 | `RelationCandidate.direction` / `.polarity` fields; `signal_refs` canonicalisation (T005) | the candidate columns and the four-ground replacement |
| 5 | `SignalKind` widened to 15 (T023, corrected per D3) | `ck_relation_signal_kind` replacement |
| 6 | **T051 — migration `021`** | the store tasks |
| 7 | T052 / T053 — store writes the new columns | the round-trip tests |
| 8 | T054 — repository/writer/reader | — |
| 9 | T057 — round-trip tests, reporting `verified only offline` | — |

Two **existing** dependencies are currently backwards or missing and this repair is where they
surface:

- T051 depends on the signal-contract and identity work, and nothing records it.
- T051's parity work touches `test_orm_migration_parity.py` and
  `test_migration_forward_only.py`, and no task owns either file.

---

## 3. The single most important statement in this document

> **`021` that adds 23 columns and no writer reproduces the exact defect it was created to
> fix.**

The whole feature exists because `spec.md:803` records that `relation_signal`,
`relation_candidate` and `source_temporal_observation` have "no repository, writer or reader at
all". The migration is the easy half; the store is the half that matters. D1 specifies the
columns precisely so the store has a stable target, and the parity tests exist so the two halves
cannot drift — but a green parity suite with an unwritten store is the same failure one
migration later, with 23 more columns.

---

## 4. Summary of every `op.` in `021.upgrade()`

| # | Operation | Target | Object |
|---|---|---|---|
| 1–9 | `op.add_column` | `relation_signal` | `predicate_signature_key`, `predicate_normalized`, `predicate_arity`, `predicate_roles`, `predicate_argument_shapes`, `predicate_polarity`, `predicate_alternatives`, `predicate_mapping_evidence`, `observational_basis` — all NULL, no default |
| 10 | `op.drop_constraint` | `relation_signal` | `ck_relation_signal_asserts_something`, `type_="check"` |
| 11 | `op.create_check_constraint` | `relation_signal` | `ck_relation_signal_asserts_something` (four grounds) |
| 12 | `op.create_check_constraint` | `relation_signal` | `ck_relation_signal_predicate_text_basis` |
| 13 | `op.create_check_constraint` | `relation_signal` | `ck_relation_signal_observational_basis` (9 members) |
| 14 | `op.create_check_constraint` | `relation_signal` | `ck_relation_signal_signature_whole` |
| 15 | `op.drop_constraint` | `relation_signal` | `ck_relation_signal_kind`, `type_="check"` |
| 16 | `op.create_check_constraint` | `relation_signal` | `ck_relation_signal_kind` (15 members) |
| 17–27 | `op.add_column` | `relation_candidate` | `predicate_signature_key`, `predicate_normalized`, `predicate_arity`, `predicate_roles`, `predicate_argument_shapes`, `direction`, `polarity`, `signal_refs`, `predicate_alternatives`, `predicate_mapping_evidence` (all NULL, no default), `confidence` (Float NOT NULL `DEFAULT 0.5`) |
| 28 | `op.drop_constraint` | `relation_candidate` | `ck_relation_candidate_asserts_something`, `type_="check"` |
| 29 | `op.create_check_constraint` | `relation_candidate` | `ck_relation_candidate_asserts_something` (four grounds) |
| 30 | `op.create_check_constraint` | `relation_candidate` | `ck_relation_candidate_signature_whole` |
| 31 | `op.create_check_constraint` | `relation_candidate` | `ck_relation_candidate_direction` (the 4 literals, nullable-tolerant) |
| 32 | `op.create_check_constraint` | `relation_candidate` | `ck_relation_candidate_polarity` (3 literals, nullable-tolerant) |
| 33 | `op.add_column` | `relation_claim` | `candidate_id`, String(64) NOT NULL `DEFAULT ''` |
| 34 | `op.add_column` | `relation_claim` | `validation_record`, JSONB NULL, no default |
| 35 | `op.add_column` | `validation_findings` | `candidate_id`, String(64) NULL, no default |
| 36–41 | `op.create_index` | 4 tables | the six indexes of D4.1, all leading with `tenant_id` |
| — | `downgrade()` | — | `raise NotImplementedError` before any operation |

**42 operations. 0 `create_table`, 0 `drop_table`, 0 `drop_column`, 0 `UPDATE`, 0 `DELETE`,
0 `op.execute`.** The seven `create_check_constraint` calls are steps 11–14, 16 and 29–32.

---

## 5. Disagreements register

Recorded per the job's instruction to state where I disagree with a premise.

| # | Premise as given | My position | Where it lands |
|---|---|---|---|
| 1 | "The two constraints enforce **the same predicate**" | True today, false for the replacement: a signal has a `signal_kind`, a candidate has none. **Two different replacement rules.** | D2.2, D2.3, D10.1 |
| 2 | "**The replacement**" (singular) | Two replacements, plus two new CHECKs on the signal side (`predicate_text_basis`, `observational_basis`) and two more (whole-or-absent) on both tables | D2.3, §4 |
| 3 | K6's three constraint operations | **Four** schema operations: the three DROPs **plus** the new `observational_basis` column that no artefact mentions | §0, D1.1 |
| 4 | "`validation_findings` has no `relation_id`/`candidate_id` column, **so a relation validation finding has nowhere to attach**" | **Overstated.** A *claim*-stage finding attaches today via `assertion_ref` (64 chars) + `ix_validation_finding_assertion` + `stage`. What genuinely has no home is a **candidate**-stage finding, because `assertion_ref` is `NOT NULL` with no default. The residue is **one column and one index** | D5.4, D1.4 |
| 5 | "`SC-012` … is unachievable as planned" | Correct, and **worse than K6 says**: the binding constraint is the *candidate* one, because "assemblable" is the clause that has nowhere to go | §0.1, D2.5, D10.4 |
| 6 | "The brief mandates `SYNTACTIC`, `STRUCTURAL`, `EVENT`, `SEMANTIC`, and the disputed `TEMPORAL`" | `TEMPORAL` is not a dispute between equals: FR-011 is a `MUST` from the brief and C2 is a Phase 2 inspection row. **`TEMPORAL` is adopted**, and `NEGATION` is dropped on a principled split, not a compromise | D3.2 |
| 7 | The four mandated members may be assumed mutually distinguishable | `HIERARCHY`/`STRUCTURAL` and `SCHEMA`/`SEMANTIC` are **near-synonyms at HEAD** (`signal.py:91-92`). I propose a split; it is **my** definition, not the brief's, and needs the brief owner | D3.2, §5 |
| 8 | "downgrade: refuse the same way, or refuse selectively" | **Refuse absolutely, before emitting anything.** "Selectively" is the worse option, because a partial downgrade leaves a schema matching no revision | D8.1, D8.2 |
| 9 | `020`'s test asserting `_SIGNAL_KINDS == 13` is a parity hazard | It is not a hazard — it loads `020` by path and will keep passing forever. The hazard is that **nothing compares either whitelist to the live enum**, and `schema.py:2437` follows the enum automatically | D3.4 |
| 10 | `020`'s `test_the_check_constraints_agree` is the model to extend | It compares constraint **names only**, so a whitelist that changes on one path and not the other is **invisible to it**. The 021 test must compare **text** | D6.1, D6.5 |
| 11 | The candidate side needs the same replacement as the signal side | It cannot: a candidate has no kind, and `SC-012` requires it to be storable with an empty surface, no ref and no signature. Its basis is `signal_refs` | D2.3, D2.5 |
| 12 | Implicit: `021` can be written now, from the artefacts | No. It needs `PredicateSignature`, `Polarity` and `SignalBasis`, none of which exist. `SignalBasis` is named by **no** artefact | D1.5, §2 |
| 13 | The instinct that every `op.add_column` should carry `existing_type=`, imported from `020` | **`020` uses `existing_type` on `alter_column`, not `add_column`.** `Operations.add_column` does not accept it; passing it is a `TypeError` at migration time. `021` adds no `alter_column`, so the argument must simply be absent. Caught while specifying D1 — `020`'s parity test standard does not transfer to a different operation | D1.0, D1.1, D1.3, P3 |

---

## 6. What this repair did not decide

- **Whether `SignalAspect` (FR-012) becomes a real type.** Deferred to a forward revision
  (FR-152). `021` only requires that a `TEMPORAL` signal carries a reference to the temporal
  facts, so the kind cannot become a container.
- **Whether brief §13's n-ary `participants` lands in `021` or `022`.** Decided for `022`,
  on Principle I grounds (D1.2), and recorded in `021`'s docstring so the omission reads as a
  decision.
- **The `btree_gin` question** (D4.3 option ii). Named as the upgrade path for `by_signal`;
  not taken, because a migration that needs superuser to create an extension has not earned
  it.
- **Whether `relation_claim` should gain an FK to `relation_candidate`** once
  `candidate_id` is a real column. Not taken: the 015/016/018/019 stance is no FKs
  (`schema.py:1604-1615`), and adopting one here would be a schema decision this feature has
  not earned.
- **The live behaviour of every CHECK.** Unreachable in this environment; enumerated in D6.4
  and required to be reported as "not verified" rather than "verified only offline", because
  "not verified" is the honest label for a claim that has never been executed.

