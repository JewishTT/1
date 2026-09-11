"""Contract tests for domain invariants (T017, I-1…I-12).

ConstraintViolation on observation immutable (I-1), Mention/Candidate/Entity
separation (I-2), assertion not truth (I-3), no blobs on Kafka (I-5), projections
rebuildable (I-12).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "apps" / "shared"))

import pytest

from domain import (
    AssertionNotTruthError,
    ConstraintViolation,
    MentionCandidateEntitySeparationError,
    NoBlobsOnKafkaError,
    ObservationImmutableError,
    ProjectionRebuildableError,
    TDAIsNotTruthError,
    enforce_no_blobs,
    enforce_observation_immutable,
    enforce_projection_provenance,
)


@pytest.mark.contract
class TestDomainInvariants:
    def test_i1_observation_immutable_rejects_update(self) -> None:
        existing = {"observation_id": "OBS-1", "status": "created", "uri": "http://x"}
        update = {"uri": "http://y"}  # immutable field
        with pytest.raises(ObservationImmutableError):
            enforce_observation_immutable(existing, update)

    def test_i1_observation_immutable_allows_status_change(self) -> None:
        existing = {"observation_id": "OBS-1", "status": "created"}
        update = {"status": "unchanged"}  # mutable operational field
        enforce_observation_immutable(existing, update)  # should not raise

    def test_i1_observation_immutable_allows_provenance_append(self) -> None:
        existing = {"observation_id": "OBS-1"}
        update = {"provenance": {"version": 2}}
        enforce_observation_immutable(existing, update)

    def test_i5_no_blobs_on_kafka(self) -> None:
        large_payload = b"x" * 1024 * 100
        with pytest.raises(NoBlobsOnKafkaError):
            enforce_no_blobs(large_payload, max_inline=1024)

    def test_i5_no_blobs_allows_small_refs(self) -> None:
        small_ref = b'{"s3_ref": "s3://knowledge/raw/..."}'
        enforce_no_blobs(small_ref, max_inline=1024)

    def test_i12_projection_requires_provenance(self) -> None:
        with pytest.raises(ProjectionRebuildableError):
            enforce_projection_provenance(None)

    def test_i12_projection_requires_event_id(self) -> None:
        with pytest.raises(ProjectionRebuildableError):
            enforce_projection_provenance({"observation_id": "obs-1"})

    def test_i12_projection_valid_provenance(self) -> None:
        enforce_projection_provenance({"event_id": "evt-1", "observation_id": "obs-1"})

    def test_constraint_violation_base_exception(self) -> None:
        err = ConstraintViolation("TEST", "test message")
        assert err.code == "TEST"
        assert "test message" in str(err)

    def test_assertion_not_truth(self) -> None:
        err = AssertionNotTruthError("ASSERT-1")
        assert "ASSERT-1" in str(err)
        assert err.code == "I-3"

    def test_tda_not_truth(self) -> None:
        err = TDAIsNotTruthError()
        assert err.code == "I-6"

    def test_mention_candidate_entity_separation(self) -> None:
        err = MentionCandidateEntitySeparationError()
        assert err.code == "I-2"