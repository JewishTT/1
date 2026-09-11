# Correlation + Review Contract (OpenOSINT / Vitni pattern)

Correlation edges exist between Candidates without auto-merge (FR-004); analyst reviews are immutable provenance (FR-006, US2).

## CorrelationEdge

```text
CorrelationEdge {
  edge_id           // CE-<uuid>
  candidate_a       // Candidate id
  candidate_b       // Candidate id
  kind              // possible_match | similar | derivation
  raw_pair_score    // blocking/pairwise score (I-7: separate from identity)
  reasons           // blocking keys / signals used
  collective_score  // optional post-propagation score
  state             // OPEN -> REVIEWED -> RESOLVED
}
```

## ReviewDecision

```text
ReviewDecision {
  review_id   // RV-<uuid>
  target_type // candidate | assertion | correlation_edge | finding
  target_id
  decision    // ACCEPT | REJECT | UNCERTAIN
  analyst_id  // RBAC subject
  reasoning   // optional
  reviewed_at
  provenance  // immutable, replayable via kafka event
}
```

## Rules

- **No auto-merge**: correlation edges NEVER collapse Candidates into Entities. Identity comes only from an admitted assertion (I-2).
- **No all-pairs**: candidate pairs originate from blocking, never O(N²) (FR-012/resolution contract of feature 001).
- **DEFER default**: insufficient evidence → DEFER, never destructive REJECT (FR-005).
- **Review is append-only** and changes projections only via events (I-12).
- Extraction confidence and resolution score are stored separately (I-7).