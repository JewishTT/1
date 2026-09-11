# Statement contract (FollowTheMoney pattern)

Authoritative contract: [`specs/002-donor-pattern-integration/contracts/statement.md`](../../../specs/002-donor-pattern-integration/contracts/statement.md).

Statement-level provenance for every assertion (FR-001/FR-003): `dataset_id`,
`first_seen/last_seen`, `original_value` (immutable, I-1), `extraction_version`,
temporal validity windows, full provenance. Implementation: `engine/assertions.py::Statement`
(admission), Postgres table `statements` (control-plane `db/schema.py`).