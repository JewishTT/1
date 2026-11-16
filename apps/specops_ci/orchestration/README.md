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

The returned adapter must compose:
- PostgresSpecOpsAuthorizationGate for current authorizations and durable admin
  decisions;
- a tenant-scoped ArtexGraphPort that reads only the supplied snapshot/roster and
  deduplicates writes using the idempotency key;
- a ReadOnlyAssessmentEngine for the closed step vocabulary.

No implementation is fabricated in this repository because the ARTEX Asset Graph,
Exploration Graph and safe assessment engine services were not present in the source
tree. Until a real factory is supplied, worker startup fails closed.

Example environment (replace the factory with a reviewed deployment module):

~~~bash
export PYTHONPATH="$PWD/apps:$PWD/apps/control-plane"
export TEMPORAL_ADDRESS="localhost:7233"
export TEMPORAL_NAMESPACE="default"
export SPECOPS_CI_TASK_QUEUE="specops-ci-operations"
export SPECOPS_CI_RUNTIME_FACTORY="deployment.specops_runtime:build_runtime"
python -m specops_ci.orchestration.worker
~~~

## API lifecycle

- POST /api/v1/specops-ci/operations submits the immutable spec.
- GET /api/v1/specops-ci/operations/{operation_id}/approval reads the pending
  challenge.
- POST /api/v1/specops-ci/operations/{operation_id}/steps/{step_id}/decision records
  an admin decision in PostgreSQL before sending the Temporal Signal.

The worker re-checks the engagement authorization before each step. A signal is not
itself an approval; the Activity must find the matching durable decision row.

## Production blockers

The Payload Codec/KMS, continue-as-new, workflow version compatibility, concrete ARTEX
adapter/evaluator, Signal retry outbox, lifecycle UI/metrics and live Temporal fault
tests are tracked in specs/042-specops-durable-orchestration/tasks.md.
