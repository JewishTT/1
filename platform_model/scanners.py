"""Static scanners: Python (ast), TypeScript/React (lightweight parser), Rust.

Each scanner returns plain dicts so the model serialises to JSON without custom
encoders and can be diffed by ``--check``.
"""

from __future__ import annotations

import ast
import os
import re
from pathlib import Path

# ---------------------------------------------------------------------------
# shared helpers
# ---------------------------------------------------------------------------

EXCLUDE_DIRS = {
    "donors",
    "tmp",
    "logs",
    ".venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".git",
    "dist",
    "build",
    "target",
    "k8s",
}


def _rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def iter_files(root: Path, exts: set[str]) -> list[Path]:
    """Files under ``root`` with one of ``exts``, excluding the excluded trees.

    The walk prunes as it descends rather than filtering afterwards: the excluded
    trees hold more files than the whole platform does (``.venv`` alone is tens of
    thousands), and a post-filter walk spends minutes reading directories it will
    throw away.
    """
    out: list[Path] = []
    if not root.exists():
        return out
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for name in filenames:
            if Path(name).suffix in exts:
                out.append(Path(dirpath) / name)
    return sorted(out)


def _first_line(docstring: str | None, limit: int = 200) -> str:
    if not docstring:
        return ""
    line = docstring.strip().splitlines()[0].strip()
    return line[:limit]


# ---------------------------------------------------------------------------
# Python
# ---------------------------------------------------------------------------

#: exception names whose handler also swallows ImportError
_BROAD_IMPORT_HANDLERS = frozenset({"Exception", "BaseException"})

#: markers that a body is a placeholder rather than an implementation.
_STUB_MARKERS = re.compile(
    r"\b(TODO|FIXME|XXX|HACK|placeholder|not implemented|unimplemented|stub)\b", re.I
)


def _body_maturity(node) -> dict:
    """Classify a function/method body as a stub, a NotImplementedError, or real.

    This is what separates "the symbol exists" from "the symbol does anything".
    A body of only ``pass``/``...``/a docstring, or one that raises
    ``NotImplementedError``, is not an implementation.
    """
    stmts = list(getattr(node, "body", []))
    if stmts and isinstance(stmts[0], ast.Expr) and isinstance(stmts[0].value, ast.Constant) \
            and isinstance(stmts[0].value.value, str):
        stmts = stmts[1:]
    stub = False
    if not stmts:
        stub = True
    elif all(isinstance(s, ast.Pass) for s in stmts):
        stub = True
    elif len(stmts) == 1 and isinstance(stmts[0], ast.Expr) and isinstance(stmts[0].value, ast.Constant) \
            and stmts[0].value.value is Ellipsis:
        stub = True
    not_implemented = False
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Raise):
            continue
        exc = sub.exc
        name = ""
        if isinstance(exc, ast.Call):
            name = _dotted(exc.func)
        elif isinstance(exc, ast.Name):
            name = exc.id
        if "NotImplemented" in name:
            not_implemented = True
            break
    return {"stub": stub, "not_implemented": not_implemented}


def _catches_import_error(handler: ast.ExceptHandler) -> bool:
    """True when this handler would swallow an ImportError."""
    exc = handler.type
    if exc is None:  # bare except
        return True
    if isinstance(exc, ast.Name):
        return exc.id == "ImportError" or exc.id in _BROAD_IMPORT_HANDLERS
    if isinstance(exc, ast.Tuple):
        return any(
            isinstance(e, ast.Name)
            and (e.id == "ImportError" or e.id in _BROAD_IMPORT_HANDLERS)
            for e in exc.elts
        )
    return False


