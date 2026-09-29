# A6 — FR Triage for feature 021

**Job**: spec-repair **A6 — FR TRIAGE**. Analysis and decision-table work. No existing file was
modified. This file is the only artefact written.

**Scope of this job**: the FR **set** only. Identity derivation, the field lists of the domain
types, the mapping model and the type-pack shape are owned by other repair agents and are **not**
redesigned here. Where this document must state something about those, it states the *constraint
the set must leave room for* and marks the row `CLAIMED BY AGENT`.

**Sources read in full**: `spec.md` (936 lines, 102 FR / 16 SC / 5 INV), `tasks.md` (281 lines,
T001–T074), `checklists/requirements.md` (158 lines, 82 items), `phase0-results.md` §4.1 D1–D16 and
§4.3 K6, `input.md` (4898 lines, §0–§114), `plan.md`, `research.md`, `data-model.md`. All counts
below were re-measured from the files, not inherited.

---

## 0. Premises checked. Four of the given numbers are wrong.

I agree with the substance of every defect listed. Four of the **magnitudes** are not reproducible
from the files, and two premises are attributed to the wrong task.

| Given premise | Measured | Verdict |
|---|---|---|
| 52 FRs have no task and no checklist item | **52** — exact match, reproduced by set difference | **confirmed** |
| 18 of 50 FR citations in `tasks.md` point at an unrelated FR | `tasks.md` holds **69 FR citation tokens across 51 task lines** (66 real + 3 phantom). **19** point at an unrelated or non-governing FR (18 hard + 1 weak) | **direction confirmed, magnitudes wrong** — "50" is not reproducible; the list omits nothing but `T015` is weak, not an error |
| `FR-103` cited by 4 artefacts, does not exist | cited by **3 task lines** (`T019`, `T020`, `T038`), plus `research.md` ×2 and `data-model.md` ×2 = **7 places** | **confirmed, understated** |
| 29 of §108's 47 acceptance bullets have no SC | §108 has **48** bullets, not 47. **16** are covered by an existing SC; **32** are not | **32, not 29** — D8 omitted the 4 determinism bullets and miscounted by one |
| `SC-015` demands ≥ 20 invariants; FR-078 enumerates 18; §93 lists 18 | `input.md` §93 = 6 entity + 8 relation + 4 projection = **18**; FR-078's enumeration matches §93 exactly | **confirmed** |
| checklist claims "17 mutations from §94–§101" | §94–§99 = **6**; §100 is spec/ADR deliverables; §101 is the domain model. `T066` cites `§94, §101, §94…§99` — §101 is cited **as a mutation source** | **confirmed; worse than stated** |
| `FR-079` says "Four" and lists six | verbatim: `Four named mutations MUST exist` followed by six semicolon-separated mutations | **confirmed** |
| `SC-001` is unachievable by any task | confirmed — and the gap is **two** obligations, not one (§1.2) | **confirmed, under-specified** |
| `T022` "violates FR-011" | false. `T022` (the `participants` tuple) never touches `SignalKind`. The FR-011 violation is **`T023`**, which forbids the `TEMPORAL` member *while citing FR-011* | **corrected: this is D14, and it belongs to T023** |
| `T019/T020 → FR-016/FR-018` | correct, but the two tasks split differently: `T019` (build the index) is FR-**018**; `T020` (inject the resolver) is FR-**016** + FR-017 + FR-019 | **confirmed, refined** |
| T4 asks for "the user's 10-phase structure" | `input.md` §110 states **12** phases; `tasks.md` has **13** (it adds a blocking Phase 0). "10" is a third count | **corrected in §5.1** |
| D16: "T022 breaks 7 construction sites, T023 breaks 12 enum references" | 7 `RelationSignal(` sites in non-test code — **confirmed**. The enum break is **9 lines in 5 files** for `NEGATION`/`QUANTITY`/`COREFERENCE`/`SCHEMA`, of which only **2 lines** reference members actually being removed (`assembly.py:219`, `signal.py:394`); `QUANTITY` and `COREFERENCE` have **zero** references outside the enum definition. Total `SignalKind.*` references in non-test code: **35** | **7 confirmed; "12 enum references" is wrong in both directions — the real figure is 2 breaking lines, which makes Phase 4 committable green** |
| `T001↔T004`, `T048↔T044-047`, `T012↔T013`, `T033-T037`, `T065`, `T067`, `T072` share files | `T001↔T004` **real** (both write `checklists/requirements.md`). `T048↔T044-047` **real** (all edit `execution.py`). `T033-T037` **wrong as stated** — they are different files; the real collision is that `tables.py` holds **both** `TableExtractor` and `ListExtractor`. `T012↔T013` **soft** (same directory, different new modules; the real defect is the package `__init__` surface). `T065/T067/T072` **weak** | **corrected in §5.3(d)** |

**Two further defects the instruction did not list**, found while measuring:

- **`T071` cites `FR-047`.** `FR-047` exists and means *"The table producer MUST preserve
  `table_ref`, `row_ref`, …"*. `T071` is a benchmark task and means brief `§47` (COST MODEL).
  This is the **second instance of the `FR-103` class** — a brief section number presented as an
  FR id — and it survived review because `FR-047` happens to exist. It is a *type* error, not a
  typo, and `CHK-TY-01` (§6) exists solely to catch it.
- **23 tasks carry no FR citation at all**, and several carry real obligations: T004 → FR-083,
  T010 → an identity obligation no FR governs, T054/T055 → FR-059, T058 → `INV-004`/FR-058,
  T060/T062 → FR-068, T063 → FR-076, T064 → FR-075, T065 → FR-073, T066 → FR-078, T067 → FR-072,
  T073 → FR-083. **The converse direction fails on 23 tasks just as the normative direction
  fails on 52 FRs**, and the original report only counted one of the two directions.

---

## 1. T1 — The triage table

### 1.1 Verdict legend

| Verdict | Meaning | Effect on the normative set |
|---|---|---|
| `KEEP` | Normative as written. | Survives with its number. |
| `KEEP ▸ merge target` | Normative, and absorbs a deleted FR. | Survives; the absorbed FR is deleted. |
| `MERGE` | Deleted as a standalone requirement; its text is absorbed. | Deleted. The absorbing slot is named. |
| `REWRITE` | Normative in intent, defective as written; replacement text supplied in §2.4. | Survives with a rewritten body. |
| `REMOVE` | Not an obligation. Moved to an ADR or a design note. | Deleted. |
| `CLAIMED BY AGENT` | Owned by another repair agent. Not re-decided here; only the constraint it must satisfy is stated. | Unchanged pending that agent. |

Checklist ids use a **new** space: `R-0nn` = one primary item per surviving FR, in FR order;
`R-1nn` = a second, independently-failing check for an FR that needs two. The legacy `A1…J14` ids
are retained as a cross-reference column in the rebuilt checklist, not deleted.

### 1.2 The two obligations that make `SC-001` reachable

`SC-001` ("one `logical_candidate_id`" from two realisations) fails because **two** things are
specified nowhere, not one:

1. **Canonical participant ordering.** `FR-002` says logical identity "MUST depend on participant
   configuration", but no FR says participants are *canonically ordered* before they enter
   identity material. `data-model.md` §3 does say it — and `data-model.md` is not normative.
   → folded into the **FR-002 rewrite** (§2.4), with owner task `T131`.
2. **Voice normalisation of role bindings.** `FR-003` lists "voice normalization" as a
   `PredicateSignature` component, so it *is* specified — but FR-003 is `CLAIMED BY AGENT`. The
   constraint I impose from this side: whatever A2/A4b write for FR-003 **must** make
   `role_bindings` part of the signature's identity contribution and must be reachable from
   `"Acme was acquired by John"` **without** ontology mapping. If it is not, `SC-001` stays
   unreachable and the `FR-002` rewrite alone will not save it. This is a blocking interface, not
   a re-decision.

Neither FR-003 nor FR-004 is marked "KEEP without task". Both are `CLAIMED` and both have an
owner task **reserved** below (`T130`) — reserved so the DAG and the checker stay closed, not
authored by this job.

### 1.3 The 102 rows

