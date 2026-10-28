"""Contract tests for the standalone semantic documentation graph."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
MODULE_PATH = ROOT / "tools" / "semantic_docgraph.py"
spec = importlib.util.spec_from_file_location("semantic_docgraph", MODULE_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Cannot load semantic documentation graph: {MODULE_PATH}")
semantic_docgraph = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = semantic_docgraph
spec.loader.exec_module(semantic_docgraph)


class PythonAstContractTests(unittest.TestCase):
    def test_records_public_symbols_arguments_and_decorated_routes(self) -> None:
        source = '''"""Module contract."""\n\nfrom typing import Any\n\nclass Engine:\n    """An engine."""\n\n    def run(self, value: str, retry: int = 2) -> Any:\n        return parse(value)\n\ndef parse(value: str) -> str:\n    return value.strip()\n\n@router.post("/v1/items")\ndef create_item(payload: dict) -> dict:\n    return payload\n'''
        result = semantic_docgraph.scan_python_text("apps/example.py", source)
        self.assertEqual(result["parser"], "python-ast")
        self.assertIsNone(result["parse_error"])
        symbols = {(item["qualified_name"], item["kind"]) for item in result["symbols"]}
        self.assertIn(("Engine", "class"), symbols)
        self.assertIn(("Engine.run", "function"), symbols)
        self.assertIn(("parse", "function"), symbols)
        engine_method = next(item for item in result["symbols"] if item["qualified_name"] == "Engine.run")
        self.assertIn("value: str", engine_method["arguments"])
        self.assertEqual(result["routes"], [{
            "method": "POST", "path": "/v1/items", "line": 14,
            "decorator": "router.post"
        }])
        self.assertIn({"callee": "parse", "line": 9}, result["calls"])

    def test_syntax_errors_are_reported_not_silently_discarded(self) -> None:
        result = semantic_docgraph.scan_python_text("broken.py", "def broken(:\n  pass\n")
        self.assertEqual(result["parser"], "python-ast")
        self.assertIsNotNone(result["parse_error"])
        self.assertEqual(result["symbols"], [])

    def test_doc_link_resolver_resolves_relative_and_root_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "docs" / "architecture").mkdir(parents=True)
            (root / "docs" / "adr").mkdir(parents=True)
            (root / "docs" / "adr" / "0001-decision.md").write_text("# ADR\n", encoding="utf-8")
            (root / "apps").mkdir()
            (root / "apps" / "engine.py").write_text("pass\n", encoding="utf-8")
            relative = semantic_docgraph.resolve_doc_target(
                root, "docs/architecture/overview.md", "../adr/0001-decision.md#status",
                {"docs/adr/0001-decision.md"},
            )
            absolute = semantic_docgraph.resolve_doc_target(
                root, "docs/architecture/overview.md", "apps/engine.py", {"apps/engine.py"},
            )
            self.assertEqual(relative, "docs/adr/0001-decision.md")
            self.assertEqual(absolute, "apps/engine.py")

    def test_source_import_resolution_uses_repository_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "apps" / "shared" / "contracts").mkdir(parents=True)
            (root / "apps" / "shared" / "contracts" / "thing.py").write_text("class Thing: pass\n", encoding="utf-8")
            (root / "apps" / "acquisition").mkdir(parents=True)
            source_path = root / "apps" / "acquisition" / "worker.py"
            source_path.write_text("from contracts.thing import Thing\n", encoding="utf-8")
            resolved = semantic_docgraph.source_module_target(
                root, "apps/acquisition/worker.py", "contracts.thing", 0,
            )
            self.assertEqual(resolved, "apps/shared/contracts/thing.py")


if __name__ == "__main__":
    unittest.main()
