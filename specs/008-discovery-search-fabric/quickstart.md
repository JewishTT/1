# Quickstart: Discovery & Rebuildable Search Projection Fabric

**Feature**: `008-discovery-search-fabric` | **Date**: 2026-09-26

All commands run from the **project root** (`1/`), not the workspace root. The apps are `uv`
workspace members, so each suite is invoked with `--project`.

> Every "before" number below was produced by running the command on 2026-09-26, not
> estimated. The two suites this feature repairs are **currently red** — that is the point.

---

## 0. The two red suites (the reason this feature exists)

### 0.1 Projection suite — collection is interrupted

```bash
cd 1
uv run --project apps/projection pytest apps/projection/tests -q
```

**Current (broken):**

```text
ERROR apps\projection\tests\test_bm25s_backend.py
ERROR apps\projection\tests\test_relevance.py
ModuleNotFoundError: No module named 'search.bm25s_backend'
!!! Interrupted: 2 errors during collection !!!  164 tests collected
```

`apps/projection/search/indexer.py:23` does `from search.bm25s_backend import BM25SRankedIndex`
at module import time, and that file does not exist. Because it is an unconditional top-level
import, **nothing** in the search plane imports. `bm25s>=0.2` *is* declared in
`apps/projection/pyproject.toml:14` — the package is available, the module is missing.

**After T001:** `N passed, 0 failed` — no collection errors.

### 0.2 Acquisition + websearch — cross-suite pollution

```bash
cd 1
uv run --project apps/acquisition pytest apps/acquisition/tests apps/shared/tests/unit/websearch -q
```

**Current:** `15 failed, 134 passed, 10 skipped`

The same websearch suite **on its own**:

```bash
uv run --project apps/acquisition pytest apps/shared/tests/unit/websearch -q
```

**Current:** `2 failed, 21 passed`

The two genuine failures are:

```text
TestQueryBuilder::test_name_becomes_quoted_entity_query_first
TestDiscoverySink::test_host_diversity_caps_one_source
```

So **11 further failures are caused purely by running the two suites in one session**. Adding
*any single* acquisition test file reproduces 13 failures (verified for `test_browser_fabric.py`,
`test_cc_plan.py`, `test_adapter_onboarding.py` and others), which rules out one bad test and
points at import-time global state. Both `conftest.py` files are **empty**, so the cause is a
module-level side effect in an acquisition import, not a fixture.

This matters because CI runs them together, and because a red suite in one plane hides a real
regression in the other. See task **T033**.

---

## 1. Prove Layer A without a network (the point of the injection seams)

Every discovery source takes an injected callable, so the whole layer is testable offline.

```bash
cd 1
uv run --project apps/acquisition pytest apps/acquisition/tests/unit/test_discovery_contracts.py -v
uv run --project apps/acquisition pytest apps/acquisition/tests/unit/test_discovery_registry.py -v
uv run --project apps/acquisition pytest apps/acquisition/tests/unit/test_discovery_sources.py -v
```

### Canonicalisation is total, pure and deterministic

```python
from apps.acquisition.adapters.discovery.contracts import canonicalize   # via path shim in tests

canonicalize("HTTPS://Example.ORG:443/a/")   # 'https://example.org/a/'   port dropped
canonicalize("http://example.org:80/a")      # 'http://example.org/a'     default port dropped
canonicalize("https://example.org/a#frag")   # 'https://example.org/a'    fragment dropped
canonicalize("mailto:a@b.c")                 # None                       not acquisition
canonicalize("https://example.org/a")        # 'https://example.org/a'    trailing slash is SIGNIFICANT
```

The last line is the one that matters: `/a` and `/a/` are different resources, so the
canonicaliser must **not** strip it. Every source drops `None` returns, which is how
non-http(s) schemes never reach the frontier.

### Discovery is idempotent and auditable

