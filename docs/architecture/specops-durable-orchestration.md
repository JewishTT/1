# SpecOps&CI durable operation orchestration

**Status:** Feature 042 foundation implemented; production ARTEX adapter and rollout gates remain open.  
**Owner:** SpecOps&CI domain silo  
**Version:** specops-ci-operation-v1

## Intent

Add a durable, reviewable operation lifecycle to SpecOps&CI without moving evidence
ownership out of Intelligence or creating a second source of truth for the ARTEX graphs.
This is an execution-control plane for approved defensive assessments and synthetic lab
validation, not an autonomous attack planner.

The implementation intentionally starts with a fixed, reviewed graph and a declarative
operation plan. It does not accept operator-authored Python, arbitrary LangGraph code,
shell commands, arbitrary tool names, URLs, credentials, payloads or dynamic target
expansion.

## Responsibility split

    Operator / API
      | submits immutable OperationSpec
      | tenant + authorization + snapshot + exact roster + expiry
      v
    LangGraph SpecGraph (versioned code; deterministic routing)
      | validate spec digest
      | request live authorization check (Activity)
      | interrupt for operator decision (Activity)
      | verify durable decision (Activity)
      | revalidate authorization and expiry (Activity)
      | bounded assessment (Activity)
      | append idempotent result to Exploration Graph (adapter)
      v
    Temporal Workflow
      | durable event history, retries and timeouts
      | query: get_operation_summary / get_pending_approval
      | signal: provide_operator_decision
      v
    ARTEX adapters (deployment-supplied)
      | Asset Graph read port
      | Exploration Graph read/append port
      | read-only / synthetic assessment engine

    PostgreSQL
      | authoritative engagement authorization + revocation
      | append-only per-step operator decision ledger

### LangGraph

apps/specops_ci/orchestration/contracts.py defines immutable OperationSpec and
SpecStep records. The SHA-256 digest is computed over a canonical JSON representation.
The contract validates schema version, step vocabulary, operation expiry, duplicate
IDs, explicit targets, topological dependency order and the rule that every step needs
operator approval.

apps/specops_ci/orchestration/graph.py defines the versioned StateGraph. The graph
is static trusted code. The operation payload selects from a narrow step enum:
evidence_review, configuration_review, detection_coverage_review,
lab_simulation and report_generation. Conditional edges stop on an invalid approval
or authorization and re-check authorization between steps. An assessment result marked needs_review
terminates the workflow in a manual-review state rather than progressing to the next
step automatically.

### Temporal

apps/specops_ci/orchestration/workflow.py wraps the graph through Temporal's
LangGraph plugin. Activity nodes perform I/O and receive Temporal retry/timeout policy.
Workflow nodes are deterministic state transitions. A LangGraph interrupt() becomes
a durable wait: the Workflow exposes the request via Query, accepts a correlated Signal,
and resumes via Command(resume=...).

The Workflow IDs equal the immutable operation IDs. The task queue is
specops-ci-operations. API submission uses the existing shared Temporal connection
bootstrap; the dedicated worker is separately deployed.

### ARTEX and PostgreSQL

apps/specops_ci/orchestration/runtime_ports.py defines the strict adapter protocols.
ArtexSpecOpsRuntime is a composition layer that:
1. revalidates the durable authorization and operation expiry;
2. reads only the Asset Graph nodes in the frozen roster/snapshot;
3. reads the operation's Exploration Graph state;
4. invokes the allow-listed read-only or synthetic evaluator; and
5. appends a compact result with deterministic idempotency key
   operation_id:step_id:spec_digest.

It writes only bounded result metadata and opaque evidence identifiers. Raw evidence
bodies, credentials and arbitrary tool output must never enter Temporal history.

apps/control-plane/services/specops_ci_authorization_gate.py checks the current
tenant-bound authorization at Activity time and verifies step decisions against
specops_ci_operation_decisions. The decision and a compact Signal intent are written in the same PostgreSQL
transaction. The lease-based outbox relay sends the Signal and retries after Temporal
outages or relay crashes. The unique decision and outbox keys make enqueue/delivery
idempotent. The signal is transport; the database row is the auditable decision.

