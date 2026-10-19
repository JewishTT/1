# Contract 06 — Resolution Proposal and Decision

**Feature**: `032-global-upgrade-execution`
**Governs**: how a proposed identity or conflict resolution becomes a recorded decision.
**Enforces**: FR-028, FR-033, FR-034; blueprint §5.4, §6.5.

---

## Why this contract exists

The blueprint draws a line that most systems blur: *"Resolvers propose; admission decides."* A
similarity score, a resolver strategy and an analyst's adjudication all produce **proposals**. Only
the admission path produces a **decision**, and only a decision changes canonical identity or a
conflict's status.

Keeping the two apart is what makes an identity change auditable, reversible and attributable.

---

## Shape — `ResolutionProposal`

```text
ResolutionProposal
├── proposal_id               REQUIRED
├── tenant_id                 REQUIRED
├── subject                   REQUIRED   identity | conflict
├── subject_ref               REQUIRED   the candidate pair / cluster / conflict
├── proposed_outcome          REQUIRED   merge | split | admit | defer | reject | reopen |
│                                        provisional_value | abstain
├── alternatives[]            REQUIRED   every competing option, with its support
├── supporting_evidence[]     REQUIRED   claim refs + spans
├── refuting_evidence[]       REQUIRED   claim refs + spans — may be empty, must be present
├── strategy                  REQUIRED   authority_weighted | temporal_applicability |
│                                        lineage_voting | ontology_constraint |
│                                        source_of_record | analyst_adjudication | abstain
├── strategy_version          REQUIRED
├── component_vector          REQUIRED   the dimensions the strategy used, separately
├── assumptions[]             OPTIONAL   what the strategy took for granted
├── sensitivity               OPTIONAL   how the outcome changes under a stated perturbation
├── policy_ref                REQUIRED
├── uncertainty               REQUIRED   structured, not a single scalar
└── produced_by               REQUIRED   operator ref + fingerprint
```

## Shape — `ResolutionDecision`

```text
ResolutionDecision
├── decision_id               REQUIRED
├── tenant_id                 REQUIRED
├── proposal_refs[]           REQUIRED   one or more; a decision cites what it considered
├── subject_ref               REQUIRED
├── outcome                   REQUIRED   the proposal outcome actually committed
├── actor                     REQUIRED   operator id | system policy id | analyst id
├── rationale                 REQUIRED   why this outcome, in terms a reviewer can audit
├── conflict_snapshot_ref     OPTIONAL   for a conflict decision
├── expected_context_revision REQUIRED   the optimistic-concurrency guard
├── committed_revision        REQUIRED   the revision this decision produced
├── previous_decision_ref     OPTIONAL   so a correction chains rather than overwrites
└── created_at                REQUIRED
```

---

## Normative rules

### R1 — Proposals never commit

A proposal has no side effect on canonical identity, claim status or conflict status. Only the
admission path commits, and only by appending a `ResolutionDecision`.

### R2 — Decisions are append-only

A decision is never edited or deleted. A correction is a new decision whose `previous_decision_ref`
points at the one it supersedes, and both remain readable.

### R3 — Every decision cites its proposals and its rationale

A decision with no cited proposal is an unexplained act. A decision with no rationale cannot be
reviewed. Both are contract violations.

### R4 — Optimistic concurrency

`expected_context_revision` guards against a decision landing on stale state. A mismatch rejects the
decision and returns the current revision; it never silently rebases.

### R5 — The score is never the decision

No strategy may commit an outcome from a similarity score, a centrality measure or a graph-proximity
value alone. Those may order candidates, and the decision must cite the strategy plus the evidence
that justifies it (FR-027, SC-006).

### R6 — A split does not rewrite history

When a false merge is corrected, the prior claims keep the interpretation under which they were
created. The current grouping changes; the projections are regenerated through explicit
supersession; nothing is rewritten (FR-028, US5-AS3).

### R7 — Abstention is a decision

`abstain` is a legitimate outcome. It records that the evidence was insufficient, keeps the conflict
in `BOTH`, and opens a discriminating-evidence obligation.

### R8 — Analyst adjudication carries authority

An analyst decision records the actor, the rationale, the conflict or candidate snapshot and the
expected revision. It is not a comment; it is a decision with the same append-only discipline.

---

## Prohibitions

- A resolver writing to the identity store.
- A decision without a proposal reference.
- Editing or deleting a prior decision.
- Committing a merge from a score with no evidentiary rationale.
- A provisional winner that removes the alternatives from storage.

---

## Tests

| Test | Asserts |
|---|---|
| `tests/integration/test_resolution_decision_append_only.py` | R2 |
| `tests/integration/test_admission_is_only_committer.py` | R1 |
| `tests/golden/test_false_merge_correction.py` | R6 |
| `tests/contract/test_resolution_decision.py::test_expected_revision_mismatch_rejected` | R4 |
| `tests/golden/conflict_corpus/test_abstain_opens_obligation.py` | R7 |
