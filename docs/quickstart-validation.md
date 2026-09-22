# Quickstart Validation Record (T134)

Record of running `specs/001-global-osint-platform/quickstart.md` scenarios against
the current codebase. Date: 2026-09-17. Environment: Windows dev box, `uv`
toolchain, MinIO reachable on :9000, control-plane HTTP API not running.

## Scenario A — closed-loop smoke (`bench.run --scenario smoke-val`)

Harness run (stack-free, CI-safe): fixtures present + full §84 traceability chain
(14 events) asserted.

```
uv run python bench/run.py --scenario smoke-val --dry-run
[PASS] fixtures-present
[PASS] event-in-chain:investigation.created … feedback.generated (14/14)
RESULT: PASS
```

Live-stack execution of steps 1–8 (`--api-base http://localhost:8000`) requires
the control-plane API container; recorded as **PENDING** until the dev compose
profiles are brought up (`--profile core --profile analytics`).

## Scenario B — regression / contract suites

| Suite | Command | Result |
| --- | --- | --- |
| control-plane + shared (unit/contract) | `uv run pytest apps/control-plane/tests apps/shared/tests` | 209 passed |
| bulk-ingestion unit + archive/live contract | `uv run pytest apps/bulk-ingestion/tests` | 12 passed (incl. MinIO contract) |
| bench suite | `uv run pytest bench/tests` | 23 passed |
| acquisition region/replay/browser | `uv run pytest apps/acquisition/tests` | green (earlier waves) |

## Scenario C — scale + chaos (T123/T124/T125)

```
uv run python -m bench.collection.bench_scale --millions 10
observations: 10000000   observations_per_sec: 32795.6   run_seconds: 304.9
lifecycle {created: 4864865, changed: 135135, unchanged: 0, duplicate: 5000000}

uv run python -m bench.chaos.bench_replay
records: 2000  processed_before_crash: 700  replayed_after_crash: 1300
exactly_once_projection: true  uncovered: 0
```

Cost-per-useful-observation KPI (T115): `cost_per_useful_observation` guards
`ZeroDivision` (+inf when no useful findings) and composes collection cost
against findings counters in `apps/shared/scoring/metrics.py`.

## Outcome

- SC-001/SC-002/SC-003/SC-006 invariants covered by the contract suites above
  (content addressing, rebuildability, dedup/conditional acquisition).
- Full live-stack Scenarios A/B remain gated on the API/streaming containers
  being up; dry-run PASS + hermetic/contract suites are the CI-verifiable core.

See `apps/deploy/docker-compose.yml` for the phased profiles used to bring the
stack up.