"""Build the WP0 capability matrix from real import edges (T005/T006/T007).

Why generated: the blueprint's WP0 exists because "declared", "unit-tested" and
"wired" were being used interchangeably. A hand-written matrix reproduces that
error, because the person writing it believes what they remember. This script
answers three questions mechanically and refuses to answer the fourth:

* **Does it exist?** — the module file is present.
* **Is it reached from production code?** — some non-test module under ``apps/``
  imports it. That is what "wired" means here, and nothing weaker counts.
* **Is it pinned by tests?** — which test files import it, and how many tests
  live in those files.
* **Is it live-proven?** — *not answered*. That requires an end-to-end run
  against real infrastructure, and no amount of static analysis substitutes for
  it. The column is emitted as ``NOT_PROVEN`` unless an evidence file exists
  under ``benchmarks/evidence/``.

The two static answers are still worth having: they separate "implemented and
unused" from "implemented and called", which is the distinction 030's audit
found missing.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APPS = ROOT / "apps"
OUT_MD = ROOT / "specs/032-global-upgrade-execution/benchmarks/WP0-capability-matrix.md"
OUT_JSON = ROOT / "specs/032-global-upgrade-execution/benchmarks/WP0-capability-matrix.json"
EVIDENCE = ROOT / "specs/032-global-upgrade-execution/benchmarks/evidence"


@dataclass
class Capability:
    """One row of the matrix."""

    id: str
    claim: str
    module: str
    requirement: str = ""
    writers: list[str] = field(default_factory=list)
    importers: list[str] = field(default_factory=list)
    tests: list[str] = field(default_factory=list)
    notes: str = ""


#: Curated from the blueprint's §2 authority table and Feature 032's FR set. The
#: 030 audit warns that a matrix which only lists what someone remembered is
#: worthless, so every row here is a *seam* the spec names, not a module that
#: merely looked interesting.
CAPABILITIES: tuple[Capability, ...] = (
    Capability("artifact-sink", "the one ingestion seam for every executor", "apps/acquisition/artifact_sink.py", "FR-001..FR-005"),
    Capability("observation-gate", "capture/observation identity, lifecycle, publication", "apps/shared/events/observation_gate.py", "FR-002..FR-005"),
    Capability("observation-identity", "deterministic capture/observation ids", "apps/shared/domain/observation_identity.py", "FR-002"),
    Capability("event-outbox", "transactional publication", "apps/control-plane/db/materialization_outbox.py", "FR-004"),
    Capability("event-envelope", "canonical event envelope", "apps/shared/events/kafka.py", "FR-004"),
    Capability("content-router", "ref-only event routing", "apps/shared/events/content_router.py", "FR-004"),
    Capability("durable-dlq", "quarantine + replay", "apps/shared/events/dlq_durable.py", "FR-012"),
    Capability("operator-result", "universal operator envelope", "apps/shared/contracts/operator_result.py", "FR-014"),
    Capability("evidence-span", "typed span contract", "apps/shared/contracts/evidence_span.py", "FR-016..FR-018"),
    Capability("stage-outcome", "closed outcome taxonomy", "apps/shared/contracts/stage_outcome.py", "FR-012"),
    Capability("canonical-serialisation", "deterministic digests", "apps/shared/contracts/canonical.py", "FR-002"),
    Capability("projection-manifest", "projection reproducibility record", "apps/shared/contracts/projection_manifest.py", "FR-006"),
    Capability("error-codes", "stable machine-readable codes", "apps/shared/contracts/error_codes.py", "FR-012"),
    Capability("graph-invariant", "versioned relational invariant / worldline", "apps/shared/domain/graph_invariant.py", "FR-026, FR-028"),
    Capability("invariant-reducer", "deterministic reduction from the accepted stream", "apps/control-plane/context_engine/invariant_reducer.py", "FR-026"),
    Capability("context-engine", "research process kernel", "apps/control-plane/context_engine/engine.py", "FR-046..FR-053"),
    Capability("context-store", "durable context state", "apps/control-plane/context_engine/postgres_store.py", "FR-046"),
    Capability("evidence-context", "content-addressed interpretation frame", "apps/shared/domain/evidence_context.py", "FR-019"),
    Capability("identity-resolution", "candidate generation and decisions", "apps/admission/resolution/candidate.py", "FR-026..FR-028"),
    Capability("conflict-detection", "admission gate: comparability + conflict outcome", "apps/admission/engine/admission.py", "FR-029..FR-034"),
    Capability("admission-decisions", "the only committer of identity/claim decisions", "apps/admission/resolution/decision_store.py", "FR-034"),
    Capability("websearch", "entity-driven discovery", "apps/shared/websearch/discovery.py", "FR-013"),
    Capability(
        "temporal-filter",
        "CURRENT / AS_OF / INTERVAL selection over dated facts",
        "apps/science/context/temporal_filter.py",
        "FR-037",
        notes="tested and deliberately unwired: no executor consumes the temporal clause yet",
    ),
    Capability("badges", "capability routing façade (public package surface)", "apps/control-plane/badges/__init__.py", "FR-040"),
    Capability("donor-registry", "FR-113 supply-chain record", "donors/registry.yaml", "FR-038"),
    Capability("layer-boundaries", "cross-layer dependency guard", "apps/shared/tools/layer_boundaries.py", "FR-006"),
    Capability("interpretation-lane", "reproducible extraction lane", "apps/interpretation/extractors/lane.py", "FR-014"),
    Capability("parser-registry", "parser dispatch + offset semantics", "apps/interpretation/parsers/registry.py", "FR-016"),
    Capability("projection-search", "lexical serving projection", "apps/projection/search/index.py", "FR-006"),
    Capability("projection-graph", "graph serving projection", "apps/projection/graph/relation_store.py", "FR-006"),
)


def _module_names(path: Path) -> set[str]:
    """Dotted import spellings that could resolve to ``path``.

    The repository puts ``apps/<layer>`` and ``apps/shared`` on ``sys.path``, so a
    module is imported as a flat dotted name (``from contracts.evidence_span import``)
    rather than as ``apps.shared.contracts...``. Both spellings are derived.
    """
    rel = path.relative_to(ROOT).as_posix()
    if not rel.endswith(".py"):
        return set()
    stem = rel[:-3]
    # A package's public surface is its ``__init__``; ``from badges import X`` imports
    # ``badges``, never ``badges.__init__``, so the package name must be matchable.
    package_only = stem.endswith("/__init__") or stem == "__init__"
    if package_only:
        stem = stem.removesuffix("/__init__") if stem != "__init__" else "__init__"
    names: set[str] = set()
    names.add(stem.replace("/", "."))
    parts = stem.split("/")
    if len(parts) >= 3 and parts[0] == "apps":
        # apps/shared/contracts/x.py -> shared.contracts.x and contracts.x
        names.add(".".join(parts[1:]))
        names.add(".".join(parts[2:]))
        if len(parts) >= 4:
            names.add(".".join(parts[3:]))
    return names


def _imports_in(path: Path) -> set[str]:
    """Every absolute dotted module name imported by ``path``."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, SyntaxError):
        return set()
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            found.add(node.module)
    return found


