# Data Model — 025 **v2**

**Feature**: `025-context-reality-approximation-engine`
**Baseline**: [input.md](input.md) §5–§16A, §39–§40, Appendix G, Y, Z
**Decisions**: [ADR-0028](../../../docs/adr/0028-context-definition-identity-and-placement.md)

Phase 1 output. PostgreSQL is the sole authority (ADR-0027). No new store. **SQLite is not
used for persistence tests** (§47.1, V.16).

---

## 1. Identity namespaces (Appendix G.1, v2)

| Prefix | Object | Note |
|---|---|---|
| `CXD-` | `ContextDefinition` | **new namespace** (ADR-0028; v2 §5.1 still says `CXI-`) |
| `CXI-` | `InvestigationContext` / `ContextDefinition` per §5.1 text | preserved as written; see ADR-0028 |
| `BRN-` | `ContextBranch` | **new in v2** |
| `REV-` | revision state hash | separate from revision number |
| `CXC-` `OVL-` `RST-` `CMP-` `GLU-` | cell, overlap (pair/triple), restriction, compatibility, gluing | |
| `VAR-` `STE-` `MOD-` | state variable, estimate, observation model | `MOD-` newly declared |
| `HSP-` `LHYP-` `HYP-` | hypothesis space, logical hypothesis, hypothesis revision | `HSP-` new |
| `ASM-` `EXP-` `PRD-` `PRO-` `DGT-` `DLP-` | assumption, explanation, prediction, **prediction outcome**, discriminating test, dialectical pair | `PRD-`/`PRO-` newly declared |
| `CTR-` | contradiction | |
| `OBST-` | obstruction | **fixed in v2** — `OBS-` is Observation only. Closes the v1 collision flagged in `W0-04` |
| `OBS-` | observation | owned by substrate |
| `EDG-` | evidence dependency group | new |
| `CQA-` | coverage-qualified absence | new |
| `ANL-` | analyst assertion | new |
| `DEC-` | decision / analyst decision | |
| `RPF-` | reasoning profile | new |
| `RET-` | retention policy | new |
| `SAT-` `OBL-` `ACT-` `RUN-` `MF-` `PF-` | saturation, obligation, action, reasoning run, fingerprints | |
| `REG-` `TRN-` `TDA-` `CAU-` | regime, transition, topological feature, causal model | |
| `QRY-` `SR-` `WLS-` `EVID-` `GAP-` | query, semantic regime, worldline snapshot, evidence item, evidence gap | newly declared / substrate |
| `ENT-` `REL-` | entity, relation | substrate, listed for reference |

All digests 32 lowercase hex, content-addressed. Prefix length is not a semantic commitment.

---

## 2. v2 entity additions and their storage consequences

| Object | New table | Non-obvious storage requirement |
|---|---|---|
| `ContextBranch` | `context_branch` | `(context_id, branch_id, revision)` becomes the revision key — **all revision uniqueness constraints change** (§6.1.7, T025-031) |
| revision manifest | `revision_manifest`, `artifact_store` | revisions store artifact **digests**, not rows; GC only from non-expired, non-held revisions (§39.4) |
| `EvidenceDependencyGroup` | `evidence_dependency_group` | derived deterministically from lineage; assignments versioned. Index `(context_id, dependency_group)` |
| `HypothesisSpace` | `hypothesis_space` | stores `exhaustive` flag + residual hypothesis ref; `residual_mass` is a first-class queryable |
| `CoverageQualifiedAbsence` | `coverage_absence` | `admissibility` is **non-nullable enum**; `INFORMATIONAL_ONLY` is the safe default and may not be defaulted *up* to `NEGATIVE_EVIDENCE` |
| `PredictionOutcome` | `prediction_outcome` | append-only per revision; feeds realised gain and calibration cohorts |
| `ReasoningProfile` | `reasoning_profile` | versioned + fingerprinted; referenced by every revision |
| `RetentionPolicy` | `retention_policy` | `legal_hold` scope must be queryable; hold blocks expiry |
| `InferencePolicy` | `inference_policy` | sensitive classes gate the compiler and generators (§49.3) |
| `AnalystAssertion` | `analyst_assertion` | enters as observation kind `ANALYST_INPUT`; subject to independence accounting |
| `AnalystDecision` | reuses `context_decision` | adds `principal`, `justification` (required), `OVERRIDE_STATUS` kind |
| `ReplayReport` | `replay_report` | `REPLAY_DEGRADED` state with unreadable-input list |

