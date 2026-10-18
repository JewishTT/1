# Quickstart — COGNITIVE Global Platform Upgrade

**Feature**: `030-global-platform-upgrade`

Everything below was **executed on this machine on 2026-10-14**. Nothing here is aspirational.
Commands marked ⚠️ have a known blocking condition — see §6.

```powershell
cd C:\Users\tim\Desktop\COGNITIVE\1
```

---

## 0. Prerequisites

```powershell
uv sync
```

**Measured environment [2026-10-14]**

| Component | Version | Command |
|---|---|---|
| Python | 3.11.9 | `python --version` |
| uv | 0.12.12 | `uv --version` |
| Node | v24.19.0 | `node --version` |
| Git HEAD | `608c3ad8f4743e4e729807c903b0364ed571b311` | `git rev-parse HEAD` |
| Branch | `main` | `git branch --show-current` |
| Dirty entries | **147** | `git status --porcelain \| Measure-Object -Line` |

> ⚠️ **147 dirty entries.** No acceptance claim may be made against a clean tree until WP-0 records
> which of them belong to this feature.

---

## 1. Baseline — the number every later run is compared against

```powershell
.venv\Scripts\python.exe -m pytest -q
```

**Last honest recorded baseline** (feature 029, 2026-10-13, same HEAD):
`22 failed, 4288 passed, 27 skipped` in ~19 minutes.

**This feature has not yet re-run it.** WP0 does. A run producing a *different* failure set is a
regression, not progress.

Collection only (~70s):

```powershell
.venv\Scripts\python.exe -m pytest --co -q
```

**Expected: `4336 collected, 0 errors`.** Collection errors reported from `donors/` or `tmp/` mean
the `testpaths` / `norecursedirs` configuration has been lost.

---

## 2. Why the config looks the way it does

**[MEASURED]** Each of these was added because its absence caused a *silent* wrong answer:

```toml
testpaths        = ["apps"]                              # pyproject.toml:36
norecursedirs    = ["donors", "tmp", "logs", ...]        # pyproject.toml:39-49
markers          = ["contract", "integration", "live", "unit"]  # :68
asyncio_mode     = "auto"                               # :79
addopts          = "--import-mode=importlib"            # :88
```

| Setting | Failure it prevents |
|---|---|
| `testpaths` | Bare `pytest -q` collected **6769 tests with 831 collection errors** — every one from a vendored checkout under `donors/` |
| `norecursedirs` | A vendored tree re-enters collection from any explicit path argument |
| `asyncio_mode = auto` | 71 context-engine tests failed *only* when run from the repo-root config while passing from the member config — pytest reads the **common ancestor** config |
| `--import-mode=importlib` | Six sibling packages named `contract` and two named `integration` collapse under `prepend`, hiding **98 passing tests** including the three transport-critical ones |
| `bench` excluded from `testpaths` | Collected with `apps/`, pytest fails with `ImportError: cannot import name 'harness' from 'bench'` |

**Consequences for new code in this feature:**

- A new test package named `contract` or `integration` inherits the `importlib` requirement.
- A new `async def` test requires `asyncio_mode = "auto"`.
- `bench` tests run from the `bench` workspace member, **never** alongside `apps`.

---

## 3. The kernel — fast iteration

```powershell
.venv\Scripts\python.exe -m pytest apps/control-plane/tests/unit/test_context_engine.py `
                            apps/control-plane/tests/unit/test_cognitive_loop.py `
                            apps/control-plane/tests/unit/test_context_termination_and_catalogue.py -q
```

The Context Kernel lives at **[MEASURED]** `apps/control-plane/context_engine/` — 19 modules:

```text
engine.py (38K)  loop.py (32K)  enrichment_service.py (29K)  postgres_store.py (26K)
context_graph.py (23K)  obligations.py (20K)  invariant_reducer.py (17K)
fabric_store.py (16K)  context_graph_store.py (13K)  dossier_store.py (13K)
return_path.py (10K)  catalogue_bridge.py (9K)  query_cycle.py (9K)
fabric_runner.py (8K)  store.py (8K)  fabric_bridge.py (8K)
science_bridge.py (6K)  worldline.py (3K)
```

The five responsibilities are **already separated** in `engine.py`:

| Responsibility | Class | Line |
|---|---|---|
| Obligation generation | `ObligationGenerator` | 100 |
| Satisfaction evaluation | `SatisfactionEvaluator` | 185 |
| Action proposing | `ActionProposer` | 264 |
| Decision recording | `DecisionRecorder` | 345 |
| Revision management | `RevisionManager` | 407 |

---

## 4. Per-package runs — narrow, fast, honest

```powershell
.venv\Scripts\python.exe -m pytest apps/admission -q
.venv\Scripts\python.exe -m pytest apps/acquisition -q --ignore=apps/acquisition/tests/integration
.venv\Scripts\python.exe -m pytest apps/shared apps/projection apps/science -q
.venv\Scripts\python.exe -m pytest apps/feedback apps/zero apps/interpretation -q
```

**Recorded results from the 029 session [MEASURED, 2026-10-13]** — use as comparison points:

