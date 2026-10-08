# Quickstart — 025

**Feature**: `025-context-reality-approximation-engine`
How to verify that what exists still works, and how to bring up each new wave.

Repo root: `C:\Users\tim\Desktop\COGNITIVE\1`

---

## 0. Current gate status

```text
Wave 0 contract freeze : CLOSED — 12/12 ADR accepted (docs/adr/0028…0039 + WAVE-000-index)
Phase A implementation : UNBLOCKED — next step is Phase A, then B, then 2S Slice-0
Baseline               : Design Baseline v2 (verbatim in input.md, 155 KB)
```

Task breakdown is complete: [tasks.md](tasks.md) — **154 tasks** plus 12 ADR records,
16 execution phases including the **Wave 2S vertical slice**.

---

## 1. Verify the substrate 025 adopts (must stay green at every wave)

025 is additive. The 024 Context Engine is `REUSE`/`EXTEND`, so any wave that turns these
red has broken something it was supposed to extend.

```powershell
cd C:\Users\tim\Desktop\COGNITIVE\1

# Context Engine + durable store + cognitive loop  (expects 104 passed)
.\.venv\Scripts\python.exe -m pytest `
  apps\control-plane\tests\unit\test_context_engine.py `
  apps\control-plane\tests\unit\test_cognitive_loop.py `
  apps\control-plane\tests\unit\test_context_termination_and_catalogue.py `
  apps\control-plane\tests\unit\test_postgres_context_store.py `
  apps\control-plane\tests\integration\test_layer0_direct_pipeline.py `
  -q --no-header
```

```powershell
# Whole-platform regression. Baseline: 19 failed / 3190 passed / 16 skipped
# The 19 are pre-existing and listed in research.md; a 20th is a regression.
.\.venv\Scripts\python.exe -m pytest apps -q --no-header
```

```powershell
# Collection must be clean. Non-zero here invalidates every test count above.
.\.venv\Scripts\python.exe -m pytest apps --collect-only -q 2>&1 | Select-String "error"
```

### Configuration-scope check (research R1)

Config resolves from the **common ancestor** of the arguments, not the repo root. Every new
package's tool config must be verified from root:

```powershell
.\.venv\Scripts\python.exe -m pytest `
  apps\shared\tests\unit `
  apps\control-plane\tests\unit\test_context_engine.py `
  -q --no-header
```

Async tests silently fail in one scope and pass in the other if `asyncio_mode = "auto"` is
missing from the config that pytest actually loaded. See root `pyproject.toml`.

---

## 2. Bring up the platform

```powershell
cd C:\Users\tim\Desktop\COGNITIVE\1
docker compose -f apps\deploy\docker-compose.yml up -d
```

| Service | Where |
|---|---|
| PostgreSQL | authority for context/research state |
| ClickHouse | temporal-graph projection, `http://localhost:18123` |
| Redpanda | transport |
| MinIO | raw bytes |
| Temporal | workflow |
| Neo4j | rebuildable serving projection only |

---

## 3. Live walkthrough — the path 025 extends

Proves durable context → natural question → obligations → frontier → replay. Every wave
must keep this working.

```powershell
$root = "C:\Users\tim\Desktop\COGNITIVE\1"
Start-Process cmd -ArgumentList "/c","cd /d `"$root\apps\control-plane`" && set `"PYTHONPATH=$root\apps\control-plane;$root\apps\shared;$root\apps\acquisition;$root\apps\interpretation;$root\apps\projection`" && `"$root\.venv\Scripts\python.exe`" -m uvicorn api.main:app --host 0.0.0.0 --port 8001"

$h = @{ "X-Tenant-Id" = "default-tenant" }

$inv = Invoke-RestMethod -Method Post -Uri "http://localhost:8001/api/v1/investigations" `
  -Headers $h -ContentType "application/json" `
  -Body '{"name":"Putin family","objective":{"intent":"recon"},"seeds":[],"scope":{}}'

$ctx = Invoke-RestMethod -Method Post `
  -Uri "http://localhost:8001/api/v1/investigations/$($inv.investigation_id)/context" `
  -Headers $h -ContentType "application/json" `
  -Body ('{"title":"Putin family structure","question":"find everything about the Putin family structure","scope_refs":["' + $inv.investigation_id + '"]}')

$gaps = '[{"kind":"operator_intent","question":"Who are the members of the Putin family?","rationale":"operator asked for family structure","knowledge_type":"entity","priority":0.9,"evidence_refs":["op-1"]},{"kind":"coverage_gap","question":"Which companies are linked to Putin family members?","rationale":"no organisation evidence yet","knowledge_type":"relation","priority":0.8,"evidence_refs":[]}]'

$r = Invoke-RestMethod -Method Post `
  -Uri "http://localhost:8001/api/v1/investigations/$($inv.investigation_id)/context/ingest" `
  -Headers $h -ContentType "application/json" -Body $gaps