def _importers(module_names: set[str]) -> tuple[list[str], list[str]]:
    production: list[str] = []
    tests: list[str] = []
    for path in APPS.rglob("*.py"):
        parts = path.parts
        if "__pycache__" in parts or path.name.startswith("test_") or "tests" in parts:
            continue
        imported = _imports_in(path)
        if any(
            imported_name == target or imported_name.startswith(target + ".")
            for imported_name in imported
            for target in module_names
        ):
            production.append(path.relative_to(ROOT).as_posix())
    for path in APPS.rglob("test_*.py"):
        if "__pycache__" in path.parts:
            continue
        imported = _imports_in(path)
        if any(
            imported_name == target or imported_name.startswith(target + ".")
            for imported_name in imported
            for target in module_names
        ):
            tests.append(path.relative_to(ROOT).as_posix())
    return sorted(production), sorted(tests)


def _test_count(path: Path) -> int:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, SyntaxError):
        return 0
    return sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
    )


def _evidence(capability_id: str) -> str:
    """An end-to-end evidence artefact, if one was actually recorded."""
    if not EVIDENCE.is_dir():
        return ""
    for candidate in sorted(EVIDENCE.glob(f"*{capability_id}*")):
        if candidate.is_file():
            return candidate.relative_to(ROOT).as_posix()
    return ""


