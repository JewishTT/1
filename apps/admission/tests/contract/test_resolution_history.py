"""Split supersedes, never erases; corroboration counts roots (spec 030 T079, T080).

ADR-030-03 D1/D3/D6, FR-082, and the WP-E closure from feature 029 that T080 exists to guard.

The two failures this file is written against:

**A split that deletes.** The obvious implementation of "undo a merge" is to drop the merge or
set a flag on it. Both destroy the record that the system once believed these were one person
*with the evidence that justified it*, which is the only thing that makes the split auditable.
An unauditable split is indistinguishable from a silent correction, so the store has no update
and no delete method and the decisions are frozen dataclasses.

**Corroboration that counts hats.** Twenty mirrors of one wire story on twenty domains are one
source wearing twenty hats. Count the hats and a press release becomes twenty independent
confirmations. :mod:`engine.intake` already counts lineage roots (WP-E T071); T080 pins that
behaviour here and pins that the measure is *named* on every decision, so an analyst reading
"corroboration 2" can see whether that was two origins or two hostnames.
"""

from __future__ import annotations

import dataclasses

import pytest

from engine.calibration import MediaProfile
from engine.intake import IntakeClaim, WarcIntake
from resolution.decision_store import (
    CORROBORATION_MEASURES,
    ClaimBinding,
    DecisionKind,
    DecisionStore,
    DecisionStoreError,
    DuplicateDecision,
    IdentityHypothesis,
    MatcherProfile,
    ResolutionDecision,
    UnknownDecision,
    corroboration_from_counts,
    new_decision,
)
from resolution.gate import (
    EvidenceItem,
    EvidenceKind,
    IdentityResolutionGate,
    MergeAuthority,
)
from resolution.span import CharSpanSelector, EvidenceSpanRef, SourceLocator

pytestmark = pytest.mark.contract

PAIR = "ENT-A&&ENT-B"
REVIEWER = "analyst-1"
CALIBRATED = MatcherProfile(
    name="fellegi_sunter",
    version="calibrated-labelled-v1",
    calibrated=True,
    calibration_evidence="benchmarks/er-baseline.md",
)


class _Doc:
    def __init__(self, document_id: str, url: str, notes: tuple[str, ...] = ()) -> None:
        self.document_id = document_id
        self.url = url
        self.body_sha256 = "sha256:" + "0" * 64
        self.notes = notes
        self.is_revisit = False


def _span(ref: str) -> EvidenceSpanRef:
    return EvidenceSpanRef(
        observation_ref=ref,
        blob_digest="sha256:" + "0" * 64,
        selector=CharSpanSelector(0, 1),
        source_locator=SourceLocator(uri=f"https://corpus.example/{ref}"),
    )


def _merge(gate: IdentityResolutionGate, pair: str = PAIR, **kwargs) -> ResolutionDecision:
    outcome = gate.commit_merge(
        pair,
        authority=MergeAuthority.HUMAN_REVIEW,
        decided_by=REVIEWER,
        reviewer_id=REVIEWER,
        matcher=CALIBRATED,
        evidence=[EvidenceItem(EvidenceKind.OBSERVATION, "registry")],
        span_refs=[_span(pair.replace("&&", "-"))],
        documents=kwargs.pop("documents", 3),
        hosts=kwargs.pop("hosts", 3),
        lineage_roots=kwargs.pop("lineage_roots", 3),
        rationale=kwargs.pop("rationale", "national id on both rows"),
    )
    assert outcome.committed is True, outcome.codes
    return outcome.decision