| id | one-line requirement | verdict | target task (new) | acceptance test | checklist | rationale |
|---|---|---|---|---|---|---|
| FR-001 | `logical_candidate_id` MUST NOT depend on surface, producer, capture, confidence, status, observation refs or any observation timestamp | KEEP | T133 (+T110 red) | `test_logical_id_independent_of_revision_material` | R-001 | Core negative obligation; no conflict found; the only defect is that it is untested |
| FR-002 | Logical identity MUST depend on tenant, participant config, arity, role shape, direction, polarity, signature | **REWRITE** | T131 | `test_active_passive_share_one_logical_id` | R-001a, R-002 | States the *dependency* but never the *canonicalisation*; half of D6 |
| FR-003 | Deterministic `PredicateSignature` with ≥9 named components; not a `RelationRef`, not an ontology concept | CLAIMED (A2/A4b) | T130 *(reserved)* | `test_signature_components_and_no_ref` | R-003 | Must absorb canonical ordering + a sourced synonym table; §1.2 |
| FR-004 | Normalisation deterministic; MUST NOT unify distinct relations; surface variation must not force inequality | CLAIMED (A2/A4b) | T130 *(reserved)* | `test_owns_controls_manages_remain_distinct` | R-004 | E1: `data-model.md` N5 asserts `owns ≡ controls` as the worked example |
| FR-005 | A surface-variant pair MUST derive the same signature **through the derivation**, never a fixture | KEEP | T133 | `test_derivation_not_fixture` | R-005 | Correct; old T029 cites it correctly |
| FR-006 | `signal_id` stays producer-specific; independence over `producer_ref`/`independence_family` | KEEP | T152 | `test_independence_over_producer_family` | R-006 | Correct; the one-anchor double count is FR-045's defect, not this FR's |
| FR-007 | Candidate partition stays two-level (`CAND-`/`CNDR-`); no fourth epistemic level | KEEP | T134 | `test_no_fourth_epistemic_level` | R-007 | FR-007's `§103` is a **brief-section** citation and is legal; unrelated to the phantom `FR-103` |
| FR-008 | `participants: tuple[RelationParticipant, …]` canonical, 2..N, no fake binary decomposition | KEEP | T123 | `test_signal_is_variadic_nary` | R-008 | Old T022 cited FR-012/FR-013 instead |
| FR-009 | `RelationParticipant` carries `mention_ref`, `slot`, `role_hypothesis`, `ordinal`, `confidence` | KEEP | T123 | `test_participant_field_set` | R-009 | **Three** field lists exist: FR-009, old T013, `data-model.md` §2. The types agent owns the union |
| FR-010 | Signal contract must support 13 named dimensions; load-bearing dimensions typed, not JSONB | KEEP | T123 | `test_required_dimensions_are_typed` | R-010 | The `extra` exclusion defect belongs to FR-089; do not merge |
| FR-011 | `SignalKind` MUST contain ≥13 named members **including `TEMPORAL`** | **REWRITE** | T125, T128 | `test_signal_kind_is_channel_not_aspect` | R-011 | Mandates `TEMPORAL`, which `T023` forbids while citing this FR — D14. MUST-list + MAY-list is also not a partition |
| FR-012 | `NEGATION`/`TEMPORAL`/`QUANTITY`/`COREFERENCE`/`UNCERTAINTY` **SHOULD** move to a `SignalAspect`; "make the smallest coherent change" | **REWRITE** | T125 | `test_aspect_split_is_exhaustive` | R-012 | `SHOULD` + "smallest coherent change" is untestable and under-specified against FR-011/FR-040 |
| FR-013 | A signal MUST NOT require non-empty `relation_surface`; empty-surface co-occurrence representable | **REWRITE** | T129 + T165 | `test_cooccurrence_empty_surface_constructs_persists_assembles` | R-013a, R-013b | E6: names the **string error code** `signal_asserts_nothing` as if it were a function. K6: no artefact schedules dropping the two CHECKs, so `SC-012` is unachievable |
| FR-014 | Observational basis MUST be one of 9 named bases | **REWRITE** | T126 | `test_observational_basis_is_required_and_typed` | R-014 | No FR requires the field to *exist* or be set; the enumeration is currently decorative |
| FR-015 | `polarity` explicit on every signal, `ASSERTED`/`DENIED`; a denial is evidence | **REWRITE** | T124 + T166 | `test_denial_yields_denied_candidate_and_no_positive` | R-015a, R-015b | Two-valued here, three-valued in `T012`/`data-model.md` §5, and **not a column on any table** |
| FR-016 | No producer may invent a mention identity; every `participant.mention_ref` resolves | KEEP | T119 | `test_every_participant_ref_resolves` | R-016 | 12 fabrication prefixes measured and enumerated in §5.4 |
| FR-017 | A non-mention value yields the structural raw slot + a typed **deferred** reference, never a synthesised id | KEEP | T119 | `test_deferred_participant_reference` | R-017 | No task and no checklist item today |
| FR-018 | `MentionOccurrenceIndex` with deterministic lookup on capture, segment, offset/span, normalized surface, extractor occurrence | **REWRITE** | T118 | `test_index_lookup_keys_are_unique_per_capture` | R-018a, R-018b | E11: old T019 omitted `capture`, so two captures of one segment collide. Prefix conflict (`MENTION-` vs `MN-`) is the identity owner's call |
| FR-019 | Mention binding stays distinct from entity resolution; no `ENT-`/`RES-` literals | KEEP | T152 | `test_no_entity_literals_in_producer_code` | R-019 | No task today; the literal ban has no named test |
| FR-020 | Producers import no graph/claim/admission/projection symbol; `TYPE_CHECKING` only | **REWRITE** | T152 | `test_producer_imports_no_projection_symbols` | R-020a, R-020b | D9: §74 names **six** symbols; FR-020 names **zero** and does not forbid *construction* |
| FR-021 | `PredicateHypothesis` preserves 7 named fields; 4 states; no `UNKNOWN_RELATION`; no fabricated `RelationRef` | KEEP | T132 | `test_predicate_hypothesis_field_and_state_set` | R-021 | Old T028 cited FR-016/FR-017 instead |
| FR-022 | A signal mapping to a known operator becomes typed only through explicit regime interpretation | KEEP | T132 | `test_known_operator_requires_regime` | R-022 | No task today |
| FR-023 | A predicate with no operator survives as an `UNKNOWN` candidate and 7 facts stay answerable | KEEP | T135 | `test_unknown_candidate_answers_all_seven` | R-023 | The 7 questions are implied by the sentence, not enumerated; the FR-003 rewrite must not narrow them |
| FR-024 | `RelationClaimMaterial` constructible only when predicate/participants/roles are resolved; no invented local relation type | KEEP | T135 | `test_unknown_predicate_yields_candidate_only` | R-024 | No task today |
| FR-025 | Assembly groups by structural participant configuration, preserves direction/polarity/signature/signal refs/alternatives, detects conflicts, resolves nothing, admits nothing | KEEP | T155 (+T136, T157) | `test_assembly_groups_and_preserves` | R-025 | Correctly cited by old T031/T041/T043 |
| FR-026 | No majority-vote semantic adjudication; `_arity_of()`-style resolution removed | KEEP | T153 | `test_no_majority_vote_path_exists` | R-026 | Correctly cited by old T040 |
| FR-027 | Distinct predicates over the same endpoints stay distinct hypotheses | KEEP | T155 | `test_equal_endpoints_do_not_merge` | R-027 | Correctly cited |
| FR-028 | Differing `relation_ref`s → one `AMBIGUOUS` hypothesis; genuine disagreement → `CONFLICTING`, both preserved | CLAIMED (A2/A4b) | T154 *(reserved)* | `test_one_hypothesis_two_regimes` | R-028 | Must also cover E5: two differing **signatures** are two candidates, not one ambiguous one |
| FR-029 | A versioned foundational type pack exposing 8 per-type fields; no relation semantics, no truth | CLAIMED (A5) | T111 *(reserved)* | `test_pack_field_set_and_version` | R-029 | Old T017 cited FR-029 for `TypeHypothesis` — wrong FR |
| FR-030 | The pack MUST cover ≥32 named `core:` entity classes | CLAIMED (A5) | T111 *(reserved)* | `test_pack_manifest_matches_shipped_artifact` | R-030 | D7: 32 mandated classes with **no producer obligation**; a closed inline list is a spec artefact, not a semantic rule |
| FR-031 | Value types conceptually separate; a value MUST NOT be forced into `Entity` | CLAIMED (A5) | T111 *(reserved)* | `test_value_type_is_not_an_entity` | R-031 | Old T017 cited it for `TypeHypothesis`; it belongs to the pack |
| FR-032 | `TypeHypothesis` first-class with 13 named fields and 6 states; distinguishable from `TypeAssertion` | CLAIMED (A5) | T116 *(reserved)* | `test_type_hypothesis_field_and_state_set` | R-032 | E3: `data-model.md` §6 makes it a container of `TypeCandidate`s — a new epistemic level, against §103 |
| FR-033 | A mention holds several competing `TypeHypothesis` values with none silently selected | CLAIMED (A5) | T116 *(reserved)* | `test_apple_retains_three_selects_none` | R-033 | P2; must not gate `SC-001` |
| FR-034 | Type space extensible by hierarchy; `broader`/`narrower` usable for expansion/blocking/ranking/validation, never as a gate | CLAIMED (A5) | T111 *(reserved)* | `test_hierarchy_expansion_never_gates` | R-034 | Old T019 cited it for the mention index |
| FR-034a | Type space desirable; a finite mandatory **relation** list is forbidden (policy) | CLAIMED (A5) — **recommended: REMOVE → ADR B + non-goals** | T115 *(ADR)* | — *(n/a)* | — | Restates `INV-002` and the constitutional non-goals; no observable criterion is constructible; its only citation is by a task that mis-cites it |
| FR-035 | External vocabularies MUST produce a `TypeSignal` with `source_vocab`/`surface`/`mapping_candidates`, never a `TypeAssertion` | CLAIMED (A2/A4b **and** A5 — needs arbitration) | T112 *(reserved)* | `test_jsonld_yields_type_signal_not_assertion` | R-035 | Double-claimed. Needs an explicit handover before Phase 2 can start |
| FR-036 | A type mapping retains 8 provenance fields; no collapse without a mapping record; SSSOM-compatible; non-equivalence recordable | CLAIMED (A2/A4b **and** A5) | T113 *(reserved)* | `test_mapping_retains_provenance` | R-036 | Double-claimed, same handover problem |
| FR-037 | Type pipeline order; all prior states retained; a later `INFERRED` is a new revision | CLAIMED (A5) | T117 *(reserved)* | `test_type_pipeline_retains_all_states` | R-037 | Old T018 cited FR-032 instead |
| FR-038 | An ontology miss MUST mean `unknown type`, never a rejected mention | CLAIMED (A5) | T117 *(reserved)* | `test_ontology_miss_yields_unknown_not_rejection` | R-038 | No task today; §97's mutation has no owner (see FR-102) |
| FR-039 | Type resolution **SHOULD** consume 8 context inputs; **MUST** represent competing hypotheses with evidence | CLAIMED (A5) — **recommended: REWRITE** (split MUST from SHOULD) | T120 *(reserved)* | `test_context_inputs_are_consumed` | R-039 | A `SHOULD` cannot gate a checklist item; the MUST half is the testable half |
| FR-039a | Type hypotheses and role hypotheses MUST be mutually consumable; hints MUST stay hints | CLAIMED (A5) — **recommended: REWRITE** (forbid role hints entering identity) | T121 *(reserved)* | `test_role_hint_is_never_truth` | R-039a | E2: `role: str` free text inside `logical_material` relocates the exact defect the feature exists to destroy |
| FR-040 | 13 producer families MUST all be implementable, writing to one downstream model | CLAIMED (A5) — **recommended: REWRITE** (completeness marker + minimum implementable set) | T151 *(reserved)* | `test_every_channel_implemented_or_explicitly_unsupported` | R-040 | 13 MUSTs, 5 producers, no task, no test. "Universal" ≠ 13 implementations |
| FR-041 | The lexical producer stays one producer and is upgraded; `RELATION_CUES` retained, not the global vocabulary | KEEP | T139 | `test_lexical_emits_signature_roles_direction_arity` | R-041 | No task today |
| FR-042 | The syntactic producer covers ≥8 realisations and emits no operator the mapping layer did not say | KEEP | T138 | `test_syntactic_realisation_matrix` | R-042 | No task today |
| FR-043 | Parser capability explicit and pinned; no LLM in the constitutional path; a missing parser means no syntactic signals, never batch failure | **REWRITE** | T137 | `test_batch_succeeds_and_emits_useful_signals_without_parser` | R-043 | D9: §30's parser-free baseline has **no enforcing test**. "MUST be explicit" has no observable form |
| FR-044 | The structural producer represents `structural_path`; structure MUST NOT be flattened into a predicate | KEEP | T140 | `test_structural_path_is_not_flattened` | R-044 | No task today |
| FR-045 | The link producer preserves 9 fields and asserts only "A links to B" | **REWRITE** | T141 | `test_one_anchor_is_one_corroboration` | R-045 | `HyperlinkExtractor` emits `LINK` **and** `REFERENCE` per anchor with identical participant refs and identical surface, differing only in `kind` — one hyperlink counted as two independent observations |
| FR-046 | The reference/citation producer covers ≥6 forms and never emits `cites` | KEEP | T142 | `test_reference_producer_form_coverage` | R-046 | No task today |
| FR-047 | The table producer preserves 6 refs; a row is n-ary structural evidence; malformed tables refused by explicit rule, never positionally guessed | KEEP | T143 | `test_table_row_is_nary_evidence` | R-047 | No task today. FR-047 *is* cited — by old T071, meaning §47 (§0) |
| FR-048 | The list producer handles term/item structure without creating semantic relations | KEEP | T144 | `test_list_structure_creates_no_relation` | R-048 | No task today; shares `tables.py` with the table producer |
| FR-049 | The metadata producer covers 10 named fields plus unrecognised metadata, which MUST survive; `author` ≠ `authored_by` | KEEP | T145 | `test_unrecognised_metadata_survives` | R-049 | No task today |
| FR-050 | The attribute producer represents `Key: value`; a value is not an entity; three arrow kinds distinguished | KEEP | T146 | `test_attribute_arrow_kinds_are_distinguished` | R-050 | No task today |
| FR-051 | The temporal producer attaches the expression as evidence with surface, interval, precision and span | KEEP | T147 | `test_temporal_evidence_carries_precision` | R-051 | No task today |
| FR-052 | The event producer supports n-ary and MUST NOT reduce the sale sentence to two binary edges at substrate level | KEEP | T148 | `test_event_is_nary_at_substrate` | R-052 | No task today |
| FR-053 | The co-occurrence producer reports adjacency and MUST NEVER produce `related_to` | KEEP | T149 | `test_cooccurrence_never_becomes_related_to` | R-053 | No task today; the kind exists and **no producer emits it** |
| FR-054 | The semantic producer creates interpretation candidates only; an ontology match is never automatic truth | KEEP | T150 | `test_semantic_producer_never_yields_truth` | R-054 | No task today |
| FR-055 | The executable path MUST implement 14 named stages **in order** | **REWRITE** | T158 (+T164) | `test_lifecycle_stage_partial_order_holds` | R-055a, R-055b | A **third** order the brief never states: §57 puts `REGIME` before `RELATION SIGNALS`, §101 puts `SEMANTIC REGIME` after `ENTITY RESOLUTION`, FR-055 puts it between them and asserts it as mandatory without flagging the conflict |
| FR-056 | The claim lifecycle is Candidate → ClaimMaterial → Validation → Admission → RelationClaim; no fake `SUPPORTED` gate | KEEP | T161 | `test_claim_lifecycle_order` | R-056 | Old T045 cited FR-057/FR-058 instead |
| FR-057 | `ExecutionResult` exposes `material` as a real stage product; a stage that silently validates or admits is unacceptable | KEEP | T159 | `test_execution_result_exposes_every_stage_object` | R-057 | No task today |
| FR-058 | A `GraphEdge`/`HyperEdge` exists only after a `RelationClaim` | **MERGE → `INV-004`** | T174 | `test_edge_implies_an_admitted_claim` | R-058 | Byte-equivalent to `INV-004`; two normative owners for one obligation |
| FR-059 | Durable store seams for 3 types with 6 named operations | KEEP | T169 (+T170) | `test_store_operations_exist` | R-059 | Old T046 cited FR-059 for the admission gate |
| FR-060 | Every store reconstructs the exact domain object; a digest may identify data but MUST NOT be the only copy | KEEP | T172 (+T168) | `test_build_store_read_asserts_field_list` | R-060 | Correctly cited by old T057 |
| FR-061 | The normal acquisition path MUST persist `SourceTemporalObservation`; EDGAR day-precision, Common Crawl index-time; publication time never in `Capture.fetched_at` | **REWRITE** | T171 | `test_normal_path_emits_a_temporal_observation` | R-061 | Unachievable as written while live PostgreSQL is unreachable; must become a *write*-obligation testable offline plus an explicit reporting clause |
| FR-062 | A forward-only migration; applied migrations unedited; parity + schema invariants + **round-trip tests MUST be created** | **REWRITE** | T173 (+T165) | `test_live_roundtrip_is_conditional_and_reports_offline` | R-062a, R-062b | Brief §62 says *"round-trip tests **if PostgreSQL available**"*; FR-062 turned a conditional into an unconditional MUST and thereby contradicts the spec's own assumption. Must also absorb K6 |
| FR-063 | `DIRECTED` claims project with direction preserved; no `min`/`max` canonicalisation | KEEP | T175 | `test_directed_endpoints_are_not_reordered` | R-063 | No task today |
| FR-064 | `UNDIRECTED` MAY canonicalise **only** when the admitted contract declares symmetry | KEEP | T175 | `test_symmetry_must_come_from_the_contract` | R-064 | No task today |
| FR-065 | `NARY` projects to `HyperEdge`; flattening needs an explicit policy and each derived edge names its source claim | KEEP | T176 | `test_derived_binary_edge_names_its_claim` | R-065 | No task today |
| FR-066 | Entity→value relations distinguishable from entity→entity in claim and projection | KEEP | T177 | `test_value_relation_is_distinguishable` | R-066 | No task today |
| FR-067 | An explicit hypothesis/evidence view serves unadmitted relations; `GraphEdge` MUST NOT be reused | KEEP | T178 | `test_hypothesis_view_is_not_a_graph_edge` | R-067 | No task today; `RelationEvidenceView` is a named Key Entity with no FR and no task |
| FR-068 | Navigate edge → claim → candidate → signals → observations → source, and back to every edge the source fed | KEEP | T179 (+T180) | `test_edge_to_source_and_back_reaches_every_edge` | R-068 | K7: `EVIDENCE_BACKWARD_CHAIN` has no `CANDIDATE` and no `ENTITY` hop, so the promised walk cannot terminate |
| FR-069 | Projection preserves 9 provenance facts; that metadata MUST NOT enter edge identity | KEEP | T175 | `test_edge_metadata_is_not_edge_identity` | R-069 | Old T059 cited FR-079 instead |
| FR-070 | RDF-compatible shape is permitted; RDF MUST NOT become the internal model; SHACL is an optional sidecar | **REMOVE → design note + non-goals** | — *(design note)* | — *(n/a)* | — | A permission plus two restatements of constitutional non-goals. No acceptance criterion is constructible from a permission |
| FR-071 | Bounded-neighbourhood generation; 11 named neighbourhood classes; every signal states its actual neighbourhood | KEEP | T137 | `test_every_signal_declares_a_neighbourhood_class` | R-071 | Old T021 cited FR-070/FR-095 instead |
| FR-072 | Every producer reports 5 metrics; hard ceilings explicit; the **implementation** must be bounded, not the counter | KEEP ▸ **merge target** ← FR-080 | T187 (+T191) | `test_ceilings_are_live_and_all_five_metrics_reported` | R-072, R-072a | Two FRs for the same five metrics; the merge also carries §72's O(N²) mutation |
| FR-073 | Two independent runs identical; producer order irrelevant; no `uuid4`, no `now()`, no dict-order, no random tie-break | KEEP | T186 | `test_ids_independent_of_order_clock_and_randomness` | R-073 | No task today |
| FR-074 | No hidden semantic gate: no `allows_type()` as a drop/deny, no `if relation not in registry: continue` | **REWRITE** | T152 | `test_no_ontology_drop_gate_in_any_extraction_path` | R-074 | `registry.py:76` **does** call `pack.allows_type(name)` today, so the FR describes a state that is false; a grep cannot prove the absence of a gate, so the check must be AST-based |
| FR-075 | A deterministic golden entity-type corpus over §82's surfaces including the 5 ambiguous names | KEEP | T182 | `test_entity_type_golden_corpus` | R-075 | No FR citation today; `T064` covers it in substance |
| FR-076 | A deterministic golden relation corpus over §83's cases plus §70's six end-to-end HTML cases | KEEP | T181 | `test_relation_golden_corpus` | R-076 | No FR citation today; `T063` covers it in substance |
| FR-077 | An active/passive identity test where the **derivation itself** produces the shared id | KEEP | T183 | `test_derivation_produces_the_shared_logical_id` | R-077 | No task today; this is `SC-001`'s only named enforcement and it is unowned |
| FR-078 | A mutation harness breaking 6 entity + 8 relation + 4 projection fields; a **named** test fails for each | KEEP ▸ **merge target** ← FR-079 | T184 | `test_every_manifest_entry_has_a_failing_named_test` | R-078a, R-078b | `SC-015` demands ≥ 20; FR-078 and §93 both give **18** |
| FR-079 | "**Four** named mutations MUST exist" — then lists **six** | **MERGE → FR-078** | T184 | `test_the_six_section_mutations_fail` | R-079 | The count contradicts the list in the same sentence; the six are a subset of §93, not a separate apparatus |
| FR-080 | The extraction layer stays linear or bounded-superlinear; every producer reports 5 metrics | **MERGE → FR-072** | T187 | `test_extraction_complexity_is_bounded` | R-080 | The same five metrics as FR-072 plus a complexity bound |
| FR-081 | No regression into 7 named packages; known failures unchanged; "green" forbidden with hidden new failures | KEEP | T190 (+T101, T192) | `test_baseline_membership_is_unchanged` | R-081, R-081a | Correctly cited. Must also track the **22 tests that never executed** (14 self-skipped + 8 Postgres-blocked) or the floor is a lie |
| FR-082 | Six stop conditions; report `UNKNOWN`/`AMBIGUOUS`/`CONFLICTING`/`UNSUPPORTED` rather than guessing | KEEP | T193 | `test_every_stop_condition_is_reported` | R-082 | Correct as a rule. It is **not** the home for the synonym table (old T015) — that is a distinct gap |
| FR-083 | Ship 7 spec artefacts plus `contracts/` plus ADR-level records A–K | **REWRITE** | T193 (+T115, T164) | `test_all_mandated_artefacts_exist` | R-083 | No task cites it. K5: governance requires an ADR for entity-resolution-grade decisions and the N5 synonym table has no slot in A–K |
| FR-084 | The completion report distinguishes 5 status categories and does not claim completeness from passing tests | **REWRITE** | T194 | `test_report_has_all_fourteen_mandated_sections` | R-084a, R-084b | Only 5 of §114's **14** mandated sections survive; the other 9 have no owner at all |
| FR-085 | `signal_refs` canonicalised on construction; determinism from the type, not a call-site sort | KEEP | T105 | `test_candidate_id_is_order_independent` | R-085 | Correctly cited by old T005 |
| FR-086 | `RelationCandidate` gains `to_dict`/`from_dict` round-tripping "its 26 fields … including `signal_refs`, `direction`, `polarity`, `alternative_refs`, `mapping_evidence_refs` and `confidence`" | **REWRITE** | T106 | `test_candidate_roundtrip_asserts_field_list` | R-086 | E10: **none** of `direction`, `polarity`, `alternative_refs`, `mapping_evidence_refs` is a `RelationCandidate` field today; FR-088 says they do not exist yet. The FR asserts as fact what another FR defers |
| FR-087 | `predicate_signature` persisted in its own columns on both tables | CLAIMED (A7) | T167 *(reserved)* | `test_signature_columns_exist_and_are_read_back` | R-087 | Correctly cited by old T051/T053 |
| FR-088 | `relation_candidate` gains 4 columns, `relation_claim` gains `candidate_id`; no id-participating field absent from its row | CLAIMED (A7) | T166 *(reserved)* | `test_no_identity_field_is_missing_a_column` | R-088 | Correctly cited by old T052 |
| FR-089 | `_material()` includes declared arity mode and role bindings; `producer_ref` stays; 3 wrong docstrings corrected | KEEP | T129 | `test_arity_change_changes_the_signal_id` | R-089 | Correctly cited by old T026/T027 |
| FR-090 | Conflict over arity/direction/polarity/roles yields `CONTRADICTED` with both readings; vote and tie-break deleted; `-> Any` becomes `RelationArityMode` | KEEP | T153 (+T154) | `test_conflict_yields_contradicted_and_both_readings` | R-090 | Correctly cited by old T039/T040 |
| FR-091 | `RelationalReading.to_candidate()` removed or reduced to a call into the assembler | KEEP | T156 | `test_exactly_one_signal_to_candidate_path` | R-091 | Correctly cited by old T042 |
| FR-092 | Lifecycle split observable; `ValidationReport` retained; the post-admission re-validation is removed **or justified**; the admission decision actually gates the store write; no doubled production writes | **REWRITE** | T160 (+T161, T162) | `test_admission_decision_gates_the_store_write` | R-092a, R-092b, R-092c | "removed **or justified**" has no pass condition, so a one-line written justification satisfies it while leaving the banned `candidate → … → claim → validate again` path in place. Old T046 cited FR-059 for this |
| FR-093 | `pairs_considered` reports something real; `scanned // 16` / `// 32` deleted; `max_pairs_considered` is a live ceiling | KEEP | T139, T143, T145 | `test_pairs_considered_is_real_or_a_stated_zero` | R-093 | Correctly cited by old T033/T036 |
| FR-094 | No field name, property name, document placeholder or truncated string as a participant; `document:current` removed; 64-char truncation replaced | KEEP | T145 | `test_no_placeholder_or_truncated_participant` | R-094 | Correctly cited by old T033/T035. Measured: 4 truncations, 1 fallback, 6 property-name subjects |
| FR-095 | Structural data loss reported, not silent; `zip(..., strict=False)` becomes strict; a width-mismatched row emits a note; a heuristic header choice MUST NOT be published as `precision="exact"` | **REWRITE** | T144 | `test_no_silent_structural_loss` | R-095 | **E7: the premise is false.** `Neighbourhood.is_exhaustive` tests for the substring `"exhaustive"`, not `"exact"`. The FR as written is unverifiable |
| FR-096 | `SourceTemporalObservation` reachable from the normal acquisition path; a repository with a writer and a reader exists | KEEP | T171 | `test_temporal_observation_is_reachable_and_persisted` | R-096 | Correctly cited by old T056 |
| FR-097 | Migration `021` on top of the forward-only `020`; `020` unedited; every column FR-087/FR-088 requires is added | CLAIMED (A7) — **recommended: REWRITE** to absorb K6 | T165 *(reserved)* | `test_migration_021_adds_columns_and_drops_the_asserts_checks` | R-097a | **K6: `021` is specified as ADD-only.** It must also DROP `ck_relation_signal_asserts_something` and `ck_relation_candidate_asserts_something` and update `ck_relation_signal_kind`'s whitelist. No artefact says so, so `SC-012` is unachievable as planned |
| FR-098 | `verify_candidate_material_partition()` called and made correct, or deleted | KEEP | T107 | `test_material_partition_verifier_passes` | R-098 | Correctly cited by old T008 |
| FR-099 | `RelationClaim` re-derives and checks its own carried `relation_id` | KEEP | T108 | `test_claim_rejects_a_forged_id` | R-099 | Correctly cited by old T009 |
| FR-100 | The semantic path is wired into the live production path; `ExecutionRequest.producers` is populated | KEEP | T188 (+T163, T189) | `test_live_post_produces_signal_candidate_claim_edge` | R-100 | Correctly cited by old T050/T068 |

