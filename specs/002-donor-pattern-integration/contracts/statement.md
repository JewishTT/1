# Statement Contract (FollowTheMoney pattern)

Every assertion is backed by a statement record (FR-001, FR-003, US1). Consumers of interpretation output MUST receive statement-level provenance.

## Statement shape

```text
Statement {
  statement_id      // ST-<uuid>; idempotency key
  assertion_id      // backing assertion (feature 001)
  dataset_id        // provenance boundary — reprints share one dataset chain
  first_seen        // RFC3339 first observation
  last_seen         // RFC3339 latest observation
  original_value    // literal value from source; immutable (I-1)
  extraction_version// extractor version tag
  valid_from        // optional temporal window start
  valid_until       // optional temporal window end
  provenance        // producer, causation_id, observation refs
}
```

## Rules

- Every assertion MUST have a Statement with non-null `dataset_id` + `extraction_version` + `original_value`.
- `original_value` is immutable after write (I-1); supersession creates a new statement linked to the old (FR-016).
- `publication_count` and `independent_sources` are computed by the evidence layer, never stored equal (FR-002).
- Temporal policies (single/multi/interval/append-only/supersedable/contradictory) are enforced by the admission engine's temporal layer, not here.
- Lineage walk MUST reach a raw observation via assertion → statement → observation → raw uri.