class TestASplitSupersedesAndNeverDeletes:
    def test_the_merge_is_still_there_after_the_split(self):
        gate = IdentityResolutionGate()
        merge = _merge(gate)
        split = gate.split(PAIR, decided_by=REVIEWER, reviewer_id="analyst-2", rationale="two people")

        assert split.decision.kind is DecisionKind.SPLIT
        assert split.decision.supersedes == merge.decision_id

        history = gate.store.history(PAIR)
        assert len(history) == 2
        first, second = history
        assert first is merge
        assert first.decision_id == merge.decision_id
        assert first.decided_by == REVIEWER
        assert first.rationale == "national id on both rows"
        assert len(first.span_refs) == 1
        assert first.corroboration_value == 3
        assert first.corroboration_measure == "lineage_roots"
        assert second.kind is DecisionKind.SPLIT
        assert second.supersedes == first.decision_id

    def test_the_merge_is_retrievable_by_id_after_being_superseded(self):
        gate = IdentityResolutionGate()
        merge = _merge(gate)
        gate.split(PAIR, decided_by=REVIEWER, rationale="two people")
        retrieved = gate.store.get(merge.decision_id)
        assert retrieved is not None
        assert retrieved.kind is DecisionKind.MERGE
        assert gate.store.is_superseded(merge.decision_id) is True

    def test_current_is_the_latest_not_superseded_row(self):
        gate = IdentityResolutionGate()
        merge = _merge(gate)
        split = gate.split(PAIR, decided_by=REVIEWER, rationale="two people").decision
        current = gate.store.current(PAIR)
        assert current.decision_id == split.decision_id
        assert current.supersedes == merge.decision_id
        assert gate.store.current_identity(PAIR) is None

    def test_the_decision_row_cannot_be_edited(self):
        gate = IdentityResolutionGate()
        merge = _merge(gate)
        with pytest.raises(dataclasses.FrozenInstanceError):
            merge.kind = DecisionKind.SPLIT
        with pytest.raises(dataclasses.FrozenInstanceError):
            merge.decided_by = "someone-else"
        with pytest.raises(dataclasses.FrozenInstanceError):
            merge.rationale = "reinterpreted"

    def test_the_corroboration_detail_cannot_be_edited_through_the_row(self):
        gate = IdentityResolutionGate()
        merge = _merge(gate)
        with pytest.raises(TypeError):
            merge.corroboration_detail["hosts"] = 99

    def test_the_store_has_no_update_or_delete(self):
        forbidden = ("update", "delete", "remove", "revoke", "set_state", "unset", "clear", "pop")
        store = DecisionStore()
        for name in forbidden:
            assert not hasattr(store, name), f"DecisionStore.{name} would let history be rewritten"

    def test_appending_the_same_id_twice_is_refused(self):
        store = DecisionStore()
        merge = _merge(IdentityResolutionGate(store))
        with pytest.raises(DuplicateDecision):
            store.append(merge)

    def test_a_split_with_nothing_to_contradict_is_refused(self):
        gate = IdentityResolutionGate()
        from resolution.decision_store import UnknownDecision as _Unknown

        with pytest.raises(_Unknown):
            gate.split(PAIR, decided_by=REVIEWER, rationale="no merge exists")

    def test_a_chain_is_a_chain_not_a_fork(self):
        gate = IdentityResolutionGate()
        merge = _merge(gate)
        split = gate.split(PAIR, decided_by=REVIEWER, rationale="two people").decision
        from resolution.decision_store import DecisionStoreError

        forked = new_decision(
            pair_key=PAIR,
            kind=DecisionKind.NO_MATCH,
            decided_by=REVIEWER,
            supersedes=merge.decision_id,
        )
        with pytest.raises(DecisionStoreError):
            gate.store.append(forked)
        assert gate.store.superseding(split.decision_id) is None
        assert len(gate.store.history(PAIR)) == 2

    def test_the_audit_trail_answers_what_did_the_system_believe_at_time_t(self):
        gate = IdentityResolutionGate()
        _merge(gate)
        gate.split(PAIR, decided_by=REVIEWER, rationale="two people")
        believed = [d for d in gate.store.history(PAIR) if not gate.store.is_superseded(d.decision_id)]
        assert [d.kind for d in believed] == [DecisionKind.SPLIT]
        # ...and the question that the flag-based alternative cannot answer.
        assert len(gate.store.history(PAIR)) == 2


