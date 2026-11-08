from __future__ import annotations

from pathlib import Path

from db.schema import TypeSignalRow


def test_type_signal_row_is_an_observation_shape_not_a_type_assertion():
    columns = set(TypeSignalRow.__table__.columns.keys())
    assert {
        "signal_id", "tenant_id", "mention_ref", "source_vocab", "surface",
        "structural_path", "observation_refs", "evidence_refs", "producer_ref",
        "mapping_candidates", "created_at",
    } <= columns
    assert not {"entity_ref", "type_ref", "scope", "status"} & columns


def test_type_signal_migration_matches_the_orm_table():
    root = Path(__file__).resolve().parents[2]
    migration = (root / "db" / "migrations" / "versions" / "032_type_signals.py").read_text(
        encoding="utf-8"
    )
    assert 'revision = "032_type_signals"' in migration
    assert 'down_revision = "031_relation_claim_projection_outbox"' in migration
    for column in (
        "signal_id", "tenant_id", "mention_ref", "source_vocab", "surface",
        "structural_path", "observation_refs", "evidence_refs", "producer_ref",
        "mapping_candidates",
    ):
        assert f'"{column}"' in migration