class _PyVisitor(ast.NodeVisitor):
    """Collect module-level structure and imports from one module."""

    def __init__(self) -> None:
        self.imports: list[dict] = []
        self.classes: list[dict] = []
        self.functions: list[dict] = []
        self.constants: list[str] = []
        self.calls: list[str] = []
        self._optional_depth = 0
        #: depth inside a ``class`` body. Methods are recorded on their class and
        #: must not also land in the module-level ``functions`` list; without this
        #: guard ``generic_visit`` in ``visit_ClassDef`` double-counts every method.
        self._class_depth = 0

    # -- imports -----------------------------------------------------------
    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imports.append(
                {
                    "module": alias.name,
                    "names": [],
                    "lineno": node.lineno,
                    "optional": self._optional_depth > 0,
                }
            )

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        names = [a.name for a in node.names]
        self.imports.append(
            {
                "module": node.module or "",
                "names": names,
                "lineno": node.lineno,
                "level": node.level,
                "optional": self._optional_depth > 0,
            }
        )

    def visit_Try(self, node: ast.Try) -> None:
        """Track whether an import is guarded.

        An import inside ``try: ... except ImportError`` is a capability probe,
        not a dependency: the platform is written to work without it. Reporting
        those as undeclared dependencies would be a false positive on a design
        that is deliberate and documented.
        """
        guarded = any(_catches_import_error(h) for h in node.handlers)
        if guarded:
            self._optional_depth += 1
        self.generic_visit(node)
        if guarded:
            self._optional_depth -= 1

    # -- calls -------------------------------------------------------------
    def visit_Call(self, node: ast.Call) -> None:
        fn = node.func
        if isinstance(fn, ast.Name):
            self.calls.append(fn.id)
        elif isinstance(fn, ast.Attribute):
            self.calls.append(fn.attr)
        self.generic_visit(node)

    # -- classes -----------------------------------------------------------
    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        bases = []
        for b in node.bases:
            try:
                bases.append(ast.unparse(b))
            except Exception:
                bases.append("?")
        methods = []
        for child in node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                methods.append(
                    {
                        "name": child.name,
                        "args": _args(child.args),
                        "lineno": child.lineno,
                        "decorators": _decorators(child),
                        **_body_maturity(child),
                    }
                )
        self.classes.append(
            {
                "name": node.name,
                "lineno": node.lineno,
                "bases": bases,
                "docstring": _first_line(ast.get_docstring(node)),
                "methods": methods,
            }
        )
        # Descend for imports/calls (they may live in method bodies), but mark the
        # depth so method definitions are not also recorded as module functions.
        self._class_depth += 1
        self.generic_visit(node)
        self._class_depth -= 1

    # -- functions ---------------------------------------------------------
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if self._class_depth == 0:
            self.functions.append(_func(node))
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        if self._class_depth == 0:
            f = _func(node)
            f["async"] = True
            self.functions.append(f)
        self.generic_visit(node)

    # -- constants ---------------------------------------------------------
    def visit_Assign(self, node: ast.Assign) -> None:
        for t in node.targets:
            if isinstance(t, ast.Name) and t.id.isupper():
                self.constants.append(t.id)
        self.generic_visit(node)


def _args(args: ast.arguments) -> list[str]:
    out = []
    for a in list(args.args) + list(args.kwonlyargs):
        if a.arg == "self":
            continue
        ann = ""
        if a.annotation is not None:
            try:
                ann = ast.unparse(a.annotation)
            except Exception:
                ann = "?"
        out.append(f"{a.arg}: {ann}" if ann else a.arg)
    return out


def _decorators(node) -> list[str]:
    out = []
    for d in node.decorator_list:
        try:
            out.append(ast.unparse(d)[:80])
        except Exception:
            out.append("?")
    return out


def _func(node) -> dict:
    return {
        "name": node.name,
        "lineno": node.lineno,
        "args": _args(node.args),
        "decorators": _decorators(node),
        "docstring": _first_line(ast.get_docstring(node)),
        **_body_maturity(node),
    }


# ---------------------------------------------------------------------------
# sys.path manipulation
# ---------------------------------------------------------------------------
#
# A module that puts a directory on sys.path can import anything in it by bare
# name, and the platform does that a lot -- tests import sibling helpers, and
# several scripts import the shared tree directly. Without reading those calls
# the model reports those imports as unknown names, which is a false finding.


