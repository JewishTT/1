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
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CODE_ROOTS = ("apps", "bench", "benchmarks", "tools", "platform_model", "implementation", "specs")
DOC_ROOTS = ("docs", "specs", ".opencode", ".specify")
SOURCE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".rs", ".proto", ".sql", ".css", ".scss", ".html"}
AST_PARSERS = {"python-ast", "typescript-compiler-ast", "rust-syn-ast", "postcss-ast", "parse5-ast", "sqlglot-ast", "protobuf-descriptor-ast"}
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
ADR_REF = re.compile(r"\bADR-(\d{4})\b")


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



def scan_sql_text(path: str, text: str) -> dict[str, Any]:
    """Parse SQL with SQLGlot and expose statement, table and column AST nodes."""
    common: dict[str, Any] = {
        "path": path, "parser": "sqlglot-ast", "parse_error": None,
        "docstring": "", "line_count": text.count("\n") + 1,
        "symbols": [], "imports": [], "routes": [], "calls": [], "references": [],
    }
    try:
        import sqlglot
        from sqlglot import exp
    except ImportError as exc:
        common["parse_error"] = "sqlglot is required for the SQL AST: " + str(exc)
        return common
    try:
        statements = [statement for statement in sqlglot.parse(text) if statement is not None]
    except Exception as exc:
        common["parse_error"] = str(exc)[:1600]
        return common
    symbols: list[dict[str, Any]] = []
    references: list[dict[str, Any]] = []

    def line_of(node: Any, fallback: int = 1) -> int:
        value = getattr(node, "meta", {}).get("line")
        return int(value) if isinstance(value, int) and value > 0 else fallback

    def table_name(table: Any) -> str:
        parts = [getattr(part, "name", "") for part in getattr(table, "parts", ())]
        return ".".join(str(part) for part in parts if part) or str(getattr(table, "name", ""))

    for index, statement in enumerate(statements, start=1):
        statement_line = line_of(statement)
        statement_kind = str(getattr(statement, "key", "statement") or "statement").lower()
        create_table = isinstance(statement, exp.Create) and str(statement.args.get("kind", "")).upper() == "TABLE"
        target_table = statement.find(exp.Table) if create_table else None
        target_name = table_name(target_table) if target_table is not None else ""
        symbols.append({
            "name": "statement_" + str(index).zfill(4),
            "qualified_name": "statement:" + str(index).zfill(4) + ":" + statement_kind,
            "kind": "sql-statement", "line": statement_line, "public": True,
            "signature": statement.sql()[:240],
        })
        for table in statement.find_all(exp.Table):
            full_table_name = table_name(table)
            if not full_table_name:
                continue
            if create_table and table is target_table:
                symbols.append({
                    "name": str(getattr(table, "name", full_table_name)),
                    "qualified_name": full_table_name, "kind": "sql-table",
                    "line": line_of(table, statement_line), "public": True,
                    "signature": table.sql()[:240],
                })
            else:
                references.append({
                    "target": full_table_name, "target_kind": "sql-table",
                    "kind": "references-sql-table", "line": line_of(table, statement_line),
                })
        if create_table and target_name:
            for column in statement.find_all(exp.ColumnDef):
                column_name = str(getattr(column, "name", "") or "")
                if column_name:
                    symbols.append({
                        "name": column_name, "qualified_name": target_name + "." + column_name,
                        "kind": "sql-column", "line": line_of(column, statement_line),
                        "public": True, "signature": column.sql()[:240],
                    })
    common["symbols"] = symbols
    common["references"] = references
    return common


