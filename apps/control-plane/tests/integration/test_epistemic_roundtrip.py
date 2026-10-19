"""The thirteen epistemic states survive storage -> events -> API -> UI without collapse.

Spec 030 T065, T066 — US3, FR-010, FR-011, FR-012, FR-014, contract 03, contract 07 R4.

The user story's central claim is a claim about *transport*: that thirteen epistemic
states come out the other end of four layers still being thirteen states. That claim is
only testable if the four layers are real, so this file builds them rather than mocking
them:

* **storage** -- :func:`json_dumps` / :func:`json_loads` over the serialised record. A
  real persistence boundary, and the one that loses information quietly: a value that
  serialises to ``None`` and a value that is omitted read the same on the way back in.
* **events** -- the wire envelope each state travels in, built from the contract-03
  :class:`StageOutcome` and the contract-07 :class:`ErrorCode`.
* **API** -- the response dict a route would serialise, gated by contract 07 R4's
  :func:`coverage.assert_states_absence`.
* **UI** -- the projection a view renders, which is where a collapse becomes a lie a
  human reads.

The load-bearing assertion is not that a state survives but that **two distinct states
never become one value at any layer**. That is checked pairwise across all thirteen, at
every layer, which is why the file enumerates rather than spot-checks: a spot check
finds the collapse you thought of.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from context.completeness import (
    DegradedUniversalAnswer,
    LimitationKind,
    ResultSet,
    degrade_universal,
)
from context.coverage import BareEmptyResultError, assert_states_absence
from context.epistemic import (
    AbsenceAxis,
    Contradiction,
    ContradictionKind,
    EvidenceAxis,
    EvidenceContribution,
    Proposition,
    ResearchState,
    ResearchStateName,
    ResolutionHeuristic,
    SearchDisposition,
    TruthState,
    attempt_resolution,
)
from contracts.error_codes import EmptyStateEnvelope, ErrorCode, ErrorSurfaceError
from contracts.stage_outcome import (
    CoverageStatement,
    EpistemicState,
    ErrorClass,
    StageOutcome,
    StageStatus,
)

CORPUS = (
    Path(__file__).resolve().parents[4]
    / "bench"
    / "fixtures"
    / "global_upgrade"
    / "epistemic"
    / "cases.jsonl"
)

pytestmark = pytest.mark.integration

STATES = tuple(ResearchStateName)


# =============================================================================
# The four layers, built for real
# =============================================================================


def json_dumps(state: ResearchState) -> str:
    """Layer 1 -- storage. Canonical JSON, exactly as a column would hold it."""
    return json.dumps(state.as_dict(), sort_keys=True, separators=(",", ":"))


def json_loads(blob: str) -> ResearchState:
    return ResearchState.from_dict(json.loads(blob))


def build_outcome(state: ResearchState) -> StageOutcome:
    """Layer 2 -- the event wire form, from the contract-03 envelope.

    A ``no_result`` must carry the coverage statement that produced it, so the absence
    states below are the ones the contract already enforces rather than ones invented
    here: reusing them is the point, since a bespoke envelope would prove nothing about
    the real one.
    """
    if state.absence is AbsenceAxis.NOT_APPLICABLE:
        return StageOutcome(
            status=StageStatus.SUCCEEDED,
            new_independent_evidence=1 if state.truth_state is not TruthState.NEITHER else 0,
        )
    coverage = CoverageStatement(
        universe="fixture corpus",
        coverage="synthetic declared universe",
        residual=state.disposition.value,
        detection_power=state.detection_power,
    )
    error_class = (
        ErrorClass.EXPECTED_NO_RESULT
        if state.absence is AbsenceAxis.SEARCHED_NO_RESULT
        else ErrorClass.HUMAN_REVIEW_REQUIRED
    )
    return StageOutcome(status=StageStatus.NO_RESULT, error_class=error_class, coverage=coverage)


def build_event(state: ResearchState) -> dict[str, Any]:
    """The published event body."""
    outcome = build_outcome(state)
    return {
        "event_type": "epistemic.state.recorded",
        "payload": {
            "research_state": json.loads(json_dumps(state)),
            "outcome": outcome.as_dict(),
            "epistemic_state": (
                str(outcome.epistemic_state) if outcome.epistemic_state is not None else None
            ),
            "error_code": (
                str(outcome.error_code) if outcome.error_code is not None else None
            ),
            "may_claim_absence": state.may_claim_absence,
        },
    }


def build_api_response(state: ResearchState) -> dict[str, Any]:
    """Layer 3 -- what a route would return, gated by contract 07 R4."""
    response: dict[str, Any] = {
        "items": [],
        "status": state.disposition.value,
        "coverage": state.query.value,
        "provenance": "synthetic fixture, licence=synthetic",
        "limitations": list(state.limitations) or ["no further limitation recorded"],
        "state": json.loads(json_dumps(state)),
    }
    return assert_states_absence(response)


def build_ui_projection(state: ResearchState) -> dict[str, Any]:
    """Layer 4 -- what a reader is shown. A collapse here is a lie a human reads."""
    return {
        "headline": _headline(state),
        "badge": state.absence.value,
        "detail_rows": [
            ("search", state.disposition.value),
            ("query", state.query.value),
            ("support", state.truth_state.value),
            ("evidence", state.evidence.value),
            ("scope", state.scope.value),
        ],
        "limitations": list(state.limitations),
        "claimable": state.may_claim_absence,
    }


def _headline(state: ResearchState) -> str:
    if state.absence is AbsenceAxis.QUALIFIED_ABSENCE:
        return "No candidate satisfies the query within the declared universe"
    if state.absence is AbsenceAxis.INFORMATIONAL_ONLY:
        return "Nothing found under the stated coverage — not a claim of absence"
    if state.absence is AbsenceAxis.SEARCHED_NO_RESULT:
        return "Searched; no result"
    if state.truth_state is TruthState.BOTH:
        return "Sources disagree — both readings are held"
    if state.truth_state is TruthState.TRUE_ONLY:
        return "Supported"
    if state.truth_state is TruthState.FALSE_ONLY:
        return (
            "Refuted" if state.evidence is EvidenceAxis.REFUTED else "Evidence leans negative"
        )
    if state.disposition is SearchDisposition.NOT_INVESTIGATED:
        return "Not investigated"
    if state.disposition is SearchDisposition.UNREPRESENTABLE:
        return "This query is not representable here"
    if state.disposition is SearchDisposition.FAILED:
        return "The source did not respond — nothing was searched"
    return "Inconclusive"


def _anchor(name: ResearchStateName) -> ResearchState:
    return ResearchState.for_name(
        name, detection_power=1.0 if name is ResearchStateName.QUALIFIED_ABSENCE else None
    )


ALL_STATES: tuple[ResearchState, ...] = tuple(_anchor(name) for name in STATES)


# =============================================================================
# T065 -- thirteen states, four layers, no collapse
# =============================================================================


class TestRoundTrip:
    def test_there_are_thirteen(self) -> None:
        assert len(ALL_STATES) == 13

    @pytest.mark.parametrize("state", ALL_STATES, ids=[str(s) for s in STATES])
    def test_storage_round_trips_the_fingerprint(self, state: ResearchState) -> None:
        assert json_loads(json_dumps(state)).fingerprint == state.fingerprint

    @pytest.mark.parametrize("state", ALL_STATES, ids=[str(s) for s in STATES])
    def test_the_event_layer_carries_the_same_state(self, state: ResearchState) -> None:
        assert build_event(state)["payload"]["research_state"] == json.loads(
            json_dumps(state)
        )

    @pytest.mark.parametrize("state", ALL_STATES, ids=[str(s) for s in STATES])
    def test_the_api_layer_never_returns_a_bare_list(self, state: ResearchState) -> None:
        response = build_api_response(state)
        assert response != []
        assert set(response) >= {"items", "status", "coverage", "provenance", "limitations"}
        assert all(response[key] not in (None, "", [], {}) for key in
                   ("status", "coverage", "provenance", "limitations"))

    @pytest.mark.parametrize("state", ALL_STATES, ids=[str(s) for s in STATES])
    def test_the_ui_projection_still_says_which_state_it_is(
        self, state: ResearchState
    ) -> None:
        projection = build_ui_projection(state)
        assert projection["badge"] == state.absence.value
        assert dict(projection["detail_rows"]) == {
            "search": state.disposition.value,
            "query": state.query.value,
            "support": state.truth_state.value,
            "evidence": state.evidence.value,
            "scope": state.scope.value,
        }

    def test_no_two_states_collapse_at_any_layer(self) -> None:
        """The whole of T065: pairwise distinctness, at every one of the four layers.

        Checked at storage, event, API and UI separately rather than once end-to-end,
        because a collapse at any single layer is invisible from the outside: the record
        can come out the other end looking fine while having passed through a state that
        could not be told apart from another.
        """
        layers = {
            "storage": lambda s: json_loads(json_dumps(s)).fingerprint,
            "event": lambda s: json.dumps(
                build_event(s)["payload"]["research_state"], sort_keys=True
            ),
            "api": lambda s: json.dumps(build_api_response(s), sort_keys=True),
            "ui": lambda s: json.dumps(
                build_ui_projection(s), sort_keys=True, default=str
            ),
        }
        for layer, key in layers.items():
            seen: dict[Any, ResearchStateName] = {}
            for name, state in zip(STATES, ALL_STATES, strict=True):
                value = key(state)
                assert value not in seen, (
                    f"{name} and {seen.get(value)} are indistinguishable at the {layer} "
                    "layer; two distinct epistemic facts reached the same value"
                )
                seen[value] = name
            assert len(seen) == 13, f"{layer} layer collapsed thirteen states to {len(seen)}"

    def test_the_ui_headline_never_claims_an_absence_it_cannot_support(self) -> None:
        for state in ALL_STATES:
            headline = build_ui_projection(state)["headline"]
            if "No candidate satisfies" in headline:
                assert state.may_claim_absence, (
                    f"{state.fingerprint} rendered the qualified-absence headline without a "
                    "declared detection power"
                )

    def test_a_state_read_back_twice_is_stable(self) -> None:
        """Idempotence. A second storage round must not drift, or replay diverges."""
        for state in ALL_STATES:
            once = json_loads(json_dumps(state))
            twice = json_loads(json_dumps(once))
            assert twice.fingerprint == once.fingerprint
            assert json_dumps(once) == json_dumps(twice)


# =============================================================================
# T066 -- undeclared detection power is INFORMATIONAL_ONLY, never QUALIFIED_ABSENCE
# =============================================================================


class TestDetectionPowerNeverCollapses:
    def test_contract_03_splits_a_no_result_on_the_declared_power(self) -> None:
        """The contract already draws the line; this pins it so it cannot be undone."""
        unknown = CoverageStatement(
            universe="u", coverage="c", detection_power=None
        ).epistemic_state
        declared = CoverageStatement(
            universe="u", coverage="c", detection_power=0.94
        ).epistemic_state
        assert unknown is EpistemicState.INFORMATIONAL_ONLY
        assert declared is EpistemicState.QUALIFIED_ABSENCE
        assert unknown is not declared

    def test_the_undeclared_case_is_a_release_blocker_code(self) -> None:
        assert ErrorCode.DETECTION_POWER_UNKNOWN.is_release_blocker
        assert ErrorCode.DETECTION_POWER_UNKNOWN.category.value == "expected_negative"

    def test_the_undeclared_case_never_reaches_the_api_as_an_absence(self) -> None:
        state = ResearchState.resolve(query_executed=True, detection_power=None, coverage_estimate=0.99)
        assert state.absence is AbsenceAxis.INFORMATIONAL_ONLY
        assert state.may_claim_absence is False
        response = build_api_response(state)
        assert response["state"]["absence"] == "informational_only"
        assert response["state"]["detection_power"] is None
        assert "not a claim of absence" in build_ui_projection(state)["headline"]

    def test_the_declared_case_does_reach_it(self) -> None:
        state = ResearchState.resolve(
            query_executed=True,
            detection_power=0.94,
            coverage_estimate=0.96,
            universe_declared=True,
            freshness_declared=True,
        )
        assert state.absence is AbsenceAxis.QUALIFIED_ABSENCE
        assert state.may_claim_absence is True
        assert "No candidate satisfies" in build_ui_projection(state)["headline"]

    def test_an_empty_result_set_is_never_returned_bare(self) -> None:
        """Contract 07 R4, exercised rather than restated.

        ``EmptyStateEnvelope`` refuses to be constructed without status, coverage,
        provenance and limitations; ``assert_states_absence`` is the gate on the response
        side. Both directions are checked because R4's failure mode is a field that is
        present and empty, which a presence check alone would pass.
        """
        envelope = EmptyStateEnvelope(
            status=ErrorCode.DETECTION_POWER_UNKNOWN,
            coverage="synthetic declared universe",
            provenance="synthetic fixture, licence=synthetic",
            limitations=("detection_power not declared",),
        )
        wire = envelope.as_wire()
        assert wire["status"] == "DETECTION_POWER_UNKNOWN"
        assert wire["limitations"]
        with pytest.raises(ErrorSurfaceError, match="coverage"):
            EmptyStateEnvelope(
                status=ErrorCode.DETECTION_POWER_UNKNOWN,
                coverage="",
                provenance="p",
                limitations=(),
            )

    def test_a_coverage_free_response_is_refused_even_when_it_has_items(self) -> None:
        with pytest.raises(BareEmptyResultError, match="coverage"):
            assert_states_absence(
                {
                    "items": ["something"],
                    "status": "completed",
                    "coverage": None,
                    "provenance": "p",
                    "limitations": ["l"],
                }
            )

    def test_an_empty_limitations_list_is_refused(self) -> None:
        with pytest.raises(BareEmptyResultError, match="limitations"):
            assert_states_absence(
                {
                    "items": [],
                    "status": "no_result",
                    "coverage": "c",
                    "provenance": "p",
                    "limitations": [],
                }
            )


# =============================================================================
# FR-011 / FR-012 -- conflict survives the round trip
# =============================================================================


class TestContradictionReachesTheApi:
    def _both(self) -> Proposition:
        return Proposition(
            subject="Corvid Marine", predicate="beneficial_owner", object="T. Bramley",
            truth_state=TruthState.BOTH,
        )

    def test_a_conflicted_state_survives_storage_and_api(self) -> None:
        prop = self._both()
        state = ResearchState.resolve(
            query_executed=True,
            contributions=[
                EvidenceContribution(evidence_id="EVD-A", positive=True),
                EvidenceContribution(evidence_id="EVD-B", positive=False),
            ],
        )
        assert state.truth_state is TruthState.BOTH
        assert json_loads(json_dumps(state)).fingerprint == state.fingerprint
        assert build_api_response(state)["state"]["truth_state"] == "both"
        assert build_ui_projection(state)["headline"] == (
            "Sources disagree — both readings are held"
        )
        assert prop.truth_state is TruthState.BOTH

    def test_the_contradiction_is_built_and_retains_both_sides(self) -> None:
        prop = self._both()
        contradiction = Contradiction(
            proposition_id=prop.proposition_id,
            kind=ContradictionKind.SUPPORT,
            detail="two sources state opposite things",
            sides=(
                {"side": "supporting", "refs": ("EVD-A",)},
                {"side": "refuting", "refs": ("EVD-B",)},
            ),
            subject_refs=("EVD-A", "EVD-B"),
        )
        payload = contradiction.as_dict()
        assert [side["side"] for side in payload["sides"]] == ["supporting", "refuting"]
        assert json.loads(json.dumps(payload))["status"] == "open"

    @pytest.mark.parametrize("heuristic", list(ResolutionHeuristic))
    def test_no_heuristic_resolves_it_anywhere_in_the_round_trip(
        self, heuristic: ResolutionHeuristic
    ) -> None:
        prop = self._both()
        contradiction = Contradiction(
            proposition_id=prop.proposition_id,
            kind=ContradictionKind.SUPPORT,
            detail="d",
            sides=(
                {"side": "supporting", "refs": ("EVD-A",)},
                {"side": "refuting", "refs": ("EVD-B",)},
            ),
        )
        attempt = attempt_resolution(
            contradiction, offered=[heuristic], declared_state=TruthState.TRUE_ONLY
        )
        assert attempt.resolved is False
        assert attempt.declared_state is TruthState.BOTH
        # The event and API layers report BOTH regardless of what the caller wanted.
        state = ResearchState.resolve(
            query_executed=True,
            contributions=[
                EvidenceContribution(evidence_id="EVD-A", positive=True),
                EvidenceContribution(evidence_id="EVD-B", positive=False),
            ],
        )
        assert build_event(state)["payload"]["research_state"]["truth_state"] == "both"
        assert build_api_response(state)["state"]["evidence"] == "conflicted"

    def test_support_and_refutation_are_not_a_boolean(self) -> None:
        both = ResearchState.resolve(
            query_executed=True,
            contributions=[
                EvidenceContribution(evidence_id="EVD-A", positive=True),
                EvidenceContribution(evidence_id="EVD-B", positive=False),
            ],
        )
        true_only = ResearchState.resolve(
            query_executed=True,
            contributions=[EvidenceContribution(evidence_id="EVD-A", positive=True)],
        )
        assert build_api_response(both)["state"] != build_api_response(true_only)["state"]
        assert build_ui_projection(both)["headline"] != build_ui_projection(true_only)["headline"]

    def test_negative_support_and_a_refutation_stay_distinct_in_the_ui(self) -> None:
        leaning = ResearchState.resolve(
            query_executed=True,
            contributions=[EvidenceContribution(evidence_id="EVD-A", positive=False)],
        )
        denied = ResearchState.resolve(
            query_executed=True,
            contributions=[
                EvidenceContribution(
                    evidence_id="EVD-A", positive=False, explicit_denial=True
                )
            ],
        )
        assert leaning.evidence is EvidenceAxis.OBSERVED
        assert denied.evidence is EvidenceAxis.REFUTED
        assert build_ui_projection(leaning)["headline"] == "Evidence leans negative"
        assert build_ui_projection(denied)["headline"] == "Refuted"


# =============================================================================
# FR-014 -- universal quantification degrades with enumerated limitations
# =============================================================================


class TestUniversalDegradationThroughTheApi:
    def _result_set(self, **over) -> ResultSet:
        return ResultSet(source_universe="registered sources", **over)

    def test_a_universal_query_over_unquantified_sources_degrades(self) -> None:
        answer = degrade_universal(self._result_set(candidate_set=("C1",), resolved_set=("C1",)))
        assert isinstance(answer, DegradedUniversalAnswer)
        assert answer.may_claim_universal_negative is False
        assert "Not a universal answer" in answer.phrasing
        assert "candidates observed within the stated coverage" in answer.phrasing.lower()
        payload = assert_states_absence(
            {
                "items": list(answer.candidates),
                "status": answer.completeness_mode.value,
                "coverage": answer.coverage,
                "provenance": "synthetic fixture, licence=synthetic",
                "limitations": [item.value for item in answer.limitations],
            }
        )
        assert "detection_power_undeclared" in payload["limitations"]

    def test_every_unmet_precondition_is_enumerated_by_name(self) -> None:
        answer = degrade_universal(
            self._result_set(candidate_set=("C1",)),
            universe_declared=False,
            coverage_declared=False,
            freshness_declared=False,
            capabilities_available=False,
            budget_truncated=True,
            detection_power_declared=False,
        )
        assert set(answer.limitations) == set(LimitationKind) - {LimitationKind.NONE}

    def test_a_degraded_answer_with_no_limitations_cannot_be_built(self) -> None:
        with pytest.raises(ValueError, match="enumerate at least one limitation"):
            DegradedUniversalAnswer(
                candidates=("C1",),
                coverage="registered sources",
                limitations=(),
                completeness_mode="open_world_discovery",
            )

    def test_a_degraded_answer_must_state_its_coverage(self) -> None:
        with pytest.raises(ValueError, match="stated coverage"):
            DegradedUniversalAnswer(
                candidates=("C1",),
                coverage="  ",
                limitations=(LimitationKind.DETECTION_POWER_UNDECLARED,),
                completeness_mode="open_world_discovery",
            )

    def test_a_flat_none_is_not_producible(self) -> None:
        """The phrasing can never be "there are none" without a qualified absence."""
        result_set = self._result_set(candidate_set=("C1",), resolved_set=("C1",))
        for power in (None, 0.2, 0.9):
            answer = degrade_universal(result_set, detection_power_declared=power is not None)
            assert answer.phrasing.strip() != "none"
            assert answer.limitations, "every degraded answer enumerates what limited it"
            if not answer.may_claim_universal_negative:
                assert "Not a universal answer" in answer.phrasing
        # Even where the negative reading is available the phrasing reports what was
        # observed alongside it -- "no candidate satisfies the query within X; N observed
        # within X" -- and never a flat "there are none".
        claimable = degrade_universal(
            result_set,
            detection_power_declared=True,
            coverage_declared=True,
            freshness_declared=False,
        )
        assert claimable.may_claim_universal_negative
        assert "candidate observed within" in claimable.phrasing
        assert claimable.phrasing.strip() != "none"

    def test_a_universal_query_whose_preconditions_all_hold_is_not_degraded(self) -> None:
        """Degradation is for answers that had to be weakened, not for every universal query.

        Phrasing a supported universal answer as a degraded one *understates* what was
        established, which is a different dishonesty from the one FR-014 prevents and
        worth refusing rather than papering over with a filler limitation.
        """
        with pytest.raises(ValueError, match="every FR-014 precondition is met"):
            degrade_universal(
                self._result_set(candidate_set=("C1",), resolved_set=("C1",)),
                detection_power_declared=True,
                coverage_declared=True,
            )


# =============================================================================
# The fixture corpus, read end to end
# =============================================================================


def _load_corpus() -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in CORPUS.read_text(encoding="utf-8").splitlines()
        if line
    ]


CORPUS_CASES = _load_corpus()


def _state_for(case: dict[str, Any]) -> ResearchState:
    sources = case["sources"]
    declared = [s["declared_detection_power"] for s in sources
                if s["declared_detection_power"] is not None]
    return ResearchState.resolve(
        source_reachable=all(s["reaches_platform"] for s in sources) if sources else True,
        supports_query_kind=all(s["supports_query_kind"] for s in sources) if sources else True,
        capability_available=all(s["capability_available"] for s in sources) if sources else True,
        query_executed=bool(case["query_ran"]),
        collection_completed=bool(case.get("collection_completed")),
        observations_read=len(case["evidence"]),
        inconclusive_evidence=any(i["positive"] is None for i in case["evidence"]),
        contributions=[
            EvidenceContribution(
                evidence_id=i["ref"],
                positive=bool(i["positive"]),
                explicit_denial=bool(i.get("explicit_denial")),
            )
            for i in case["evidence"]
            if i["positive"] is not None
        ],
        detection_power=declared[0] if declared else None,
        coverage_estimate=sources[0]["coverage_estimate"] if sources else None,
        universe_declared=bool(case.get("all_fr014_preconditions_declared")),
        freshness_declared=bool(case.get("all_fr014_preconditions_declared")),
        errors_accounted=all(s["errors_accounted"] for s in sources) if sources else True,
        budget_truncated=any(s["budget_truncated"] for s in sources),
        exhausted_within_declared_scope=bool(case.get("exhausted_within_declared_scope")),
    )


@pytest.mark.parametrize(
    "case", CORPUS_CASES, ids=[case["case_id"] for case in CORPUS_CASES]
)
class TestCorpusEndToEnd:
    def test_the_case_survives_all_four_layers(self, case: dict[str, Any]) -> None:
        state = _state_for(case)
        assert json_loads(json_dumps(state)).fingerprint == state.fingerprint
        assert build_event(state)["payload"]["may_claim_absence"] == state.may_claim_absence
        build_api_response(state)
        assert build_ui_projection(state)["badge"] == state.absence.value

    def test_the_api_never_claims_more_than_the_fixture_permits(
        self, case: dict[str, Any]
    ) -> None:
        state = _state_for(case)
        response = build_api_response(state)
        assert (
            response["state"]["may_claim_absence"]
            == case["expected"]["may_claim_universal_negative"]
        ), (
            f"{case['case_id']}: the API may-claim flag disagrees with the fixture. Ground "
            f"truth: {case['ground_truth']}"
        )
        assert state.may_claim_absence == case["expected"]["may_claim_universal_negative"]
        assert response["limitations"], (
            "R4 requires the response to say what it could not cover; a response naming "
            "no limitation has not distinguished itself from a bare empty list"
        )

    def test_the_ui_never_renders_an_unearned_absence(self, case: dict[str, Any]) -> None:
        state = _state_for(case)
        projection = build_ui_projection(state)
        if not case["expected"]["may_claim_universal_negative"]:
            assert projection["claimable"] is False
            assert "No candidate satisfies" not in projection["headline"]


class TestTheIndependentTestEndToEnd:
    """The five inputs, each carried through all four layers."""

    FIVE = (
        "EPI-FAIL-01",
        "EPI-SNR-KNOWN-02",
        "EPI-SNR-UNKNOWN-01",
        "EPI-BOTH-01",
        "EPI-UNK-01",
    )

    def _state(self, case_id: str) -> ResearchState:
        return _state_for(next(c for c in CORPUS_CASES if c["case_id"] == case_id))

    def test_they_stay_distinct_at_every_layer(self) -> None:
        layers = {
            "storage": lambda s: json_loads(json_dumps(s)).fingerprint,
            "event": lambda s: json.dumps(build_event(s)["payload"], sort_keys=True),
            "api": lambda s: json.dumps(build_api_response(s), sort_keys=True),
            "ui": lambda s: json.dumps(build_ui_projection(s), sort_keys=True, default=str),
        }
        for layer, key in layers.items():
            values = {key(self._state(case_id)) for case_id in self.FIVE}
            assert len(values) == 5, f"the {layer} layer collapsed five inputs to {len(values)}"

    def test_the_zero_result_pair_differs_only_in_the_absence_axis_after_the_round_trip(
        self,
    ) -> None:
        declared = json_loads(json_dumps(self._state("EPI-SNR-KNOWN-02")))
        undeclared = json_loads(json_dumps(self._state("EPI-SNR-UNKNOWN-01")))
        assert declared.absence is AbsenceAxis.QUALIFIED_ABSENCE
        assert undeclared.absence is AbsenceAxis.INFORMATIONAL_ONLY
        differing = {
            axis
            for axis in ("disposition", "query", "truth_state", "evidence", "scope")
            if getattr(declared, axis) is not getattr(undeclared, axis)
        }
        assert differing == set(), (
            f"the pair is supposed to differ on the absence axis alone; it also differs on "
            f"{sorted(differing)}"
        )