### 1.4 Verdict tally

| Verdict | Count | FRs |
|---|---|---|
| KEEP | 57 | all others in the table above |
| KEEP ▸ merge target | 2 | FR-072, FR-078 |
| REWRITE | 19 | 002, 011, 012, 013, 014, 015, 018, 020, 043, 045, 055, 061, 062, 074, 083, 084, 086, 092, 095 |
| MERGE (deleted as standalone) | 3 | FR-058 → INV-004; FR-079 → FR-078; FR-080 → FR-072 |
| REMOVE | 1 | FR-070 |
| CLAIMED BY AGENT | 20 | 003, 004, 028, 029–040 (incl. 034a, 039a), 087, 088, 097 |
| **Total** | **102** | ✔ matches the measured FR count exactly |

Of the 20 `CLAIMED`, this job additionally *recommends* a verdict for four — FR-034a (REMOVE),
FR-039 (REWRITE), FR-039a (REWRITE), FR-040 (REWRITE) — because their defects are set-level
defects, recorded here so the owning agent inherits them rather than re-derives them.
**FR-035 and FR-036 are claimed by two agents** and need an arbitration decision before Phase 2
can start; that is a coordination blocker, not a spec defect, and I record it as one.

---

## 2. T2 — The consolidated normative FR set

### 2.1 Total

> **The post-triage normative set is 100 functional requirements**, plus 5 constitutional
> invariants (unchanged, one widened by a merge) and 38 success criteria (16 existing + 22 new).

Arithmetic: `102 − 3 merged away − 1 removed + 2 new = 100`. If A5 accepts the `FR-034a` removal
recommendation the total is **99**.

### 2.2 Deleted IDs and where each went

| Deleted | Goes to | Reason |
|---|---|---|
| FR-058 | `INV-004` | byte-equivalent duplicate of an invariant; two normative owners for one obligation |
| FR-070 | design note `design-notes/rdf-interoperability.md` + the constitutional non-goals list | a permission plus two non-goals; no acceptance criterion is constructible from a permission |
| FR-079 | FR-078 | "Four" vs six in one sentence; the six are a subset of §93 |
| FR-080 | FR-072 | the same five metrics restated |
| FR-034a *(recommended)* | ADR B + non-goals | restates `INV-002`; its only citation is by a task that mis-cites it |

Every deleted slot MUST retain a tombstone in `spec.md` in the form
`**FR-058**: *merged into `INV-004` — see repair/A6-fr-triage.md §2.2*` so that no citation
anywhere in the repository dangles. **No surviving FR is renumbered.**

### 2.3 Renumbering: none, deliberately

The instruction asks which FRs are renumbered. **My decision is that none are.** Reasons:

1. The surviving 100 keep their original ids, so the **1006 inline `FR-0xx` citations in the
   code** get a *stable target set* to be reconciled against. Renumbering invalidates that
   reconciliation twice and no agent is budgeted for a third pass.
2. The gaps at 058, 070, 079, 080 are cheap and are themselves evidence: a machine checker can
   assert "every id in 001–102 is either defined, tombstoned, or a declared new id" — a check
   that a dense renumbering makes impossible to express.
3. `FR-034a` and `FR-039a` already force the citation regex to accept a lowercase suffix. That
   constraint is recorded in §6 as a hard grammar rule, not worked around by renumbering.

The alternative (dense 001–100) is recorded as **rejected**, with its cost: it makes every one of
the 1006 code citations, 66 task citations and 2 checklist citations wrong again for a purely
cosmetic gain, and it destroys the audit trail between the broken artefact and the repaired one.

### 2.4 Replacement text for the 19 REWRITEs, and merged text for the 3 MERGEs

Each block is the complete replacement body. Where a rewrite depends on another agent's decision
it is marked `[INTERFACE: …]` and the dependency is named.

---

**FR-002 (REWRITE)** — *the `SC-001` enabler, half 1 of 2*

> `logical_candidate_id` MUST be derived from exactly: tenant, the **canonically ordered**
> participant configuration, arity shape, role shape, directional configuration, polarity, and
> the predicate signature. Participants MUST be canonically ordered before they enter identity
> material: for a `DIRECTED` reading, subject before object; for `NARY`, by the signature's
> normalised role name then by participant ordinal; for `UNDIRECTED`, by the signature's canonical
> subject/object slots — never by input order, and never by `min`/`max` of a raw ref. The
> derivation MUST produce the identity; a fixture MUST NOT. Canonicalisation MUST be implemented in
> the identity function, not at a call site. *(§19, §23, §84, §101)*

**FR-011 (REWRITE)** — *removes the `TEMPORAL` contradiction*

> `SignalKind` names an **observation channel** only. It MUST contain at least `LEXICAL`,
> `SYNTACTIC`, `STRUCTURAL`, `METADATA`, `LINK`, `REFERENCE`, `TABLE`, `LIST`, `EVENT`,
> `ATTRIBUTE`, `CO_OCCURRENCE`, `SEMANTIC`. It MUST NOT contain any member naming an orthogonal
> aspect (`NEGATION`, `QUANTITY`, `COREFERENCE`, `UNCERTAINTY`) and MUST NOT contain `TEMPORAL`:
> temporal observation is a channel expressed as an aspect on a signal, because time already lives
> in `stated_axes`/`SourceTemporalObservation` and a `TEMPORAL` *kind* would re-mix channel with
> aspect. `SCHEMA` MAY remain as a channel of the semantic producer. The `TEMPORAL`-as-a-channel
> reading of §15/§27 is **rejected in writing** by this FR, so that no task may cite §15 or this FR
> either to forbid or to require the member. *(§15, §27, §16)*

**FR-012 (REWRITE)** — *turns a SHOULD into a gateable MUST*

> `NEGATION`, `QUANTITY`, `COREFERENCE` and `UNCERTAINTY` MUST be expressed as members of a
> separate `SignalAspect` value carried by `RelationSignal`, with the following field mapping and
> no other: `NEGATION → Polarity.denied`; `QUANTITY → RelationParticipant.argument_shape = "value"`
> plus a producer note; `COREFERENCE → a reference relation between two mention refs, not an
> observation channel`; `UNCERTAINTY → Polarity.uncertain` or
> `TypeHypothesis.hypothesis_state`, whichever the reading is about. A `SignalKind` member naming
> an aspect MUST fail a structural test. *(§15)*

**FR-013 (REWRITE)** — *fixes E6 and closes K6*

> A `RelationSignal` MUST NOT require `relation_surface` to be non-empty. A `CO_OCCURRENCE` signal
> with an empty `relation_surface` and a `None` `predicate_signature` MUST be constructible,
> persistable and assemblable, provided it states an explicit observational basis. Migration `021`
> MUST **drop** `ck_relation_signal_asserts_something` and
> `ck_relation_candidate_asserts_something`, which encode
> `relation_surface <> '' OR relation_ref IS NOT NULL`, and MUST update the
> `ck_relation_signal_kind` whitelist for every member removed by FR-011. The domain-side check
> MUST be a named module constant `SIGNAL_ASSERTS_NOTHING`, replacing the current `__post_init__`
> string error code; it is a value, not a function. *(§16, §62)*

**FR-014 (REWRITE)**

> `observational_basis` MUST be a required, typed field on every `RelationSignal`, drawn from a
> closed enumeration: predicate text, DOM relation, table slot, hyperlink, citation, proximity,
> metadata field, event frame, attribute key. A signal with no basis MUST fail construction. The
> enumeration is closed: a new basis is an explicit extension with a version bump, not a free
> string. *(§16)*

**FR-015 (REWRITE)** — *closes the two-vs-three polarity contradiction*

> `polarity` MUST be an explicit, required, durable field on every `RelationSignal` and on every
> `RelationCandidate`. Its domain is **closed and is `Polarity.{ASSERTED, DENIED}`** — two
> members, not three. Uncertainty is not polarity: it is `TypeHypothesis.hypothesis_state` for
> types and `PredicateHypothesis.resolution_state` for predicates, and neither is a third
> polarity. A denied relation MUST preserve its predicate surface and its signature, MUST be
> storable and queryable, MUST NOT be dropped, and MUST NOT yield a positive candidate or an edge.
> `polarity` MUST be a column on `relation_signal` and `relation_candidate` — a derived local is
> not persistence. *(§41, §89)*

**FR-018 (REWRITE)**

> `MentionOccurrenceIndex` MUST exist with deterministic lookup on the full tuple **(capture,
> segment, offset/span, normalized surface, extractor occurrence)**; omitting `capture` is
> forbidden, because two captures of one segment MUST NOT collide onto one id. The index MUST be
> the **sole minter** of mention identifiers; no other component may construct one. Lookup MUST
> resolve to a mention, never to an entity.
> `[INTERFACE: the identifier prefix is currently `MENTION-…` in `spec.md` and `MN-…` in
> `data-model.md` §6 and `tasks.md` T019. The identity owner picks one; the checker (§6) will
> require spec and code to agree.]` *(§26)*

**FR-020 (REWRITE)** — *makes §74's six-symbol prohibition testable*

> No producer module may **import or construct** any of: `GraphEdge`, `HyperEdge`, `GraphStore`,
> `RelationClaim`, the `admission` package, the `projection` package. `TYPE_CHECKING` is the only
> permitted reference and never in executable code. The check MUST be an AST/import-graph test
> over the producer package, not a grep, and it MUST cover construction as well as import.
> *(§74, §75)*

**FR-043 (REWRITE)** — *makes §30's parser-free baseline gateable*

> Parser capability MUST be explicit and pinned: `model_ref`, `model_version`, `parser_version` and
> `configuration_hash` are part of interpretation provenance. No LLM may appear in the
> constitutional extraction path. A missing parser MUST mean *no syntactic signals*, never batch
> failure. **A named test MUST run the full production batch with the parser capability
> unavailable and MUST assert: exit success, ≥1 non-empty lexical signal, and ≥1 candidate.**
> *(§30)*

**FR-045 (REWRITE)** — *absorbs the one-anchor double count*

> The link producer MUST preserve source mention, target/resource mention, href, anchor text, DOM
> path, link position, the `rel` attribute and target metadata, and MUST assert only "A links to
> B" — never `cites`, `owns`, `hosts` or `employs`. `rel="author"` MAY strengthen a signal and is
> still only a candidate. **One anchor MUST NOT yield two signals that count as independent
> corroboration**: two signals over one anchor that differ only in `kind` share a `producer_ref` and
> MUST count once. *(§32, §24, §85)*

