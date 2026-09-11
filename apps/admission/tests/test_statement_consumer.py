"""Feature 005 US1: admission consumes the canonical shared.domain.Statement."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from domain.statement import Statement as CanonicalStatement

from engine.assertions import AssertionExtractor, EvidenceRef


class _MockProducer:
    def __init__(self) -> None:
        self.sent: list[tuple[str, object, str | None]] = []

    def produce(self, topic, envelope, key=None, **kwargs) -> None:
        self.sent.append((topic, envelope, key))


class TestCanonicalStatementConsumer:
    def test_statement_is_canonical_domain_type(self):
        ext = AssertionExtractor()
        a = ext.extract(
            subject_candidate_id="c1",
            relation="works_at",
            object_value="ACME",
            refs=[EvidenceRef(observation_id="o1")],
            dataset_id="ds-1",
        )
        assert isinstance(a.statement, CanonicalStatement)
        assert type(a.statement).__module__ == "domain.statement"

    def test_observation_to_statement_round_trip_preserves_boundary(self):
        from datetime import UTC, datetime

        ext = AssertionExtractor()
        snapshot = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
        a = ext.extract(
            subject_candidate_id="c1",
            relation="works_at",
            object_value="ACME",
            refs=[EvidenceRef(observation_id="o1"), EvidenceRef(observation_id="o2")],
            dataset_id="ds-1",
            extraction_version="extractor-v9",
            valid_from=snapshot,
            valid_to=snapshot,
        )
        assert a.statement is not None
        data = a.statement.to_dict()
        assert data["dataset_id"] == "ds-1"
        assert data["extraction_version"] == "extractor-v9"
        assert data["original_value"] == "ACME"
        assert data["valid_from"] == "2026-03-01T12:00:00+00:00"
        assert data["valid_until"] == "2026-03-01T12:00:00+00:00"
        assert data["entity_id"] == "c1"
        assert data["claimed"] is True

    def test_no_dataset_boundary_means_no_statement(self):
        ext = AssertionExtractor()
        a = ext.extract(
            subject_candidate_id="c1",
            relation="works_at",
            object_value="ACME",
            refs=[EvidenceRef(observation_id="o1")],
        )
        assert a.statement is None

    def test_emission_uses_canonical_envelope(self):
        producer = _MockProducer()
        ext = AssertionExtractor()
        a = ext.extract(
            subject_candidate_id="c1",
            relation="works_at",
            object_value="ACME",
            refs=[EvidenceRef(observation_id="o1")],
            dataset_id="ds-1",
            producer=producer,
        )
        assert len(producer.sent) == 1
        topic, envelope, key = producer.sent[0]
        assert topic == "statement"
        assert envelope.event_type == "statement.created"
        assert envelope.entity_id == "c1"
        assert key == a.statement.statement_id
        payload = envelope.payload.decode("utf-8")
        assert '"dataset_id": "ds-1"' in payload

    def test_domain_invariant_guards_empty_provenance(self):
        from domain import StatementProvenanceError

        with pytest.raises(StatementProvenanceError):
            CanonicalStatement(
                statement_id="ST-x",
                entity_id="c1",
                schema_name="",
                dataset_id="",
                original_value="ACME",
                extraction_version="e1",
            )