---

## 3. Column types that must be right at migration time

| Concern | Rule |
|---|---|
| `truth_state` | two `boolean` columns on **Proposition**, never an enum. Property test asserts no path maps `(true,true) → true` (FR-025-088) |
| `exhaustive` | tri-state boolean (`true`/`false`/`UNKNOWN`), not nullable-with-default |
| `numeric_mode` | enum on `StateVariable` and every operator; drives canonicalisation (Appendix G.2) |
| `estimate` | `point`/`interval`/`distribution`/`feasible_set` nullable siblings + `epistemic_status` incl. `INCONSISTENT`. A latent estimate can never read as observed |
| `gain` | `tier` enum + nullable `value` + `includes_residual_hypothesis`. Tier is mandatory; a value without a tier is invalid |
| `admissibility` | non-nullable enum; `INFORMATIONAL_ONLY` is the only legal default |
| `n_eff` | stored alongside the raw count, never instead of it |
| `causal_evaluation` | three separately nullable stage columns/rows. No `causal_confidence` column exists (§27.2) |
| `seed` | column on `reasoning_run` and inside `parameter_fingerprint`; never ambient |
| `temporal relation` | non-empty **subset of the 13 Allen relations**, not a single enum (Appendix G.1/§24.2) |
| `status` vs `trend` | hypothesis `status` is a machine field; `trend` is **derived** and must not be writable directly |
| timestamps | `created_at` excluded from identity; the six authoritative axes never substituted |

---

## 4. Mandatory indexes (§40, v2)

```text
(context_id, branch_id, revision)
(context_id, status)
(context_id, obligation_lifecycle, readiness)
(context_id, hypothesis_status)
(context_id, space_id)
(context_id, contradiction_state)
(context_id, temporal_start, temporal_end)
(context_id, entity_ref)
(context_id, source_ref)
(context_id, dependency_group)
(context_id, method_fingerprint)
(context_id, state_hash)
```

Added for v2 access patterns:

```text
(hypothesis_space_id, hypothesis_id)          -- exclusivity groups, H_OTHER mass
(prediction_id, evaluated_at_revision)        -- outcome history
(absence_id, admissibility)                   -- informational-only sweep
(branch_id, forked_from_revision)             -- lineage of scenarios
(artifact_digest)                             -- manifest resolution + GC reachability
(tenant_id, cache_key)                        -- §30.5, fail closed
(legal_hold_scope)                            -- retention drill
```

Every tenant-scoped table has tenant-aware indexes. Cross-tenant reads fail closed —
**including cache reads**.

---

## 5. Append-only vs erasure

Append-only is a *logical* property (§39.3). Physical erasure is possible without breaking
integrity:

```text
payload (encrypted per class/subject key)
        │  erase
        ▼
key destroyed  ──►  tombstone {id, digest, class, erasure decision ref, timestamp}
        │
        ▼
manifest + digests survive  ──►  dependents marked INPUT_ERASED
        │
        ▼
replay  ──►  REPLAY_DEGRADED + list of unreadable inputs
```

GC removes only artifacts unreachable from any non-expired revision and not under legal hold.

---

## 6. Six time axes and the derived algebra

`fetched_at`, `observed_at`, `published_at`, `valid_from`, `valid_to`, `known_from` remain
authoritative. v2 adds the **full 13-relation Allen algebra** with disjunctive relation
values (`allen.py`, T025-140): a relation is a non-empty subset of the 13; the full set is
`UNKNOWN`; operations `converse`/`intersection`/`composition` are table-driven and
deterministic. No seventh authoritative axis. This is a migration constraint, not only a
runtime one — the temporal columns must support interval semantics.

---

## 7. Appendix Y coverage is machine-checkable

`T025-153` is a CI gate: any `FR-025-001…088` without a task reference **and** a test
reference fails the build. Appendix Y is the maintained source for that mapping; this
data model is the schema side of it.