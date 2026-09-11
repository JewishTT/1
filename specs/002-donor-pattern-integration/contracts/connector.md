# Connector Contract (SpiderFoot / reNgine pattern)

Every source is a **connector** implementing the existing `AcquisitionWorker` contract (FR-008, FR-009, US4). `apps/acquisition/` owns connector adapters.

## Connector registry entry

```text
Connector {
  connector_id   // CN-<uuid>
  name           // unique connector name
  source_types   // [HTTP, API, Feed, Dataset, Document, ...]
  capabilities   // capabilities() output (source types, content types)
  policy_id      // binding source policy
  status         // REGISTERED -> ACTIVE -> DISABLED
  version        // connector version
}
```

## Compliance

- Connector MUST implement `capabilities() / estimate(task) / acquire(task)` per the AcquisitionWorker contract before it may be ACTIVE.
- `acquire(task)` returns `observation_created | unchanged | duplicate | failed` and, on success, writes a content-addressed raw object via the Storage contract.
- Outputs are the standard Observation/Artifact/Mention/Candidate chain — **no bespoke per-source formats**.
- Connectors run in isolated worker pools per class (Security-First, C-7). Browser connectors are escalation-only.
- A reNgine-style **recon plan** (plan_id) groups an investigation's acquisition tasks; tasks flow through Kafka to collectors and back as observations without custom plumbing (FR-009).
- Connector registration requires a policy and tenant scope; no external access beyond public interfaces (Constitution VII).