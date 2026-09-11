# Contracts

Phase 1 output — the stable interface contracts of the platform. Implementation must preserve these; consumers must program only against these.

| File | Contract | Owners |
|---|---|---|
| [event-envelope.proto](./event-envelope.proto) | Kafka event envelope + payload policy | all planes |
| [acquisition-worker.md](./acquisition-worker.md) | AcquisitionWorker interface (capabilities/estimate/acquire) | acquisition, dispatcher |
| [graph.md](./graph.md) | GraphProjector/Reader/Traversal/Snapshot/Exporter | projection, search, analytics, TDA |
| [utility-scorer.md](./utility-scorer.md) | UtilityScorer + adaptive scheduler state | feedback, acquisition |
| [storage.md](./storage.md) | Storage abstraction (S3 content addressing) + RawBucket | evidence plane |
| [resolution-admission.md](./resolution-admission.md) | Blocking→Pairwise→Collective resolution + calibrated epistemic admission + Source Independence | interpretation, admission, evidence |

## Rules

- No vendor-specific types cross application boundaries (Constitution C-4/C-5).
- Event `payload` is the serialized per-type proto; `event_id`, `correlation_id`, `causation_id` are lineage-critical and must always be carried (Spec FR-023).
- Consumers must be idempotent on `event_id` / `task_id` / `observation_id` / projection offsets (Spec FR-024).
- Contract changes require a new minor/major event version or ADR — never a silent break (Constitution Governance).