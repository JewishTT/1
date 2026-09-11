"""Contract tests: hypothesis lifecycle + information-gain planner (T099, US2).

Tests-first for ``apps/science/hypotheses/*`` per interface-contracts §3–4:
proposal emits an event, direction-tagged evidence attaches and stays
append-only, discards require a DecisionRecord (SC-003) and keep links, and the
planner ranks by expected KL gain across **alive** hypotheses only.
"""

from __future__ import annotations

import pytest

from claims.model import DecisionRecord, EvidenceDirection, EvidenceLink
from errors import DecisionRequiredError
from hypotheses.coverage import project_coverage
from hypotheses.decide import discard_hypothesis
from hypotheses.evidence import attach_evidence
from hypotheses.gain import EvidenceOpportunity, plan_collection
from hypotheses.model import propose_hypothesis, transition_hypothesis_status


class CaptureProducer:
    def __init__(self) -> None:
        self.sent: list[tuple[str, object, str | None]] = []

    def produce(self, topic, envelope, key=None, **kwargs) -> None:
        self.sent.append((topic, envelope, key))


def _link(hypothesis_id: str, observation_id: str, direction: str = "supports") -> EvidenceLink:
    return EvidenceLink(
        link_id=f"L-{hypothesis_id}-{observation_id}",
        observation_id=observation_id,
        raw_sha256=f"sha256:{observation_id}",
        direction=EvidenceDirection(direction),
        weight=0.6,
    )


class TestHypothesisLifecycle:
    def test_propose_emits_event_and_starts_proposed(self) -> None:
        producer = CaptureProducer()
        h = propose_hypothesis(
            project_id="P-1",
            text="transmission accelerates under dense network coupling",
            tenant_id="t-1",
            producer=producer,
        )
        assert h.hypothesis_id.startswith("HY-")
        assert h.status.value == "proposed"
        assert [env.event_type for _t, env, _k in producer.sent] == [
            "science.hypothesis.proposed"
        ]

    def test_attach_evidence_appends_with_direction(self) -> None:
        store = None
        h = propose_hypothesis(project_id="P-1", text="the cheap hypothesis", producer=None, store=store)
        attach_evidence(h, _link(h.hypothesis_id, "OBS-A", "supports"), producer=None, store=store)
        attach_evidence(h, _link(h.hypothesis_id, "OBS-B", "refutes"), producer=None, store=store)
        assert len(h.evidence_links) == 2
        assert h.evidence_links[1].direction.value == "refutes"

    def test_discard_without_decision_rejected(self) -> None:
        h = propose_hypothesis(project_id="P-1", text="some hypothesis")
        attach_evidence(h, _link(h.hypothesis_id, "OBS-A"))
        with pytest.raises(DecisionRequiredError):
            discard_hypothesis(h, None, producer=None, store=None)
        # links survive the failed attempt
        assert len(h.evidence_links) == 1

    def test_discard_with_decision_preserves_links(self) -> None:
        h = propose_hypothesis(project_id="P-1", text="some hypothesis")
        attach_evidence(h, _link(h.hypothesis_id, "OBS-A"))
        discard_hypothesis(
            h,
            DecisionRecord(actor="analyst@org", reason="contradicted by OBS-B"),
            producer=None,
            store=None,
        )
        assert h.status.value == "discarded"
        assert len(h.evidence_links) == 1
        assert h.decisions[0].reason == "contradicted by OBS-B"

    def test_dead_hypothesis_excluded_from_planner_and_priority_none(self) -> None:
        producer = CaptureProducer()
        alive_a = propose_hypothesis(project_id="P-1", text="hypothesis A", producer=producer)
        alive_b = propose_hypothesis(project_id="P-1", text="hypothesis B", producer=producer)
        dead = propose_hypothesis(project_id="P-1", text="hypothesis C", producer=producer)
        transition_hypothesis_status(alive_a, "active", actor="system", producer=producer)
        transition_hypothesis_status(alive_b, "active", actor="system", producer=producer)
        discard_hypothesis(
            dead,
            DecisionRecord(actor="analyst@org", reason="ruled out"),
            producer=producer,
            store=None,
        )
        assert dead.gain_priority is None
        # a plan over the dead hypothesis alone has nothing to collect
        assert not plan_collection(
            "P-1",
            [EvidenceOpportunity(opportunity_id="OP-1", description="probe", likelihoods={})],
            5,
            hypotheses=[dead],
        )
        # with alive hypotheses present the dead id is never discriminated
        ranked = plan_collection(
            "P-1",
            [EvidenceOpportunity(opportunity_id="OP-2", description="probe", likelihoods={})],
            5,
            hypotheses=[alive_a, alive_b, dead],
        )
        for opp in ranked:
            assert dead.hypothesis_id not in opp.discriminating_pair


class TestPlanner:
    def test_ranks_discriminating_opportunity_first(self) -> None:
        from claims.model import Hypothesis

        h_a = Hypothesis(hypothesis_id="HY-A", project_id="P-1", text="A accelerates")
        h_b = Hypothesis(hypothesis_id="HY-B", project_id="P-1", text="A decelerates")
        opportunities = [
            EvidenceOpportunity(
                opportunity_id="OP-HIGH",
                description="density probe",
                likelihoods={"HY-A": 0.9, "HY-B": 0.1},
            ),
            EvidenceOpportunity(
                opportunity_id="OP-NULL",
                description="non-discriminating probe",
                likelihoods={"HY-A": 0.5, "HY-B": 0.5},
            ),
        ]
        ranked = plan_collection(
            "P-1",
            opportunities,
            5,
            hypotheses=[h_a, h_b],
        )
        assert ranked[0].opportunity_id == "OP-HIGH"
        assert ranked[0].expected_gain > ranked[1].expected_gain

    def test_budget_limits_plan(self) -> None:
        from claims.model import Hypothesis

        h_a = Hypothesis(hypothesis_id="HY-A", project_id="P-1", text="A")
        h_b = Hypothesis(hypothesis_id="HY-B", project_id="P-1", text="B")
        opportunities = [
            EvidenceOpportunity(
                opportunity_id=f"OP-{i}",
                description="probe",
                likelihoods={"HY-A": 0.9, "HY-B": 0.1},
            )
            for i in range(4)
        ]
        ranked = plan_collection("P-1", opportunities, 2, hypotheses=[h_a, h_b])
        assert len(ranked) == 2


class TestCoverage:
    def test_per_project_coverage_counts(self) -> None:
        a = propose_hypothesis(project_id="P-1", text="A")
        b = propose_hypothesis(project_id="P-1", text="B")
        attach_evidence(a, _link(a.hypothesis_id, "OBS-1"))
        attach_evidence(a, _link(a.hypothesis_id, "OBS-2", "refutes"))
        attach_evidence(b, _link(b.hypothesis_id, "OBS-3"))
        coverage = project_coverage([a, b], project_id="P-1")
        assert coverage["hypotheses"] == 2
        assert coverage["with_evidence"] == 2
        assert coverage["evidence_links"] == 3
        assert coverage["direction_counts"]["supports"] == 2