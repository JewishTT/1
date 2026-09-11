# Resolution → Admission Contract

Consumes the calibrated admission pipeline (Spec FR-012/013/015/016, T035/T082–T087). Domain-neutral; the specifics of model internals (clustering algorithms, ML rankers) never leak into admission decisions or events.

## Pipeline (fixed order — no collective resolution after admission; TDA never replaces resolution identity evidence)

```text
Mention
   ↓
Candidate
   ↓
Candidate Graph
   ↓
Blocking (multi-strategy, union candidate pairs, no O(N²))
   ↓
Pairwise Resolution
   ↓
Collective / Graph-aware Resolution (iterative, until convergence)
   ↓
Temporal Compatibility
   ↓
Source Independence (independent evidence chains)
   ↓
Evidence Fusion
   ↓
Calibrated Admission
```

## Resolution interface

```text
block(candidate) -> BlockKeys
    // keys: normalized_name_prefix, phonetic, transliteration, email/domain,
    // id-fragments, date/year, location, org, same-doc, co-occurrence, shared handle
    // Multiple strategies run in parallel; candidate pairs = union across strategies.

pair_score(c1, c2) -> PairScore
    // raw_pair_score from identifier/name/attribute/temporal/semantic/
    // relational/source/evidence/neighborhood signals; reasons[]

collective(candidate_pairs) -> CollectiveResolution
    // candidate-resolution graph → relational propagation (X≈X' when Y≈Y'
    // and X→director→Y / X'→director→Y') → re-score → cluster/resolve;
    // iterate until convergence; output = raw_pair_score + collective_score + reasons.
```

Output of resolution always preserves: `raw_pair_score`, `collective_score`, `reasons`, `version`, `provenance`. No opaque graph magic.

## Admission interface

```text
decide(candidate, evidence, profile) -> Decision
    // Decision: ACCEPT_NEW | ACCEPT_EXISTING | DEFER | REJECT | QUARANTINE
    // Decision carries: score_vector (validity, relevance, novelty,
    //   resolution_confidence, source_quality, evidence_support,
    //   structural_significance), reasons[], evidence_refs, model/policy versions,
    //   profile_id, timestamp.
```

### Decision precedence (categorical rules FIRST)

1. Invalid identifier or entity-type mismatch → **REJECT** (hard rule, not score-driven).
2. Explicit strong contradiction (e.g., born-1990 vs born-1980) → **QUARANTINE** or **REJECT** per policy.
3. Insufficient evidence → **DEFER** (the default for `uncertain`; never auto-REJECT).
4. Score ≥ auto_accept under calibrated/`CalibrationProfile` → **ACCEPT** (given corroboration).
5. Otherwise by per-type thresholds from the active `CalibrationProfile`.

Epistemic conservatism: a wrongly-rejected rare evidence (false negative) is costlier than an accepted noisy candidate (false positive); `uncertain` maps to DEFER/QUARANTINE, not REJECT.

## CalibrationProfile lifecycle

```text
v1 (bootstrap, conservative)         → calibration_status=UNCALIBRATED, source=bootstrap_policy, tagged_provisional=true
gold corpus (T085) measures v1 → calibration curves → operating points (asymmetric false-merge/false-split cost)
v2+ (empirically fitted)             → calibration_status=CALIBRATED
```

- Profiles are immutable and versioned; existing profiles are NEVER overwritten — a new version is appended so decisions replay against the exact profile that produced them.
- Fields: entity_type, language, script, resolver_version, calibration_version, feature_schema_version, policy_version, calibration_status, source, auto_accept/defer/reject thresholds, hard_reject_rules, provenance, effective_from/to.
- Admission looks up the active profile by (entity_type [, language/script]) with version bounds; replay uses the historical profile by time.

## Source Independence Engine (input to evidence fusion)

```text
build_publication_graph(observations) -> citation/derivation graph
    // edges: cites / copies / references / rewrites (near-dedup + timestamps + link structure)

independent_chains(evidence_refs) -> {chains: int, per_ref_role: copied|derived|independent}
    // assertion evidence: publication_count vs independent_support vs independent_evidence_chains —
    // NEVER publication_count == independent_support.
```

## Rules

- TDA/Finding → structural signals only (I-6). Identity comes from resolution; TDA output may feed a candidate/admission but never creates a trusted Entity directly.
- Admission decisions are persisted (ACCEPT…/DEFER/REJECT/QUARANTINE) with full context — rejected/deferred/quarantined candidates are never auto-deleted and are replayable (FR-014).
- No threshold is globally uniform; per-type (+ language/script) profiles are authoritative (FR-012).