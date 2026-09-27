"""I-1 and I-3: observation is immutable, and a finding is never a deletion.

The two oldest promises in the platform, and the two most often broken by accident.

**I-1 — an observation is immutable.** Not "should not be updated": *cannot*. The mechanism
is frozen dataclasses and content addresses, and the test checks both halves. The reason it
matters is that an observation is the only account of what was actually seen. If a later
step can rewrite one, then every claim resting on it is resting on something that was
edited after the fact by a process with no record of the edit, and "what did the platform
see" becomes unanswerable.

**I-3 — a finding is a finding, not a deletion.** The tempting shortcut everywhere in an
extraction pipeline is to drop the thing that caused a problem: the contradicted candidate,
the signal that could not be attributed, the row whose type is not in the vocabulary. Each
of those is a *finding about the world*, and dropping it converts "we looked and found
something odd" into "we looked and found nothing" — which is a false report about the
document, and the most consequential kind this platform makes.

The three types checked here - candidate, signal, temporal observation - are the three that
019 made durable, and each carries a ``content_key``/``observation_id`` that is derived from
its own contents and *refuses* a mismatch. That refusal is the mechanism: an address is not
a label somebody set, it is a function of the value, so a rewritten value cannot keep the
old address.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime

import pytest
from extractors.signals import Neighbourhood, RelationSignal, SignalKind

from domain.capture import CaptureTimeBasis
from domain.predicate_hypothesis import PredicateHypothesis
from domain.relation_candidate import (
    CandidateStatus,
    RelationCandidate,
    TemporalHypothesis,
)
from domain.temporal_observation import (
    SourceTemporalObservation,
    TemporalAxis,
    TemporalObservationContractError,
    TemporalPrecision,
)
from semantic.contracts import RelationRef

UTC = UTC


def _candidate(**over) -> RelationCandidate:
    base = {
        "subject_mention_ref": "MN-A",
        "object_mention_ref": "MN-B",
        "relation_ref": RelationRef("works_for"),
        "relation_surface": "CEO of",
        "context_ref": "CX-1",
        "semantic_regime_ref": "RG-1",
        "tenant_id": "T1",
        "temporal_hypothesis": TemporalHypothesis.absent(),
    }
    return RelationCandidate(**{**base, **over}).with_id()


def _signal(**over) -> RelationSignal:
    base = {
        "subject_mention_ref": "MN-A",
        "object_mention_ref": "MN-B",
        "kind": SignalKind.LEXICAL,
        "relation_surface": "CEO of",
        "neighbourhood": Neighbourhood(
            characters_scanned=40, pairs_considered=0, scope_read="one sentence"
        ),
        "context_ref": "CX-1",
        "semantic_regime_ref": "RG-1",
        "tenant_id": "T1",
    }
    return RelationSignal(**{**base, **over})


def _observation(**over) -> SourceTemporalObservation:
    base = {
        "temporal_axis": TemporalAxis.PUBLISHED_AT,
        "capture_ref": "CAP-1",
        "stated_value": datetime(2024, 3, 15, tzinfo=UTC),
        "raw_value": "20240315",
        "precision": TemporalPrecision.DAY,
        "basis": CaptureTimeBasis.PUBLICATION,
        "evidence_location": "date filed",
        "tenant_id": "T1",
    }
    return SourceTemporalObservation(**{**base, **over})


class TestObservationsAreImmutable:
    @pytest.mark.parametrize(
        "value",
        [
            pytest.param(_candidate(), id="candidate"),
            pytest.param(_signal(), id="signal"),
            pytest.param(_observation(), id="temporal-observation"),
            pytest.param(PredicateHypothesis(relation_ref=RelationRef("owns")), id="predicate"),
        ],
    )
    def test_assignment_raises_rather_than_altering_the_record(self, value) -> None:
        """The half of I-1 that is actually a mechanism rather than a convention."""
        assert dataclasses.is_dataclass(value)
        with pytest.raises(dataclasses.FrozenInstanceError):
            value.tenant_id = "someone-else"  # type: ignore[misc]

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param(_candidate(), id="candidate"),
            pytest.param(_signal(), id="signal"),
            pytest.param(_observation(), id="temporal-observation"),
        ],
    )
    def test_the_address_is_derived_not_carried(self, value) -> None:
        """A content address is a function of the value, so it cannot be inherited.

        The failure this defends against: a record is edited, keeps its id, and every
        reference to that id now points at something nobody recorded.

        The rebuild strips every address field the type has and re-derives them, so this
        fails if any id is anything other than a function of the remaining fields. It needs
        ``with_id()`` because derivation is explicit on this platform - construction does
        not compute an address it was not given.
        """
        address_names = (
            "candidate_id", "logical_candidate_id", "signal_id", "observation_id",
        )
        addresses = [
            f.name for f in dataclasses.fields(value) if f.name in address_names
        ]
        assert addresses, f"{type(value).__name__} has no address field to check"
        stripped = {
            f.name: getattr(value, f.name)
            for f in dataclasses.fields(value)
            if f.name not in addresses
        }
        rebuilt = type(value)(**stripped)
        if hasattr(rebuilt, "with_id"):
            rebuilt = rebuilt.with_id()
        for name in addresses:
            assert getattr(value, name) == getattr(rebuilt, name), (
                f"{type(value).__name__}.{name} is not a function of its contents"
            )

    def test_a_carried_address_that_disagrees_is_refused(self) -> None:
        """The check that makes the address load-bearing rather than decorative.

        Written for the three types 019 made durable, because the property is only a
        property if every type keeps it the same way. Two of the three already refused -
        ``RelationClaimMaterial``, ``SemanticRegime`` and
        ``SourceTemporalObservation`` all did - and :class:`RelationCandidate` accepted a
        forged ``candidate_id`` silently. This is the test that caught it.
        """
        zero = "0" * 32
        for value, field_name, forged in (
            (_candidate(), "candidate_id", f"CNDR-{zero}"),
            (_signal(), "signal_id", f"SIG-{zero}"),
            (_observation(), "observation_id", f"STO-{zero}"),
        ):
            fields = {
                f.name: getattr(value, f.name) for f in dataclasses.fields(value)
            }
            fields[field_name] = forged
            with pytest.raises(Exception) as excinfo:
                type(value)(**fields)
            assert "mismatch" in str(excinfo.value), (
                f"{type(value).__name__} accepted a forged {field_name}: {excinfo.value}"
            )

    def test_a_frozen_record_cannot_be_edited_in_place_either(self) -> None:
        """Belt and braces: the field cannot be reassigned, and it cannot be forged."""
        value = _candidate()
        with pytest.raises(dataclasses.FrozenInstanceError):
            value.relation_surface = "something else"  # type: ignore[misc]
        assert value.relation_surface == "CEO of"


class TestFindingsAreNeverDeletions:
    def test_a_contradicted_candidate_is_still_a_candidate(self) -> None:
        """Not deleted, not refused at construction - preserved, and readable."""
        contradicted = _candidate(candidate_status=CandidateStatus.CONTRADICTED)
        assert contradicted.candidate_id
        assert contradicted.candidate_status is CandidateStatus.CONTRADICTED
        assert contradicted.subject_mention_ref == "MN-A"

    def test_a_rejected_candidate_keeps_its_address_relationship(self) -> None:
        """One hypothesis, several dispositions - the logical id is shared, not re-minted.

        The failure this defends against is the one that makes I-3 unkeepable: if a rejection
        re-addressed the hypothesis, there would be no way to ask "what did we make of this?"
        and the rejection would be indistinguishable from never having considered it.
        """
        proposed = _candidate(candidate_status=CandidateStatus.PROPOSE)
        rejected = _candidate(candidate_status=CandidateStatus.REJECTED)
        assert proposed.logical_candidate_id == rejected.logical_candidate_id
        assert proposed.candidate_id != rejected.candidate_id

    def test_a_signal_the_platform_cannot_type_is_still_stored(self) -> None:
        """The CD-6/CD-7 case: no operator, and the words are kept anyway."""
        untyped = _signal(kind=SignalKind.TABLE, relation_surface="CEO", relation_ref=None)
        assert untyped.signal_id
        assert untyped.relation_surface == "CEO"
        assert untyped.relation_ref is None

    def test_a_conflicting_temporal_fact_is_refused_rather_than_overwritten(self) -> None:
        """Two readings of one axis are a conflict to report, not a last-one-wins."""
        from domain.temporal_observation import observations_by_axis

        first = _observation()
        second = _observation(stated_value=datetime(2024, 6, 1, tzinfo=UTC), raw_value="20240601")
        with pytest.raises(TemporalObservationContractError) as excinfo:
            observations_by_axis([first, second])
        assert excinfo.value.code == "conflicting_temporal_observation"
        # Both survive as values: the refusal is about the *merge*, not about the records.
        assert first.stated_value != second.stated_value
        assert first.observation_id and second.observation_id

    def test_the_same_reading_twice_is_one_reading_not_two(self) -> None:
        """Idempotence, and it is what makes a replay safe (I-11's cousin)."""
        assert _signal().signal_id == _signal().signal_id
        assert _candidate().candidate_id == _candidate().candidate_id
        assert _observation().observation_id == _observation().observation_id
