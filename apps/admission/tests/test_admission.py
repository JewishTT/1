"""Unit tests for admission/resolution/evidence (T035-T037, T082-T084, T086-T087)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.admission import AdmissionEngine, AdmitDecision
from engine.assertions import AssertionExtractor, EvidenceLink, EvidenceRef
from engine.calibration import AdmissionInput, CalibrationProfile, MediaProfile
from engine.temporal import (
    AssertionState,
    IllegalAssertionTransition,
    TemporalConsistencyEngine,
    TemporalPolicy,
)
from evidence.independence import DerivationEdge, SourceIndependenceEngine
from resolution.blocking import BlockingEngine, CandidateRecord
from resolution.collective import CollectiveResolver
from resolution.resolver import PairwiseResolver


def _rec(cid: str, name: str, **extra) -> CandidateRecord:
    base = {
        "candidate_id": cid,
        "entity_type": "person",
        "canonical_value": name,
        "display_name": name,
        "doc_ids": [f"d-{cid}"],
    }
    base.update(extra)
    return CandidateRecord(**base)


class TestBlocking:
    def test_same_name_prefix_generates_pair(self):
        a = _rec("c1", "Ivan Petrov")
        b = _rec("c2", "Ivan Petroff")
        pairs = BlockingEngine().block([a, b])
        assert len(pairs) == 1
        assert pairs[0].strategies >= {"name_prefix", "phonetic"}

    def test_same_email_generates_pair(self):
        a = _rec("c1", "Ivan", email="ivan@mail.ru")
        b = _rec("c2", "Ivan2", email="ivan@mail.ru")
        pairs = BlockingEngine().block([a, b])
        assert any("email" in p.strategies for p in pairs)

    def test_same_doc_generates_pair(self):
        a = _rec("c1", "A", doc_ids=["doc-x"])
        b = _rec("c2", "B", doc_ids=["doc-x"])
        pairs = BlockingEngine().block([a, b])
        assert any("same_doc" in p.strategies for p in pairs)

    def test_no_o2_pairs_large_bucket_skipped(self):
        recs = [_rec(f"c{i}", f"Name{i % 50}", doc_ids=["d1"], handle="shared") for i in range(300)]
        engine = BlockingEngine(max_bucket=64)
        pairs = engine.block(recs)
        # Bounded by bucket capacity + strategy index; far below brute-force N²/2.
        assert len(pairs) < 300 * 299 // 2

    def test_soundex_folds(self):
        a = _rec("c1", "Smith")
        b = _rec("c2", "Smyth")
        pairs = BlockingEngine().block([a, b])
        assert any("phonetic" in p.strategies for p in pairs)


class TestPairwiseResolver:
    def test_equal_hard_signals(self):
        a = _rec("c1", "Ivan Petrov", email="i@x.ru", birth_date="1990-05-01")
        b = _rec("c2", "Ivan Petrov", email="i@x.ru", birth_date="1990-05-01")
        pair = PairwiseResolver().resolve(a, b)
        assert pair.raw_pair_score > 0.9
        assert "email" in pair.reasons and "name" in pair.reasons

    def test_reasons_only_when_strong(self):
        a = _rec("c1", "Alice")
        b = _rec("c2", "Bob")
        pair = PairwiseResolver().resolve(a, b)
        assert pair.raw_pair_score == 0.0 and pair.reasons == []


class TestCollectiveResolver:
    def test_transitive_boost(self):
        resolver = PairwiseResolver()
        a = _rec("c1", "Ivan", email="i@x.ru")
        b = _rec("c2", "Ivan Petrov")
        c = _rec("c3", "Ivan Petroff")
        pairs = [resolver.resolve(a, b, None), resolver.resolve(b, c, None)]
        result = CollectiveResolver().resolve(pairs)
        # Both edges gain confidence from mutual support (transitive propagation),
        # even though the (c1, c3) pair is NOT an input pair.
        for p in result.pairs:
            assert p.collective_score >= p.raw_pair_score
        # a↔b and b↔c are similar; their scores should be at least as high as alone.
        assert result.iterations >= 1

    def test_cluster_count(self):
        resolver = PairwiseResolver()
        a = _rec("c1", "Ivan", email="i@x.ru")
        b = _rec("c2", "Margarita")
        pairs = [resolver.resolve(a, b, None)]
        result = CollectiveResolver().resolve(pairs)
        # different names, no shared doc → weak edge → no cluster merge
        assert result.cluster_count == 0


class TestTemporal:
    def test_single_policy_supersedes_and_keeps_history(self):
        engine = TemporalConsistencyEngine()
        old = engine.post(relation="citizenship", subject_candidate_id="c1", object_value="USSR")
        new = engine.post(
            relation="citizenship",
            subject_candidate_id="c1",
            object_value="Russia",
            policy=TemporalPolicy.SINGLE,
        )
        engine.supersede(old.assertion_id, new.assertion_id)
        assert engine.get(old.assertion_id).state == AssertionState.SUPERSEDED
        assert engine.get(new.assertion_id).supersedes == old.assertion_id
        assert len(engine.history(old.assertion_id)) == 2  # FR-016: never deleted

    def test_append_only_cannot_supersede(self):
        engine = TemporalConsistencyEngine()
        rec = engine.post(relation="nick", subject_candidate_id="c1", object_value="x", policy=TemporalPolicy.APPEND_ONLY)
        other = engine.post(
            relation="nick",
            subject_candidate_id="c1",
            object_value="y",
            policy=TemporalPolicy.APPEND_ONLY,
        )
        try:
            engine.supersede(rec.assertion_id, other.assertion_id)
            assert False, "expected IllegalAssertionTransition"
        except IllegalAssertionTransition:
            pass

    def test_retract_never_deletes(self):
        engine = TemporalConsistencyEngine()
        rec = engine.post(relation="ph", subject_candidate_id="c1", object_value="123")
        engine.retract(rec.assertion_id, reason="withdrawn")
        assert engine.get(rec.assertion_id).state == AssertionState.RETRACTED
        assert len(engine.history(rec.assertion_id)) == 2


class TestAssertions:
    def test_publication_count_distinct_docs(self):
        ext = AssertionExtractor()
        refs = [
            EvidenceRef(observation_id="o1"),
            EvidenceRef(observation_id="o1"),
            EvidenceRef(observation_id="o2"),
        ]
        a = ext.extract(subject_candidate_id="c1", relation="hacked_by", object_value="x", refs=refs)
        assert a.publication_count() == 2

    def test_evidence_never_drops_original_refs(self):
        ext = AssertionExtractor()
        refs = [EvidenceRef(observation_id="o9", mention_id="m9")]
        a = ext.extract(subject_candidate_id="c1", relation="r", object_value="v", refs=refs)
        assert {r.observation_id for r in a.evidence.evidence_refs} == {"o9"}


class TestIndependence:
    def test_copy_chain_reduces_to_single_root(self):
        engine = SourceIndependenceEngine()
        engine.add_edge("o2", "o1", DerivationEdge.COPIES)
        engine.add_edge("o3", "o2", DerivationEdge.REWRITES)
        link = EvidenceLink(evidence_refs=[EvidenceRef(observation_id="o1"), EvidenceRef(observation_id="o3")])
        engine.fuse(link)
        assert len(link.independent_evidence_chains) == 1
        assert link.independent_support == 0.0

    def test_two_independent_roots_raise_support(self):
        engine = SourceIndependenceEngine()
        link = EvidenceLink(evidence_refs=[EvidenceRef(observation_id="o1"), EvidenceRef(observation_id="o2")])
        engine.fuse(link)
        assert link.independent_support > 0.4
        assert len(link.independent_evidence_chains) == 2

    def test_derived_plus_independent_chains(self):
        engine = SourceIndependenceEngine()
        engine.add_edge("o2", "o1", DerivationEdge.CITES)
        link = EvidenceLink(evidence_refs=[EvidenceRef(observation_id="o1"), EvidenceRef(observation_id="o2")])
        engine.fuse(link)
        assert engine.independence_score_for(link) == 0.0


class TestAdmission:
    def test_hard_reject_invalid_id(self):
        engine = AdmissionEngine()
        inp = AdmissionInput(candidate_id="c1", entity_type="person", has_valid_identifier=False)
        result = engine.decide(inp, EvidenceLink(evidence_refs=[]))
        assert result.decision == AdmitDecision.REJECT
        assert "hard_reject_invalid_id" in result.reason_codes

    def test_contradiction_quarantines(self):
        engine = AdmissionEngine()
        inp = AdmissionInput(candidate_id="c1", entity_type="person", strong_contradiction=True)
        result = engine.decide(inp, EvidenceLink(evidence_refs=[]))
        assert result.decision == AdmitDecision.QUARANTINE

    def test_strong_corroboration_accepts(self):
        engine = AdmissionEngine()
        inp = AdmissionInput(
            candidate_id="c1",
            entity_type="person",
            corroboration_score=0.9,
            structural_score=0.8,
        )
        result = engine.decide(inp, EvidenceLink(evidence_refs=[]))
        assert result.decision == AdmitDecision.ACCEPT_NEW

    def test_profile_threshold_defer(self):
        profiles = MediaProfile()
        profiles.register(CalibrationProfile(entity_type="person", threshold_accept=0.99))
        engine = AdmissionEngine(profiles)
        inp = AdmissionInput(candidate_id="c1", entity_type="person", corroboration_score=0.6)
        result = engine.decide(inp, EvidenceLink(evidence_refs=[]))
        assert result.decision == AdmitDecision.DEFER

    def test_replayed_decisions_kept(self):
        engine = AdmissionEngine()
        inp = AdmissionInput(candidate_id="c1", entity_type="person", corroboration_score=0.9)
        result = engine.decide(inp, EvidenceLink(evidence_refs=[]))
        assert engine.resident(result.admission_id) is not None
        assert result.replayable