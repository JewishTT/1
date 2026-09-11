"""Unit tests: reprint collapse + claim verdicts + storylines + event emission (T012/T029/T031/T033)."""

import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from scoring.claim import ClaimVerdict, assess_claim, corroboration_score

from engine.assertions import AssertionExtractor, EvidenceLink, EvidenceRef
from engine.storyline import StorylineBuilder
from evidence.independence import DerivationEdge, SourceIndependenceEngine
from resolution.collective import CorrelationService, ResolvedPair


class _MockProducer:
    def __init__(self) -> None:
        self.sent: list[tuple[str, object, str | None]] = []

    def produce(self, topic, envelope, key=None, **kwargs) -> None:
        self.sent.append((topic, envelope, key))


class TestReprintCollapse:
    def test_reprints_collapse_to_one_chain(self):
        engine = SourceIndependenceEngine()
        # o2..o21 are reprints/copies of the original o1 (FR-002 dataset boundary).
        for i in range(2, 22):
            engine.add_edge(f"o{i}", "o1", DerivationEdge.COPIES)
        link = EvidenceLink(
            evidence_refs=[EvidenceRef(observation_id=f"o{i}") for i in range(1, 22)]
        )
        engine.fuse(link)
        boundary = engine.dataset_boundary(link)
        assert boundary["publication_count"] == 21
        assert boundary["independent_source_count"] == 1
        assert link.independent_source_count == 1

    def test_reprints_plus_independent_chain(self):
        engine = SourceIndependenceEngine()
        engine.add_edge("o2", "o1", DerivationEdge.COPIES)
        link = EvidenceLink(
            evidence_refs=[
                EvidenceRef(observation_id="o1"),
                EvidenceRef(observation_id="o2"),
                EvidenceRef(observation_id="o9"),
            ]
        )
        engine.fuse(link)
        boundary = engine.dataset_boundary(link)
        assert boundary["publication_count"] == 3
        assert boundary["independent_source_count"] == 2


class TestClaimVerdict:
    def test_corroboration_zero_without_chains(self):
        assert corroboration_score(0, 5) == 0.0

    def test_reprints_do_not_corroborate(self):
        result = assess_claim(
            assertion_refs=["A-1"], independent_chain_count=1, publication_count=20
        )
        assert result.verdict == ClaimVerdict.UNCERTAIN
        assert "reprints_collapsed" in result.reasons
        assert result.corroboration == pytest.approx(0.1)

    def test_two_independent_chains_support(self):
        result = assess_claim(
            assertion_refs=["A-1"], independent_chain_count=2, publication_count=2
        )
        assert result.verdict == ClaimVerdict.SUPPORTED
        assert result.corroboration >= 0.6

    def test_contradiction_verdict(self):
        result = assess_claim(
            assertion_refs=["A-1"],
            independent_chain_count=3,
            publication_count=3,
            contradicted=True,
        )
        assert result.verdict == ClaimVerdict.CONTRADICTED
        assert result.triangulation.get("conflict") is True

    def test_no_chains_uncertain(self):
        result = assess_claim(
            assertion_refs=["A-1"], independent_chain_count=0, publication_count=1
        )
        assert result.verdict == ClaimVerdict.UNCERTAIN

    def test_engine_assess_claim_uses_chains(self):
        engine = SourceIndependenceEngine()
        link = EvidenceLink(
            evidence_refs=[EvidenceRef(observation_id="o1"), EvidenceRef(observation_id="o2")]
        )
        link.publication_count = 2  # extractor sets this from distinct docs
        result = engine.assess_claim(link, assertion_refs=["A-1"])
        assert result.verdict == ClaimVerdict.SUPPORTED
        assert result.independent_chain_count == 2
        assert result.publication_count == 2