```python
from apps.acquisition.adapters.discovery.registry import (
    DiscoveryRegistry, InMemoryFrontierSink,
)
from apps.acquisition.adapters.discovery.contracts import candidates_from_urls

reg, sink = DiscoveryRegistry(), InMemoryFrontierSink()

class Stub:
    name = "stub"
    capabilities = frozenset({"index"})
    def discover(self, query):
        return candidates_from_urls(
            ["https://example.org/a", "https://example.org/a#x", "mailto:x@y.z"],
            source="stub", method="index-query", query=query,
        )

reg.register(Stub())
first = reg.discover("example.org", frontier=sink, tenant_id="T1", investigation_id="I1")
second = reg.discover("example.org", frontier=sink, tenant_id="T1", investigation_id="I1")

assert first.candidates_found == 1        # dedup + non-http(s) drop
assert first.enqueued == 1
assert second.enqueued == 0               # idempotent: nothing new (FR-006, SC-002)
assert sink.uris() == ["https://example.org/a"]
```

Re-running the same pass must produce a byte-identical report — that is what makes replay
deterministic rather than merely correct.

### A broken source is recorded, not fatal

```python
class Broken:
    name, capabilities = "broken", frozenset({"api"})
    def discover(self, query): raise RuntimeError("upstream 503")

reg.register(Broken())
report = reg.discover("example.org", frontier=sink)
assert report.sources_failed[0]["source"] == "broken"
```

`sources_failed` and `empty_sources` are **separate fields**. "This source is broken" and
"this source genuinely found nothing" are different operational facts; collapsing them is how a
dead source goes unnoticed for months.

---

## 2. Prove the search projection is a rebuildable projection

```bash
cd 1
uv run --project apps/projection pytest apps/projection/tests/test_projection.py -v
uv run --project apps/projection pytest apps/projection/tests/test_mappings.py -v
uv run --project apps/projection pytest apps/projection/tests/test_quickwit.py -v
```

### Replay is idempotent (FR-010, SC-003)

```python
from search.projector import SearchEvent, SearchProjector
from search.index import InMemorySearchIndex

def build():
    idx = InMemorySearchIndex()
    p = SearchProjector(idx)
    for e in EVENTS:                      # same EVENTS every time
        p.project(e)
    return p, idx

p1, i1 = build(); p1.rebuild()
p2, i2 = build(); p2.rebuild(); p2.rebuild()      # rebuild twice

assert i1.all("entities") == i2.all("entities")   # identical document set
```

Rebuilding a **second** time must not change anything. A projector whose rebuild is
order-dependent or accumulating is not a projection, it is a store.

### Tenant isolation fails closed (FR-011, SC-004)

```python
from search.mappings import physical_index_name, alias_name

assert physical_index_name("entities", "T1") == "entities-v1-T1"
assert alias_name("entities", "T1") == "entities-T1"
for bad in ("", None):
    try:
        physical_index_name("entities", bad); raise AssertionError("must fail closed")
    except ValueError:
        pass
```

A permission error must **raise**, never degrade to an empty result set — an empty set means
"no matches", and conflating the two is exactly the ambiguity Constitution Invariant 9 exists
to prevent.

### The kind list cannot drift (D8)

```python
from search.mappings import DOC_KINDS, all_index_configs
assert len(DOC_KINDS) == 7                # not 6 — this feature's own spec got this wrong once
assert {c["index_id"] for c in all_index_configs(tenant="T1")} == \
       {f"{k}-v1-T1" for k in DOC_KINDS}
```

---

## 3. Prove provenance survives the bridge (FR-007)

```bash
cd 1
uv run --project apps/control-plane pytest apps/control-plane/tests/integration/test_frontier_provenance.py -v
uv run --project apps/control-plane pytest apps/control-plane/tests/unit/test_migration_017_forward_only.py -v
```

