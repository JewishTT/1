"""Build the dynamic platform documentation.

Usage::

    python -m platform_model.build            # write docs/platform/*
    python -m platform_model.build --json     # print the model to stdout
    python -m platform_model.build --check    # exit 1 if the committed docs drifted

The model is derived from the tree. ``--check`` is what makes it a gate: a
commit that changes the platform without regenerating the docs fails.

Two machine artifacts are written:

``platform-model.json``
    The summary model — aggregates, contracts, API, capabilities, ownership.
    Small enough to read and to diff.
``modules.jsonl``
    The per-module detail, one JSON object per line. Line-oriented so a diff
    shows the module that changed, not a 40 000-line reformat.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import sysconfig
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "platform"
OUT_JSON = OUT / "platform-model.json"
OUT_MODULES = OUT / "modules.jsonl"

SCAN_ROOTS = ("apps", "bench", "tools", "deploy", "platform_model")
EXTRA_ROOT_FILES = ("conftest.py",)

#: path parts that mark a file as "installed dependency", not platform code.
#: The virtualenv is checked out inside the repository, so a naive path
#: containment check would classify every third-party package as local code.
_VENV_PARTS = frozenset({".venv", "venv", "site-packages", "dist-packages", "node_modules"})

#: import prefix -> repo-relative directory. The platform's packages are imported
#: by their *directory* name (conftest.py puts each app dir on sys.path), and
#: ``apps/shared`` puts each of its subpackages at top level, so ``contracts``
#: resolves to ``apps/shared/contracts``.
#:
#: This table is a fallback. The authoritative mapping is derived at runtime from
#: the platform's own ``sys.path`` -- see :func:`import_roots` -- because a hand
#: maintained table of import roots is exactly the thing that goes stale when a
#: package moves.
IMPORT_ROOTS = {
    "contracts": "apps/shared/contracts",
    "events": "apps/shared/events",
    "domain": "apps/shared/domain",
    "storage": "apps/shared/storage",
    "config": "apps/shared/config",
    "ids": "apps/shared/ids",
    "net": "apps/shared/net",
    "network": "apps/shared/network",
    "observability": "apps/shared/observability",
    "scoring": "apps/shared/scoring",
    "semantic": "apps/shared/semantic",
    "tools": "apps/shared/tools",
    "websearch": "apps/shared/websearch",
    "workflow": "apps/shared/workflow",
    "datasets": "apps/shared/datasets",
    "donor": "apps/shared/donor",
    "acquisition": "apps/acquisition",
    "admission": "apps/admission",
    "interpretation": "apps/interpretation",
    "projection": "apps/projection",
    "feedback": "apps/feedback",
    "science": "apps/science",
    "zero": "apps/zero/zero",
    "specops": "apps/specops",
    "api": "apps/control-plane/api",
    "db": "apps/control-plane/db",
    "services": "apps/control-plane/services",
    "application": "apps/control-plane/application",
    "workflows": "apps/control-plane/workflows",
    "badges": "apps/control-plane/badges",
    "modifier": "apps/control-plane/modifier",
    "cp_domain": "apps/control-plane/cp_domain",
    "context_engine": "apps/control-plane/context_engine",
    "semantic_path": "apps/control-plane/semantic_path",
    "bulk_ingestion": "apps/bulk-ingestion",
    "bench": "bench/bench",
}

COMPONENTS = {
    "shared": ("apps/shared", "Contracts, events, domain invariants, storage, security — the substrate every app imports."),
    "control-plane": ("apps/control-plane", "FastAPI control plane: investigations, context engine, frontier, review, query planner, HTTP API."),
    "acquisition": ("apps/acquisition", "Discovery, frontier, dispatcher, content router, HTTP/browser workers, ArtifactSink."),
    "interpretation": ("apps/interpretation", "Parsers, deterministic entity-extraction stack, NER/normalization, candidate aggregation."),
    "admission": ("apps/admission", "Blocking/resolution, assertion extraction, source independence, calibrated admission."),
    "projection": ("apps/projection", "Graph abstraction, search/analytics projectors, snapshots, TDA."),
    "feedback": ("apps/feedback", "Recrawl/priority feedback, stopping policy."),
    "science": ("apps/science", "Context operators, fabric, retrieval economics, abstraction ladder."),
    "zero": ("apps/zero", "Zero-layer contact harvesting from arbitrary seeds."),
    "specops": ("apps/specops", "Isolated spec-ops lab profile (never in the routine path)."),
    "bulk-ingestion": ("apps/bulk-ingestion", "Common Crawl / Wayback / WARC / dataset backfill profiles."),
    "webapp": ("apps/webapp", "React analyst surfaces: investigation, search, entity, finding, ops, lineage."),
    "bench": ("bench", "E2E smoke harness, micro-benchmarks, knowledge-quality harness."),
    "tools": ("tools", "Generators, capability/owner/donor tools, probes."),
    "platform_model": ("platform_model", "The generator that produces docs/platform from the tree."),
    "deploy": ("apps/deploy", "Docker Compose dev topology, Grafana, k8s configs."),
    "root": (".", "Repo-root wiring: pytest conftest and the import roots it installs."),
}

PIPELINE = [
    ("context", "Context & obligation creation", ["context_engine", "investigation_context", "obligations", "store"]),
    ("planning", "Policy-first capability planning", ["catalogue_bridge", "tool_catalog", "frontier", "scheduler"]),
    ("acquisition", "Acquisition (raw-first)", ["artifact_sink", "cc_plan", "entity_search", "sources", "dispatcher"]),
    ("seam", "Observation gate & outbox", ["observation_gate", "bus", "kafka", "evidence_store_guard"]),
    ("interpretation", "Parsing & extraction", ["parsers", "extractors", "aggregation", "normalization"]),
    ("identity", "Identity resolution & admission", ["blocking", "splink_adapter", "decision_store", "resolution"]),
    ("fabric", "Claims, conflicts, independence", ["fabric", "capture_interpretation", "independence", "scoring"]),
    ("projection", "Rebuildable projections", ["search", "temporal_materialization", "tda", "graph"]),
    ("loop", "Closed loop / frontier", ["feedback", "gain", "frontier", "stopping"]),
    ("report", "Report & completion", ["findings", "report", "dossier"]),
]


# ---------------------------------------------------------------------------
# scanning
# ---------------------------------------------------------------------------

def _scan_python_batch(batch: list[tuple[str, str]]) -> list[dict]:
    """Worker entry point: scan a batch of Python files in a separate process."""
    from .scanners import scan_python

    root = Path(batch[0][1])
    return [scan_python(root / rel, root) for rel, _ in batch]


def _scan_ts_batch(batch: list[tuple[str, str]]) -> list[dict]:
    """Worker entry point: scan a batch of TypeScript files."""
    from .scanners import scan_typescript

    root = Path(batch[0][1])
    return [scan_typescript(root / rel, root) for rel, _ in batch]


def _scan_rust_batch(batch: list[tuple[str, str]]) -> list[dict]:
    """Worker entry point: scan a batch of Rust files."""
    from .scanners import scan_rust

    root = Path(batch[0][1])
    return [scan_rust(root / rel, root) for rel, _ in batch]


def _batched(root: Path, files: list[Path], worker) -> list[dict]:
    """Run a scan over ``files`` in parallel, chunked by file count."""
    unique = sorted(set(files))
    if not unique:
        return []
    # the scan is IO bound (the parser waits on the file system), so it gets
    # more processes than there are cores
    workers = min(max((os.cpu_count() or 1) * 2, 4), 16, len(unique))
    chunk = max(1, len(unique) // workers)
    batches = [
        [(p.relative_to(root).as_posix(), str(root)) for p in unique[i : i + chunk]]
        for i in range(0, len(unique), chunk)
    ]
    if workers == 1 or len(batches) == 1:
        return [m for batch in batches for m in worker(batch)]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(worker, batches))
    return [m for batch in results for m in batch]


def collect_python(root: Path) -> list[dict]:
    """Scan every Python file in the tree.

    Parsing ~950 modules dominates the build, and it is embarrassingly
    parallel, so the work is spread over processes.
    """
    from .scanners import iter_files

    files: list[Path] = []
    for base in SCAN_ROOTS:
        files.extend(iter_files(root / base, {".py"}))
    for name in EXTRA_ROOT_FILES:
        p = root / name
        if p.exists():
            files.append(p)
    return _batched(root, files, _scan_python_batch)


def collect_ts(root: Path) -> list[dict]:
    from .scanners import iter_files

    files: list[Path] = []
    for base in SCAN_ROOTS:
        files.extend(iter_files(root / base, {".ts", ".tsx"}))
    return _batched(root, files, _scan_ts_batch)


def collect_rust(root: Path) -> tuple[list[dict], list[dict]]:
    from .scanners import iter_files, scan_cargo

    files: list[Path] = []
    for base in SCAN_ROOTS:
        files.extend(iter_files(root / base, {".rs"}))
    modules = _batched(root, files, _scan_rust_batch)
    crates = [scan_cargo(p, root) for p in sorted(iter_files(root / "apps", {".toml"})) if p.name == "Cargo.toml"]
    return modules, crates


# ---------------------------------------------------------------------------
# import graph
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def canonical_sys_path() -> tuple[str, ...]:
    """The import path the platform itself declares, in a clean interpreter.

    The model's import resolution must not depend on the process that happens to
    be running it: pytest puts test package directories on ``sys.path``, a
    notebook puts its own directory first, and the two resolve the same import
    to different files. The platform's own contract is what ``conftest.py``
    establishes, so it is read from a fresh interpreter whose ``sys.path``
    contains nothing but the working directory and the standard library.
    """
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME")}
    env["PYTHONNOUSERSITE"] = "1"
    code = "import json, sys, conftest; print(json.dumps(sys.path))"
    try:
        proc = subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError):
        return tuple(sys.path)
    if proc.returncode != 0:
        return tuple(sys.path)
    try:
        paths = json.loads(proc.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return tuple(sys.path)
    return tuple(str(p) for p in paths)


@lru_cache(maxsize=1)
def _sys_path_index() -> tuple[tuple[str, frozenset[str], frozenset[str]], ...]:
    """One listing per import path entry: the module stems and directory names.

    Listing each path entry once and answering from that listing turns
    resolution into dictionary lookups. Asking the filesystem per candidate
    name costs ~45 ms, because each question is answered with several stats
    on a directory tree that has tens of thousands of files.
    """
    entries: list[tuple[str, frozenset[str], frozenset[str]]] = []
    for entry in canonical_sys_path():
        if not entry:
            continue
        base = Path(entry)
        try:
            if not base.is_dir():
                continue
            modules: set[str] = set()
            dirs: set[str] = set()
            for child in base.iterdir():
                name = child.name
                if name.startswith("."):
                    continue
                try:
                    if child.is_dir():
                        dirs.add(name)
                    elif child.suffix == ".py":
                        modules.add(name[:-3])
                except OSError:
                    continue
        except OSError:
            continue
        entries.append((str(base), frozenset(modules), frozenset(dirs)))
    return tuple(entries)


def _resolve_on_sys_path(name: str) -> Path | None:
    """Where a top-level import name lands, by walking ``sys.path`` directly.

    ``importlib.util.find_spec`` answers the same question but costs ~30 ms per
    name because it imports parent packages and consults every path finder. The
    build asks this question for every import name in the tree, so the walk is
    done by hand, in the order the interpreter uses: a regular package or
    module anywhere on the path wins, and a namespace directory is only used
    when nothing else matched.
    """
    index = _sys_path_index()
    namespace: Path | None = None
    for base, modules, dirs in index:
        if name in dirs:
            init = Path(base) / name / "__init__.py"
            try:
                if init.is_file():
                    return init
            except OSError:
                pass
            if namespace is None:
                namespace = Path(base) / name
        if name in modules:
            return Path(base) / f"{name}.py"
    return namespace


def import_roots(candidates: list[str]) -> dict[str, str]:
    """Map every importable top-level name to the repo directory it resolves to.

    The platform resolves its own packages by directory name, and the mapping is
    decided by the ``sys.path`` that ``conftest.py`` builds. Asking the
    interpreter where a name lands is the only way to get this right: the
    directory names are not derivable from the import statements themselves, and
    a hand-maintained table of them goes stale the first time a package moves.

    Names that do not resolve to anything inside the repository are not platform
    packages, so they are simply absent from the result.
    """
    roots: dict[str, str] = {}
    for name in candidates:
        origin_path = _resolve_on_sys_path(name)
        if origin_path is None:
            continue
        try:
            rel = origin_path.resolve().relative_to(ROOT)
        except (ValueError, OSError):
            continue
        # the virtualenv lives inside the repository, so an installed package
        # is technically "in the tree". It is not platform code.
        if any(part in _VENV_PARTS for part in rel.parts):
            continue
        roots[name] = rel.as_posix()
    return roots


def import_candidates(
    module: str, level: int, path: str, roots: dict[str, str], names: tuple[str, ...] = ()
) -> list[tuple[str, str]]:
    """Candidate repo-relative files an import statement could mean.

    The platform imports its own packages by *directory* name, and several of
    those directories nest a second package of the same name
    (``apps/feedback/feedback/``). The candidate list keeps the alternatives so
    the caller can pick the one that actually exists.

    Each candidate is a ``(path, dotted_name)`` pair: the dotted name is the
    module the edge is really about, which differs from the imported name when
    the import pulls a submodule (``from knowledge import quality``).
    """
    out: list[tuple[str, str]] = []
    if level:
        parts = path.split("/")[:-1]
        for _ in range(level - 1):
            if parts:
                parts.pop()
        rest = [s for s in module.split(".") if s]
        base = "/".join(parts + rest)
        if base:
            out.append((base + ".py", module))
            out.append((base + "/__init__.py", module))
        elif parts:
            out.append(("/".join(parts) + "/__init__.py", module))
        return out
    parts = module.split(".")
    for n in range(len(parts), 0, -1):
        prefix = ".".join(parts[:n])
        base = roots.get(prefix)
        if base:
            rest = parts[n:]
            if base.endswith("/__init__.py"):
                base = base[: -len("/__init__.py")]
            elif base.endswith(".py"):
                base = base[: -len(".py")]
            rel = "/".join([base] + rest) if rest else base
            out.append((rel + ".py", module))
            out.append((rel + "/__init__.py", module))
            for name in names:
                out.append((f"{rel}/{name}.py", f"{module}.{name}"))
                out.append((f"{rel}/{name}/__init__.py", f"{module}.{name}"))
            break
    suffix = module.replace(".", "/")
    out.append((suffix + ".py", module))
    out.append((suffix + "/__init__.py", module))
    return out


@lru_cache(maxsize=1)
def _stdlib_roots() -> frozenset[str]:
    return frozenset(getattr(sys, "stdlib_module_names", ()))


@lru_cache(maxsize=1)
def _thirdparty_roots() -> frozenset[str]:
    """Top-level names installed in the interpreter that runs this tool.

    Cached: this walks site-packages, and it is consulted once per import
    statement. Uncached it cost more than the rest of the build combined.
    """
    names: set[str] = set()
    for key in ("purelib", "platlib"):
        base = sysconfig.get_paths().get(key)
        if not base:
            continue
        p = Path(base)
        if not p.exists():
            continue
        for child in p.iterdir():
            if child.name.startswith("__") or child.name.endswith((".dist-info", ".egg-info", ".pth")):
                continue
            if child.is_dir():
                names.add(child.name)
            elif child.suffix == ".py":
                names.add(child.stem)
    return frozenset(names)


@lru_cache(maxsize=8)
def _declared_dependencies(root: Path) -> frozenset[str]:
    """Distribution names declared by any workspace manifest."""
    names: set[str] = set()
    try:
        import tomllib
    except ModuleNotFoundError:  # pragma: no cover - py<3.11
        return names
    manifests = list(root.glob("pyproject.toml"))
    manifests += list(root.glob("apps/*/pyproject.toml"))
    manifests += list(root.glob("bench/pyproject.toml"))
    for p in manifests:
        try:
            data = tomllib.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        project = data.get("project", {})
        groups = [project.get("dependencies", [])]
        for extra in (project.get("optional-dependencies") or {}).values():
            groups.append(extra)
        for group in groups:
            for spec in group:
                name = re.split(r"[\s<>=!~\[;]", spec.strip(), 1)[0]
                if name:
                    names.add(name.replace("_", "-").lower())
    return frozenset(names)


def _is_declared(top: str, declared: set[str]) -> bool:
    """Match an import name against a declared distribution name.

    Distribution and import names differ (``pyahocorasick`` vs
    ``ahocorasick``, ``pyyaml`` vs ``yaml``), so a declared name that ends
    with the import name counts as a match.
    """
    norm = top.replace("_", "-").lower()
    if norm in declared:
        return True
    return any(name.endswith(norm) for name in declared)


@lru_cache(maxsize=None)
def classify_import(module: str, level: int, declared: frozenset[str], roots: frozenset[str]) -> str:
    """``local`` | ``stdlib`` | ``third-party`` | ``declared-not-installed`` | ``unknown``.

    ``unknown`` is the interesting bucket: a top-level name that is neither a
    platform root, nor an installed package, nor a declared dependency.
    It is a path shim the platform owns, or a genuinely broken import.
    """
    if level:
        return "local"
    top = module.split(".")[0]
    if top in roots:
        return "local"
    if top in _stdlib_roots():
        return "stdlib"
    if top in _thirdparty_roots():
        return "third-party"
    if _is_declared(top, declared):
        return "declared-not-installed"
    return "unknown"


_GUARD_MARKERS = ("not landed", "missing feature", "skipif")


def _leaf_exists(module: str, module_by_path: dict[str, dict]) -> bool:
    """True when the last segment of a dotted import names a real platform file."""
    leaf = module.rsplit(".", 1)[-1]
    if not leaf:
        return False
    return any(
        p.rsplit("/", 1)[-1] in (f"{leaf}.py", f"{leaf}.pyi") for p in module_by_path
    ) or any(p.endswith(f"/{leaf}/__init__.py") for p in module_by_path)


def _is_guarded_gap(root: Path, path: str, module: str) -> bool:
    """True when the platform knowingly guards a module that does not exist.

    The platform tracks missing features by importing them inside a ``try``
    and skipping the dependent tests. That is a tracked gap, not a broken
    import, and the model must not report it as one.
    """
    f = root / path
    try:
        text = f.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    leaf = module.split(".")[-1]
    if leaf not in text:
        return False
    return any(m in text.lower() for m in _GUARD_MARKERS)


def build_import_graph(py_modules: list[dict], root: Path) -> dict:
    module_by_path = {m["path"]: m for m in py_modules}
    # suffix index: last two path components -> modules ending with them.
    # A dotted import can only match a module whose path ends with the
    # dotted form, so indexing by the tail turns a linear scan of the whole
    # tree per import into a dictionary lookup.
    suffix_index: dict[str, list[str]] = defaultdict(list)
    for p in module_by_path:
        parts = p.split("/")
        if len(parts) >= 2:
            suffix_index["/".join(parts[-2:])].append(p)
    declared = _declared_dependencies(root)
    candidates = sorted(
        {imp["module"].split(".")[0] for m in py_modules for imp in m["imports"] if imp["module"]}
    )
    derived = import_roots(candidates)
    roots = {**IMPORT_ROOTS, **derived}
    root_names = frozenset(roots)
    edges: list[dict] = []
    local_unresolved: list[dict] = []
    external: dict[str, int] = defaultdict(int)
    optional: dict[str, int] = defaultdict(int)
    unknown: dict[str, int] = defaultdict(int)
    for m in py_modules:
        for imp in m["imports"]:
            module = imp["module"]
            level = imp.get("level", 0)
            kind = classify_import(module, level, declared, root_names)
            if kind in ("stdlib", "third-party", "declared-not-installed"):
                external[f"{kind}:{module.split('.')[0]}"] += 1
                continue
            target = None
            via = module
            names = tuple(imp.get("names") or ())
            # ``from pkg import sub`` is often a submodule import (``from api.routes
            # import fabric``). Resolving it to the package ``__init__`` alone hides the
            # edge to the submodule, which is exactly the edge reachability needs. Emit
            # an edge for every name that is itself a module; otherwise fall through to
            # the single-target resolution below.
            if level == 0 and names and module:
                sub_hit = False
                for name in names:
                    sub = f"{module}.{name}"
                    for cand, cand_via in import_candidates(sub, 0, m["path"], roots, ()):
                        if cand in module_by_path:
                            edges.append({"from": m["path"], "to": cand, "via": sub})
                            sub_hit = True
                            break
                if sub_hit:
                    continue
            for cand, cand_via in import_candidates(module, level, m["path"], roots, names):
                if cand in module_by_path:
                    target, via = cand, cand_via
                    break
            if target is None and level == 0:
                # a directory this module puts on sys.path can supply the name
                for base in m.get("path_roots", ()):
                    dotted = module.replace(".", "/")
                    extra = [(f"{base}/{dotted}.py", module), (f"{base}/{dotted}/__init__.py", module)]
                    for name in names:
                        extra.append((f"{base}/{dotted}/{name}.py", f"{module}.{name}"))
                        extra.append((f"{base}/{dotted}/{name}/__init__.py", f"{module}.{name}"))
                    for cand, cand_via in extra:
                        if cand in module_by_path:
                            target, via = cand, cand_via
                            break
                    if target:
                        break
            if target is None and level == 0:
                # the platform nests same-named packages; match the dotted
                # suffix against what actually exists in the tree.
                suffix = module.replace(".", "/")
                for cand in (f"{suffix}.py", f"{suffix}/__init__.py"):
                    tail = "/".join(cand.split("/")[-2:])
                    hits = sorted(
                        (p for p in suffix_index.get(tail, ()) if p.endswith(cand)),
                        key=lambda p: (len(p), p),
                    )
                    if hits:
                        target = hits[0]
                        break
            if target:
                edges.append({"from": m["path"], "to": target, "via": module})
                continue
            if kind == "local":
                # a platform package that cannot be imported is a defect even
                # when the import is guarded: the guard turns a crash into a
                # silently disabled feature -- unless the platform tracks the
                # feature as not landed, which is a different thing.
                if _is_guarded_gap(root, m["path"], module):
                    kind = "guarded-gap"
                elif imp.get("optional"):
                    kind = "guarded-local"
            elif kind == "unknown":
                if imp.get("optional"):
                    optional[module.split(".")[0]] += 1
                    continue
                if "." in module and _leaf_exists(module, module_by_path):
                    # a platform package that was renamed or removed: the leaf
                    # still exists in the tree under a different root.
                    kind = "stale-platform-path"
                else:
                    unknown[module] += 1
            local_unresolved.append({"from": m["path"], "import": module, "kind": kind})
    return {
        "edges": edges,
        "unresolved": local_unresolved,
        "external": dict(sorted(external.items())),
        "optional": dict(sorted(optional.items())),
        "unknown": dict(sorted(unknown.items())),
        "roots": dict(sorted(roots.items())),
        "module_count": len(py_modules),
        "edge_count": len(edges),
    }


def _is_test_path(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return "/tests/" in path or name.startswith("test_") or name.endswith("_test.py")


def component_of(path: str) -> str:
    parts = path.split("/")
    if len(parts) >= 2 and parts[0] == "apps":
        if parts[1] == "shared":
            return "shared"
        return parts[1]
    if len(parts) == 1:
        return "root"
    if parts[0] in COMPONENTS:
        return parts[0]
    return parts[0]


def build_components(py_modules: list[dict], ts_modules: list[dict]) -> list[dict]:
    groups: dict[str, dict] = {}
    for m in py_modules:
        comp = component_of(m["path"])
        g = groups.setdefault(comp, {"name": comp, "py": 0, "ts": 0, "tests": 0, "modules": []})
        g["py"] += 1
        g["modules"].append(m["module"])
    for m in ts_modules:
        comp = component_of(m["path"])
        g = groups.setdefault(comp, {"name": comp, "py": 0, "ts": 0, "tests": 0, "modules": []})
        g["ts"] += 1
    out = []
    for name, g in sorted(groups.items()):
        desc = COMPONENTS.get(name, (name, ""))[1]
        out.append(
            {
                "name": name,
                "description": desc,
                "python_modules": g["py"],
                "typescript_modules": g["ts"],
                "modules": sorted(set(g["modules"]))[:200],
            }
        )
    return out


# ---------------------------------------------------------------------------
# model
# ---------------------------------------------------------------------------

def build_model(root: Path) -> dict:
    from .semantic import (
        load_spec_artifacts,
        scan_api,
        scan_contract_docs,
        scan_python_contracts,
        scan_root_contracts,
        scan_tests,
    )

    py = collect_python(root)
    ts = collect_ts(root)
    rust, crates = collect_rust(root)
    graph = build_import_graph(py, root)
    components = build_components(py, ts)
    tests = scan_tests(root, py, graph["roots"])
    artifacts = load_spec_artifacts(root)

    from .architecture import build_architecture

    # A module is "tested" when some test file targets it (resolved through the
    # same import roots as the import graph). "Not imported by a test" is a fact
    # about reachability, not a claim about behavioural coverage.
    targeted: set[str] = set()
    for t in tests.values():
        targeted.update(t.get("targets", ()))
    untested = [
        m["path"]
        for m in py
        if not _is_test_path(m["path"]) and m["path"] not in targeted
    ]

    model = {
        "generated_from": str(root),
        "scan_roots": list(SCAN_ROOTS),
        "excluded": ["donors", "tmp", "logs", ".venv", "node_modules"],
        "components": components,
        "python": {"modules": py, "count": len(py)},
        "typescript": {"modules": ts, "count": len(ts)},
        "rust": {"modules": rust, "count": len(rust), "crates": crates},
        "import_graph": graph,
        "tests": {"by_file": sorted(tests.values(), key=lambda t: t["path"]), "total": sum(t["tests"] for t in tests.values())},
        "contracts": {
            "python": scan_python_contracts(root),
            "docs": scan_contract_docs(root),
            "root": scan_root_contracts(root),
        },
        "api": scan_api(root),
        "pipeline": PIPELINE,
        "capabilities": artifacts["capabilities"],
        "ownership": artifacts["ownership"],
        "donors": artifacts["donors"],
        "untested_modules": untested[:200],
        "untested_count": len(untested),
    }
    model["architecture"] = build_architecture(root, model)
    from .maturity import build_maturity
    model["maturity"] = build_maturity(root, model)
    from .reachability import build_reachability
    model["reachability"] = build_reachability(root, model)
    from .gaps import verify as verify_gaps
    model["gaps"] = verify_gaps(root)
    from .golden_path import build_golden_path, build_plan
    model["golden_path"] = build_golden_path(root, model)
    model["build_plan"] = build_plan(model["golden_path"])
    from .events import build_event_coverage
    model["event_coverage"] = build_event_coverage(root, model)
    try:
        from .evidence import build_evidence
        model["evidence"] = build_evidence(root, model)
    except Exception:
        model["evidence"] = {"facts": [], "stats": {"facts_total": 0, "static_facts": 0, "inferred": 0, "intended": 0}}
    return model


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------

def _md_table(headers: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(c).replace("|", "\\|") for c in r) + " |")
    return "\n".join(out)


def render_index(model: dict) -> str:
    comps = model["components"]
    g = model["import_graph"]
    by_kind: dict[str, int] = {}
    for u in g.get("unresolved", []):
        k = u.get("kind", "unknown")
        by_kind[k] = by_kind.get(k, 0) + 1
    unresolved_total = len(g.get("unresolved", []))
    lines = [
        "# COGNITIVE Platform — Dynamic Model",
        "",
        "Generated from the source tree by `platform_model/build.py`. **Do not edit by hand**;",
        "regenerate with `python -m platform_model.build`. `--check` fails the build when the",
        "committed model no longer matches the tree.",
        "",
        "## Scale",
        "",
        _md_table(
            ["Metric", "Value"],
            [
                ["Components", len(comps)],
                ["Python modules", model["python"]["count"]],
                ["TypeScript modules", model["typescript"]["count"]],
                ["Rust crates", len(model["rust"]["crates"])],
                ["Rust source files", model["rust"]["count"]],
                ["Import edges (local)", g["edge_count"]],
                ["Unresolved imports (no local target)", unresolved_total],
                ["Unresolved: local", by_kind.get("local", 0)],
                ["Unresolved: stale-platform-path", by_kind.get("stale-platform-path", 0)],
                ["Unresolved: guarded-local", by_kind.get("guarded-local", 0)],
                ["Unresolved: guarded-gap", by_kind.get("guarded-gap", 0)],
                ["Unresolved: unknown (undeclared)", by_kind.get("unknown", 0)],
                ["Test files", len(model["tests"]["by_file"])],
                ["Test functions", model["tests"]["total"]],
                ["Untested platform modules", model["untested_count"]],
                ["HTTP routes", sum(len(a["routes"]) for a in model["api"])],
                ["Contracts (python/docs/root)", f"{len(model['contracts']['python'])} / {len(model['contracts']['docs'])} / {len(model['contracts']['root'])}"],
                ["Capabilities", len(model["capabilities"])],
            ],
        ),
        "",
        "## Pages",
        "",
        "- [Components](components.md) — every service and what it owns.",
        "- [Contracts](contracts.md) — the typed cross-layer surface.",
        "- [API](api.md) — the HTTP surface.",
        "- [Data flow](data-flow.md) — the canonical pipeline and the gaps.",
        "- [Import graph](imports.md) — who imports whom, and what does not resolve.",
        "- [Maturity](maturity.md) — which modules are built, primitive, or stubs.",
        "- [Reachability](reachability.md) — what production can actually reach.",
        "- [Tests](tests.md) — coverage and what is untested.",
        "- [Capabilities](capabilities.md) — WIRED vs TEST_ONLY vs MISSING.",
        "- [Ownership](ownership.md) — one writer per object, and the competing writers.",
        "- [Donors](donors.md) — the supply-chain record.",
        "- [Findings](findings.md) — what the model says is broken.",
        "- [Gaps](gaps.md) — machine-checked defects with re-checkable evidence.",
        "- [Golden path](golden-path.md) — the person-background path, capability by capability.",
        "",
        "## Components",
        "",
        _md_table(
            ["Component", "Python", "TS", "Description"],
            [[c["name"], c["python_modules"], c["typescript_modules"], c["description"]] for c in comps],
        ),
        "",
    ]
    return "\n".join(lines)


def render_components(model: dict) -> str:
    lines = ["# Components", "", "One row per deployable unit / package root.", ""]
    for c in model["components"]:
        lines.append(f"## `{c['name']}`")
        lines.append("")
        lines.append(c["description"])
        lines.append("")
        lines.append(
            f"Python modules: **{c['python_modules']}** · TypeScript modules: **{c['typescript_modules']}**"
        )
        lines.append("")
        if c["modules"]:
            lines.append("<details><summary>module sample</summary>")
            lines.append("")
            lines.append("```")
            lines.extend(c["modules"][:40])
            lines.append("```")
            lines.append("")
            lines.append("</details>")
        lines.append("")
    return "\n".join(lines)


def render_contracts(model: dict) -> str:
    c = model["contracts"]
    lines = [
        "# Contracts",
        "",
        "The typed surface other layers must not bypass. Python contracts carry the dataclasses/enums;",
        "the markdown contracts carry the prose contract; the root YAML/JSON carry request/response schemas.",
        "",
        "## Python contracts",
        "",
        _md_table(
            ["Contract", "Path", "Classes", "Functions"],
            [
                [
                    f"`{p['name']}`",
                    f"`{p['path']}`",
                    ", ".join(f"`{x}`" for x in p["classes"][:8]),
                    ", ".join(f"`{x}`" for x in p["functions"][:8]),
                ]
                for p in c["python"]
            ],
        ),
        "",
        "## Contract documents",
        "",
        _md_table(["Document", "Path"], [[f"`{d['name']}`", f"`{d['path']}`"] for d in c["docs"]]),
        "",
        "## Root schemas",
        "",
        _md_table(["Schema", "Path", "Kind"], [[f"`{d['name']}`", f"`{d['path']}`", d["kind"]] for d in c["root"]]),
        "",
    ]
    return "\n".join(lines)


def render_api(model: dict) -> str:
    lines = ["# HTTP API surface", "", "Extracted from `@router.<method>` decorators in `apps/control-plane/api/routes/`.", ""]
    for a in model["api"]:
        lines.append(f"## `{a['router']}` — `{a['path']}`")
        lines.append("")
        lines.append(_md_table(["Method", "Path", "Line"], [[r["method"], f"`{r['path']}`", r["lineno"]] for r in a["routes"]]))
        lines.append("")
    return "\n".join(lines)


def render_data_flow(model: dict) -> str:
    py = model["python"]["modules"]
    by_name = {m["path"]: m for m in py}
    lines = [
        "# Data flow",
        "",
        "The canonical pipeline, mapped to the modules that implement each stage. This is the",
        "shape the specs describe; the gaps page records where the shape is not yet executable.",
        "",
    ]
    for stage_id, title, needles in model["pipeline"]:
        lines.append(f"## {title}")
        lines.append("")
        found = [p for p in py if any(n in p["path"] for n in needles)]
        if found:
            lines.append(_md_table(["Module", "Docstring"], [[f"`{m['path']}`", m["docstring"]] for m in found[:25]]))
        else:
            lines.append("_No module in this stage was found by name._")
        lines.append("")
    lines += [
        "## Golden paths",
        "",
        "**None are proven end-to-end.** The pipeline above is the intended shape; a golden path",
        "requires a live stack (Postgres/MinIO/Kafka/OpenSearch/ClickHouse/Temporal) and a",
        "request→report run. See [findings.md](findings.md).",
        "",
    ]
    return "\n".join(lines)


def render_imports(model: dict) -> str:
    g = model["import_graph"]
    external = sorted(
        ((k.split(":", 1)[1], k.split(":", 1)[0], n) for k, n in g["external"].items()),
        key=lambda t: -t[2],
    )
    by_kind: dict[str, list[dict]] = defaultdict(list)
    for u in g["unresolved"]:
        by_kind[u.get("kind", "local")].append(u)
    lines = [
        "# Import graph",
        "",
        f"{g['module_count']} Python modules, {g['edge_count']} resolved local edges.",
        "",
        "Imports are classified against the platform's own import roots, the standard library,",
        "the packages installed in the interpreter that ran the generator, and the distributions",
        "declared in the workspace manifests. A name in none of those is a defect, not a dependency.",
        "",
        "## External dependencies (top 40)",
        "",
        _md_table(["Package", "Kind", "Import sites"], [[f"`{n}`", kind, c] for n, kind, c in external[:40]]),
        "",
    ]
    if g.get("optional"):
        lines += [
            "## Optional capability probes",
            "",
            "Imported inside a `try`/`except ImportError`. The platform is written to run without",
            "them, so they are neither a dependency nor a defect — but each one is a capability",
            "that is switched off in this environment.",
            "",
            _md_table(
                ["Package", "Probe sites"],
                [[f"`{k}`", v] for k, v in sorted(g["optional"].items(), key=lambda kv: -kv[1])],
            ),
            "",
        ]
    if by_kind.get("local") or by_kind.get("stale-platform-path") or by_kind.get("guarded-local"):
        rows = (
            by_kind.get("local", [])
            + by_kind.get("stale-platform-path", [])
            + by_kind.get("guarded-local", [])
        )
        lines += [
            "## Platform imports with no resolved target",
            "",
            "The import names a platform package that does not exist at the resolved target. Classified by proof:",
            "",
            "* `local` — no target found; treated as a potential defect until proven otherwise.",
            "* `stale-platform-path` — the module still exists under a different root; a rename that did not reach the importer.",
            "* `guarded-local` — the import is inside a `try`, so it does not crash, but the feature behind it is silently switched off.",
            "",
            _md_table(
                ["From", "Import", "Kind"],
                [[f"`{u['from']}`", f"`{u['import']}`", u.get("kind", "local")] for u in rows],
            ),
            "",
        ]
    if g.get("roots"):
        lines += [
            "## Import roots",
            "",
            "Top-level name → the directory it resolves to, taken from the platform's own "
            "`sys.path` at generation time.",
            "",
            _md_table(
                ["Name", "Directory"],
                [[f"`{k}`", f"`{v}`"] for k, v in sorted(g["roots"].items())],
            ),
            "",
        ]
    if by_kind.get("unknown"):
        lines += [
            "## Undeclared dependencies",
            "",
            "The import names a third-party package that is neither installed nor declared in any",
            "workspace manifest. It will fail at runtime on a clean environment.",
            "",
            _md_table(
                ["From", "Import"],
                [[f"`{u['from']}`", f"`{u['import']}`"] for u in by_kind["unknown"]],
            ),
            "",
        ]
    if by_kind.get("guarded-gap"):
        lines += [
            "## Guarded gaps (tracked missing features)",
            "",
            "The platform imports the module inside a guard and skips the dependent tests. These",
            "are tracked gaps, not defects — but each one is a feature that is not implemented.",
            "",
            _md_table(
                ["From", "Import"],
                [[f"`{u['from']}`", f"`{u['import']}`"] for u in by_kind["guarded-gap"]],
            ),
            "",
        ]
    return "\n".join(lines)


def render_tests(model: dict) -> str:
    t = model["tests"]
    lines = [
        "# Tests",
        "",
        f"{len(t['by_file'])} test files, {t['total']} test functions. "
        f"{model['untested_count']} platform modules are not targeted by any test.",
        "",
        "`Targets` is resolved through the platform's own import roots, so a test that imports a "
        "package by its bare name resolves to the module it exercises. A target is reachability, "
        "not behavioural coverage.",
        "",
        "## Test files",
        "",
        _md_table(
            ["File", "Tests", "Targets"],
            [
                [f"`{f['path']}`", f["tests"], ", ".join(f"`{x}`" for x in f["targets"][:4]) or "—"]
                for f in t["by_file"]
            ],
        ),
        "",
        "## Platform modules not targeted by any test (sample)",
        "",
        _md_table(["Module"], [[f"`{m}`"] for m in model["untested_modules"][:60]]),
        "",
    ]
    return "\n".join(lines)


def render_capabilities(model: dict) -> str:
    caps = model["capabilities"]
    lines = [
        "# Capabilities",
        "",
        "Generated by `tools/specs/build_capability_matrix.py`. `WIRED_AND_TESTED` = reached from",
        "production code and pinned by tests. `TEST_ONLY` = only tests reach it — a live risk.",
        "`live_proven` is answered only by an end-to-end run against real infrastructure.",
        "",
        _md_table(
            ["Capability", "Status", "Production importers", "Tests"],
            [
                [f"`{c['id']}`", c["status"], ", ".join(f"`{i}`" for i in c.get("production_importers", [])[:2]) or "—", c.get("test_count", 0)]
                for c in caps
            ],
        ),
        "",
    ]
    return "\n".join(lines)


def render_ownership(model: dict) -> str:
    own = model["ownership"]
    lines = [
        "# Ownership",
        "",
        "Generated by `tools/specs/build_owner_map.py` from write sites. `COMPETING_WRITERS` is a",
        "defect (two writers of canonical state); `NO_DIRECT_WRITER_FOUND` is the other defect.",
        "",
        _md_table(
            ["Object", "Table", "Status", "Writers"],
            [
                [f"`{o['object']}`", f"`{o['table']}`" if o.get("table") else "—", o["status"], ", ".join(f"`{w}`" for w in o.get("writers", [])[:3]) or "—"]
                for o in own
            ],
        ),
        "",
    ]
    return "\n".join(lines)


def render_donors(model: dict) -> str:
    d = model["donors"]
    reg = d.get("registry", {}) if isinstance(d, dict) else {}
    donors = d.get("donors", []) if isinstance(d, dict) else []
    lines = [
        "# Donors",
        "",
        f"Supply-chain record generated by `tools/specs/build_donor_registry.py`.",
        f"{reg.get('vendored_checkout_count', '?')} vendored checkouts.",
        "Almost everything is `unverified`: an SPDX signature match is not a licence review, and",
        "calling it `verified` would be exactly the guess the gate exists to reject.",
        "",
        _md_table(
            ["Donor", "Upstream", "Licence", "Status", "Role"],
            [
                [f"`{x['id']}`", x.get("upstream", "—"), x.get("license") or "—", x["status"], x.get("role", "—")]
                for x in donors[:80]
            ],
        ),
        "",
    ]
    return "\n".join(lines)


def _writer_label(w) -> str:
    if isinstance(w, dict):
        lines = w.get("lines") or []
        loc = f"{w.get('file', '?')}:{lines[0]}" if lines else w.get("file", "?")
        ev = (w.get("evidence") or "").strip().replace("|", "\\|")
        return f"`{loc}` — {ev[:70]}"
    return f"`{w}`"


_LAYER_LABEL = {"0": "Layer 0 — collection", "1": "Layer 1 — extraction/resolution", "2": "Layer 2 — context engine", "x": "cross-cutting"}


def render_audit(model: dict) -> str:
    from .narrative import _counts
    counts = _counts(model)
    ev = model.get("evidence", {}).get("stats", {})
    mat = model.get("maturity", {}).get("summary", {})
    reach = model.get("reachability", {}).get("summary", {})
    gp = model.get("golden_path", {}).get("summary", {})
    gaps = model.get("gaps", {})
    ec = model.get("event_coverage", {})
    caps = model.get("capabilities", [])
    own = model.get("ownership", [])
    test_only = [c for c in caps if c.get("status") == "TEST_ONLY"]
    competing = [o for o in own if o.get("status") == "COMPETING_WRITERS"]
    no_writer = [o for o in own if o.get("status") == "NO_DIRECT_WRITER_FOUND"]
    trace = model.get("architecture", {}).get("spec_traceability", {}).get("specs", [])
    behind = [s for s in trace if s.get("tasks_total", 0) and s.get("tasks_checked", 0) == 0 and s.get("module_count", 0) > 0]
    linked = [s for s in trace if s.get("capabilities")]
    lines = [
        "# Platform audit",
        "",
        "A verified snapshot of the platform's true state. Every number is derived from the tree; "
        "the section pages hold the detail. **Read this with its caveats**: the model proves "
        "*structure, reachability and maturity* -- not correctness, not runtime behaviour.",
        "",
        "## Scale",
        "",
        _md_table(["Metric", "Value"], [
            ["Components", counts["components"]],
            ["Python / TypeScript / Rust modules", f"{counts['python_modules']} / {counts['typescript_modules']} / {counts['rust_modules']}"],
            ["Resolved import edges", counts["import_edges"]],
            ["HTTP routes / routers", f"{counts['http_routes']} / {len(model['api'])}"],
            ["Test files / functions", f"{counts['test_files']} / {counts['test_functions']}"],
            ["Evidence facts (static)", ev.get("facts_total", 0)],
        ]),
        "",
        "## Implementation maturity",
        "",
        _md_table(["Status", "Modules"], [[k, mat.get(k, 0)] for k in
                  ("IMPLEMENTED", "PRIMITIVE", "STUB", "NOT_IMPLEMENTED", "DECLARATION_ONLY", "PACKAGE_INIT", "MIGRATION", "TEST")]),
        "",
        "See [maturity.md](maturity.md).",
        "",
        "## Reachability",
        "",
        _md_table(["Status", "Modules"], [[k, reach.get(k, 0)] for k in
                  ("PRODUCTION", "TEST_ONLY", "ORPHAN", "TEST")]),
        "",
        "See [reachability.md](reachability.md) for the entrypoints and the test-only/orphan lists.",
        "",
        "## Golden path readiness",
        "",
        _md_table(["Status", "Capabilities"], [[k, gp.get(k, 0)] for k in
                  ("READY", "PARTIAL", "STUB", "TEST_ONLY", "ORPHAN", "MISSING")]),
        "",
        "See [golden-path.md](golden-path.md) for the capability map and the build plan.",
        "",
        "## Gaps (machine-checked)",
        "",
        f"**{gaps.get('open', 0)}** open, machine-checked gaps. See [gaps.md](gaps.md).",
        "",
        "## Event coverage",
        "",
        f"{ec.get('total', 0)} catalogued event types across {ec.get('lanes', 0)} lanes; "
        f"{ec.get('produced', 0)} have a likely producer line; "
        f"**{len(ec.get('unreferenced', []))}** are referenced by no file outside the catalog.",
        "",
    ]
    unreferenced = ec.get("unreferenced", [])
    if unreferenced:
        lines += ["Unreferenced event types (catalogued, but no producer or consumer string):", ""]
        lines += ["- " + ", ".join(f"`{t}`" for t in unreferenced[i:i + 6]) for i in range(0, len(unreferenced), 6)]
        lines.append("")
    crates = model.get("rust", {}).get("crates", [])
    runnable = [c for c in crates if c.get("runnable")]
    lines += [
        "## Rust crates",
        "",
        f"{len(crates)} crates, **{len(runnable)} runnable** (has a `[[bin]]` or `src/main.rs`). "
        "A crate with neither builds only an rlib: nothing outside its own tests can run it, so "
        "it is not a worker.",
        "",
        _md_table(
            ["Crate", "Runnable", "Bin", "main.rs"],
            [[f"`{c['name']}`", "yes" if c.get("runnable") else "**no**", c.get("has_bin"), c.get("has_main_rs")] for c in crates],
        ),
        "",
        "## Spec ↔ capability traceability",
        "",
        "Capabilities linked to a spec when the capability's module is cited by that spec's "
        "(spec-numbered) modules. A spec with no linked capability is either unmapped or has no "
        "capability behind it.",
        "",
        _md_table(
            ["Spec", "Capabilities"],
            [[f"`{s['id']}`", ", ".join(f"`{c}`" for c in s["capabilities"])] for s in linked],
        ) if linked else "_None linked yet._",
        "",
        "## Test-only capabilities",
        "",
        "Declared capabilities that only tests reach -- a live risk if production is believed to use them.",
        "",
        _md_table(["Capability", "Module"], [[f"`{c['id']}`", f"`{c['module']}`"] for c in test_only]),
        "",
        "## Ownership (heuristic — competing writers are candidates, not verdicts)",
        "",
        f"`{len(competing)}` objects have competing writers and `{len(no_writer)}` have no writer found. "
        "The owner map is built from textual write-site heuristics (reads and ORM imports are counted), "
        "so each row is a candidate to verify, not a proven defect. See [ownership.md](ownership.md).",
        "",
        "## Spec bookkeeping behind the code",
        "",
        "Specs whose task list shows 0 checked but whose number is cited by real modules -- the file "
        "understates the code.",
        "",
        _md_table(
            ["Spec", "Tasks", "Modules citing it"],
            [[f"`{s['id']}`", f"{s['tasks_checked']}/{s['tasks_total']}", s["module_count"]] for s in behind],
        ) if behind else "_None._",
        "",
    ]
    return "\n".join(lines)


def render_golden_path(model: dict) -> str:
    gp = model.get("golden_path", {})
    plan = model.get("build_plan", [])
    s = gp.get("summary", {})
    lines = [
        "# Golden path — person background analysis",
        "",
        gp.get("goal", ""),
        "",
        "Each capability is checked against the tree (`platform_model/golden_path.yaml`, a hybrid "
        "manifest: specs + the platform philosophy). Status is **reachability and maturity**, not "
        "correctness: `READY` means present, production-reachable and not a stub; `TEST_ONLY` means "
        "only tests reach it; `ORPHAN` means nothing imports it.",
        "",
        _md_table(
            ["Status", "Capabilities"],
            [[k, s.get(k, 0)] for k in ("READY", "PARTIAL", "STUB", "TEST_ONLY", "ORPHAN", "MISSING")],
        ),
        "",
    ]
    for layer in gp.get("layers", []):
        lines.append(f"## {layer['title']}")
        lines.append("")
        lines.append(_md_table(
            ["Capability", "Status", "Module", "Reachability", "Maturity"],
            [
                [
                    f"`{c['id']}` — {c['title']}",
                    c["status"],
                    f"`{c['primary']}`" if c["primary"] else "—",
                    c["reachability"] or "—",
                    c["maturity"] or "—",
                ]
                for c in layer["capabilities"]
            ],
        ))
        lines.append("")
    if plan:
        lines += [
            "---",
            "",
            "## Build plan (prioritized)",
            "",
            "Non-READY capabilities, worst-first within each layer. `MISSING` before `ORPHAN` before "
            "`TEST_ONLY` before `STUB` before `PARTIAL`.",
            "",
        ]
        for stream in plan:
            lines.append(f"### {stream['title']}")
            lines.append("")
            lines.append(_md_table(
                ["Capability", "Status", "Why it matters", "Module"],
                [[f"`{c['id']}`", c["status"], c["why"], f"`{c['primary']}`" if c["primary"] else "—"] for c in stream["items"]],
            ))
            lines.append("")
    return "\n".join(lines)


def render_gaps(model: dict) -> str:
    g = model.get("gaps", {})
    lines = [
        "# Gaps (machine-checked)",
        "",
        "Every defect below is a claim tied to re-checkable evidence (a file and a regex). "
        "`platform_model/gaps.py` re-reads the tree and a contract test fails if any open gap's "
        "evidence no longer holds. This is the replacement for the old free-text `KNOWN_GAPS`.",
        "",
        f"**{g.get('open', 0)}** open gaps; **{g.get('stale_or_resolved', 0)}** stale/resolved "
        "(must be zero — the test fails otherwise).",
        "",
    ]
    by_layer: dict[str, list[dict]] = {}
    for gap in g.get("gaps", []):
        by_layer.setdefault(gap["layer"], []).append(gap)
    for layer in ("0", "1", "2", "x"):
        items = by_layer.get(layer)
        if not items:
            continue
        lines.append(f"## {_LAYER_LABEL.get(layer, layer)}")
        lines.append("")
        lines.append(_md_table(
            ["ID", "Severity", "Status", "Claim", "Evidence"],
            [
                [
                    f"`{x['id']}`",
                    x["severity"],
                    x["status"],
                    x["claim"],
                    ", ".join(f"`{c['path']}`" for c in x["checks"]),
                ]
                for x in sorted(items, key=lambda x: (x["severity"], x["id"]))
            ],
        ))
        lines.append("")
    resolved = g.get("resolved", [])
    if resolved:
        lines += [
            "## Resolved claims (regression guards)",
            "",
            "Formerly-recorded gaps whose fix must stay in place; a regression flips the guard.",
            "",
            _md_table(
                ["ID", "Status", "Claim"],
                [[f"`{x['id']}`", x["status"], x["claim"]] for x in resolved],
            ),
            "",
        ]
    return "\n".join(lines)


def render_reachability(model: dict) -> str:
    r = model.get("reachability", {})
    s = r.get("summary", {})
    entrypoints = r.get("entrypoints", [])
    test_only = r.get("test_only", [])
    orphan = r.get("orphan", [])
    lines = [
        "# Reachability",
        "",
        "The import graph says A imports B; that is not the same as *B runs*. This walks the "
        "import graph forward from the deployed processes (HTTP app, Temporal worker, acquisition "
        "worker, CLI mains) and labels every module by whether production can reach it.",
        "",
        "`PRODUCTION` — reachable from a real entrypoint · `TEST_ONLY` — reachable only from tests · "
        "`ORPHAN` — imported by nothing (dead or unwired).",
        "",
        _md_table(
            ["Status", "Modules"],
            [["PRODUCTION", s.get("PRODUCTION", 0)], ["TEST_ONLY", s.get("TEST_ONLY", 0)],
             ["ORPHAN", s.get("ORPHAN", 0)], ["TEST", s.get("TEST", 0)]],
        ),
        "",
        "## Entrypoints (production roots)",
        "",
        _md_table(["Entrypoint"], [[f"`{p}`"] for p in entrypoints]),
        "",
        "## Test-only modules (production never reaches them)",
        "",
        f"**{len(test_only)}** modules are reached only by tests.",
        "",
        _md_table(["Module"], [[f"`{p}`"] for p in test_only]),
        "",
        "## Orphan modules (nothing imports them)",
        "",
        f"**{len(orphan)}** modules are imported by neither production nor tests.",
        "",
        _md_table(["Module"], [[f"`{p}`"] for p in orphan]),
        "",
    ]
    return "\n".join(lines)


def render_maturity(model: dict) -> str:
    m = model.get("maturity", {})
    rows = m.get("modules", [])
    summary = m.get("summary", {})
    unbuilt = [r for r in rows if r["status"] in ("STUB", "NOT_IMPLEMENTED", "PRIMITIVE")]
    lines = [
        "# Implementation maturity",
        "",
        "Generated from the scanner's per-body flags. This separates *the symbol exists* "
        "from *the symbol does anything*. It is a heuristic over bodies and source markers, "
        "not a judgement of correctness.",
        "",
        _md_table(
            ["Status", "Modules"],
            [[k, summary.get(k, 0)] for k in
             ("IMPLEMENTED", "PRIMITIVE", "STUB", "NOT_IMPLEMENTED", "DECLARATION_ONLY", "PACKAGE_INIT", "MIGRATION", "TEST")],
        ),
        "",
        f"**{len(unbuilt)}** modules are present but not really built "
        f"(STUB / NOT_IMPLEMENTED / PRIMITIVE).",
        "",
        "## Not really built (STUB / NOT_IMPLEMENTED / PRIMITIVE)",
        "",
        _md_table(
            ["Module", "Status", "LOC", "Callables", "Stubs", "NotImpl", "Markers"],
            [
                [
                    f"`{r['path']}`",
                    r["status"],
                    r["loc"],
                    r["callables"],
                    r["stubs"],
                    r["not_implemented"],
                    ", ".join(r["markers"]) or "—",
                ]
                for r in sorted(unbuilt, key=lambda r: (r["status"], r["path"]))
            ],
        )
        if unbuilt
        else "_None._",
        "",
        "## Declaration-only modules (no callables) — review for stubs",
        "",
        "A non-``__init__`` module with no callables is either a data/declaration module "
        "or a stub that declares a capability and implements nothing. This list is where "
        "the second kind hides.",
        "",
        _md_table(
            ["Module", "LOC", "Markers"],
            [
                [f"`{r['path']}`", r["loc"], ", ".join(r["markers"]) or "—"]
                for r in sorted(
                    (r for r in rows if r["status"] == "DECLARATION_ONLY"),
                    key=lambda r: (r["loc"], r["path"]),
                )
            ],
        ),
        "",
    ]
    return "\n".join(lines)


def render_findings(model: dict) -> str:
    caps = model["capabilities"]
    own = model["ownership"]
    test_only = [c for c in caps if c["status"] == "TEST_ONLY"]
    missing = [c for c in caps if not c.get("exists", True)]
    competing = [o for o in own if o["status"] == "COMPETING_WRITERS"]
    no_writer = [o for o in own if o["status"] == "NO_DIRECT_WRITER_FOUND"]
    graph = model["import_graph"]
    lines = [
        "# Findings",
        "",
        "What the generated model says is broken or unproven. Every row is derived from the tree;",
        "nothing here is a matter of opinion.",
        "",
        "## Test-only capabilities (production never calls them)",
        "",
        _md_table(
            ["Capability", "Module", "Claim"],
            [[f"`{c['id']}`", f"`{c['module']}`", c["claim"]] for c in test_only],
        ),
        "",
        "## Missing capabilities",
        "",
        _md_table(["Capability", "Requirement"], [[f"`{c['id']}`", c.get("requirement", "")] for c in missing])
        if missing
        else "_None: every declared capability has a module in the tree._",
        "",
        "## Competing writers (two writers of canonical state)",
        "",
        _md_table(
            ["Object", "Table", "Writer"],
            [
                [f"`{o['object']}`", f"`{o.get('table')}`" if o.get("table") else "—", _writer_label(w)]
                for o in competing
                for w in (o.get("writers") or ["—"])
            ],
        ),
        "",
        "## Objects with no writer",
        "",
        _md_table(
            ["Object", "Table", "Note"],
            [
                [f"`{o['object']}`", f"`{o.get('table')}`" if o.get("table") else "—", o.get("note") or "—"]
                for o in no_writer
            ],
        ),
        "",
        "## Untested modules",
        "",
        f"{model['untested_count']} platform modules are not imported by any test. Sample:",
        "",
        _md_table(["Module"], [[f"`{m}`"] for m in model["untested_modules"][:40]]),
        "",
        "## Unresolved imports (by evidence)",
        "",
        f"{sum(1 for u in graph['unresolved'] if u.get('kind') in ('local', 'stale-platform-path', 'guarded-local'))}"
        " platform imports have no resolved target (local/stale/guarded-local); "
        f"{sum(1 for u in graph['unresolved'] if u.get('kind') == 'guarded-gap')} tracked guarded gaps; "
        f"{sum(1 for u in graph['unresolved'] if u.get('kind') == 'unknown')} undeclared (not platform/stdlib/installed/declared).",
        "",
        _md_table(
            ["From", "Import", "Kind"],
            [
                [f"`{u['from']}`", f"`{u['import']}`", u.get("kind", "local")]
                for u in graph["unresolved"]
            ],
        ),
        "",
    ]
    return "\n".join(lines)


RENDERERS = {
    "index.md": render_index,
    "components.md": render_components,
    "contracts.md": render_contracts,
    "api.md": render_api,
    "data-flow.md": render_data_flow,
    "imports.md": render_imports,
    "maturity.md": render_maturity,
    "reachability.md": render_reachability,
    "tests.md": render_tests,
    "capabilities.md": render_capabilities,
    "ownership.md": render_ownership,
    "donors.md": render_donors,
    "audit.md": render_audit,
    "findings.md": render_findings,
    "gaps.md": render_gaps,
    "golden-path.md": render_golden_path,
}


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------

def render_all(model: dict) -> dict[str, str]:
    return {name: fn(model) for name, fn in RENDERERS.items()}


# ---------------------------------------------------------------------------
# artifacts
# ---------------------------------------------------------------------------

#: per-module keys that are pure noise in a machine artifact
_DROP_MODULE_KEYS = ("error",)


def _trim_module(mod: dict) -> dict:
    out = {k: v for k, v in mod.items() if k not in _DROP_MODULE_KEYS}
    for fn in out.get("functions", []):
        fn.pop("decorators", None)
        if len(fn.get("docstring", "")) > 160:
            fn["docstring"] = fn["docstring"][:157] + "..."
    for cls in out.get("classes", []):
        for m in cls.get("methods", []):
            m.pop("decorators", None)
            if len(m.get("docstring", "")) > 160:
                m["docstring"] = m["docstring"][:157] + "..."
    return out


def module_lines(model: dict) -> list[str]:
    """One compact JSON object per module, in a stable order."""
    lines: list[str] = []
    for lang, key in (("python", "modules"), ("typescript", "modules"), ("rust", "modules")):
        for mod in model[lang][key]:
            row = {"lang": lang}
            row.update(_trim_module(mod))
            lines.append(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
    return lines


def summary_model(model: dict) -> dict:
    """The model without the per-module rows — aggregates and surfaces only."""
    g = model["import_graph"]
    out = {k: v for k, v in model.items() if k not in ("python", "typescript", "rust")}
    out["counts"] = {
        "components": len(model["components"]),
        "python_modules": model["python"]["count"],
        "typescript_modules": model["typescript"]["count"],
        "rust_modules": model["rust"]["count"],
        "rust_crates": len(model["rust"]["crates"]),
        "import_edges": g["edge_count"],
        "test_files": len(model["tests"]["by_file"]),
        "test_functions": model["tests"]["total"],
        "untested_modules": model["untested_count"],
        "http_routes": sum(len(a["routes"]) for a in model["api"]),
    }
    if model.get("evidence"):
        out["evidence_stats"] = model["evidence"].get("stats", {})
    if model.get("maturity"):
        out["maturity_summary"] = model["maturity"].get("summary", {})
    if model.get("reachability"):
        r = model["reachability"]
        out["reachability_summary"] = r.get("summary", {})
        out["reachability_entrypoints"] = r.get("entrypoints", [])
        out["test_only_modules"] = r.get("test_only", [])
        out["orphan_modules"] = r.get("orphan", [])
    if model.get("golden_path"):
        out["golden_path_summary"] = model["golden_path"].get("summary", {})
    if model.get("event_coverage"):
        ec = model["event_coverage"]
        out["event_coverage_summary"] = {
            "total": ec["total"], "lanes": ec["lanes"], "produced": ec["produced"],
            "unreferenced": ec["unreferenced"],
        }
    if model.get("gaps"):
        out["gaps_open"] = model["gaps"].get("open", 0)
    out["import_graph"] = {
        "module_count": g["module_count"],
        "edge_count": g["edge_count"],
        "external": g["external"],
        "optional": g.get("optional", {}),
        "unknown": g["unknown"],
        "unresolved": g["unresolved"],
        "edges": g["edges"],
        "roots": g.get("roots", {}),
    }
    out["rust"] = {"count": model["rust"]["count"], "crates": model["rust"]["crates"]}
    out["tests"]["by_file"] = [
        {
            "path": f["path"],
            "tests": f["tests"],
            "test_names": f.get("test_names", [])[:30],
            "targets": f.get("targets", []),
        }
        for f in model["tests"]["by_file"]
    ]
    out["module_detail"] = "modules.jsonl"
    return out


def artifacts(model: dict) -> dict[str, str]:
    files = render_all(model)
    files["platform-model.json"] = json.dumps(summary_model(model), indent=2, ensure_ascii=False)
    files["modules.jsonl"] = "\n".join(module_lines(model)) + "\n"
    if model.get("architecture"):
        files["architecture.json"] = json.dumps(model["architecture"], indent=2, ensure_ascii=False)
    if model.get("evidence"):
        ev = model["evidence"]
        facts = ev.get("facts", [])
        lines = []
        for f in facts:
            lines.append(json.dumps(f, ensure_ascii=False))
        files["architecture-evidence.jsonl"] = "\n".join(lines) + ("\n" if lines else "")
        files["architecture-evidence.json"] = json.dumps({"stats": ev.get("stats", {}), "facts": facts}, indent=2, ensure_ascii=False)
    return files


#: narrative documents that live outside docs/platform/ but are still generated.
#: repo-relative path -> renderer.
NARRATIVE_DOCS = {
    "README.md": "render_readme",
    "docs/README.md": "render_docs_index",
    "docs/CONTRIBUTING.md": "render_contributing",
    "docs/architecture/overview.md": "render_architecture_overview",
    "docs/architecture/stream-processing.md": "render_stream_processing",
    "docs/architecture/fabric-collection.md": "render_fabric_collection",
    "docs/architecture/multi-region.md": "render_multi_region",
    "docs/architecture/dynamic-entity-invariant.md": "render_dynamic_entity_invariant",
    "docs/architecture/donors/00-INDEX.md": "render_donors_index",
    "docs/adr/0028-context-definition-identity-and-placement.md": "render_adr_0028",
}


def narrative_artifacts(model: dict) -> dict[str, str]:
    """Generated documents outside ``docs/platform/``, keyed by repo-relative path."""
    from . import narrative

    out: dict[str, str] = {}
    for rel, fn_name in NARRATIVE_DOCS.items():
        out[rel] = getattr(narrative, fn_name)(model)
    return out


def write(model: dict) -> dict[str, str]:
    OUT.mkdir(parents=True, exist_ok=True)
    files = artifacts(model)
    for name, content in files.items():
        (OUT / name).write_text(content, encoding="utf-8")
    for rel, content in narrative_artifacts(model).items():
        path = ROOT / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return files


def check(model: dict) -> list[str]:
    """Return the list of pages whose committed content differs from the model."""
    drift: list[str] = []
    for name, content in artifacts(model).items():
        path = OUT / name
        if not path.exists() or path.read_text(encoding="utf-8") != content:
            drift.append(str(path.relative_to(ROOT)))
    for rel, content in narrative_artifacts(model).items():
        path = ROOT / rel
        if not path.exists() or path.read_text(encoding="utf-8") != content:
            drift.append(rel)
    return drift


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="print the model as JSON")
    parser.add_argument("--check", action="store_true", help="fail if the committed docs drifted")
    args = parser.parse_args(argv)

    model = build_model(ROOT)
    if args.json:
        print(json.dumps(model, indent=2, ensure_ascii=False))
        return 0
    if args.check:
        drift = check(model)
        if drift:
            print("platform model drift — regenerate with `python -m platform_model.build`:")
            for d in drift:
                print(f"  {d}")
            return 1
        print("platform model is up to date")
        return 0
    files = write(model)
    print(f"wrote {len(files)} pages to {OUT.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
