"""Unit tests: ladder top-rung gating (T134, US7, FR-013).

The top rung of the evidence ladder requires recorded artifacts for every one
of the four gates — calibration, null model, robustness, reproduction — while
rungs below top are independently rated as each gate is recorded.
"""

from __future__ import annotations

from claims.model import CredenceDistribution, EvidenceDirection, EvidenceLink, ScientificClaim
from review.ladder import LadderGates, ladder_position, top_rung


def _gates(**held: bool) -> LadderGates:
    return LadderGates(
        calibrated=held.get("calibrated", False),
        null_model=held.get("null_model", False),
        robustness=held.get("robustness", False),
        reproduction=held.get("reproduction", False),
    )


def _claim() -> ScientificClaim:
    return ScientificClaim(
        claim_id="CL-1",
        project_id="P1",
        statement="density shapes spreading",
        distribution=CredenceDistribution(states=["a", "b"], labels=["a", "b"], probs=[0.7, 0.3], method="binomial-kde@1.0"),
        model_id="binomial-kde@1.0",
        provenance=[
            EvidenceLink(
                link_id="L1",
                observation_id="O1",
                raw_sha256="sha256:1",
                direction=EvidenceDirection.DISCRIMINATES,
                weight=0.5,
            )
        ],
    )


class TestTopRungGating:
    def test_top_rung_requires_all_four(self) -> None:
        assert top_rung() == 4
        assert ladder_position(_claim(), _gates(calibrated=True, null_model=True, robustness=True, reproduction=True)) == 4

    def test_each_missing_gate_lowers_rung(self) -> None:
        claim = _claim()
        assert ladder_position(claim, _gates(reproduction=True)) == 1
        assert ladder_position(claim, _gates(calibrated=True, reproduction=True)) == 2
        assert ladder_position(claim, _gates(calibrated=True, null_model=True, reproduction=True)) == 3

    def test_only_recorded_gates_count(self) -> None:
        claim = _claim()
        assert ladder_position(claim, _gates()) == 0

    def test_unprovenanced_claim_is_unratable(self) -> None:
        claim = _claim()
        claim.provenance.clear()
        assert ladder_position(claim, _gates(calibrated=True, null_model=True, robustness=True, reproduction=True)) is None