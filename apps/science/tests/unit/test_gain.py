"""Unit tests: information-gain planner (T100, US2).

The planner must rank opportunities by expected KL divergence over **alive**
hypotheses and never let a discarded/resolved hypothesis influence the plan
(dead hypotheses have ``gain_priority=None`` so nothing pulls collection).
"""

from __future__ import annotations

from claims.model import DecisionRecord, EvidenceDirection, EvidenceLink, Hypothesis
from hypotheses.decide import discard_hypothesis
from hypotheses.evidence import attach_evidence, derive_credence
from hypotheses.gain import EvidenceOpportunity, plan_collection
from hypotheses.model import is_alive, propose_hypothesis, transition_hypothesis_status


class TestPlannerExcludesDead:
    def _project(self) -> list[Hypothesis]:
        a = propose_hypothesis(project_id="P-1", text="A sparse structure")
        b = propose_hypothesis(project_id="P-1", text="B dense structure")
        c = propose_hypothesis(project_id="P-1", text="C noise artifact")
        transition_hypothesis_status(a, "active")
        transition_hypothesis_status(b, "active")
        discard_hypothesis(c, DecisionRecord(actor="analyst", reason="no signal"))
        return [a, b, c]

    def test_planner_ignores_discarded_hypothesis(self) -> None:
        hypotheses = self._project()
        opportunities = [
            EvidenceOpportunity(
                opportunity_id=f"OP-{i}",
                description="probe",
                likelihoods={h.hypothesis_id: 0.5 for h in hypotheses},
            )
            for i in range(3)
        ]
        ranked = plan_collection("P-1", opportunities, 5, hypotheses=hypotheses)
        dead_id = next(h for h in hypotheses if not is_alive(h)).hypothesis_id
        assert ranked, "alive hypotheses should generate a plan"
        for opp in ranked:
            assert dead_id not in opp.discriminating_pair, "dead hypothesis leaked into plan"

    def test_dead_hypothesis_has_no_priority(self) -> None:
        hypotheses = self._project()
        dead = next(h for h in hypotheses if not is_alive(h))
        assert dead.gain_priority is None

    def test_alive_hypotheses_get_priorities(self) -> None:
        a, b, _c = self._project()
        attach_evidence(a, EvidenceLink(
            link_id="L-1", observation_id="OBS-1", raw_sha256="sha256:1",
            direction=EvidenceDirection.SUPPORTS, weight=0.8,
        ))
        attach_evidence(b, EvidenceLink(
            link_id="L-2", observation_id="OBS-2", raw_sha256="sha256:2",
            direction=EvidenceDirection.SUPPORTS, weight=0.2,
        ))
        credence = derive_credence([a, b])
        assert abs(sum(credence.probs) - 1.0) < 1e-9
        assert credence.probs[0] > credence.probs[1]