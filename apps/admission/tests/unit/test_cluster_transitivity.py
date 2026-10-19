"""A↔B and B↔C do not imply A = C (spec 030 T078, FR-084).

ADR-030-03 D5: *pairwise agreement is not cluster membership*. The contaminated case is
structural rather than statistical — ``zero.resolution.graph.connected_components`` is a
union-find, and union-find is transitive by construction, so any matcher that emits "A matches B"
and "B matches C" has already produced the cluster {A, B, C} whether or not anyone looked.

These tests pin the refusal. Each builds the triangle, shows that plain transitivity fuses all
three, and shows that ``cluster_from_decisions`` does not.
"""

from __future__ import annotations

import pytest

from resolution.cluster import (
    PairAssessment,
    PairVerdict,
    cluster_from_decisions,
    contradiction_reasons,
    naive_transitive_closure,
)
from resolution.decision_store import DecisionKind, DecisionStore, MatcherProfile
from resolution.gate import (
    EvidenceItem,
    EvidenceKind,
    IdentityResolutionGate,
    MergeAuthority,
)
from resolution.span import CharSpanSelector, EvidenceSpanRef, SourceLocator

pytestmark = pytest.mark.unit

A, B, C = "ENT-A", "ENT-B", "ENT-C"
AB, BC, AC = f"{A}&&{B}", f"{B}&&{C}", f"{A}&&{C}"

REVIEWER = "analyst-1"
MATCHER = MatcherProfile(
    name="fellegi_sunter", version="calibrated-labelled-v1", calibrated=True,
    calibration_evidence="benchmarks/er-baseline.md",
)


def _span(ref: str) -> EvidenceSpanRef:
    return EvidenceSpanRef(
        observation_ref=ref,
        blob_digest="sha256:" + "0" * 64,
        selector=CharSpanSelector(0, 1),
        source_locator=SourceLocator(uri=f"https://corpus.example/{ref}"),
    )


def _commit(gate: IdentityResolutionGate, pair_key: str) -> None:
    outcome = gate.commit_merge(
        pair_key,
        authority=MergeAuthority.HUMAN_REVIEW,
        decided_by=REVIEWER,
        reviewer_id=REVIEWER,
        matcher=MATCHER,
        evidence=[EvidenceItem(EvidenceKind.OBSERVATION, pair_key)],
        span_refs=[_span(pair_key.replace("&&", "-"))],
        lineage_roots=2,
        rationale="reviewed and signed off",
    )
    assert outcome.committed is True, outcome.codes


def _triangle() -> IdentityResolutionGate:
    gate = IdentityResolutionGate()
    _commit(gate, AB)
    _commit(gate, BC)
    return gate


