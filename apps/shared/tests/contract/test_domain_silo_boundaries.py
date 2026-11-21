"""Architecture guard: domain consumers obtain context from Intelligence.

These checks intentionally inspect imports rather than class names: a consumer
must not be able to grow a parallel collection/recon stack by importing one.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[4]
CONSUMERS = (ROOT / "apps" / "economics", ROOT / "apps" / "specops_ci")
FORBIDDEN_IMPORT_ROOTS = {
    "acquisition",
    "zero",
    "interpretation",
    "admission",
    "projection",
    "bulk_ingestion",
}
FORBIDDEN_IMPORT_PREFIXES = (
    "services.source_registry",
    "services.dispatcher",
    "services.recon",
    "api.routes.connectors",
)


def _imported_modules(path: Path) -> list[tuple[str, int]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((alias.name, node.lineno) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.append((node.module, node.lineno))
    return found


@pytest.mark.parametrize("consumer", CONSUMERS, ids=lambda path: path.name)
def test_domain_consumers_do_not_import_recon_or_acquisition(consumer: Path) -> None:
    assert consumer.is_dir(), f"domain package is missing: {consumer}"
    violations: list[str] = []
    for source in sorted(consumer.rglob("*.py")):
        if any(part in {"__pycache__", ".venv"} for part in source.parts):
            continue
        for module, line in _imported_modules(source):
            root = module.split(".", 1)[0]
            if root in FORBIDDEN_IMPORT_ROOTS or any(
                module == prefix or module.startswith(prefix + ".")
                for prefix in FORBIDDEN_IMPORT_PREFIXES
            ):
                violations.append(f"{source.relative_to(ROOT)}:{line}: {module}")
    assert not violations, "domain silo imported Intelligence internals:\n" + "\n".join(violations)


def test_both_consumers_use_the_shared_intelligence_read_contract() -> None:
    for consumer in CONSUMERS:
        source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in consumer.rglob("*.py")
            if path.is_file()
        )
        assert "IntelligenceReadPort" in source, (
            f"{consumer.name} must consume the shared IntelligenceReadPort contract"
        )
