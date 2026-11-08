from __future__ import annotations

from pathlib import Path

import pytest


TABLES = (
    "investigation_contexts",
    "context_revisions",
    "research_obligations",
    "research_actions",
    "context_frontiers",
    "context_action_memory",
)


def test_context_store_tables_have_a_canonical_forward_only_migration() -> None:
    root = Path(__file__).resolve().parents[2]
    migration = (
        root / "db" / "migrations" / "versions" / "034_durable_investigation_contexts.py"
    ).read_text(encoding="utf-8")

    assert 'revision = "034_durable_investigation_contexts"' in migration
    assert 'down_revision = "033_durable_case_budgets"' in migration
    assert "forward-only" in migration
    assert "_has_table(bind," in migration
    for table in TABLES:
        assert f'"{table}"' in migration


@pytest.mark.parametrize("table", TABLES)
def test_context_store_schema_contains_the_runtime_write_contract(table: str) -> None:
    root = Path(__file__).resolve().parents[2]
    store = (root / "context_engine" / "postgres_store.py").read_text(encoding="utf-8")
    migration = (
        root / "db" / "migrations" / "versions" / "034_durable_investigation_contexts.py"
    ).read_text(encoding="utf-8")

    assert f"CREATE TABLE IF NOT EXISTS {table}" in store
    assert f'"{table}"' in migration

    for column in ("context_id", "tenant_id", "investigation_id", "identity_schema", "payload", "created_at"):
        assert f'"{column}"' in migration