def _referencers(literal: str) -> tuple[list[str], list[str]]:
    """Files that name ``literal`` (a repository-relative path) in their text.

    A data artefact — the donor registry, a schema, a fixture — has no import
    edge. Its "caller" is whatever reads it by path, so the reachability question
    has to be asked of the text rather than the AST.
    """
    production: list[str] = []
    tests: list[str] = []
    needle = literal.replace("\\", "/")
    for path in APPS.rglob("*"):
        if path.suffix not in {".py", ".ts", ".tsx", ".ps1", ".sh"}:
            continue
        parts = path.parts
        if "__pycache__" in parts or "node_modules" in parts:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if needle not in text:
            continue
        rel = path.relative_to(ROOT).as_posix()
        if path.name.startswith("test_") or "tests" in parts:
            tests.append(rel)
        else:
            production.append(rel)
    return sorted(production), sorted(tests)


def _row(cap: Capability) -> dict[str, object]:
    path = ROOT / cap.module
    exists = path.exists()
    if path.suffix == ".py":
        module_names = _module_names(path)
        production, tests = _importers(module_names) if module_names else ([], [])
    else:
        production, tests = _referencers(cap.module)
    test_count = sum(_test_count(ROOT / t) for t in tests if t.endswith(".py"))
    evidence = _evidence(cap.id)
    if not exists:
        status = "MISSING"
    elif production and tests:
        status = "WIRED_AND_TESTED"
    elif production:
        status = "WIRED_UNTESTED"
    elif tests:
        status = "TEST_ONLY"
    else:
        status = "IMPLEMENTED_UNREFERENCED"
    return {
        "id": cap.id,
        "claim": cap.claim,
        "module": cap.module,
        "exists": exists,
        "requirement": cap.requirement,
        "status": status,
        "production_importers": production,
        "test_files": tests,
        "test_count": test_count,
        "live_proven": evidence or "NOT_PROVEN",
        "notes": cap.notes,
    }


def build() -> list[dict[str, object]]:
    return [_row(cap) for cap in CAPABILITIES]


STATUS_LEGEND = {
    "WIRED_AND_TESTED": "reached from production code and pinned by tests",
    "WIRED_UNTESTED": "reached from production code, no test imports it — a live risk",
    "TEST_ONLY": "only tests reach it; production does not call it",
    "IMPLEMENTED_UNREFERENCED": "present but nothing imports it",
    "MISSING": "the spec names it; the file is not there",
}


