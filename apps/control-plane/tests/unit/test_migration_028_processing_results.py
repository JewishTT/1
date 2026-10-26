"""Migration and ORM parity tests for durable processing results."""
from __future__ import annotations

import inspect
import re
import sys
from pathlib import Path

_APPS = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_APPS / "shared"))
sys.path.insert(0, str(_APPS / "control-plane"))

VERSIONS_DIR = _APPS / "control-plane" / "db" / "migrations" / "versions"
MIGRATION = VERSIONS_DIR / "028_observation_processing_results.py"


def _load_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("revision_028_processing_results_under_test", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _body(module, name: str) -> str:
    return re.sub(r'""".*?"""', "", inspect.getsource(getattr(module, name)), flags=re.DOTALL)


def test_028_is_the_single_additive_head_after_027():
    assert MIGRATION.is_file()
    module = _load_module()
    assert module.revision == "028_observation_processing_results"
    assert module.down_revision == "027_person_research_case_records"

    parents: dict[str, str | None] = {}
    revision_re = re.compile(r'^revision\s*=\s*["\']([^"\']+)["\']', re.MULTILINE)
    parent_re = re.compile(r'^down_revision\s*=\s*(.+)$', re.MULTILINE)
    for path in VERSIONS_DIR.glob("*.py"):
        if path.name == "__init__.py":
            continue
        source = path.read_text(encoding="utf-8")
        revision = revision_re.search(source)
        parent = parent_re.search(source)
        assert revision and parent, path.name
        raw_parent = parent.group(1).strip()
        if raw_parent == "None":
            parents[revision.group(1)] = None
        else:
            value = re.match(r'^["\']([^"\']+)["\']$', raw_parent)
            assert value, f"unsupported migration parent syntax: {path.name}"
            parents[revision.group(1)] = value.group(1)
    assert parents["028_observation_processing_results"] == "027_person_research_case_records"
    assert len([revision for revision in parents if revision not in parents.values()]) == 1


def test_028_has_idempotency_key_and_append_safe_processing_fields():
    module = _load_module()
    upgrade = _body(module, "upgrade")
    downgrade = _body(module, "downgrade")
    assert upgrade.count("op.create_table(") == 1
    assert '"processing_results"' in upgrade
    assert '"uq_processing_result_observation_consumer"' in upgrade
    assert '"ix_processing_result_tenant_case"' in upgrade
    assert '"ix_processing_result_status"' in upgrade
    for field in (
        "processing_run_id", "tenant_id", "investigation_id", "observation_id",
        "capture_id", "raw_ref", "consumer", "consumer_version", "processed_at",
        "status", "derived_ref", "record_count", "mention_count", "normalization",
        "interpretation",
    ):
        assert f'"{field}"' in upgrade, f"migration omits {field}"
    assert "status IN ('processed','skipped_replay','refused')" in upgrade
    assert "op.drop_table(\"processing_results\")" in downgrade


def test_processing_result_orm_declares_the_same_durable_columns():
    from db.schema import ProcessingResultRow

    migration = _load_module()
    upgrade = _body(migration, "upgrade")
    orm_columns = set(ProcessingResultRow.__table__.columns.keys())
    for column in (
        "processing_result_id", "processing_run_id", "tenant_id", "investigation_id",
        "observation_id", "capture_id", "raw_ref", "consumer", "consumer_version",
        "processed_at", "status", "derived_ref", "locator", "record_count",
        "mention_count", "truncated", "failure_code", "detail", "normalization",
        "interpretation", "created_at", "updated_at",
    ):
        assert column in orm_columns
        assert f'"{column}"' in upgrade
    assert any(
        constraint.name == "uq_processing_result_observation_consumer"
        for constraint in ProcessingResultRow.__table__.constraints
    )