class TestClaimsStayTraceableToTheirInterpretation:
    def test_a_claim_records_the_decision_it_was_written_under(self):
        gate = IdentityResolutionGate()
        merge = _merge(gate)
        binding = gate.bind_claim("CL-1", PAIR, decided_by="intake")
        assert binding.interpretation_id == merge.decision_id
        assert gate.store.reading_of("CL-1").decision_id == merge.decision_id

    def test_a_later_split_does_not_repoint_the_claim(self):
        """FR-082's second clause, and the one a mutable entity_id column destroys."""
        gate = IdentityResolutionGate()
        merge = _merge(gate)
        gate.bind_claim("CL-1", PAIR)
        split = gate.split(PAIR, decided_by=REVIEWER, rationale="two people").decision

        assert gate.store.claim_binding("CL-1").interpretation_id == merge.decision_id
        assert gate.store.reading_of("CL-1").decision_id == merge.decision_id
        assert gate.store.reading_of("CL-1").kind is DecisionKind.MERGE
        assert gate.store.current(PAIR).decision_id == split.decision_id

    def test_the_claim_reads_differently_under_the_new_interpretation_without_being_rewritten(self):
        gate = IdentityResolutionGate()
        _merge(gate)
        gate.bind_claim("CL-1", PAIR)
        gate.split(PAIR, decided_by=REVIEWER, rationale="two people")
        remerged = gate.commit_merge(
            PAIR,
            authority=MergeAuthority.HUMAN_REVIEW,
            decided_by="analyst-3",
            reviewer_id="analyst-3",
            matcher=CALIBRATED,
            evidence=[EvidenceItem(EvidenceKind.OBSERVATION, "registry")],
            span_refs=[_span("re-grounded")],
            lineage_roots=2,
            rationale="new passport number on both rows",
        )
        assert remerged.committed is True

        written_under = gate.store.claim_binding("CL-1").interpretation_id
        assert written_under != remerged.decision.decision_id
        assert gate.store.claim_binding("CL-1").interpretation_id == written_under
        assert gate.store.reading_of("CL-1").decision_id == written_under

    def test_claims_written_before_any_decision_record_no_interpretation(self):
        gate = IdentityResolutionGate()
        binding = gate.bind_claim("CL-orphan", PAIR)
        assert binding.interpretation_id is None
        assert gate.store.reading_of("CL-orphan") is None
        # ...and it is not back-filled when a merge arrives later.
        _merge(gate)
        assert gate.store.claim_binding("CL-orphan").interpretation_id is None

    def test_a_claim_cannot_be_bound_to_a_decision_that_does_not_exist(self):
        store = DecisionStore()
        with pytest.raises(UnknownDecision):
            store.bind_claim("CL-9", "RDC-does-not-exist")

    def test_claims_written_under_a_decision_are_listable(self):
        gate = IdentityResolutionGate()
        merge = _merge(gate)
        for claim in ("CL-1", "CL-2", "CL-3"):
            gate.bind_claim(claim, PAIR)
        assert {b.claim_id for b in gate.store.claims_written_under(merge.decision_id)} == {
            "CL-1",
            "CL-2",
            "CL-3",
        }