```python
adapter.enqueue(uri="https://example.org/a", tenant_id="T1", investigation_id="I1",
                source="cc-index", method="index-query", priority=0,
                provenance={"sources": ["cc-index"], "seen_by": [{"source": "ct-log"}]})

row = frontier.get("T1", "https://example.org/a")
assert row.provenance["method"] == "index-query"      # NOT dropped at the boundary
assert row.state == "READY"                            # discovery set no schedule fields
```

`state`, `lease_until`, `next_schedule_at` and `retries` must be untouched by the adapter:
those are frontier policy (ADR-0016/0017), and a discovery adapter that sets them has become a
scheduler.

---

## 4. Prove the query surface degrades (FR-015, SC-006)

```bash
cd 1
uv run --project apps/control-plane pytest apps/control-plane/tests/unit/test_query_degradation.py -v
uv run --project apps/control-plane pytest apps/control-plane/tests/unit/test_query_fusion.py -v
```

```python
# one sick backend must not zero the whole query
results = await planner.execute(plan)
assert results and results[0].degraded_backends == ["graph"]

# ...but a total outage must NOT look like "no matches"
with pytest.raises(AllBackendsFailed):
    await planner.execute(plan_with_only_dead_backends)
```

The second assertion is the important one. Returning `[]` when everything is down is
indistinguishable from a genuine empty result set.

---

## 5. The API surface

```bash
cd 1
uv run --project apps/control-plane pytest apps/control-plane/tests/integration/test_discovery_api.py -v
```

```bash
curl -sX POST localhost:8000/discovery/run \
  -H 'content-type: application/json' \
  -d '{"seed":"example.org","seed_type":"domain","investigation_id":"I1"}' | jq .report
```

```json
{"query": "example.org", "sources_run": ["cc-index"], "sources_failed": [],
 "candidates_found": 42, "enqueued": 40, "empty_sources": ["crtsh"]}
```

`candidates_found` is the true total; the response `candidates` array is capped. A cap that
silently truncated would make the report lie to whoever reads it.

---

## 6. Full-suite baseline

```bash
cd 1
foreach ($a in @("acquisition","projection","control-plane","shared","admission","science","zero")) {
  uv run --project "apps/$a" pytest "apps/$a/tests" -q --no-header -p no:cacheprovider |
    Select-String -Pattern "passed|failed|error" | Select-Object -Last 1
}
```

**Recorded baseline, 2026-09-26:**

| Suite | Before | Expected after |
|---|---|---|
| `apps/projection` | collection **interrupted** (2 errors, 164 collected) | green |
| `apps/acquisition` + `apps/shared/tests/unit/websearch` | 15 failed, 134 passed, 10 skipped | 2 failed → 0 failed |

The two residual websearch failures are pre-existing and unrelated to this feature's
requirements; they are listed in `tasks.md` as **T034** so they are not silently absorbed into
this feature's exit criteria.

---

## Definition of done

| Criterion | How it is shown |
|---|---|
| FR-002 – FR-004 discovery sources proven offline | §1 — all four sources via injection seams |
| FR-005, FR-007 frontier binding + provenance survives | §3 — `test_frontier_provenance.py` |
| FR-006, SC-002 idempotent by canonical URL | §1 — second pass enqueues 0 |
| FR-010, SC-003, SC-010 rebuild determinism | §2 — double-replay, identical doc set |
| FR-011, SC-004 tenant isolation fail-closed | §2 — `ValueError`, never an empty set |
| FR-012 reproducible mappings | §2 — `DOC_KINDS` ↔ config parity |
| FR-013, FR-014 TDA adjacency + shared keys | `test_link_edge_provider.py` + existing adjacency tests |
| FR-015, SC-006 graceful degradation | §4 — isolation, and total failure raises |
| SC-007 green offline CI | §6 — no network in any test |
| SC-008, FR-018 no access-control bypass | registration-refusal test in §1 |
| SC-012, FR-017 no new backbone | component inventory diff — one column, no new table |
