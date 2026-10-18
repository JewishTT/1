# Quickstart — running the suites for feature 028

Everything below was executed on this machine on 2026-10-13. No command here is
aspirational.

---

## 0. Prerequisites

```
cd C:\Users\tim\Desktop\COGNITIVE\1
uv sync
```

Python 3.11.9, uv 0.12.12.

---

## 1. The platform suite — one command, whole tree

```powershell
.venv\Scripts\python.exe -m pytest -q
```

**Expected: `22 failed, 4288 passed, 27 skipped` in ~19 minutes.**

The 22 failures are the pre-existing set recorded in `audit/current-state-audit.md` §1.
They are not caused by this feature and are not expected to change until WP-C and
WP-F. A run showing a *different* failure set is a regression — investigate before
committing.

Collection only (~70s):

```powershell
.venv\Scripts\python.exe -m pytest --co -q
```

**Expected: `4336 tests collected`, zero errors.** If this reports collection errors in
`donors/` or `tmp/`, the `testpaths`/`norecursedirs` configuration has been lost.

---

## 2. The closed-loop tests — the thing this feature actually changed

```powershell
.venv\Scripts\python.exe -m pytest apps/control-plane/tests/integration/test_closed_research_loop.py -q
```

**Expected: `15 passed` in under a second.**

These are the regression guard for WP-A. If the loop stops closing, they fail.

---

## 3. The context engine alone — fast iteration

```powershell
.venv\Scripts\python.exe -m pytest apps/control-plane/tests/unit/test_context_engine.py `
                            apps/control-plane/tests/unit/test_cognitive_loop.py `
                            apps/control-plane/tests/unit/test_context_termination_and_catalogue.py `
                            apps/control-plane/tests/unit/test_invariant_reducer.py -q
```

~91 tests, under 30 seconds. Run this while iterating on the context kernel.

---

## 4. The bench suite — a separate workspace member

```powershell
cd bench
..\.venv\Scripts\python.exe -m pytest -q
```

**Expected: `2 failed, 21 passed`.**

It runs from its own directory by necessity, not preference. `bench` is a workspace
member whose importable package is `bench/bench/`, while the repo root also holds a
plain `bench/` directory. Collected alongside `apps/…`, pytest installs a namespace
placeholder for `bench` in `sys.modules` and the import cannot be repaired. Both trees
are legitimate; they do not share a collection root. The reasoning is recorded in
`pyproject.toml` next to the setting.

---

## 5. Selection by tier

```powershell
# unit only
pytest -m unit -q

# contract
pytest -m contract -q

# integration
pytest -m integration -q

# live — makes real network calls; opt-in, never part of the baseline
pytest -m live -q
```

`live` tests **skip** rather than pass when the network is absent. A live run that
reports skips has proved nothing about the sources and must not be reported as a pass.

---

## 6. Services

```powershell
docker compose -f apps/deploy/docker-compose.yml --profile core --profile analytics up -d
```

Minimum for the durability claims: `postgres`. `core` alone gives you postgres, minio,
redis, temporal, redpanda and searxng.

Note for WP-C onwards: `apps/control-plane/tests/unit/test_postgres_context_store.py`
connects to a real postgres but never exercises `remember`/`memory_for`, which is where
the `ActionMemoryEntry.from_dict` defect lives. Connecting does not prove that path
works.

---

## 7. Recording a result

Any claim in this feature directory must carry the command that produced it and the
observed output. A claim without both is a `tasks.md` checkbox, and `tasks.md`
checkboxes are not evidence — `audit/current-state-audit.md` §4 lists seven that were.

Record results in this format:

```
Command:  .venv\Scripts\python.exe -m pytest <path> -q
Result:   <n> passed, <n> failed
Exit:     <code>
Date:     <date>
```