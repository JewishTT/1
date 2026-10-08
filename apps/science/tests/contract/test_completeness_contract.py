"""Contract: query intent, completeness modes, honesty over results (§32, §33, Appendix P).

§33.1: "The platform MUST NOT claim literal global completeness unless the source
universe and coverage model make that defensible." §33.2 gives three modes and
requires the UI to display which applies. Appendix P makes it a protocol: any query
whose wording implies universality must be checked, and if the conditions are unmet
the result is phrased internally as "observed candidates under declared coverage".

The load-bearing property is that the mode is **derived, not requested**. A caller
asking for ``EXACT_ENUMERATION`` without the conditions receives a downgrade with
the missing conditions named. Without that inversion, the default response to an
unreasonable request would be to honour it.

The second property is that "none exist" is only expressible when a
``CoverageQualifiedAbsence`` meets the §13A thresholds. Otherwise the answer is
"none observed under declared coverage" -- a much weaker claim, and the only one the
evidence supports.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from context.completeness import (
    UNIVERSAL_MARKERS,
    CompletenessMode,
    CompletenessRequirement,
    Objective,
    QueryIntent,
    RequestedMode,
    ResultSet,
    Target,
    TemporalMode,
    UniverseDefinition,
    assess_completeness,
    compile_intent,
    implies_universal,
)
from context.coverage import (
    CoverageQualifiedAbsence,
)

pytestmark = pytest.mark.contract

CTX = "CXI-test"

SATISFIED = {
    "catalogue_exhausted": True,
    "temporal_scope_defined": True,
    "identity_resolution_complete": True,
    "pagination_complete": True,
    "source_errors_zero_or_accounted": True,
}


def _absence(coverage, detection_power) -> CoverageQualifiedAbsence:
    return CoverageQualifiedAbsence(
        context_id=CTX,
        query="registry entry for SPV-77",
        sources=("reg-a", "reg-b", "reg-c"),
        coverage=coverage,
        detection_power=detection_power,
        relevance="predicts the SPV is registered",
    )


class TestThreeModes:
    def test_exactly_three_modes(self) -> None:
        assert len(list(CompletenessMode)) == 3

    def test_mode_names_match_the_spec(self) -> None:
        assert {mode.value for mode in CompletenessMode} == {
            "exact_enumeration",
            "known_universe_enumeration",
            "open_world_discovery",
        }

    def test_enumerable_universe_fully_scanned_yields_exact(self) -> None:
        requirement = assess_completeness(
            universe=UniverseDefinition.EXPLICITLY_ENUMERABLE, **SATISFIED
        )
        assert requirement.feasible_mode is CompletenessMode.EXACT_ENUMERATION

    def test_registered_universe_fully_exhausted_yields_known_universe(self) -> None:
        requirement = assess_completeness(
            universe=UniverseDefinition.REGISTERED_SOURCES, **SATISFIED
        )
        assert requirement.feasible_mode is CompletenessMode.KNOWN_UNIVERSE_ENUMERATION

    def test_available_sources_never_yield_exact(self) -> None:
        """An unenumerable universe cannot produce an exact enumeration."""
        requirement = assess_completeness(
            universe=UniverseDefinition.AVAILABLE_SOURCES, **SATISFIED
        )
        assert requirement.feasible_mode is CompletenessMode.OPEN_WORLD_DISCOVERY


class TestModeIsDerivedNotRequested:
    def test_a_universal_request_without_conditions_is_downgraded(self) -> None:
        requirement = assess_completeness(
            universe=UniverseDefinition.REGISTERED_SOURCES,
            requested_mode=RequestedMode.UNIVERSAL,
        )
        assert requirement.feasible_mode is CompletenessMode.OPEN_WORLD_DISCOVERY
        assert requirement.downgrade_reason

    def test_the_downgrade_names_the_unmet_conditions(self) -> None:
        requirement = assess_completeness(
            universe=UniverseDefinition.REGISTERED_SOURCES,
            catalogue_exhausted=True,
            requested_mode=RequestedMode.UNIVERSAL,
        )
        assert set(requirement.unmet) >= {"pagination_complete"}
        assert "pagination_complete" in requirement.downgrade_reason

    def test_five_conditions_are_reported(self) -> None:
        requirement = assess_completeness(universe=UniverseDefinition.REGISTERED_SOURCES)
        assert len(requirement.conditions) == 5

    def test_each_condition_explains_itself(self) -> None:
        requirement = assess_completeness(universe=UniverseDefinition.REGISTERED_SOURCES)
        assert all(condition.detail for condition in requirement.conditions)

    def test_unenumerable_universe_downgrades_even_when_all_conditions_hold(self) -> None:
        requirement = assess_completeness(
            universe=UniverseDefinition.AVAILABLE_SOURCES,
            requested_mode=RequestedMode.UNIVERSAL,
            **SATISFIED,
        )
        assert requirement.feasible_mode is CompletenessMode.OPEN_WORLD_DISCOVERY


class TestUniversalWording:
    @pytest.mark.parametrize(
        "question",
        [
            "найди всех крипто-китов",
            "find every wallet above 1M",
            "list all entities in the registry",
            "ничего не найдено",
            "нет ни одного кошелька",
        ],
    )
    def test_universal_wording_is_detected(self, question: str) -> None:
        assert implies_universal(question) is True
        assert compile_intent(question).requested_mode is RequestedMode.UNIVERSAL

    @pytest.mark.parametrize(
        "question",
        ["сколько кошельков у X", "ownership of ORG-1", "when was the SPV registered"],
    )
    def test_ordinary_wording_is_not_universal(self, question: str) -> None:
        assert implies_universal(question) is False
        assert compile_intent(question).requested_mode is RequestedMode.BEST_EFFORT

    def test_universal_wording_forbids_unresolved_members(self) -> None:
        assert compile_intent("find all whales").allow_unresolved is False

    def test_ordinary_wording_allows_unresolved_members(self) -> None:
        assert compile_intent("how many wallets does X hold").allow_unresolved is True

    def test_markers_cover_both_languages(self) -> None:
        assert "all" in UNIVERSAL_MARKERS
        assert "всех" in UNIVERSAL_MARKERS


class TestQueryIntent:
    def _intent(self, **kwargs) -> QueryIntent:
        defaults = {
            "objective": Objective.IDENTIFY_COHORT,
            "target": Target(
                "wallet_control_cluster", "aggregate_asset_value", 1_000_000, "USD"
            ),
            "question": "find all whales above 1M",
        }
        defaults.update(kwargs)
        return QueryIntent(**defaults)

    def test_target_must_name_a_subject_class(self) -> None:
        with pytest.raises(ValueError):
            Target(subject_class="")

    def test_universal_negative_cannot_allow_unresolved(self) -> None:
        with pytest.raises(ValueError) as excinfo:
            self._intent(objective=Objective.UNIVERSAL_NEGATIVE, allow_unresolved=True)
        assert "contradict" in str(excinfo.value)

    def test_universal_negative_without_unresolved_is_allowed(self) -> None:
        intent = self._intent(
            objective=Objective.UNIVERSAL_NEGATIVE, allow_unresolved=False
        )
        assert intent.objective is Objective.UNIVERSAL_NEGATIVE

    def test_intent_id_is_content_addressed(self) -> None:
        assert self._intent().intent_id.startswith("QIN-")
        assert self._intent().intent_id == self._intent().intent_id

    def test_serialises_the_section_32_1_fields(self) -> None:
        payload = self._intent().as_dict()
        for field in (
            "objective",
            "target",
            "temporal_scope",
            "identity_requirement",
            "evidence_requirement",
            "saturation",
            "requested_mode",
        ):
            assert field in payload

    def test_temporal_scope_defaults_to_current(self) -> None:
        assert self._intent().temporal_scope is TemporalMode.CURRENT


class TestResultSetHonesty:
    def test_a_result_must_name_its_universe(self) -> None:
        with pytest.raises(ValueError):
            ResultSet(candidate_set=())

    def test_an_item_cannot_be_both_resolved_and_unresolved(self) -> None:
        with pytest.raises(ValueError):
            ResultSet(
                candidate_set=("E1",),
                resolved_set=("E1",),
                unresolved_set=("E1",),
                source_universe="registered",
            )

    def test_every_resolved_item_must_be_a_candidate(self) -> None:
        with pytest.raises(ValueError):
            ResultSet(candidate_set=(), resolved_set=("E1",), source_universe="registered")

    def test_coverage_outside_the_unit_interval_is_refused(self) -> None:
        with pytest.raises(ValueError):
            ResultSet(candidate_set=(), source_universe="u", coverage_estimate=1.5)

    def test_unresolved_items_stay_in_the_candidate_set(self) -> None:
        """Dropping an unresolved candidate is the §0.2 violation in set form."""
        result = ResultSet(
            candidate_set=("E1", "E2"),
            resolved_set=("E1",),
            unresolved_set=("E2",),
            source_universe="registered",
        )
        assert "E2" in result.candidate_set


class TestUniversalNegative:
    """Appendix P.2: 'none exist' only under a qualifying absence."""

    def test_a_qualifying_absence_permits_the_strong_claim(self) -> None:
        result = ResultSet(
            candidate_set=(),
            source_universe="registered chain sources",
            qualified_absences=(_absence(0.95, 0.8),),
        )
        assert result.may_claim_universal_negative() is True

    def test_an_absence_with_unknown_coverage_does_not(self) -> None:
        result = ResultSet(
            candidate_set=(),
            source_universe="registered",
            qualified_absences=(_absence(None, 0.8),),
        )
        assert result.may_claim_universal_negative() is False
        assert result.phrasing() == "none observed under declared coverage"

    def test_an_absence_with_unknown_detection_power_does_not(self) -> None:
        result = ResultSet(
            candidate_set=(),
            source_universe="registered",
            qualified_absences=(_absence(0.95, None),),
        )
        assert result.may_claim_universal_negative() is False

    def test_no_absence_means_nothing_searched(self) -> None:
        result = ResultSet(candidate_set=(), source_universe="registered")
        assert result.may_claim_universal_negative() is False
        assert result.phrasing() == "nothing searched yet"

    def test_the_strong_claim_is_phrased_as_an_absence(self) -> None:
        result = ResultSet(
            candidate_set=(),
            source_universe="registered chain sources",
            qualified_absences=(_absence(0.95, 0.8),),
        )
        assert "no registered chain sources candidate" in result.phrasing()

    def test_partial_results_are_phrased_under_declared_coverage(self) -> None:
        result = ResultSet(
            candidate_set=("E1", "E2", "E3"),
            resolved_set=("E1", "E2"),
            unresolved_set=("E3",),
            source_universe="registered",
            coverage_estimate=0.9,
            known_blind_spots=("off-chain",),
        )
        phrasing = result.phrasing()
        assert "2 resolved" in phrasing
        assert "1 unresolved" in phrasing
        assert "declared coverage" in phrasing


class TestBanner:
    """§33.2: the UI must display which mode applies."""

    def test_banner_always_carries_a_mode(self) -> None:
        result = ResultSet(candidate_set=(), source_universe="registered")
        assert result.banner()["completeness_mode"] == "open_world_discovery"

    def test_banner_carries_the_downgrade_reason(self) -> None:
        requirement = assess_completeness(
            universe=UniverseDefinition.REGISTERED_SOURCES,
            requested_mode=RequestedMode.UNIVERSAL,
        )
        result = ResultSet(
            candidate_set=(), source_universe="registered", completeness=requirement
        )
        assert result.banner()["downgrade_reason"]
        assert result.banner()["unmet_conditions"]

    def test_banner_reports_the_negative_claim_permission(self) -> None:
        result = ResultSet(
            candidate_set=(), source_universe="registered",
            qualified_absences=(_absence(0.95, 0.8),),
        )
        assert result.banner()["may_claim_universal_negative"] is True

    def test_serialised_result_carries_the_banner(self) -> None:
        result = ResultSet(candidate_set=("E1",), resolved_set=("E1",), source_universe="u")
        assert "banner" in result.as_dict()

    def test_completeness_requirement_is_immutable_but_serialisable(self) -> None:
        requirement = assess_completeness(universe=UniverseDefinition.REGISTERED_SOURCES)
        assert isinstance(requirement, CompletenessRequirement)
        assert "feasible_mode" in requirement.as_dict()