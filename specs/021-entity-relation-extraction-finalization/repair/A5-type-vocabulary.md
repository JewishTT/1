# A5 — TYPE VOCABULARY + `TypeHypothesis` (spec-repair)

**Feature**: `021-entity-relation-extraction-finalization`
**Repo root**: `C:\Users\tim\Desktop\COGNITIVE\1` (not the parent directory)
**HEAD at time of repair**: `0056665`
**Scope of this job**: the *entity/type* half of the substrate — the foundational type pack,
`TypeSignal`, `TypeHypothesis`, the mention's hypothesis set, the §8 extractor-expansion
requirements, and the nine §108 entity-substrate success criteria.
**Explicitly out of scope** (owned by `A2-identity-subsystem.md`, referenced here only as a given
interface): `PredicateSignature`, voice normalisation, role normalisation, participant ordering,
`logical_candidate_id`. This document does not specify, restate or constrain any of them.

**This document edits nothing.** It supplies exact old/new text for the repairer to apply. It
adds one file and modifies no other.

---

## 0. Findings this job opens before it repairs anything

These are measured, not inherited. Each is reproducible from the files named.

| # | Finding | Evidence |
|---|---|---|
| A5-1 | `CandidateResolutionState` is a **control-plane ORM enum**, and its members are `OPEN`/`MATCHED`/`SUPERSEDED`/`REJECTED`/`QUARANTINED`. **None of the three values `data-model.md` §6 attributes to it exist.** | `apps/control-plane/db/schema.py:70-75` |
| A5-2 | `AMBOUSSED` is a misspelling and appears **once in the entire repository**. | `data-model.md:229` |
| A5-3 | `TypeCandidate` does not exist anywhere in the codebase. `data-model.md` §6 makes a container of them out of nothing. | full-tree search of `apps/`, `bench/`, `tools/`, `donors/` |
| A5-4 | The brief's §6 field list has **13** fields and the brief's §6 state list has **6** states. `data-model.md` §6 replaced both with 6 fields and 3 states. | `input.md:465-492` vs `data-model.md:225-232` |
| A5-5 | The brief's §10 worked example emits **two separate `TypeHypothesis` blocks** (`core:Organization confidence=0.71`, then `core:Product confidence=0.22`). The brief's own worked example is a container-free pair. A hypothesis is one hypothesis. | `input.md:827-833` |
| A5-6 | The brief's §7 says, verbatim: `TypedMention` `+` `type_hypotheses[]` — the **set belongs to the mention**, not to a hypothesis. | `input.md:517-522` |
| A5-7 | The brief's §103 names exactly four nested/value objects — `PredicateHypothesis`, `PredicateSignature`, `TemporalHypothesis`, `RelationParticipant` — and pointedly **not** `TypeHypothesis`, while naming `TypeHypothesis` as one of the nine **distinct concepts** of §3 that must not be collapsed. | `input.md:4149-4185`, `input.md:252-268` |
| A5-8 | **The codebase already treats `TypeHypothesis` as one hypothesis and the set as a container field**: `BlockingResult.type_hypotheses: tuple[TypeHypothesis, ...]`, `BlockingOutcome.hypotheses: tuple[TypeHypothesis, ...]`, `type_hypotheses_for() -> tuple[TypeHypothesis, ...]`. The container already exists; the `data-model.md` rewrite would have created a second, competing one. | `blocking.py:301`, `resolution.py:774`, `resolution.py:734-749` |
| A5-9 | **FR-030's "32" does not exist.** `spec.md` nowhere writes "32 named types"; FR-030 enumerates exactly **31** distinct `core:*` entity classes. The "32" is a review-prose artefact in `phase0-results.md` §4.1 D7 ("FR-030 mandates 32 type classes"). The number is unsourced *and* the enumeration the review counted is 31. | `spec.md:488-495`; `phase0-results.md` §4.1 D7 |
| A5-10 | `core:Coordinate` (entity, FR-030) and `value:Coordinate` (value, FR-031) are the **same label in two namespaces**. The brief has the same duplication (`input.md:369` and `input.md:416`). `spec.md` FR-031 forbids forcing a value into `Entity` while FR-030 places a `Coordinate` in the entity list, so the spec contradicts itself unless `kind` is load-bearing. | `spec.md:491`, `spec.md:499`, `input.md:369`, `input.md:416` |
| A5-11 | There is **no `TypeSignal` type in the codebase at all.** FR-035 requires one with `source_vocab`, `surface`, `mapping_candidates`; §55 requires a `TYPE_SIGNALS` lifecycle stage. `A4b-mapping-layer.md` §D5.2 has since specified it as `apps/shared/semantic/type_signal.py::TypeSignal`, with `mapping_candidates: tuple[TypeMappingCandidate, …]` — **proposals, not records**. A5 conforms to that (see D2.4). | full-tree search; `repair/A4b-mapping-layer.md:1290-1319` |
| A5-12 | §8 is **170 lines** (`input.md:559-728`) and 7 mandatory sub-sections. Across `spec.md`, `data-model.md`, `plan.md`, `tasks.md` and `checklists/requirements.md`, `Cyrillic`, `github.com`, `CVE` and `persons.py` appear **zero** times. | re-measured D7 |
| A5-13 | `apps/shared/semantic/mappings.py` **already implements** the SSSOM-oriented mapping record FR-036 demands (`SemanticMapping` with `subject_ref`, `object_ref`, `predicate`, `mapping_set_id`, `mapping_set_version`, `mapping_source`, `mapping_version`, `justification`, `provenance`, `confidence`, `subject_scheme`, `object_scheme`, `supersedes`). So `TypeHypothesis.mapping_candidates` needs **no new mapping type** — it needs a reference to an existing one. | `mappings.py:75-88`, `mappings.py:244-264` |
| A5-14 | `TypedMention.kind` today takes exactly seven values: `crypto`, `handle`, `ip`, `org`, `person`, `phone`, `place`. These are producer classifications, not a vocabulary, and the §4.1 type space covers none of the §8 gaps. | `extractors/*.py` `kind="…"` sweep |

---

## D1 — `TypeHypothesis` is ONE hypothesis

### D1.1 The defect, quoted

`data-model.md:225-232` (verbatim, today):

```python
@dataclass(frozen=True)
class TypeHypothesis:            # competing, not singular
    mention_ref: str
    hypotheses: tuple[TypeCandidate, ...]   # >= 1
    state: CandidateResolutionState          # RESOLVED | AMBOUSSED | UNRESOLVED
    vocabulary_version: str
    evidence_refs: tuple[str, ...]
```

Every clause of that block is wrong, and each for a different reason:

| Clause | Why it is wrong |
|---|---|
| `# competing, not singular` | The **brief** says the opposite. §6 titles the section "TYPE HYPOTHESIS MODEL" and §6's field list is per-hypothesis. §10's worked example prints two hypotheses as two blocks. |
| `hypotheses: tuple[TypeCandidate, …]` | `TypeCandidate` does not exist (A5-3). The container is already `type_hypotheses: tuple[TypeHypothesis, …]` on `BlockingResult` and `BlockingOutcome` (A5-8). This would create a *second* container for the same facts. |
| `state: CandidateResolutionState` | Wrong enum (A5-1) and an inverted dependency: `apps/control-plane/db/schema.py` is the control-plane ORM; `apps/shared` does not import it and must not. Importing a control-plane ORM enum into `shared` inverts the layering (`shared` is imported *by* control-plane). |
| `RESOLVED \| AMBOUSSED \| UNRESOLVED` | Two of the three are not the brief's states and one is a misspelling (A5-2). `RESOLVED` and `UNRESOLVED` also do not exist in the enum they claim to come from. |
| `vocabulary_version` | Not one of the brief's 13 fields. It is legitimate information but it belongs on the **pack**, and the brief's own mechanism for it is `mapping_candidates` / `scheme`. Dropping it here loses nothing the brief asked for. |
| `evidence_refs` | Present in the brief. Keep. |

`data-model.md:234-235` then compounds it:

> `TypeHypothesis` today is thin (`semantic/blocking.py`) and `TypeAssertion` carries a single
> hypothesis, so "Apple" cannot be three things at once (User Story 4).

`TypeAssertion` is not the problem. §6 of the brief names the actual defect in one line, and it is
a *reader*-side defect, not an assertion-side defect:

> Do not confuse this with `SemanticStatus` on `TypeAssertion`.
>
> The distinction is:
>
> ```text
> TypeHypothesis
>     = interpretation candidate
>
> TypeAssertion
>     = evidence-bearing semantic assertion
> ```

`TypeAssertion` already holds *several* assertions at once — it has a two-level identity
(`logical_type_assertion_id` over `(tenant, entity, type, scope)`, and `type_assertion_id` per
revision) precisely so that "one entity is never one type" can be true
(`contracts.py:214-229`, `spec.md` INV-001). The thing that is thin is
`semantic/blocking.py::TypeHypothesis`, and the thing that is singular is the **producer's
`TypedMention.kind: str`**. Both of those are fixed by the D1.3 dataclass and the D1.4 container,
with no change to `TypeAssertion` at all.

### D1.2 The six states, quoted from the brief

`input.md:483-492` (verbatim):

> States may be:
>
> ```text
> UNKNOWN
> OBSERVED
> INFERRED
> MAPPED
> AMBIGUOUS
> CONFLICTING
> ```

`input.md:465-481` (verbatim) — the thirteen required conceptual fields:

> Required conceptual fields:
>
> ```text
> type_surface
> normalized_surface
> type_ref
> scheme
> hypothesis_state
> confidence
> source_ref
> extractor_ref
> extractor_version
> evidence_refs
> context_ref
> semantic_regime_ref
> mapping_candidates
> ```

**Count check**: `type_surface`, `normalized_surface`, `type_ref`, `scheme`, `hypothesis_state`,
`confidence`, `source_ref`, `extractor_ref`, `extractor_version`, `evidence_refs`, `context_ref`,
`semantic_regime_ref`, `mapping_candidates` = **13**. `spec.md` FR-032 lists the same thirteen in
the same order and adds the same six states. Brief and spec agree; `data-model.md` §6 is the sole
outlier. **13 fields, 6 states — that is the number, and there is no negotiation available.**

Note also `input.md:483`: "States **may be**:" — the brief is permissive about the *set*, and
`spec.md` FR-032 has hardened it to "with states `UNKNOWN`, `OBSERVED`, `INFERRED`, `MAPPED`,
`AMBIGUOUS`, `CONFLICTING`". Hardening a permissive "may" into a closed six is legitimate and is
what the code should do; it is `data-model.md`'s *replacement* of that set with three invented
values that is not.

### D1.3 The replacement type — verbatim

```python
# apps/shared/semantic/types.py  (new module; see D1.6 for why a new module and not contracts.py)

class HypothesisState(StrEnum):
    """How one type hypothesis stands. Per §6 of the brief; closed at six."""
    UNKNOWN     = "unknown"
    OBSERVED    = "observed"
    INFERRED    = "inferred"
    MAPPED      = "mapped"
    AMBIGUOUS   = "ambiguous"
    CONFLICTING = "conflicting"


@dataclass(frozen=True)
class TypeHypothesis:
    """ONE interpretation candidate for what a mention is. Never a set of them.

    §6 of the brief is explicit that this is `= interpretation candidate`, and §6's field list is
    thirteen fields about *one* candidate. The competing-candidates reading belongs to the
    mention, which holds them: §7 says `TypedMention` `+` `type_hypotheses[]`. §10's worked
    example prints `core:Organization confidence=0.71` and `core:Product confidence=0.22` as two
    hypotheses, not as one hypothesis with two children.
    """

    type_surface: str                     # the words that triggered the hypothesis, verbatim
    normalized_surface: str              # NFKC + casefold + whitespace fold; for matching only
    type_ref: str                         # the candidate ref, e.g. "core:Organization"
    scheme: SemanticRef                   # how to treat the ref; never what it means
    hypothesis_state: HypothesisState
    confidence: float = 0.0
    source_ref: str = ""                 # the observation this was read off
    extractor_ref: str = ""              # which producer proposed it
    extractor_version: str = ""          # pinned, per FR-043's provenance rule
    evidence_refs: tuple[str, ...] = ()  # citable; sorted + de-duplicated on construction
    context_ref: str = ""                # the CONTEXT stage product consumed, per FR-159
    semantic_regime_ref: str = ""        # the regime that read the context, or ""
    mapping_candidates: tuple[TypeMappingCandidate, ...] = ()   # never collapsed, never chosen
```

Field notes, each traceable to a quote rather than to taste:

* `type_surface` / `normalized_surface` — §6 lists both. `normalized_surface` is a *matching* form.
  `vocabularies.normalize_surface_form` already implements the exact transform required (NFKC,
  Unicode-aware camel split, `_`/`-`→space, casefold, whitespace collapse) and its own docstring
  states the discipline this type needs: "It makes no judgement about what the form *means* — it
  is a string normalisation, never a type inference." Reuse it; do not write a second one.
* `scheme` — `SemanticRef`, the existing six-member `StrEnum` (`INTERNAL`, `PROFILE`, `SKOS`,
  `EXTERNAL`, `LOCAL`, `UNRESOLVED`) whose docstring is itself open-world: "An unrecognised
  scheme is not an error (FR-001) — it is a new scheme, and the resolver declines to expand it
  rather than guessing." §63's `core:`/`value:`/`industry:` prefixes are a *ref-namespace*
  concern, not a `SemanticRef` concern — see D3.3 — so this field keeps its existing meaning and
  the namespace travels inside `type_ref`.
* `confidence` — a projection, never identity. Same rule the predicate side applies
  (`data-model.md:39`: "Confidence is a mutable projection field, never identity"). A
  `TypeHypothesis` has no content-addressed id at all in this feature, precisely because it is a
  transient interpretation candidate; do not mint one (see D1.5).
* `extractor_version` — a `TypeHypothesis` that does not say which version of which extractor
  proposed it cannot be re-derived, which is the whole point of §30's "a parser capability MUST be
  explicit and pinned". It is in §6's list for the same reason it is in FR-043.
* `mapping_candidates` — `tuple[TypeMappingCandidate, …]`, the type-side twin of A4b's
  `PredicateMappingCandidate`, from `A4b-mapping-layer.md` §D5.2, in `semantic/type_signal.py`.
  **Proposals, not records, and that is deliberate**: a hypothesis has reached no reviewed,
  sourced or recorded mapping either, so it is in exactly the same epistemic position as the
  signal that suggested it. A `TypeMapping` (= `SemanticMapping`, A4b §D5.1) exists only once a
  `MappingSet` holds it. It is a tuple and it is never collapsed, for the reason
  `mappings.py`'s own docstring gives: "Several mappings for one pair is the normal case, and none
  of them is chosen over another." **A5 defers to A4b on this type; see D2.4.**
* **What this type deliberately does NOT carry**, stated so a later reviewer does not "helpfully"
  add it back:

| Absent | Reason |
|---|---|
| `mention_ref` | A hypothesis is owned by a mention. Carrying the owner's id inside the owned value is the identity inversion `data-model.md:36-40` forbids on the predicate side ("any entity id… `Mention ≠ Entity`"). A4b's `TypeSignal` **does** carry `mention_ref` and this is not a disagreement: a signal is an *observation about a specific occurrence* and must be de-duplicable per occurrence, which is why A4b derives `signal_id` from `(tenant_id, producer_ref, mention_ref, source_vocab, surface, structural_path)`. A hypothesis is a *candidate owned by that occurrence*, so a back-pointer is redundant — and worse, it would make the hypothesis's content key a function of an id minted by a different layer. **The asymmetry is load-bearing and is FR-151's test.** |
| `hypotheses` / children | §103. See D1.5. |
| `state` as a *resolution verdict* | A hypothesis does not resolve anything. Resolution is `TypeAssertion`'s business and its ladder is `SemanticStatus` (`contracts.py:110-123`). Two different questions. |
| `entity_ref` | INV-001: "one mention is never one entity." A hypothesis is about a mention. |
| `signal_id` / any id / digest | See D1.5. Note the deliberate asymmetry: `TypeSignal` **has** a `signal_id` (A4b §D5.2) and `TypeHypothesis` has none. The observation is citable, de-duplicable and replayable; the candidate is discarded with the comparison. If a hypothesis is ever given an id, the thing it was id'd *for* has changed and this section is wrong. |
| `type_ref` prefixed `core:`/`value:` *by this type* | A4b §D5.2, verbatim: "The signal does not know what the term means and MUST NOT carry a `core:` reference: the first moment a local type may appear on this path is `TypeHypothesis`, and reaching it requires a TypeMapping record." The *hypothesis* is that first moment, so this field is where a local ref is legal. |

### D1.4 The set container — specified

`input.md:515-522` (verbatim):

> Instead:
>
> ```text
> TypedMention
>     +
> type_hypotheses[]
> ```
>
> or equivalent.
>
> The raw `kind` may be retained as legacy/coarse producer classification.

So the container is a **field**, and the field is owned by a **mention**. There are exactly two
mention types in play and the container must be on both, because they are on opposite sides of a
process boundary and neither is a copy of the other:

**(a) Producer side — `apps/interpretation/extractors/types.py::TypedMention`** (the type the brief
names, verbatim §7). Additive field, defaults empty, so all 14 existing extractors and every
existing test keep working untouched:

```python
    type_hypotheses: tuple[TypeHypothesis, ...] = ()
```

`kind: str` is **retained unchanged** — brief §7 says so, and `spec.md` FR-033 says
"`TypedMention.kind` MAY be retained as a coarse producer classification". `kind` is not
deprecated, not renamed, not given an enum; it is a *producer classification* and it is compared
to nothing. The seven values in use today are `crypto`, `handle`, `ip`, `org`, `person`, `phone`,
`place` (A5-14) and all seven are producer classes, none of which is a vocabulary term.

`TypedMention.to_dict()` gains `"type_hypotheses": [...]` in the existing `_sorted_dict` path, so
determinism (constitution VI) is preserved by construction rather than by a new sorting rule.

**(b) Resolution side — `apps/shared/semantic/resolution.py::ResolutionMention`**. It is already
the substrate's mention-shaped record, it already carries `declared_type_refs: tuple[str, ...]`
(`resolution.py:276`) and `type_assertions: tuple[TypeAssertion, ...]` (`resolution.py:277`), and
it already has `type_refs() -> tuple[tuple[str, SemanticRef], …]` and
`type_hypotheses_for() -> tuple[TypeHypothesis, …]` (`resolution.py:286-307`, `734-749`). The
hypothesis set belongs beside the assertion set, on the same object, in the same style:

```python
    type_hypotheses: tuple[TypeHypothesis, ...] = ()
```

…with `__post_init__` freezing it exactly as it freezes `type_assertions` (`resolution.py:284`).
This is the **only** durable home for the set in this feature.

**Why not a new `TypeCandidate`/`TypeHypothesisSet` type.** Because it would be a fifth place the
same facts live, and the codebase has already made the choice twice and consistently (A5-8). A
fifth carrier is the defect, not the cure.

**Ordering rule (both sites).** The set is sorted, de-duplicated and frozen on construction, by
`(-confidence, type_ref, str(scheme), str(hypothesis_state))`, and de-duplication is by
`(type_ref, str(scheme), str(hypothesis_state))` keeping the highest-confidence occurrence. This
is not new: `blocking.py:542-565` (`_ordered_hypotheses`) already implements exactly this policy
and explains why — "Ordering is total and value-based rather than insertion-based so that the
recorded hypothesis list — and therefore the result's content key — cannot depend on the order a
caller happened to build its hypotheses in." **Reuse that function; do not write a second one.**

### D1.5 Justification: the set container is NOT a fourth epistemic level

This is the question the brief's §103 exists to answer, and it must be answered without appealing
to authority. Three independent arguments:

**Argument 1 — §103's own enumeration puts `TypeHypothesis` in the same class as
`PredicateHypothesis`.** `input.md:4149-4185` (verbatim):

> # 103. DO NOT CREATE A FOURTH EPISTEMIC LEVEL
>
> Do not end up with:
>
> ```text
> Signal
> Hypothesis
> Candidate
> Interpretation
> Assertion
> Claim
> Edge
> ```
>
> all meaning almost the same thing.
>
> Use:
>
> ```text
> Signal
> Candidate
> Claim
> Edge
> ```
>
> as the main relation hierarchy.
>
> Use nested/value objects for:
>
> ```text
> PredicateHypothesis
> PredicateSignature
> TemporalHypothesis
> RelationParticipant
> ```
>
> where necessary.

`PredicateHypothesis` is named in the **nested/value-object** list. `TypeHypothesis` is
structurally the same object — an interpretation candidate about one thing, owned by its parent,
with a competing-siblings field on the parent. The brief simply did not need to name it there
because it had already placed it, at `input.md:252-268` (§3), in the list of concepts that must
remain *distinct*:

> Preserve the separation:
>
> ```text
> Mention
> Candidate
> Entity
> TypeHypothesis
> TypeAssertion
> RelationCandidate
> RelationClaim
> GraphNode
> GraphEdge
> ```
>
> must remain different concepts.

Nine distinct **concepts**, not nine ordered **stages**. §103's prohibition is against *stages
that mean the same thing*; §3's requirement is that the *concepts* not collapse into each other.
`TypeHypothesis` ≠ `TypeAssertion` is §3. `TypeHypothesis` = "one candidate" and the mention's
tuple = "the candidates" is not a new concept at all, it is a field. `data-model.md:10-11` is
what converts §3's list into an ordered chain — and that conversion is the error.

**Argument 2 — the entity-side chain the brief itself draws has three rungs, and `TypeHypothesis`
is not one of them.** `input.md:4035-4043` (§101, verbatim excerpt):

```text
MENTION OCCURRENCES
    │
    ├──────────────► TYPE SIGNALS
    │                    │
    │                    ▼
    │               TYPE HYPOTHESES
    │                    │
    │                    ▼
    │               TYPE ASSERTIONS
```

