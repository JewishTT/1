# Requirements checklist: 021-entity-relation-extraction-finalization

**Gate**: every item must be `verified` or explicitly `verified only offline` / `known
limitation` / `deferred` before the feature is called complete. A tick means *checked against
the code or a test*, never "read and believed".

**Verification key**: `T` = automated test, `I` = inspection of the actual file, `M` = mutation
must fail, `B` = baseline comparison, `P` = production-path proof.

**Hard rule**: the 16 known baseline failures (2 control-plane `test_donor_api`, 14 shared) are
not to be fixed, hidden, or counted as progress (FR-081).

---

## A. Constitutional invariants

| # | Item | Method | Task | State |
|---|---|---|---|---|
| A1 | The seven levels stay distinct; `CandidateStatus` never becomes a `rank()` | T | T005, T029 | ☐ |
| A2 | Unknown is a retained state, never a drop | T | T025, T028, T032 | ☐ |
| A3 | `GraphEdge`/`HyperEdge` derivable only from admitted claims — enforced at the type level | T | T011a | ☐ |
| A4 | Determinism: ids re-derived, never trusted; no dependence on dict iteration order | T | T005, T029 | ☐ |
| A5 | Tenancy: no cross-tenant write or read | T | existing suites | ☐ |
| A6 | Graph is a projection and is rebuildable from the stores | T | T011c | ☐ |
| A7 | No `ENT-`/`RES-` literal in producer code; no `TYPE_CHECKING` outside type positions | I | T007f | ☐ |

## B. Identity and the signature (the constitutional heart)

| # | Item | Method | Task | State |
|---|---|---|---|---|
| B1 | `logical_candidate_id` is keyed on the **signature**, not the raw surface | T | T006, T029 | ☐ |
| B2 | Active and passive realisations share one `logical_candidate_id`, two revisions | T | T006, T029 | ☐ |
| B3 | Case/whitespace variants share one logical id | T | T029 | ☐ |
| B4 | A surface change creates a `candidate_id` revision without changing the logical id | T | T030 | ☐ |
| B5 | `signal_refs` canonicalised on construction; order-independent `candidate_id` | T | T005 | ☐ |
| B6 | `to_dict`/`from_dict` round-trip every field losslessly | T | T007 | ☐ |
| B7 | `RelationClaim` re-derives and checks its own carried `relation_id` | T | T009 | ☐ |
| B8 | §90 unknown case end to end: signal → candidate → surface → normalised → signature → `UNKNOWN` → no claim → no edge, evidence retrievable | T | T032 | ☐ |
| B9 | N5 synonym table is versioned, sourced, provenance-carrying; unjustified entries dropped | I | T015 | ☐ |

## C. `RelationSignal` structure

| # | Item | Method | Task | State |
|---|---|---|---|---|
| C1 | Natively n-ary; the two hard-coded scalars are gone | T | T022 | ☐ |
| C2 | `SignalKind` carries observation channels only; no `NEGATION`/`QUANTITY`/`COREFERENCE`; no `TEMPORAL` added | I | T023 | ☐ |
| C3 | Polarity is a real field; a denial is evidence, not a drop | T | T024 | ☐ |
| C4 | A `CO_OCCURRENCE` signal may have an empty surface and a `None` signature | T | T025 | ☐ |
| C5 | `_material()` includes signature, polarity, arity, roles; `producer_ref` retained | T | T026 | ☐ |
| C6 | Two signals differing only in arity do not collapse to one `signal_id` | T | T027 | ☐ |
| C7 | The three wrong `signal_id` docstrings are corrected | I | T026 | ☐ |

## D. Producers and mention binding

| # | Item | Method | Task | State |
|---|---|---|---|---|
| D1 | Zero synthetic `*_mention_ref` values in production producer code | I | T007f | ☐ |
| D2 | Every `participant.mention_ref` resolves in the mention index | T | T020, T007f | ☐ |
| D3 | §96 mutation (a synthetic `surface:person:john`) **fails** the contract | M | T012d | ☐ |
| D4 | No property name, field name, document placeholder or truncated string as a participant | I | T007c | ☐ |
| D5 | `document:current` fallback removed; required `document_ref` | I | T007c | ☐ |
| D6 | `pairs_considered` is a real count or a stated `0`; `max_pairs_considered` is live | T | T033, T036 | ☐ |
| D7 | `zip(..., strict=False)` is strict; a dropped `<dt>`/row is reported, not silent | T | T034 | ☐ |
| D8 | A heuristic scan is not published as `precision="exact"` | I | T034 | ☐ |
| D9 | §99 mutation (a producer importing/constructing `GraphEdge`) **fails** | M | T012d | ☐ |

## E. Assembly

| # | Item | Method | Task | State |
|---|---|---|---|---|
| E1 | `_arity_of` majority vote and alphabetical tie-break deleted; `-> RelationArityMode` | I | T039 | ☐ |
| E2 | §95 mutation (majority-vote arity/direction) **fails** | M | T012d | ☐ |
| E3 | A conflicting reading yields `CONTRADICTED` with both readings preserved, and is reported | T | T040 | ☐ |
| E4 | A declared NARY schema is never downgraded to DIRECTED; roles never lost with a vote | T | T040 | ☐ |
| E5 | Equal endpoints do not merge | T | T041 | ☐ |
| E6 | §43/§44: one logical candidate carrying many signals; a different reading a different one | T | T043 | ☐ |
| E7 | Exactly one code path from signal to candidate (the dead `to_candidate()` bypass removed) | I | T042 | ☐ |