## Safety invariants

1. An operation references exactly one tenant, authorization, Intelligence snapshot
   and immutable SHA-256 spec digest.
2. Operation targets and every step target are subsets of the authorization's exact
   target roster. Unknown IDs are rejected; no target expansion is available.
3. The authorization must be active at submission and revalidated immediately before
   each assessment Activity. Revocation/expiry blocks the step.
4. Every step requires an authenticated admin decision recorded in the append-only
   decision ledger. A valid rejection terminates the operation; it never reaches the
   evaluator.
5. Only the five reviewed step kinds above are accepted. No autonomous exploitation,
   initial access, privilege escalation, lateral movement, phishing, credential capture,
   arbitrary command execution, source acquisition or recon is exposed by this worker.
6. ARTEX graph writes are bounded and idempotent. A result is never accepted as a new
   discovery or a scope expansion.
7. Temporal workflow history carries identifiers, digests, summaries and opaque
   evidence refs only — never raw document bodies, secrets or credentials.
8. If any runtime adapter is missing, the worker exits before polling. There is no
   permissive no-op or fallback executor.

## Failure and consistency model

Temporal history is the durable execution ledger; PostgreSQL remains authoritative for
engagement authorization and operator decisions; ARTEX Asset/Exploration Graphs remain
the authoritative domain state. These systems are not treated as one distributed
transaction.

A worker retry may repeat an Activity. Therefore ARTEX append operations must enforce
the supplied idempotency key. An Activity failure before the graph append is retried;
a failure after the append but before Activity completion must return the original
result for that idempotency key rather than append a duplicate.

The Temporal history is not a second copy of raw evidence. It records workflow inputs,
state transitions, approved decisions and compact output references. Payload Codec/KMS
encryption is a production requirement even with that minimization; the current worker
does not yet configure a Payload Codec.

For very long runs, Temporal's LangGraph integration requires a continue-as-new strategy
to bound event history. cache() propagation and a workflow continuation policy are
not implemented in this first slice.

## Deployment boundary and current gaps

The repository currently contains no production ARTEX Asset Graph or Exploration Graph
implementation that this feature can bind to. The protocols and composition class are
implemented, and services.specops_ci_runtime_factory:build_runtime composes the
PostgreSQL gate with deployment-supplied graph/evaluator factories. The actual ARTEX
adapter and assessment evaluator must still be supplied by the deployment.
SPECOPS_CI_RUNTIME_FACTORY, SPECOPS_CI_ARTEX_GRAPH_FACTORY and
SPECOPS_CI_ASSESSMENT_ENGINE_FACTORY are mandatory; missing or incomplete factories
cause worker startup to fail closed.

The HTTP API can submit operations, query pending approvals and atomically persist
admin decisions plus a Temporal Signal outbox entry. Run
cognitive-specops-ci-signal-outbox as a separate control-plane process to deliver and
retry the signals. The API does not enable the legacy SpecOps execution routes. Those consumers
must be migrated separately and must not bypass the durable gate.

The Temporal-LangGraph integration package temporalio-langgraph is version 0.1.0
and is documented by Temporal as Public Preview. It is pinned alongside
temporalio==1.36.1 and langgraph==1.2.22 in the isolated worker requirements.
Treat the integration as experimental until canary, crash/retry, replay, upgrade and
long-wait fault tests pass on the production Temporal server.

## Operational rollout gates

Before production use:
- deliver the concrete ARTEX graph and evaluator adapters;
- configure a KMS-backed Temporal Payload Codec and verify ciphertext at rest and in
  the Web/CLI query surfaces;
- implement continue-as-new before history reaches service limits;
- add workflow version/build-ID compatibility policy for running operations;
- test duplicate workflow submission, duplicate decision signals, worker crashes before
  and after graph writes, Temporal disconnects, approval waits, approval rejection,
  authorization revocation and expiry;
- add a full operation/decision audit view and lifecycle metrics;
- run the migration, full CI suite and full-stack acceptance against a real Temporal
  test server and a synthetic ARTEX fixture.

Feature 042 is not production-complete until these gates are closed.
