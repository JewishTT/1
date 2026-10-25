# Import graph

977 Python modules, 2695 resolved local edges.

Imports are classified against the platform's own import roots, the standard library,
the packages installed in the interpreter that ran the generator, and the distributions
declared in the workspace manifests. A name in none of those is a defect, not a dependency.

## External dependencies (top 40)

| Package | Kind | Import sites |
|---|---|---|
| `__future__` | stdlib | 850 |
| `dataclasses` | stdlib | 388 |
| `typing` | stdlib | 354 |
| `pathlib` | stdlib | 303 |
| `pytest` | third-party | 260 |
| `sys` | stdlib | 248 |
| `collections` | stdlib | 238 |
| `json` | stdlib | 185 |
| `datetime` | stdlib | 183 |
| `sqlalchemy` | third-party | 124 |
| `hashlib` | stdlib | 119 |
| `enum` | stdlib | 117 |
| `re` | stdlib | 92 |
| `fastapi` | third-party | 66 |
| `os` | stdlib | 65 |
| `asyncio` | stdlib | 64 |
| `uuid` | stdlib | 48 |
| `math` | stdlib | 41 |
| `urllib` | stdlib | 39 |
| `pydantic` | third-party | 34 |
| `importlib` | stdlib | 29 |
| `time` | stdlib | 29 |
| `types` | stdlib | 29 |
| `ast` | stdlib | 26 |
| `io` | stdlib | 25 |
| `numpy` | third-party | 23 |
| `logging` | stdlib | 21 |
| `inspect` | stdlib | 20 |
| `alembic` | third-party | 20 |
| `httpx` | third-party | 20 |
| `argparse` | stdlib | 18 |
| `tempfile` | stdlib | 17 |
| `threading` | stdlib | 17 |
| `subprocess` | stdlib | 15 |
| `warcio` | third-party | 15 |
| `shutil` | stdlib | 14 |
| `confluent_kafka` | third-party | 14 |
| `temporalio` | third-party | 13 |
| `itertools` | stdlib | 11 |
| `base64` | stdlib | 9 |

## Optional capability probes

Imported inside a `try`/`except ImportError`. The platform is written to run without
them, so they are neither a dependency nor a defect — but each one is a capability
that is switched off in this environment.

| Package | Probe sites |
|---|---|
| `pyshacl` | 1 |
| `pyzbar` | 1 |
| `tantivy` | 1 |

## Import roots

Top-level name → the directory it resolves to, taken from the platform's own `sys.path` at generation time.