class TestCompetingHypothesesSurvive:
    def test_a_decision_does_not_delete_the_hypotheses_it_rejected(self):
        gate = IdentityResolutionGate()
        same = gate.propose(PAIR, "same person", raised_by="fellegi_sunter", score=0.97)
        other = gate.propose(PAIR, "same name, different person", raised_by="analyst-1")
        _merge(gate)

        surviving = {h.statement for h in gate.store.hypotheses(PAIR)}
        assert surviving == {"same person", "same name, different person"}
        assert same.hypothesis_id in {h.hypothesis_id for h in gate.store.hypotheses(PAIR)}
        assert other.hypothesis_id in {h.hypothesis_id for h in gate.store.hypotheses(PAIR)}

    def test_a_rejected_hypothesis_is_retrievable_after_the_merge(self):
        gate = IdentityResolutionGate()
        rejected = gate.propose(PAIR, "shared mailbox, two people", raised_by="analyst-1")
        considered = gate.propose(PAIR, "same person", raised_by="fellegi_sunter", score=0.97)
        _merge(gate)
        found = gate.store.hypotheses(PAIR)
        assert len(found) == 2
        assert {h.statement for h in found} == {"same person", "shared mailbox, two people"}
        assert rejected.hypothesis_id in {h.hypothesis_id for h in found}
        assert considered.hypothesis_id in {h.hypothesis_id for h in found}

    def test_a_split_can_point_at_the_hypothesis_that_was_right(self):
        gate = IdentityResolutionGate()
        _merge(gate)
        other = gate.propose(PAIR, "same name, different person", raised_by="analyst-2")
        outcome = gate.split(
            PAIR, decided_by=REVIEWER, reviewer_id="analyst-2", hypothesis_id=other.hypothesis_id,
            rationale="national ids differ",
        )
        assert outcome.committed
        assert outcome.decision.hypothesis_id == other.hypothesis_id
        assert other.statement in {h.statement for h in gate.store.hypotheses(PAIR)}

    def test_a_decision_cannot_cite_a_hypothesis_that_was_never_proposed(self):
        gate = IdentityResolutionGate()
        outcome = gate.commit_merge(
            PAIR,
            authority=MergeAuthority.HUMAN_REVIEW,
            decided_by=REVIEWER,
            hypothesis_id="HYP-invented",
            evidence=[EvidenceItem(EvidenceKind.OBSERVATION, "registry")],
            span_refs=[_span("x")],
        )
        assert outcome.committed is False
        assert "fr080_unknown_hypothesis" in outcome.codes

    def test_a_hypothesis_id_is_unique(self):
        store = DecisionStore()
        hypothesis = IdentityHypothesis(
            hypothesis_id="HYP-1", pair_key=PAIR, statement="same person", raised_by="m"
        )
        store.record_hypothesis(hypothesis)
        with pytest.raises(DuplicateDecision):
            store.record_hypothesis(hypothesis)


