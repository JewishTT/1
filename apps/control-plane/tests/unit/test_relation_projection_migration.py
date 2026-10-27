"""Pin the durable projection migration chain."""
from pathlib import Path


def test_claim_projection_migration_adds_verdict_and_outbox() -> None:
    path = (
        Path(__file__).resolve().parents[2]
        / "db"
        / "migrations"
        / "versions"
        / "031_relation_claim_projection_outbox.py"
    )
    source = path.read_text(encoding="utf-8")
    assert 'down_revision = "030_observation_candidate_hardening"' in source
    assert '"validation_record"' in source
    assert '"relation_claim_projection_outbox"' in source
    assert "uq_relation_claim_projection_outbox_claim" in source
    assert "lease_expires_at" in source
