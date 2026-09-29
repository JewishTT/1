# P4C persistence — the ordered column and constraint list for migration `021`

**Authority**: `repair/ARBITRATION.md` §5 (phase order), §6 (n-ary persistence), §14 (FR
allocation). **Produced by**: Phase 4C, feature 021, 2026-09-28. **Status**: specification for
an implementer. **This file edits nothing** — no migration and no `db/schema.py` change is in
Phase 4C's remit, and this list is the hand-off that makes the next task executable without
re-deriving it.

---

## 0 — Read this first: three things that are *not* additive

Everything in §1 and §2 is an `op.add_column`. Everything in §3 is a `DROP` followed by a
`CREATE`, and two of the three constraint operations **narrow** rather than widen. `ARBITRATION`
§5 is the reason the phase is split the way it is: `P4A` added the domain fields while the
binary columns still worked, `P4B` migrated the seven producers and closed the door behind them,
and `P4C` is where the deletions and the drops land. This document is the `P4C` half of `021`.

**Phase order (`ARBITRATION` §5), and the dependency each step has:**

| Order | Step | Blocked by |
|---|---|---|
| 1 | the two `DROP CONSTRAINT`s in §3.1 and §3.2 | the two `NOT NULL` columns in §1.1 / §2.1 existing — the old constraint forbids the row `participants` makes legal |
| 2 | the `observational_basis` column (§1.2) | `domain.signal_basis.SignalBasis` existing — it does, `apps/shared/domain/signal_basis.py`, nine members |
| 3 | the `ck_relation_signal_observational_basis` and `ck_relation_signal_predicate_text_basis` CHECKs (§3.3) | step 2 |
| 4 | the `DROP`+`CREATE` of `ck_relation_signal_kind` (§3.5) | the pre-flight in §3.5.1 |
| 5 | the remaining `add_column`s | nothing |

`ARBITRATION` §5 also records the measured figure this phase rests on: **2 breaking lines**, not
12, which is why `4A`/`4B`/`4C` is green at all.

---

## 1 — `relation_signal`: four columns

Target table: `relation_signal` (created by `020`, `apps/control-plane/db/migrations/versions/
020_universal_relation_extraction.py:236`). `020` **MUST NOT be edited**; the ORM side is
`apps/control-plane/db/schema.py:2376`.

### 1.1 `participants` — the n-ary tuple, and the reason it is `NOT NULL`

| Property | Value |
|---|---|
| Type | `postgresql.JSONB(astext_type=sa.Text())` |
| Nullable | **`NOT NULL`**, no server default |
| Classification | **identity-bearing** — it is in `RelationSignal._material()` via `RelationParticipant.to_identity()` |
| Requirement | `ARBITRATION` §6, `FR-008` |
| Band | **unnumbered** — see §5.1 blocker B1 |

`ARBITRATION` §6 is explicit and this overrides A7: *"A7's 'no participants column in 021,
n-ary to 022' is REJECTED"*, it is **not** `extra`, and it is **not deferred to `022`**. The
canonical serialisation is the identity subsystem's participant ordering, so a stored
`participants` round-trips to an identical in-memory object and re-derives an identical
`signal_id`.

`subject_mention_ref` / `object_mention_ref` are **retained as compatibility accessors** and
become derived from `participants[0]` / `participants[1]`. They are never a second source of
truth; `RelationSignal.subject_mention_ref` is already a `@property` over the tuple
(`apps/interpretation/extractors/signals/signal.py`, installed by
`_install_derived_endpoint_accessors`).

> **STOP — the `NOT NULL` pre-flight.** A `NOT NULL` column with no default cannot be added to a
> table that holds rows, and the two ways round it — a `DEFAULT` and a backfill `UPDATE` — are
> both forbidden here: a default would fabricate a participant tuple, and Principle I
> (`input.md:2823`) forbids editing an observation. So `021` **MUST** carry a pre-flight
> `SELECT` alongside the one in §3.5.1, it **MUST** refuse rather than work around a non-zero
> count, and it **MUST NOT** issue an `UPDATE`, a `DELETE` or a transitional default:
>
> ```sql
> -- Pre-flight, run by an operator before `alembic upgrade head` reaches 021.
> -- A non-zero row count means 021 cannot add `participants NOT NULL` without writing a
> -- participant tuple nobody observed, and that refusal is correct.
> SELECT 'relation_signal' AS table_name, count(*) FROM relation_signal
> UNION ALL SELECT 'relation_candidate', count(*) FROM relation_candidate;
> ```
>
> **Measured, not assumed**: `A7-migration-021.md` D2.4 records that no `INSERT` into
> `relation_signal` exists anywhere in `apps/`, `bench/` or `tools/`, and no writer or repository
> exists for either table at all (`spec.md:803`). In every database this repository can produce
> the query returns zero rows. The pre-flight exists for a database somebody populated by other
> means, and its cost is one query.

