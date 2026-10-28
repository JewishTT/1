#!/usr/bin/env python3
"""Build and query the COGNITIVE semantic documentation graph.

The graph is derived from source and specifications at invocation time. It is
not another hand-maintained map and it does not replace platform_model.build.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CODE_ROOTS = ("apps", "bench", "benchmarks", "tools", "platform_model", "implementation", "specs")
DOC_ROOTS = ("docs", "specs", ".opencode", ".specify")
SOURCE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".rs", ".proto", ".sql", ".css", ".scss", ".html"}
CONFIG_SUFFIXES = {".yaml", ".yml", ".json", ".toml", ".ini", ".conf"}
EXCLUDED_DIRS = {
    ".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache",
    ".ruff_cache", "target", "dist", "build", "tmp", "logs", "donors",
    "pip-unpack", "pip-metadata",
}
EVENT_NAME = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+$")
PATH_REF = re.compile(r"\b(?:apps|bench|tools|platform_model|specs|docs)/[A-Za-z0-9_./-]+")
MARKDOWN_LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
SPEC_REF = re.compile(r"\b(?:spec|feature)[ /]0*(\d{1,3})\b", re.I)


def relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def walk(root: Path, bases: tuple[str, ...], suffixes: set[str]) -> list[Path]:
    found: list[Path] = []
    for base in bases:
        start = root / base
        if not start.exists():
            continue
        for directory, dirnames, filenames in os.walk(start):
            dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDED_DIRS)
            for name in filenames:
                path = Path(directory) / name
                if path.suffix.lower() in suffixes:
                    found.append(path)
    return sorted(set(found))


def is_intentionally_excluded_tracked_path(path: str) -> bool:
    parts = Path(path).parts
    if any(part in EXCLUDED_DIRS for part in parts):
        return True
    root_name = parts[0] if parts else ""
    return (
        root_name.startswith(("pip-unpack-", "pip-metadata-", "pytest-of-tim"))
        or bool(re.fullmatch(r"tmp[a-z0-9]{6,}", root_name))
    )


def tracked_source_candidates(root: Path) -> list[str] | None:
    """Find tracked source-like files so a new source root cannot be silently skipped."""
    try:
        result = subprocess.run(
            ["git", "ls-files", "-z"], cwd=root, capture_output=True, timeout=30, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode:
        return None
    candidates = []
    for item in result.stdout.decode("utf-8", errors="replace").split("\0"):
        if not item or Path(item).suffix.lower() not in SOURCE_SUFFIXES:
            continue
        if not is_intentionally_excluded_tracked_path(item):
            candidates.append(item)
    return sorted(set(candidates))


def text_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = dotted(node.value)
        return base + "." + node.attr if base else node.attr
    return ""


def annotation(node: ast.AST | None) -> str:
    if node is None:
        return ""
    try:
        return ast.unparse(node)
    except (ValueError, AttributeError):
        return "?"


def function_arguments(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    args = node.args
    result: list[str] = []
    positional = list(args.posonlyargs) + list(args.args)
    defaults = [None] * (len(positional) - len(args.defaults)) + list(args.defaults)
    for arg, default in zip(positional, defaults):
        ann = annotation(arg.annotation)
        value = arg.arg + (": " + ann if ann else "")
        if default is not None:
            value += " = " + annotation(default)
        result.append(value)
    if args.vararg:
        result.append("*" + args.vararg.arg)
    for arg, default in zip(args.kwonlyargs, args.kw_defaults):
        ann = annotation(arg.annotation)
        value = arg.arg + (": " + ann if ann else "")
        if default is not None:
            value += " = " + annotation(default)
        result.append(value)
    if args.kwarg:
        result.append("**" + args.kwarg.arg)
    return result


def scan_python_text(path: str, text: str) -> dict[str, Any]:
    """Return a true Python-AST module record; exposed for fast contract tests."""
    try:
        # A UTF-8 BOM is legal in repository text files. Strip it only from the
        # parser input; the graph's content hash remains over the original text.
        tree = ast.parse(text.removeprefix("\ufeff"), filename=path)
    except SyntaxError as exc:
        return {
            "path": path, "parser": "python-ast", "parse_error": str(exc),
            "symbols": [], "imports": [], "routes": [], "calls": [],
            "docstring": "", "line_count": text.count("\n") + 1,
        }

    module_name = path[:-3].replace("/", ".")
    if module_name.endswith(".__init__"):
        module_name = module_name[:-9]
    symbols: list[dict[str, Any]] = []
    imports: list[dict[str, Any]] = []
    routes: list[dict[str, Any]] = []
    calls: list[dict[str, Any]] = []

    class Collector(ast.NodeVisitor):
        def __init__(self) -> None:
            self.scopes: list[str] = []

        def add_symbol(self, node: ast.AST, name: str, kind: str, doc: str = "") -> str:
            qualified = ".".join(self.scopes + [name])
            symbol_id = "symbol:" + path + "#" + qualified
            entry: dict[str, Any] = {
                "id": symbol_id, "name": name, "qualified_name": qualified,
                "kind": kind, "line": getattr(node, "lineno", 1),
                "docstring": ((doc or "").strip().splitlines() or [""])[0][:240],
                "public": not name.startswith("_"),
            }
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                entry["async"] = isinstance(node, ast.AsyncFunctionDef)
                entry["arguments"] = function_arguments(node)
                entry["returns"] = annotation(node.returns)
                entry["decorators"] = [annotation(x)[:120] for x in node.decorator_list]
            elif isinstance(node, ast.ClassDef):
                entry["bases"] = [annotation(x) for x in node.bases]
            symbols.append(entry)
            return symbol_id

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            self.add_symbol(node, node.name, "class", ast.get_docstring(node) or "")
            self.scopes.append(node.name)
            self.generic_visit(node)
            self.scopes.pop()

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self.add_symbol(node, node.name, "function", ast.get_docstring(node) or "")
            self._visit_function_body(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self.add_symbol(node, node.name, "function", ast.get_docstring(node) or "")
            self._visit_function_body(node)

        def _visit_function_body(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
            for decorator in node.decorator_list:
                self.visit(decorator)
            self.scopes.append(node.name)
            for child in node.body:
                self.visit(child)
            self.scopes.pop()

        def visit_Import(self, node: ast.Import) -> None:
            for alias in node.names:
                imports.append({
                    "module": alias.name, "names": [], "level": 0,
                    "line": node.lineno, "kind": "import",
                })

        def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
            imports.append({
                "module": node.module or "", "names": [a.name for a in node.names],
                "level": node.level, "line": node.lineno, "kind": "from",
            })

        def visit_Assign(self, node: ast.Assign) -> None:
            if not self.scopes:
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id.isupper():
                        self.add_symbol(node, target.id, "constant")
            self.generic_visit(node)

        def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
            if not self.scopes and isinstance(node.target, ast.Name) and node.target.id.isupper():
                self.add_symbol(node, node.target.id, "constant")
            self.generic_visit(node)

        def visit_Call(self, node: ast.Call) -> None:
            target = dotted(node.func)
            if target:
                calls.append({"callee": target, "line": node.lineno})
            method = target.rsplit(".", 1)[-1].lower()
            if method in {"get", "post", "put", "patch", "delete", "head", "options"} and node.args:
                first = node.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str) and first.value.startswith("/"):
                    routes.append({
                        "method": method.upper(), "path": first.value,
                        "line": node.lineno, "decorator": target,
                    })
            self.generic_visit(node)

    Collector().visit(tree)
    return {
        "path": path, "parser": "python-ast", "parse_error": None,
        "docstring": (ast.get_docstring(tree) or "").strip().splitlines()[0][:240]
        if ast.get_docstring(tree) else "",
        "line_count": text.count("\n") + 1,
        "symbols": symbols, "imports": imports, "routes": routes, "calls": calls,
    }


def source_module_target(root: Path, source: str, module: str, level: int = 0) -> str | None:
    """Resolve common first-party Python imports against the actual checked-out tree."""
    candidates: list[Path] = []
    source_path = root / source
    if level:
        package = source_path.parent
        for _ in range(max(0, level - 1)):
            package = package.parent
        base = package / module.replace(".", "/") if module else package
        candidates.extend((base.with_suffix(".py"), base / "__init__.py"))
    else:
        rel = module.replace(".", "/")
        candidates.extend((root / (rel + ".py"), root / rel / "__init__.py"))
        app_dirs = sorted((root / "apps").iterdir()) if (root / "apps").exists() else []
        for app in app_dirs:
            if app.is_dir():
                base = app / rel
                candidates.extend((base.with_suffix(".py"), base / "__init__.py"))
        shared = root / "apps" / "shared" / rel
        candidates.extend((shared.with_suffix(".py"), shared / "__init__.py"))
    for candidate in candidates:
        try:
            if candidate.is_file():
                return relative(candidate, root)
        except OSError:
            pass
    return None


def resolve_doc_target(root: Path, source: str, target: str, known: set[str]) -> str | None:
    clean = target.split("#", 1)[0].split("?", 1)[0].strip()
    if not clean or clean.startswith(("http://", "https://", "mailto:", "data:")):
        return None
    decoded = clean.replace("%20", " ")
    base = (root / source).parent
    candidates = [base / decoded, root / decoded]
    expanded: list[Path] = []
    for candidate in candidates:
        expanded.append(candidate)
        if candidate.is_dir():
            expanded.extend(candidate / name for name in ("index.md", "README.md", "00-INDEX.md"))
    for candidate in expanded:
        try:
            if candidate.exists():
                return relative(candidate.resolve(), root)
        except (OSError, ValueError):
            continue
    return None


def document_kind(path: str) -> str:
    if path.startswith("specs/"):
        return "specification"
    if path.startswith("docs/adr/"):
        return "architecture-decision"
    if path.startswith("docs/architecture/"):
        return "architecture-document"
    if path == "AGENTS.md" or path.startswith(".opencode/") or path.startswith(".specify/"):
        return "agent-instruction"
    return "documentation"


def first_heading(text: str, fallback: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("#"):
            return line.lstrip("# ").strip()[:240]
    return fallback


def run_parser(command: list[str], root: Path, parser_name: str) -> dict[str, Any]:
    try:
        proc = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=240)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"parser_error": parser_name + ": " + str(exc), "modules": []}
    if proc.returncode:
        message = (proc.stderr or proc.stdout or "parser failed").strip()[-5000:]
        return {"parser_error": parser_name + ": " + message, "modules": []}
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return {"parser_error": parser_name + ": invalid JSON: " + str(exc), "modules": []}


def build_graph(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    code_paths = walk(root, CODE_ROOTS, SOURCE_SUFFIXES)
    code_paths.extend(
        path for path in root.iterdir()
        if path.is_file() and path.suffix.lower() in SOURCE_SUFFIXES
    )
    code_paths = sorted(set(code_paths))
    code_rel = {relative(p, root) for p in code_paths}
    ts_paths = [p for p in code_paths if p.suffix.lower() in {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}]
    rust_paths = [p for p in code_paths if p.suffix.lower() == ".rs"]
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    module_records: dict[str, dict[str, Any]] = {}
    texts: dict[str, str] = {}

    for path in code_paths:
        rel = relative(path, root)
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            text = ""
            module_records[rel] = {
                "path": rel, "parser": "read-error", "parse_error": str(exc),
                "symbols": [], "imports": [], "routes": [],
            }
        texts[rel] = text
        if path.suffix.lower() == ".py":
            module_records[rel] = scan_python_text(rel, text)
        nodes.append({
            "id": "module:" + rel, "kind": "source-module", "path": rel,
            "language": path.suffix.lower().lstrip("."),
            "sha256": text_digest(text), "line_count": text.count("\n") + 1,
        })

    ts_result: dict[str, Any] = {"modules": []}
    if ts_paths:
        ts_result = run_parser(
            ["node", "tools/semantic_docgraph_ts.mjs", "--root", str(root)],
            root, "TypeScript compiler AST",
        )
    ts_by_path = {m["path"]: m for m in ts_result.get("modules", [])}
    rust_result: dict[str, Any] = {"modules": []}
    if rust_paths:
        rust_result = run_parser(
            ["cargo", "run", "--quiet", "--manifest-path",
             "tools/semantic-docgraph-rust/Cargo.toml", "--", "--root", str(root)],
            root, "Rust syn AST",
        )
    rust_by_path = {m["path"]: m for m in rust_result.get("modules", [])}
    config_paths = walk(
        root,
        ("apps", "bench", "benchmarks", "tools", "deploy", "platform_model",
         "contracts", "implementation", "specs", ".github", ".opencode", ".specify"),
        CONFIG_SUFFIXES,
    )
    root_config_names = {".env.example", ".gitignore", ".gitattributes", "uv.lock"}
    config_paths.extend(
        path for path in root.iterdir()
        if path.is_file() and (
            path.suffix.lower() in CONFIG_SUFFIXES or path.name in root_config_names
        )
    )
    config_paths = sorted(set(config_paths))
    config_rel = {relative(p, root) for p in config_paths}

    for rel in sorted(code_rel):
        record = module_records.get(rel)
        suffix = Path(rel).suffix.lower()
        if suffix in {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}:
            record = ts_by_path.get(rel)
            if record is None:
                record = {
                    "path": rel, "parser": "typescript-ast", "parse_error": "file missing from parser output",
                    "symbols": [], "imports": [], "routes": [],
                }
            module_records[rel] = record
        elif suffix == ".rs":
            record = rust_by_path.get(rel)
            if record is None:
                record = {
                    "path": rel, "parser": "rust-syn-ast", "parse_error": "file missing from parser output",
                    "symbols": [], "imports": [], "routes": [],
                }
            module_records[rel] = record
        elif suffix in {".proto", ".sql", ".css", ".scss", ".html"}:
            module_records[rel] = {
                "path": rel, "parser": "domain-source-inventory", "parse_error": None,
                "symbols": [], "imports": [], "routes": [],
            }
        record = module_records[rel]
        module_id = "module:" + rel
        record.setdefault("imports", [])
        record.setdefault("symbols", [])
        record.setdefault("routes", [])
        record.setdefault("calls", [])
        for symbol in record["symbols"]:
            if not symbol.get("id"):
                qualified_name = symbol.get("qualified_name") or symbol.get("name") or "<anonymous>"
                symbol["id"] = "symbol:" + rel + "#" + qualified_name
            nodes.append({
                "id": symbol["id"], "kind": symbol.get("kind", "symbol"),
                "path": rel, "name": symbol.get("qualified_name", symbol.get("name", "")),
                "line": symbol.get("line"),
                "docstring": symbol.get("docstring", ""),
                "public": symbol.get("public"),
            })
            edges.append({"from": module_id, "to": symbol["id"], "kind": "defines",
                          "evidence": {"path": rel, "line": symbol.get("line")}})
        for imp in record["imports"]:
            module_name = imp.get("module", imp.get("specifier", imp.get("path", "")))
            level = int(imp.get("level", 0) or 0)
            target = None
            if suffix == ".py":
                target = source_module_target(root, rel, module_name, level)
            elif module_name.startswith("."):
                base = (root / rel).parent / module_name
                for candidate in (base, base.with_suffix(".ts"), base.with_suffix(".tsx"),
                                  base.with_suffix(".js"), base.with_suffix(".jsx"),
                                  base / "index.ts", base / "index.tsx", base / "index.js"):
                    try:
                        if candidate.is_file():
                            target = relative(candidate, root)
                            break
                    except OSError:
                        pass
            if target:
                edges.append({
                    "from": module_id, "to": "module:" + target, "kind": "imports",
                    "evidence": {"path": rel, "line": imp.get("line")},
                    "import_name": module_name,
                })
                if "/tests/" in rel or Path(rel).name.startswith("test_") or ".test." in rel or ".spec." in rel:
                    edges.append({
                        "from": module_id, "to": "module:" + target, "kind": "test-imports",
                        "evidence": {"path": rel, "line": imp.get("line")},
                    })
        for route in record["routes"]:
            is_route = route.get("method") != "CALL"
            route_id = ("route:" if is_route else "callsite:") + rel + "#" + route["method"] + " " + route["path"]
            nodes.append({
                "id": route_id, "kind": "http-route" if is_route else "call-site", "path": rel,
                "method": route["method"], "route": route["path"], "line": route.get("line"),
            })
            edges.append({
                "from": module_id, "to": route_id, "kind": "declares-route" if is_route else "contains-call-site",
                "evidence": {"path": rel, "line": route.get("line")},
            })
        local_symbols: dict[str, list[str]] = {}
        for symbol in record["symbols"]:
            local_symbols.setdefault(symbol.get("name", ""), []).append(symbol["id"])
        for call in record["calls"]:
            leaf = str(call.get("callee", "")).split(".")[-1]
            targets = local_symbols.get(leaf, [])
            if len(targets) == 1:
                edges.append({"from": module_id, "to": targets[0], "kind": "calls-local-symbol",
                              "evidence": {"path": rel, "line": call.get("line")},
                              "callee": call.get("callee")})

    document_paths = walk(root, DOC_ROOTS, {".md", ".mdx"})
    fixed_docs = [root / name for name in ("AGENTS.md", "README.md") if (root / name).is_file()]
    document_paths = sorted(set(document_paths + fixed_docs))
    doc_rel = {relative(p, root) for p in document_paths}
    known_paths = code_rel | doc_rel | config_rel
    for rel in sorted(config_rel):
        path = root / rel
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            content = ""
        nodes.append({"id": "config:" + rel, "kind": "configuration", "path": rel,
                      "title": path.name, "sha256": text_digest(content),
                      "line_count": content.count("\n") + 1})
    doc_texts: dict[str, str] = {}
    broken_doc_links: list[dict[str, Any]] = []
    linked_assets: set[str] = set()
    linked_directories: set[str] = set()
    for path in document_paths:
        rel = relative(path, root)
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            content = ""
        doc_texts[rel] = content
        nodes.append({
            "id": "doc:" + rel, "kind": document_kind(rel), "path": rel,
            "title": first_heading(content, Path(rel).name),
            "sha256": text_digest(content), "line_count": content.count("\n") + 1,
        })
        for match in MARKDOWN_LINK.finditer(content):
            raw_target = match.group(1).strip().strip("<>")
            target = resolve_doc_target(root, rel, raw_target, known_paths)
            line_no = content[:match.start()].count("\n") + 1
            if target:
                if target in doc_rel:
                    node_target = "doc:" + target
                elif target in code_rel:
                    node_target = "module:" + target
                elif target in config_rel:
                    node_target = "config:" + target
                elif (root / target).is_dir():
                    node_target = "directory:" + target
                    if target not in linked_directories:
                        linked_directories.add(target)
                        nodes.append({"id": node_target, "kind": "directory-reference", "path": target,
                                      "title": Path(target).name})
                else:
                    node_target = "asset:" + target
                    if target not in linked_assets:
                        linked_assets.add(target)
                        asset = root / target
                        try:
                            digest = hashlib.sha256(asset.read_bytes()).hexdigest()
                        except OSError:
                            digest = ""
                        nodes.append({"id": node_target, "kind": "linked-asset", "path": target,
                                      "title": asset.name, "sha256": digest})
                edges.append({
                    "from": "doc:" + rel, "to": node_target, "kind": "links-to",
                    "evidence": {"path": rel, "line": line_no},
                })
            else:
                clean_target = raw_target.split("#", 1)[0].split("?", 1)[0].strip()
                if clean_target and not raw_target.startswith(("#", "/", "//", "http://", "https://", "mailto:", "data:")):
                    broken_doc_links.append({"source": rel, "target": raw_target, "line": line_no})
        for match in PATH_REF.finditer(content):
            candidate = match.group(0).rstrip(".,;:)")
            if candidate in code_rel:
                edges.append({
                    "from": "doc:" + rel, "to": "module:" + candidate, "kind": "references-source",
                    "evidence": {"path": rel, "line": content[:match.start()].count("\n") + 1},
                })

    # Derive explicit semantic nodes for the event catalogue instead of treating
    # event names as untyped strings in the documentation.
    catalog_path = "apps/shared/events/topics.py"
    event_names: set[str] = set()
    if catalog_path in module_records:
        try:
            tree = ast.parse(texts.get(catalog_path, ""), filename=catalog_path)
            for statement in tree.body:
                targets: list[ast.AST] = []
                if isinstance(statement, (ast.Assign, ast.AnnAssign)):
                    targets = statement.targets if isinstance(statement, ast.Assign) else [statement.target]
                if not any(isinstance(t, ast.Name) and t.id == "EVENT_CATALOG" for t in targets):
                    continue
                for node in ast.walk(statement):
                    if isinstance(node, ast.Constant) and isinstance(node.value, str) and EVENT_NAME.match(node.value):
                        event_names.add(node.value)
        except SyntaxError:
            pass
    for event_name in sorted(event_names):
        event_id = "event:" + event_name
        nodes.append({"id": event_id, "kind": "event-type", "name": event_name,
                      "catalogue": catalog_path})
        edges.append({"from": "module:" + catalog_path, "to": event_id, "kind": "catalogues",
                      "evidence": {"path": catalog_path}})
        for rel, source in texts.items():
            if rel != catalog_path and event_name in source:
                edges.append({"from": "module:" + rel, "to": event_id, "kind": "mentions-event",
                              "evidence": {"path": rel}})

    # Numbered feature/spec references are evidence links, not proof that an
    # acceptance criterion is implemented. Keep this distinction explicit.
    spec_dirs: dict[str, str] = {}
    for rel in doc_rel:
        if not rel.startswith("specs/"):
            continue
        parts = rel.split("/")
        if len(parts) >= 2:
            spec_dirs[parts[1]] = "doc:" + rel if parts[-1] == "spec.md" else spec_dirs.get(parts[1], "")
    for rel, content in {**texts, **doc_texts}.items():
        source_id = ("doc:" if rel in doc_rel else "module:") + rel
        for match in SPEC_REF.finditer(content):
            number = match.group(1).zfill(3)
            target_dir = next((name for name in spec_dirs if name.startswith(number + "-")), None)
            if target_dir and spec_dirs.get(target_dir):
                edges.append({
                    "from": source_id, "to": spec_dirs[target_dir], "kind": "mentions-spec",
                    "evidence": {"path": rel, "line": content[:match.start()].count("\n") + 1},
                })

    nodes.sort(key=lambda n: n["id"])
    unique_edges: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for edge in edges:
        ev = edge.get("evidence", {})
        key = (edge["from"], edge["to"], edge["kind"], str(ev.get("line", "")))
        unique_edges[key] = edge
    edges = sorted(unique_edges.values(), key=lambda e: (e["from"], e["kind"], e["to"]))
    parser_errors: list[dict[str, str]] = []
    for rel, record in module_records.items():
        error = record.get("parse_error")
        if error:
            parser_errors.append({"path": rel, "error": str(error)[:800]})
    for parser_error in (ts_result.get("parser_error"), rust_result.get("parser_error")):
        if parser_error:
            parser_errors.append({"path": "<parser>", "error": str(parser_error)[:800]})
    mapped = {n["path"] for n in nodes if n.get("kind") == "source-module"}
    missing = sorted(code_rel - mapped)
    language_counts: dict[str, dict[str, int]] = {}
    for rel, record in module_records.items():
        language = Path(rel).suffix.lower().lstrip(".")
        lang = language_counts.setdefault(language, {"files": 0, "ast_parsed": 0, "errors": 0})
        lang["files"] += 1
        if record.get("parser") in {"python-ast", "typescript-compiler-ast", "rust-syn-ast"} and not record.get("parse_error"):
            lang["ast_parsed"] += 1
        if record.get("parse_error"):
            lang["errors"] += 1
    tracked_candidates = tracked_source_candidates(root)
    unmapped_tracked = (
        sorted(set(tracked_candidates) - code_rel) if tracked_candidates is not None else []
    )
    tracked_mapped = (
        len(set(tracked_candidates) & code_rel) if tracked_candidates is not None else 0
    )
    coverage = {
        "source_roots": list(CODE_ROOTS),
        "tracked_source_inventory_available": tracked_candidates is not None,
        "tracked_source_candidate_files": len(tracked_candidates) if tracked_candidates is not None else None,
        "tracked_source_coverage_percent": (
            round(100 * tracked_mapped / max(1, len(tracked_candidates)), 2)
            if tracked_candidates is not None else None
        ),
        "unmapped_tracked_source_candidates": unmapped_tracked,
        "root_level_source_files": sum(1 for rel in code_rel if "/" not in rel),
        "configuration_files": len(config_rel),
        "code_files": len(code_rel), "mapped_code_files": len(mapped),
        "file_mapping_percent": round(100 * len(mapped) / max(1, len(code_rel)), 2),
        "symbols": sum(1 for n in nodes if n["id"].startswith("symbol:")),
        "documents": len(doc_rel), "events": len(event_names),
        "http_routes": sum(1 for n in nodes if n["kind"] == "http-route"),
        "local_call_edges": sum(1 for e in edges if e["kind"] == "calls-local-symbol"),
        "broken_doc_links": len(broken_doc_links),
        "edges": len(edges), "parser_errors": len(parser_errors),
        "unmapped_code_files": missing, "languages": language_counts,
        "parser_tool_errors": [x for x in parser_errors if x["path"] == "<parser>"],
    }
    return {
        "schema_version": 1,
        "purpose": "Source-derived semantic documentation graph; static evidence is not runtime proof.",
        "coverage": coverage, "nodes": nodes, "edges": edges,
        "broken_doc_links": broken_doc_links, "parser_errors": parser_errors,
        "module_records": module_records,
    }


def context_view(graph: dict[str, Any], target_path: str) -> str:
    path = target_path.replace("\\", "/").lstrip("./")
    modules = {n["path"]: n for n in graph["nodes"] if n.get("kind") == "source-module"}
    if path not in modules:
        matches = [p for p in modules if p.endswith("/" + path) or Path(p).name == path]
        if len(matches) != 1:
            return "Path not found or ambiguous: " + path + "\nMatches: " + ", ".join(matches[:30])
        path = matches[0]
    module_id = "module:" + path
    record = graph["module_records"].get(path, {})
    incoming = [e for e in graph["edges"] if e["to"] == module_id]
    outgoing = [e for e in graph["edges"] if e["from"] == module_id]
    symbol_nodes = [n for n in graph["nodes"] if n.get("path") == path and n["id"].startswith("symbol:")]
    route_nodes = [n for n in graph["nodes"] if n.get("path") == path and n["kind"] == "http-route"]
    out = [
        "# Context packet: " + path, "",
        "Static source-derived context. Import or citation edges are navigation evidence, not proof of runtime wiring.",
        "",
        "## Module facts",
        "- Parser: " + str(record.get("parser", "inventory-only")),
        "- Syntax error: " + str(record.get("parse_error") or "none"),
        "- Symbols: " + str(len(symbol_nodes)),
        "- Declared HTTP routes: " + str(len(route_nodes)),
        "",
        "## Symbols",
    ]
    out.extend("- " + str(s.get("kind")) + " " + str(s.get("name")) +
               (" (line " + str(s.get("line")) + ")" if s.get("line") else "")
               for s in symbol_nodes[:120])
    out.extend(["", "## Declared routes"])
    out.extend("- " + str(r.get("method")) + " " + str(r.get("route")) for r in route_nodes[:80])
    out.extend(["", "## Direct relationships"])
    for edge in outgoing[:160]:
        out.append("- " + edge["kind"] + " → " + edge["to"])
    for edge in incoming[:160]:
        out.append("- " + edge["kind"] + " ← " + edge["from"])
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--check", action="store_true",
                        help="fail on syntax/parser errors or incomplete file mapping")
    parser.add_argument("--json", action="store_true", help="print the complete graph as JSON")
    parser.add_argument("--output", type=Path, help="write the graph JSON to this path")
    parser.add_argument("--context", metavar="PATH", help="print a compact context packet for a source path")
    args = parser.parse_args(argv)
    graph = build_graph(args.root.resolve())
    coverage = graph["coverage"]
    if args.output:
        target = args.output if args.output.is_absolute() else args.root.resolve() / args.output
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(graph, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.context:
        print(context_view(graph, args.context))
    elif args.json:
        print(json.dumps(graph, indent=2, ensure_ascii=False))
    else:
        print(json.dumps(coverage, indent=2, ensure_ascii=False))
    failures = []
    if args.check:
        if coverage["mapped_code_files"] != coverage["code_files"]:
            failures.append("not every first-party code file has a source-module node")
        if not coverage["tracked_source_inventory_available"]:
            failures.append("could not enumerate tracked source files with git ls-files")
        if coverage["unmapped_tracked_source_candidates"]:
            failures.append("tracked source files exist outside the declared semantic scan roots")
        if graph["parser_errors"]:
            failures.append("one or more files failed syntax parsing or a parser tool failed")
        if coverage["broken_doc_links"]:
            failures.append("one or more local Markdown links are unresolved")
        if coverage["parser_tool_errors"]:
            failures.append("one or more language AST parsers could not run")
    if failures:
        for failure in failures:
            print("ERROR: " + failure, file=sys.stderr)
        for item in graph["parser_errors"][:100]:
            print("  " + item["path"] + ": " + item["error"], file=sys.stderr)
        for item in graph["broken_doc_links"][:100]:
            print("  " + item["source"] + ":" + str(item["line"]) + ": " + item["target"], file=sys.stderr)
        return 1
    if args.check:
        print("Semantic documentation graph is complete for the configured first-party source roots.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