$r.revision.caused_by_event_ids   # revision names its cause
$r.obligations                    # 2 created
$r.open_obligations               # 2

# idempotence: re-posting the same gaps must create nothing new
$r2 = Invoke-RestMethod -Method Post `
  -Uri "http://localhost:8001/api/v1/investigations/$($inv.investigation_id)/context/ingest" `
  -Headers $h -ContentType "application/json" -Body $gaps
$r2.obligations.Count             # 0
$r2.open_obligations              # 2 — addresses are stable, nothing duplicated
```

Read back from PostgreSQL — not from memory:

```powershell
Invoke-RestMethod -Uri "http://localhost:8001/api/v1/investigations/$($inv.investigation_id)/context" -Headers $h
Invoke-RestMethod -Uri "http://localhost:8001/api/v1/investigations/$($inv.investigation_id)/context/frontier" -Headers $h
Invoke-RestMethod -Method Post -Uri "http://localhost:8001/api/v1/investigations/$($inv.investigation_id)/context/replay" -Headers $h -Body '{}'
```

---

## 4. Determinism check (baseline §4, §36 — FR-025-068)

The constitutional acceptance mode. Same inputs + same versions + same parameters must give
byte-identical revision content.

```powershell
# run twice, compare state hashes
.\.venv\Scripts\python.exe -m pytest apps -q --no-header -k "determinism or replay or canonical"
```

Enforced at every declared artifact boundary (T025-128), not only at the final graph.

---

## 5. Per-wave bring-up

| Wave | Bring-up | Gate |
|---|---|---|
| 0 | none — documents only; ratify §47.4 targets | no 024/025 terminology **or lifecycle** conflict; ADR 01–12 accepted |
| A | import `apps/shared/domain/context/*` with no services running | truth algebra truth-table green |
| B | `alembic upgrade head` against PostgreSQL | restart preserves state; append-only enforced |
| C | seed 3+ cells, run blocking | conflicts survive gluing; obstructions queryable |
| D | seed a series with a change point | regime ≠ transition; late event ⇒ new revision |
| E | abduction corpus | multiple explanations coexist; pruning explainable |
| G | conflicting-source corpus | `truth_state == BOTH` survives storage→API→UI |
| F | dialectical corpus | inconclusive stays inconclusive |
| H | frontier with two discriminating actions | utility decomposed, not one scalar |
| I | worldline snapshot + TDA | topological feature cannot write identity/truth |
| J | register first operator | fingerprint resolves to concrete versions |
| K | golden queries incl. a universal term | completeness mode explicit |
| L | endpoint smoke | no confident bare array |
| M | workspace | provenance clickable end-to-end |
| 2S | Slice-0 end-to-end (dev-lite **and** dev-full) | conflicting sources → `BOTH` → Contradiction → space+`H_OTHER` → prediction+test → obligation → action → analyst approval → observation → outcome → revision; replay reproduces every intermediate artifact |
| N | full corpora | replay fixed-point per determinism class; budgets enforced; erasure drill; §54 **A–Q** green |

**Note the PostgreSQL requirement (§47.1, V.16)**: persistence tests run against PostgreSQL,
**not SQLite**. Append-only guards, row-level security, generated columns and JSONB indexing
behave differently and SQLite would hide defects until late. SQLite is allowed only for pure
unit tests that touch no persistence semantics.

**Slice-0 is the first thing to run after Wave 2.** It is the cheapest end-to-end proof that
the epistemic chain works, and it deliberately precedes locality, dynamics and abduction.

---

## 6. v2 verification commands

```powershell
# Truth-state truth tables + lattice laws (T025-020, T025-149)
.\.venv\Scripts\python.exe -m pytest apps -q -k "truth or lattice or belnap"

# Allen algebra tables (T025-140)
.\.venv\Scripts\python.exe -m pytest apps -q -k "allen or temporal or interval"

# Determinism classes + seeds (T025-136)
.\.venv\Scripts\python.exe -m pytest apps -q -k "determinism or numeric_mode or seed or replay"

# Independence / n_eff / absence admissibility (T025-130..132, T025-135)
.\.venv\Scripts\python.exe -m pytest apps -q -k "independence or n_eff or absence or coverage"

# Slice-0 (T025-152)
.\.venv\Scripts\python.exe -m pytest apps -q -k "slice0 or slice_0"

# FR coverage gate (T025-153) — must never fail
.\.venv\Scripts\python.exe -m pytest apps -q -k "fr_coverage or traceability"
```

## 7. What must never regress

- `ContextEngine` stays **async** end to end (store contract, in-memory store, PostgreSQL
  store, engine, `CognitiveLoop`, routes).
- `InvestigationContext` identity derivation is untouched; `definition_ref` is additive.
- Zero duplicate modules at collection.
- Cross-tenant reads fail closed.
- Nothing derived is visible before durable commit.