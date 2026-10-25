"""Reachability: which modules a real runtime can actually reach.

The import graph says A imports B. That is not the same as "B runs": a module can
be imported only by tests, or by nothing at all. This analyzer walks the import
graph *backwards* from production entrypoints and labels every module:

``PRODUCTION``   reachable from an entrypoint (router, worker, workflow,
                 composition root, CLI main)
``TEST_ONLY``    reachable only from test modules
``ORPHAN``       reachable from neither -- imported by nothing, or only by other
                 orphans

Entrypoints are derived, not listed by hand: a non-test module that no other
non-test module imports is an entrypoint by construction (nothing calls it), and
well-known entrypoint paths (``api/main.py``, ``worker_*.py``, ``workflows/worker.py``,
``composition.py``, ``bench/run.py``) are added explicitly so a module that is both
imported and run is still treated as a root.
"""

from __future__ import annotations

from collections import defaultdict, deque
from pathlib import Path


def _is_test_path(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return "/tests/" in path or name.startswith("test_") or name.endswith("_test.py")


#: The processes that actually run in a deployment. A module is "production"
#: only if one of these transitively imports it. This list is deliberately narrow:
#: a broad pattern (``/api/routes/``, ``/runtime/``) makes almost everything
#: reachable and the label meaningless.
_ENTRYPOINT_SUFFIXES = (
    "api/main.py",
    "workflows/worker.py",
    "composition.py",
    "bench/run.py",
)

_ENTRYPOINT_NAME_PREFIXES = ("worker_",)
_ENTRYPOINT_NAME_SUFFIXES = ("_worker.py", "/worker.py")


def _is_entrypoint(path: str, has_main: bool) -> bool:
    name = path.rsplit("/", 1)[-1]
    if path.endswith(_ENTRYPOINT_SUFFIXES):
        return True
    if name.startswith(_ENTRYPOINT_NAME_PREFIXES) or path.endswith(_ENTRYPOINT_NAME_SUFFIXES):
        return True
    return has_main


def build_reachability(root: Path, model: dict) -> dict:
    modules = {m["path"] for m in model["python"]["modules"]}
    has_main = {m["path"]: bool(m.get("has_main")) for m in model["python"]["modules"]}
    edges = model["import_graph"]["edges"]
    # forward adjacency: importer -> imported
    imports: dict[str, set[str]] = defaultdict(set)
    for e in edges:
        imports[e["from"]].add(e["to"])

    tests = {p for p in modules if _is_test_path(p)}
    prod = modules - tests

    # production roots: the deployed processes (see _ENTRYPOINT_SUFFIXES), worker
    # modules, and any runnable script with a ``__main__`` guard.
    roots: set[str] = {p for p in prod if _is_entrypoint(p, has_main.get(p, False))}

    def reach(starts: set[str]) -> set[str]:
        """Everything the start modules transitively import."""
        seen: set[str] = set()
        q = deque(starts)
        while q:
            cur = q.popleft()
            if cur in seen:
                continue
            seen.add(cur)
            for nxt in imports.get(cur, ()):  # what cur imports
                if nxt not in seen:
                    q.append(nxt)
        return seen

    reachable_prod = reach(roots)
    reachable_test = reach(tests)

    rows: list[dict] = []
    for p in sorted(modules):
        if p in tests:
            status = "TEST"
        elif p in reachable_prod:
            status = "PRODUCTION"
        elif p in reachable_test:
            status = "TEST_ONLY"
        else:
            status = "ORPHAN"
        rows.append({"path": p, "status": status})

    tally: dict[str, int] = defaultdict(int)
    for r in rows:
        tally[r["status"]] += 1

    test_only = [r["path"] for r in rows if r["status"] == "TEST_ONLY"]
    orphan = [r["path"] for r in rows if r["status"] == "ORPHAN"]
    return {
        "modules": rows,
        "entrypoints": sorted(roots),
        "summary": {
            "PRODUCTION": tally["PRODUCTION"],
            "TEST_ONLY": tally["TEST_ONLY"],
            "ORPHAN": tally["ORPHAN"],
            "TEST": tally["TEST"],
            "total": len(rows),
        },
        "test_only": test_only,
        "orphan": orphan,
    }
