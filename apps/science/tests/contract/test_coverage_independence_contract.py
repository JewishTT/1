"""Contract: evidence independence, coverage-qualified absence, saturation.

§14A opens with the reason this exists: "Source count is not source independence,
and correlated evidence double-counts." Five hundred outlets republishing one
press release are one observation, and a confidence figure computed from the raw
count is wrong by two and a half orders of magnitude.

Four rules from §14A.2 are enforced rather than documented, and each is pinned
here:

1. update rules consume groups, never items -- within a group the contribution is
   ``max``, not a sum;
2. ``n_eff`` is reported **next to** the raw count, never instead of it;
3. undeterminable dependence collapses to one group and records
   ``INDEPENDENCE_UNKNOWN`` -- the conservative direction, because "maybe one
   source" is the safe reading when lineage is unknown;
4. ``truth_state`` flags are **unaffected** by grouping.

§13A is the mirror: unknown detection power is ``INFORMATIONAL_ONLY`` always, and
a non-search is not an object of this type at all.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from context.coverage import (
    AbsenceAdmissibility,
    CorrelationModel,
    CoverageQualifiedAbsence,
    CoverageThresholds,
    EvidenceDependencyGroup,
    SaturationReason,
    SaturationState,
    SaturationVerdict,
    assess_independence,
    assess_saturation,
    group_contribution,
    independence_obstruction,
)

pytestmark = pytest.mark.contract

CTX = "CXI-test"
SOURCES = ("archive.org", "reuters", "gov-registry")


class TestIndependence:
    def test_syndication_collapses_to_one(self) -> None:
        """The headline: 500 items, one underlying observation."""
        items = [f"EV-{index}" for index in range(500)]
        lineage = {item: "OBS-press-release-1" for item in items}
        assessment = assess_independence(items, lineage)
        assert assessment.raw_count == 500
        assert assessment.n_eff == 1.0

    def test_genuinely_independent_sources_are_not_collapsed(self) -> None:
        items = [f"EV-{index}" for index in range(5)]
        lineage = {f"EV-{index}": f"OBS-{index}" for index in range(5)}
        assessment = assess_independence(items, lineage)
        assert assessment.n_eff == 5.0
        assert assessment.independence_known is True

    def test_unknown_lineage_collapses_and_records_the_reason(self) -> None:
        """§14A.2 rule 3."""
        assessment = assess_independence(
            ["EV-a", "EV-b", "EV-c"], {"EV-a": "OBS-1", "EV-b": "OBS-1"}
        )
        assert assessment.independence_known is False
        assert assessment.n_eff < assessment.raw_count
        assert "INDEPENDENCE_UNKNOWN" in assessment.obstruction

    def test_unknown_lineage_produces_a_recorded_obstruction(self) -> None:
        assessment = assess_independence(["EV-a"], {})
        obstruction = independence_obstruction(assessment)
        assert obstruction is not None
        assert obstruction.detail

    def test_known_lineage_produces_no_obstruction(self) -> None:
        assessment = assess_independence(["EV-a"], {"EV-a": "OBS-1"})
        assert independence_obstruction(assessment) is None

    def test_empty_evidence_is_empty_not_one(self) -> None:
        assessment = assess_independence([], {})
        assert assessment.raw_count == 0
        assert assessment.n_eff == 0.0

    def test_n_eff_is_shown_next_to_the_raw_count(self) -> None:
        """Rule 2: computing n_eff and displaying the raw count gains nothing."""
        assessment = assess_independence(["a", "b"], {"a": "O1", "b": "O2"})
        display = assessment.as_display()
        assert "2" in display
        assert "of 2 items" in display

    def test_uncertainty_is_shown_in_the_display(self) -> None:
        assessment = assess_independence(["a"], {})
        assert "independence unknown" in assessment.as_display()

    def test_grouping_does_not_change_support_existence(self) -> None:
        """Rule 4: grouping changes scores, not whether support exists."""
        from context.epistemic import EvidenceContribution, TruthState, derive_truth_state

        items = [
            EvidenceContribution("EV-a", positive=True),
            EvidenceContribution("EV-b", positive=True),
        ]
        assert derive_truth_state(items) is TruthState.TRUE_ONLY

    def test_within_a_group_the_best_contribution_wins(self) -> None:
        """Rule 1: a group cannot make itself stronger by repeating."""
        assessment = assess_independence(
            ["E1", "E2", "E3", "E4", "E5"],
            {"E1": "OBS-p", "E2": "OBS-p", "E3": "OBS-p", "E4": "OBS-q", "E5": "OBS-q"},
        )
        contribution = group_contribution(assessment)
        assert contribution["combined"] == 2.0
        assert assessment.raw_count == 5

    def test_serialises_for_display(self) -> None:
        assessment = assess_independence(["a", "b"], {"a": "O1", "b": "O1"})
        payload = assessment.as_dict()
        assert payload["raw_count"] == 2
        assert payload["effective_independent_sources"] == 1.0
        assert payload["group_count"] == 1


class TestDependencyGroup:
    def test_id_is_content_addressed(self) -> None:
        group = EvidenceDependencyGroup(members=("a", "b"), basis=())
        assert group.group_id.startswith("EDG-")
        assert group.group_id == group.address()

    def test_identical_groups_address_identically(self) -> None:
        left = EvidenceDependencyGroup(members=("a", "b"), basis=())
        right = EvidenceDependencyGroup(members=("b", "a"), basis=())
        assert left.group_id == right.group_id

    def test_an_empty_group_constrains_nothing(self) -> None:
        with pytest.raises(ValueError):
            EvidenceDependencyGroup(members=(), basis=())

    def test_duplicate_members_are_refused(self) -> None:
        with pytest.raises(ValueError):
            EvidenceDependencyGroup(members=("a", "a"), basis=())

    def test_a_zero_discount_is_refused(self) -> None:
        """Zero means 'contributes nothing', which is a different claim."""
        with pytest.raises(ValueError):
            EvidenceDependencyGroup(members=("a",), basis=(), discount=0.0)

    def test_a_discount_above_one_is_refused(self) -> None:
        with pytest.raises(ValueError):
            EvidenceDependencyGroup(members=("a",), basis=(), discount=1.5)

    def test_correlation_model_defaults_to_max_only(self) -> None:
        group = EvidenceDependencyGroup(members=("a",), basis=())
        assert group.correlation_model is CorrelationModel.MAX_ONLY


class TestCoverageQualifiedAbsence:
    def _absence(self, **kwargs):
        return CoverageQualifiedAbsence(
            context_id=CTX,
            query="registry entry for SPV-77",
            sources=SOURCES,
            relevance="predicts the SPV is registered",
            **kwargs,
        )

    def test_full_coverage_admits_negative_evidence(self) -> None:
        absence = self._absence(coverage=0.95, detection_power=0.8)
        assert absence.admissibility is AbsenceAdmissibility.NEGATIVE_EVIDENCE
        assert absence.contributes_negative_support is True

    def test_unknown_coverage_is_informational_only(self) -> None:
        absence = self._absence(coverage=None, detection_power=0.8)
        assert absence.admissibility is AbsenceAdmissibility.INFORMATIONAL_ONLY
        assert absence.contributes_negative_support is False

    def test_unknown_detection_power_is_always_informational_only(self) -> None:
        """§13A: "Unknown detection power implies INFORMATIONAL_ONLY, always"."""
        absence = self._absence(coverage=0.99, detection_power=None)
        assert absence.admissibility is AbsenceAdmissibility.INFORMATIONAL_ONLY

    def test_low_coverage_below_threshold_is_informational_only(self) -> None:
        absence = self._absence(coverage=0.3, detection_power=0.95)
        assert absence.admissibility is AbsenceAdmissibility.INFORMATIONAL_ONLY

    def test_low_detection_power_below_threshold_is_informational_only(self) -> None:
        absence = self._absence(coverage=0.95, detection_power=0.1)
        assert absence.admissibility is AbsenceAdmissibility.INFORMATIONAL_ONLY

    def test_unaccounted_source_errors_block_admission(self) -> None:
        absence = self._absence(coverage=0.95, detection_power=0.95, errors_accounted=False)
        assert absence.admissibility is AbsenceAdmissibility.INFORMATIONAL_ONLY

    def test_a_non_search_is_not_an_absence(self) -> None:
        """§13A: 'not searched' never contributes, and has no such object."""
        with pytest.raises(ValueError) as excinfo:
            CoverageQualifiedAbsence(context_id=CTX, query="x", sources=(), relevance="r")
        assert "non-search" in str(excinfo.value)

    def test_absence_must_name_a_query(self) -> None:
        with pytest.raises(ValueError):
            CoverageQualifiedAbsence(context_id=CTX, query="", sources=SOURCES, relevance="r")

    def test_absence_must_be_relevant_to_a_falsifiable_prediction(self) -> None:
        with pytest.raises(ValueError) as excinfo:
            CoverageQualifiedAbsence(context_id=CTX, query="x", sources=SOURCES, relevance="")
        assert "falsifiable" in str(excinfo.value)

    def test_out_of_range_coverage_is_refused(self) -> None:
        with pytest.raises(ValueError):
            self._absence(coverage=1.5, detection_power=0.5)

    def test_thresholds_are_configurable_and_stricter_is_respected(self) -> None:
        strict = self._absence(coverage=0.85, detection_power=0.6)
        assert strict.admissibility is AbsenceAdmissibility.NEGATIVE_EVIDENCE
        stricter = CoverageQualifiedAbsence(
            context_id=CTX,
            query="q",
            sources=SOURCES,
            coverage=0.85,
            detection_power=0.6,
            relevance="r",
            thresholds=CoverageThresholds(min_coverage=0.95),
        )
        assert stricter.admissibility is AbsenceAdmissibility.INFORMATIONAL_ONLY

    def test_id_is_content_addressed(self) -> None:
        assert self._absence(coverage=0.9, detection_power=0.9).absence_id.startswith("CQA-")


class TestSaturation:
    def _good(self):
        return assess_independence(["a", "b", "c"], {"a": "O1", "b": "O2", "c": "O3"})

    def test_saturation_requires_reasons(self) -> None:
        """§22.1: saturation is not 'we searched a lot'."""
        with pytest.raises(ValueError) as excinfo:
            SaturationState(
                obligation_id="OBL-1", verdict=SaturationVerdict.SATURATED
            )
        assert "reason codes" in str(excinfo.value)

    def test_saturated_requires_reasons_even_with_reasons(self) -> None:
        state = SaturationState(
            obligation_id="OBL-1",
            verdict=SaturationVerdict.SATURATED,
            reason_codes=(SaturationReason.INSUFFICIENT_COVERAGE,),
        )
        assert state.reason_codes

    def test_coverage_and_n_eff_and_families_saturate(self) -> None:
        state = assess_saturation(
            "OBL-1",
            assessment=self._good(),
            coverage=0.95,
            source_families=4,
            marginal_gain=0.01,
        )
        assert state.verdict is SaturationVerdict.SATURATED

    def test_low_coverage_blocks_saturation_with_a_reason(self) -> None:
        state = assess_saturation(
            "OBL-1",
            assessment=self._good(),
            coverage=0.2,
            source_families=4,
            marginal_gain=0.01,
        )
        assert state.verdict is SaturationVerdict.UNSATURATED
        assert SaturationReason.INSUFFICIENT_COVERAGE in state.reason_codes

    def test_syndication_blocks_saturation_despite_a_high_raw_count(self) -> None:
        """A syndication cluster is not coverage, however many items it has."""
        items = [f"EV-{index}" for index in range(50)]
        assessment = assess_independence(items, {item: "OBS-p" for item in items})
        state = assess_saturation(
            "OBL-1",
            assessment=assessment,
            coverage=0.95,
            source_families=4,
            marginal_gain=0.01,
        )
        assert state.distinct_sources == 50
        assert state.effective_independent_sources == 1.0
        assert SaturationReason.INSUFFICIENT_INDEPENDENCE in state.reason_codes
        assert state.verdict is not SaturationVerdict.SATURATED

    def test_narrow_source_families_block_saturation(self) -> None:
        state = assess_saturation(
            "OBL-1", assessment=self._good(), coverage=0.95, source_families=1
        )
        assert SaturationReason.NARROW_SOURCE_FAMILIES in state.reason_codes

    def test_unexplored_capability_classes_block_saturation(self) -> None:
        state = assess_saturation(
            "OBL-1",
            assessment=self._good(),
            coverage=0.95,
            source_families=4,
            unexplored_capability_classes=("aircraft",),
        )
        assert SaturationReason.UNEXPLORED_CAPABILITY in state.reason_codes

    def test_unresolved_obstructions_block_the_obligation(self) -> None:
        state = assess_saturation(
            "OBL-1",
            assessment=self._good(),
            coverage=0.95,
            source_families=4,
            unresolved_obstruction_count=1,
        )
        assert state.verdict is SaturationVerdict.BLOCKED

    def test_unknown_coverage_is_named_as_unknown(self) -> None:
        state = assess_saturation(
            "OBL-1", assessment=self._good(), coverage=None, source_families=4
        )
        assert SaturationReason.UNKNOWN_INPUTS in state.reason_codes

    def test_raw_and_effective_counts_are_both_reported(self) -> None:
        state = assess_saturation(
            "OBL-1", assessment=self._good(), coverage=0.2, source_families=1
        )
        payload = state.as_dict()
        assert payload["distinct_sources"] == 3
        assert payload["effective_independent_sources"] == 3.0

    def test_claiming_independence_met_with_one_effective_source_is_refused(self) -> None:
        """A self-contradictory saturation must not be constructible."""
        with pytest.raises(ValueError):
            SaturationState(
                obligation_id="OBL-1",
                verdict=SaturationVerdict.SATURATED,
                reason_codes=(SaturationReason.INDEPENDENCE_MET,),
                distinct_sources=10,
                effective_independent_sources=1.0,
            )

    def test_saturated_names_the_conditions_it_met(self) -> None:
        """\"Done\" must say what was achieved, not just assert it."""
        state = assess_saturation(
            "OBL-1",
            assessment=self._good(),
            coverage=0.95,
            source_families=4,
            marginal_gain=0.01,
        )
        assert state.reason_codes
        assert SaturationReason.COVERAGE_MET in state.reason_codes
        assert SaturationReason.INDEPENDENCE_MET in state.reason_codes

    def test_declining_marginal_gain_supports_saturation(self) -> None:
        """A search that has stopped paying off is the definition of saturated."""
        state = assess_saturation(
            "OBL-1",
            assessment=self._good(),
            coverage=0.95,
            source_families=4,
            marginal_gain=0.001,
        )
        assert SaturationReason.MARGINAL_GAIN_DECLINED in state.reason_codes
        assert state.verdict is SaturationVerdict.SATURATED

    def test_a_gain_still_above_threshold_keeps_the_obligation_open(self) -> None:
        state = assess_saturation(
            "OBL-1",
            assessment=self._good(),
            coverage=0.95,
            source_families=4,
            marginal_gain=0.4,
        )
        assert SaturationReason.MARGINAL_GAIN_REMAINS in state.reason_codes
        assert state.verdict is SaturationVerdict.UNSATURATED
