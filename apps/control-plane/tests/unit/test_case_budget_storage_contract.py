from __future__ import annotations

from pathlib import Path

from db.schema import Budget


def test_budget_orm_shape_matches_the_durable_runtime_contract() -> None:
    columns = Budget.__table__.columns
    assert set(columns.keys()) == {
        "budget_id",
        "tenant_id",
        "investigation_id",
        "limits",
        "current_usage",
        "created_at",
    }
    assert columns["budget_id"].primary_key
    assert not columns["tenant_id"].nullable


def test_budget_migration_follows_type_signals_and_preserves_legacy_tables() -> None:
    root = Path(__file__).resolve().parents[2]
    migration = (
        root / "db" / "migrations" / "versions" / "033_durable_case_budgets.py"
    ).read_text(encoding="utf-8")

    assert 'revision = "033_durable_case_budgets"' in migration
    assert 'down_revision = "032_type_signals"' in migration
    assert 'has_table("budgets")' in migration
    for column in (
        "budget_id",
        "tenant_id",
        "investigation_id",
        "limits",
        "current_usage",
        "created_at",
    ):
        assert f'"{column}"' in migration
    assert "forward-only" in migration
