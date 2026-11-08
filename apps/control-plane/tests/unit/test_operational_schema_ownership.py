"""Operational code must not create or mutate schema outside Alembic."""

from __future__ import annotations

import ast
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[2]


def test_operational_python_does_not_call_create_all_or_create_tables() -> None:
    violations: list[str] = []
    for source in PROJECT.rglob("*.py"):
        relative = source.relative_to(PROJECT)
        if "tests" in relative.parts or "migrations" in relative.parts:
            continue
        if relative == Path("db/session.py"):
            # Explicit test/dev helper; never imported by an operational service.
            continue
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                target = node.func
                name = target.id if isinstance(target, ast.Name) else (
                    target.attr if isinstance(target, ast.Attribute) else ""
                )
                if name in {"create_all", "create_tables"}:
                    violations.append(f"{relative}:{node.lineno}:{name}")
            elif isinstance(node, ast.ImportFrom) and node.module == "db.session":
                if any(alias.name == "create_tables" for alias in node.names):
                    violations.append(f"{relative}:{node.lineno}:import create_tables")
    assert not violations, "Operational schema DDL found outside Alembic:\n" + "\n".join(violations)