def render(rows: list[dict[str, object]]) -> str:
    counts: dict[str, int] = {}
    for row in rows:
        counts[str(row["status"])] = counts.get(str(row["status"]), 0) + 1

    lines = [
        "# WP0 Capability Matrix",
        "",
        "**Feature**: `032-global-upgrade-execution` · **Generated by**: `tools/specs/build_capability_matrix.py`",
        "",
        "Static analysis over the executing tree. Regenerate rather than edit: a hand-written matrix",
        "records what someone remembers, and the reason WP0 exists is that memory and reality diverged.",
        "",
        "## Status vocabulary",
        "",
        "| Status | Meaning |",
        "|---|---|",
    ]
    lines += [f"| `{key}` | {value} |" for key, value in STATUS_LEGEND.items()]
    lines += [
        "",
        "`live_proven` is answered **only** by an artefact under `benchmarks/evidence/`. No static",
        "analysis can produce it, and with Postgres/MinIO/Kafka absent on this host no capability can",
        "claim it. `NOT_PROVEN` is the honest value, not a missing one.",
        "",
        "## Summary",
        "",
        "| Status | Count |",
        "|---|---|",
    ]
    lines += [f"| `{key}` | {counts[key]} |" for key in sorted(counts)]
    lines += [f"| **total** | **{len(rows)}** |", "", "## Matrix", ""]
    lines += [
        "| Capability | Requirement | Status | Production importers | Test files | Tests | Live-proven |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        importers = row["production_importers"]
        shown = ", ".join(f"`{p}`" for p in importers[:2]) or "—"
        if len(importers) > 2:
            shown += f" (+{len(importers) - 2})"
        lines.append(
            f"| `{row['id']}` | {row['requirement']} | `{row['status']}` | {shown} | "
            f"{len(row['test_files'])} | {row['test_count']} | `{row['live_proven']}` |"
        )

    interesting = [
        row for row in rows if row["status"] in {"TEST_ONLY", "IMPLEMENTED_UNREFERENCED", "WIRED_UNTESTED", "MISSING"}
    ]
    lines += ["", "## Rows that are not simply wired-and-tested", ""]
    if not interesting:
        lines.append("None. Every listed capability is both reached from production and pinned by a test.")
    for row in interesting:
        lines.append(f"### `{row['id']}` — `{row['status']}`")
        lines.append("")
        lines.append(f"- claim: {row['claim']}")
        lines.append(f"- module: `{row['module']}`")
        if row["production_importers"]:
            lines.append("- production importers: " + ", ".join(f"`{p}`" for p in row["production_importers"]))
        else:
            lines.append("- production importers: **none found**")
        lines.append(f"- test files: {len(row['test_files'])}")
        lines.append("")

    lines += ["", "## Findings that change the plan", ""]
    lines.append(
        "These were verified by hand after the matrix flagged them: the import graph said "
        "\"no production caller\", and reading the code showed *why*. They are the reason WP0 "
        "is a gate rather than a report."
    )
    lines.append("")
    lines += FINDINGS
    return "\n".join(lines) + "\n"


#: Verified findings. A finding is only listed here after the import graph flagged the
#: row *and* the code was read: the matrix is the detector, not the verdict.
FINDINGS = [
    "### F1 — two `OperatorResult` types — **bridged, not merged**",
    "",
    "`apps/shared/contracts/operator_result.py` is the contract Feature 032's FR-014 names. It had 51",
    "tests and **no production importer**, while `apps/science/context/operators/base.py:167` defines",
    "a *second* `OperatorResult` that `adapters.py:44` actually returns.",
    "",
    "**Bridged in this session.** `apps/science/context/operators/contract_bridge.py` converts a",
    "science result into the canonical envelope, and 13 tests pin the conversion. The types were",
    "deliberately **not** merged: they answer different questions. The science type records what one",
    "calculation produced; the contract records one operator run over one input set for one tenant,",
    "with replay identity, evidence and cost. The bridge therefore *requires* the context the science",
    "type lacks (identity, inputs, output, start time) instead of inventing it — and the contract",
    "refused three of the bridge's first drafts, each time correctly:",
    "",
    "- an output that derives from claims rather than raw bytes must declare that, not look grounded;",
    "- a success with no evidence refs must name the reason in `missingness`;",
    "- a non-deterministic run must name its model, and a `BLOCKED` result must carry an error code.",
    "",
    "Those refusals are the finding: the gap between the two types is real, and it is now stated in",
    "code where a caller meets it, rather than at the far end of a pipeline.",
    "",
    "### F2 — `ProjectionManifest` had no production consumer — **resolved**",
    "",
    "The contract existed (`apps/shared/contracts/projection_manifest.py`) with 24 tests and no",
    "production importer. FR-006 requires every projection to carry one; no projection did. The",
    "tests proved the type was well-formed, not that it was used.",
    "",
    "**Closed in this session.** `apps/projection/search/projector.py` now imports the contract and",
    "`rebuild()` returns a manifest: a source cut, an input snapshot digest, an output digest over",
    "the documents actually written, and `rebuildable` reflecting whether the batch is durable.",
    "`apps/projection/tests/contract/test_search_projection_manifest.py` pins 9 properties — "
    "including that a changed body moves the output digest and an unchanged batch reproduces the",
    "fingerprint. The row above now reads `WIRED_AND_TESTED`; the generator detected the adoption",
    "without being told.",
    "",
    "### F3 — two DLQ implementations; production reaches the non-durable one",
    "",
    "`apps/shared/events/dlq_durable.py` is test-only. `apps/control-plane/api/routes/quarantine.py:13`",
    "imports the other one. The blueprint's quarantine-replay requirement (FR-012) is therefore",
    "served by the non-durable path, and `dlq_durable`'s 9 tests pin behaviour nothing runs.",
    "",
    "### F4 — rows whose `TEST_ONLY` status is correct by design",
    "",
    "`layer-boundaries` is a build-time guard and `donor-registry` is a supply-chain record: neither",
    "should have a runtime caller. They are listed rather than hidden, so that the five findings",
    "above cannot be mistaken for seven.",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    rows = build()
    markdown = render(rows)
    if args.check:
        if not OUT_JSON.is_file():
            print("capability matrix JSON is missing")
            return 1
        current = json.loads(OUT_JSON.read_text(encoding="utf-8"))
        if current != rows:
            print("capability matrix is out of date; rerun without --check")
            return 1
        print("capability matrix is up to date")
        return 0

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text(markdown, encoding="utf-8")
    OUT_JSON.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    counts: dict[str, int] = {}
    for row in rows:
        counts[str(row["status"])] = counts.get(str(row["status"]), 0) + 1
    print(f"wrote {OUT_MD.relative_to(ROOT)}: {len(rows)} capabilities {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
