"""Canonical SQL graph rebuild wiring contract."""
from pathlib import Path


def test_projection_rebuild_is_registered_and_reads_latest_claim_revisions() -> None:
    root = Path(__file__).resolve().parents[2]
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    source = (root / "services" / "relation_projection_rebuild.py").read_text(encoding="utf-8")
    assert (
        'cognitive-relation-projection-rebuild = "services.relation_projection_rebuild:main"'
        in pyproject
    )
    assert "validation_record" in source
    assert "RelationClaimRow.revision_number.desc()" in source
    assert "graph.clear_tenant_projection(tenant_id)" in source
