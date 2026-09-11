# Correlation + Review contract (OpenOSINT / Vitni pattern)

Authoritative contract: [`specs/002-donor-pattern-integration/contracts/correlation-review.md`](../../../specs/002-donor-pattern-integration/contracts/correlation-review.md).

possible_match edges between candidates WITHOUT auto-merge (FR-004, I-2) and
append-only analyst reviews ACCEPT/REJECT/UNCERTAIN (FR-006). Implementation:
`resolution/collective.py::CorrelationEdge` + `correlate()` (admission),
`services/review.py` (control-plane), Postgres tables `correlation_edges` /
`review_decisions`.