| Name | Directory |
|---|---|
| `_events` | `apps/science/_events.py` |
| `_prove_readback` | `apps/acquisition/_prove_readback.py` |
| `acquisition` | `apps/acquisition` |
| `adapters` | `apps/acquisition/adapters/__init__.py` |
| `admission` | `apps/admission` |
| `aggregation` | `apps/interpretation/aggregation` |
| `analytics` | `apps/projection/analytics/__init__.py` |
| `anchoring` | `apps/science/anchoring.py` |
| `api` | `apps/control-plane/api/__init__.py` |
| `application` | `apps/control-plane/application` |
| `artifact_sink` | `apps/acquisition/artifact_sink.py` |
| `backfill` | `apps/bulk-ingestion/backfill.py` |
| `badges` | `apps/control-plane/badges/__init__.py` |
| `beliefs` | `apps/science/beliefs/__init__.py` |
| `bench` | `bench/bench/__init__.py` |
| `bulk_ingestion` | `apps/bulk-ingestion` |
| `causal` | `apps/science/causal/__init__.py` |
| `cc_extract` | `apps/acquisition/cc_extract.py` |
| `cc_plan` | `apps/acquisition/cc_plan.py` |
| `claims` | `apps/science/claims/__init__.py` |
| `composition` | `apps/control-plane/composition.py` |
| `config` | `apps/shared/config/__init__.py` |
| `context` | `apps/science/context/__init__.py` |
| `context_engine` | `apps/control-plane/context_engine/__init__.py` |
| `contracts` | `apps/shared/contracts/__init__.py` |
| `cp_domain` | `apps/control-plane/cp_domain/__init__.py` |
| `datasets` | `apps/shared/datasets/__init__.py` |
| `db` | `apps/control-plane/db/__init__.py` |
| `dictionaries` | `apps/interpretation/dictionaries/__init__.py` |
| `dispatcher` | `apps/acquisition/dispatcher/__init__.py` |
| `domain` | `apps/shared/domain/__init__.py` |
| `donor` | `apps/shared/donor/__init__.py` |
| `econ` | `apps/science/econ/__init__.py` |
| `engine` | `apps/admission/engine/__init__.py` |
| `errors` | `apps/science/errors.py` |
| `events` | `apps/shared/events/__init__.py` |
| `evidence` | `apps/interpretation/evidence/__init__.py` |
| `experiments` | `apps/science/experiments/__init__.py` |
| `extractors` | `apps/interpretation/extractors/__init__.py` |
| `feedback` | `apps/feedback/feedback/__init__.py` |
| `feedback_engine` | `apps/feedback/feedback_engine.py` |
| `fixtures` | `apps/science/fixtures/__init__.py` |
| `frontier` | `apps/acquisition/frontier` |
| `graph` | `apps/projection/graph/__init__.py` |
| `historical` | `apps/bulk-ingestion/historical/__init__.py` |
| `hypotheses` | `apps/science/hypotheses/__init__.py` |
| `ids` | `apps/shared/ids/__init__.py` |
| `independence` | `apps/admission/independence/__init__.py` |
| `interpretation` | `apps/interpretation/__init__.py` |
| `isolation` | `apps/shared/isolation.py` |
| `kinetics` | `apps/science/kinetics/__init__.py` |
| `knowledge` | `bench/knowledge` |
| `lakehouse` | `apps/projection/lakehouse/__init__.py` |
| `metrics` | `apps/projection/metrics/__init__.py` |
| `modifier` | `apps/control-plane/modifier/__init__.py` |
| `net` | `apps/shared/net` |
| `network` | `apps/shared/network/__init__.py` |
| `normalization` | `apps/interpretation/normalization` |
| `observability` | `apps/shared/observability/__init__.py` |
| `observation_consumer` | `apps/interpretation/observation_consumer/__init__.py` |
| `observation_gate` | `apps/acquisition/observation_gate/__init__.py` |
| `operators` | `apps/science/operators/__init__.py` |
| `parsers` | `apps/interpretation/parsers/__init__.py` |
| `path_shim` | `apps/projection/path_shim.py` |
| `pipeline` | `apps/interpretation/pipeline.py` |
| `projection` | `apps/projection` |
| `registry` | `apps/acquisition/registry.py` |
| `relations` | `apps/interpretation/relations.py` |
| `resolution` | `apps/admission/resolution/__init__.py` |
| `retrieval` | `apps/interpretation/retrieval/__init__.py` |
| `review` | `apps/science/review/__init__.py` |
| `robustness` | `apps/science/robustness/__init__.py` |
| `runtime` | `apps/acquisition/runtime/__init__.py` |
| `science` | `apps/science` |
| `scitda` | `apps/science/scitda/__init__.py` |
| `scoring` | `apps/shared/scoring/__init__.py` |
| `search` | `apps/projection/search/__init__.py` |
| `security` | `apps/shared/security.py` |
| `semantic` | `apps/shared/semantic/__init__.py` |
| `semantic_path` | `apps/control-plane/semantic_path/__init__.py` |
| `services` | `apps/control-plane/services/__init__.py` |
| `sims` | `apps/science/sims/__init__.py` |
| `sources` | `apps/acquisition/sources/__init__.py` |
| `spatial` | `apps/projection/spatial` |
| `specops` | `apps/specops/__init__.py` |
| `stopping` | `apps/feedback/stopping.py` |
| `storage` | `apps/shared/storage/__init__.py` |
| `store` | `apps/science/store.py` |
| `stream` | `apps/acquisition/stream.py` |
| `streaming` | `apps/science/streaming` |
| `streams` | `apps/projection/streams/__init__.py` |
| `structure` | `apps/science/structure/__init__.py` |
| `tda` | `apps/projection/tda/__init__.py` |
| `temporal` | `apps/science/temporal/__init__.py` |
| `tools` | `apps/shared/tools` |
| `websearch` | `apps/shared/websearch/__init__.py` |
| `worker_acquisition` | `apps/acquisition/worker_acquisition.py` |
| `worker_browser` | `apps/acquisition/worker_browser/__init__.py` |
| `worker_http` | `apps/acquisition/worker_http/__init__.py` |
| `workflow` | `apps/shared/workflow/__init__.py` |
| `workflows` | `apps/control-plane/workflows/__init__.py` |
| `zero` | `apps/zero/zero/__init__.py` |

## Guarded gaps (tracked missing features)

The platform imports the module inside a guard and skips the dependent tests. These
are tracked gaps, not defects — but each one is a feature that is not implemented.

| From | Import |
|---|---|
| `apps/shared/tests/unit/test_relation_schema.py` | `domain.context_validation` |
