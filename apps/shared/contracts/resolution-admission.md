# Contract: Resolution & Admission (T035-T037, T082-T084, T086-T087)

## Scope

Converts extracted Candidates (T034) + observations into a graph of resolved
entities and admitted assertions, while preserving provenance and enabling
replay. Implementations must satisfy the invariants below.

## Concepts

- **CandidateRecord**: an unresolved identity hypothesis (one canonical value,
  N aliases, supporting sources/observations, temporal metadata).
- **CandidatePair**: two candidates scored for resolution; carries
  `raw_pair_score`, `reasons` (evidence enum labels), and (after T083)
  `collective_score`.
- **EvidenceLink**: a reference from an assertion to the observations/mentions
  that support it (`evidence_refs`). `publication_count` counts distinct docs;
  `independent_support` and `independent_evidence_chains` come from T087.
- **ScoreVector**: per-signal scores kept as separate named fields (never
  collapsed to a single opaque number).
- **AdmitDecision**: one of `ACCEPT_NEW | ACCEPT_EXISTING | DEFER | REJECT |
  QUARANTINE`. Rejections are returned with a machine-readable reason code and
  remain replayable (never deleted).

## Blocking (T082)

- Blocking must NOT compare every candidate pair: use inverted indexes over
  extracted keys; candidate-pair generation is bounded by bucket size.
- Multi-strategy: name-prefix, phonetic, transliteration, email/domain,
  id-fragments, date/year, location, org, same-doc, co-occurrence, shared
  handle. The union of per-strategy candidate pairs is emitted with `strategy`
  provenance per pair.
- Buckets above `max_bucket` are skipped (recorded as `skipped_buckets`) rather
  than generating O(N²) pairs.

## Pairwise resolver (T035)

- Takes blocking pairs; per entity-type signal scoring; output:
  `raw_pair_score` (0..1), `reasons` list of evidence labels, and the mapping
  back to the two candidates. Deterministic given same inputs.

## Collective resolution (T083)

- Builds a candidate-resolution graph from pairs; applies relational
  propagation (a↔b and b↔c high ⇒ a↔c boosted); iterates until the graph stops
  changing (convergence); outputs per-pair `collective_score` + reasons.
  Must be transparent: no opaque embedding magic.

## Temporal consistency (T084)

- Relation-specific temporal policies: `single`, `multi`, `interval`,
  `append_only`, `supersedable`, `contradictory`.
- Assertion state machine: `ASSERTED → SUPERSEDED | RETRACTED | CONTRADICTED |
  EXPIRED`. Supersedes/replacement links recorded; the original assertion is
  NEVER deleted (FR-016, replayable).

## Source independence (T087)

- Citation/derivation edges: `cites | copies | references | rewrites`.
- Computes `independent_evidence_chains`; independence score in 0..1 feeding
  evidence fusion. `publication_count` (T037) is distinct from
  `independent_support` (T087).

## Admission (T036)

- Score vector stored with separate fields per signal; decision policy applies
  model/policy versions; output decision + evidence refs + provenance.

## Calibration (T086)

- Categorical hard-reject rules run FIRST: invalid identifier → REJECT; explicit
  strong contradiction → QUARANTINE/REJECT per policy; insufficient evidence →
  DEFER; strong corroboration → ACCEPT.
- `CalibrationProfile` per (entity_type, language, script) with per-type
  thresholds; uncertified bootstrap profile `UNCALIBRATED` v1 until calibrated
  per T085.

## Invariants

- I-2: Mention ≠ Candidate ≠ Entity; resolution produces Entities, never
  mutates Candidates.
- I-3: an admitted Assertion is a claim, not truth; every Assertion carries
  evidence_refs.
- FR-016: a superseded/retracted assertion remains stored and replayable.
- Original candidate surface forms are never overwritten.