class TestStatementProvenance:
    def test_extractor_attaches_statement(self):
        ext = AssertionExtractor()
        refs = [EvidenceRef(observation_id="o1")]
        a = ext.extract(
            subject_candidate_id="c1",
            relation="works_at",
            object_value="ACME",
            refs=refs,
            dataset_id="ds-1",
        )
        assert a.statement is not None
        assert a.statement.dataset_id == "ds-1"
        assert a.statement.original_value == "ACME"
        assert a.statement.entity_id == "c1"
        assert a.statement.schema_name == ""  # schema attributed at resolution
        d = a.statement.to_dict()
        assert d["extraction_version"]
        assert d["first_seen"] and d["last_seen"]
        assert d["entity_id"] == "c1"


class TestCorrelationService:
    def test_edges_created_and_events_emitted(self):
        producer = _MockProducer()
        svc = CorrelationService(producer=producer)
        pairs = [
            ResolvedPair(candidate_a="c1", candidate_b="c2", raw_pair_score=0.8, reasons=["email"]),
            ResolvedPair(candidate_a="c3", candidate_b="c4", raw_pair_score=0.0),  # filtered out
        ]
        edges = svc.create_edges(pairs)
        assert len(edges) == 1
        assert edges[0].kind == "possible_match"
        assert edges[0].state == "OPEN"
        assert len(producer.sent) == 1
        topic, envelope, key = producer.sent[0]
        assert topic == "correlation"
        assert envelope.event_type == "correlation.edge_created"
        assert envelope.event_id == f"evt-{edges[0].edge_id}"
        assert key == edges[0].edge_id

    def test_edges_never_merge_and_stay_queryable(self):
        svc = CorrelationService()
        svc.create_edges([ResolvedPair(candidate_a="c1", candidate_b="c2", raw_pair_score=0.99)])
        assert len(svc.edges_for("c1")) == 1
        assert len(svc.edges_for("c2")) == 1
        assert svc.edges_for("c3") == []


class TestStatementEventEmission:
    def test_statement_created_envelope_emitted(self):
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
        assert envelope.event_id == f"evt-{a.statement.statement_id}"
        assert key == a.statement.statement_id

    def test_no_producer_is_silent(self):
        ext = AssertionExtractor()
        a = ext.extract(
            subject_candidate_id="c1",
            relation="works_at",
            object_value="ACME",
            refs=[EvidenceRef(observation_id="o1")],
            dataset_id="ds-1",
        )
        assert a.statement is not None


class TestStoryline:
    def test_grouped_by_subject_time_ordered(self):
        builder = StorylineBuilder()
        a1 = {"assertion_id": "A-1", "subject_candidate_id": "c1", "relation": "works_at", "observed_at": datetime(2026, 1, 3, tzinfo=UTC)}
        a2 = {"assertion_id": "A-2", "subject_candidate_id": "c1", "relation": "owns", "observed_at": datetime(2026, 1, 1, tzinfo=UTC)}
        a3 = {"assertion_id": "A-3", "subject_candidate_id": "c2", "relation": "linked_to", "observed_at": datetime(2026, 1, 2, tzinfo=UTC)}
        storylines = builder.build([a1, a2, a3])
        assert len(storylines) == 2
        c1 = next(s for s in storylines if s.subject_id == "c1")
        assert c1.assertion_ids == ["A-2", "A-1"]  # time-ordered
        assert c1.relations == ["owns", "works_at"]
        assert c1.start == datetime(2026, 1, 1, tzinfo=UTC)
        assert c1.end == datetime(2026, 1, 3, tzinfo=UTC)
        c2 = next(s for s in storylines if s.subject_id == "c2")
        assert c2.assertion_ids == ["A-3"]

    def test_works_with_extracted_assertions(self):
        ext = AssertionExtractor()
        a1 = ext.extract(subject_candidate_id="c1", relation="works_at", object_value="ACME", refs=[EvidenceRef(observation_id="o1")], dataset_id="ds-1")
        a2 = ext.extract(subject_candidate_id="c1", relation="owns", object_value="ACME", refs=[EvidenceRef(observation_id="o2")], dataset_id="ds-1")
        storylines = StorylineBuilder().build([a1, a2])
        assert len(storylines) == 1
        assert storylines[0].subject_id == "c1"
        assert set(storylines[0].assertion_ids) == {a1.assertion_id, a2.assertion_id}
        assert storylines[0].storyline_id.startswith("SL-")