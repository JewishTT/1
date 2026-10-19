# Contract 08 — API and Events

**Feature**: `033-universal-context-runtime`
**Governs**: the typed resource surface and the event envelope.
**Enforces**: FR-059…FR-065; blueprint §27.

---

## Why this contract exists

Two failures are easy and expensive here. The first is a **second API set**: a new `/v2`-shaped
surface that duplicates the existing routers, so the platform has two answers for one question. The
second is a **dishonest long-running response**: a request that returns `200` for work that has not
run.

§27.1 addresses the first explicitly — naming is a project recommendation, and final naming must be
reconciled with the existing routers and contracts *without creating a second set*. §27.2 addresses
the second: an event exists only after its backing transaction commits.

---

## Resources

```text
POST   /v1/contexts                        create from natural language or typed definition
GET    /v1/contexts/{id}                   current revision, status, summary
GET    /v1/contexts/{id}/revisions         history + diffs
POST   /v1/contexts/{id}/branches          alternative interpretation branch
POST   /v1/contexts/{id}/questions         add question/hypothesis
GET    /v1/contexts/{id}/obligations       gaps, status, dependencies, acceptance
POST   /v1/contexts/{id}/actions:plan      plan without executing
POST   /v1/contexts/{id}/actions:execute   execute an approved plan
POST   /v1/contexts/{id}/actions/{aid}:cancel
GET    /v1/contexts/{id}/timeline
GET    /v1/contexts/{id}/graph             bounded projection query
GET    /v1/contexts/{id}/conflicts
POST   /v1/conflicts/{id}/resolution-proposals
POST   /v1/resolutions/{id}:adjudicate
GET    /v1/entities/{id}/worldline
GET    /v1/evidence/{id}
GET    /v1/evidence/{id}/spans/{span_id}
GET    /v1/ontologies/{id}/revisions
POST   /v1/ontologies/{id}/revisions:propose
POST   /v1/ontologies/{id}/revisions:validate
POST   /v1/ontologies/{id}/revisions:activate
GET    /v1/capabilities
POST   /v1/queries
POST   /v1/analyses
GET    /v1/runs/{id}
GET    /v1/runs/{id}/trace
POST   /v1/evaluations
GET    /v1/reports/{id}
GET    /v1/audit/events
```

---

## Normative rules

### R1 — Reconcile, do not duplicate

Every resource is mapped onto an existing router or replaces one with a migration plan. A route that
exists in both the old and new surface is a defect until one is retired.

### R2 — Long work returns a run

A request that cannot complete synchronously returns a durable run id and its current status. It
never returns success for queued work. `GET /v1/runs/{id}` reports real progress, and
`/runs/{id}/trace` reports the operator lineage with redaction.

### R3 — Errors are typed

`problem+json`-style with a stable `reason_code`, a `retriable` flag and a remediation hint. No raw
secrets, no unrestricted stack traces, no `500` for a validation error.

### R4 — Events follow commits

An event is published only after its backing canonical transaction commits, through the approved
outbox seam. The bus is delivery and replay; it is not an authority.

### R5 — The envelope is canonical

```text
EventEnvelope
├── schema_version       REQUIRED
├── event_id             REQUIRED
├── occurred_at          REQUIRED
├── recorded_at          REQUIRED
├── tenant_id            REQUIRED
├── context_id           CONDITIONAL
├── context_revision     CONDITIONAL
├── actor                REQUIRED   user | operator | system
├── correlation_id       REQUIRED
├── causation_id         REQUIRED
├── idempotency_key      REQUIRED
├── provenance_ref       REQUIRED
└── payload_ref          REQUIRED   a reference or digest, never raw sensitive content
```

### R6 — Eleven event families

`context`, `obligation`, `action`, `acquisition`, `interpretation`, `identity`, `conflict`,
`ontology`, `projection`, `report`, `governance`, `system`. Each family's member events are declared
in the schema registry, and an unregistered event type is refused at publish time.

### R7 — The DSL is typed and bounded

The JSON query DSL supports graph patterns, scope/time/space/perspective constraints, epistemic and
source-quality filters, required provenance level, execution mode (`preview`, `execute`, `replay`,
`explain`), budget caps and an accepted output schema. Arbitrary code is not the DSL.

### R8 — Specialised languages are separate capabilities

SQL, SPARQL and graph languages sit behind their own validation and resource controls. They are not
exposed as the universal query language.

### R9 — Evaluation is authorised

`POST /v1/evaluations` runs a declared golden suite and requires authorisation. It is not a general
script runner.

---

## Prohibitions

- A second API set with no migration plan.
- `200 OK` for work that has not completed.
- An event emitted before its transaction commits.
- Raw sensitive payloads in an event.
- Arbitrary code execution through the query DSL.
- A stack trace or secret in an error body.

---

## Tests

| Test | Asserts |
|---|---|
| `tests/contract/test_api_surface.py::test_no_duplicate_routes` | R1 |
| `tests/integration/test_long_running_returns_run.py` | R2 |
| `tests/contract/test_errors.py::test_problem_json` | R3 |
| `tests/integration/test_event_only_after_commit.py` | R4 |
| `tests/contract/test_event_envelope.py::test_all_families_registered` | R6 |
| `tests/security/test_dsl_no_code_execution.py` | R7, R8 |