Compare §102's three semantic layers, verbatim (`input.md:4103-4135`): Layer 1 observation =
`RelationSignal`; Layer 2 hypothesis = `RelationCandidate`; Layer 3 world assertion =
`RelationClaim`. The entity-side analogue of Layer 1 is `TypeSignal`; of Layer 3 is
`TypeAssertion`. `TYPE HYPOTHESES` is drawn *between* them as a fan-out annotation on the mention
occurrence — the same visual position `PredicateHypothesis` occupies on the relation side, and the
same position `data-model.md:181-184` assigns it ("`PredicateSignature` is **not** stored inside
`PredicateHypothesis`: the signature is the *structure*, the hypothesis is the *mapping attempt*").
It is a stage in the *pipeline* (§10 lists it: `Observation → Mention → TypeSignal →
TypeHypothesis → SemanticRegime interpretation → TypeAssertion`) and a **value object** in the
*type hierarchy*. Those are different questions and §103 is about the second. A dataclass that
one mention owns and that contains only evidence about one candidate is a value object whatever
arrow points at it.

**Argument 3 — the counter-case, tested.** What *would* be a fourth level: a type that (a) has its
own identity, (b) can be minted by something other than a mention, (c) can exist without a
mention, and (d) can be projected without a mention. `data-model.md`'s container fails (a) — it has
no identity, `data-model.md:297` correctly says `| TypeHypothesis | EXTENDED | — |` i.e. no
identity key. A type with no identity cannot be a level; a level is precisely what you mint an id
for. `TypeHypothesis` as specified in D1.3 also has no id, and that is intentional: it is
discarded with the comparison, exactly as `blocking.py:169-180` says today ("A hypothesis narrows a
comparison and is discarded with it"). **A level you cannot cite is not a level.** The durable,
citable, identity-bearing type on the entity side is `TypeAssertion` — `TA-`/`TAR-`
(`contracts.py:58-61`) — and that is the level.

**Corollary, and it is a test.** If the hypothesis set ever needs a *status* that is not any
hypothesis's own `hypothesis_state`, that is the signal that a container has become a level. The
brief gives exactly one such status — `§10`'s "A later `status=INFERRED` must be a new revision, not
destructive replacement" — and `input.md:854` says where it lands: "This follows the existing
`TypeAssertion` two-level identity model." So the promotion status belongs to
`TypeAssertion.status` (`SemanticStatus.INFERRED`, `contracts.py:110-123`) and to
`TypeAssertion.promoted()` (`contracts.py:327-342`). Nothing new is needed for it, and the
hypothesis set stays a tuple of frozen values forever.

### D1.6 Placement, and why a new module

`TypeHypothesis` does **not** go in `semantic/contracts.py` and does **not** stay in
`semantic/blocking.py`.

* Not `blocking.py`: that module's stated reason for existing is comparison cost — "Blocking is
  the difference between a comparison that costs ten thousand times and one that costs a hundred"
  (`blocking.py:2-4`) — and it forbids itself from carrying anything durable ("there is no field
  on it that could survive into a record", `resolution.py:741`). A 13-field evidence-bearing
  record does not belong in the query-narrowing module. The **existing**
  `blocking.TypeHypothesis` is a different, deliberately-thin narrowing value and stays where it
  is; it keeps `type_ref`/`scheme`/`confidence` and its two importers
  (`extractors/relations.py:64`, `domain/entity_identity.py:106`) are unaffected.
* Not `contracts.py`: that module is `TypeAssertion`, `ValidationReport`, `RelationRef` — durable
  and evidence-bearing. `TypeHypothesis` is an *unresolved* candidate. Putting the unresolved type
  next to the resolved one in the same module invites the very conflation §6 warns about.
* New module `apps/shared/semantic/types.py`, alongside the existing `semantic/mappings.py` and
  `semantic/vocabularies.py`, and alongside **A4b's** `apps/shared/semantic/type_signal.py`. Its
  imports are: `semantic.contracts` (for `SemanticRef`, `content_key`), `semantic.vocabularies`
  (for `normalize_surface_form`, `normalize_type_ref`) and `semantic.type_signal` (for
  `TypeMappingCandidate`) — plus stdlib. It imports **nothing** from `apps/control-plane`, and
  `semantic.type_signal` imports nothing from it, so the dependency graph is acyclic and
  one-directional. That is the whole dependency contract, and it is testable (FR-151's test).
* `TypePack` / `TypePackEntry` (D3.3) go in the same module, because a pack entry is a vocabulary
  object and `semantic.vocabularies.Concept` — with `broader`/`narrower`/`related` and the four
  `*_match` link fields — is the same idea already implemented. Reuse `ConceptScheme`'s
  conventions (canonically ordered by id, link sets de-duplicated and sorted, derived indexes
  built once, unknown reference returns empty rather than raising) rather than inventing a second
  registry; `vocabularies.py:369-372` states the rule this pack must inherit verbatim: "A concept
  it does not contain is not a concept that cannot exist, and every lookup for an unknown
  reference returns an empty result instead of raising."

**Naming collision, called out so the repairer does not create one.** There are then two types
named `TypeHypothesis` in `apps/`. That is unacceptable. The thin narrowing one is
`semantic.blocking.TypeHypothesis` and it is the one with three importers; the new one is
`semantic.types.TypeHypothesis`. **Decision: rename the blocking one to
`semantic.blocking.TypeRefHint`** at the three call sites
(`blocking.py:170`, `resolution.py:112`, `relations.py:64`, `entity_identity.py:106-108`) —
a pure rename, no field change, no behaviour change, covered by the existing blocking tests. It is
also the more honest name: it is a hint for comparison, it never becomes a type, and the codebase
already calls the thing it feeds `type_hypotheses_offered` (`resolution.py:777`). Log the rename as
a breaking change in the feature's changelog and do it in its own commit.

---

## D2 — The `TypeSignal` layer

### D2.1 What a `TypeSignal` is, in the brief's words

There is no `TypeSignal` in the codebase (A5-11). The brief names it four times and specifies it
once. `input.md:743-766` (verbatim):

> A structured statement like:
>
> ```json
> {
>   "@type": "Person",
>   "name": "John Smith"
> }
> ```
>
> must produce:
>
> ```text
> TypeSignal(
>     source_vocab = schema.org,
>     surface = "Person",
>     mapping_candidates = [...]
> )
> ```
>
> not immediately:
>
> ```text
> TypeAssertion(core:Person)
> ```

and `input.md:807-816` (§10, verbatim):

> ```text
> Observation
> → Mention
> → TypeSignal
> → TypeHypothesis
> → SemanticRegime interpretation
> → TypeAssertion
> ```
>
> Maintain all previous states.

`spec.md` FR-035 (verbatim) makes it mandatory for one family and names the three fields:

> **FR-035**: External vocabularies (JSON-LD, schema.org, OpenGraph, RDFa, microdata, HTML
> metadata) MUST produce a `TypeSignal` with `source_vocab`, `surface` and
> `mapping_candidates`, and MUST NOT immediately produce a `TypeAssertion`. (§9)

**The layer in one sentence:** a `TypeSignal` is the entity-side *observation record* — "a
source, in a vocabulary, said something type-shaped about this mention" — and it is the direct
analogue of `RelationSignal` on the relation side, subject to the identical rule (a signal is
Layer 1, `input.md:4107-4115`: "something relational-looking was observed"). It carries **no
commitment**, resolves to nothing, and is never projectable.

### D2.2 What produces `TypeSignal`s — the six producing families

`TypeSignal` is **A4b's type** (`repair/A4b-mapping-layer.md` §D5.2,
`apps/shared/semantic/type_signal.py`), verbatim field list:

```python
source_vocab: str                                            # the vocabulary that said it
surface: str                                                 # verbatim, as stated
mapping_candidates: tuple[TypeMappingCandidate, ...] = ()    # >= 0; may legitimately be 0
mention_ref: str = ""                                        # the mention this is about
structural_path: tuple[str, ...] = ()
observation_refs: tuple[str, ...] = ()
evidence_refs: tuple[str, ...] = ()
producer_ref: str = ""                                       # observation channel identity (FR-006)
signal_id: str = ""
```

**A5 withdraws its own `signal_source` proposal.** A5 initially specified a
`TypeSignalSource` enum over `{SURFACE, DOCUMENT, MARKUP, REGEX, NER, METADATA}`. That is a
**second name for an axis A4b's type already carries** in `source_vocab` (which vocabulary said
it) and `producer_ref` (which instrument said it), and a new enum over an existing axis is
precisely the defect A4b identifies when it refuses one generic `MappingCandidate`:
"which is how `RelationSignal.kind` ended up mixing thirteen meanings before FR-011 split it"
(`A4b:1367-1368`). **Withdrawn.** The six families are therefore expressed as a *producer
convention*, not as a new field: each instrument registers under `ExtractorRegistry` and writes
`producer_ref` plus the `source_vocab` value it declares.

| Family | Producer | `producer_ref` | `source_vocab` | Distinguishing evidence |
|---|---|---|---|---|
| **surface** | the text as observed | the person/org instrument | `""` (local — see the ask in D2.4) | `structural_path` = the span |
| **document** | document-level facts | the document instrument | `""` | `observation_refs` names the document resource |
| **markup** | JSON-LD / schema.org / OpenGraph / RDFa / microdata / HTML `<meta>` | the structured-semantics producer | `"schema.org"` / `"opengraph"` / `"rdfa"` / `"microdata"` / `"html-meta"` / `"jsonld"` | `source_vocab` verbatim; §9's list is the §9 producer list |
| **regex** | deterministic pattern instruments | `extraction_rule_id`'s instrument | `""` | `evidence_refs` = the rule id |
| **NER** | the person-name / role NER pass | the NER instrument | `""` | `evidence_refs` = `model_ref` + `model_version` (pinned — §30) |
| **metadata** | external artifact metadata | the metadata producer | `"opengraph"` / `"html-meta"` | `source_vocab` verbatim |

Two observations that are decisions rather than restatements:

* **Four of the six families have no external vocabulary.** A4b's `source_vocab` docstring
  enumerates six *external* vocabularies, so a Cyrillic name matched by `persons.py` has no legal
  value to write there. D2.4 ask 3 asks A4b to name the reserved local sentinel and its
  normalisation rule. Until A4b answers, A5 does **not** invent one: `source_vocab=""` is the
  documented default in A4b's own dataclass, and §104's rule applies here too — an empty
  vocabulary is *unrecorded*, never *absent* (`blocking.py:126-127`: "Both may be empty, and empty
  means *unrecorded*, never *absent*").
* **`TypeSignal` has no producer *version*.** A4b's field list has `producer_ref` and `signal_id`
  but nothing that pins which version of the instrument or NER model spoke. §30 requires
  `model_ref`, `model_version`, `parser_version` and `configuration_hash` as "part of
  interpretation provenance", and FR-140's re-derivability depends on it. D2.4 ask 2 asks A4b for
  `producer_version: str = ""`. **A5 does not add the field to A4b's type unilaterally.**

### D2.3 The pipeline this job specifies, end to end

```text
  surface / document / markup / regex / NER / metadata
        │
        │   (each is an Observation; each yields one or more TypeSignals, each with its own
        │    signal_id over (tenant_id, producer_ref, mention_ref, source_vocab, surface,
        │    structural_path) — A4b §D5.2, and mapping_candidates deliberately excluded)
        ▼
  TypeSignal(source_vocab, surface, mapping_candidates, producer_ref, signal_id)
        │
        │   the mention's OWN type_hypotheses tuple gains one entry per distinct candidate
        ▼
  TypeHypothesis × N        ← §10: core:Organization conf=0.71  AND  core:Product conf=0.22
        │
        │   SemanticRegime interpretation — consumes §77 context, records context_ref,
        │   may raise a hypothesis's confidence or add a competing one; never deletes one
        ▼
  TypeAssertion(entity=ENT-…, type=core:Organization, scope=OBSERVED, status=OBSERVED, evidence=…)
        │
        └── a mapping crosses only via a recorded SemanticMapping in a MappingSet (A4b §D5.1)
```

**The id asymmetry, stated once, because it is the strongest evidence for D1.5.** The *signal*
carries a `signal_id`; the *hypothesis* does not; the *assertion* carries two
(`TA-`/`TAR-`). Three types, three id policies, each matching what the type is for: an observation
must be citable and de-duplicable, a candidate must be discardable, an assertion must be
revisable without erasure. **A type that carried an id at every level would be a level; three
different id policies is what "not a level" looks like in code.**

The two rules that make this safe, quoted:

* §10 (verbatim, `input.md:846-854`):
  > A later inference:
  >
  > ```text
  > status=INFERRED
  > ```
  >
  > must be a new revision, not destructive replacement.
  >
  > This follows the existing `TypeAssertion` two-level identity model.
* §7 (verbatim, `input.md:528-535`):
  > ```text
  > surface "Apple"
  >     → Person hypothesis
  >     → Organization hypothesis
  >     → Product hypothesis
  > ```
  >
  > before resolution.
* §7 (verbatim, `input.md:553-555`):
  > This is not an error.
  >
  > It is information.

`TypeAssertion` is unchanged. Its two-level identity already provides the new-revision
requirement (`contracts.py:281-325`), and its `mapping_ref` field (`contracts.py:255`) is already
where a `SemanticMapping` id goes. Nothing in D1–D3 changes `TypeAssertion`.

### D2.4 Coordination with `A4b-mapping-layer.md` — resolved and open

`A4b-mapping-layer.md` exists and owns `TypeSignal`, `TypeMappingCandidate` and
`TypeMapping`/`SemanticMapping`. **A5 conforms on the first two and does not overrule A4b on
either.** Status of each item:

| # | Item | Status | Detail |
|---|---|---|---|
| 1 | `TypeSignal.mapping_candidates` element type | **CONFORMED — A5 was wrong** | A5 assumed `tuple[SemanticMapping, …]`. A4b §D5.2 specifies `tuple[TypeMappingCandidate, …]`: proposals, not records, "Same proposal/record split as the predicate side, and for the same reason: a `TypeSignal` produced by a JSON-LD block has, at best, a *candidate* mapping — nothing has been reviewed, sourced, or recorded. A `TypeMapping` exists only once a `MappingSet` holds it." A5 adopts this verbatim. A5's original assumption is withdrawn. |
| 2 | `TypeHypothesis.mapping_candidates` element type | **CONFORMED to A4b** | Same `TypeMappingCandidate`, for the same reason: a hypothesis has reached no reviewed mapping either, so it is in the same epistemic position as the signal that suggested it. This makes the two fields the same type, which is required — a divergence would have FR-035 and FR-032 contradicting each other on the record. |
| 3 | `TypeSignal.producer_version` | **OPEN — A5's ask** | A4b's field list has `producer_ref` and `signal_id` but **no version pin**. §30 requires `model_ref`, `model_version`, `parser_version` and `configuration_hash` "as part of interpretation provenance"; FR-140's re-derivability and FR-141's Cyrillic/NER coverage both depend on it. **Request: add `producer_version: str = ""`.** Adding a defaulted field does not move `content_key()` for any existing row, so this is the low-risk form of the change. |
| 4 | `source_vocab` for a **local** producer | **OPEN — A5's ask** | A4b's `source_vocab` documents six *external* vocabularies (`schema.org`, `opengraph`, `rdfa`, `microdata`, `html-meta`, `jsonld`). Four of §8's six families — surface, document, regex, NER — have no external vocabulary and no legal value to write. **Request: name the reserved local sentinel** (A5's proposal, for A4b to accept or override: `""`, already the dataclass default, or a `local:`-prefixed value) **and state the normalisation rule for it.** A5 will not invent one unilaterally, because a second spelling of "no external vocabulary" across two modules is the inconsistency A5 is here to remove. |
| 5 | `TypeSignal.mention_ref` vs `TypeHypothesis`'s prohibition on it | **ASKING A4b TO CONFIRM** | A4b derives `signal_id` from `(tenant_id, producer_ref, mention_ref, source_vocab, surface, structural_path)`, so its signal carries `mention_ref`; A5's hypothesis must not (D1.3). A5's reason: the hypothesis is *owned* by the mention, and a back-pointer inside an owned value makes the owned value's content key a function of an id minted by a different layer. Confirm the asymmetry is intended rather than incidental, so FR-151 locks it deliberately. |
| 6 | The §64 initial mapping set | **A4b's deliverable; A5 states a dependency** | `input.md:2876-2883` (verbatim):<br>`schema:Person → core:Person` / `schema:Organization → core:Organization` / `schema:WebSite → core:WebSite` / `schema:WebPage → core:WebPage` / `schema:Event → core:Event` / `schema:Product → core:Product` / `schema:SoftwareApplication → core:Software`.<br>A5's only requirement: `schema:SoftwareApplication → core:Software` MUST be recorded as **not** `EXACT_MATCH`, because `input.md:2888` says "Do not silently treat mappings as exact equivalence if they are not" and a software application is not a software product. SC-023's test asserts that. |
| 7 | `TypeMapping` = `SemanticMapping` | **ACCEPTED** | A5 relied on this before A4b's file existed (A5-13) and A4b §D5.1 confirms it field-for-field, eight for eight. No conflict. |
| 8 | A5's withdrawn `TypeSignalSource` enum | **A5 WITHDRAWS** | See D2.2. `source_vocab` + `producer_ref` already carry the axis. |
| 9 | Lookup from an external type ref to candidate mappings | **NOT NEEDED** | A5 originally asked A4b for a `mappings_for_type(source_scheme, source_ref)`. On reading §D5.2, A4b's answer is that the **mapping-set layer owns the lookup** and A5 asks *nothing*; the `TypeSignal`'s `mapping_candidates` are populated by the mapping layer, and A5's type layer only carries them forward. This is the correct direction of dependency: a type hypothesis must never be able to *choose* a mapping (A4b §D5.2's whole argument). |
| 10 | `MappingPayloadTooLarge` / `TenantScopeRefused` | **ACCEPTED as A4b's** | Both are `SemanticMapping`'s construction-time refusals. A5's `TypeHypothesis` carries **candidates**, not `SemanticMapping`s, so it is not on that refusal path at all — and that is another reason the candidate/record split is right. No A5 obligation here. |

**What I do not touch.** `PredicateSignature`, voice normalisation, role normalisation,
participant ordering, operator mapping, `RelationSignal`, `RelationCandidate`, `PredicateHypothesis`,
`PredicateMappingCandidate`, `MappingMatchType`, `MappingSet`, `MappingRegistry`. A2 owns the
first six, A4b the rest.

---

## D3 — The foundational type pack: a **normative vocabulary**, not 32 extractors

### D3.1 The contract, as a normative requirement

This is the user's explicit decision and it is stated as a requirement, not as a rationale:

> **A type existing in the foundational vocabulary does not mean the system must have a
> dedicated extractor for it.**

The converse is equally binding and is what makes the first half non-vacuous:

> **The absence of a type from the foundational vocabulary does not mean a mention of that kind
> is refused, dropped, quarantined or downgraded.**

Both halves are already the brief's position. `input.md:439-445` (verbatim):

> but the existence of `core:Organization` must never imply:
>
> ```text
> everything unknown cannot be Organization
> ```
>
> Unknown remains unknown.

`input.md:455` (verbatim): "They must not be used as an extraction gate."
`input.md:4662-4664` (§110, verbatim): "Do not start by adding dozens of extraction rules. / First
make the substrate correct."

The consequence for the plan is concrete and it is the resolution of D12/§8: **the 31 `core:*`
entity classes and 13 `value:*` value classes are a vocabulary deliverable. The number of
extractor families is a separate, much smaller deliverable, enumerated by FR-141…FR-147 (eight
obligations), and it is nowhere near 31.** At HEAD there are 7 `kind` values (A5-14) and 14
extractor modules; this feature adds **no new extraction framework** and **at most 4 new
instrument modules** (URL/domain, profile-URL, document-structure, event-mention) — all of them
thin wrappers over the existing registry, per FR-140.

### D3.2 What the pack must contain

Pack identity — `input.md:2839-2843` (verbatim), and the string is exactly:

```text
core-atomic-types@1
```

> Create a small foundational pack such as:
>
> ```text
> core-atomic-types@1
> ```
>
> with the atomic type definitions above.

(Confirmed: `core-atomic-types@1` is the literal, at `input.md:2842`. It is the *pack id and
version as one string*, `@`-separated, not a Python module path and not a bare `1`.)

Per-entry fields — `input.md:2847-2858` (verbatim):

> Each type needs:
>
> ```text
> type_ref
> label
> alt_labels
> broader_refs
> narrower_refs
> description
> kind = entity/value
> version
> ```

and `spec.md` FR-029 names the same eight, adding the two prohibitions and one permission
(verbatim): "It MUST NOT encode relation semantics and MUST NOT encode truth; it MAY carry
blocking hints."

and `input.md:2860-2868` (verbatim):

> Do not encode massive relation semantics into the type pack.
>
> The pack may contain:
>
> ```text
> blocking hints
> ```
>
> but not truth.

**The 31 `core:*` entity classes** (`input.md:338-397`, identical to `spec.md` FR-030's
enumeration — 31, not 32; see A5-9):

| §4.1 group | Types |
|---|---|
| Person / agent | `core:Person` `core:Organization` `core:LegalEntity` `core:Group` `core:Agent` |
| Web / digital | `core:WebSite` `core:WebPage` `core:OnlineAccount` `core:SocialProfile` `core:Domain` `core:DigitalResource` |
| Place / geography | `core:PhysicalPlace` `core:Facility` `core:Address` `core:GeographicRegion` `core:Country` `core:StateOrProvince` `core:City` `core:Coordinate` |
| Information | `core:Document` `core:Dataset` `core:CreativeWork` `core:MediaResource` `core:Software` `core:Project` |
| Commercial / physical objects | `core:Product` `core:Service` `core:Asset` `core:Vehicle` `core:FinancialInstrument` |
| Events | `core:Event` |

**The 13 `value:*` value types** (`input.md:403-416`, identical to `spec.md` FR-031):
`value:EmailAddress` `value:PhoneNumber` `value:URL` `value:Handle` `value:Identifier`
`value:IPAddress` `value:Hash` `value:CryptoAddress` `value:Date` `value:DateTime` `value:Money`
`value:Quantity` `value:Coordinate`.

`input.md:419` (verbatim): "Do not force every value into `Entity`."

**Total 44 entries: 31 entity-kind + 13 value-kind.** That is the pack's floor, and — see D3.5 —
not its ceiling and not its obligation on producers.

**Blocking hints** are permitted, and there is already a place for them:
`apps/interpretation/extractors/registry.py:45-62::SemanticHint` exists, with
`recognized=False` meaning "unrecognized" and its own docstring saying "A pack that does not know
a kind yields `recognized=False`, which is a legitimate state, not a rejection: nothing here can
refuse a mention." `spec.md` FR-038 makes this binding: "an ontology miss MUST mean `unknown
type`, never a rejected mention." A pack may carry hints; it may not carry a `deny` field, and
adding one is a stop condition (see D7.6).

### D3.3 Namespace, version, and scheme — so `industry:Bank` can exist

**The gap this job closes.** FR-034 requires a hierarchy that extends past the pack
(`spec.md:510-513`, verbatim):

> **FR-034**: The type space MUST be extensible by hierarchy (`core:Organization` →
> `industry:Bank` → `industry:CommercialBank`), and `broader`/`narrower` relations MUST be
> usable for query expansion, blocking, ranking, validation and role matching — never as an
> extraction gate. Unknown remains unknown. (§5)

but FR-029's eight-field list has **no namespace, no scheme, and no pack-registration mechanism**.
There is literally no field in which "which pack does `industry:Bank` come from" could be written.
And `scheme` — the only vocabulary-ish field anywhere near it — is a field on `TypeHypothesis`
(§6), not on a pack entry, and it means "how to treat this ref" (`SemanticRef`), not "which
namespace".

**The mechanism, specified minimally.** Three additions, all inside the pack object, none of them
a new epistemic level:

```python
# apps/shared/semantic/types.py

CORE_NAMESPACE  = "core"
VALUE_NAMESPACE = "value"

@dataclass(frozen=True)
class TypePackEntry:
    type_ref: str                 # "core:Organization" / "value:URL" / "industry:Bank"
    label: str
    alt_labels: tuple[str, ...] = ()
    broader_refs: tuple[str, ...] = ()
    narrower_refs: tuple[str, ...] = ()      # completed from other entries' broader, never trusted
    description: str = ""
    kind: TypePackKind            # ENTITY | VALUE          <- §63's "kind = entity/value"
    version: str = "1"            # per-entry version       <- §63's `version`
    namespace: str = ""           # "core" | "value" | "industry" | <any tenant-registered ns>
    pack_ref: str = ""            # "core-atomic-types@1" — provenance of THIS entry
    blocking_hints: tuple[str, ...] = ()      # permitted by §63; never a deny list


@dataclass(frozen=True)
class TypePack:
    pack_id: str                  # "core-atomic-types"
    version: str                  # "1"
    namespace: str                # "core"          <- the namespace this pack OWNS
    entries: tuple[TypePackEntry, ...] = ()
    status: PackStatus            # DRAFT | REGISTERED | ACTIVE   (mirrors events.ontology_pack)
```

* **`namespace` is the prefix of `type_ref`, and it is data, not a hard-coded set.**
  `type_ref == f"{namespace}:{local_name}"` is validated on construction, and a `type_ref` whose
  prefix is neither `core` nor `value` is **legal** — that is exactly how `industry:Bank` lives.
  There is no `if namespace == "core"` branch anywhere in the codebase. §5's example
  (`input.md:431-437`, verbatim):
  > ```text
  > core:Organization
  >     ↓
  > industry:Bank
  >     ↓
  > industry:CommercialBank
  > ```
  is therefore reachable by registering a **second pack** (`industry-types@1`, namespace
  `industry`) whose `core:Organization` entry declares `narrower_refs=("industry:Bank",)`.
* **`pack_ref` is a string, not an import.** The foundational pack is data — a
  frozen tuple of entries loaded from a module-level constant, byte-identical across processes
  and hashable for replay. §63's "Do not encode massive relation semantics into the type pack" is
  a size bound as well as a semantic one, and it is the reason the pack is a value and not a
  graph of live objects.
* **Status and version are the existing discipline, not a new one.**
  `apps/shared/events/ontology_pack.py:60-101::OntologyPackRegistry` already implements
  "DRAFT → REGISTERED → ACTIVE; never overwrite a version" and raises
  `ValueError(f"ontology pack version already registered: {pack.pack_version}")`. `TypePack`
  **reuses that registry**, unchanged, rather than growing a second one. `spec.md` §7's
  "Migration numbering is independent" and the constitution's reproducibility rule both want
  immutability per version, and that code already has it.
* **The `relations` list on the existing pack stays inert.** `ontology_pack.py:36-38` declares
  `relations: list[str] = field(default_factory=lambda: ["works_at", "owns", "controls",
  "corresponds_to", "linked_to"])` and `allows_relation()` (`:45-46`) is never called. It stays
  uncalled. A fixed relation list is what `input.md:4214-4233` forbids, and the fix for that is
  not "make it work", it is "leave it dead and say so in a test" (FR-155's test).

### D3.4 `core:Coordinate` vs `value:Coordinate` — the self-contradiction, resolved

A5-10: the same label is an entity in FR-030's list and a value in FR-031's list, in both the
brief and the spec. FR-031 says "A value MUST NOT be forced into `Entity`"; FR-030 puts a
`Coordinate` in the entity list. That is a real contradiction and it needs a decision, not a
shrug.

**Decision.** Both entries stay, with the same `type_ref` local name and different namespaces,
and **`kind` is the load-bearing discriminator** — which is precisely why §63 lists
`kind = entity/value` as a required per-entry field and why `TypePackKind` is a non-defaulted
field above. Semantics:

* `value:Coordinate` — a *geographic measurement as a value* (`"56.9496, 24.1052"`,
  `"40°42'46\"N 74°00'21\"W"`). A value. Never an `Entity`. Sortable, comparable, a scalar.
* `core:Coordinate` — a *located place reference as a thing the platform can talk about*
  (a geocoded point with a name, an authority, a containment relation to a country). An entity.
  Its own coordinates live on it as `value:Coordinate`.

They never collide as references, because `normalize_type_ref` deliberately preserves case and
full form (`vocabularies.py:103-113`: "a reference is an opaque identifier, and `schema:Person`
and `schema:person` are different references"), and the namespace prefix is part of the string. A
consumer that forgets to read `kind` gets two different *strings*, which is the safe failure: it
cannot accidentally treat the value as the entity, because the refs differ.

**Open question OQ-A5-1.** Is `core:Coordinate` intended at all, or is it a brief typo for
`core:GeographicRegion`? The brief lists it in "Place / geography" (`input.md:369`) and again
under "Values" (`input.md:416`). **Stop condition:** if §4.1's intent cannot be established from
the brief, ship both entries as decided above and record the question. Do **not** delete a
vocabulary entry on a guess — a deleted entry is a silent narrowing, which is the one thing
INV-002 forbids. Raised as `UNKNOWN` in the ADR per `input.md:4681-4688`.

### D3.5 FR-030 ("at minimum") vs INV-002 ("never a completeness condition") — the tension, resolved

**The tension, stated plainly.** FR-030:

> **FR-030**: The pack MUST cover, at minimum, entity classes `core:Person`, … `core:Event`. (§4)

INV-002:

> **INV-002**: The type vocabulary is an interpretation instrument — naming, hierarchy,
> aliases, blocking, role hints, mapping surface, validation vocabulary. It is never the
> definition of what exists, a permit/deny gate, a completeness condition, the source of
> truth, or a mandatory relation universe. (§2)

A reader can hold both and still write the wrong code, because "MUST cover at minimum" and "never
a completeness condition" point in opposite directions if the *completeness condition* is read as
being about the *pack's contents* rather than about the *world*. If it is read as being about the
world, FR-030 is fine; if it is read as being about the pack, FR-030 is a violation.

**Resolution, three clauses, and the reading that survives all three:**

1. **`MUST cover` is a requirement on the pack, and only on the pack.** FR-030 obliges
   `TypePack` to *contain* 31 named entries at `core-atomic-types@1`. It is a **fixture
   requirement**: there is a test asserting `pack.contains("core:Organization")` and 30 siblings,
   and that test is about a literal data structure.
2. **`never a completeness condition` is a requirement on everything downstream of the pack.** No
   producer, resolver, blocker, validator, mapper or projector may consult the pack in a way that
   makes a mention's survival, its type, or its extraction depend on the pack containing a
   matching entry. A type reference the pack has never heard of is a first-class `TypeHypothesis`
   with `type_ref="whatever:Thing"`, `scheme=SemanticRef.UNRESOLVED`, `hypothesis_state=UNKNOWN`.
   §97 is the mutation that proves it: `input.md:3921-3927` (verbatim):
   > ```text
   > if core pack does not know type:
   >     continue
   > ```
   >
   > must fail.
   >
   > Unknown semantic types remain observations.
3. **The vocabulary is open upward and downward, permanently.** Entries may be added to the pack
   by a later version (`core-atomic-types@2` is a *new pack version*, never an edit of `@1`, by
   `ontology_pack.py:80-83`), and refs outside every registered namespace are always admissible.
   `input.md:425-427` (verbatim): "The `core:*` vocabulary is deliberately small enough to be
   infrastructure. / It must be possible to extend it."

**Why this resolution and not the other candidates:**

* *Delete FR-030.* Rejected: §108's first bullet is "foundational atomic vocabulary exists"
  (`input.md:4361`) and FR-030 is what makes that testable. Deleting the only enumerating
  requirement leaves the deliverable unfalsifiable.
* *Soften FR-030 to "MAY cover".* Rejected: it would make the pack's contents a matter of
  taste, and §63's whole point is a *small foundational pack* with a *named* floor.
* *Add a "completeness" check anywhere in the pipeline.* Rejected outright — that is the mutation
  of §97 wearing a costume. It would be a new deny path, and the whole architecture is the
  removal of deny paths.
* **Keep both, bound each to its own layer.** Adopted. The clause that makes it non-vacuous is
  the mutation test: FR-156's test *is* "the pack is complete and the pipeline still does not
  care", because the mutation is applied to a pack that satisfies FR-030 in full.

**Restated so no reader can get it wrong, and this is the text that goes in the spec:**

> The pack MUST contain its 31 named entity classes and 13 named value types (FR-030, FR-031).
> The pipeline MUST NOT require the pack to contain anything. A `type_ref` outside every
> registered namespace is a valid `TypeHypothesis` with `hypothesis_state=UNKNOWN`; the mention
> is retained; `UNKNOWN` is a recorded state, never a rejection (FR-038, FR-155, FR-156, §76,
> §97, INV-002, INV-003).

---

## D4 — §8 requirement extraction: seven sub-sections → seven FRs

`input.md:559-728` is the whole of §8, **170 lines**, and it appears **zero** times in
`spec.md`, `data-model.md`, `plan.md`, `tasks.md` or `checklists/requirements.md` (A5-12, defect
**D7**). Each sub-section becomes one FR, quoted from the brief, with a named test. All seven FR
texts are in §D6 below; this section is the derivation and the test map.

### D4.0 §8 preamble — adapt, never duplicate

Brief, `input.md:559-563` (verbatim):

> # 8. ENTITY EXTRACTOR EXPANSION
>
> Complete the deterministic extraction layer around actual atomic types.
>
> Existing extractors must be adapted rather than duplicated into a second unrelated extraction
> framework.

→ **FR-140**. Test: `test_a5_fr140_…` (below) — a *no-new-framework* test. It is a test, not a
preference: the existing fan-out is `extractors/registry.py:107-119::ExtractorRegistry` with
`register_builtin()`, and the new instruments must be reachable from it.

### D4.A Person — §8 A

Brief, `input.md:567-595` (verbatim):

> ### A. Person
>
> Existing:
>
> ```text
> persons.py
> ```
>
> Improve:
>
> * Latin names
> * Cyrillic names
> * initials
> * multi-token names
> * titles
> * person-name contextual cues
> * aliases
> * transliteration
> * Unicode normalization
> * surname-first patterns
> * social/profile names where useful
>
> No assumption:
>
> ```text
> name-shaped string == person
> ```
>
> Every person result is a type hypothesis/mention observation.

→ **FR-141**. Two obligations, and they are separable and separately testable:
(a) coverage of the eleven listed capabilities; (b) the *refusal* of the
`name-shaped string == person` assumption.

Coverage is partly real at HEAD — `persons.py` has `_parse_ru` (`:83`), `_ru_mentions` (`:157`),
`en_name_from_window` (`:218`), `_gazetteer_terms` (`:263`), `_titular_phrase` (`:205`),
`translit.py::transliterate` (`:42`) / `from_latin` (`:61`), `normalize.py::_initials_hypothesis`
(`:103`). That is why the FR says *adapt*: the work is wiring the existing capability to emit
`TypeHypothesis`, plus the gaps (surname-first order, aliases, profile names).

The prohibition is the load-bearing half and it is a test, not a docstring. At HEAD
`persons.py:279 extract_persons` returns `TypedMention(kind="person", …)` with no hypothesis, so
the assumption is currently *structurally* inescapable. FR-141 makes the output a hypothesis with
`hypothesis_state=INFERRED` (not `OBSERVED`) whenever the only evidence is name shape, and the
test asserts that a name-shaped string which no cue supports still produces a hypothesis whose
`extractor_ref` names a cue-bearing instrument or whose `confidence` is below the cue-bearing
floor. **Test**: `test_a5_fr141_…` — golden corpus rows from §82 (A5-16 below).

### D4.B Organization — §8 B

Brief, `input.md:597-632` (verbatim):

> ### B. Organization
>
> Existing:
>
> ```text
> orgs.py
> ```
>
> Extend beyond legal-form-only detection.
>
> Recognize:
>
> * legal-form patterns
> * corporate suffixes
> * institutional names
> * brands
> * agencies
> * universities
> * government bodies
> * media organizations
> * banks
> * companies
> * NGOs
> * organizations inferred from strong contextual structures
>
> Again:
>
> ```text
> organization hypothesis
> ```
>
> not:
>
> ```text
> entity = organization
> ```

→ **FR-142**. Twelve listed recognisers, of which `legal-form patterns` is the only one
`orgs.py` does today (`orgs.py:71 _grammar_layer` plus `orgs.py:43 _dictionary_layer`). So
"extend beyond legal-form-only detection" is accurate and the eleven additions are real work.
The two halves again separate: recognisers emit `TypeSignal`/`TypeHypothesis`;
`entity = organization` never happens, because no producer may mint an `entity_ref`
(`spec.md` FR-075 "NO ENTITY IDS IN PRODUCERS", `input.md:3254`).
**Test**: `test_a5_fr142_…` — §82 rows `Acme Corporation`, `Acme`, `Apple Inc.`,
`University of …`, plus one organisation named **without** any legal form and **without** a
dictionary entry, which must still yield a hypothesis from a contextual-structure signal.

### D4.C WebSite / WebPage / Domain / URL — §8 C

Brief, `input.md:634-663` (verbatim):

> ### C. WebSite / WebPage / Domain / URL
>
> Create deterministic extraction for:
>
> ```text
> https://example.com
> example.com
> www.example.com
> ```
>
> and distinguish:
>
> ```text
> URL
> Domain
> WebSite
> WebPage
> ```
>
> These are not interchangeable.
>
> A URL string is a value.
>
> A WebPage is a resource.
>
> A WebSite is a higher-level resource.
>
> A domain is a namespace/network resource.
>
> Preserve the distinction.

→ **FR-143**. This is the one §8 sub-section that also **fixes a real gap**: at HEAD the
`url`/`domain` patterns exist in `registry.py:84,86` but are **not in any `kind="…"` emit list**
(A5-14: only `crypto`, `handle`, `ip`, `org`, `person`, `phone`, `place` are emitted), so today a
URL produces no typed mention at all. The distinction maps onto the pack as:

| Observed surface | `TypeSignal` → `TypeHypothesis` | Pack entry | `kind` |
|---|---|---|---|
| `https://example.com/a` | one value hypothesis | `value:URL` | VALUE |
| `https://example.com` | one value hypothesis **and** one resource hypothesis | `value:URL` + `core:WebSite` | VALUE + ENTITY |
| `example.com` | one namespace hypothesis | `core:Domain` | ENTITY |
| `www.example.com` | `core:Domain`, with `www` recorded as a **hint**, not a subdomain assertion | `core:Domain` | ENTITY |
| a retrieved page, with content | one resource hypothesis | `core:WebPage` | ENTITY |

"A URL string is a value" is the reason this row exists: **`value:URL` is a `TypeHypothesis`
about a mention, and a `TypeHypothesis` is not an `Entity`** (INV-001, `input.md:419`). "A
WebSite is a higher-level resource" is the reason `www.example.com` must not silently become a
`core:WebSite`: the registrable domain is the resource; the `www` host is a naming convention. The
FR therefore requires the distinction to be **recorded**, not to be inferred away.
**Test**: `test_a5_fr143_…` — one input string yields the exact set above; the four refs are four
distinct strings; and no `TypeAssertion` is produced (signals and hypotheses only, per FR-037).

### D4.D OnlineAccount / SocialProfile — §8 D

Brief, `input.md:665-679` (verbatim):

> ### D. OnlineAccount / SocialProfile
>
> Recognize structured profile URLs and handles.
>
> Examples:
>
> ```text
> github.com/user
> twitter/x.com/user
> linkedin.com/in/user
> t.me/user
> youtube.com/@channel
> ```
>
> Do not infer account identity merely from a display name.

→ **FR-144**. Two obligations:
(a) a **table-driven, versioned** profile-URL/handle instrument. The five shapes above are
*patterns of a site*, not of a person: `github.com/<segment>`,
`(twitter|x).com/<segment>`, `linkedin.com/in/<segment>`, `t.me/<segment>`,
`youtube.com/@<segment>`. Each is a `TypeSignal` whose `producer_ref` names the profile-URL
instrument, with a named profile-URL rule, and an `extractor_version` — because a site changes its
URL shape and an unversioned rule silently rots. The output is a `value:Handle` hypothesis and/or
a `core:OnlineAccount` / `core:SocialProfile` hypothesis, with the site recorded in
`evidence_refs`, never a merged "social identity".
(b) the prohibition. `input.md:679` verbatim: "Do not infer account identity merely from a
display name." At HEAD `contacts.py:221 _handle_mentions` emits `kind="handle"` from a bare
`@name` pattern, which is exactly the forbidden inference in embryo: `@johnsmith` is a handle
*surface*; whether it denotes an account, a person or a spammer is a hypothesis. So FR-144
requires `hypothesis_state=INFERRED` and no `core:OnlineAccount` `TypeAssertion` from a display
name alone — a display name yields a `value:Handle` value hypothesis and nothing else.
**Test**: `test_a5_fr144_…` — the five shapes each produce their hypotheses with the site rule
named; and `test_a5_fr144_display_name_alone_produces_no_account_…` — the display-name case
produces no `core:OnlineAccount` hypothesis at all.

### D4.E Digital identifiers — §8 E

Brief, `input.md:681-694` (verbatim):

> ### E. Digital identifiers
>
> Extend existing indicator extraction:
>
> ```text
> IP
> hash
> CVE
> crypto address
> file path
> identifier
> ```
>
> into value-type hypotheses.

→ **FR-145**. At HEAD the patterns exist in `registry.py:85-95` (`ipv4`, `domain`, `cve`,
`sha256`, `md5`, `windows_file`, `gateway_ip`, `crypto_address`, `strong_token`) and three of
them reach a `kind` (`ip`, `crypto`, and `handle` for phone-adjacent — A5-14). So this is
**extend-and-wire**, again not new-framework. Two notes that are decisions, not restatements:

* **`CVE` and `file path` have no value type in §4.1's list.** There is no `value:CVE`,
  `value:FilePath`, or `value:DomainName` in `input.md:403-416`. They therefore become
  `value:Identifier` hypotheses with the *specific* form recorded in `normalized_surface` and in
  `evidence_refs` (`extraction_rule_id` = `cve` / `windows_file` / …). This is exactly the
  "vocabulary is not a completeness condition" case run in the honest direction: a value the pack
  does not have a word for is still a value, named `value:Identifier`, with the specificity kept
  as evidence. **Adding `value:CVE` would be the alternative** and is a legitimate
  `core-atomic-types@2` change — recorded as an open question, not taken unilaterally (OQ-A5-2,
  stop condition in D7.6).
* **A value is not an entity.** §111 lists "an entity/value ambiguity" as a stop condition
  (`input.md:4676`). So the FR requires these to be `kind=VALUE` hypotheses and requires the
  FR-050 discipline to be inherited: "MUST NOT turn a value into an entity"
  (`spec.md:582-584`). **Test**: `test_a5_fr145_…` — all six indicator families produce `VALUE`
  hypotheses with a named `extraction_rule_id`; and a mutation that coerces any of them to
  `kind=ENTITY` is caught by name.

### D4.F Documents — §8 F

Brief, `input.md:696-706` (verbatim):

> ### F. Documents
>
> Detect/documentize:
>
> * URLs pointing to files
> * filenames
> * document IDs
> * report-like structures
> * PDFs/documents when source metadata provides them
> * citations
> * document title/identifier structure

→ **FR-146**. Seven listed detectors. Two of them (**citations**, **document IDs**) are
*relation* concerns and this is the boundary I must not cross:

| §8 F item | This job's obligation | The other job's obligation |
|---|---|---|
| URLs pointing to files | `core:Document` hypothesis + `value:URL` value hypothesis (FR-143 already) | — |
| filenames | `core:Document` hypothesis; extension is evidence, not the type | — |
| document IDs | `value:Identifier` **value hypothesis** (FR-145) | the `REFERENCE` signal family (`spec.md` FR-046) |
| report-like structures | `core:Document` hypothesis from structure | — |
| PDFs/documents from source metadata | `core:Document` hypothesis; `TypeSignal.source_vocab` = `"opengraph"`/`"html-meta"` | — |
| citations | `value:Identifier` value hypothesis for the cited id | `REFERENCE` signal family (FR-046) — **not mine** |
| document title/identifier structure | the title becomes a `context_ref` for FR-159 | — |

"I detect the *thing*; the relation agent emits the *edge*" is the whole boundary, and it is
`input.md:725-726` (verbatim, from §8 G, and it applies identically here): "An event mention is
not a relation." **Test**: `test_a5_fr146_…` — the seven rows each produce a named hypothesis;
and `test_a5_fr146_no_relation_…` — no document detector emits a `RelationSignal`, and the
`relations`-side assertion is a source scan of the new modules for `RelationSignal` /
`GraphEdge` imports, which is the shape of `spec.md` FR-099 / `input.md:3944-3952`.

### D4.G Event mentions — §8 G

Brief, `input.md:708-726` (verbatim):

> ### G. Event mentions
>
> An event mention is not a relation.
>
> Create event/entity hypotheses for:
>
> ```text
> conference
> meeting
> acquisition
> launch
> publication
> incident
> transaction
> election
> appointment
> ```
>
> But do not turn event words directly into claims.

→ **FR-147**. The nine listed event words. The two prohibitions are the substance and they are
quoted above: "An event mention is not a relation." and "But do not turn event words directly
into claims."

**The explicit rule, stated as a requirement (the task's "event word must not become a claim"):**

> A recognised event word produces (a) a `TypeSignal` recording the lexical match with its span,
> and (b) a `TypeHypothesis(type_ref="core:Event", hypothesis_state=OBSERVED, …)`. It produces
> **no** `RelationSignal`, **no** `RelationCandidate`, **no** `TypeAssertion` about a participant
> role, and **no** claim of any kind. A participant, a date, a place or an organisation appearing
> near an event word is a *separate* mention with its own hypotheses; co-presence is recorded as
> a co-occurrence, never as event participation. The word `acquisition` in a document does not
> license the statement "X acquired Y" — that is the predicate regime's earned mapping
> (`input.md:4235-4247`: the relational space "begins as observed structure and only later
> becomes known predicate when the semantic system earns that mapping"), and this feature's §8
> obligations do not reach it.

That is the strictest reading available and it is the correct one, because the looser reading
("event words may produce a *candidate*") would make FR-147 depend on A2's identity work and
would put an extraction obligation inside a semantic regime. **The test is a mutation test**, and
it is the one the brief's §8 G demands:

> **Test**: `test_a5_fr147_event_word_does_not_become_a_claim_…` — a corpus of all nine words in
> isolation and in a participant-bearing sentence (`"Acme announced the acquisition of Contoso
> in March."`) yields `core:Event` hypotheses, `Mentions` for `Acme`/`Contoso`/`March`, and
> **zero** `RelationClaim`s and **zero** `GraphEdge`s. The mutation to run is
> `input.md:3926-3927` in type form — *if the pack has a `core:Event`, emit a claim* — and the
> named test must fail.

### D4.8 §82 — the golden corpus, quoted

`input.md:3461-3513` (verbatim, abridged only in the ellipsis I mark):

> Add a deterministic golden corpus covering:
>
> ```text
> John Smith
> Acme Corporation
> Acme
> Apple
> Apple Inc.
> example.com
> https://example.com/a
> @johnsmith
> john@example.com
> +370...
> 192.168.1.1
> CVE-...
> Bitcoin address
> New York
> Lithuania
> University of ...
> GitHub profile
> LinkedIn profile
> PDF/report
> dataset
> software repository
> event
> product
> service
> vehicle
> financial instrument
> ```
>
> Include ambiguity:
>
> ```text
> Apple
> Amazon
> Jordan
> Washington
> Mercury
> ```
>
> where reasonable.
>
> Each case should test:
>
> ```text
> raw mention
> type hypotheses
> mapped type
> unknown types
> alternative types
> no entity resolution assumption
> ```

Every §8 sub-section's test above is a **row of this corpus**, and the corpus is per-FR-141…FR-147
plus FR-140. Rows without an instrument (`financial instrument`, `vehicle`, `service`) are
**negative-assertion rows**: they assert that the mention is retained with
`hypothesis_state=UNKNOWN` and no `TypeAssertion` — the §97 mutation, run as data. `no entity
resolution assumption` is the last column and it is INV-001 as a fixture property: no corpus row
may assert that two mentions are the same entity.

---

## D5 — The nine missing Success Criteria

`input.md:4355-4369` (verbatim):

> # 108. ACCEPTANCE CRITERIA
>
> Feature 021 is complete only when ALL are true.
>
> ## Entity substrate
>
> * foundational atomic vocabulary exists
> * entity/value types are distinct
> * type hypotheses are first-class
> * type assertions remain durable
> * multiple type hypotheses are preserved
> * unknown types are preserved
> * external mappings are explicit
> * ontology never gates extraction
> * mention/entity separation preserved

Nine bullets, **zero** of which has a success criterion (defect **D8**: "29 of §108's 47
acceptance bullets have no success criterion — all 9 entity-substrate bullets"). `spec.md` ends at
**SC-016**, so these continue from **SC-017**. Each is written to be measurable: a count, an id, a
name or a mutation.

```markdown
- **SC-017**: The registered type pack `core-atomic-types@1` exposes 31 entity-kind entries and
  13 value-kind entries, every one carrying all eight §63 fields (`type_ref`, `label`,
  `alt_labels`, `broader_refs`, `narrower_refs`, `description`, `kind`, `version`) plus
  `namespace` and `pack_ref`; `len(pack.entries) == 44`; and the registry rejects a second
  registration of `core-atomic-types@1` with `ValueError`. Test: `test_a5_sc017_…`.
- **SC-018**: For every one of the 44 entries, `kind` is read from the entry and never inferred
  from the ref, and `core:Coordinate` and `value:Coordinate` are two distinct refs with opposite
  `kind`s; a consumer that receives `value:EmailAddress` never receives an `Entity`. Test:
  `test_a5_sc018_…` plus a mutation that flips a value entry's `kind` to `ENTITY`, which fails.
- **SC-019**: `TypeHypothesis` is an importable frozen dataclass with exactly the thirteen §6
  fields and a `hypothesis_state` whose value set is exactly
  `{UNKNOWN, OBSERVED, INFERRED, MAPPED, AMBIGUOUS, CONFLICTING}`; constructing one with a
  seventh state raises; and `semantic.types` imports nothing from `apps.control-plane` and
  nothing from `db.schema`. Test: `test_a5_sc019_…` and a module-scan test for the forbidden
  imports.
- **SC-020**: A `TypeAssertion` written before a `TypeHypothesis` set changes is still
  byte-identical after, and a promotion to `SemanticStatus.INFERRED` yields a new
  `type_assertion_id` under the *same* `logical_type_assertion_id` — verified over a store
  round trip, not over a fixture. Test: `test_a5_sc020_…`.
- **SC-021**: The surface `"Apple"` produces **at least three** retained `TypeHypothesis` values
  on one mention — `core:Person`, `core:Organization`, `core:Product` (§7, verbatim) — with
  distinct `confidence` values, non-empty `evidence_refs` on each, no hypothesis deleted by a
  later one, and no `TypedMention.kind` field that could silently select one. Test:
  `test_a5_sc021_…` (`input.md:528-535`).
- **SC-022**: A mention whose `type_ref` is in no registered namespace is retained end to end as
  a `TypeHypothesis` with `hypothesis_state=UNKNOWN`, survives a store round trip, and the §97
  mutation `if core pack does not know type: continue` fails a named test. Test:
  `test_a5_sc022_unknown_type_dropped_mutation_…` (`input.md:3916-3927`).
- **SC-023**: Every cross-vocabulary type statement the corpus produces is a `TypeSignal` with a
  populated `source_vocab`, `surface` and `mapping_candidates`, followed by zero direct
  `TypeAssertion`s; and the seven §64 mappings exist as `SemanticMapping` records with
  `mapping_set_id` and `mapping_set_version` set and with `schema:SoftwareApplication →
  core:Software` recorded as **not** `EXACT_MATCH`. Test: `test_a5_sc023_…`
  (`input.md:2876-2890`).
- **SC-024**: With a pack satisfying FR-030 and FR-031 in full, zero producers, resolvers,
  blockers, validators, mappers or projectors consult `TypePack` membership to decide whether a
  mention exists, is typed, or is retained; the pack is provably unreachable from every extraction
  path, and a corpus row with no pack entry passes identically to a corpus row with one. Test:
  `test_a5_sc024_ontology_never_gates_…` plus the §97 mutation.
- **SC-025**: `Mention`, `TypeHypothesis`, `TypeAssertion` and `Entity` are four distinct Python
  types, `TypeHypothesis` is not a subclass or alias of any of the others, no producer mints an
  `entity_ref`, and no corpus row asserts that two mentions are one entity. Test:
  `test_a5_sc025_…` (INV-001, `spec.md:359-362`).
```

**Three further SCs, beyond the nine, closing D7's unowned FR-035…FR-040** (defect **D1**:
"52 of 102 FRs have no implementing task and no checklist item"). A requirement with no
success criterion is the same defect one level down, and these three cover the seven §8 FRs
without writing seven more SCs:

```markdown
- **SC-026**: The §82 entity-type corpus runs green with every one of the seven §8 sub-sections
  covered — person, organization, URL/domain/WebSite/WebPage, profile-URL/handle, the six
  indicator families, the seven document detectors, and the nine event words — and every coverage
  row is cited by the test that asserts it. Test: `test_a5_sc026_…`
  (`input.md:559-728`, `input.md:3459-3513`).
- **SC-027**: The type pipeline executes `Observation → Mention → TypeSignal → TypeHypothesis →
  SemanticRegime interpretation → TypeAssertion` in that order with every stage exposing its
  product, and a re-read after a later `INFERRED` promotion shows **all** prior states still
  present. Test: `test_a5_sc027_…` (`input.md:807-816`, `input.md:846-854`).
- **SC-028**: The type pipeline consumes the eight §77 context inputs *by reference only*, each
  naming the bounded neighbourhood it read, and produces **zero** claims from any of them; the
  `iPhone/MacBook/iOS` vs `red apple/fruit/nutrition` example yields a *strengthened* competing
  hypothesis set, not a single chosen type. Test: `test_a5_sc028_…`
  (`input.md:3303-3354`).
```

### D5.1 §108's Lifecycle and Boundedness bullets — ownership ruling

**Lifecycle (5 bullets, `input.md:4388-4394`) — NOT mine.** Verbatim:

> * Candidate exists before material
> * Material exists before validation
> * Validation exists before admission
> * RelationClaim exists only after admission
> * GraphEdge exists only after RelationClaim

Every one is about the **relation** lifecycle and is already carried by `spec.md` FR-056/FR-057
and the `ExecutionResult` FR-055 stage list. None mentions a type. **Ruling: belongs to the
lifecycle/execution agent. I write no SC for them, and I claim none of them.**

**Boundedness (4 bullets, `input.md:4421-4426`) — NOT mine to write, but I take one obligation.**

> * no O(N²) global mention sweep
> * every producer names neighbourhood
> * hard ceilings are machine checked
> * cost metrics are reported

These are `input.md` §72, which the review (defect **D9**) notes has no enforcing test, and they
are about relation pair generation. **Ruling: the bullets belong to the boundedness/producer
agent; I write no SC for them.** But §77's context-aware type resolution (FR-159, mine) reads
*neighbour mentions*, and if my implementation reaches them by scanning the document I have
smuggled an O(N²) sweep into the type path where nobody is watching for it. So FR-159 carries
its own boundedness clause — it MUST name the neighbourhood it read, and it MUST be a bounded
structural neighbourhood, never a document sweep — and the named test for it is
`test_a5_fr159_context_reads_a_bounded_named_neighbourhood_…`. **That is the type layer's
contribution to the boundedness bullets, and it is deliberately one clause on one FR, not four
bullets I do not own.**

**Persistence (6) and Projection (5) and Relation substrate (14) and Determinism (5) — NOT
mine**, except one interaction: SC-020 (assertions remain durable) is mine because
`TypeAssertion` is the entity-side durable type, and the round trip it needs is a persistence
agent's column set. Named dependency: SC-020's test is *verified only offline* unless the
persistence agent has landed the columns. Per the brief's own discipline
(`spec.md:934-936`: "ORM/migration parity and DDL invariants are provable offline; live
round-trip is not. Anything verified only offline MUST be reported as such"), SC-020 is reported
as `verified only offline` until then, and says so.

---

## D6 — New FR text, verbatim, starting at `FR-140`

Numbering: `spec.md` currently ends at **FR-100**; these start at **FR-140** to avoid collision
with any concurrently-added FR-101…FR-139. If another job claims FR-140, the whole block shifts
and must be renumbered as a unit — the block is internally cross-referential.

Every FR below names its test method. Test names use the `test_a5_frNNN_…` /
`test_a5_scNNN_…` convention so they are greppable, collision-free across jobs, and each is
independently citable from the checklist's FR column (which currently maps zero FRs — defect
**D5**).

### D6.1 The one-hypothesis rule and the set container

```markdown
- **FR-140**: The deterministic extraction layer MUST be completed by **adapting** the existing
  extractors and registry — zero new extraction frameworks. `extractors/registry.py`'s
  `ExtractorRegistry` remains the single fan-out; `TypedMention`, `SOURCE_ORDER` and
  `to_dict()`'s `_sorted_dict` determinism are retained. A new instrument MUST be reachable from
  `register_builtin()` / `register_deterministic_extractors()` and MUST emit
  `list[TypedMention]`. A parallel module that re-implements segmentation, normalisation or
  dispatch is a defect, not an extension. (§8 preamble)
  **Test**: `test_a5_fr140_adapt_not_duplicate_extraction_framework` — asserts the new
  instruments are reachable from the existing registry, that no module under `extractors/`
  defines a second dispatch type, and that `extract_deterministic` output is unchanged for the
  §107 baseline corpus.
```

```markdown
- **FR-141**: The person instrument MUST cover Latin names, Cyrillic names, initials, multi-token
  names, titles, person-name contextual cues, aliases, transliteration, Unicode normalization,
  surname-first patterns and social/profile names where useful; it MUST be an adaptation of
  `persons.py` / `normalize.py` / `translit.py`, not a new implementation. It MUST NOT treat
  `name-shaped string == person` as a conclusion: a mention supported only by name shape yields a
  `TypeHypothesis` at `hypothesis_state=INFERRED` whose `extractor_ref` names a cue-bearing
  instrument or whose `confidence` is below the cue-bearing floor, and never a
  `TypeAssertion`. Every person result is a `TypeHypothesis` on a mention. (§8 A)
  **Test**: `test_a5_fr141_person_covers_eleven_capabilities` (§82 rows `John Smith`,
  `Иван Петров`, `J. Smith`, `Smith, John`, `Dr Ivan Petrov`, `@johnsmith`) and
  `test_a5_fr141_name_shaped_string_is_not_a_person_conclusion`.
```

```markdown
- **FR-142**: The organization instrument MUST extend beyond legal-form-only detection and
  recognise legal-form patterns, corporate suffixes, institutional names, brands, agencies,
  universities, government bodies, media organizations, banks, companies, NGOs, and
  organizations inferred from strong contextual structures; it MUST be an adaptation of
  `orgs.py`. Each recognition yields a `core:Organization`-or-narrower `TypeHypothesis`; no
  producer may mint an `entity_ref` or record `entity = organization`. (§8 B)
  **Test**: `test_a5_fr142_organisation_recognisers_exceed_legal_form` (§82 rows `Acme
  Corporation`, `Acme`, `Apple Inc.`, `University of …`, plus one suffix-free, dictionary-free
  name that must still yield a hypothesis from a contextual-structure signal) and
  `test_a5_fr142_no_producer_mints_an_entity_ref`.
```

```markdown
- **FR-143**: URL, domain, WebSite and WebPage extraction MUST be deterministic and MUST preserve
  the four as four distinct types: `https://example.com/a` is a `value:URL`; `example.com` is a
  `core:Domain`; `www.example.com` is a `core:Domain` with `www` recorded as a hint and not as a
  `subdomain` assertion; a retrieved page is a `core:WebPage`; a registrable host serving
  multiple pages is a `core:WebSite`. A URL string is a value, a WebPage and a WebSite are
  resources at different levels, and a domain is a namespace/network resource. The distinction
  MUST be recorded, never inferred away, and none of the four may produce a `TypeAssertion`
  directly. (§8 C)
  **Test**: `test_a5_fr143_url_domain_website_webpage_stay_four_types` — one input yields exactly
  the set above, the four refs are four distinct strings, and zero `TypeAssertion`s are emitted.
```

```markdown
- **FR-144**: A table-driven, versioned profile-URL and handle instrument MUST recognise
  `github.com/<segment>`, `(twitter|x).com/<segment>`, `linkedin.com/in/<segment>`,
  `t.me/<segment>` and `youtube.com/@<segment>`, each as a `TypeSignal` naming its
  `extraction_rule_id` and `extractor_version`, yielding `value:Handle` and/or
  `core:OnlineAccount` / `core:SocialProfile` hypotheses with the site in `evidence_refs`. It
  MUST NOT infer account identity from a display name: a bare `@name` yields a `value:Handle`
  value hypothesis and no `core:OnlineAccount` hypothesis. (§8 D)
  **Test**: `test_a5_fr144_profile_urls_and_handles` and
  `test_a5_fr144_display_name_alone_yields_no_account_hypothesis`.
```

```markdown
- **FR-145**: Indicator extraction MUST extend — not duplicate — the existing instruments to emit
  **value-type** hypotheses for `IP`, `hash`, `CVE`, `crypto address`, `file path` and
  `identifier`. A value with no dedicated `value:*` entry (today: `CVE`, `file path`) MUST be
  recorded as `value:Identifier` with the specific form preserved in `normalized_surface` and
  `extraction_rule_id`. No value may be coerced to `kind=ENTITY`. (§8 E)
  **Test**: `test_a5_fr145_indicators_become_value_hypotheses` (all six families, with a named
  rule id) and the mutation that coerces a value to an entity, which fails a named test.
```

```markdown
- **FR-146**: Document instrumentation MUST detect and documentize URLs pointing to files,
  filenames, document IDs, report-like structures, PDFs/documents where source metadata provides
  them, citations, and document title/identifier structure. A filename's extension is evidence,
  not the type. Document **casing** and document **identifiers** are value hypotheses
  (`value:URL`, `value:Identifier`); the `REFERENCE` signal family for citations remains owned by
  the relation substrate, and no document detector may emit a `RelationSignal` or a `GraphEdge`.
  (§8 F)
  **Test**: `test_a5_fr146_seven_document_detectors` and
  `test_a5_fr146_no_document_detector_emits_a_relation` (a source scan of the new modules).
```

```markdown
- **FR-147**: A recognised event word — `conference`, `meeting`, `acquisition`, `launch`,
  `publication`, `incident`, `transaction`, `election`, `appointment` — MUST produce a
  `TypeSignal` recording the lexical match and its span, and a
  `TypeHypothesis(type_ref="core:Event", hypothesis_state=OBSERVED)`. **An event word MUST NOT
  become a claim.** Specifically it MUST NOT produce a `RelationSignal`, a `RelationCandidate`, a
  participant-role `TypeAssertion`, a `RelationClaim` or a `GraphEdge`. A participant, date, place
  or organisation near an event word is a separate mention with its own hypotheses; co-presence
  is recorded as co-occurrence, never as event participation. (§8 G)
  **Test**: `test_a5_fr147_event_word_never_becomes_a_claim` (all nine words, alone and in
  `"Acme announced the acquisition of Contoso in March."`, asserting zero claims and zero edges)
  and the mutation *if the pack has `core:Event`, emit a claim*, which must fail.
```

### D6.2 `TypeHypothesis`: one hypothesis, the set, the six states

```markdown
- **FR-148**: `TypeHypothesis` MUST be exactly ONE interpretation candidate and MUST NOT be a
  container of candidates. It MUST be a frozen dataclass carrying the thirteen §6 fields
  `type_surface`, `normalized_surface`, `type_ref`, `scheme`, `hypothesis_state`, `confidence`,
  `source_ref`, `extractor_ref`, `extractor_version`, `evidence_refs`, `context_ref`,
  `semantic_regime_ref`, `mapping_candidates` — and no others. It MUST NOT carry `mention_ref`,
  a children collection, an `entity_ref`, a content-addressed id, or any resolution verdict. It
  MUST remain distinct from `TypeAssertion`, which is evidence-bearing and id-bearing. A
  hypothesis narrows a comparison and is discarded with it; durable typing lives on
  `TypeAssertion`'s existing two-level identity. (§6, §3, §103, INV-001)
  **Test**: `test_a5_fr148_type_hypothesis_is_one_hypothesis` — `dataclasses.fields()` equals the
  thirteen-name tuple exactly, the class is frozen, and constructing one with `mention_ref=` or
  `hypotheses=` raises `TypeError`.
```

```markdown
- **FR-149**: The **set** of competing hypotheses MUST be owned by the mention, never by a
  hypothesis. `TypedMention` MUST gain `type_hypotheses: tuple[TypeHypothesis, ...] = ()` and
  `ResolutionMention` MUST gain `type_hypotheses: tuple[TypeHypothesis, ...] = ()`, beside
  `ResolutionMention.type_assertions`. `TypedMention.kind: str` MUST be retained unchanged as a
  coarse producer classification and MUST NOT be compared against the vocabulary. The set MUST be
  frozen, de-duplicated by `(type_ref, scheme, hypothesis_state)` keeping the highest-confidence
  occurrence, and ordered by `(-confidence, type_ref, scheme, hypothesis_state)`, reusing
  `semantic.blocking._ordered_hypotheses` rather than a second ordering implementation. No new
  container type may be introduced. (§7, §3, §103)
  **Test**: `test_a5_fr149_the_set_lives_on_the_mention` and
  `test_a5_fr149_hypothesis_set_order_is_arrival_independent`.
```

```markdown
- **FR-150**: `hypothesis_state`'s value set MUST be exactly `UNKNOWN`, `OBSERVED`, `INFERRED`,
  `MAPPED`, `AMBIGUOUS`, `CONFLICTING`. No other member may exist, and no state may be spelled
  `RESOLVED`, `UNRESOLVED` or `AMBOUSSED`. `hypothesis_state` MUST NOT be confused with
  `TypeAssertion.status` (`SemanticStatus`): a hypothesis does not resolve, and the two questions
  MUST be answerable from separate fields on separate types. (§6 verbatim)
  **Test**: `test_a5_fr150_exactly_six_states` (a set-equality assertion over
  `set(HypothesisState)`) and `test_a5_fr150_hypothesis_state_is_not_semantic_status`.
```

```markdown
- **FR-151**: `semantic.types` MUST depend only on `semantic.contracts` (`SemanticRef`,
  `content_key`), `semantic.vocabularies` (`normalize_surface_form`, `normalize_type_ref`) and
  `semantic.type_signal` (`TypeMappingCandidate`, owned by A4b), plus stdlib. It MUST import
  nothing from `apps.control-plane`, nothing from `db.schema`, and no graph, claim, admission or
  projection symbol. In particular the control-plane ORM enum `CandidateResolutionState` — whose
  members are `OPEN`, `MATCHED`, `SUPERSEDED`, `REJECTED`, `QUARANTINED` — MUST NOT be used as a
  type-layer state, because `shared` is imported *by* control-plane and the dependency would
  invert the layering. The deliberate id asymmetry MUST be locked: `TypeSignal` has a `signal_id`,
  `TypeHypothesis` has none and no `mention_ref`, `TypeAssertion` has two. (§103 layering,
  `db/schema.py:70-75`, A4b §D5.2)
  **Test**: `test_a5_fr151_shared_type_layer_imports_no_control_plane_symbol` — an AST scan of
  `apps/shared/semantic/types.py` for forbidden import roots, plus a reverse-import assertion
  that `import semantic.types` succeeds with `apps.control-plane` absent from `sys.modules`; plus
  `test_a5_fr151_id_asymmetry_is_locked`.
```

### D6.3 The pack: identity, versioning, scheme, and the extractor contract

```markdown
- **FR-152**: A versioned foundational type pack MUST exist with the identity
  `core-atomic-types@1` — pack id `core-atomic-types`, version `1`, as one `@`-separated string.
  It MUST be a frozen value (a tuple of entries) so that two processes load byte-identical
  content, and it MUST be registered through the existing `OntologyPackRegistry` discipline
  (`DRAFT → REGISTERED → ACTIVE`, never overwritten). A change to pack contents MUST be a NEW
  pack version; an existing version MUST NOT be edited. (§63 verbatim, §4.1)
  **Test**: `test_a5_fr152_pack_identity_is_core_atomic_types_at_1` and
  `test_a5_fr152_a_pack_version_is_never_overwritten`.
```

```markdown
- **FR-153**: Every pack entry MUST expose all eight §63 fields — `type_ref`, `label`,
  `alt_labels`, `broader_refs`, `narrower_refs`, `description`, `kind ∈ {entity, value}`,
  `version` — plus `namespace`, `pack_ref` and `blocking_hints`. `kind` MUST be a required,
  non-defaulted field read from the entry and NEVER inferred from the `type_ref` prefix. An
  entry MUST NOT encode relation semantics and MUST NOT encode truth; `blocking_hints` MAY be
  present and MUST NOT be able to express a denial. (`narrower_refs` MUST be completed from other
  entries' `broader_refs`, and a one-sided declaration is not a disagreement.) (§63, FR-029,
  §65)
  **Test**: `test_a5_fr153_every_entry_carries_all_eight_fields` and
  `test_a5_fr153_kind_is_read_not_inferred` and the mutation that flips a value entry's `kind`,
  which fails.
```

```markdown
- **FR-154**: The type space MUST be extensible by hierarchy **across packs**. Each entry MUST
  carry a `namespace`, and `type_ref` MUST equal `"<namespace>:<local_name>"`. A namespace other
  than `core`/`value` MUST be legal with no special-casing anywhere in the codebase, so
  `core:Organization` → `industry:Bank` → `industry:CommercialBank` is reachable by registering a
  second pack whose entry declares `narrower_refs`. `broader_refs`/`narrower_refs` MUST be usable
  for query expansion, blocking, ranking, validation and role matching, and MUST NOT be usable as
  an extraction gate. `narrower_refs` MUST be derivable from the union of all entries' `broader_refs`
  and MUST never contradict them. (§5, §104, FR-034)
  **Test**: `test_a5_fr154_industry_namespace_needs_no_code_change` — register
  `industry-types@1` at test time, assert the chain resolves, and assert zero `if namespace ==
  "core"`-shaped branches exist by source scan; plus
  `test_a5_fr154_hierarchy_is_never_an_extraction_gate`.
```

```markdown
- **FR-155**: **A type existing in the foundational vocabulary does not mean the system must have
  a dedicated extractor for it; and the absence of a type from the vocabulary does not mean a
  mention of that kind is refused, dropped, quarantined or downgraded.** The pack is a naming,
  hierarchy, alias, blocking-hint, role-hint, mapping-surface and validation instrument. It MUST
  NOT be a permit/deny gate, a completeness condition over the world, the source of truth, or a
  mandatory universe. The number of extractor families is a separate deliverable from the
  number of vocabulary entries, and neither may be derived from the other. The `relations` list on
  `events/ontology_pack.py` MUST remain uncalled — a fixed relation list is what §104 forbids.
  (§2, §5, §104, §110, INV-002)
  **Test**: `test_a5_fr155_vocabulary_membership_implies_no_extractor_obligation` and
  `test_a5_fr155_inert_relations_list_stays_inert` (an assertion that `allows_relation` has zero
  callers) and a source scan proving the number of pack entries and the number of instruments are
  independent constants.
```

```markdown
- **FR-156**: The pack MUST contain its 31 named entity classes (FR-030) and 13 named value types
  (FR-031) — 44 entries — and **no component downstream of the pack may require the pack to
  contain anything**. A `type_ref` outside every registered namespace MUST be a valid
  `TypeHypothesis` with `hypothesis_state=UNKNOWN`; the mention MUST be retained; `UNKNOWN` is a
  recorded state, never a rejection. This reconciles FR-030's "at minimum" with INV-002's ban on
  the vocabulary being "a completeness condition": **`MUST cover` binds the pack's contents as a
  fixture requirement; `never a completeness condition` binds everything downstream of it.**
  (§2, §76, §97, INV-002, INV-003)
  **Test**: `test_a5_sc017_pack_holds_44_entries` plus
  `test_a5_fr156_ontology_miss_is_unknown_never_rejection` and the §97 mutation
  `if core pack does not know type: continue` against a **pack that satisfies FR-030 in full**,
  which must fail — the mutation is only meaningful when the pack is complete.
```

### D6.4 The type pipeline, context, and type/role mutual consumption

```markdown
- **FR-157**: `TypeSignal` MUST exist as a distinct frozen observation type carrying at least
  `source_vocab`, `surface` and `mapping_candidates` (the `tuple[TypeMappingCandidate, ...]` of
  §9/FR-035, per A4b §D5.2), plus `mention_ref`, `structural_path`, `observation_refs`,
  `evidence_refs`, `producer_ref` and `signal_id`. Its `signal_id` MUST be derived from
  `(tenant_id, producer_ref, mention_ref, source_vocab, surface, structural_path)` and MUST NOT
  include `mapping_candidates`. A `TypeSignal` MUST NOT carry a `core:`/`value:` reference — the
  first moment a local type may appear on this path is `TypeHypothesis` — MUST NOT carry a
  commitment, a status or a resolution, and MUST NOT be projectable. It is the entity-side
  analogue of `RelationSignal` and is **not** a `SignalKind`; the §15 relation vocabulary MUST be
  unchanged. Every §8 and §9 producer MUST emit a `TypeSignal` and MUST NOT emit a
  `TypeAssertion`. A second enumeration over the same axis as `source_vocab`/`producer_ref` MUST
  NOT be introduced. (§9, FR-035, §10, §102, §55 `TYPE_SIGNALS` stage)
  **Test**: `test_a5_fr157_type_signal_is_observation_not_commitment`,
  `test_a5_fr157_every_family_emits_a_signal` (the six families of D2.2), and
  `test_a5_fr157_no_type_signal_emits_an_assertion`; plus
  `test_a5_fr157_no_second_enumeration_over_source_vocab` (a source scan for a `TypeSignalSource`-
  shaped enum).
```

```markdown
- **FR-158**: The type pipeline MUST run `Observation → Mention → TypeSignal → TypeHypothesis →
  SemanticRegime interpretation → TypeAssertion` in that order, each stage exposing the object it
  produced, and MUST retain **all** prior states: a later `INFERRED` status MUST be a new
  `TypeAssertion` revision under the same `logical_type_assertion_id`, never a destructive
  replacement, and MUST NOT delete, downgrade or overwrite any `TypeHypothesis`. (§10 verbatim)
  **Test**: `test_a5_fr158_pipeline_order_and_stage_products` and
  `test_a5_fr158_promotion_is_a_new_revision_under_one_logical_id` and
  `test_a5_fr158_promotion_destroys_no_hypothesis`.
```

```markdown
- **FR-159**: Type resolution SHOULD consume already-available context — document title, section
  heading, DOM parent, table heading, neighbour mentions, URL/domain, metadata, language — and
  MUST record `context_ref` on every hypothesis it changed. It MUST represent competing
  hypotheses with evidence and MUST NOT encode a universal deterministic truth rule: the
  `iPhone/MacBook/iOS` example strengthens a `core:Organization` hypothesis and the
  `red apple/fruit/nutrition` example strengthens a `core:Product` hypothesis **as competing
  members of one set**, and neither may collapse the set to a single chosen type. Context reads
  MUST be confined to a **bounded, named structural neighbourhood**, MUST NOT be a document-wide
  sweep, and the neighbourhood read MUST be reported as a countable metric. (§77 verbatim)
  **Test**: `test_a5_fr159_context_strengthens_competing_hypotheses` and
  `test_a5_fr159_context_reads_a_bounded_named_neighbourhood` and the mutation that reduces a
  hypothesis set to a single winner, which fails.
```

```markdown
- **FR-160**: A mention's `type_hypotheses` and a relation signal's `role_hypotheses` MUST be
  mutually consumable, so that resolution and blocking can exploit both — e.g. a `works_for`
  operator hinting a `Person-like` subject and an `Organization-like` object. Those hints MUST
  remain hints: they MUST NOT become truth, MUST NOT produce a `TypeAssertion` by themselves, and
  MUST NOT change a hypothesis's `hypothesis_state` above `INFERRED` on operator affordance alone.
  (§71 verbatim, §72, FR-039a)
  **Test**: `test_a5_fr160_type_and_role_hints_are_mutually_consumable` and
  `test_a5_fr160_operator_affordance_never_becomes_truth` (the mutation: promote an affordance-
  derived hypothesis to a `TypeAssertion`, which must fail).
```

### D6.5 Cross-reference integrity of the new block

| FR | brief § | closes |
|---|---|---|
| FR-140 | §8 preamble | D7 (adapt-not-duplicate) |
| FR-141 | §8 A | D7 |
| FR-142 | §8 B | D7 |
| FR-143 | §8 C | D7 |
| FR-144 | §8 D | D7 |
| FR-145 | §8 E | D7 |
| FR-146 | §8 F | D7 |
| FR-147 | §8 G | D7 |
| FR-148 | §6, §3, §103 | E3, A5-1, A5-2, A5-3, A5-4 |
| FR-149 | §7, §3, §103 | E3, A5-6, A5-8 |
| FR-150 | §6 | E3, A5-4 |
| FR-151 | layering | A5-1 |
| FR-152 | §63, §4.1 | §108 bullet 1 |
| FR-153 | §63, FR-029 | §108 bullet 1, bullet 2 |
| FR-154 | §5, §104, FR-034 | FR-029's missing namespace/scheme |
| FR-155 | §2, §5, §104, §110 | D7's "32 extractors" misreading; INV-002 |
| FR-156 | §2, §76, §97 | FR-030 ↔ INV-002 tension (D3.5) |
| FR-157 | §9, §10, §102 | A5-11, FR-035 |
| FR-158 | §10 | FR-037, SC-027 |
| FR-159 | §77 | FR-039, SC-028 |
| FR-160 | §71, §72 | FR-039a |

---

## D7 — Line ranges that must change: exact old text, exact new text

### D7.1 `data-model.md:9-11` — the level chain

**OLD (verbatim):**

```
**The seven levels are never collapsed** (I-2):
`Observation → Mention → TypeHypothesis → RelationSignal → PredicateSignature →
RelationCandidate → RelationClaimMaterial → RelationClaim → GraphEdge/HyperEdge`
```

**NEW (verbatim):**

```
**The levels are never collapsed** (I-2). `TypeHypothesis` is **not** a level: it is a nested
value object owned by a mention, in the same class as `PredicateHypothesis` (brief §103), and the
`Observation → …` chain below is the *relation* chain:

`Observation → Mention → RelationSignal → RelationCandidate → RelationClaim → GraphEdge/HyperEdge`

The entity-side chain, per brief §101/§102 and the three semantic layers, is three rungs:

`Observation → TypeSignal → TypeAssertion`

with `TypeHypothesis` as a fan-out annotation on the mention occurrence — a stage in the *pipeline*
(§10) and a value object in the *type hierarchy*, which are different questions. See
`repair/A5-type-vocabulary.md` §D1.5.
```

> Note: the arithmetic error ("seven levels" then nine entries) is **E4**, the author's to fix;
> this edit removes `TypeHypothesis` from the chain on its own merits and the count must then be
> re-derived by whoever fixes E4.

### D7.2 `data-model.md:222-242` — the whole `TypeHypothesis` + vocabulary block

**OLD (verbatim, `data-model.md:222-242`):**

````markdown
**`TypedMention`** gains real type state (FR-029…FR-032):

```python
@dataclass(frozen=True)
class TypeHypothesis:            # competing, not singular
    mention_ref: str
    hypotheses: tuple[TypeCandidate, ...]   # >= 1
    state: CandidateResolutionState          # RESOLVED | AMBOUSSED | UNRESOLVED
    vocabulary_version: str
    evidence_refs: tuple[str, ...]
```

`TypeHypothesis` today is thin (`semantic/blocking.py`) and `TypeAssertion` carries a single
hypothesis, so "Apple" cannot be three things at once (User Story 4).

**Bounded type vocabulary (NEW)** — `core:*` for entities, `value:*` for value types, versioned,
extensible by hierarchy (`core:Organization` → `industry:Bank` → `industry:CommercialBank`).
Answering **Q2**: the vocabulary is a **mapping/blocking/validation instrument, not a gate**. An
unmapped type yields `UNKNOWN` and is retained; it is never a rejection. The `relations` list on
the existing `apps/shared/events/ontology_pack.py` is inert (`allows_relation()` is never
called) and stays inert — a fixed relation list is what §104 forbids.
````

**NEW (verbatim):**

````markdown
**`TypeHypothesis` is ONE hypothesis** (FR-148), never a container. Thirteen fields, six states,
both verbatim from brief §6:

```python
class HypothesisState(StrEnum):        # the six states of §6, and no others
    UNKNOWN     = "unknown"
    OBSERVED    = "observed"
    INFERRED    = "inferred"
    MAPPED      = "mapped"
    AMBIGUOUS   = "ambiguous"
    CONFLICTING = "conflicting"

@dataclass(frozen=True)
class TypeHypothesis:                   # = interpretation candidate (§6)
    type_surface: str                   # §6: the words, verbatim
    normalized_surface: str              # §6: NFKC + casefold + whitespace fold, for matching only
    type_ref: str                       # §6: the candidate, e.g. "core:Organization"
    scheme: SemanticRef                 # §6: how to treat the ref; never what it means
    hypothesis_state: HypothesisState   # §6: one of the six above
    confidence: float = 0.0
    source_ref: str = ""                # §6: the observation this was read off
    extractor_ref: str = ""             # §6: which producer proposed it
    extractor_version: str = ""         # §6: pinned, so the proposal is re-derivable
    evidence_refs: tuple[str, ...] = () # §6
    context_ref: str = ""               # §6: the CONTEXT product consumed (§77)
    semantic_regime_ref: str = ""       # §6
    mapping_candidates: tuple[TypeMappingCandidate, ...] = ()   # §6; never collapsed, never chosen
```

It carries no `mention_ref`, no children, no `entity_ref` and no id: a hypothesis narrows a
comparison and is discarded with it. Durable typing is `TypeAssertion`, which already has the
two-level identity §10 requires ("a later `status=INFERRED` must be a new revision, not
destructive replacement… This follows the existing `TypeAssertion` two-level identity model").
`TypeHypothesis` is a nested value object in exactly the sense of brief §103's list, which names
`PredicateHypothesis`, `PredicateSignature`, `TemporalHypothesis` and `RelationParticipant` — and
not a level. A fourth epistemic level is what `data-model.md`'s earlier draft of this section
created.

**The SET of hypotheses belongs to the mention** (FR-149), per brief §7 verbatim
(`TypedMention` `+` `type_hypotheses[]`):

- `extractors/types.py::TypedMention.type_hypotheses: tuple[TypeHypothesis, ...] = ()`, with
  `kind: str` retained unchanged as a coarse producer classification (§7, FR-033).
- `semantic/resolution.py::ResolutionMention.type_hypotheses: tuple[TypeHypothesis, ...] = ()`,
  beside the `type_assertions` it already carries.

Both are frozen, de-duplicated by `(type_ref, scheme, hypothesis_state)` and ordered by
`(-confidence, type_ref, scheme, hypothesis_state)`, reusing
`semantic/blocking._ordered_hypotheses` — which the codebase already uses for exactly this policy.
No new container type is introduced; `BlockingResult.type_hypotheses` and
`BlockingOutcome.hypotheses` are the precedent, and a second container for the same facts is the
defect, not the cure.

**`TypeSignal` (NEW — the observation layer, FR-157)** sits between the mention and the
hypothesis, per §10: `Observation → Mention → TypeSignal → TypeHypothesis → SemanticRegime
interpretation → TypeAssertion`. Owned and specified by `A4b-mapping-layer.md` §D5.2 as
`semantic/type_signal.py`; it carries `source_vocab`, `surface` and `mapping_candidates`
(§9, FR-035) plus `mention_ref`, `structural_path`, `observation_refs`, `evidence_refs`,
`producer_ref` and `signal_id`, with `signal_id` derived from `(tenant_id, producer_ref,
mention_ref, source_vocab, surface, structural_path)`. It may **not** carry a `core:`/`value:`
reference: the first moment a local type may appear on this path is `TypeHypothesis`. It is the
entity-side analogue of `RelationSignal` and is **not** a `SignalKind`; §15's relation vocabulary
is untouched. Note the id asymmetry with the two neighbouring types: the signal has one id, the
hypothesis has none, the assertion has two.

**Bounded type vocabulary (NEW)** — pack identity `core-atomic-types@1` (FR-152, §63 verbatim),
31 `core:*` entity classes and 13 `value:*` value types, 44 entries, each carrying the eight §63
fields plus `namespace`, `pack_ref` and `blocking_hints` (FR-153). `kind` is a required field read
from the entry, never inferred from the prefix, because `core:Coordinate` and `value:Coordinate`
are the same label in two namespaces (FR-156, `spec.md:491` vs `spec.md:499`).

**Extensibility crosses packs** (FR-154, §5, FR-034): `type_ref == "<namespace>:<local>"`, and a
namespace other than `core`/`value` is legal with no special-casing, so `core:Organization` →
`industry:Bank` → `industry:CommercialBank` is reachable by registering `industry-types@1`. This
closes the gap where FR-029's eight fields have no namespace and FR-034 nevertheless demands a
hierarchy that leaves the pack.

Answering **Q2**: the vocabulary is a **mapping/blocking/validation instrument, not a gate**. An
unmapped type yields `UNKNOWN` and is retained; it is never a rejection. The contract, verbatim
(FR-155): **a type existing in the foundational vocabulary does not mean the system must have a
dedicated extractor for it; and the absence of a type does not mean a mention is refused.** The 44
entries are a vocabulary deliverable; the number of instruments is a separate, much smaller one
(FR-140…FR-147, eight obligations). The `relations` list on the existing
`apps/shared/events/ontology_pack.py` is inert (`allows_relation()` is never called) and stays
inert — a fixed relation list is what §104 forbids — and a named test asserts it has zero callers.
````

### D7.3 `data-model.md:297` — the §9 entity-summary row

**OLD (verbatim):**

```
| `TypeHypothesis` | EXTENDED | — | Competing hypotheses, not singular |
```

**NEW (verbatim):**

```
| `TypeHypothesis` | EXTENDED | — | ONE interpretation candidate, 13 fields, 6 states; a nested value object, not a level |
| `MentionTypeSets` (field, not a type) | — | — | `type_hypotheses: tuple[TypeHypothesis, ...]` on `TypedMention` and `ResolutionMention`; the SET lives here, not in a hypothesis |
| `TypeSignal` | NEW | — | Observation layer: `source_vocab`, `surface`, `mapping_candidates`; no commitment, never projectable |
| `TypePack` / `TypePackEntry` | NEW | `core-atomic-types@1` | 31 entity + 13 value entries; `namespace` + `pack_ref` per entry; registered through the existing `OntologyPackRegistry`; never a gate, never a completeness condition |
```

**And `data-model.md:299`, for completeness:**

**OLD (verbatim):**

```
| `TypeVocabulary` (`core:*`/`value:*`) | NEW | — | Versioned, bounded, never a gate |
```

**NEW (verbatim):**

```
| `TypeVocabulary` (`core:*`/`value:*`/`industry:*`) | NEW | — | Renamed to `TypePack`; `core:*`/`value:*` are two namespaces of a space that is open in both directions, so the namespace is a field and not a closed set. Versioned, bounded **as a pack**, never a gate and never a completeness condition over the world |
```

### D7.4 `spec.md:501-506` — FR-032

**OLD (verbatim):**

```markdown
- **FR-032**: `TypeHypothesis` MUST be a first-class type carrying at least `type_surface`,
  `normalized_surface`, `type_ref`, `scheme`, `hypothesis_state`, `confidence`, `source_ref`,
  `extractor_ref`, `extractor_version`, `evidence_refs`, `context_ref`, `semantic_regime_ref`
  and `mapping_candidates`, with states `UNKNOWN`, `OBSERVED`, `INFERRED`, `MAPPED`,
  `AMBIGUOUS`, `CONFLICTING`. It MUST be distinguishable from `TypeAssertion`, which is
  evidence-bearing. (§6)
```

**NEW (verbatim)** — note "at least" is tightened to "exactly", because the brief's list is a
required set and the tightening is what makes FR-148's field test possible:

```markdown
- **FR-032**: `TypeHypothesis` MUST be a first-class type carrying **exactly** the thirteen
  fields `type_surface`, `normalized_surface`, `type_ref`, `scheme`, `hypothesis_state`,
  `confidence`, `source_ref`, `extractor_ref`, `extractor_version`, `evidence_refs`,
  `context_ref`, `semantic_regime_ref` and `mapping_candidates`, and no others, with
  `hypothesis_state` taking **exactly** the six values `UNKNOWN`, `OBSERVED`, `INFERRED`,
  `MAPPED`, `AMBIGUOUS`, `CONFLICTING`. It is **one** interpretation candidate and MUST NOT be a
  container of candidates (FR-148). It MUST be distinguishable from `TypeAssertion`, which is
  evidence-bearing and id-bearing. (§6)
```

### D7.5 `spec.md:488-495` — FR-030, and the A5-9 correction

**OLD (verbatim):**

```markdown
- **FR-030**: The pack MUST cover, at minimum, entity classes `core:Person`,
  `core:Organization`, `core:LegalEntity`, `core:Group`, `core:Agent`, `core:WebSite`,
  `core:WebPage`, `core:OnlineAccount`, `core:SocialProfile`, `core:Domain`,
  `core:DigitalResource`, `core:PhysicalPlace`, `core:Facility`, `core:Address`,
  `core:GeographicRegion`, `core:Country`, `core:StateOrProvince`, `core:City`,
  `core:Coordinate`, `core:Document`, `core:Dataset`, `core:CreativeWork`,
  `core:MediaResource`, `core:Software`, `core:Project`, `core:Product`, `core:Service`,
  `core:Asset`, `core:Vehicle`, `core:FinancialInstrument`, `core:Event`. (§4)
```

**NEW (verbatim)** — the count is stated because it is now testable, and it is **31**, not 32:

```markdown
- **FR-030**: The pack MUST cover, at minimum, the following **31** entity classes:
  `core:Person`,
  `core:Organization`, `core:LegalEntity`, `core:Group`, `core:Agent`, `core:WebSite`,
  `core:WebPage`, `core:OnlineAccount`, `core:SocialProfile`, `core:Domain`,
  `core:DigitalResource`, `core:PhysicalPlace`, `core:Facility`, `core:Address`,
  `core:GeographicRegion`, `core:Country`, `core:StateOrProvince`, `core:City`,
  `core:Coordinate`, `core:Document`, `core:Dataset`, `core:CreativeWork`,
  `core:MediaResource`, `core:Software`, `core:Project`, `core:Product`, `core:Service`,
  `core:Asset`, `core:Vehicle`, `core:FinancialInstrument`, `core:Event`. (§4)
  This is a **fixture requirement on the pack's contents** and MUST NOT be read as a producer
  obligation: a type's presence here does not oblige the system to have a dedicated extractor for
  it (FR-155). `core:Coordinate` is an **entity** here; `value:Coordinate` in FR-031 is a
  **value** with the same local name, and the two are distinct references distinguished by
  `kind` (FR-153, FR-156).
```

**Also correct, in `phase0-results.md` §4.1 D7** (not a spec edit — a review-prose correction, and
it is load-bearing because the whole "32 extractors" reading rests on it):

**OLD (verbatim):**

> **§8 (entity extractor expansion, 170 lines, 7 mandatory sub-sections) is dropped entirely** | `Cyrillic`, `github.com`, `CVE`, `persons.py` appear zero times in every artefact. Yet FR-030 mandates 32 type classes with no producer obligation

**NEW (verbatim):**

> **§8 (entity extractor expansion, 170 lines, 7 mandatory sub-sections) is dropped entirely** | `Cyrillic`, `github.com`, `CVE`, `persons.py` appear zero times in every artefact. FR-030 enumerates **31** entity classes and nowhere states a count of 32 — the 32 is this review's own miscount — and it mandates **no** producer obligation in any case, which is the real defect: §8's seven sub-sections are the producer obligations and none of them exists. Repaired by `repair/A5-type-vocabulary.md` (FR-140…FR-147, SC-026).

### D7.6 `spec.md:510-513` — FR-034, and `spec.md:484-487` — FR-029

**OLD (verbatim, FR-029):**

```markdown
- **FR-029**: A versioned foundational type pack MUST exist, exposing per type: `type_ref`,
  `label`, `alt_labels`, `broader_refs`, `narrower_refs`, `description`, `kind ∈ {entity,
  value}` and `version`. It MUST NOT encode relation semantics and MUST NOT encode truth; it
  MAY carry blocking hints. (§4, §63)
```

**NEW (verbatim):**

```markdown
- **FR-029**: A versioned foundational type pack MUST exist with the identity
  `core-atomic-types@1` (FR-152, §63), exposing per type: `type_ref`, `label`, `alt_labels`,
  `broader_refs`, `narrower_refs`, `description`, `kind ∈ {entity, value}` and `version`, plus
  `namespace`, `pack_ref` and `blocking_hints`. `kind` MUST be read from the entry and MUST NOT be
  inferred from the `type_ref` prefix. It MUST NOT encode relation semantics and MUST NOT encode
  truth; it MAY carry blocking hints, and no hint may express a denial. (§4, §63, FR-153)
```

**OLD (verbatim, FR-034):**

```markdown
- **FR-034**: The type space MUST be extensible by hierarchy (`core:Organization` →
  `industry:Bank` → `industry:CommercialBank`), and `broader`/`narrower` relations MUST be
  usable for query expansion, blocking, ranking, validation and role matching — never as an
  extraction gate. Unknown remains unknown. (§5)
```

**NEW (verbatim):**

```markdown
- **FR-034**: The type space MUST be extensible by hierarchy **across packs** — each entry
  carries a `namespace` and `type_ref == "<namespace>:<local_name>"`, so registering
  `industry-types@1` is sufficient to make `core:Organization` → `industry:Bank` →
  `industry:CommercialBank` reachable, with no namespace special-cased in code (FR-154) — and
  `broader`/`narrower` relations MUST be usable for query expansion, blocking, ranking,
  validation and role matching — never as an extraction gate. Unknown remains unknown. (§5,
  FR-154)
```

### D7.7 Where this does **not** edit, and why

| File / line | Why not mine |
|---|---|
| `spec.md:507-509` (FR-033) | Substantively correct — "A mention MUST be able to hold several competing `TypeHypothesis` values" is exactly D1.4's container. It needs a cross-reference to FR-149, which the repairer may add as a pure citation edit. |
| `spec.md:521-523` (FR-035) | Substantively correct and I adopt it as the `TypeSignal` field list. The `TypeSignal` *type* is mine (FR-157); the mapping *record* is A4b's. |
| `spec.md:528-530` (FR-037) | Correct as written; restated as FR-158 with a test, not amended. |
| `spec.md:534-537` (FR-039), `539-541` (FR-039a) | Correct as written; restated as FR-159/FR-160 with tests, plus FR-159's boundedness clause. |
| `spec.md:514-517` (FR-011) | Relation `SignalKind`. The type layer adds no `SignalKind` member (FR-157). |
| `spec.md:545-548` (FR-040) | Relation producer families. The §8 entity instruments are separate obligations (FR-141…FR-147) and FR-040's "not 500 extractors" is the same principle as FR-155. |
| `spec.md:359-366` (INV-001, INV-002) | Both correct. INV-002 is the clause FR-156 reconciles FR-030 with. |
| `apps/shared/events/ontology_pack.py:36-46` | The `relations` list and `allows_relation()` stay exactly as they are — inert. FR-155 only adds a test asserting the inertness. |
| `apps/shared/semantic/mappings.py` | A4b's file. I do not touch it. |
| `db/schema.py:70-75` | Unchanged. `CandidateResolutionState` keeps its five members and its ORM home; FR-151 forbids importing it into `shared`. |

---

## D7.8 Review findings closed by this job

| Finding | Status | How |
|---|---|---|
| **D7** — §8 dropped entirely, 170 lines, 7 sub-sections | **CLOSED** | FR-140…FR-147, one per sub-section, each quoted, each with a named test; SC-026 as the measurable wrapper; the four "32"-misquote corrections |
| **D8** — all 9 entity-substrate §108 bullets have no SC | **CLOSED for the 9** | SC-017…SC-025, verbatim bullet-for-bullet, each measurable. Lifecycle (5) and Boundedness (4) ruled **not mine** in D5.1, with FR-159 taking one boundedness obligation |
| **E3** — `data-model.md` §6 / T017 redefines `TypeHypothesis` as a container of `TypeCandidate`s | **CLOSED** | D1.1 replacement, FR-148/FR-149/FR-150, diffs D7.2 and D7.3, plus D1.5's three-argument proof that the set is not a level |
| **D1** (partial) — 52 of 102 FRs unowned | **PARTIAL, 21 FRs owned** | FR-140…FR-160, each with a test name and a brief-§ cross-reference in D6.5. The remaining orphans are other jobs' |
| **A5-9** (new) — FR-030's "32" is unsourced and its enumeration is 31 | **CLOSED** | D7.5 states 31 in the FR and corrects the review prose |
| **A5-10** (new) — `core:Coordinate` vs `value:Coordinate` | **RESOLVED** | D3.4: both stay, `kind` is the discriminator, `kind` becomes a required non-defaulted field |
| A5-11 (new) — no `TypeSignal` type exists | **CLOSED** | FR-157, D2.1/D2.2, diff D7.2; shape conformed to A4b §D5.2 |
| **A5-1/A5-2** (new) — `CandidateResolutionState` is a control-plane ORM enum with different members; `AMBOUSSED` is a misspelling | **CLOSED** | FR-150, FR-151, D1.1 table |
| **K1** (partial) — `plan.md`'s Constitution Check omits 5 of 7 principles | **NOT MINE** | Constitutional/plan gate. This job supplies the INV-002 and §104 evidence it needs; it does not audit the check |

### D7.9 Open questions and stop conditions

Verbatim from `input.md:4668-4692` (§111) — the four that are mine:

```text
a new ontology requirement
an external vocabulary mapping ambiguity
an entity/value ambiguity
a persistence representation that loses information
```

| ID | Open question | Stop condition |
|---|---|---|
| **OQ-A5-1** | Is `core:Coordinate` intended, or a brief typo for `core:GeographicRegion`? (§4.1 lists `Coordinate` in *both* "Place / geography" and "Values"; FR-030 and FR-031 therefore contradict each other) | **Stop and report.** Ship both entries as D3.4 decides, record `UNKNOWN` in the ADR. Do **not** delete a vocabulary entry on a guess — a deletion is a silent narrowing and is the one thing INV-002 forbids. (`input.md:4673` "a new ontology requirement") |
| **OQ-A5-2** | Should `value:CVE`, `value:FilePath`, `value:DomainName` be added as first-class `value:*` entries, or is `value:Identifier` + a named `extraction_rule_id` sufficient? | Default to the second (no new vocabulary) per FR-145. If a consumer cannot discriminate the specific form from the record, that is a **new ontology requirement**: stop, report, and propose `core-atomic-types@2` with the added entries — a new version, never an edit of `@1` (FR-152). |
| **OQ-A5-3** | Does §8 C's "`www.example.com` is a `core:Domain`" conflict with a public-suffix view in which `www` *is* registrable for some TLDs? | §8 C is explicit and the FR-143 table is written to the brief. If a corpus row proves the registrable-domain reading wrong, record `www` as a hint either way (FR-143 already requires that) and stop before adding a public-suffix list — a new dependency in the constitutional extraction path is `input.md:240`'s "Do not import a giant external ontology into the core execution path" in miniature. |
| **OQ-A5-4** | ~~Is `TypeHypothesis.mapping_candidates` `tuple[SemanticMapping, …]` or `tuple[str, …]` of mapping ids?~~ **RESOLVED by A4b §D5.2:** both are `tuple[TypeMappingCandidate, …]`. A5 conformed. | Closed. Retained here so the withdrawal is on the record. |
| **OQ-A5-6** (new, from reading A4b) | `TypeSignal` has `producer_ref` but **no producer version**, and `source_vocab` documents only six *external* vocabularies — so four of §8's six families (surface, document, regex, NER) have no legal `source_vocab` value. | **Stop and coordinate with A4b (D2.4 asks 3 and 4).** Do not add a field to A4b's type, and do not invent a `local:` sentinel unilaterally. If A4b does not answer, `source_vocab=""` (already the default) is the documented value and the gap is reported as a known limitation, per `spec.md:934-936`. A version-less producer makes FR-140's re-derivability claim unverifiable, so this must be closed before SC-026 is claimed. |
| **OQ-A5-5** | Does `ResolutionMention` or `TypedMention` own the set in the *durable* path, given `data-model.md` §6's `MentionIndex` mints `MN-…` ids and no durable mention record exists at HEAD? | The durable container is deferred to the persistence agent; FR-149 specifies the two carriers that exist. If a third carrier becomes necessary, it MUST be a field on a mention and MUST NOT be a new type (D1.5, argument 3: a type with no identity is not a level). A persistence representation that loses information is a stop condition (`input.md:4678`). |

**And the standing rule, verbatim (`input.md:4692`):**

> Do not turn uncertainty into a guessed type/relation merely to make the pipeline green.

**One reporting obligation this job inherits** (`input.md:4345-4351`, §107, verbatim):

> Never report:
>
> ```text
> green
> ```
>
> when there are new failures hidden among known ones.

So: SC-020 is `verified only offline` until the persistence columns land; SC-024's proof that the
pack is unreachable from every extraction path is a **source-scan** result and must be reported as
such, not as a runtime proof; and SC-019's import test is likewise static. The baseline is
`16 failing tests, of which 3 are environment-caused; 22 additional tests never executed`
(`phase0-results.md` §1.2) and re-baseline before trusting any comparison.