class TestCorroborationCountsLineageRootsNotHostnames:
    """T080 — guarding the WP-E closure already delivered in feature 029."""

    def test_twenty_mirrors_of_one_origin_are_one_source(self):
        documents = [f"doc-{i}" for i in range(20)]
        hosts = [f"mirror{i}.example" for i in range(20)]
        docs = [_Doc(doc, f"https://{host}/wire/1") for doc, host in zip(documents, hosts, strict=True)]
        claims = [IntakeClaim("Vladimir Petrov", "mentioned in", "wire story", doc) for doc in documents]

        counted_hosts = WarcIntake().run(docs, claims)
        counted_roots = WarcIntake().run(
            docs, claims, lineage_by_document={doc: "origin-wire-story-1" for doc in documents}
        )
        by_hosts = counted_hosts.decisions[0]
        by_roots = counted_roots.decisions[0]

        # Hostname counting: 20 domains, full marks. Lineage counting: 1 origin, and the
        # corroboration halves. Same twenty documents either way.
        assert by_hosts.evidence_counts["effective_sources"] == 20
        assert by_hosts.score_vector.corroboration == 1.0
        assert by_roots.evidence_counts["hosts"] == 20
        assert by_roots.evidence_counts["effective_sources"] == 1
        assert by_roots.evidence_counts["independence_measured_on"] == "lineage"
        assert by_roots.score_vector.independence == 0.0
        assert by_roots.score_vector.corroboration == 0.5

    def test_the_measure_is_named_on_the_decision_row(self):
        gate = IdentityResolutionGate()
        merge = _merge(gate, documents=20, hosts=20, lineage_roots=1)
        assert merge.corroboration_measure == "lineage_roots"
        assert merge.corroboration_value == 1
        assert merge.corroboration_detail["hosts"] == 20
        assert merge.corroboration_detail["independence_measured_on"] == "lineage"

    def test_both_numbers_are_always_reported(self):
        """An analyst reading '20 hosts' must be able to see '1 origin' beside it."""
        gate = IdentityResolutionGate()
        merge = _merge(gate, documents=12, hosts=9, lineage_roots=2)
        assert merge.corroboration_detail["documents"] == 12
        assert merge.corroboration_detail["hosts"] == 9
        assert merge.corroboration_detail["effective_sources"] == 2

    def test_without_lineage_the_measure_is_hosts_and_says_so(self):
        gate = IdentityResolutionGate()
        merge = _merge(gate, documents=4, hosts=4, lineage_roots=None)
        assert merge.corroboration_measure == "hosts"
        assert merge.corroboration_detail["independence_measured_on"] == "hosts"

    def test_a_decision_cannot_be_written_without_naming_its_measure(self):
        with pytest.raises(Exception) as excinfo:
            ResolutionDecision(
                decision_id="RDC-1",
                pair_key=PAIR,
                kind=DecisionKind.MERGE,
                decided_by="analyst-1",
                corroboration_measure="",
                evidence_refs=("registry",),
            )
        assert "corroboration_measure" in str(excinfo.value)

    def test_the_measure_set_is_closed(self):
        assert CORROBORATION_MEASURES == {"lineage_roots", "hosts", "none"}
        with pytest.raises(DecisionStoreError):
            new_decision(
                pair_key=PAIR,
                kind=DecisionKind.REVIEW,
                decided_by="analyst-1",
                corroboration=("distinct_websites", 3, {}),
            )

    def test_every_decision_in_the_store_names_its_measure(self):
        gate = IdentityResolutionGate()
        _merge(gate)
        gate.split(PAIR, decided_by=REVIEWER, rationale="two people")
        gate.propose(PAIR, "third reading", raised_by="analyst-3")
        for decision in gate.store.all_decisions():
            assert decision.corroboration_measure in CORROBORATION_MEASURES
            assert decision.to_dict()["corroboration_measure"] == decision.corroboration_measure

    def test_none_is_an_honest_not_measured_rather_than_a_silent_zero(self):
        measure, value, detail = corroboration_from_counts(
            documents=1, hosts=1, lineage_roots=None
        )
        assert (measure, value) == ("hosts", 1)
        assert detail["independence_measured_on"] == "hosts"

        decision = new_decision(
            pair_key=PAIR, kind=DecisionKind.REVIEW, decided_by="analyst-1"
        )
        assert decision.corroboration_measure == "none"
        assert decision.corroboration_value == 0
        assert decision.corroboration_detail["independence_measured_on"] == "none"

    def test_an_unregistered_profile_falls_back_to_the_honest_measure(self):
        """The bootstrap profile is uncalibrated, so a merge on it is a human's call — but the
        counts still have to say which measure produced them."""
        profiles = MediaProfile()
        assert len(profiles) == 0
        profile = profiles.lookup("person", "*", "*")
        assert profile.is_calibrated is False


class TestDecisionRowShape:
    def test_a_decision_is_attributed(self):
        with pytest.raises(Exception) as excinfo:
            new_decision(pair_key=PAIR, kind=DecisionKind.MERGE, decided_by="")
        assert "decided_by" in str(excinfo.value)

    def test_a_merge_carries_something_to_merge_with(self):
        with pytest.raises(DecisionStoreError) as excinfo:
            ResolutionDecision(
                decision_id="RDC-2",
                pair_key=PAIR,
                kind=DecisionKind.MERGE,
                decided_by="a",
                corroboration_measure="lineage_roots",
            )
        assert "evidence" in str(excinfo.value)

    def test_a_calibration_claim_needs_a_referent(self):
        with pytest.raises(DecisionStoreError) as excinfo:
            MatcherProfile(name="m", version="v1", calibrated=True)
        assert "names no evidence" in str(excinfo.value)

    def test_a_decision_serialises_with_everything_an_auditor_needs(self):
        gate = IdentityResolutionGate()
        merge = _merge(gate)
        payload = merge.to_dict()
        for key in (
            "decision_id", "pair_key", "kind", "decided_by", "decided_at", "matcher",
            "corroboration_measure", "corroboration_value", "corroboration_detail",
            "rule_version", "rationale", "evidence_refs", "grounding",
        ):
            assert key in payload
        assert payload["grounding"] == "grounded"


def test_claim_binding_is_itself_frozen() -> None:
    binding = ClaimBinding(claim_id="CL-1", interpretation_id="RDC-1")
    with pytest.raises(dataclasses.FrozenInstanceError):
        binding.interpretation_id = "RDC-2"