def _dotted(node) -> str:
    """Dotted name of a call target, e.g. ``os.path.join``."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""


def _module_env(tree: ast.AST) -> dict[str, ast.expr]:
    """Module-level ``NAME = <expr>`` bindings."""
    env: dict[str, ast.expr] = {}
    for node in getattr(tree, "body", []):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    env[target.id] = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            env[node.target.id] = node.value
    return env


def _eval_path(node, file_path: Path, env: dict[str, ast.expr], depth: int = 0) -> Path | None:
    """Evaluate a path expression to a Path, or None when it is not derivable."""
    if node is None or depth > 8:
        return None
    if isinstance(node, ast.Name):
        if node.id == "__file__":
            return file_path
        if node.id in env:
            return _eval_path(env[node.id], file_path, env, depth + 1)
        return None
    if isinstance(node, ast.Constant):
        return Path(node.value) if isinstance(node.value, str) else None
    if isinstance(node, ast.Attribute):
        if node.attr == "parent":
            base = _eval_path(node.value, file_path, env, depth + 1)
            return base.parent if base is not None else None
        if node.attr == "resolve":
            return _eval_path(node.value, file_path, env, depth + 1)
        return None
    if isinstance(node, ast.Subscript):
        if isinstance(node.value, ast.Attribute) and node.value.attr == "parents":
            base = _eval_path(node.value.value, file_path, env, depth + 1)
            index = node.slice
            if base is not None and isinstance(index, ast.Constant) and isinstance(index.value, int):
                try:
                    return base.parents[index.value]
                except IndexError:
                    return None
        return None
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        left = _eval_path(node.left, file_path, env, depth + 1)
        right = _eval_path(node.right, file_path, env, depth + 1)
        if left is None or right is None:
            return None
        return left / right
    if isinstance(node, ast.Call):
        name = _dotted(node.func)
        if name in ("Path", "str", "os.fspath", "pathlib.Path", "PurePath") and node.args:
            return _eval_path(node.args[0], file_path, env, depth + 1)
        if name == "os.path.join":
            parts = [_eval_path(a, file_path, env, depth + 1) for a in node.args]
            if not parts or any(p is None for p in parts):
                return None
            out = parts[0]
            for part in parts[1:]:
                out = out / part
            return out
        if name in ("os.path.abspath", "os.path.realpath", "os.path.normpath") and node.args:
            base = _eval_path(node.args[0], file_path, env, depth + 1)
            if base is None:
                return None
            return base if base.is_absolute() else (file_path.parent / base)
        if name == "os.path.dirname" and node.args:
            base = _eval_path(node.args[0], file_path, env, depth + 1)
            return base.parent if base is not None else None
        if name.endswith("resolve") and isinstance(node.func, ast.Attribute):
            return _eval_path(node.func.value, file_path, env, depth + 1)
    return None


def path_insert_roots(tree: ast.AST, path: Path, root: Path) -> list[str]:
    """Directories the module puts on ``sys.path``, as repo-relative paths."""
    env = _module_env(tree)
    out: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if not isinstance(fn, ast.Attribute) or fn.attr not in ("insert", "append"):
            continue
        target = fn.value
        if not (isinstance(target, ast.Attribute) and target.attr == "path"):
            continue
        if not (isinstance(target.value, ast.Name) and target.value.id == "sys"):
            continue
        arg = node.args[1] if fn.attr == "insert" and len(node.args) > 1 else (node.args[0] if node.args else None)
        resolved = _eval_path(arg, path, env)
        if resolved is None:
            continue
        if not resolved.is_absolute():
            resolved = path.parent / resolved
        try:
            rel = resolved.resolve().relative_to(root).as_posix()
        except (ValueError, OSError):
            continue
        if rel not in out:
            out.append(rel)
    return sorted(out)


def _has_main_guard(tree: ast.AST) -> bool:
    """True when the module has a top-level ``if __name__ == "__main__":`` guard."""
    for node in getattr(tree, "body", []):
        if not isinstance(node, ast.If):
            continue
        test = node.test
        if isinstance(test, ast.Compare) and isinstance(test.left, ast.Name) \
                and test.left.id == "__name__":
            for comp in test.comparators:
                if isinstance(comp, ast.Constant) and comp.value == "__main__":
                    return True
    return False


def scan_python(path: Path, root: Path) -> dict:
    rel = _rel(path, root)
    module = rel[:-3].replace("/", ".")
    if module.endswith(".__init__"):
        module = module[: -len(".__init__")]
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError as exc:
        return {
            "path": rel,
            "module": module,
            "error": f"syntax: {exc}",
            "docstring": "",
            "loc": 0,
            "has_main": False,
            "markers": [],
            "imports": [],
            "classes": [],
            "functions": [],
            "constants": [],
            "calls": [],
            "path_roots": [],
        }
    visitor = _PyVisitor()
    visitor.visit(tree)
    text = path.read_text(encoding="utf-8", errors="replace")
    return {
        "path": rel,
        "module": module,
        "docstring": _first_line(ast.get_docstring(tree)),
        "loc": text.count("\n") + 1,
        "has_main": _has_main_guard(tree),
        "markers": sorted({m.group(0).lower() for m in _STUB_MARKERS.finditer(text)}),
        "imports": visitor.imports,
        "classes": visitor.classes,
        "functions": visitor.functions,
        "constants": visitor.constants,
        "calls": sorted(set(visitor.calls)),
        "path_roots": path_insert_roots(tree, path, root),
    }


# ---------------------------------------------------------------------------
# TypeScript / React
# ---------------------------------------------------------------------------

_TS_IMPORT = re.compile(
    r'''^\s*(?:import|export)\s+(?:[\s\S]*?\s+from\s+)?['"]([^'"]+)['"]''', re.M
)
_TS_EXPORT_DECL = re.compile(
    r'''^\s*export\s+(?:default\s+)?(?:async\s+)?(function|class|const|let|var|interface|type|enum)\s+([A-Za-z0-9_]+)''',
    re.M,
)
_TS_NAMED_EXPORT = re.compile(r'''^\s*export\s*\{([^}]*)\}''', re.M)
_TS_ROUTE = re.compile(
    r'''(?:fetch\s*\(\s*['"`]([^'"`]+)|axios\.(get|post|put|delete)\s*\(\s*['"`]([^'"`]+))'''
)
_TS_HTTP_HOOK = re.compile(r'''\b(useQuery|useMutation|useFetch|useSWR)\s*\(''')


def scan_typescript(path: Path, root: Path) -> dict:
    rel = _rel(path, root)
    text = path.read_text(encoding="utf-8", errors="replace")
    imports = [m.group(1) for m in _TS_IMPORT.finditer(text)]
    exports: list[dict] = []
    for m in _TS_EXPORT_DECL.finditer(text):
        exports.append({"kind": m.group(1), "name": m.group(2)})
    for m in _TS_NAMED_EXPORT.finditer(text):
        for name in m.group(1).split(","):
            name = name.strip().split(" as ")[-1].strip()
            if name:
                exports.append({"kind": "named", "name": name})
    components = sorted(
        {e["name"] for e in exports if e["kind"] in ("function", "class") and e["name"][:1].isupper()}
    )
    http = [m.group(1) or m.group(3) for m in _TS_ROUTE.finditer(text)]
    hooks = sorted({m.group(1) for m in _TS_HTTP_HOOK.finditer(text)})
    first_comment = ""
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("/**") or s.startswith("/*") or s.startswith("//"):
            first_comment = s.lstrip("/* ").rstrip("*/").strip()[:200]
            break
        if s:
            break
    return {
        "path": rel,
        "docstring": first_comment,
        "imports": sorted(set(imports)),
        "exports": exports,
        "components": components,
        "http_calls": sorted(set(http)),
        "data_hooks": hooks,
    }


# ---------------------------------------------------------------------------
# Rust
# ---------------------------------------------------------------------------

_RUST_ITEM = re.compile(
    r'''^\s*(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?(?:unsafe\s+)?(fn|struct|enum|trait|mod|const|static|type)\s+([A-Za-z0-9_]+)''',
    re.M,
)
_RUST_IMPL = re.compile(r'''^\s*impl(?:<[^>]*>)?\s+(?:([A-Za-z0-9_]+)\s+for\s+)?([A-Za-z0-9_]+)''', re.M)


def scan_rust(path: Path, root: Path) -> dict:
    rel = _rel(path, root)
    text = path.read_text(encoding="utf-8", errors="replace")
    items = [{"kind": m.group(1), "name": m.group(2)} for m in _RUST_ITEM.finditer(text)]
    impls = [m.group(2) for m in _RUST_IMPL.finditer(text)]
    return {
        "path": rel,
        "items": items,
        "impls": sorted(set(impls)),
        "docstring": _first_line(text.split("*/")[-1] if "/*" in text else ""),
    }


def scan_cargo(path: Path, root: Path) -> dict:
    rel = _rel(path, root)
    text = path.read_text(encoding="utf-8", errors="replace")
    name = re.search(r'''^\s*name\s*=\s*"([^"]+)''', text, re.M)
    version = re.search(r'''^\s*version\s*=\s*"([^"]+)''', text, re.M)
    deps = re.findall(r'''^\s*([A-Za-z0-9_-]+)\s*=\s*[{\s]''', text, re.M)
    # A crate with no [[bin]] and no src/main.rs builds only an rlib: nothing outside
    # its own tests can run it. "A worker crate exists" is not "a worker can run".
    has_bin = re.search(r"^\s*\[\[bin\]\]", text, re.M) is not None
    crate_dir = path.parent
    main_rs = (crate_dir / "src" / "main.rs").is_file()
    return {
        "path": rel,
        "name": name.group(1) if name else Path(rel).parent.name,
        "version": version.group(1) if version else "",
        "dependencies": sorted(set(deps)),
        "has_bin": has_bin,
        "has_main_rs": main_rs,
        "runnable": has_bin or main_rs,
    }
