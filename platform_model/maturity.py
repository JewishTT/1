"""Implementation maturity: which modules are real, primitive, stub, or declarations.

"Module exists" and "module implements something" are different facts, and the gap
between them is where a platform looks larger than it is. This analyzer reads the
per-body flags the Python scanner records (``stub``, ``not_implemented``) and the
source markers (``TODO``/``stub``/``placeholder``) and classifies each module:

``IMPLEMENTED``      callables with real bodies
``PRIMITIVE``        a majority of callables are stubs / not-implemented, or a
                     marker-bearing module too small to be more than a placeholder
``STUB``             every callable body is ``pass`` / ``...`` / a docstring
``NOT_IMPLEMENTED``  every callable raises ``NotImplementedError``
``DECLARATION_ONLY`` no callables (constants / docstring / re-export)
``PACKAGE_INIT``     an ``__init__.py`` with no callables (re-export or marker)
``TEST``             a test file (excluded from the maturity tally)

This is a heuristic and is labelled as one. It never claims a module is *correct*;
it claims only whether a body exists at all.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path


def _is_test_path(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return "/tests/" in path or name.startswith("test_") or name.endswith("_test.py")


_ABSTRACT_BASES = ("Protocol", "ABC", "ABCMeta")


def _is_abstract(bases: list[str], decorators: list[str]) -> bool:
    if any(d.split("(")[0].endswith("abstractmethod") for d in decorators):
        return True
    return any(any(b == base or b.endswith("." + base) for base in _ABSTRACT_BASES) for b in bases)


def _effective_bodies(mod: dict) -> list[dict]:
    """Callables that are supposed to have a body.

    Protocol / ABC methods and abstract methods are *meant* to be ``...``; a
    migration's ``_no_*`` helpers are *meant* to do nothing. Counting them as stubs
    is a false positive, so they are removed before the tally.
    """
    funcs = [f for f in mod.get("functions", []) if not f["name"].startswith("_no_")]
    methods: list[dict] = []
    for c in mod.get("classes", []):
        if _is_abstract(c.get("bases", []), []):
            continue
        for m in c.get("methods", []):
            if m["name"].startswith("_no_") or _is_abstract([], m.get("decorators", [])):
                continue
            methods.append(m)
    return funcs + methods


def _module_status(mod: dict) -> str:
    path = mod["path"]
    if _is_test_path(path):
        return "TEST"
    if "/db/migrations/" in path:
        # Alembic revisions are DDL scripts: a deliberate ``_no_*`` helper and a
        # deliberate ``NotImplementedError`` downgrade are not unbuilt code.
        return "MIGRATION"
    bodies = _effective_bodies(mod)
    n = len(bodies)
    if n == 0:
        if path.rsplit("/", 1)[-1] == "__init__.py":
            return "PACKAGE_INIT"
        return "DECLARATION_ONLY"
    n_stub = sum(1 for b in bodies if b.get("stub"))
    n_ni = sum(1 for b in bodies if b.get("not_implemented"))
    if n_ni == n:
        return "NOT_IMPLEMENTED"
    if n_stub == n:
        return "STUB"
    if (n_stub + n_ni) / n >= 0.5:
        return "PRIMITIVE"
    if mod.get("markers") and mod.get("loc", 0) < 40:
        return "PRIMITIVE"
    return "IMPLEMENTED"


def build_maturity(root: Path, model: dict) -> dict:
    rows: list[dict] = []
    for mod in model["python"]["modules"]:
        funcs = mod.get("functions", [])
        classes = mod.get("classes", [])
        methods = [m for c in classes for m in c.get("methods", [])]
        bodies = funcs + methods
        rows.append({
            "path": mod["path"],
            "status": _module_status(mod),
            "loc": mod.get("loc", 0),
            "callables": len(bodies),
            "stubs": sum(1 for b in bodies if b.get("stub")),
            "not_implemented": sum(1 for b in bodies if b.get("not_implemented")),
            "markers": mod.get("markers", []),
        })
    tally = Counter(r["status"] for r in rows)
    summary = dict(tally)
    summary["total"] = len(rows)
    return {"modules": rows, "summary": summary}


#: statuses that mean "present but not really built" -- the ones a build plan cares about.
UNBUILT = ("STUB", "NOT_IMPLEMENTED", "PRIMITIVE")
