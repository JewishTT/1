"""Admission ladder + WARC intake tests.

Covers the two gaps this work closed: ACCEPT_EXISTING was a declared enum member
with no code path that could ever produce it, and reason_codes reported every
satisfied rule rather than the branch that actually decided the outcome.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.admission import AdmissionEngine, AdmitDecision
from engine.assertions import EvidenceLink
from engine.calibration import AdmissionInput, CalibrationProfile, MediaProfile
from engine.intake import (
    IntakeClaim,
    Match,
    QuarantineRecord,
    WarcIntake,
    claim_id_for,
    host_of,
    untrustworthy_reason,
)


class Doc:
    """Minimal stand-in for an interpreted WARC document (structural contract)."""

    def __init__(
        self,
        document_id: str,
        url: str,
        *,
        notes: tuple[str, ...] = (),
        is_revisit: bool = False,
        text: str = "",
        body_sha256: str = "",
    ) -> None:
        self.document_id = document_id
        self.url = url
        self.notes = notes
        self.is_revisit = is_revisit
        self.text = text
        self.body_sha256 = body_sha256
        self.record_id = f"<urn:uuid:{document_id}>"
        self.warc_date = "2024-01-02T03:04:05Z"


def claim(document_id: str, *, subject="1.2.3.4", relation="exploits",
          obj="CVE-2021-44228", confidence=0.8) -> IntakeClaim:
    return IntakeClaim(
        subject=subject,
        relation=relation,
        object_value=obj,
        document_id=document_id,
        subject_kind="ipv4",
        confidence=confidence,
        evidence_id=f"EVD-{document_id}",
    )


def decide(**kwargs) -> object:
    kwargs.setdefault("candidate_id", "c1")
    kwargs.setdefault("entity_type", "ipv4")
    return AdmissionEngine().decide(AdmissionInput(**kwargs), EvidenceLink(evidence_refs=[]))



class TestAcceptExisting:
    """ACCEPT_EXISTING: a second sighting of an already-admitted entity."""

    def test_confirmed_match_merges_into_existing_entity(self):
        result = decide(
            corroboration_score=0.8, matched_entity_id="E-existing-1", match_confirmed=True
        )
        assert result.decision is AdmitDecision.ACCEPT_EXISTING
        assert result.reason_codes == ["accept_existing_match"]
        assert result.is_merge is True
        assert result.target_entity_id == "E-existing-1"

    def test_a_high_score_alone_does_not_merge_without_calibration(self):
        """**WP-E T070: this test's expectation is inverted, deliberately.**

        It read ``match_score=0.95 → ACCEPT_EXISTING`` with no confirmation. That
        cleared a bar of 0.8 out of a ``MediaProfile`` that starts empty, so the
        profile in force was the default one whose own ``version`` field reads
        ``"UNCALIBRATED-v1"``. The threshold was a number nobody fitted, applied in the
        one place where being wrong fuses two subjects irreversibly.

        0.95 is still a high score. What changed is that a score cannot *decide* on its
        own while the profile declares it has no meaning. The candidate is still
        admitted — as a new entity, carrying ``match_score`` and ``matched_entity_id``
        for a reviewer — so nothing is lost, it is simply not fused silently.

        ``test_a_calibrated_profile_restores_the_bar`` covers the other side: declare a
        calibration and the threshold works again.
        """
        result = decide(corroboration_score=0.8, matched_entity_id="E-1", match_score=0.95)
        assert result.decision is AdmitDecision.ACCEPT_NEW
        assert result.is_merge is False
        assert result.target_entity_id is None
        # The evidence for the merge is preserved on the decision, not discarded with
        # the merge. A reviewer needs to see what was proposed.
        assert result.matched_entity_id == "E-1"
        assert result.match_score == 0.95
        assert any("calibration_undeclared" in code for code in result.reason_codes), (
            f"the withheld merge must name itself: {result.reason_codes}"
        )

    def test_a_calibrated_profile_restores_the_bar(self):
        """Declaring a calibration is what re-enables the threshold, and nothing else."""
        profiles = MediaProfile()
        profiles.register(
            CalibrationProfile(
                entity_type="ipv4", threshold_match=0.8, version="ipv4-linked-v3"
            )
        )
        result = AdmissionEngine(profiles).decide(
            AdmissionInput(
                candidate_id="c-cal",
                entity_type="ipv4",
                structural_score=0.2,
                corroboration_score=0.8,
                matched_entity_id="E-cal",
                match_score=0.93,
            )
        )
        assert result.decision is AdmitDecision.ACCEPT_EXISTING
        assert result.is_merge is True
        assert result.target_entity_id == "E-cal"
        assert result.reason_codes == ["accept_existing_match"]

    def test_a_confirmed_match_merges_even_with_no_calibration(self):
        """A human looked at it. No threshold may overrule a reviewed decision."""
        result = decide(
            corroboration_score=0.8, matched_entity_id="E-1", match_score=0.1, match_confirmed=True
        )
        assert result.decision is AdmitDecision.ACCEPT_EXISTING
        assert result.is_merge is True

    def test_low_scoring_unconfirmed_match_does_not_merge(self):
        result = decide(corroboration_score=0.8, matched_entity_id="E-1", match_score=0.4)
        assert result.decision is AdmitDecision.ACCEPT_NEW
        assert result.is_merge is False
        assert result.target_entity_id is None

    def test_match_threshold_is_profile_configurable(self):
        profiles = MediaProfile()
        profiles.register(CalibrationProfile(entity_type="ipv4", threshold_match=0.99))
        result = AdmissionEngine(profiles).decide(
            AdmissionInput(
                candidate_id="c1",
                entity_type="ipv4",
                corroboration_score=0.8,
                matched_entity_id="E-1",
                match_score=0.95,
            ),
            EvidenceLink(evidence_refs=[]),
        )
        assert result.decision is AdmitDecision.ACCEPT_NEW

    def test_match_never_overrides_a_hard_reject(self):
        result = decide(
            has_valid_identifier=False,
            corroboration_score=0.9,
            matched_entity_id="E-1",
            match_confirmed=True,
        )
        assert result.decision is AdmitDecision.REJECT
        assert result.reason_codes == ["hard_reject_invalid_id"]

    def test_match_never_overrides_quarantine(self):
        result = decide(
            strong_contradiction=True,
            corroboration_score=0.9,
            matched_entity_id="E-1",
            match_confirmed=True,
        )
        assert result.decision is AdmitDecision.QUARANTINE
        assert result.target_entity_id is None

    def test_weakly_corroborated_match_still_defers(self):
        # Merging must not launder a weakly evidenced candidate into an entity.
        result = decide(corroboration_score=0.1, matched_entity_id="E-1", match_confirmed=True)
        assert result.decision is AdmitDecision.DEFER
        assert result.reason_codes == ["defer_insufficient_evidence"]

    def test_no_match_reports_no_target(self):
        result = decide(corroboration_score=0.9)
        assert result.decision is AdmitDecision.ACCEPT_NEW
        assert result.matched_entity_id is None
        assert result.target_entity_id is None


class TestReasonCodes:
    """Reason codes must describe the deciding branch, not every rule that fired."""

    def test_hard_reject_reports_only_the_reject(self):
        result = decide(has_valid_identifier=False, corroboration_score=0.95, structural_score=0.9)
        assert result.reason_codes == ["hard_reject_invalid_id"]
        assert "accept_strong_corroboration" not in result.reason_codes
        assert "accept_qualified_structurally" not in result.reason_codes

    def test_quarantine_reports_only_the_contradiction(self):
        result = decide(strong_contradiction=True, corroboration_score=0.95)
        assert result.reason_codes == ["hard_reject_contradiction"]
        assert "accept_strong_corroboration" not in result.reason_codes

    def test_defer_reports_the_failing_floor_only(self):
        assert decide(corroboration_score=0.1).reason_codes == ["defer_insufficient_evidence"]

    def test_strong_corroboration_wins_over_structural_shortcut(self):
        result = decide(corroboration_score=0.9, structural_score=0.8)
        assert result.decision is AdmitDecision.ACCEPT_NEW
        assert result.reason_codes == ["accept_strong_corroboration"]

    def test_structural_shortcut_used_when_corroboration_only_mediocre(self):
        result = decide(corroboration_score=0.5, structural_score=0.75)
        assert result.decision is AdmitDecision.ACCEPT_NEW
        assert result.reason_codes == ["accept_qualified_structurally"]

    def test_no_confident_signal_is_reported_when_nothing_fires(self):
        result = decide(corroboration_score=0.5, structural_score=0.2)
        assert result.decision is AdmitDecision.DEFER
        assert result.reason_codes == ["no_confident_signal"]


class TestIntakeAggregation:
    """The same triple seen N times is one claim with N-worth of evidence."""

    def test_single_sighting_defers(self):
        result = WarcIntake().run([Doc("d1", "https://a.example/p")], [claim("d1")])
        assert result.documents_seen == 1 and result.claims_seen == 1
        assert result.decisions[0].decision is AdmitDecision.DEFER

    def test_repeated_triple_collapses_to_one_decision(self):
        docs = [Doc(f"d{i}", f"https://h{i}.example/p") for i in range(3)]
        result = WarcIntake().run(docs, [claim(f"d{i}") for i in range(3)])
        assert len(result.decisions) == 1
        assert len(result.assertions) == 1

    def test_distinct_triples_get_distinct_decisions(self):
        docs = [Doc("d1", "https://a.example/p"), Doc("d2", "https://b.example/p")]
        result = WarcIntake().run(docs, [claim("d1"), claim("d2", obj="CVE-2022-22965")])
        assert len(result.decisions) == 2
        assert len({d.candidate_id for d in result.decisions}) == 2

    def test_independent_hosts_raise_corroboration_above_mirrors(self):
        independent = WarcIntake().run(
            [Doc(f"d{i}", f"https://h{i}.example/p") for i in range(3)],
            [claim(f"d{i}") for i in range(3)],
        )
        mirrors = WarcIntake().run(
            [Doc(f"d{i}", "https://mirror.example/p") for i in range(3)],
            [claim(f"d{i}") for i in range(3)],
        )
        assert (
            independent.decisions[0].score_vector.corroboration
            > mirrors.decisions[0].score_vector.corroboration
        )
        assert independent.decisions[0].score_vector.independence == 1.0
        assert mirrors.decisions[0].score_vector.independence == 0.0

    def test_one_host_repeated_carries_no_independence(self):
        # Three mirrors of one site are not independent corroboration.
        docs = [Doc(f"d{i}", "https://mirror.example/p") for i in range(3)]
        vector = WarcIntake().run(docs, [claim(f"d{i}") for i in range(3)]).decisions[0].score_vector
        assert vector.independence == 0.0
        assert vector.corroboration == 0.5
        assert vector.evidence_publications == 3

    def test_evidence_refs_name_every_contributing_document(self):
        docs = [Doc(f"d{i}", f"https://h{i}.example/p") for i in range(2)]
        decision = WarcIntake().run(docs, [claim("d0"), claim("d1")]).decisions[0]
        assert {r.observation_id for r in decision.evidence.evidence_refs} == {"d0", "d1"}
        assert decision.evidence.publication_count == 2
        assert decision.evidence.independent_source_count == 2


class TestIntakeQuarantine:
    def test_truncated_capture_is_quarantined_not_dropped(self):
        bad = Doc("bad", "https://a.example/p", notes=("record_truncated",))
        result = WarcIntake().run([bad], [])
        assert len(result.quarantined) == 1
        assert result.quarantined[0].reason == "intake.untrustworthy_capture:record_truncated"
        assert result.quarantined[0].document_id == "bad"

    def test_error_status_capture_is_quarantined(self):
        bad = Doc("bad", "https://a.example/p", notes=("http_error_status:503",))
        assert WarcIntake().run([bad], []).quarantined[0].reason.endswith("http_error_status:503")

    def test_quarantined_capture_cannot_corroborate(self):
        good = Doc("good", "https://a.example/p")
        bad = Doc("bad", "https://b.example/p", notes=("record_truncated",))
        result = WarcIntake().run([good, bad], [claim("good"), claim("bad")])
        # Only the trusted document produces a decision at all.
        assert len(result.decisions) == 1
        assert result.decisions[0].evidence.publication_count == 1

    def test_quarantine_record_keeps_refs_only_provenance(self):
        payload = QuarantineRecord(
            document_id="bad", reason="r", url="https://a.example/p", body_sha256="f" * 64
        ).to_dict()
        assert set(payload) == {"document_id", "reason", "url", "body_sha256"}

    def test_clean_document_is_not_quarantined(self):
        assert WarcIntake().run([Doc("ok", "https://a.example/p")], []).quarantined == []

    def test_untrustworthy_reason_ignores_informational_notes(self):
        doc = Doc("d", "https://a.example", notes=("non_text_payload",))
        assert untrustworthy_reason(doc) is None


class TestIntakeResolution:
    def test_a_resolver_score_alone_does_not_merge(self):
        """**WP-E T070: an uncalibrated resolver score routes to review, not to merge.**

        ``WarcIntake`` reaches the admission lane with no resolver-confirmed match, so
        the merge decision rests entirely on ``threshold_match`` — which, with an empty
        ``MediaProfile``, is 0.8 out of a profile that declares itself uncalibrated.
        A resolver returning ``Match(score=0.93)`` is evidence *for* a merge, not a
        decision to make one.

        The candidate is still admitted as a new entity and still carries the
        resolver's target for a reviewer. What it is not is fused silently on a
        threshold nobody fitted.
        """
        result = WarcIntake().run(
            [Doc(f"d{i}", f"https://h{i}.example/p") for i in range(2)],
            [claim("d0"), claim("d1")],
            resolver=lambda c: Match(entity_id="E-77", score=0.93),
        )
        decision = result.decisions[0]
        assert decision.decision is AdmitDecision.ACCEPT_NEW
        assert decision.is_merge is False
        assert decision.matched_entity_id == "E-77", "the reviewer's evidence must survive"
        assert any("calibration_undeclared" in code for code in decision.reason_codes)
        assert result.accepted_entities != ["E-77"], (
            "an uncalibrated score must not put the candidate into an existing entity's "
            "accepted set"
        )

    def test_resolver_returning_none_leaves_the_candidate_new(self):
        result = WarcIntake().run(
            [Doc(f"d{i}", f"https://h{i}.example/p") for i in range(3)],
            [claim(f"d{i}") for i in range(3)],
            resolver=lambda c: None,
        )
        assert result.decisions[0].decision is AdmitDecision.ACCEPT_NEW
        assert result.decisions[0].is_merge is False

    def test_accepted_entities_lists_candidates_and_merges(self):
        # Each triple needs independent corroboration before it is admitted.
        docs = [Doc(f"d{i}", f"https://h{i}.example/p") for i in range(3)]
        claims = [claim(f"d{i}") for i in range(3)]
        claims += [claim(f"d{i}", obj="CVE-2022-22965") for i in range(3)]
        assert len(WarcIntake().run(docs, claims).accepted_entities) == 2

    def test_counts_by_decision_covers_every_outcome(self):
        result = WarcIntake().run([Doc("d1", "https://a.example/p")], [claim("d1")])
        assert set(result.counts_by_decision()) == {d.value for d in AdmitDecision}


class TestHelpers:
    def test_host_of_strips_www_and_lowercases(self):
        assert host_of("https://WWW.Example.COM/a") == "example.com"
        assert host_of("") == ""
        assert host_of("not a url") == ""

    def test_claim_id_is_stable_per_triple(self):
        assert claim_id_for("a", "b", "c") == claim_id_for("a", "b", "c")
        assert claim_id_for("a", "b", "c") != claim_id_for("a", "b", "d")

    def test_claim_id_property_matches_helper(self):
        assert claim("d1").claim_id == claim_id_for("1.2.3.4", "exploits", "CVE-2021-44228")

    def test_empty_intake_produces_no_decisions(self):
        result = WarcIntake().run([], [])
        assert result.decisions == [] and result.documents_seen == 0


    def test_candidate_id_is_the_stable_claim_id(self):
        result = WarcIntake().run([Doc("d1", "https://a.example/p")], [claim("d1")])
        assert result.decisions[0].candidate_id == claim_id_for(
            "1.2.3.4", "exploits", "CVE-2021-44228"
        )

    def test_revisit_counts_as_a_document_but_adds_no_claims(self):
        docs = [
            Doc("d1", "https://a.example/p"),
            Doc("d2", "https://a.example/p", is_revisit=True),
        ]
        result = WarcIntake().run(docs, [claim("d1")])
        assert result.documents_seen == 2 and result.revisits_seen == 1
        assert result.decisions[0].score_vector.evidence_publications == 1