## F. Types

| # | Item | Method | Task | State |
|---|---|---|---|---|
| F1 | `TypeHypothesis` carries competing hypotheses with state, vocabulary version, evidence | T | T017 | ☐ |
| F2 | "Apple" retains ≥3 hypotheses and selects none | T | T017 | ☐ |
| F3 | §97 mutation (`if core pack does not know type: continue`) **fails** | M | T012d | ☐ |
| F4 | An ontology match never becomes automatic truth | T | T018 | ☐ |
| F5 | Bounded versioned `core:*`/`value:*` vocabulary with hierarchy | T | T016 | ☐ |
| F6 | The vocabulary is a mapping/blocking/validation instrument, never an extraction gate | T | T016 | ☐ |
| F7 | `OntologyPack.relations` stays inert; `allows_relation()` is never used as a requirement | I | T016 | ☐ |

## G. Lifecycle

| # | Item | Method | Task | State |
|---|---|---|---|---|
| G1 | Materialisation, validation, admission, projection separately observable | T | T044 | ☐ |
| G2 | The `ValidationReport` that gated admission is retained and surfaced | T | T044 | ☐ |
| G3 | No post-admission re-validation, or it is justified in writing | I | T045 | ☐ |
| G4 | The admission decision actually gates the store write | T | T046 | ☐ |
| G5 | Production writes are not doubled to demonstrate idempotency | I | T047 | ☐ |
| G6 | `ExecutionRequest.producers` is populated | I | T050 | ☐ |

## H. Persistence

| # | Item | Method | Task | State |
|---|---|---|---|---|
| H1 | Migration `021` added on top of the forward-only `020`; `020` unedited | I | T051 | ☐ |
| H2 | `predicate_signature` columns on `relation_signal` and `relation_candidate` | I | T051 | ☐ |
| H3 | `signal_refs`, `direction`, `polarity`, `confidence` on `relation_candidate` | I | T052 | ☐ |
| H4 | `candidate_id` on `relation_claim`, written and read by the store | I | T052 | ☐ |
| H5 | `alternative_refs` and `mapping_evidence_refs` have real columns | I | T053 | ☐ |
| H6 | A repository/writer/reader exists for all three 020 tables | I | T054 | ☐ |
| H7 | ORM/migration parity test-enforced for `021` | T | T051 | ☐ |
| H8 | `capture_with_observations()` reachable from the normal acquisition path | T | T056 | ☐ |
| H9 | Build → store → read test asserts the full field list per type | T | T057 | ☐ |
| H10 | DB verification honestly labelled `verified only offline` while live PostgreSQL is unreachable | I | T057 | ☐ |
| H11 | §98 mutation (`if relation_ref is None: return ()`) **fails** | M | T012d | ☐ |

## I. Projection

| # | Item | Method | Task | State |
|---|---|---|---|---|
| I1 | `GraphProjectionBridge` accepts only a `RelationClaim`; a test tries and fails | T | T058 | ☐ |
| I2 | `direction` and `polarity` present in properties | T | T059 | ☐ |
| I3 | Edge metadata is not edge identity | T | T059, T062 | ☐ |
| I4 | Rebuild proven: write → project → rebuild → compare | T | T060 | ☐ |
| I5 | §78–§81 projection tests pass; unknown stays unknown in the graph | T | T062 | ☐ |

## J. Corpus, mutations, regression, wiring

| # | Item | Method | Task | State |
|---|---|---|---|---|
| J1 | 6 end-to-end HTML cases of §70 in the golden corpus | T | T063 | ☐ |
| J2 | §83 relation cases and §82 type cases in the golden corpus | T | T063, T064 | ☐ |
| J3 | Replay determinism: same ids in a second process | T | T065 | ☐ |
| J4 | 17 mutations from §94–§101 all fail for the right reason | M | T066 | ☐ |
| J5 | Boundedness/coverage report per §106 | I | T067 | ☐ |
| J6 | **P** — live `POST /api/v1/entities` produces signals → candidates → claims → edges with real mention ids | P | T068 | ☐ |
| J7 | **P** — `lexical_signals` demonstrably runs | P | T069 | ☐ |
| J8 | Full T001 baseline re-run; no suite exceeds its Phase 0 failure count | B | T070 | ☐ |
| J9 | Every failure classified baseline / new / fixed / flaky | I | T070 | ☐ |
| J10 | No O(N²) mention sweep; locality-window cost benchmarked | T | T071 | ☐ |
| J11 | `ruff check` clean on all changed paths | I | T072 | ☐ |
| J12 | `contracts/`, ADRs A–K, `quickstart.md` written | I | T073 | ☐ |
| J13 | Completion report distinguishes implemented / verified / verified only offline / known limitation / deferred | I | T074 | ☐ |
| J14 | §101 architecture present in **production** code, not only in the corpus harness | P | T074 | ☐ |

---

## Sign-off conditions

The feature is complete only when **J14 and J13** both hold. Specifically:

1. No item above is `☐`.
2. The §108 proof is tests, not prose.
3. Live PostgreSQL remains unreachable → H9/H10 stay `verified only offline`, and J13 says so.
4. Any stop condition triggered (FR-082) is listed in J13 as `deferred` with its reason —
   never silently resolved by widening the vocabulary or casting a guess as a type.
5. The 16 baseline failures are unchanged and individually accounted for in J9.
