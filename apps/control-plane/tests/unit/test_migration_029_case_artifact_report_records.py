"""Migration contract for immutable static case artifacts and completion reports."""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

APPS = Path(__file__).resolve().parents[3]
VERSIONS = APPS / "control-plane" / "db" / "migrations" / "versions"
MIGRATION = VERSIONS / "029_person_case_artifacts_reports.py"


def _source() -> str:
    assert MIGRATION.is_file()
    return MIGRATION.read_text(encoding="utf-8")


def _load():
    spec = importlib.util.spec_from_file_location("feature_034_revision_029", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_029_is_the_forward_revision_after_processing_results() -> None:
    source = _source()
    assert re.search(r'^revision\s*=\s*"029_person_case_artifacts_reports"$', source, re.MULTILINE)
    assert re.search(r'^down_revision\s*=\s*"028_observation_processing_results"$', source, re.MULTILINE)


def test_029_creates_tenant_scoped_artifact_and_report_ledgers() -> None:
    module = _load()
    upgrade_source = re.sub(
        r'""".*?"""', "", module.upgrade.__code__.co_consts[0] if False else _source(),
        flags=re.DOTALL,
    )
    assert upgrade_source.count("op.create_table(") == 2
    assert '"person_case_artifacts"' in upgrade_source
    assert '"person_case_reports"' in upgrade_source
    assert '"uq_person_case_artifact_observation"' in upgrade_source
    assert '"uq_person_case_report_digest"' in upgrade_source
    assert '"ix_person_case_artifacts_case"' in upgrade_source
    assert '"ix_person_case_artifacts_capture"' in upgrade_source
    assert '"ix_person_case_reports_case"' in upgrade_source
    assert '"content_digest ~' in upgrade_source
    assert '"byte_length > 0"' in upgrade_source
    assert "length(scope_digest) = 71" in upgrade_source
    assert "length(report_digest) = 71" in upgrade_source
    assert "status IN ('COMPLETE','PARTIAL','BLOCKED')" in upgrade_source


def test_029_downgrade_removes_only_its_owned_objects_in_dependency_order() -> None:
    source = _source()
    downgrade = source[source.index("def downgrade"):]
    assert "op.drop_table" in downgrade
    assert downgrade.index('op.drop_table("person_case_reports")') < downgrade.index(
        'op.drop_table("person_case_artifacts")'
    )
    assert "op.drop_column" not in downgrade
    assert "op.alter_column" not in downgrade
