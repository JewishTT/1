# Connector contract (SpiderFoot / reNgine pattern)

Authoritative contract: [`specs/002-donor-pattern-integration/contracts/connector.md`](../../../specs/002-donor-pattern-integration/contracts/connector.md).

Every source is a connector implementing the AcquisitionWorker contract —
`capabilities()/estimate()/acquire()` (FR-008) — emitting standard
Observation/Artifact/Mention/Candidate outputs. Recon plans (FR-009)
orchestrate Investigation → Tasks → Kafka → Collectors. Implementation:
`services/source_registry.py::Connector`/`ConnectorRegistry`/`ReconPlanService`
(control-plane), API `api/routes/connectors.py`, gate: ACTIVE only when compliant.