### 1.2 `observational_basis` — the basis attestation

| Property | Value |
|---|---|
| Type | `sa.String(24)` |
| Nullable | nullable, **no** server default |
| Classification | **basis attestation** — the subject of the replaced constraint, and **not** identity material in its own right (`SignalBasis` *is* in `_material()`, so a stored basis participates in `signal_id`) |
| Requirement | `FR-014`, brief §16 |
| Band | `FR-150` / `FR-151` (A7) |

Width 24 is not a round number: `domain/signal_basis.py:MAX_BASIS_TOKEN_LENGTH` is **24** and is
published for exactly this purpose, sized from the longest member (`predicate_text` /
`metadata_field`, 14 characters). The nine values, in declaration order, which are also the
whitelist for §3.3:

```
predicate_text, dom_relation, table_slot, hyperlink, citation,
proximity, metadata_field, event_frame, attribute_key
```

### 1.3 `polarity` — the signal's own polarity, and why it is not `predicate_polarity`

| Property | Value |
|---|---|
| Type | `sa.String(16)` |
| Nullable | nullable, **no** server default |
| Classification | **identity-bearing** — `polarity` is in `RelationSignal._material()` |
| Requirement | `FR-015` (`"polarity` MUST be a column on `relation_signal` and `relation_candidate`"`) |
| Band | see §5.1 blocker B2 |

Values: `asserted`, `denied`, `uncertain` — longest 9, matching `020`'s
`predicate_state: sa.String(16)` terseness.

> **BLOCKER B2 — read before writing.** `FR-015` requires a `polarity` column on
> `relation_signal`. `A7-migration-021.md` D1.1 §6 lists **`predicate_polarity`** on
> `relation_signal` and **no plain `polarity`**, while D1.2 §7 lists **`polarity`** on
> `relation_candidate`. Those are two different facts: `RelationSignal.polarity` is the signal's
> own assertion polarity (in `_material()` since 4A, and the *only* place a denial can be
> recorded since 4C deleted `SignalKind.NEGATION`), and `PredicateSignature.polarity` is the
> signature's. A column called `predicate_polarity` cannot hold the first, and after 4C nothing
> else can.
>
> **This list requires both**: `predicate_polarity` as A7 specifies, and `polarity` for the
> signal. Writing one where the other is meant produces a column that satisfies the CHECK and
> loses the record.

### 1.4 `signal_end_kind` — the C4 distinction, on every participant

| Property | Value |
|---|---|
| Type | `postgresql.JSONB(astext_type=sa.Text())` — **not** a column of its own; see below |
| Nullable | n/a |
| Classification | **identity-bearing**, through `participant.mention_ref` |
| Requirement | C4; `FR-016`, `FR-018` |
| Band | see §5.1 blocker B3 |

**There is no `signal_end_kind` column and this is the deliberate reading.** Phase 4C made the
retrieval/occurrence distinction a **field on the participant**
(`domain/relation_participant.py:ParticipantEndKind`, two members `occurrence` / `retrieval`),
excluded from `RelationParticipant.to_identity()` because `mention_ref` already implies it. It
is in `RelationParticipant.to_dict()` and therefore in the canonical `participants`
serialisation, so **§1.1's `participants` column already stores it losslessly** and no second
column is required. A separate column would be a second source of truth for a value the
participant tuple decides, and the two could disagree.

---

## 2 — `relation_candidate`: two columns

Target table: `relation_candidate` (`020:289`), ORM `db/schema.py:2280`.

### 2.1 `participants` — the same tuple, and the same `NOT NULL` pre-flight

Identical row to §1.1 with one difference in the requirement's reach: on the candidate side the
tuple is in `RelationCandidate._logical_material()`'s `participants` key
(`apps/shared/domain/relation_candidate.py:757` onward), so it is **logical** material as well
as revision material. The pre-flight in §1.1 covers this table in the same query.

### 2.2 `assembly_state` — the structural verdict, on the candidate

| Property | Value |
|---|---|
| Type | `sa.String(16)` |
| Nullable | nullable, **no** server default |
| Classification | **revision material** — in `CANDIDATE_REVISION_MATERIAL_FIELDS` (`db/relation_candidate.py:715`), deliberately **not** in `CANDIDATE_LOGICAL_MATERIAL_FIELDS` |
| Requirement | `ARBITRATION` §3 |
| Band | see §5.1 blocker B3 |

Values: `consistent`, `ambiguous`, `conflicting` — longest 11 (`conflicting`), so `String(16)`
with the same headroom `predicate_state` and `predicate_polarity` take.

Nullable and not `NOT NULL` because the value is **derived by assembly** and a row written
before `021` has no verdict; a `NOT NULL DEFAULT 'consistent'` would be worse than a null,
because "consistent" is a *finding* ("the producers agreed on the shape") and defaulting it
records agreement nobody established. A `DEFAULT` here is exactly the fabrication I-3 forbids.
The null-tolerant membership CHECK belongs in §3.4.

---

## 3 — The three constraint operations

### 3.1 DROP `ck_relation_signal_asserts_something`

* Table `relation_signal`, `type_="check"`. Declared at `020:268`; ORM at `db/schema.py:2425`.
* Current text, verbatim: `relation_surface <> '' OR relation_ref IS NOT NULL`
* **Why it must go.** It is a ceiling dressed as a floor: it forbids a `CO_OCCURRENCE` signal
  with an empty `relation_surface` and no `relation_ref`, which FR-013 requires to be
  constructible, persistable and assemblable — and which 4A made representable by adding
  `SignalBasis`. Phase 4C deleted `SignalKind.NEGATION`/`QUANTITY`/`COREFERENCE` precisely
  because their aspects moved to fields; this constraint is the same kind of redundancy.
* **It cannot simply be dropped and not replaced.** `input.md:1119-1137` (brief §16) *replaces*
  it with a positive requirement — "every signal must have an explicit observational basis" — so
  §3.3 recreates it.

### 3.2 DROP `ck_relation_candidate_asserts_something`

* Table `relation_candidate`, `type_="check"`. Declared at `020:334`; ORM at `db/schema.py`.
* Current text, verbatim: `relation_surface <> '' OR relation_ref IS NOT NULL`
* **Why it must go, and why it is the *binding* half of FR-013.** A candidate assembled only
  from co-occurrence signals has an empty `relation_surface`, no `relation_ref` and no
  signature, so the *candidate-side* constraint blocks `SC-012` just as much as the signal side
  does (`A7-migration-021.md` §0.1).
* **The two replacements are different rules and writing one predicate into both tables is
  wrong** (`A7-migration-021.md` §0, D2.1): a signal has an `signal_kind` and an observational
  basis; a candidate has neither, and its basis is its `signal_refs`.

### 3.3 CREATE the two signal-side replacements

```python
_SIGNAL_ASSERTS_SOMETHING_021 = (
    "observational_basis IS NOT NULL"
    " OR relation_surface <> ''"
    " OR relation_ref IS NOT NULL"
)                                    # name: ck_relation_signal_asserts_something

_SIGNAL_BASIS_PREDICATE_021 = (
    "observational_basis IS DISTINCT FROM 'predicate_text'"
    " OR relation_surface <> ''"
    " OR relation_ref IS NOT NULL"
)                                    # name: ck_relation_signal_predicate_text_basis

_SIGNAL_BASIS_VOCABULARY_021 = (
    "observational_basis IS NULL OR "
    + _in("observational_basis", _OBSERVATIONAL_BASES_021)
)                                    # name: ck_relation_signal_observational_basis
```

The first is a **strict superset** of the constraint it replaces (the old two disjuncts appear
verbatim), so no stored row can become invalid. The second is the narrowing that actually
unblocks `SC-012`: only `predicate_text` obliges a surface, and it is the only basis where "I
read the words" with nothing to show is arithmetically impossible. The third is the closed
vocabulary, nullable-tolerant — a `NULL` basis is a row written before `021` and is legal.

**Neither replacement may mention `co_occurrence`.** The escape hatch is a *basis*, not a kind
(`A7-migration-021.md` D2.5), and a replacement that special-cases a kind would be the
constraint re-creating the vocabulary this phase just cleaned up.

### 3.4 CREATE the candidate-side replacement, plus the two vocabulary CHECKs

```python
_CANDIDATE_ASSERTS_SOMETHING_021 = (
    "relation_surface <> ''"
    " OR relation_ref IS NOT NULL"
    " OR predicate_signature_key IS NOT NULL"
    " OR (signal_refs IS NOT NULL AND jsonb_array_length(signal_refs) > 0)"
)                                    # name: ck_relation_candidate_asserts_something

_CANDIDATE_ASSEMBLY_STATE_021 = (
    "assembly_state IS NULL OR " + _in("assembly_state", _ASSEMBLY_STATES_021)
)                                    # name: ck_relation_candidate_assembly_state
```

The first is again a strict superset of what it replaces. The second is **not** in A7's list and
is added here for the same reason §2.2 is: a closed vocabulary that exists only in Python is a
vocabulary a `COPY` walks straight past (`020:144-147`), and `assembly_state` is new in `4A`.

### 3.5 DROP + CREATE `ck_relation_signal_kind` — and the one operation that **narrows**

* Declared at `020:276`; ORM at `db/schema.py:2437`. Thirteen literals, listed at `020:103-117`.
* This is the **only** operation in `021` that makes an existing row invalid rather than merely
  acceptable, and it is the one `020`'s file must keep unchanged so the pair becomes a drift
  detector (`A7-migration-021.md` D3.4, tests P14 and P18).

**Removed (3):** `coreference`, `quantity`, `negation` — deleted from `SignalKind` in Phase 4C.
Their aspects have landing places that already existed and are tested:
`NEGATION → RelationSignal.polarity = 'denied'`, `QUANTITY → participant.argument_shape =
'value'`, `COREFERENCE → a relation between two mention refs, not a channel`.

**Added (5):** `structural`, `event`, `semantic`, `temporal` (FR-011, absent since 019) and
`syntax` — the last being the *existing* `SignalKind.SYNTAX` literal, which `4B` added and which
the 020 whitelist has never heard of.

**Net: 13 − 3 + 5 = 15**, matching `FR-152`'s count.

The live enum, in declaration order, measured at
`apps/interpretation/extractors/signals/signal.py` after Phase 4C:

```
lexical, syntax, structural, event, semantic, temporal, link, reference,
table, list, metadata, attribute, hierarchy, schema, co_occurrence
```

#### 3.5.1 The narrowing pre-flight — `021` MUST refuse, not rewrite

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

**What `021` MUST NOT do to make that query return zero.** It must not
`UPDATE relation_signal SET signal_kind = …`, must not `DELETE` the rows, and must not add a
transitional whitelist admitting all three. All three mutate or re-label an observation. The
measured situation is benign and is stated as measured: no `INSERT` into `relation_signal`
exists anywhere in this repository, so in every database it can produce the query returns zero
rows.

**The forward alternative, if the pre-flight is non-empty, is a later revision and not a
workaround**: `022` re-adds the three kinds as *aspect* columns and only then narrows.

---

## 4 — Indexes, and the one that must **not** be added

`021`'s six new indexes (`A7-migration-021.md` D4.1) are all **leading with `tenant_id`** and
none of them serves the columns this list adds:

* `ix_relation_candidate_object`, `ix_relation_signal_object`, `ix_relation_claim_candidate`,
  `ix_relation_candidate_status`, `ix_relation_candidate_signature`,
  `ix_validation_finding_candidate`.

**`participants` gets no index, and `by_signal` on the candidate side gets no index either.**
`participants` and `signal_refs` are `JSONB`; no plain btree serves containment and a
tenant-prefixed GIN needs a `btree_gin` extension this repository does not declare. The
resulting `O(candidates in tenant)` cost is a **known limitation to be reported**, not a design
win, and it is the same call A7 made for `by_signal`.

---

## 5 — Blockers, with stop conditions

Four things in this list cannot be executed without a decision this phase does not have the
authority to make. They are reported, not numbered and not filled (`ARBITRATION` §14 rule 1).

### B1 — `participants` has no FR number

`ARBITRATION` §6 mandates the column in `021` and §0 assigns "Migration / schema" to **A7**,
whose band is `FR-150…FR-160`. A7's own D1 column tables list **neither** `participants` on
either table — A7 deferred both to `022`, which §6 **rejects** — and A7's §7.1 records that
deferral as a decision. So the column is mandated, owned, unnumbered, and absent from the owning
document's list.

**Stop condition.** An implementer who needs a citation for the `participants` column and cannot
find one must **report the gap**, not mint a number. `ARBITRATION` §14 rule 1 is the authority.
The two artefacts that do carry the obligation are `ARBITRATION` §6 and `FR-008`; those are the
citations to write, and the missing FR is a defect in the allocation map.

### B2 — `relation_signal.polarity` versus `predicate_polarity`

Described in §1.3. **Stop condition.** Do not write `predicate_polarity` where the signal's own
`polarity` is meant, and do not rename one to the other. Both columns are required;
`FR-015` settles the obligation and A7's D1.1 table settles the signature's.

### B3 — `assembly_state` is absent from A7's column list

`CandidateAssemblyState` is declared **NEW** in `ARBITRATION` §3 and the field landed in `4A`
(`db/relation_candidate.py:225`). A7's D1.2 §7 column table for `relation_candidate` does not
list it, and neither does its 42-operation table (§4). The same is true of `signal_end_kind` —
which this list resolves by *not* adding a column (§1.4), because `participants` carries it.

**Stop condition.** `assembly_state` is added as §2.2 specifies. If the implementer is working
from A7's §4 operation table rather than from this list, the table is short one `add_column` and
the `ck_relation_candidate_assembly_state` CHECK in §3.4 has no column to read.

### B4 — `syntax` versus `syntactic`: the whitelist literal

`FR-152` and `A7-migration-021.md` D1/§4 both write the literal **`syntactic`** — twice each,
in the requirement text and in the fifteen-member list. The live enum member is
`SignalKind.SYNTAX` with value **`"syntax"`**, added by the 4B syntactic producer. The two do not
agree, and `test_the_whitelist_is_exactly_the_live_signal_kind` (A7 P14/D3.4, which compares the
migration's literals to `SignalKind` *by value*) **cannot pass while they differ**.

Phase 4C did **not** rename the enum member, because the rename was not in its scope and because
the value is inside `RelationSignal._material()` — renaming it would re-key every stored signal
on the platform for a reason that has nothing to do with this phase's deletions.

**Stop condition.** One of the two must give, and the choice is not this phase's:

* amend `FR-152`'s literal to `syntax` (no data movement, a spec edit), **or**
* rename `SignalKind.SYNTAX`'s value to `syntactic` (matches the brief §15 wording, re-keys every
  stored signal, and needs a pre-flight of its own in the same shape as §3.5.1).

**This phase's recommendation is the first**, and the reason is the one the whole document is
built on: the brief's `SYNTACTIC` is a *spelling* disagreement and the pre-flight machinery
exists for a *content* narrowing. But a recommendation is not a decision, and an implementer who
picks the second must say so in the change log.

---

## 6 — Operation count, for the parity test

`021` as specified by this list, on top of A7's 42:

| # | Operation | Target | Object |
|---|---|---|---|
| +1 | `op.add_column` | `relation_signal` | `participants` JSONB **NOT NULL**, no default |
| +2 | `op.add_column` | `relation_signal` | `polarity` String(16) NULL, no default |
| +3 | `op.add_column` | `relation_candidate` | `participants` JSONB **NOT NULL**, no default |
| +4 | `op.add_column` | `relation_candidate` | `assembly_state` String(16) NULL, no default |
| +5 | `op.create_check_constraint` | `relation_candidate` | `ck_relation_candidate_assembly_state` (3 literals, nullable-tolerant) |

**`observational_basis`, both `DROP CONSTRAINT`s, the two signal-side replacements, the
candidate-side replacement, the `ck_relation_signal_kind` DROP+CREATE and the six indexes are
A7's and are listed here only so the count is checkable: 42 + 5 = 47 operations.** A7's own
invariants still hold and are re-asserted by the parity tests: **0** `create_table`,
**0** `drop_table`, **0** `drop_column`, **0** `UPDATE`, **0** `DELETE`, **0** `op.execute`, and
`downgrade()` **MUST** `raise NotImplementedError` before emitting anything.

`020` **MUST NOT be edited** and its content digest **MUST** be pinned in
`test_migration_forward_only.py`; `relation_signal`, `relation_candidate` and
`source_temporal_observation` **MUST** be added to the live `OWNED_TABLES` drift check. The
parity test **MUST** compare CHECK constraints **by text, not by name** — a whitelist that
changes on one install path and not the other leaves the constraint *names* identical, which is
exactly how the `syntax`/`syntactic` divergence in B4 would otherwise stay invisible.
