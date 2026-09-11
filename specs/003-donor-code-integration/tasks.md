---

description: "Task list for donor code extraction & integration"
---

# Tasks: Donor Code Integration

**Input**: `specs/003-donor-code-integration/spec.md`, `plan.md`

**Organization**: Tasks are in execution order respecting file ownership; `[P]`
tasks touch disjoint files and can run in parallel.

## Format: `[ID] [P?] [Area] Description` — include exact file paths

---

## Phase 1: Adapted donor modules (new package)

- [x] T001 Donor package scaffold + attribution: `apps/shared/donor/__init__.py`
  (re-export `CorrelationGraph`, `Statement`, `EvidenceVault`; header lists source
  repos + licenses). Add `"donor"` to `packages` in `apps/shared/pyproject.toml`.
- [x] T002 Correlation graph ← OpenOSINT: `apps/shared/donor/correlation_graph.py`
  (adapt `correlation.py`: `CorrelationKind`, `CorrelationNode` with `observations`
  instead of `source_tools`, `CorrelationLink`, `CorrelationGraph` add/merge/
  neighbors + `to_dict`/`to_json`/`to_graphml`/`to_mermaid`/`summary`).
- [x] T003 Statement provenance ← FollowTheMoney:
  `apps/shared/donor/statement.py` (adapt `statement.py`: `Statement` value-class,
  deterministic `make_key` sha1 over dataset.entity.prop.value[+@lang][+.ext],
  `original_value` preservation, `clone`/`from_dict`/`to_db_row`; drop rigour/
  sqlalchemy deps).
- [x] T004 Evidence vault ← NetForensicAI: `apps/shared/donor/evidence.py`
  (adapt `evidence.py`: `EvidenceItem` manifest, `EvidenceVault` add/load/list/
  stored_file_path/verify, streaming sha256, read-only stored copy; audit hook
  → logging).
- [x] T005 [P] Unit tests `apps/shared/tests/unit/donor/test_correlation_graph.py`
  (identity dedup, no-merge, deterministic exports: JSON node-link / GraphML parses /
  Mermaid, neighbors both directions, summary counts).
- [x] T006 [P] Unit tests `apps/shared/tests/unit/donor/test_statement.py`
  (key determinism, lang/external composition, original_value collapse, clone
  preserves/regenerates id correctly, from_dict round-trip, to_db_row).
- [x] T007 [P] Unit tests `apps/shared/tests/unit/donor/test_evidence.py`
  (ingest → manifest + read-only file; verify true; tampered file → verify false;
  list skips corrupt manifest; missing source error; id sequence).

## Phase 2: Pipeline integration

- [x] T008 Wire correlation graph into resolution:
  `apps/admission/resolution/collective.py` — add
  `CorrelationService.export_graph()` building a donor `CorrelationGraph` from edges
  (kind "possible_match", nodes = candidate/values, observations = edge ids) and
  returning `{"node_link": ..., "mermaid": str}`. Add test
  `apps/admission/tests/test_collective_export.py` (edges → valid node-link +
  mermaid). Also re-run `test_donor_patterns.py` (T033) to keep green.
- [x] T009 Wire statement + evidence into the bench harness:
  `bench/bench/harness.py` — extend `bench_donor`: statement-stable-key latency via
  `Statement.make_key`; add evidence ingest+verify throughput scenario through
  `EvidenceVault` (tmp dir, emits `evidence_ingest_per_s`, `evidence_verify_per_s`).
  Register in `BENCHMARKS`. Update `bench/tests/test_harness.py`.
- [x] T010 Gate validation: `ruff` clean + shared / admission / bench suites green
  (shared 77+, admission 37+, bench 18+); update this file to `[x]` for all tasks.