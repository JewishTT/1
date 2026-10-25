# Implementation maturity

Generated from the scanner's per-body flags. This separates *the symbol exists* from *the symbol does anything*. It is a heuristic over bodies and source markers, not a judgement of correctness.

| Status | Modules |
|---|---|
| IMPLEMENTED | 527 |
| PRIMITIVE | 0 |
| STUB | 0 |
| NOT_IMPLEMENTED | 0 |
| DECLARATION_ONLY | 18 |
| PACKAGE_INIT | 90 |
| MIGRATION | 14 |
| TEST | 321 |

**0** modules are present but not really built (STUB / NOT_IMPLEMENTED / PRIMITIVE).

## Not really built (STUB / NOT_IMPLEMENTED / PRIMITIVE)

_None._

## Declaration-only modules (no callables) — review for stubs

A non-``__init__`` module with no callables is either a data/declaration module or a stub that declares a capability and implements nothing. This list is where the second kind hides.

| Module | LOC | Markers |
|---|---|---|
| `apps/acquisition/source_query_set.py` | 0 | — |
| `apps/shared/conftest.py` | 2 | — |
| `apps/zero/zero/harvesters/modules.py` | 16 | — |
| `apps/projection/path_shim.py` | 20 | — |
| `tools/strip_zero_inventory.py` | 22 | — |
| `apps/projection/search/tantivy_backend.py` | 23 | — |
| `tools/append_zero_sources_b.py` | 29 | — |
| `tools/append_zero_frontend_b.py` | 32 | — |
| `tools/append_zero_sources_a.py` | 36 | — |
| `apps/shared/events/event_envelope_pb2.py` | 37 | — |
| `tools/append_zero_frontend_a.py` | 47 | — |
| `apps/acquisition/_probe_catalogue.py` | 51 | — |
| `apps/control-plane/api/path_shim.py` | 60 | — |
| `tools/fix_zero_layer_doc.py` | 87 | — |
| `tools/append_zero_inventory.py` | 98 | — |
| `apps/shared/domain/signal_basis.py` | 148 | — |
| `apps/control-plane/semantic_path/signal_corpus_baseline.py` | 159 | — |
| `apps/interpretation/parsers/primproc/reasons.py` | 381 | — |
