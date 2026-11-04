# Security policy

## Reporting

Please do not publish an unpatched vulnerability or sensitive exploit details in a public issue. Use GitHub's private vulnerability reporting / Security Advisory workflow for this repository when available. If private reporting is not enabled, contact the repository maintainers privately before disclosure.

Include the affected commit, component, impact, reproduction steps, and any proposed mitigation. Avoid including real credentials, personal data, private datasets, or unredacted production evidence.

## Platform security invariants

- Authentication and authorization fail closed; identity and role claims come from verified principals.
- Every data access is tenant-scoped. Source acquisition requires explicit policy and authorization.
- Raw evidence is immutable and content-addressed; derived claims retain provenance and observation lineage.
- Source collection is bounded by explicit budgets, timeouts, egress rules, provider terms, and retention policy.
- Discovery results are leads, not verified facts or identity-resolution decisions.
- Secrets must not be logged, committed, copied into fixtures, or emitted in events.
- Unknown or unconnected security/operations controls must be reported as unavailable, not green.

Security-sensitive changes require focused regression tests and review of the relevant threat model, constitution clauses, and ADRs.