| Scope | Result |
|---|---|
| `apps/admission` | 114 passed |
| `apps/acquisition` unit + contract | 338 passed |
| `apps/acquisition` integration (worker, backpressure, loop_closed) | 13 passed |
| `apps/shared` + `apps/projection` + `apps/science` | 2203 passed, 16 failed |
| `apps/control-plane` unit + contract | 508 passed, 9 failed |
| `apps/feedback` + `apps/zero` + `apps/interpretation` | 908 + 123 passed |

---

## 5. Bench harness

```powershell
cd bench
..\.venv\Scripts\python.exe -m pytest -q
..\.venv\Scripts\python.exe run.py --help
```

`bench` is a workspace member with its own `pythonpath = ["."]`. Run it **from `bench/`**.

---

## 6. ⚠️ Blocking condition — measured today, still live

```powershell
Test-NetConnection -ComputerName localhost -Port 5432   # True
Test-NetConnection -ComputerName localhost -Port 9000   # True
Test-NetConnection -ComputerName localhost -Port 8123   # False  (ClickHouse refused)
Test-NetConnection -ComputerName localhost -Port 6379   # True
docker ps                                               # EMPTY
```

| Probe | Result |
|---|---|
| `localhost:5432` | **OPEN** |
| `localhost:9000` | **OPEN** |
| `localhost:8123` | connection refused |
| `localhost:6379` | OPEN |
| Owner of 5432 and 9000 | **pid 12640 `com.docker.backend`** |
| `docker ps` | **empty — no running containers** |

**Diagnosis**: Docker's backend holds published host ports while reporting no containers.

**Measured effect** (from 029, same condition):

- **7** `control-plane/tests/unit/test_postgres_context_store.py` — previously *skipped* (nothing on
  the port), now *run and fail* on handshake timeout.
- **2** `feedback/tests/test_frontier_loop.py` — same cause.
- **4** `shared/tests/integration/test_infra_connectivity.py` — same cause.
- `acquisition/tests/integration/test_adapters_gate.py` and `test_engine_adapters_gate.py` —
  **hang**. MinIO is now reachable so the skip no longer applies, and the path does not complete.
  These were skipped for the whole earlier baseline, so **there is no prior measurement**.

**This is not a code regression and must not be read as one.**

### Unblock options

1. Identify and release the Docker publication holding 5432/9000.
2. Point the suite at a working instance (`COGNITIVE_PG_DSN` and the object-store equivalent).
3. If neither is possible: **every affected test is reported as `blocked`**, and any gate needing
   them is reported blocked. Never as passing.

**No acceptance criterion is evaluated against a run that did not execute** (SC-016).

---

## 7. Validation scenarios — what must be provable

Each maps to a success criterion. These are the runnable proofs, not unit tests.

| # | Scenario | Proves |
|---|---|---|
| V-1 | Start an investigation, deliver one independently-sourced observation | Obligation reaches a terminal state, stop report names the reason, revision advances, **next action changes** | SC-001, SC-002 |
| V-2 | Resolve a table-cell finding to source bytes | Span → content address → exact cell; raw digest unchanged | SC-004, SC-005 |
| V-3 | Run the epistemic fixture corpus | All 13 states round-trip through storage → events → API → UI without collapse | SC-003 |
| V-4 | Replay a recorded event stream after restart | Same head, same revision chain, same digests; zero duplicated effects | SC-006, SC-007 |
| V-5 | Late evidence (valid 2020, acquired 2026) | `CURRENT` / `AS_OF` / `INTERVAL` return three different correct answers | SC-008 |
| V-6 | High-score pair without an admission decision | **Zero** identity merges committed by a score alone | SC-009 |
| V-7 | Injected DB failure between blob write and placement | Observation stays unplaced; zero "placed" rows with failed membership | FR-063 |
| V-8 | Inject a failure to write a new observation | Duplicate delivery yields zero extra revisions/independence/coverage | SC-007 |
| V-9 | Backlog growth downstream | Acquisition dispatch rate falls; backlog does not grow unbounded | FR-067 |
| V-10 | Disable an integrated donor | Previous path resumes; **nothing deleted** | SC-014, FR-112 |

---

## 8. Result classification — mandatory

Every result in the final report is exactly one of:

| Class | Meaning |
|---|---|
| **PASS** | Executed, asserted, succeeded |
| **FAIL** | Executed, assertion failed |
| **BLOCKED** | Could not execute — named blocker, owner, next action |
| **NOT RUN** | Not executed |

**Fabricated metrics are a release blocker.** An unavailable measurement is `null` with the missing
instrumentation named — never `0`, never an estimate presented as a measurement.

---

## 9. Documents to read before changing code

```text
spec.md                        requirements (7 stories, 115 FRs, 17 SCs)
plan.md                        decisions + work-package order + blocking condition
research.md                    measured baseline + 14 architecture decisions
data-model.md                  entities, state machines, validation rules
contracts/                     8 contracts — the integration boundary
current-state-audit.md         WP0 output — not yet written
donor-matrix.md                WP0 output — extends specs/029/.../donors/donor-matrix.md
```

**Read `specs/029-research-closed-loop-upgrade/` first.** It contains the verified audit, a
45-name donor matrix and the property note on `InvariantReducer` that this feature must not regress.