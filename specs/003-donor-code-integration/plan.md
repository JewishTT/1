---

description: "Implementation plan for donor code extraction & integration"
---

# Plan: Donor Code Integration

**Input**: `specs/003-donor-code-integration/spec.md`

## Strategy

Place adapted donor code in one namespaced package — `apps/shared/donor/` — so
licensing/attribution is auditable in one place, then wire it into existing
integration points (`collective.py`, `bench/bench/harness.py`) with tests. Faithful
ports; donor idioms replaced by COGNITIVE domain names.

## File layout (new)

```
apps/shared/donor/
  __init__.py         # re-exports + attribution manifest (DONORS.md-style header)
  correlation_graph.py   # adapted OpenOSINT correlation.py
  statement.py           # adapted FollowTheMoney statement.py
  evidence.py            # adapted NetForensicAI evidence.py
apps/shared/tests/unit/donor/
  test_correlation_graph.py
  test_statement.py
  test_evidence.py
```

## Integration points (existing files, additive edits)

- `apps/admission/resolution/collective.py` — `CorrelationService.export_graph()`
  builds a `CorrelationGraph` from its `CorrelationEdge`s and returns D3 node-link
  + Mermaid → consumed by projections/webapp GraphPanel contract.
- `bench/bench/harness.py` — `bench_donor` upgraded: statement provenance latency
  via donor `Statement.make_key`; new evidence ingest+verify throughput via the
  vault. Registered in `BENCHMARKS`.

## Rename map (donor → COGNITIVE)

| Donor | Adapted |
| --- | --- |
| `EntityType`/`Entity`/`Relationship` | `CorrelationKind`/`CorrelationNode`/`CorrelationLink` |
| `source_tools` | `observations` (set of observation refs) |
| `EntityGraph` | `CorrelationGraph` |
| FTM `Statement` | `Statement` (kept, sci-typed fields; `make_key` sha1) |
| `EvidenceManager`/`Evidence` | `EvidenceVault`/`EvidenceItem` (case→investigation) |

## Test strategy

- Unit tests per module: identity dedup, non-merge, exports valid XML/JSON/Mermaid;
  statement key determinism + dataset/lang/external composition; vault ingest
  → read-only → verify / tamper-detect.
- Integration test: `collective.export_graph()` returns valid node-link for edges;
  bench harness registers the upgraded donor benchmarks and their scenarios pass.
- Gate: `ruff` + shared/admission/bench suites green.

## Validation commands

```bash
uv run --project apps/shared pytest apps/shared/tests -q
uv run --project apps/admission pytest apps/admission/tests -q
uv run --project bench pytest bench/tests -q
uv ruff check apps/shared/donor apps/admission/resolution bench/bench/harness.py
```

## Risks

- Changing shared code could ripple into admission; mitigated by additive edits
  and running all suites.
- Porting fidelity vs codebase conventions; attribution headers keep provenance.