"""Constitution 4 and CD-7: the platform never fabricates, and losing semantics must not
cost structure.

**Constitution 4 — nothing is asserted that was not observed.** This is the invariant every
other one leans on, and it is the one with the most ways to fail quietly. The four shapes of
fabrication this suite pins, each of which has been *plausible* at some point in this
platform's design:

1. **Inventing an operator type.** The sharpest version: a bare string arrives where a
   ``RelationRef`` is expected, and accepting it means guessing whether ``"owner of"`` is a
   type or a surface. Refused, with a message naming both ways forward.
2. **Defaulting a missing reference.** A frame, a regime, a tenant - each defaulted "for
   convenience" is somebody else's decision silently replaced by a default. Refused.
3. **Padding a time.** A day-precision date parsed to midnight, with nothing recording that
   the midnight was ours. The raw text and the precision are both kept so the convention is
   checkable.
4. **Rounding an unknown to a known.** An axis the vocabulary has no entry for, mapped onto
   the nearest one - which puts the wrong kind of time into the world with the right kind's
   confidence. Refused, with the six listed.

**CD-7 — semantic incompleteness must not reduce structural observability.** This is the
invariant that is easy to agree with and hard to keep, because every individual decision that
violates it looks reasonable. A producer that skips a key it cannot type; an assembler that
drops a signal it cannot attribute; a table reader that skips a row whose columns do not line
up. Each is defensible in isolation and each loses an observation.

The tests below are paired deliberately: for every case where a fabrication is refused, the
neighbouring test shows the *honest* version is still accepted. A refusal that also lost the
observation would satisfy constitution 4 and violate CD-7, and only the pair catches that.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from extractors.signals import (
    Neighbourhood,
    RelationSignal,
    SignalContractError,
    SignalKind,
)
from extractors.signals.protocol import ExtractionScope

from domain.capture import CaptureTimeBasis
from domain.predicate_hypothesis import (
    PredicateContractError,
    PredicateHypothesis,
    PredicateResolutionState,
)
from domain.relation_candidate import (
    CandidateContractError,
    CandidateNotAdmissible,
    CandidateStatus,
    RelationCandidate,
    TemporalHypothesis,
)
from domain.relation_claim import RelationClaim, RelationStatus
from domain.relation_claim_material import (
    EvidenceGrade as MaterialGrade,
)
from domain.relation_claim_material import (
    MaterialContractError,
    build,
)
from domain.temporal_observation import (
    SourceTemporalObservation,
    TemporalAxis,
    TemporalObservationContractError,
    TemporalPrecision,
)
from semantic.contracts import RelationRef

UTC = UTC


class TestThePlatformDoesNotInventAnOperatorType:
    def test_a_bare_string_at_a_ref_position_is_refused(self) -> None:
        """``"owner of"`` and ``"works_for"`` are the same shape and mean opposite things.

        Guessing would not merely lose information - it would commit a *typed* relation to
        the world that the platform has no evidence for, and the error would be invisible
        because the guess produces a perfectly well-formed reference.
        """
        with pytest.raises(PredicateContractError) as excinfo:
            PredicateHypothesis(relation_ref="works_for", surface_form="CEO of")
        assert excinfo.value.code == "predicate_string_ref_refused"
        assert "RelationRef('works_for')" in str(excinfo.value)

    def test_the_candidate_refuses_it_too_and_redirects(self) -> None:
        with pytest.raises(CandidateContractError) as excinfo:
            RelationCandidate(
                subject_mention_ref="MN-A",
                object_mention_ref="MN-B",
                relation_ref="owner of",  # type: ignore[arg-type]
                context_ref="CX-1",
                semantic_regime_ref="RG-1",
                tenant_id="T1",
                temporal_hypothesis=TemporalHypothesis.absent(),
            )
        assert excinfo.value.code == "invalid_relation_ref"
        assert "relation_surface" in str(excinfo.value)

    def test_cd7_and_the_honest_version_is_still_accepted(self) -> None:
        """The pair that matters: refused *and* preserved.

        A refusal that also discarded the words would satisfy constitution 4 and break CD-7,
        which is why these two live in one test rather than two.
        """
        untyped = RelationCandidate(
            subject_mention_ref="MN-A",
            object_mention_ref="MN-B",
            relation_surface="owner of",
            context_ref="CX-1",
            semantic_regime_ref="RG-1",
            tenant_id="T1",
            temporal_hypothesis=TemporalHypothesis.absent(),
        ).with_id()
        assert untyped.relation_ref is None
        assert untyped.relation_surface == "owner of"
        assert untyped.predicate_hypothesis.resolution_state is PredicateResolutionState.UNKNOWN


class TestThePlatformDoesNotDefaultSomebodyElsesDecision:
    @pytest.mark.parametrize(
        "kwargs",
        [
            pytest.param({"context_ref": ""}, id="no evidence frame"),
            pytest.param({"semantic_regime_ref": ""}, id="no semantic regime"),
        ],
    )
    def test_a_candidate_names_both_or_neither(self, kwargs) -> None:
        """A frame and a regime are decisions somebody else made (FR-015, FR-016)."""
        base = {
            "subject_mention_ref": "MN-A",
            "object_mention_ref": "MN-B",
            "relation_surface": "owner of",
            "context_ref": "CX-1",
            "semantic_regime_ref": "RG-1",
            "tenant_id": "T1",
            "temporal_hypothesis": TemporalHypothesis.absent(),
        }
        with pytest.raises(CandidateContractError):
            RelationCandidate(**{**base, **kwargs})

    def test_a_signal_scope_refuses_to_invent_its_own_frame(self) -> None:
        for field in ("context_ref", "semantic_regime_ref", "tenant_id"):
            base = {
                "tenant_id": "T1",
                "context_ref": "CX-1",
                "semantic_regime_ref": "RG-1",
            }
            base[field] = ""
            with pytest.raises(SignalContractError) as excinfo:
                ExtractionScope(**base)
            assert excinfo.value.code == "extraction_scope_reference_required"

    def test_a_cd7_check_a_signal_with_neither_type_nor_words_is_refused(self) -> None:
        """``''`` is not a small gap; it is an observation with no content."""
        with pytest.raises(SignalContractError) as excinfo:
            RelationSignal(
                subject_mention_ref="MN-A",
                object_mention_ref="MN-B",
                kind=SignalKind.CO_OCCURRENCE,
                relation_surface="",
                neighbourhood=Neighbourhood(
                    characters_scanned=10, pairs_considered=1, scope_read="a sentence"
                ),
                tenant_id="T1",
            )
        assert excinfo.value.code == "signal_asserts_nothing"


class TestThePlatformDoesNotPadATime:
    def test_a_day_precision_date_records_that_midnight_was_ours(self) -> None:
        observation = SourceTemporalObservation(
            temporal_axis=TemporalAxis.PUBLISHED_AT,
            capture_ref="CAP-1",
            stated_value=datetime(2024, 3, 15, tzinfo=UTC),
            raw_value="20240315",
            precision=TemporalPrecision.DAY,
            basis=CaptureTimeBasis.PUBLICATION,
            evidence_location="date filed",
            tenant_id="T1",
        )
        assert observation.is_ordered_precision
        assert observation.raw_value == "20240315"
        assert observation.stated_value.isoformat().startswith("2024-03-15T00:00")

    def test_a_naive_instant_is_refused_rather_than_assumed_utc(self) -> None:
        """Assuming UTC would put a fact in the world that no source stated."""
        with pytest.raises(TemporalObservationContractError) as excinfo:
            SourceTemporalObservation(
                temporal_axis=TemporalAxis.PUBLISHED_AT,
                capture_ref="CAP-1",
                stated_value=datetime(2024, 3, 15),  # noqa: DTZ001 - deliberately naive
                precision=TemporalPrecision.DAY,
                evidence_location="date filed",
                tenant_id="T1",
            )
        assert excinfo.value.code == "stated_value_naive"

    def test_an_open_interval_is_left_open(self) -> None:
        """Padding ``known_until`` to "now" asserts the fact stopped being knowable when
        the platform happened to look."""
        observation = SourceTemporalObservation(
            temporal_axis=TemporalAxis.KNOWN_FROM,
            capture_ref="CAP-1",
            stated_value=datetime(2024, 1, 1, tzinfo=UTC),
            evidence_location="retrieved",
            tenant_id="T1",
        )
        assert observation.stated_value_end is None
        assert observation.precision is TemporalPrecision.RANGE


class TestThePlatformDoesNotRoundAnUnknownToAKnown:
    def test_a_seventh_axis_is_refused_and_the_six_are_listed(self) -> None:
        """Listing the vocabulary is the difference between a dead end and a next step."""
        with pytest.raises(TemporalObservationContractError) as excinfo:
            SourceTemporalObservation(
                temporal_axis="announcement_date",  # type: ignore[arg-type]
                capture_ref="CAP-1",
                stated_value=datetime(2024, 1, 1, tzinfo=UTC),
                evidence_location="x",
                tenant_id="T1",
            )
        assert excinfo.value.code == "temporal_axis_unknown"
        for axis in TemporalAxis:
            assert axis.value in str(excinfo.value)

    def test_an_unknown_meta_key_is_read_rather_than_dropped(self) -> None:
        """CD-7 in the producer: a platform that discards metadata it cannot type is
        losing evidence, and the loss is invisible in the output."""
        from extractors.signals.metadata import meta_entries

        head = '<meta name="x-custom-thing" content="kept anyway">'
        entries = meta_entries(head)
        assert len(entries) == 1
        assert entries[0][1] == "x-custom-thing"
        assert entries[0][3] == "", "reported as unrecognised rather than dropped"

    def test_a_table_row_that_does_not_line_up_is_skipped_not_mispaired(self) -> None:
        """CD-7 in the table producer, and the choice of which failure to accept.

        Skipping the row loses three cells. Mispairing them attaches values to columns the
        markup never put them in, and that is a *falsehood about the document's structure* -
        the cheapest kind to produce, because the output still looks like a table. This
        suite records the decision rather than merely the behaviour, because a future
        maintainer will reasonably wonder why rows go missing.
        """
        from extractors.signals.tables import TableExtractor

        ragged = (
            "<table><tr><th>Name</th><th>Role</th><th>Since</th></tr>"
            "<tr><td>Jane Doe</td><td>CEO</td></tr>"
            "<tr><td>John Roe</td><td>CFO</td><td>2021</td></tr></table>"
        )
        signals = TableExtractor().extract(
            ragged,
            scope=ExtractionScope(
                tenant_id="T1", context_ref="CX-1", semantic_regime_ref="RG-1"
            ),
        )
        rows = {s.extra["row_index"] for s in signals}
        # Row 0 is the header, row 1 is the short one, row 2 is the well-formed one.
        assert rows == {2}, f"only the well-formed row should report, got rows {sorted(rows)}"


class TestAdmissionIsNotAFormality:
    def test_a_cd1_reading_admits_on_its_evidence_not_its_label(self) -> None:
        """The label is not the gate, and the gate can still refuse.

        Both halves in one test because either alone would be a weak claim: a platform where
        every label admits has made admission a formality, and a platform where no label
        admits has not removed the label, it has inverted it.
        """
        from domain.relation_claim_material import admit

        def material_for(status: CandidateStatus):
            candidate = RelationCandidate(
                subject_mention_ref="MN-A",
                object_mention_ref="MN-B",
                relation_ref=RelationRef("works_for"),
                relation_surface="CEO of",
                context_ref="CX-1",
                semantic_regime_ref="RG-1",
                tenant_id="T1",
                candidate_status=status,
                temporal_hypothesis=TemporalHypothesis.absent(),
            ).with_id()
            return build(
                candidate,
                subject_ref="EN-A",
                object_ref="EN-B",
                revision_number=1,
                evidence_grade=MaterialGrade.WEAK,
                tenant_id="T1",
            )

        # The label does not block.
        propose = material_for(CandidateStatus.PROPOSE)
        assert admit(
            propose, __import__(
                "domain.relation_claim_material", fromlist=["unvalidated_report"]
            ).unvalidated_report(propose),
            claim_status=RelationStatus.ACTIVE,
        ).relation_id

        # A recorded failure still does.
        for status in (CandidateStatus.REJECTED, CandidateStatus.CONTRADICTED):
            material = material_for(status)
            with pytest.raises(CandidateNotAdmissible):
                admit(
                    material,
                    __import__(
                        "domain.relation_claim_material", fromlist=["unvalidated_report"]
                    ).unvalidated_report(material),
                )

    def test_a_cd6_boundary_the_claim_cannot_be_written_with_a_none_predicate(self) -> None:
        """``RelationClaim.relation_type`` is bare ``str``.

        Not ``str | None`` with a check - the field has nowhere to put a None, so the
        mistake is unrepresentable rather than merely refused. That is the stronger
        guarantee and the reason it was worth a boundary change.
        """
        annotation = str(RelationClaim.__dataclass_fields__["relation_type"].type)
        assert annotation == "str"
        assert "None" not in annotation

    def test_cd6_the_material_boundary_names_what_to_do_instead(self) -> None:
        """A gate that only says no gets routed around by inventing a type."""
        candidate = RelationCandidate(
            subject_mention_ref="MN-A",
            object_mention_ref="MN-B",
            relation_surface="owner of",
            context_ref="CX-1",
            semantic_regime_ref="RG-1",
            tenant_id="T1",
            temporal_hypothesis=TemporalHypothesis.absent(),
        ).with_id()
        with pytest.raises(MaterialContractError) as excinfo:
            build(
                candidate,
                subject_ref="EN-A",
                object_ref="EN-B",
                revision_number=1,
                evidence_grade=MaterialGrade.WEAK,
                tenant_id="T1",
            )
        message = str(excinfo.value)
        assert "SemanticRegime" in message
        assert "relation_surface" in message
        assert "Do not invent a type" in message