class TestTransitivityIsNotFree:
    def test_plain_transitivity_would_fuse_all_three(self):
        """The contaminated result, stated first so the refusal below has a referent."""
        roots = naive_transitive_closure([A, B, C], [(A, B), (B, C)])
        assert roots == {A}

    def test_a_and_c_are_not_a_cluster_when_their_evidence_disagrees(self):
        gate = _triangle()
        gate.propose(AC, "same person", raised_by="fellegi_sunter", score=0.11)

        proposals = cluster_from_decisions(
            gate.store,
            assessments={
                AC: PairAssessment(
                    A, C, PairVerdict.CONTRADICTED, contradiction_reasons(conflicting_birth_date=True)
                )
            },
        )
        assert len(proposals) == 1
        proposal = proposals[0]
        assert proposal.admitted is False
        assert proposal.members == (A, B, C)
        assert [p.pair_key for p in proposal.blocked_pairs] == [AC]
        assert "fr084_pairwise_agreement_is_not_cluster_membership" in proposal.reasons
        # ...and no merge exists for A and C, at any score.
        assert gate.store.current(AC) is None
        assert AC not in {d.pair_key for d in gate.store.merges_in_force()}

    def test_never_compared_is_not_the_same_as_consistent(self):
        """The default has to be the conservative one or 'we did not look' means 'fine'."""
        gate = _triangle()
        proposals = cluster_from_decisions(gate.store)
        assert proposals[0].admitted is False
        assert proposals[0].blocked_pairs[0].verdict is PairVerdict.UNASSESSED
        assert proposals[0].blocked_pairs[0].reasons == ("never_compared",)

    def test_a_consistent_closing_edge_admits_the_cluster(self):
        gate = _triangle()
        proposals = cluster_from_decisions(
            gate.store,
            assessments={AC: PairAssessment(A, C, PairVerdict.CONSISTENT, ("shared_national_id",))},
        )
        assert proposals[0].admitted is True
        assert proposals[0].members == (A, B, C)
        assert proposals[0].decisions

    def test_every_pair_in_an_admitted_cluster_has_its_own_decision_or_evidence(self):
        gate = _triangle()
        gate.propose(AC, "same person", raised_by="fellegi_sunter", score=0.98)
        _commit(gate, AC)
        proposals = cluster_from_decisions(gate.store)
        assert proposals[0].admitted is True
        assert len(proposals[0].decisions) == 3
        assert proposals[0].blocked_pairs == ()

    def test_a_split_in_the_middle_removes_the_cluster(self):
        gate = _triangle()
        gate.split(AB, decided_by=REVIEWER, reviewer_id=REVIEWER, rationale="different national ids")
        proposals = cluster_from_decisions(gate.store)
        # The A-B-C cluster is gone; what survives is the pair that is still merged.
        assert [p.members for p in proposals] == [(B, C)]
        assert A not in proposals[0].members
        assert gate.store.current(AB).kind is DecisionKind.SPLIT
        assert gate.store.is_superseded(gate.store.history(AB)[0].decision_id) is True

    def test_cluster_membership_requires_decisions_not_scores(self):
        """A high score on all three edges still produces nothing."""
        store = DecisionStore()
        gate = IdentityResolutionGate(store)
        for pair in (AB, BC, AC):
            gate.propose(pair, "same person", raised_by="fellegi_sunter", score=0.999)
        assert cluster_from_decisions(store) == ()
        assert store.merges_in_force() == ()


class TestWhatCountsAsInconsistency:
    def test_a_conflicting_birth_date_is_positive_evidence_of_difference(self):
        """Not weak evidence. Averaging it against two agreements is the contamination."""
        reasons = contradiction_reasons(conflicting_birth_date=True, shared_id_number=True)
        assert "birth_dates_disagree" in reasons
        assert "different_id_numbers_for_the_same_identifier" in reasons

    def test_contradiction_outranks_a_decision_elsewhere_in_the_chain(self):
        gate = _triangle()
        _commit(gate, AC)
        # All three pairs are merged. A contradictory national identifier still blocks, because
        # cluster membership needs the *features* to agree across the group, not just the edges.
        proposals = cluster_from_decisions(
            gate.store,
            assessments={
                AC: PairAssessment(A, C, PairVerdict.CONTRADICTED, ("different_id_numbers_for_the_same_identifier",))
            },
        )
        assert proposals[0].admitted is False
        assert proposals[0].blocked_pairs[0].verdict is PairVerdict.CONTRADICTED

    def test_assess_without_reasons_is_unassessed_not_clean(self):
        assert contradiction_reasons().__len__() == 0


class TestTheRefusalIsVisible:
    def test_a_refused_cluster_reports_what_it_would_have_contained(self):
        gate = _triangle()
        proposal = cluster_from_decisions(
            gate.store,
            assessments={AC: PairAssessment(A, C, PairVerdict.CONTRADICTED, ("birth_dates_disagree",))},
        )[0]
        payload = proposal.to_dict()
        assert payload["admitted"] is False
        assert payload["members"] == [A, B, C]
        assert payload["blocked_pairs"][0]["reasons"] == ["birth_dates_disagree"]

    def test_a_refusal_never_leaves_an_orphan(self):
        """Every merge decision that would have contributed is still in force and retrievable."""
        gate = _triangle()
        cluster_from_decisions(gate.store)
        in_force = {d.pair_key for d in gate.store.merges_in_force()}
        assert in_force == {AB, BC}
        assert all(d.kind is DecisionKind.MERGE for d in gate.store.merges_in_force())


def test_the_chain_is_not_closed_by_a_single_node() -> None:
    """A↔B alone is a pair. A third party's contradictory evidence cannot reach into it."""
    gate = IdentityResolutionGate()
    _commit(gate, AB)
    proposals = cluster_from_decisions(
        gate.store, assessments={AC: PairAssessment(A, C, PairVerdict.CONTRADICTED, ("x",))}
    )
    assert [p.members for p in proposals] == [(A, B)]
    assert C not in proposals[0].members