**FR-055 (REWRITE)** — *replaces the third order with a partial order and names the conflict*

> The executable path MUST make the following precedence constraints hold, each stage exposing the
> object it produced: `OBSERVATION ≺ CONTEXT ≺ MENTIONS ≺ TYPE_SIGNALS`; `MENTIONS ≺
> RELATION_SIGNALS`; `RELATION_SIGNALS ≺ RELATION_CANDIDATE ≺ RESOLUTION ≺ CLAIM_MATERIAL ≺
> VALIDATION ≺ ADMISSION ≺ STORE`; `STORE ≺ EDGE ≺ WORLDLINE`.
> The brief states `REGIME` in **three incompatible positions** (§57: before `RELATION SIGNALS`;
> §101: after `ENTITY RESOLUTION`; this FR previously: between them). This FR therefore fixes only
> the constraints above and records `REGIME`'s position as an **open decision for `plan.md`**, to
> be answered by an ADR before Phase 8. Until then no task may assert a total stage order and no
> test may assert one. *(§57, §58, §101)*

**FR-061 (REWRITE)** — *makes the obligation offline-testable*

> The **normal** acquisition path MUST persist `SourceTemporalObservation`:
> `adapter → Capture + SourceTemporalObservation → durable store`. The helper no production path
> calls MUST NOT be the only route. EDGAR `date_filed` MUST stay day-precision; Common Crawl
> `timestamp` MUST stay index-observation time; source publication time MUST NOT be stuffed into
> `Capture.fetched_at`.
> **Verification clause:** because live PostgreSQL is unreachable in the working environment, the
> enforcement test MUST assert that the normal path **issues a write** through the repository seam
> (a spy/recording repository is sufficient), and the live round trip MUST be reported
> `verified only offline` per FR-084. The write obligation is unconditional; only the live
> verification is conditional. *(§61, §114)*

**FR-062 (REWRITE)** — *restores the conditional and absorbs K6*

