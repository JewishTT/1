"""Semantic layer: contracts, HTTP API surface, test coverage, and the
artifacts already produced by ``tools/specs/*``.

This is the part of the model that answers "what is the platform's public
surface and what does it promise", as opposed to the scanners which answer
"what exists".
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import yaml

from .scanners import _rel

# ---------------------------------------------------------------------------
# contracts
# ---------------------------------------------------------------------------

CONTRACT_DOC_DIRS = ("apps/shared/contracts",)


def scan_python_contracts(root: Path) -> list[dict]:
    out: list[dict] = []
    for p in sorted((root / "apps" / "shared" / "contracts").glob("*.py")):
        if p.name == "__init__.py":
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        classes = [n.name for n in tree.body if isinstance(n, ast.ClassDef)]
        functions = [
            n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        out.append(
            {
                "name": p.stem,
                "path": _rel(p, root),
                "docstring": (ast.get_docstring(tree) or "").strip().splitlines()[0][:200]
                if ast.get_docstring(tree)
                else "",
                "classes": classes,
                "functions": functions,
            }
        )
    return out


def scan_contract_docs(root: Path) -> list[dict]:
    out: list[dict] = []
    patterns = [
        "apps/shared/contracts/*.md",
        "specs/*/contracts/*.md",
    ]
    seen: set[Path] = set()
    for pat in patterns:
        for p in root.glob(pat):
            if p in seen:
                continue
            seen.add(p)
            head = ""
            for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
                s = line.strip()
                if s and not s.startswith("#"):
                    head = s[:200]
                    break
                if s.startswith("#"):
                    head = s.lstrip("# ").strip()[:200]
                    break
            out.append({"name": p.stem, "path": _rel(p, root), "title": head})
    return out


def scan_root_contracts(root: Path) -> list[dict]:
    out: list[dict] = []
    base = root / "contracts"
    if not base.exists():
        return out
    for p in sorted(base.glob("*.yaml")) + sorted(base.glob("*.yml")):
        out.append({"name": p.stem, "path": _rel(p, root), "kind": "schema"})
    for p in sorted((base / "schemas").glob("*.json")):
        out.append({"name": p.stem, "path": _rel(p, root), "kind": "json-schema"})
    return out


# ---------------------------------------------------------------------------
# HTTP API surface
# ---------------------------------------------------------------------------

_ROUTE_DECORATOR = re.compile(
    r"""^\s*@\s*(?:router|app|[a-z_]*router)\.(get|post|put|delete|patch|head|options)\s*\(\s*["']([^"']+)["']""",
    re.M,
)


def scan_api(root: Path) -> list[dict]:
    out: list[dict] = []
    routes = root / "apps" / "control-plane" / "api" / "routes"
    for p in sorted(routes.rglob("*.py")):
        text = p.read_text(encoding="utf-8", errors="replace")
        methods = [
            {"method": m.group(1).upper(), "path": m.group(2), "lineno": text[: m.start()].count("\n") + 1}
            for m in _ROUTE_DECORATOR.finditer(text)
        ]
        if methods:
            out.append({"router": p.stem, "path": _rel(p, root), "routes": methods})
    return out


# ---------------------------------------------------------------------------
# test coverage
# ---------------------------------------------------------------------------

_TEST_FUNC = re.compile(r"""^\s*(?:async\s+)?def\s+(test_[A-Za-z0-9_]+)""", re.M)


def scan_tests(root: Path, py_modules: list[dict], roots: dict[str, str] | None = None) -> dict[str, dict]:
    """Map test files to the platform modules they import, and count tests.

    ``roots`` is the top-level import name → repo directory map produced by the
    import-graph builder. Without it, a test that imports a platform package by
    its bare name (``from contracts.observation import ...``, which ``conftest``
    puts on ``sys.path``) cannot be resolved to a file, and every test would be
    recorded with no target — which is the difference between a coverage claim
    and a coverage fiction.
    """
    module_by_path = {m["path"]: m for m in py_modules}
    roots = roots or {}
    by_target: dict[str, dict] = {}
    for p in iter_test_files(root):
        text = p.read_text(encoding="utf-8", errors="replace")
        tests = _TEST_FUNC.findall(text)
        imports = _test_imports(text)
        rel = _rel(p, root)
        entry = by_target.setdefault(
            rel,
            {"path": rel, "tests": 0, "test_names": [], "imports": [], "targets": []},
        )
        entry["tests"] += len(tests)
        entry["test_names"].extend(tests[:50])
        entry["imports"] = sorted(set(entry["imports"]) | set(imports))
        for imp in imports:
            tgt = _resolve_import(imp, module_by_path, roots)
            if tgt:
                entry["targets"].append(tgt)
        entry["targets"] = sorted(set(entry["targets"]))
    return by_target


def iter_test_files(root: Path) -> list[Path]:
    from .scanners import iter_files

    out: list[Path] = []
    for p in iter_files(root, {".py"}):
        posix = p.as_posix()
        if "/tests/" in posix or p.name.startswith("test_") or p.name.endswith("_test.py"):
            out.append(p)
    return sorted(out)


def _test_imports(text: str) -> list[str]:
    return re.findall(r"""^\s*(?:from|import)\s+([A-Za-z0-9_\.]+)""", text, re.M)


def _resolve_import(imp: str, module_by_path: dict[str, dict], roots: dict[str, str]) -> str | None:
    """Repo path of the platform module an import names, or None.

    Resolution goes through the same import-root map the import graph uses: the
    platform imports its packages by bare directory name, so ``contracts.x``
    means ``apps/shared/contracts/x.py`` and only ``roots`` knows that.
    """
    parts = imp.split(".")
    for n in range(len(parts), 0, -1):
        prefix = ".".join(parts[:n])
        base = roots.get(prefix)
        if not base:
            continue
        if base.endswith("/__init__.py"):
            base = base[: -len("/__init__.py")]
        elif base.endswith(".py"):
            base = base[:-3]
        rest = parts[n:]
        rel = "/".join([base] + rest) if rest else base
        for cand in (rel + ".py", rel + "/__init__.py"):
            if cand in module_by_path:
                return cand
    # fall back to a literal repo-path match (tests that import by repo path)
    for n in range(len(parts), 0, -1):
        for cand in ("/".join(parts[:n]) + ".py", "/".join(parts[:n]) + "/__init__.py"):
            if cand in module_by_path:
                return cand
    return None


# ---------------------------------------------------------------------------
# reuse of tools/specs artifacts
# ---------------------------------------------------------------------------

def load_spec_artifacts(root: Path) -> dict:
    bench = root / "specs" / "032-global-upgrade-execution" / "benchmarks"
    out: dict = {"capabilities": [], "ownership": [], "donors": {}}
    cap = bench / "WP0-capability-matrix.json"
    if cap.exists():
        out["capabilities"] = json.loads(cap.read_text(encoding="utf-8"))
    own = bench / "WP0-owner-map.json"
    if own.exists():
        out["ownership"] = json.loads(own.read_text(encoding="utf-8"))
    reg = root / "donors" / "registry.yaml"
    if reg.exists():
        out["donors"] = yaml.safe_load(reg.read_text(encoding="utf-8")) or {}
    return out
