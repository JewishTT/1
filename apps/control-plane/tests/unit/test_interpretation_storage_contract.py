from __future__ import annotations

from pathlib import Path

from db.schema import EntityVersion, Mention


def test_mention_table_matches_the_interpretation_bridge_contract() -> None:
    columns = Mention.__table__.columns
    assert set(columns.keys()) == {
        "mention_id",
        "observation_id",
        "tenant_id",
        "surface_form",
        "normalized_form",
        "transliteration_variants",
        "script",
        "language",
        "normalization_version",
        "type_hypothesis",
        "extractor_version",
        "offsets",
        "created_at",
    }
    assert columns["mention_id"].primary_key
    assert not columns["observation_id"].nullable
    assert not columns["tenant_id"].nullable
    assert not columns["surface_form"].nullable
    assert {index.name for index in Mention.__table__.indexes} >= {
        "ix_mentions_obs",
        "ix_mentions_tenant",
    }


def test_entity_version_table_matches_the_interpretation_bridge_contract() -> None:
    columns = EntityVersion.__table__.columns
    assert set(columns.keys()) == {
        "version_id",
        "entity_id",
        "tenant_id",
        "version_number",
        "canonical_name",
        "attributes",
        "created_at",
    }
    assert columns["version_id"].primary_key
    assert not columns["entity_id"].nullable
    assert not columns["tenant_id"].nullable
    assert not columns["version_number"].nullable
    assert {index.name for index in EntityVersion.__table__.indexes} >= {
        "ix_entity_versions_entity",
        "ix_entity_versions_tenant",
    }


def test_interpretation_storage_migration_follows_context_store_and_preserves_history() -> None:
    root = Path(__file__).resolve().parents[2]
    migration = (
        root
        / "db"
        / "migrations"
        / "versions"
        / "035_interpretation_mentions_and_entity_versions.py"
    ).read_text(encoding="utf-8")

    assert 'revision = "035_interpretation_mentions_and_entity_versions"' in migration
    assert 'down_revision = "034_durable_investigation_contexts"' in migration
    assert 'inspector.has_table("mentions")' in migration
    assert 'inspector.has_table("entity_versions")' in migration
    assert "forward-only" in migration
    for table in ("mentions", "entity_versions"):
        assert f' table="{table}"' in migration