def scan_proto_files(root: Path, files: list[Path]) -> dict[str, dict[str, Any]]:
    """Compile .proto sources with grpc_tools.protoc and derive symbols from descriptors."""
    results: dict[str, dict[str, Any]] = {}
    if not files:
        return results
    try:
        from google.protobuf.descriptor_pb2 import FileDescriptorSet
    except ImportError as exc:
        for path in files:
            rel = relative(path, root)
            results[rel] = {
                "path": rel, "parser": "protobuf-descriptor-ast",
                "parse_error": "protobuf descriptors are required for the .proto AST: " + str(exc),
                "symbols": [], "imports": [], "routes": [], "calls": [], "references": [],
            }
        return results

    for path in sorted(files):
        rel = relative(path, root)
        record: dict[str, Any] = {
            "path": rel, "parser": "protobuf-descriptor-ast", "parse_error": None,
            "docstring": "", "line_count": 0,
            "symbols": [], "imports": [], "routes": [], "calls": [], "references": [],
        }
        with tempfile.TemporaryDirectory(prefix="semantic-proto-") as temp_dir:
            descriptor_path = Path(temp_dir) / "descriptor-set.pb"
            command = [
                sys.executable, "-m", "grpc_tools.protoc", "-I", str(root),
                "--include_source_info", "--include_imports",
                "--descriptor_set_out=" + str(descriptor_path), rel,
            ]
            try:
                proc = subprocess.run(
                    command, cwd=root, capture_output=True, text=True, timeout=120, check=False
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                record["parse_error"] = "grpc_tools.protoc: " + str(exc)
                results[rel] = record
                continue
            if proc.returncode:
                record["parse_error"] = ("grpc_tools.protoc: " + (proc.stderr or proc.stdout or "parse failed"))[-1600:]
                results[rel] = record
                continue
            try:
                descriptor_set = FileDescriptorSet()
                descriptor_set.ParseFromString(descriptor_path.read_bytes())
            except Exception as exc:
                record["parse_error"] = "invalid descriptor set: " + str(exc)
                results[rel] = record
                continue

        file_proto = next(
            (item for item in descriptor_set.file if item.name == rel or item.name.endswith("/" + rel)),
            None,
        )
        if file_proto is None:
            record["parse_error"] = "protoc returned no descriptor for " + rel
            results[rel] = record
            continue
        locations = {tuple(item.path): item for item in file_proto.source_code_info.location}

        def line_for(path_parts: list[int], fallback: int = 1) -> int:
            location = locations.get(tuple(path_parts))
            if location is None or not location.span:
                return fallback
            return int(location.span[0]) + 1

        def full_name(parent: str, name: str) -> str:
            return ".".join(part for part in (parent, name) if part)

        def add_symbol(kind: str, name: str, qualified_name: str, source_path: list[int], signature: str = "") -> None:
            record["symbols"].append({
                "name": name, "qualified_name": qualified_name, "kind": kind,
                "line": line_for(source_path), "public": True, "signature": signature,
            })

        def scan_enum(enum_proto: Any, source_path: list[int], parent_name: str) -> None:
            qualified = full_name(parent_name, enum_proto.name)
            add_symbol("proto-enum", enum_proto.name, qualified, source_path, "enum " + enum_proto.name)
            for value_index, value in enumerate(enum_proto.value):
                add_symbol(
                    "proto-enum-value", value.name, full_name(qualified, value.name),
                    source_path + [2, value_index],
                    value.name + " = " + str(value.number),
                )

        def scan_message(message_proto: Any, source_path: list[int], parent_name: str) -> None:
            qualified = full_name(parent_name, message_proto.name)
            add_symbol("proto-message", message_proto.name, qualified, source_path, "message " + message_proto.name)
            for field_index, field in enumerate(message_proto.field):
                field_path = source_path + [2, field_index]
                add_symbol(
                    "proto-field", field.name, full_name(qualified, field.name), field_path,
                    (field.type_name + " " if field.type_name else "") + field.name + " = " + str(field.number),
                )
                if field.type_name:
                    record["references"].append({
                        "target": field.type_name.lstrip("."), "target_kind": "proto-type",
                        "kind": "uses-proto-type", "line": line_for(field_path),
                    })
            for nested_index, nested in enumerate(message_proto.nested_type):
                scan_message(nested, source_path + [3, nested_index], qualified)
            for enum_index, enum_proto in enumerate(message_proto.enum_type):
                scan_enum(enum_proto, source_path + [4, enum_index], qualified)

        package_name = file_proto.package or ""
        record["docstring"] = "Protobuf package " + package_name if package_name else "Protobuf source"
        for dep_index, dependency in enumerate(file_proto.dependency):
            record["references"].append({
                "target": dependency, "target_kind": "source-path",
                "kind": "imports-proto-file", "line": line_for([3, dep_index]),
            })
        for message_index, message in enumerate(file_proto.message_type):
            scan_message(message, [4, message_index], package_name)
        for enum_index, enum_proto in enumerate(file_proto.enum_type):
            scan_enum(enum_proto, [5, enum_index], package_name)
        for service_index, service in enumerate(file_proto.service):
            service_path = [6, service_index]
            service_name = full_name(package_name, service.name)
            add_symbol("proto-service", service.name, service_name, service_path, "service " + service.name)
            for method_index, method in enumerate(service.method):
                method_path = service_path + [2, method_index]
                method_name = full_name(service_name, method.name)
                add_symbol("proto-rpc", method.name, method_name, method_path, method.name)
                for target in (method.input_type, method.output_type):
                    if target:
                        record["references"].append({
                            "target": target.lstrip("."), "target_kind": "proto-type",
                            "kind": "uses-proto-type", "line": line_for(method_path),
                        })
        try:
            record["line_count"] = path.read_text(encoding="utf-8").count("\n") + 1
        except OSError:
            record["line_count"] = 0
        results[rel] = record
    return results


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
    ast_script_paths = [p for p in code_paths if p.suffix.lower() in {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".css", ".scss", ".html"}]
    rust_paths = [p for p in code_paths if p.suffix.lower() == ".rs"]
    proto_paths = [p for p in code_paths if p.suffix.lower() == ".proto"]
    sql_paths = [p for p in code_paths if p.suffix.lower() == ".sql"]
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
    if ast_script_paths:
        ts_result = run_parser(
            ["node", "tools/semantic_docgraph_ts.mjs", "--root", str(root)],
            root, "TypeScript/PostCSS/parse5 AST",
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
    proto_by_path = scan_proto_files(root, proto_paths)
    sql_by_path = {
        relative(path, root): scan_sql_text(relative(path, root), texts[relative(path, root)])
        for path in sql_paths
    }
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

    symbol_lookup_by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    symbol_lookup_by_qname: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for rel in sorted(code_rel):
        record = module_records.get(rel)
        suffix = Path(rel).suffix.lower()
        if suffix in {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".css", ".scss", ".html"}:
            record = ts_by_path.get(rel)
            if record is None:
                record = {
                    "path": rel, "parser": "typescript-compiler-ast", "parse_error": "file missing from parser output",
                    "symbols": [], "imports": [], "routes": [], "calls": [], "references": [],
                }
            module_records[rel] = record
        elif suffix == ".proto":
            record = proto_by_path.get(rel)
            if record is None:
                record = {
                    "path": rel, "parser": "protobuf-descriptor-ast",
                    "parse_error": "file missing from protobuf descriptor output",
                    "symbols": [], "imports": [], "routes": [], "calls": [], "references": [],
                }
            module_records[rel] = record
        elif suffix == ".sql":
            module_records[rel] = sql_by_path.get(rel, {
                "path": rel, "parser": "sqlglot-ast", "parse_error": "file missing from SQL AST output",
                "symbols": [], "imports": [], "routes": [], "calls": [], "references": [],
            })
        elif suffix == ".rs":
            record = rust_by_path.get(rel)
            if record is None:
                record = {
                    "path": rel, "parser": "rust-syn-ast", "parse_error": "file missing from parser output",
                    "symbols": [], "imports": [], "routes": [],
                }
            module_records[rel] = record
        record = module_records[rel]
        module_id = "module:" + rel
        record.setdefault("imports", [])
        record.setdefault("symbols", [])
        record.setdefault("routes", [])
        record.setdefault("calls", [])
        record.setdefault("references", [])
        for symbol in record["symbols"]:
            if not symbol.get("id"):
                qualified_name = symbol.get("qualified_name") or symbol.get("name") or "<anonymous>"
                symbol["id"] = "symbol:" + rel + "#" + qualified_name
            node = {
                "id": symbol["id"], "kind": symbol.get("kind", "symbol"),
                "path": rel, "name": symbol.get("qualified_name", symbol.get("name", "")),
                "line": symbol.get("line"),
                "docstring": symbol.get("docstring", ""),
                "public": symbol.get("public"),
            }
            if symbol.get("signature"):
                node["signature"] = symbol["signature"]
            nodes.append(node)
            if symbol.get("name"):
                symbol_lookup_by_name[str(symbol["name"]).casefold()].append(symbol)
            if symbol.get("qualified_name"):
                symbol_lookup_by_qname[str(symbol["qualified_name"]).lstrip(".").casefold()].append(symbol)
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
                for candidate in (
                    base, base.with_suffix(".ts"), base.with_suffix(".tsx"),
                    base.with_suffix(".js"), base.with_suffix(".jsx"),
                    base.with_suffix(".mjs"), base.with_suffix(".cjs"),
                    base / "index.ts", base / "index.tsx", base / "index.js",
                    base / "index.jsx", base / "index.mjs", base / "index.cjs",
                ):
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

    # Resolve cross-language references only when syntax-backed symbols support the
    # edge. Unresolved names remain reported; no guessed target is promoted to fact.
    unresolved_semantic_references: list[dict[str, Any]] = []
    for rel in sorted(code_rel):
        record = module_records.get(rel, {})
        for reference in record.get("references", []):
            target = str(reference.get("target", "")).strip()
            target_kind = str(reference.get("target_kind", ""))
            reference_kind = str(reference.get("kind", "references"))
            line = reference.get("line")
            if not target:
                continue
            target_ids: list[str] = []
            if target_kind == "source-path":
                resolved = resolve_doc_target(root, rel, target, code_rel)
                if resolved in code_rel:
                    target_ids.append("module:" + str(resolved))
                elif resolved and (root / resolved).is_file():
                    target_id = "asset:" + str(resolved)
                    target_ids.append(target_id)
                    if not any(node.get("id") == target_id for node in nodes):
                        asset_path = root / resolved
                        try:
                            digest = hashlib.sha256(asset_path.read_bytes()).hexdigest()
                        except OSError:
                            digest = ""
                        nodes.append({
                            "id": target_id, "kind": "linked-asset", "path": resolved,
                            "title": asset_path.name, "sha256": digest,
                        })
                elif target.startswith(("apps/", "bench/", "benchmarks/", "tools/", "platform_model/", "specs/")):
                    unresolved_semantic_references.append({
                        "source": rel, "target": target, "target_kind": target_kind,
                        "kind": reference_kind, "line": line,
                    })
            else:
                allowed_kinds = {
                    "sql-table": {"sql-table"},
                    "proto-type": {"proto-message", "proto-enum"},
                    "css-custom-property": {"css-custom-property"},
                    "css-class-selector": {"css-class-selector"},
                    "css-id-selector": {"css-id-selector"},
                }.get(target_kind, set())
                normalized = target.lstrip(".").casefold()
                matches = [
                    symbol for symbol in symbol_lookup_by_qname.get(normalized, [])
                    if symbol.get("kind") in allowed_kinds
                ]
                if not matches:
                    matches = [
                        symbol for symbol in symbol_lookup_by_name.get(normalized, [])
                        if symbol.get("kind") in allowed_kinds
                    ]
                target_ids.extend(str(symbol["id"]) for symbol in matches if symbol.get("id"))
                if not matches and allowed_kinds:
                    unresolved_semantic_references.append({
                        "source": rel, "target": target, "target_kind": target_kind,
                        "kind": reference_kind, "line": line,
                    })
            for target_id in sorted(set(target_ids)):
                edges.append({
                    "from": "module:" + rel, "to": target_id, "kind": reference_kind,
                    "evidence": {"path": rel, "line": line, "target": target},
                })

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
    spec_doc_link_violations: list[dict[str, Any]] = []
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
                if rel.startswith("specs/") and target.startswith("docs/"):
                    spec_doc_link_violations.append({"source": rel, "target": target, "line": line_no})
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

    # Derive decision edges from stable ADR identifiers, without wiring normative specs
    # to documentation projections through Markdown links.
    adr_by_id = {}
    for rel in doc_rel:
        match = re.match(r"docs/adr/(\d{4})-[^/]+\.md$", rel)
        if match:
            adr_by_id.setdefault(match.group(1), []).append(rel)
    for rel, content in doc_texts.items():
        if not rel.startswith("specs/"):
            continue
        for match in ADR_REF.finditer(content):
            targets = adr_by_id.get(match.group(1), [])
            if len(targets) == 1:
                edges.append({
                    "from": "doc:" + rel, "to": "doc:" + targets[0],
                    "kind": "references-decision-id",
                    "evidence": {
                        "path": rel, "line": content[:match.start()].count("\n") + 1,
                        "identifier": "ADR-" + match.group(1),
                    },
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
    ast_parsed_paths: set[str] = set()
    for rel, record in module_records.items():
        language = Path(rel).suffix.lower().lstrip(".")
        lang = language_counts.setdefault(language, {
            "files": 0, "ast_parsed": 0, "errors": 0, "diagnostics": 0,
        })
        lang["files"] += 1
        parsed = record.get("parser") in AST_PARSERS and not record.get("parse_error")
        if parsed:
            lang["ast_parsed"] += 1
            ast_parsed_paths.add(rel)
        if record.get("parse_error"):
            lang["errors"] += 1
        lang["diagnostics"] += len(record.get("diagnostics", []))
    ast_unparsed_paths = sorted(code_rel - ast_parsed_paths)
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
        "ast_parsed_files": len(ast_parsed_paths),
        "ast_coverage_percent": round(100 * len(ast_parsed_paths) / max(1, len(code_rel)), 2),
        "ast_unparsed_files": ast_unparsed_paths,
        "symbols": sum(1 for n in nodes if n["id"].startswith("symbol:")),
        "documents": len(doc_rel), "events": len(event_names),
        "http_routes": sum(1 for n in nodes if n["kind"] == "http-route"),
        "local_call_edges": sum(1 for e in edges if e["kind"] == "calls-local-symbol"),
        "semantic_reference_edges": sum(1 for e in edges if e["kind"] in {
            "references-sql-table", "uses-proto-type", "imports-proto-file",
            "imports-css-source", "uses-css-custom-property", "matches-css-class",
            "matches-css-id", "references-html-asset",
        }),
        "unresolved_semantic_references": len(unresolved_semantic_references),
        "broken_doc_links": len(broken_doc_links),
        "spec_doc_markdown_links": len(spec_doc_link_violations),
        "edges": len(edges), "parser_errors": len(parser_errors),
        "unmapped_code_files": missing, "languages": language_counts,
        "parser_tool_errors": [x for x in parser_errors if x["path"] == "<parser>"],
    }
    return {
        "schema_version": 1,
        "purpose": "Source-derived semantic documentation graph; static evidence is not runtime proof.",
        "coverage": coverage, "nodes": nodes, "edges": edges,
        "broken_doc_links": broken_doc_links,
        "spec_doc_link_violations": spec_doc_link_violations,
        "unresolved_semantic_references": unresolved_semantic_references,
        "parser_errors": parser_errors,
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
        if coverage["ast_parsed_files"] != coverage["code_files"]:
            failures.append("parser-backed AST coverage is below 100% for the declared source scope")
        if not coverage["tracked_source_inventory_available"]:
            failures.append("could not enumerate tracked source files with git ls-files")
        if coverage["unmapped_tracked_source_candidates"]:
            failures.append("tracked source files exist outside the declared semantic scan roots")
        if graph["parser_errors"]:
            failures.append("one or more files failed syntax parsing or a parser tool failed")
        if coverage["broken_doc_links"]:
            failures.append("one or more local Markdown links are unresolved")
        if graph["spec_doc_link_violations"]:
            failures.append("normative specs must not Markdown-link to docs; use local decision records and stable IDs")
        if coverage["parser_tool_errors"]:
            failures.append("one or more language AST parsers could not run")
    if failures:
        for failure in failures:
            print("ERROR: " + failure, file=sys.stderr)
        for item in graph["parser_errors"][:100]:
            print("  " + item["path"] + ": " + item["error"], file=sys.stderr)
        for item in graph["broken_doc_links"][:100]:
            print("  " + item["source"] + ":" + str(item["line"]) + ": " + item["target"], file=sys.stderr)
        for item in graph["spec_doc_link_violations"][:100]:
            print("  policy: " + item["source"] + ":" + str(item["line"]) + " -> " + item["target"], file=sys.stderr)
        return 1
    if args.check:
        print("Semantic documentation graph is complete for the configured first-party source roots.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
