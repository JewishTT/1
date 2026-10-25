"""Feature 034 durable case records — revision 027 migration contracts.

These checks protect the released migration graph and compare the DDL-only compatibility
bootstrap with the forward-only Alembic revision. Runtime schema setup must not silently
become a second, weaker schema definition.
"""
from __future__ import annotations

import inspect
import re
import sys
from pathlib import Path

_APPS = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_APPS / "shared"))
sys.path.insert(0, str(_APPS / "control-plane"))

VERSIONS_DIR = _APPS / "control-plane" / "db" / "migrations" / "versions"
MIGRATION = VERSIONS_DIR / "027_person_research_case_records.py"
PARENT = "026_person_research_case_runtime"

_REVISION = re.compile(r'^revision\s*=\s*["\']([^"\']+)["\']', re.MULTILINE)
_DOWN_REVISION = re.compile(r'^down_revision\s*=\s*["\']([^"\']+)["\']', re.MULTILINE)


def _load_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("revision_027_person_case_records_under_test", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _body(module, name: str) -> str:
    return re.sub(r'""".*?"""', "", inspect.getsource(getattr(module, name)), flags=re.DOTALL)


def test_027_is_forward_only_and_single_head() -> None:
    assert MIGRATION.is_file(), "027 durable case records migration is missing"
    source = MIGRATION.read_text(encoding="utf-8")
    assert _REVISION.search(source).group(1) == "027_person_research_case_records"
    assert _DOWN_REVISION.search(source).group(1) == PARENT

    graph: dict[str, str | None] = {}
    for path in sorted(VERSIONS_DIR.glob("*.py")):
        if path.name == "__init__.py":
            continue
        text = path.read_text(encoding="utf-8")
        revision = _REVISION.search(text)
        assert revision, f"{path.name} has no revision id"
        parent = re.search(r'^down_revision\s*=\s*(.+)$', text, re.MULTILINE)
        assert parent, f"{path.name} has no parent id"
        raw = parent.group(1).strip()
        if raw == "None":
            graph[revision.group(1)] = None
        else:
            parsed = re.match(r'^["\']([^"\']+)["\']$', raw)
            assert parsed, f"{path.name} has unsupported parent syntax: {raw}"
            graph[revision.group(1)] = parsed.group(1)

    assert graph["027_person_research_case_records"] == PARENT
    children: dict[str, list[str]] = {}
    for revision, parent in graph.items():
        if parent is not None:
            assert parent in graph, f"{revision} has missing parent {parent}"
            children.setdefault(parent, []).append(revision)
    assert all(len(kids) == 1 for kids in children.values()), children
    assert len([revision for revision in graph if revision not in children]) == 1


def test_027_adds_exactly_the_two_owned_case_record_tables() -> None:
    module = _load_module()
    upgrade = _body(module, "upgrade")
    downgrade = _body(module, "downgrade")

    for forbidden in ("op.drop_table", "op.drop_column", "op.alter_column", "op.execute"):
        assert forbidden not in upgrade, f"upgrade must be additive; found {forbidden}"
    assert upgrade.count("op.create_table(") == 2
    assert '"person_case_metadata"' in upgrade
    assert '"person_case_dispatch_intents"' in upgrade
    assert '"uq_person_case_dispatch_run"' in upgrade
    assert '"ix_person_case_metadata_tenant"' in upgrade
    assert '"ix_person_case_dispatch_intents_case"' in upgrade
    assert "length(scope_digest) = 71" in upgrade
    assert "length(policy_digest) = 71" in upgrade
    assert "op.drop_table(\"person_case_dispatch_intents\")" in downgrade
    assert "op.drop_table(\"person_case_metadata\")" in downgrade
    assert downgrade.index("op.drop_table(\"person_case_dispatch_intents\")") < downgrade.index(
        "op.drop_table(\"person_case_metadata\")"
    ), "downgrade drops dependent dispatch records before the case sidecar"


def test_runtime_bootstrap_matches_the_migration_contract() -> None:
    from context_engine.postgres_store import _DDL

    sql = "\n".join(_DDL).lower()
    for table in ("person_case_metadata", "person_case_dispatch_intents"):
        assert f"create table if not exists {table}" in sql, f"runtime bootstrap misses {table}"
    for constraint in (
        "check (case_id <> '')",
        "check (tenant_id <> '')",
        "check (idempotency_key <> '')",
        "length(scope_digest) = 71",
        "length(policy_digest) = 71",
        "updated_at",
    ):
        assert constraint in sql, f"runtime schema bootstrap and migration contract drifted: {constraint}"
    assert "primary key (tenant_id, case_id, idempotency_key)" in sql
    assert "run_id text not null unique" in sql
