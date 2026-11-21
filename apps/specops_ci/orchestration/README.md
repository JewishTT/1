# SpecOps&CI Temporal/LangGraph worker

This is an isolated worker runtime. The FastAPI control plane can submit operations and
record decisions without importing LangGraph; the worker environment installs the
experimental plugin separately.

## Install

From the repository root:

~~~bash
python -m venv .venv-specops-ci
source .venv-specops-ci/bin/activate
python -m pip install -r apps/specops_ci/orchestration/requirements.txt
~~~

The exact worker dependencies are pinned:
- temporalio==1.36.1
- langgraph==1.2.22
- temporalio-langgraph==0.1.0 (Temporal Public Preview)

## Runtime adapter is mandatory

The worker will not poll a queue unless SPECOPS_CI_RUNTIME_FACTORY points to a
synchronous Python factory that returns an implementation of SpecOpsRuntimePorts.

The default services.specops_ci_runtime_factory:build_runtime composition builds
PostgresSpecOpsAuthorizationGate automatically and loads two deployment-owned
zero-argument factories:
- SPECOPS_CI_ARTEX_GRAPH_FACTORY: a tenant-scoped ArtexGraphPort that reads only the
  supplied snapshot/roster and deduplicates writes using the idempotency key;
- SPECOPS_CI_ASSESSMENT_ENGINE_FACTORY: a ReadOnlyAssessmentEngine for the closed step
  vocabulary.

No implementation is fabricated in this repository because the ARTEX Asset Graph,
Exploration Graph and safe assessment engine services were not present in the source
tree. Until a real factory is supplied, worker startup fails closed.

Example environment (replace the factory with a reviewed deployment module):

~~~bash
export PYTHONPATH="$PWD/apps:$PWD/apps/control-plane"
export TEMPORAL_ADDRESS="localhost:7233"
export TEMPORAL_NAMESPACE="default"
export SPECOPS_CI_TASK_QUEUE="specops-ci-operations"
export SPECOPS_CI_RUNTIME_FACTORY="services.specops_ci_runtime_factory:build_runtime"
export SPECOPS_CI_ARTEX_GRAPH_FACTORY="deployment.artex:build_graph_adapter"
export SPECOPS_CI_ASSESSMENT_ENGINE_FACTORY="deployment.artex:build_safe_evaluator"
python -m specops_ci.orchestration.worker
~~~

## API lifecycle

- POST /api/v1/specops-ci/operations submits the immutable spec.
- GET /api/v1/specops-ci/operations/{operation_id}/approval reads the pending
  challenge.
- POST /api/v1/specops-ci/operations/{operation_id}/steps/{step_id}/decision records
  an admin decision and signal intent in PostgreSQL atomically.
- GET /api/v1/specops-ci/operations/{operation_id}/decisions/{decision_id}/delivery
  reports signal delivery state without exposing the signal payload.

The worker re-checks the engagement authorization before each step. A signal is not
itself an approval; the Activity must find the matching durable decision row.

Run the separate relay process with:

~~~bash
cognitive-specops-ci-signal-outbox
~~~

The API inserts the decision and its signal outbox record in one PostgreSQL transaction.
The relay uses leases and backoff to recover from Temporal outages or process crashes.

## Production blockers

The Payload Codec/KMS, continue-as-new, workflow version compatibility, concrete ARTEX
adapter/evaluator, Signal retry outbox, lifecycle UI/metrics and live Temporal fault
tests are tracked in specs/042-specops-durable-orchestration/tasks.md.