> A new forward-only migration MUST be created if required. Applied migrations MUST NOT be
> modified. It MUST preserve data, be tenant-scoped, add CHECKs only for constitutional invariants,
> keep ORM/migration parity, and never drop historical semantic observations. Create **migration
> parity tests** and **schema invariant tests** unconditionally, and **round-trip tests if
> PostgreSQL is available** — the conditional is restored from §62 and MUST NOT be hardened into an
> unconditional MUST. When PostgreSQL is unavailable the omission MUST be reported
> `verified only offline` with the reason, per FR-084. `021` MUST also drop the two
> `*_asserts_something` CHECKs and update the `SignalKind` whitelist per FR-013/FR-011.
> *(§62; the restoration is mandated by the brief's own conditional)*

**FR-074 (REWRITE)** — *a gate, not a grep*

> No hidden semantic gate. No extraction path may call `OntologyPack.allows_type()` as a
> drop/deny decision, and no relation-extraction path may contain
> `if relation not in registry: continue` or an equivalent guard whose effect is to drop an
> unrecognised reading. The check MUST be an AST test over every extraction module that fails on a
> call to `allows_type()` used in a boolean-drop position and on any continue-on-unrecognised guard,
> and it MUST be a **named mutation test** — §97's
> `if core pack does not know type: continue` MUST fail it. *(§73, §76, §97)*
> Note: `apps/interpretation/extractors/registry.py:76` calls `pack.allows_type(name)` today, so the
> FR describes a state that is **not** true at HEAD.

**FR-083 (REWRITE)**

> This feature MUST ship `specs/021-entity-relation-extraction-finalization/` containing `spec.md`,
> `plan.md`, `tasks.md`, `data-model.md`, `research.md`, `input.md`, `checklists/requirements.md`
> and `contracts/`, plus ADR-level records in `specs/021-.../adr/` for decisions **A–L**: **A**
> bounded foundational atomic vocabulary is allowed; **B** entity/value type vocabulary is separate
> from relation vocabulary; **C** relation extraction is open-world and signal-driven; **D** raw
> relation surface is evidence, not logical identity; **E** `PredicateSignature` is structural
> normalised identity before ontology mapping; **F** unknown predicates are durable hypotheses;
> **G** n-ary relations are native; **H** `GraphEdge` is a projection of admitted claims only;
> **I** mention binding is distinct from entity resolution; **J** no majority-vote semantic
> assembly; **K** producers remain observation instruments; **L** *the `PredicateSignature`
> normalisation rule set, including any synonym table, is versioned, sourced and reviewable* —
> added because governance requires an ADR for any entity-resolution-grade decision and A–K had no
> slot for the N5 synonym table (K5).

**FR-084 (REWRITE)** — *all 14 sections, not 5*

> The completion report MUST contain all 14 sections mandated by §114, in order, and MUST classify
> every claim in each as one of `implemented`, `verified`, `verified only offline`,
> `known limitation`, `deferred`: (1) changed-file manifest, (2) architecture summary, (3) domain
> model changes, (4) migration summary, (5) producer summary, (6) identity changes, (7) execution
> path before/after, (8) graph projection semantics, (9) corpus coverage, (10) mutation-test
> results, (11) replay/determinism results, (12) benchmark results, (13) complete test matrix,
> (14) explicit remaining debt. "Feature complete" requires that the §101 architecture is
> represented in **production** code and that the golden and mutation corpora prove the
> constitutional properties; passing tests alone is not sufficient. *(§114, §108)*

**FR-086 (REWRITE)**

> `RelationCandidate` MUST gain `to_dict()`/`from_dict()` and MUST round-trip **every field the
> type declares at the time of the change, and every field added by FR-088**, losslessly —
> explicitly including `signal_refs` and `confidence`, and including `direction`, `polarity`,
> `alternative_refs` and `mapping_evidence_refs` **once FR-088 has added them**. The previous
> wording asserted those four as existing fields; they do not exist at HEAD. The round-trip test
> MUST assert the field list, not a summary string. *(§59, §60, §91)*

**FR-092 (REWRITE)** — *closes the "or justified" escape*

> The lifecycle MUST be split so that materialisation, validation, admission and projection are
> separately observable. The `ValidationReport` that gated admission MUST be retained and surfaced,
> not discarded as a local. **The post-admission re-validation MUST be deleted.** There is no
> "or justified" alternative: §57 forbids `RelationClaim → Validation` as the primary lifecycle
> unconditionally, and a justification is not a pass condition. If a second check is genuinely
> required it MUST be a distinct, differently-scoped check with a different name and a different
> pass criterion, and it MUST NOT be the same check run twice. The admission decision MUST actually
> gate the store write rather than being computed and discarded. Production writes MUST NOT be
> doubled to demonstrate idempotency. *(§57, §58)*

**FR-095 (REWRITE)** — *the premise was false (E7)*

> Structural data loss MUST be reported, not silent. `zip(..., strict=False)` in the list producer
> MUST become strict. A width-mismatched table row MUST emit a note or a signal rather than being
> dropped. A heuristic header-row choice MUST NOT be published as an exact precision string:
> `Neighbourhood.is_exhaustive` is a substring test on that string — **it tests for
> `"exhaustive"`, not `"exact"`** — so publishing a heuristic with the literal text
> `precision="exact; …"` happens not to trip it. The real defect is that a human-readable string is
> load-bearing for a machine decision; the fix is to make `is_exhaustive` read a typed field and to
> state the heuristic on the signal. *(§46, §47)*

### 2.5 The two new requirements

**FR-101** (superseded local numbering → ARBITRATION §14 → **FR-179**) **(NEW)** — the §8 entity extractor expansion, absent from every artefact

> The deterministic entity extraction layer MUST be completed around the atomic type vocabulary,
> extending existing extractors rather than duplicating them into a second framework, and providing
> producers/readers for all seven classes of §8:
> **A. Person** — Latin, Cyrillic, initials, multi-token, titles, contextual cues, aliases,
> transliteration, Unicode normalisation, surname-first patterns; a name-shaped string MUST NOT
> imply person; every result is a hypothesis.
> **B. Organization** — legal forms, corporate suffixes, institutional names, brands, agencies,
> universities, government bodies, media, banks, companies, NGOs, strong contextual structures;
> hypothesis, never `entity = organization`.
> **C. WebSite / WebPage / Domain / URL** — deterministic extraction of `https://example.com`,
> `example.com`, `www.example.com`, with the four kept distinct; a URL string is a value, a WebPage
> a resource, a WebSite a higher-level resource, a domain a namespace.
> **D. OnlineAccount / SocialProfile** — structured profile URLs and handles
> (`github.com/user`, `twitter/x.com/user`, `linkedin.com/in/user`, `t.me/user`,
> `youtube.com/@channel`); account identity MUST NOT be inferred from a display name.
> **E. Digital identifiers** — IP, hash, CVE, crypto address, file path, identifier as value-type
> hypotheses.
> **F. Documents** — URLs pointing to files, filenames, document ids, report-like structures, PDFs
> where source metadata provides them, citations, title/identifier structure.
> **G. Event mentions** — conference, meeting, acquisition, launch, publication, incident,
> transaction, election, appointment; an event mention is not a relation and MUST NOT become a
> claim.
> **Phase ownership: §110-2 ("atomic entity type vocabulary").** Phase 2 is the only phase that owns
> this, and today it is occupied by work §110 places in Phase 5 — this is D15, and this FR is what
> makes the phase non-empty. *(§8, §110-2)*

**FR-102** (superseded local numbering → ARBITRATION §14 → **FR-180**) **(NEW)** — the meta-rule that closes D9 permanently

> Every hard prohibition stated in the brief MUST have at least one named test that **fails** when
> the prohibition is violated, and that test MUST be reachable from a task in this plan. At minimum
> this covers §72's all-mentions × all-mentions pair sweep, §74's six-symbol producer import **and
> construction** ban, §30's parser-free useful baseline, §73's semantic gate, §75's `ENT-`/`RES-`
> ban, §45's majority vote, §16's mandatory surface, §103's fourth epistemic level, and §104's
> finite mandatory relation list. A prohibition with no enforcing test is a **non-requirement** and
> MUST NOT be counted toward feature completeness. The checker's job is to assert that this list and
> `spec.md` agree, so a new prohibition cannot be added without a test.
> *(§72, §74, §30, §73, §75, §45, §16, §103, §104)*

### 2.6 Merged text for the 3 MERGEs

**`INV-004` ▸ absorbs `FR-058`**

> `GraphEdge`/`HyperEdge` are projections of admitted `RelationClaim`s only — never of a
> `RelationSignal` or a `RelationCandidate`, and a `GraphEdge` or `HyperEdge` MUST NOT exist before
> a `RelationClaim` exists. *(§51, §99, §108)*

**`FR-072` ▸ absorbs `FR-080`**

> The extraction layer MUST remain linear, or bounded-superlinear within named local structures.
> Every producer MUST expose and report `characters_scanned`, `tokens_scanned` where meaningful,
> `candidate_pairs_considered`, `structural_nodes_considered`, `signals_emitted`, input size,
> signals produced and elapsed time. Hard per-document and per-segment ceilings MUST be explicit.
> The implementation itself MUST remain bounded — a counter checked after the work does not make the
> work bounded. **A named mutation test MUST fail on an all-mentions × all-mentions pair sweep in
> any extraction path.** *(§47, §106, §72)*

**`FR-078` ▸ absorbs `FR-079`**

> A constitutional mutation harness MUST be manifest-driven. Its manifest is exactly the 18 fields
> enumerated in §93: **entity layer** `type_ref`, `entity_ref`, `tenant`, `evidence`, `mapping`,
> `status`; **relation layer** `predicate_signature`, `participants`, `roles`, `polarity`, producer
> identity, signal evidence, candidate identity, surface exclusion from logical identity;
> **projection layer** `direction`, `arity`, claim provenance, edge identity. Each manifest entry
> MUST have a **named** test that fails when that field is broken. The six §94–§99 mutations are
> manifest entries 7–12, named: raw surface in logical identity (§94), majority-vote
> arity/direction (§95), synthetic `surface:person:john` (§96),
> `if core pack does not know type: continue` (§97), `if relation_ref is None: return ()` (§98), a
> producer importing or constructing `GraphEdge` (§99). §100 is a deliverables section and §101 is a
> domain-model section; **neither is a mutation source.** The count of manifest entries is **18**,
> and `SC-015`'s "≥ 20" is corrected to "every entry in the manifest".

### 2.7 The five constitutional invariants after triage

`INV-001`…`INV-005` survive unchanged, with `INV-004` widened by the `FR-058` merge above.
`INV-002` and `INV-003` are the normative home for what `FR-034a` and `FR-038` restate — which is
exactly why `FR-034a` can be deleted without loss.

---

## 3. T3 — Traceability matrix, both directions

### 3.1 Normative direction: FR → semantic owner → task → test → checklist

> **No row of this table may be empty in the normative direction.** Every one of the 100
> normative FRs has **exactly one** semantic owner task, **≥1** acceptance test, and **≥1**
> checklist item. The 3 merged and 1 removed FRs are tombstones and are excluded from the count by
> construction (§2.2).

| FR | owner task (phase) | acceptance test(s) | checklist |
|---|---|---|---|
| FR-001 | T133 (P5), red-first at T110 (P1) | `test_logical_id_independent_of_revision_material` | R-001 |
| FR-002 | T131 (P5) | `test_active_passive_share_one_logical_id`, `test_participants_canonically_ordered` | R-001a, R-002 |
| FR-003 | T130 (P5) *(reserved, A2/A4b)* | `test_signature_components_and_no_ref` | R-003 |
| FR-004 | T130 (P5) *(reserved, A2/A4b)* | `test_owns_controls_manages_remain_distinct` | R-004 |
| FR-005 | T133 (P5) | `test_derivation_not_fixture` | R-005 |
| FR-006 | T152 (P6) | `test_independence_over_producer_family` | R-006 |
| FR-007 | T134 (P5) | `test_no_fourth_epistemic_level` | R-007 |
| FR-008 | T123 (P4) | `test_signal_is_variadic_nary` | R-008 |
| FR-009 | T123 (P4) | `test_participant_field_set` | R-009 |
| FR-010 | T123 (P4) | `test_required_dimensions_are_typed` | R-010 |
| FR-011 | T125, T128 (P4) | `test_signal_kind_is_channel_not_aspect` | R-011 |
| FR-012 | T125 (P4) | `test_aspect_split_is_exhaustive` | R-012 |
| FR-013 | T129 (P4) + T165 (P9) | `test_cooccurrence_empty_surface_constructs_persists_assembles`, `test_asserts_checks_are_dropped` | R-013a, R-013b |
| FR-014 | T126 (P4) | `test_observational_basis_is_required_and_typed` | R-014 |
| FR-015 | T124 (P4) + T166 (P9) | `test_denial_yields_denied_candidate_and_no_positive`, `test_polarity_is_a_column` | R-015a, R-015b |
| FR-016 | T119 (P3) | `test_every_participant_ref_resolves` | R-016 |
| FR-017 | T119 (P3) | `test_deferred_participant_reference` | R-017 |
| FR-018 | T118 (P3) | `test_index_lookup_keys_are_unique_per_capture`, `test_only_the_index_mints` | R-018a, R-018b |
| FR-019 | T152 (P6) | `test_no_entity_literals_in_producer_code` | R-019 |
| FR-020 | T152 (P6) | `test_producer_imports_no_projection_symbols` (import **and** construction) | R-020a, R-020b |
| FR-021 | T132 (P5) | `test_predicate_hypothesis_field_and_state_set` | R-021 |
| FR-022 | T132 (P5) | `test_known_operator_requires_regime` | R-022 |
| FR-023 | T135 (P5) | `test_unknown_candidate_answers_all_seven` | R-023 |
| FR-024 | T135 (P5) | `test_unknown_predicate_yields_candidate_only` | R-024 |
| FR-025 | T136, T155, T157 (P5/P7) | `test_assembly_groups_and_preserves`, `test_43_44_many_signals_one_candidate` | R-025 |
| FR-026 | T153 (P7) | `test_no_majority_vote_path_exists` | R-026 |
| FR-027 | T155 (P7) | `test_equal_endpoints_do_not_merge` | R-027 |
| FR-028 | T154 (P7) *(reserved, A2/A4b)* | `test_one_hypothesis_two_regimes`, `test_two_signatures_two_candidates` | R-028 |
| FR-029 | T111 (P2) *(reserved, A5)* | `test_pack_field_set_and_version` | R-029 |
| FR-030 | T111 (P2) *(reserved, A5)* | `test_pack_manifest_matches_shipped_artifact` | R-030 |
| FR-031 | T111 (P2) *(reserved, A5)* | `test_value_type_is_not_an_entity` | R-031 |
| FR-032 | T116 (P3) *(reserved, A5)* | `test_type_hypothesis_field_and_state_set` | R-032 |
| FR-033 | T116 (P3) *(reserved, A5)* | `test_apple_retains_three_selects_none` | R-033 |
| FR-034 | T111 (P2) *(reserved, A5)* | `test_hierarchy_expansion_never_gates` | R-034 |
| FR-035 | T112 (P2) *(reserved, A2/A4b ∧ A5 — arbitration needed)* | `test_jsonld_yields_type_signal_not_assertion` | R-035 |
| FR-036 | T113 (P2) *(reserved, same arbitration)* | `test_mapping_retains_provenance` | R-036 |
| FR-037 | T117 (P3) *(reserved, A5)* | `test_type_pipeline_retains_all_states` | R-037 |
| FR-038 | T117 (P3) *(reserved, A5)* | `test_ontology_miss_yields_unknown_not_rejection` | R-038 |
| FR-039 | T120 (P3) *(reserved, A5)* | `test_context_inputs_are_consumed` | R-039 |
| FR-039a | T121 (P3) *(reserved, A5)* | `test_role_hint_is_never_truth` | R-039a |
| FR-040 | T151 (P6) *(reserved, A5)* | `test_every_channel_implemented_or_explicitly_unsupported` | R-040 |
| FR-041 | T139 (P6) | `test_lexical_emits_signature_roles_direction_arity` | R-041 |
| FR-042 | T138 (P6) | `test_syntactic_realisation_matrix` | R-042 |
| FR-043 | T137 (P6) | `test_batch_succeeds_and_emits_useful_signals_without_parser` | R-043 |
| FR-044 | T140 (P6) | `test_structural_path_is_not_flattened` | R-044 |
| FR-045 | T141 (P6) | `test_one_anchor_is_one_corroboration` | R-045 |
| FR-046 | T142 (P6) | `test_reference_producer_form_coverage` | R-046 |
| FR-047 | T143 (P6) | `test_table_row_is_nary_evidence` | R-047 |
| FR-048 | T144 (P6) | `test_list_structure_creates_no_relation` | R-048 |
| FR-049 | T145 (P6) | `test_unrecognised_metadata_survives` | R-049 |
| FR-050 | T146 (P6) | `test_attribute_arrow_kinds_are_distinguished` | R-050 |
| FR-051 | T147 (P6) | `test_temporal_evidence_carries_precision` | R-051 |
| FR-052 | T148 (P6) | `test_event_is_nary_at_substrate` | R-052 |
| FR-053 | T149 (P6) | `test_cooccurrence_never_becomes_related_to` | R-053 |
| FR-054 | T150 (P6) | `test_semantic_producer_never_yields_truth` | R-054 |
| FR-055 | T158, T164 (P8) | `test_lifecycle_stage_partial_order_holds`, `test_regime_position_is_recorded_as_open` | R-055a, R-055b |
| FR-056 | T161 (P8) | `test_claim_lifecycle_order` | R-056 |
| FR-057 | T159 (P8) | `test_execution_result_exposes_every_stage_object` | R-057 |
| FR-058 | → `INV-004`, enforced by T174 (P10) | `test_edge_implies_an_admitted_claim` | R-058 |
| FR-059 | T169, T170 (P9) | `test_store_operations_exist` | R-059 |
| FR-060 | T168, T172 (P9) | `test_build_store_read_asserts_field_list` | R-060 |
| FR-061 | T171 (P9) | `test_normal_path_emits_a_temporal_observation` | R-061 |
| FR-062 | T165, T173 (P9) | `test_parity_and_schema_invariants`, `test_live_roundtrip_is_conditional_and_reports_offline` | R-062a, R-062b |
| FR-063 | T175 (P10) | `test_directed_endpoints_are_not_reordered` | R-063 |
| FR-064 | T175 (P10) | `test_symmetry_must_come_from_the_contract` | R-064 |
| FR-065 | T176 (P10) | `test_derived_binary_edge_names_its_claim` | R-065 |
| FR-066 | T177 (P10) | `test_value_relation_is_distinguishable` | R-066 |
| FR-067 | T178 (P10) | `test_hypothesis_view_is_not_a_graph_edge` | R-067 |
| FR-068 | T179, T180 (P10) | `test_edge_to_source_and_back_reaches_every_edge`, `test_rebuild_equals_projection` | R-068 |
| FR-069 | T175 (P10) | `test_edge_metadata_is_not_edge_identity` | R-069 |
| FR-070 | — *(removed; design note + non-goals)* | — | — |
| FR-071 | T137 (P6) | `test_every_signal_declares_a_neighbourhood_class` | R-071 |
| FR-072 | T187, T191 (P11/P12) | `test_ceilings_are_live_and_all_five_metrics_reported`, `test_no_global_pair_sweep` | R-072, R-072a |
| FR-073 | T186 (P11) | `test_ids_independent_of_order_clock_and_randomness` | R-073 |
| FR-074 | T152 (P6) | `test_no_ontology_drop_gate_in_any_extraction_path` | R-074 |
| FR-075 | T182 (P11) | `test_entity_type_golden_corpus` | R-075 |
| FR-076 | T181 (P11) | `test_relation_golden_corpus` | R-076 |
| FR-077 | T183 (P11) | `test_derivation_produces_the_shared_logical_id` | R-077 |
| FR-078 | T184 (P11) | `test_every_manifest_entry_has_a_failing_named_test` | R-078a, R-078b |
| FR-079 | → FR-078, enforced by T184 (P11) | `test_the_six_section_mutations_fail` | R-079 |
| FR-080 | → FR-072, enforced by T187 (P11) | `test_extraction_complexity_is_bounded` | R-080 |
| FR-081 | T101, T190, T192 (P0/P12) | `test_baseline_membership_is_unchanged`, `test_skipped_tests_are_tracked` | R-081, R-081a |
| FR-082 | T193 (P12) | `test_every_stop_condition_is_reported` | R-082 |
| FR-083 | T115, T164, T193 (P2/P8/P12) | `test_all_mandated_artefacts_exist` | R-083 |
| FR-084 | T194 (P12) | `test_report_has_all_fourteen_mandated_sections` | R-084a, R-084b |
| FR-085 | T105 (P1) | `test_candidate_id_is_order_independent` | R-085 |
| FR-086 | T106 (P1) | `test_candidate_roundtrip_asserts_field_list` | R-086 |
| FR-087 | T167 (P9) *(reserved, A7)* | `test_signature_columns_exist_and_are_read_back` | R-087 |
| FR-088 | T166 (P9) *(reserved, A7)* | `test_no_identity_field_is_missing_a_column` | R-088 |
| FR-089 | T129 (P4) | `test_arity_change_changes_the_signal_id` | R-089 |
| FR-090 | T153, T154 (P7) | `test_conflict_yields_contradicted_and_both_readings` | R-090 |
| FR-091 | T156 (P7) | `test_exactly_one_signal_to_candidate_path` | R-091 |
| FR-092 | T160, T161, T162 (P8) | `test_admission_decision_gates_the_store_write`, `test_no_second_validation_of_an_admitted_claim`, `test_writes_are_not_doubled` | R-092a, R-092b, R-092c |
| FR-093 | T139, T143, T145 (P6) | `test_pairs_considered_is_real_or_a_stated_zero` | R-093 |
| FR-094 | T145 (P6) | `test_no_placeholder_or_truncated_participant` | R-094 |
| FR-095 | T144 (P6) | `test_no_silent_structural_loss`, `test_is_exhaustive_reads_a_typed_field` | R-095 |
| FR-096 | T171 (P9) | `test_temporal_observation_is_reachable_and_persisted` | R-096 |
| FR-097 | T165 (P9) *(reserved, A7)* | `test_migration_021_adds_columns_and_drops_the_asserts_checks` | R-097a |
| FR-098 | T107 (P1) | `test_material_partition_verifier_passes` | R-098 |
| FR-099 | T108 (P1) | `test_claim_rejects_a_forged_id` | R-099 |
| FR-100 | T163, T188, T189 (P8/P12) | `test_live_post_produces_signal_candidate_claim_edge`, `test_lexical_signals_actually_runs` | R-100 |
| **FR-101** (new) | T114 (P2) | `test_entity_extractor_covers_all_seven_classes` | R-101 |
| **FR-102** (new) | T185 (P11) | `test_every_hard_prohibition_has_a_failing_test` | R-102 |

**Checklist rebuild**: 100 primary items `R-001`…`R-100` (one per normative FR; `FR-070`'s slot
becomes a tombstone) **+ 20 secondary items** = **120 rows**. The 20 secondaries are the
independent second checks listed above: R-001a, R-013b, R-015b, R-018b, R-020b, R-055b, R-062b,
R-072a, R-078b, R-081a, R-084b, R-092b, R-092c and 7 per-phase/ADR confirmations. Every legacy
`A1…J14` id is carried as a `legacy:` cross-reference so the audit trail survives.

### 3.2 Converse direction: task → FR → test → checklist

> **No task may be empty in the converse direction either.** Every one of the 94 tasks has **≥1**
> FR, and every test and checklist row resolves to an FR. This is the direction that fails hardest
> today: **23 of the 74 existing tasks cite no FR at all**, and 3 of the 51 that do cite one cite
> only the phantom `FR-103`.

| new task | phase | FR (≥1) | acceptance test | checklist |
|---|---|---|---|---|
| T101 Baseline re-run + record | P0 | FR-081 | `test_baseline_manifest_exists` | R-081 |
| T102 Alembic head confirmation | P0 | FR-097 | `test_alembic_head_is_020_and_downgrade_raises` | R-097a |
| T103 DOM/parser determinism digest pinned | P0 | FR-043 | `test_tree_digest_is_pinned_and_reproducible` | R-043 |
| T104 Rebuild the requirements checklist **with an FR column** | P0 | FR-083 | `test_every_normative_fr_has_a_checklist_row` | R-083 |
| T105 `signal_refs` canonicalised on construction | P1 | FR-085 | `test_candidate_id_is_order_independent` | R-085 |
| T106 `to_dict`/`from_dict` | P1 | FR-086 | `test_candidate_roundtrip_asserts_field_list` | R-086 |
| T107 Material-partition verifier reconciled | P1 | FR-098 | `test_material_partition_verifier_passes` | R-098 |
| T108 `RelationClaim` self-verifies its id | P1 | FR-099 | `test_claim_rejects_a_forged_id` | R-099 |
| T109 Dead `valid_from`/`valid_to` kwargs removed | P1 | FR-002 | `test_identity_function_has_no_unread_parameters` | R-002 |
| T110 **RED** identity-property test (green in P5) | P1 | FR-001, FR-002 | `test_logical_id_independent_of_revision_material` *(expected red)* | R-001 |
| T111 `core:`/`value:` pack, versioned, manifest-recorded | P2 | FR-029, FR-030, FR-031, FR-034 | `test_pack_manifest_matches_shipped_artifact` | R-029, R-030, R-031, R-034 |
| T112 `TypeSignal` from external vocabularies | P2 | FR-035 | `test_jsonld_yields_type_signal_not_assertion` | R-035 |
| T113 `TypeMapping` SSSOM record | P2 | FR-036 | `test_mapping_retains_provenance` | R-036 |
| T114 **§8 entity extractor expansion A–G** | P2 | FR-101 | `test_entity_extractor_covers_all_seven_classes` | R-101 |
| T115 ADR B + ADR L (type policy; synonym table) | P2 | FR-083 | `test_adr_b_and_l_exist` | R-083 |
| T116 `TypeHypothesis` first-class, competing | P3 | FR-032, FR-033 | `test_apple_retains_three_selects_none` | R-032, R-033 |
| T117 `TypeAssertion` pipeline + revisions | P3 | FR-037, FR-038 | `test_type_pipeline_retains_all_states` | R-037, R-038 |
| T118 `MentionOccurrenceIndex`, sole minter | P3 | FR-018 | `test_index_lookup_keys_are_unique_per_capture` | R-018a, R-018b |
| T119 Resolver injected into the producer scope | P3 | FR-016, FR-017 | `test_deferred_participant_reference` | R-016, R-017 |
| T120 Context inputs for type resolution | P3 | FR-039 | `test_context_inputs_are_consumed` | R-039 |
| T121 Type ↔ role mutual consumability | P3 | FR-039a | `test_role_hint_is_never_truth` | R-039a |
| T122 Type-pipeline contract test | P3 | FR-035, FR-037 | `test_type_pipeline_order_is_enforced` | R-035, R-037 |
| T123 **4A** `RelationParticipant` + `participants` canonical, scalars demoted | P4 | FR-008, FR-009, FR-010 | `test_signal_is_variadic_nary` | R-008, R-009, R-010 |
| T124 **4A** `Polarity`, closed two-member domain | P4 | FR-015 | `test_denial_yields_denied_candidate_and_no_positive` | R-015a |
| T125 **4A** `SignalAspect` split, additive only | P4 | FR-011, FR-012 | `test_aspect_split_is_exhaustive` | R-011, R-012 |
| T126 **4A** `observational_basis`, required typed field | P4 | FR-014 | `test_observational_basis_is_required_and_typed` | R-014 |
| T127 **4B** migrate the 7 `RelationSignal(` sites to `participants=` | P4 | FR-008 | `test_no_legacy_scalar_construction_sites` | R-008 |
| T128 **4B** remove the aspect-named members + legacy ctor params | P4 | FR-011, FR-012 | `test_signal_kind_is_channel_not_aspect` | R-011 |
| T129 Signal contract tests: n-ary end to end, empty-surface co-occurrence, arity in `_material` | P4 | FR-013, FR-089 | `test_cooccurrence_empty_surface_constructs_persists_assembles` | R-013a, R-089 |
| T130 `PredicateSignature` + N1–N6, one test per rule | P5 | FR-003, FR-004 | `test_signature_components_and_no_ref` | R-003, R-004 |
| T131 Canonical participant ordering + voice-normalised roles | P5 | FR-002 | `test_active_passive_share_one_logical_id` | R-001a, R-002 |
| T132 `PredicateHypothesis` real normaliser, 4 states | P5 | FR-021, FR-022 | `test_predicate_hypothesis_field_and_state_set` | R-021, R-022 |
| T133 `logical_candidate_id` keyed on the signature | P5 | FR-001, FR-005 | `test_derivation_not_fixture` | R-001, R-005 |
| T134 Surface change ⇒ `candidate_id` revision only | P5 | FR-001, FR-007 | `test_no_fourth_epistemic_level` | R-007 |
| T135 §90 unknown case end to end | P5 | FR-023, FR-024 | `test_unknown_candidate_answers_all_seven` | R-023, R-024 |
| T136 Signature carried signal → candidate | P5 | FR-025 | `test_assembly_carries_the_signature` | R-025 |
| T137 Parser pinned; **§30 parser-free baseline test**; neighbourhood class | P6 | FR-043, FR-071 | `test_batch_succeeds_and_emits_useful_signals_without_parser` | R-043, R-071 |
| T138 Syntactic producer | P6 | FR-042 | `test_syntactic_realisation_matrix` | R-042 |
| T139 Lexical producer upgrade + real `pairs_considered` | P6 | FR-041, FR-093 | `test_lexical_emits_signature_roles_direction_arity` | R-041, R-093 |
| T140 Structural producer, `structural_path` | P6 | FR-044 | `test_structural_path_is_not_flattened` | R-044 |
| T141 Link producer: one anchor = one corroboration | P6 | FR-045 | `test_one_anchor_is_one_corroboration` | R-045 |
| T142 Reference/citation producer | P6 | FR-046 | `test_reference_producer_form_coverage` | R-046 |
| T143 Table producer, real refs, no positional guess, live ceiling | P6 | FR-047, FR-093 | `test_table_row_is_nary_evidence` | R-047, R-093 |
| T144 List producer strict; typed `is_exhaustive` | P6 | FR-048, FR-095 | `test_no_silent_structural_loss` | R-048, R-095 |
| T145 Metadata producer: no key-subject, no fallback, no truncation | P6 | FR-049, FR-094 | `test_no_placeholder_or_truncated_participant` | R-049, R-094 |
| T146 Attribute producer: value ≠ entity | P6 | FR-050 | `test_attribute_arrow_kinds_are_distinguished` | R-050 |
| T147 Temporal producer | P6 | FR-051 | `test_temporal_evidence_carries_precision` | R-051 |
| T148 Event producer, n-ary | P6 | FR-052 | `test_event_is_nary_at_substrate` | R-052 |
| T149 Co-occurrence producer | P6 | FR-053 | `test_cooccurrence_never_becomes_related_to` | R-053 |
| T150 Semantic producer | P6 | FR-054 | `test_semantic_producer_never_yields_truth` | R-054 |
| T151 Producer-set completeness marker | P6 | FR-040 | `test_every_channel_implemented_or_explicitly_unsupported` | R-040 |
| T152 Cross-producer bans: six symbols, `ENT-`/`RES-`, 12 prefixes, no gate | P6 | FR-006, FR-019, FR-020, FR-074 | `test_producer_imports_no_projection_symbols` | R-006, R-019, R-020a, R-074 |
| T153 Delete the majority vote and tie-break | P7 | FR-026, FR-090 | `test_no_majority_vote_path_exists` | R-026, R-090 |
| T154 Conflict ⇒ `CONTRADICTED`/`AMBIGUOUS`, both readings kept | P7 | FR-028, FR-090 | `test_one_hypothesis_two_regimes` | R-028, R-090 |
| T155 Group by structural participant configuration | P7 | FR-025, FR-027 | `test_equal_endpoints_do_not_merge` | R-025, R-027 |
| T156 Remove the `to_candidate()` bypass | P7 | FR-091 | `test_exactly_one_signal_to_candidate_path` | R-091 |
| T157 §43/§44 assembly contract test | P7 | FR-025 | `test_43_44_many_signals_one_candidate` | R-025 |
| T158 Stage **partial order** + record the `REGIME` conflict | P8 | FR-055 | `test_lifecycle_stage_partial_order_holds` | R-055a, R-055b |
| T159 `ExecutionResult` exposes every stage object | P8 | FR-057 | `test_execution_result_exposes_every_stage_object` | R-057 |
| T160 Admission gates the store write | P8 | FR-092 | `test_admission_decision_gates_the_store_write` | R-092a |
| T161 Delete the post-admission re-validation (no "or justified") | P8 | FR-056, FR-092 | `test_no_second_validation_of_an_admitted_claim` | R-056, R-092b |
| T162 No doubled production writes | P8 | FR-092 | `test_writes_are_not_doubled` | R-092c |
| T163 `ExecutionRequest.producers` populated | P8 | FR-100 | `test_execution_request_producers_is_populated` | R-100 |
| T164 Docstring/ADR corrections in `execution.py` | P8 | FR-055, FR-083 | `test_no_docstring_states_a_total_stage_order` | R-055b, R-083 |
| T165 Migration `021`: add **and drop**, whitelist update | P9 | FR-013, FR-062, FR-097 | `test_migration_021_adds_columns_and_drops_the_asserts_checks` | R-013b, R-062b, R-097a |
| T166 `signal_refs`/`direction`/`polarity`/`confidence`/`candidate_id` | P9 | FR-015, FR-088 | `test_no_identity_field_is_missing_a_column` | R-015b, R-088 |
| T167 `predicate_signature` column set | P9 | FR-087 | `test_signature_columns_exist_and_are_read_back` | R-087 |
| T168 `alternative_refs`/`mapping_evidence_refs` columns | P9 | FR-060, FR-087 | `test_mapping_evidence_is_not_only_a_digest` | R-060, R-087 |
| T169 Repository/writer/reader for the three tables | P9 | FR-059 | `test_store_operations_exist` | R-059 |
| T170 `SqlRelationClaimStore` resolution | P9 | FR-059 | `test_claim_store_is_usable_or_removed` | R-059 |
| T171 Temporal observations on the normal path | P9 | FR-061, FR-096 | `test_normal_path_emits_a_temporal_observation` | R-061, R-096 |
| T172 build → store → read tests asserting the field list | P9 | FR-060 | `test_build_store_read_asserts_field_list` | R-060 |
| T173 Parity + schema invariants + **conditional** live round trip | P9 | FR-062 | `test_live_roundtrip_is_conditional_and_reports_offline` | R-062a, R-062b |
| T174 Bridge stays claim-only; a test that tries and fails | P10 | FR-058 (`INV-004`) | `test_edge_implies_an_admitted_claim` | R-058 |
| T175 Direction + polarity in properties, not in identity | P10 | FR-063, FR-064, FR-069 | `test_directed_endpoints_are_not_reordered` | R-063, R-064, R-069 |
| T176 n-ary → `HyperEdge`; derived edges name their claim | P10 | FR-065 | `test_derived_binary_edge_names_its_claim` | R-065 |
| T177 entity→value distinguishable | P10 | FR-066 | `test_value_relation_is_distinguishable` | R-066 |
| T178 Hypothesis/evidence view, not `GraphEdge` | P10 | FR-067 | `test_hypothesis_view_is_not_a_graph_edge` | R-067 |
| T179 Bidirectional navigation, incl. the `CANDIDATE`/`ENTITY` hop | P10 | FR-068 | `test_edge_to_source_and_back_reaches_every_edge` | R-068 |
| T180 write → project → rebuild → compare | P10 | FR-068 | `test_rebuild_equals_projection` | R-068 |
| T181 Golden relation corpus: §70's six + §83's sets | P11 | FR-076 | `test_relation_golden_corpus` | R-076 |
| T182 Golden entity-type corpus: §82's surfaces | P11 | FR-075 | `test_entity_type_golden_corpus` | R-075 |
| T183 Active/passive **derivation** test | P11 | FR-077 | `test_derivation_produces_the_shared_logical_id` | R-077 |
| T184 Manifest-driven mutation harness, 18 entries | P11 | FR-078, FR-079 | `test_every_manifest_entry_has_a_failing_named_test` | R-078a, R-078b, R-079 |
| T185 **Prohibition-coverage sweep** | P11 | FR-102 | `test_every_hard_prohibition_has_a_failing_test` | R-102 |
| T186 Replay determinism, second process | P11 | FR-073 | `test_ids_independent_of_order_clock_and_randomness` | R-073 |
| T187 Boundedness + coverage report; live ceilings | P11 | FR-072, FR-080 | `test_ceilings_are_live_and_all_five_metrics_reported` | R-072, R-072a, R-080 |
| T188 Wire into `interpret_warc_capture`; live POST proof | P12 | FR-100 | `test_live_post_produces_signal_candidate_claim_edge` | R-100 |
| T189 Prove `lexical_signals` runs | P12 | FR-100 | `test_lexical_signals_actually_runs` | R-100 |
| T190 Baseline re-run + full failure classification | P12 | FR-081 | `test_baseline_membership_is_unchanged` | R-081, R-081a |
| T191 Benchmarks incl. no O(N²) locality-window cost | P12 | FR-072 | `test_no_global_pair_sweep` | R-072a |
| T192 `ruff check` on all changed paths | P12 | FR-081 | `test_ruff_is_clean` | R-081 |
| T193 `contracts/`, ADR A–L, `quickstart.md` | P12 | FR-082, FR-083 | `test_all_mandated_artefacts_exist` | R-082, R-083 |
| T194 Completion report, 14 sections, 5 categories | P12 | FR-084 | `test_report_has_all_fourteen_mandated_sections` | R-084a, R-084b |

**Counts**: 94 tasks; 0 without an FR; 0 tests without an FR; 0 checklist rows without an FR.
The 3 merged FRs (058, 079, 080) and 1 removed FR (070) are enforced through their absorbing tasks,
which is why the converse direction also has no empty row.

---

## 4. The 19 mis-mapped and 1 weak task→FR citation, verified

The instruction asked me to verify the list and correct it. Each row was checked against the
actual FR body. "should be" is my correction.

| task | cites | actual subject of the task | correct? | should be |
|---|---|---|---|---|
| T011 | FR-020 | build `PredicateSignature` + N1–N6 | **no** — FR-020 is the producer import ban | FR-003 (+FR-004) |
| T012 | FR-021 | add `Polarity` | **no** — FR-021 is `PredicateHypothesis` | FR-015 (+FR-012) |
| T013 | FR-022 | add `RelationParticipant` | **no** — FR-022 is signal→known-operator typing | FR-009 (+FR-008) |
| T015 | FR-082 | the N5 synonym table | **weak, not an error** — FR-082's stop condition genuinely applies ("drop it and let the predicate stay `AMBIGUOUS` rather than guessing"), but **no FR governs the synonym table itself** | *nothing existing* → new clause in the FR-003/FR-004 rewrite + ADR L (FR-083) |
| T016 | FR-030, FR-033, FR-034a | create the `core:`/`value:` pack | **partial** — FR-034a fits; FR-030 over-specifies a 32-item list the task does not deliver; **FR-033 is `TypeHypothesis`, i.e. T017's job** | FR-029, FR-031, FR-034a |
| T017 | FR-029, FR-031 | extend `TypeHypothesis` with competing hypotheses | **no** — both are pack FRs | FR-032 (+FR-033) |
| T018 | FR-032 | make `TypeAssertion` consume the hypotheses | **no** — FR-032 is `TypeHypothesis` | FR-037 (+FR-054) — **not FR-038**, which is about an ontology *miss*, the opposite situation |
| T019 | FR-034, FR-103 | build the mention index | **no** — FR-034 is the type hierarchy; FR-103 does not exist | FR-018 (+FR-019) |
| T020 | FR-103 | inject the resolver into producers | **no** — FR-103 does not exist | FR-016 (+FR-017) |
| T021 | FR-070, FR-095 | define the bounded-neighbourhood scope | **no** — FR-070 is the RDF permission; FR-095 is structural data loss | FR-071 (+FR-072) |
| T022 | FR-012, FR-013 | convert `RelationSignal` to `participants` | **no** — FR-012 is the aspect split, FR-013 the empty surface; **and this task does *not* violate FR-011** (the instruction attributed that to T022; it is T023) | FR-008 (+FR-010) |
| T023 | FR-011 | remove `NEGATION`/`QUANTITY`/`COREFERENCE`, forbid `TEMPORAL` | **no** — FR-011 *mandates* `TEMPORAL`. This is D14 and needs the FR-011 rewrite, not a re-citation | FR-011 (rewritten), FR-012 |
| T024 | FR-014, FR-015 | move negation to `Polarity.denied` | **partial** — FR-015 fits; FR-014 is the observational-basis list | FR-015 (+FR-012) |
| T025 | FR-006 | replace the empty-surface assertion | **no** — FR-006 is the `signal_id` producer-specificity rule | FR-013 (+FR-014) |
| T028 | FR-016, FR-017 | give `PredicateHypothesis` a real normaliser | **no** — both are mention-binding FRs | FR-021 (+FR-003) |
| T030 | FR-008 | surface change ⇒ revision only | **no** — FR-008 is the participants tuple | FR-001 (+FR-007) |
| T045 | FR-057, FR-058 | remove the post-admission re-validation | **no** — FR-057 is `ExecutionResult.material`; FR-058 is the edge-after-claim rule | FR-056 (+FR-092) |
| T046 | FR-059 | make admission gate the store write | **no** — FR-059 is the store seams | FR-092 |
| T059 | FR-079 | add `direction`/`polarity` to edge properties | **no** — FR-079 is the mutation list | FR-069 (+FR-063) |
| T071 | FR-047 | benchmark; prove no O(N²) sweep | **no, and a different class of error** — `FR-047` *exists* but means "the table producer"; the task means brief `§47` | FR-072 (+FR-071) — see §0 |

**Additional citation defects found while verifying** (not in the given list):

- **23 tasks carry no FR at all**: T001, T002, T003, T004, T010, T014, T032, T048, T049, T054, T055,
  T058, T060, T061, T062, T063, T064, T065, T066, T067, T069, T072, T073. Several carry real
  obligations (T004 → FR-083; T054 → FR-059; T058 → `INV-004`/FR-058; T060/T062 → FR-068;
  T063 → FR-076; T064 → FR-075; T065 → FR-073; T066 → FR-078; T067 → FR-072; T073 → FR-083).
- **T032 cites only `SC-002`** — an SC where an FR is required. **T062, T063, T064, T066** cite
  only `§nnn` brief sections. **T049** cites nothing. All are empty in the converse direction.
- **T016's ADR citation is wrong**: it records the controlled-vocabulary decision "as an ADR per
  §100 decision **D/E**", but §100's ADR D is "Raw relation surface is evidence, not logical
  identity" and E is "`PredicateSignature` is structural normalised identity" — neither is the
  vocabulary question (that is ADR A/B). `research.md` Q2 repeats the same "decision D/E" error.
- **T048 records the docstring fix "as an ADR per §100 decision K"** — decision K is
  "Producers remain observation instruments", which has nothing to do with a stage count.
- **T066 cites `§101` as a mutation source.** §101 is `RECOMMENDED FINAL DOMAIN MODEL`.

---

## 5. T4 — `tasks.md` renumbering plan

### 5.1 The phase count, corrected

`input.md` §110 states **12 phases**. `tasks.md` has **13**, because it adds a blocking Phase 0
that the brief's §107 (test baseline) and §108 (acceptance) require but do not enumerate. The
instruction's "10-phase structure" is a third count and is reproducible from neither file.

**Adopted: 13 phases, 0–12, none skipped.** Every phase has ≥1 task.

**The `0→1→2→5` MVP is abolished (D12).** Phase 5 (`PredicateSignature` + candidate identity)
cannot be reached without Phase 4's structural signal contract, and Phase 4 needs Phase 3's
participant shape and Phase 2's vocabulary. The honest MVP is:

> The smallest defensible increment is **Phases 0–5 inclusive** (six phases, no gap). It delivers
> User Stories 1, 2 and the serialisation half of 8, and it is the only increment whose absence
> makes the rest of the substrate *wrong* rather than merely incomplete. No phase in 0–5 may be
> deferred.

### 5.2 The new numbering scheme

`T1xx`…`T9xx` are **sequential across the whole file**; the phase is a mandatory field on every
line, not encoded in the id. Task ids are `^T\d{3}$` — **three digits, no letter suffix**. That
single grammar rule makes the `T007c`/`T011a`/`T012d` phantom class unrepresentable.

| phase | §110 | tasks | count |
|---|---|---|---|
| 0 Baseline | — (added; §107/§108) | T101–T104 | 4 |
| 1 Identity / domain cleanup | §110-1 | T105–T110 | 6 |
| 2 **Atomic entity type vocabulary** | §110-2 | T111–T115 | 5 |
| 3 Type hypothesis + mention binding | §110-3 | T116–T122 | 7 |
| 4 `RelationSignal` structural contract | §110-4 | T123–T129 | 7 |
| 5 `PredicateSignature` + candidate identity | §110-5 | T130–T136 | 7 |
| 6 Producer corrections | §110-6 | T137–T152 | 16 |
| 7 Assembly / conflict semantics | §110-7 | T153–T157 | 5 |
| 8 Real execution lifecycle | §110-8 | T158–T164 | 7 |
| 9 Durable persistence + replay | §110-9 | T165–T173 | 9 |
| 10 Graph projection verification | §110-10 | T174–T180 | 7 |
| 11 Golden corpus + mutation tests | §110-11 | T181–T187 | 7 |
| 12 Benchmark, regression, wiring | §110-12 | T188–T194 | 7 |
| | | **total** | **94** |

**Phase 2 is relabelled and refilled (D15).** `input.md` §110-2 is *"atomic entity type
vocabulary"*; `tasks.md` Phase 2 is `PredicateSignature`/`Polarity`/`RelationParticipant`, all
three of which §110 places in **Phase 5**. Moving them back to Phase 5 is what makes Phase 2
non-empty, and it is the precondition for `FR-101` (§8 extractor expansion) having an owner at
all. The four silently narrowed phases are 2 (mislabelled), 3 (no `TypeAssertion` pipeline), 6 (no
`STRUCTURAL`/`SEMANTIC`/`ATTRIBUTE`/`EVENT` producers), and 11 (no mutation coverage for the §72,
§74, §30 prohibitions). All four are repaired by the task list above.

### 5.3 The five DAG defects, fixed

**(a) The `0→1→2→5` MVP that skips Phase 4 (D12).** Replaced by `0→1→2→3→4→5` — see §5.1.

**(b) T006's backwards edge to T020 (D13).** The old T006 (Phase 1) said *"key logical identity
on the signature (T020)"* where T020 is Phase 3 mention-index wiring. Two fixes, neither of which
reorders phases:

1. The old T006 is **split by responsibility, not by phase**. "Remove `relation_surface` from
   `_logical_material()`" is a Phase 1 concern only to the extent that the identity function's
   declared parameters are dishonest — that is **T109** (the dead `valid_from`/`valid_to` kwargs),
   which needs no signature. The actual re-keying on the signature is **T131**, in Phase 5 where
   the brief puts it and where T130 has built the signature.
2. The test that proves active/passive collapse is **written red in Phase 1 as T110** and turned
   green by T131 in Phase 5. This satisfies the file's own rule (*"tests are written FIRST and MUST
   fail before the implementation exists"*), converts a DAG cycle into a legitimate
   red→green edge, and is the concrete mechanism that keeps `SC-001` reachable. `CHK-DAG-04` in §6
   exists to admit exactly this one edge shape and forbid it everywhere else.

**(c) Phase 4 cannot be committed green (D16).** Re-measured: **7** `RelationSignal(` construction
sites in non-test code — `signal_corpus.py:117`, `execution.py:2824`, `tables.py:165`,
`tables.py:261`, `lexical.py:169`, `links.py:209`, `metadata.py:397` — **confirmed**. But the enum
break is only **2** lines: `assembly.py:219` (`polarity = "denied" if signal.kind is
SignalKind.NEGATION`) and `signal.py:394`. `QUANTITY` and `COREFERENCE` have **zero** references
outside the enum definition. The 7 sites, not the 35 enum references, are the whole problem.

**Fix: split Phase 4 into 4A (additive) and 4B (breaking), and pull the 7-site migration into 4B
as part of the same breaking task.**

- **4A — T123, T124, T125, T126. Purely additive; green at every commit.** `participants` is
  introduced as the canonical field; the two scalars become *derived accessors* computed from it
  and are still accepted as constructor parameters (deprecated, one phase of grace). `Polarity` is
  added with its closed two-member domain. `SignalAspect` is added and new `SignalKind` members are
  added — **nothing is removed in 4A**.
- **4B — T127, T128. Breaking; green at every commit.** T127 mechanically converts all 7
  construction sites from scalar arguments to `participants=(...)` **without changing any
  producer's semantics** — mention-ref resolution is Phase 6's job and needs the index from
  T118/T119. Only after T127 lands does T128 remove the deprecated constructor parameters and the
  two aspect-named enum members.

Because T127 touches every site, the phase boundary is never crossed mid-break and the
*"never bundle a phase boundary"* rule survives: the removal and its migration are **one task**, not
a boundary. This is the substantive correction to D16 — the phase is un-greenable as written
because the *removal* and the *migration* sat in different phases, not because the phase is too big.
`CHK-DAG-05` in §6 encodes this as a general rule: **a breaking task may not have a dependent in a
later phase.**

**(d) `[P]` tasks that share files.** `[P]` means *"different files, no dependency"*, so two `[P]`
tasks touching one file is a self-contradiction. Fixes, with the given list corrected where the
premise was wrong:

| given pair | verdict | fix |
|---|---|---|
| T001↔T004 | **real** — both write `checklists/requirements.md` | split the target: **T101** writes `checklists/baseline.md`, **T104** writes `checklists/requirements.md`. Neither is `[P]`; T104 depends on T101 |
| T048↔T044–T047 | **real** — T044–T047 and T048 all edit `semantic_path/execution.py` | **T158–T164 are ordered; none is `[P]`.** New rule: *at most one task per file per phase* |
| T012↔T013 | **soft** — same directory, different new modules | **T123** owns the `relation_signal_parts` package `__init__` and its export surface; **T124** imports through it. The package-`__init__` write is not `[P]`. The real defect was the three-value `Polarity`, not the files |
| T033–T037 | **wrong as stated** — `links.py`, `tables.py`, `metadata.py`, `lexical.py` are four distinct files and the fifth is new | the real collision is that **`tables.py` holds both `TableExtractor` and `ListExtractor`**, so the table work and the list work are one file. **T143 and T144 are not `[P]`** and are ordered; the other four keep `[P]` |
| T065, T067, T072 | **weak** — separate phases | all three write under `semantic_path/` test modules and the reports directory. **T186, T187, T191 are ordered**; only T192 (`ruff`) stays `[P]` |
| — *(not in the given list)* | additional finding | **T152 and T110** both assert across all producers and both touch the producer test suite. T152 must come strictly after T137–T151. Ordered, not `[P]` |

**(e) The 5 phantom task ids in the checklist.** `T007c`, `T007f`, `T011a`, `T011c`, `T012d` are
the *only* verification for: the graph-projection invariant (`INV-004`/FR-058), the `ENT-`/`RES-`
ban (FR-019), the no-placeholder-participant rule (FR-094), the `document:current` fallback
(FR-094), and **the entire mutation apparatus** (§96, §95, §97, §98, §99 — checklist rows D3, D9,
E2, F3, H11). All five are re-homed on real tasks:

| phantom | checklist rows it gates | real owner |
|---|---|---|
| `T007c` | A3, D4, D5 | T174 (P10) and T145 (P6) |
| `T007f` | A7, D1, D2 | T152 (P6) |
| `T011a` | A3 | T174 (P10) |
| `T011c` | A6 | T180 (P10) |
| `T012d` | D3, D9, E2, F3, H11 | T185 (P11) — the new prohibition-coverage sweep, FR-102 |

### 5.4 The 12 synthetic mention-ref prefixes, verified

`T038`'s checkpoint says *"grep for the 12 fabrication prefixes"*. Verified from the code — there
are exactly 12: `surface:`, `anchor:`, `href:`, `header:`, `cell:`, `document:`, `meta:`, `byline:`,
`attribute:`, `value:`, `jsonld:`, `jsonld-value:`. Sites: `lexical.py:164,165,276,289`;
`tables.py:109`; `links.py:282,283`; `metadata.py:237,238,262,263,289,290,363,364` — of which four
are `[:64]` truncations (`metadata.py:238,263,290,364`) and two are the `document:current`
fallback (`metadata.py:237,262`). The count in `tasks.md` is correct; the *task* that checks it is
a phantom.

### 5.5 The dependency DAG, spelled out

```
P0  T101 ──► T102, T103, T104
P1  T105, T106, T107, T108, T109  (independent, all [P])
    T110  writes the RED identity test
P2  T111 ──► T112, T113 ──► T114 ──► T115
P3  T116 (needs T111) ; T117 (needs T116) ; T118 (independent)
    T119 (needs T118) ; T120 (needs T116) ; T121 (needs T116, T119) ; T122 (needs T117, T119)
P4  T123, T124, T125, T126          (4A: additive, all [P])
    T127 (needs T123) ──► T128 (needs T125, T127)
    T129 (needs T123, T125, T127)
P5  T130 ──► T131 ──► T132 ──► T133, T134, T135
    T136 (needs T130, T133)
    *** T110 turns GREEN here — the edge that makes SC-001 reachable ***
P6  T137 ──► T138, T140, T141, T142, T143, T144, T145, T146, T147, T148, T149, T150
    T139 (needs T137) ; T151 (needs T138…T150) ──► T152 (needs T151, T119)
P7  T153 ──► T154, T155 ──► T156 ──► T157 (needs T136, T155)
P8  T158 ──► T159 ──► T160 ──► T161 ──► T162 ──► T163 ──► T164
P9  T165 ──► T166, T167, T168 ; T169 ──► T170, T171, T172 ; T173 (needs T165)
P10 T174 (needs T169) ; T175 ──► T176, T177, T178 ; T179 (needs T175) ──► T180
P11 T181, T182, T183, T186 ([P]) ; T184 (needs T129, T152, T153) ──► T185
    T187 (needs T137, T143, T145)
P12 T188 (needs T163, T184) ──► T189 ──► T190 ──► T191, T193 ──► T194
```

Two invariants the checker must assert: every `needs:` edge points to a strictly lower-or-equal
phase (`CHK-DAG-02`), and every task is reachable from Phase 0 (`CHK-DAG-03`).

---

## 6. T5 — The specification-reference schema the machine checker must enforce

The checker consumes `spec.md`, `tasks.md` and `checklists/requirements.md` and must fail the
build on any violation.

### 6.1 Lexical grammar (hard)

| Token | Regex | Note |
|---|---|---|
| FR | `^FR-(\d{3})([a-z])?$` | the optional single lowercase suffix is **required** by `FR-034a` and `FR-039a`; a checker written `^FR-\d{3}$` will reject them |
| INV | `^INV-(\d{3})$` | |
| SC | `^SC-(\d{3})$` | |
| ADR | `^ADR-([A-L])$` | extended to `L` by the FR-083 rewrite |
| Task | `^T(\d{3})$` | **three digits, no suffix** — makes `T007c` unrepresentable |
| Checklist | `^R-(\d{3})([abc])?$` | new space; `legacy:` column carries the old `A1…J14` ids |
| Brief section | `^§(\d{1,3})(\.\d{1,2})?([A-Za-z])?$` | covers `§4.1`, `§100`, `§1B` |
| Phase | `^P(\d{1,2})$` | must be 0–12 |
| Story | `^US(\d)$` | 1–9 |
| Mutation | `^MUT-(\d{3})$` | the §93 manifest, 18 entries |
| Test nodeid | `^(test_[a-z0-9_]+\|apps/[a-z-]+/tests/\S+)$` | |

### 6.2 Semantic rules and check ids

| id | rule | fails today on |
|---|---|---|
| `CHK-FR-01` | An FR is **defined** in exactly one `#### ` block of `spec.md`. | a duplicate definition |
| `CHK-FR-02` | Every defined FR is cited by **≥1** task line. | the 52-FR defect |
| `CHK-FR-03` | Every FR **cited** by a task, checklist row or SC is **defined**. | `FR-103` |
| `CHK-FR-04` | Every task line cites **≥1** FR. | the 23 uncited tasks |
| `CHK-FR-05` | Every FR has **exactly one** semantic owner task in the normative matrix. | two owners, or zero |
| `CHK-FR-06` | Every FR has **≥1** acceptance test, and the test name is a resolvable nodeid. | `SC-001` having no enabler |
| `CHK-FR-07` | Every FR has **≥1** checklist row. | the checklist's zero-FR coverage (D5) |
| `CHK-FR-08` | Every checklist row cites **≥1** FR. | the 82 rows that cite none |
| `CHK-FR-09` | Every deleted or merged FR slot carries a tombstone naming its destination. | a dangling id |
| `CHK-FR-10` | Every tombstoned id has **≥1** citing task pointing at the absorbing FR/INV. | FR-058 enforced by nothing |
| `CHK-FR-11` | No id in the 001–102 range is undefined and untombstoned. | a hole that is not a decision |
| `CHK-FR-12` | Every `MUST` in an FR body is reachable from ≥1 acceptance test. | FR-055's stage order, FR-072's five metrics |
| `CHK-FR-13` | No FR contains a `SHOULD` without a paired `MUST` covering the same subject. | FR-012, FR-039 |
| `CHK-FR-14` | Every FR marked `REMOVE` or `MERGE` names a destination that exists. | a removal into nowhere |
| `CHK-TY-01` | An FR-id token and a brief-section token are **distinguishable by shape**; a citation that *means* `§N` but is *written* `FR-0N` is a **type error**, not a miss. | **`T071`'s `FR-047` for `§47`** — the second `FR-103`-class error, which a naive existence check passes |
| `CHK-TY-02` | A `§N` citation resolves to a heading in `input.md`. | D10's "`§N` string-match passes citation without content" |
| `CHK-TY-03` | A `§N` citation whose section is not a *requirement* section (e.g. §100, §101, §109) may not be the source of a mutation or a task obligation. | `T066`'s `§101` |
| `CHK-AR-01` | Every ADR referenced exists in `specs/021-.../adr/`. | `T048`'s "ADR per decision K" for a docstring fix |
| `CHK-AR-02` | The ADR set is exactly `A…L` and every letter has a file. | K5: no slot for the synonym table |
| `CHK-TK-01` | A task id is `^T\d{3}$` and within `T101…T194`. | the 5 phantoms |
| `CHK-TK-02` | Every task cites ≥1 FR and ≥1 test name. | `T049`, `T054`, `T032` |
| `CHK-TK-03` | Every task's phase is 0–12. | a phase-13 task |
| `CHK-TK-04` | Every phase 0–12 has ≥1 task. | a skipped phase (D12) |
| `CHK-TK-05` | Every task declares a `files:` set; two `[P]` tasks in the same phase MUST have disjoint `files:` sets. | the `[P]` collisions in §5.3(d) |
| `CHK-DAG-01` | Every `needs:` target exists. | — |
| `CHK-DAG-02` | Every `needs:` edge points to a strictly lower-or-equal phase. | **D13's `T006→T020`** |
| `CHK-DAG-03` | Every task is reachable from a Phase 0 task. | an orphan |
| `CHK-DAG-04` | No task declares `needs:` on a later phase, *except* an explicitly-declared `red→green:` test edge. | reintroducing a cycle |
| `CHK-DAG-05` | No breaking task (one that removes a field, member or parameter) has a dependent in a later phase. | **D16's un-greenable Phase 4** |
| `CHK-CL-01` | Every checklist row has a populated FR column. | D5 |
| `CHK-CL-02` | Every row's `Method` ∈ {`T`,`I`,`M`,`B`,`P`}. | — |
| `CHK-CL-03` | A row with `Method = M` names a `MUT-nnn` in the manifest and a test that fails when the mutation is applied. | the 6 phantom-gated mutations |
| `CHK-CL-04` | No row cites a task id absent from the task file. | `T007c`, `T007f`, `T011a`, `T011c`, `T012d` |
| `CHK-CL-05` | The checklist has ≥1 row per normative FR and the count is stated in the file header. | an unstated count |
| `CHK-SC-01` | Every SC cites ≥1 FR. | — |
| `CHK-SC-02` | Every normative FR is cited by ≥1 SC. | the 32 uncovered §108 bullets |
| `CHK-SC-03` | Every SC is either cited by ≥1 §108 bullet or carries an explicit `out-of-scope:` reason. | a criterion nobody asked for |
| `CHK-SC-04` | Every numeric count asserted in an SC equals the count in its source. | **`SC-015`'s "≥ 20" vs §93's 18; `FR-079`'s "Four" vs six** |
| `CHK-MU-01` | The `MUT-` manifest has exactly the fields enumerated in its source section, and the manifest count equals the number of entries. | FR-078/FR-079 |
| `CHK-MU-02` | Every brief hard prohibition in the FR-102 list has ≥1 `MUT-` entry. | **D9's three unenforced prohibitions** |
| `CHK-MU-03` | Every `MUT-` entry is reachable from a task. | — |
| `CHK-CODE-01` | An inline `FR-0xx` citation in `apps/**` is checked against the *repaired* set and reported `unreconciled` unless it resolves to an FR whose text the citing line supports. | the 1006 citations (D11) |
| `CHK-CODE-02` | `apps/**` may not cite a tombstoned FR id without a comment naming the destination. | a reader following a code comment |
| `CHK-VER-01` | A `verified only offline` claim names an FR that permits offline-only verification. | FR-062's conditional |
| `CHK-VER-02` | A `verified` (not `verified only offline`) claim for any DB-touching FR requires a live-connection record. | the "green while offline" lie |
| `CHK-PHASE-01` | §110's 12 phase titles appear verbatim as the phase headers, and the added Phase 0 is declared as an addition. | **D15's 4 narrowed phases** |
| `CHK-PHASE-02` | Every brief section cited by an FR is either mapped to a phase or recorded out-of-scope with a reason. | **D7: §8 appears zero times in every artefact** |

### 6.3 What the checker must *not* do

- It must **not** treat "the cited FR exists" as "the citation is correct". `T071`→`FR-047` passes
  an existence check and is wrong. `CHK-TY-01` exists solely for this.
- It must **not** accept a `§N` citation on a string match alone (D10).
- It must **not** infer coverage from a task's prose. `T063` covers `FR-076` in substance and cites
  nothing; a text-similarity heuristic would make the 52-FR number unstable in both directions.
  Coverage is a declared field or it is not coverage.

---

## 7. T6 — §108 coverage (48 bullets) and §114 coverage (14 sections)

### 7.1 §108's 48 acceptance bullets → SC

| # | bullet | SC | status |
|---|---|---|---|
| | **Entity substrate** | | |
| 1 | foundational atomic vocabulary exists | **SC-017** | new |
| 2 | entity/value types are distinct | **SC-017** | new |
| 3 | type hypotheses are first-class | **SC-018** | new |
| 4 | type assertions remain durable | **SC-019** | new |
| 5 | multiple type hypotheses are preserved | **SC-018** | new |
| 6 | unknown types are preserved | **SC-020** | new |
| 7 | external mappings are explicit | **SC-021** | new |
| 8 | ontology never gates extraction | **SC-022** | new |
| 9 | mention/entity separation preserved | **SC-023** | new |
| | **Relation substrate** | | |
| 10 | RelationSignal has explicit structural contract | **SC-024** | new |
| 11 | mandatory signal kinds exist | **SC-025** | new |
| 12 | real mention references are used | SC-004 | **existing** |
| 13 | n-ary relation is native | SC-003 | **existing** |
| 14 | polarity is explicit | **SC-026** | new |
| 15 | predicate signature exists | **SC-027** | new |
| 16 | raw surface is evidence, not logical identity | **SC-028** | new |
| 17 | active/passive can share logical identity | SC-001 | **existing** |
| 18 | multiple producers can corroborate one candidate | SC-005 | **existing** |
| 19 | distinct relations on same endpoints do not merge | SC-007 | **existing** |
| 20 | semantic conflicts do not use majority vote | SC-006 | **existing** |
| 21 | unknown predicates survive | SC-002 | **existing** |
| 22 | alternatives survive | **SC-029** | new |
| 23 | no producer emits claim/edge | SC-011 | **existing** |
| | **Lifecycle** | | |
| 24 | Candidate exists before material | **SC-030** | new |
| 25 | Material exists before validation | **SC-030** | new |
| 26 | Validation exists before admission | **SC-030** | new |
| 27 | RelationClaim exists only after admission | **SC-030** | new |
| 28 | GraphEdge exists only after RelationClaim | **SC-031** | new |
| | **Persistence** | | |
| 29 | signals persist | **SC-032** | new |
| 30 | candidates persist | **SC-032** | new |
| 31 | predicate hypotheses are reconstructible | SC-008 | **existing** |
| 32 | temporal observations persist | SC-009 | **existing** |
| 33 | round-trip works | SC-008 | **existing** |
| 34 | replay works | SC-010 | **existing** |
| | **Projection** | | |
| 35 | direction preserved | SC-014 | **existing** |
| 36 | n-ary preserved | SC-003 | **existing** |
| 37 | attributes distinguished from entity-to-entity edges | **SC-033** | new |
| 38 | edge points back to claim | SC-013 | **existing** |
| 39 | graph remains rebuildable | **SC-034** | new |
| | **Determinism** | | |
| 40 | two independent runs identical | SC-010 | **existing** |
| 41 | order of producers does not alter IDs | **SC-035** | new |
| 42 | no clock dependency | **SC-035** | new |
| 43 | no random dependency | **SC-035** | new |
| 44 | no dict-order dependency | **SC-035** | new |
| | **Boundedness** | | |
| 45 | no O(N²) global mention sweep | **SC-036** | new |
| 46 | every producer names neighbourhood | **SC-037** | new |
| 47 | hard ceilings are machine checked | **SC-038** | new |
| 48 | cost metrics are reported | **SC-038** | new |

**Result: 48 bullets → 16 covered by an existing SC, 32 covered by 22 new SCs
(SC-017…SC-038), 0 declared out of scope.** No §108 bullet is "out of scope with reason": every one
is a real acceptance criterion, and the correct fix for an uncovered bullet is a criterion, not an
exclusion. This is also the honest reading of the user's rule — the 29/47 figure understated the
gap and mis-scoped it.

### 7.2 The 22 new success criteria

- **SC-017** — A versioned foundational type pack exists, its shipped manifest matches the artefact
  byte for byte, and a `value:*` type is never representable as an entity. *(FR-029, FR-030, FR-031)*
- **SC-018** — `TypeHypothesis` is first-class; a mention holds ≥1 retained hypothesis; for each of
  `Apple`, `Amazon`, `Jordan`, `Washington`, `Mercury`, ≥2 are retained and none is silently
  selected. *(FR-032, FR-033)*
- **SC-019** — `TypeAssertion` is durable; a later `INFERRED` status is a new revision and every
  prior state is still retrievable. *(FR-037)*
- **SC-020** — A type the `core:` pack has never heard of is retained as `UNKNOWN`; zero mentions
  are dropped for an ontology miss. *(FR-038, `INV-003`)*
- **SC-021** — An external structured statement yields a `TypeSignal` with `mapping_candidates` and
  a `TypeMapping` record, and **not** a `TypeAssertion`. *(FR-035, FR-036)*
- **SC-022** — No extraction path can be disabled by an ontology miss; §97's
  `if core pack does not know type: continue` fails a named test. *(FR-074, `INV-003`)*
- **SC-023** — `mention.kind != entity.type` holds for every mention; zero `ENT-`/`RES-` literals
  exist in producer code. *(`INV-001`, FR-019)*
- **SC-024** — Every field named in FR-010 is present and typed; zero load-bearing dimensions are
  JSONB; `extra` carries only producer-specific metadata. *(FR-008, FR-010)*
- **SC-025** — Every channel in FR-040's list is either implemented or carries an explicit
  `UNSUPPORTED` marker with a reason; `SignalKind` contains no aspect-named member. *(FR-011,
  FR-012, FR-040)*
- **SC-026** — `polarity` is a required field and a durable column; a denied acquisition yields a
  `DENIED` candidate with its signature intact and **zero** positive candidates. *(FR-015)*
- **SC-027** — A `PredicateSignature` exists, is content-keyed, is not a `RelationRef`, and is
  stored in its own columns rather than as a digest. *(FR-003, FR-087)*
- **SC-028** — Changing `relation_surface` alone changes `candidate_id` and **not**
  `logical_candidate_id`; changing a producer, a capture or a confidence changes neither. *(FR-001)*
- **SC-029** — Two regimes over one signature yield **one** candidate carrying alternatives with
  nothing overwritten; two differing signatures yield two candidates. *(FR-028)*
- **SC-030** — `Candidate` exists before `ClaimMaterial`, which exists before `Validation`, which
  exists before `Admission`, which exists before `RelationClaim` — asserted by four ordered
  timestamps in one run, not by four separate tests. *(FR-056, FR-057, FR-092)*
- **SC-031** — No `GraphEdge`/`HyperEdge` exists for a non-claim; the bridge has no overload; §99's
  producer-constructs-`GraphEdge` mutation fails. *(`INV-004`, FR-058, FR-020)*
- **SC-032** — `RelationSignal` and `RelationCandidate` each have a working `write` / `get` /
  `by_tenant` / `by_logical_id` round trip against a real (in-memory or live) seam. *(FR-059,
  FR-060)*
- **SC-033** — An entity→value relation is distinguishable from entity→entity in both the claim and
  the projection; `Person → email → EmailAddress` never becomes a normal entity edge. *(FR-066)*
- **SC-034** — Write claims → project → rebuild via `RebuildableGraphStore` → compare, over
  `InMemoryGraphStore`, with zero equality. *(FR-068)*
- **SC-035** — Removing producer order, the clock, randomness and dict iteration order
  **individually** leaves every signal, candidate, material, claim and edge id identical.
  *(FR-073, FR-085)*
- **SC-036** — §72's all-mentions × all-mentions mutation fails its named test in every extraction
  path. *(FR-072)*
- **SC-037** — Every signal states a neighbourhood class from §46's 11-item list, and the class is
  a typed field, not a substring in a `precision` string. *(FR-071)*
- **SC-038** — `max_pairs_considered` is a live ceiling that a real violation exceeds, and all five
  §47 metrics are reported by every producer. *(FR-072, FR-080, FR-093)*

**Total SCs after repair: 38** (16 existing + 22 new). The two existing SCs that assert wrong counts
must be corrected in place: `SC-015` becomes *"every entry in the §93 mutation manifest, each with a
named failing test"* (18, not "≥ 20"), and `SC-016` is retained but extended to name the 22
never-executed tests.

### 7.3 §114's 14 mandated report sections → FR or task

Every section is owned by the **FR-084 rewrite** (§2.4) and produced by task **T194**. The middle
column names the task that *supplies the content*, so a section cannot be empty in the report.

| # | §114 section | owner | content supplied by | checklist |
|---|---|---|---|---|
| 1 | changed-file manifest | FR-084 | T194 (from `git diff --stat` against `0056665`) | R-084a |
| 2 | architecture summary | FR-084 | T194 (must show the §101 model in production code) | R-084a, R-100 |
| 3 | domain model changes | FR-084 | T106, T130, T136 (the nine changed/new types) | R-084a |
| 4 | migration summary | FR-084 | T165, T166, T167, T168 (add **and drop**; `020` unedited) | R-084a, R-097a |
| 5 | producer summary | FR-084 | T138–T151 plus the FR-040 completeness marker | R-084a, R-040 |
| 6 | identity changes | FR-084 | T105, T109, T131, T133, T134 | R-084a, R-001, R-002 |
| 7 | execution path before/after | FR-084 | T158–T164 (the partial order, with `REGIME` resolved) | R-084a, R-055a, R-055b |
| 8 | graph projection semantics | FR-084 | T174–T180 | R-084a, R-063…R-069 |
| 9 | corpus coverage | FR-084 | T181, T182, T183 (the §70/§82/§83/§109 sets) | R-084a, R-075, R-076, R-077 |
| 10 | mutation-test results | FR-084 | T184, T185 (all 18 manifest entries + the FR-102 sweep) | R-084a, R-078a, R-102 |
| 11 | replay/determinism results | FR-084 | T186 (second-process replay) | R-084a, R-073 |
| 12 | benchmark results | FR-084 | T187, T191 (metrics, ceilings, locality-window cost) | R-084a, R-072, R-072a |
| 13 | complete test matrix | FR-084 | T190 (baseline membership, new/fixed/flaky, and the 22 skipped) | R-084a, R-081, R-081a |
| 14 | explicit remaining debt | FR-084 | T194 (every FR-082 stop condition, listed as `deferred` with its reason) | R-084a, R-082 |

The five status categories `implemented` / `verified` / `verified only offline` /
`known limitation` / `deferred` are a **classification applied inside every one of the 14
sections**, not a 15th section. Rows that are `verified only offline` must cite FR-061/FR-062,
which are the only two FRs that permit offline-only verification (see `CHK-VER-01`).

---

## 8. What this triage does *not* decide, and the three things blocking the rebuild

Recorded so the next agent does not re-derive them and no one treats them as settled.

1. **FR-003 / FR-004 content (A2/A4b).** §1.2 states the blocking interface: if the signature's
   `role_bindings` are not part of identity *and* are voice-normalised, `SC-001` stays
   unreachable. `T130` is reserved, not authored.
2. **FR-035 / FR-036 ownership arbitration.** Claimed by both A2/A4b and A5. Phase 2 cannot start
   until one of them stands down. This is the only *scheduling* blocker in the plan.
3. **The `MENTION-` vs `MN-` prefix and the three `RelationParticipant` field lists.** Owned by
   the identity/types agents. The triage carries them as `[INTERFACE]` notes on FR-018 and FR-009
   so they are not lost, and `CHK-CODE-01` will surface the disagreement at the first code citation.

Two open decisions this job created deliberately rather than silently:

- **`REGIME`'s position in the lifecycle** (FR-055 rewrite, §2.4). Three sources disagree; I fixed
  only the precedence constraints all three agree on and made the position an explicit open
  decision for `plan.md`. Asserting a fourth order would repeat the defect.
- **Whether to renumber** (§2.3). I decided no. If the rebuild team prefers dense 001–100, the
  cost is the 1006 code citations plus a second reconciliation pass, and `CHK-FR-11` must then be
  replaced by a range check.

---

*End of A6 FR triage. No file in the repository was modified by this job.*
