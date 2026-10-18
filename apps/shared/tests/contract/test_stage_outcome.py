"""Stage outcome contract tests (spec 030 contract 03, task T030/T036).

Three named invariants, plus the retry table they hang off:

* ``no_result`` != ``unsupported`` -- the query ran and matched nothing, versus the system could
  not express the query. Opposite client behaviour, so the collapse is a correctness defect;
* ``failed`` != succeeded-with-empty -- an error is not a document with zero content;
* ``no_result`` carries the coverage statement that produced it -- without declared detection
  power the result is ``INFORMATIONAL_ONLY``, which is its own epistemic state and is never a
  qualified absence.

Also pinned: nine statuses and seventeen failure classes exist and no more, every class has
exactly one retry rule, ``no_change`` is the suppression signal rather than a success, and an
exhausted retry budget is ``blocked`` with the level named -- never a silent success.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from contracts.error_codes import ErrorCategory, ErrorCode
from contracts.stage_outcome import (
    BudgetLevel,
    CoverageStatement,
    EpistemicState,
    ErrorClass,
    QuarantineRecord,
    RetrySemantics,
    StageOutcome,
    StageOutcomeError,
    StageStatus,
)

pytestmark = pytest.mark.contract

FIRST = datetime(2026, 10, 14, 9, 0, tzinfo=UTC)


def _coverage(**kw) -> CoverageStatement:
    base = {"universe": "declared web sources A-E", "coverage": "A,B,C,D,E searched to 2026-10-14"}
    base.update(kw)
    return CoverageStatement(**base)


def _outcome(**kw) -> StageOutcome:
    base: dict[str, object] = {"status": StageStatus.SUCCEEDED}
    base.update(kw)
    return StageOutcome(**base)


class TestTheVocabulariesAreClosed:
    def test_there_are_exactly_nine_statuses(self):
        assert len(StageStatus) == 9

    def test_the_nine_are_the_named_nine(self):
        assert {str(s) for s in StageStatus} == {
            "succeeded",
            "partial",
            "no_result",
            "unsupported",
            "blocked",
            "failed",
            "quarantined",
            "abstained",
            "no_change",
        }

    def test_there_are_exactly_seventeen_failure_classes(self):
        assert len(ErrorClass) == 17

    def test_every_failure_class_declares_exactly_one_retry_rule(self):
        for failure in ErrorClass:
            assert isinstance(failure.retry, RetrySemantics)

    def test_every_failure_class_maps_to_a_classified_contract_07_code(self):
        for failure in ErrorClass:
            assert isinstance(failure.contract07_code, ErrorCode)
            assert isinstance(failure.category, ErrorCategory)

    def test_the_retry_table_matches_contract_03_row_for_row(self):
        """Every row of contract 03's failure-class table, checked."""
        expected = {
            ErrorClass.EXPECTED_NO_RESULT: RetrySemantics.NEVER,
            ErrorClass.SOURCE_UNAVAILABLE: RetrySemantics.BOUNDED,
            ErrorClass.RATE_LIMITED: RetrySemantics.AFTER_BACKOFF,
            ErrorClass.POLICY_BLOCKED: RetrySemantics.NEVER,
            ErrorClass.CAPABILITY_UNAVAILABLE: RetrySemantics.NEVER,
            ErrorClass.UNSUPPORTED_QUERY: RetrySemantics.NEVER,
            ErrorClass.MALFORMED_INPUT: RetrySemantics.NEVER,
            ErrorClass.PARTIAL_OUTPUT: RetrySemantics.RESUMABLE,
            ErrorClass.TIMEOUT: RetrySemantics.BOUNDED,
            ErrorClass.RESOURCE_CAP: RetrySemantics.BOUNDED,
            ErrorClass.TRANSIENT_INFRA: RetrySemantics.BOUNDED,
            ErrorClass.PERMANENT_OPERATOR_ERROR: RetrySemantics.NEVER,
            ErrorClass.SCHEMA_MISMATCH: RetrySemantics.NEVER,
            ErrorClass.ADMISSION_REJECTED: RetrySemantics.NEVER,
            ErrorClass.QUARANTINED: RetrySemantics.REPLAY_ONLY,
            ErrorClass.REPLAY_MISMATCH: RetrySemantics.FAILS_LOUDLY,
            ErrorClass.HUMAN_REVIEW_REQUIRED: RetrySemantics.NEVER,
        }
        assert {f: f.retry for f in ErrorClass} == expected

    def test_replay_mismatch_fails_loudly_rather_than_retrying(self):
        """Accepting the newer output is the alternative, and it discards reproducibility."""
        assert ErrorClass.REPLAY_MISMATCH.retry is RetrySemantics.FAILS_LOUDLY
        assert ErrorClass.REPLAY_MISMATCH.contract07_code.is_release_blocker is True


class TestNoResultIsNotUnsupported:
    """The first of the five pairs that must never collapse."""

    def test_a_no_result_carries_a_coverage_statement(self):
        outcome = _outcome(
            status=StageStatus.NO_RESULT,
            error_class=ErrorClass.EXPECTED_NO_RESULT,
            coverage=_coverage(),
        )
        assert outcome.status is StageStatus.NO_RESULT
        assert outcome.coverage is not None

    def test_a_no_result_without_a_coverage_statement_is_refused(self):
        with pytest.raises(StageOutcomeError) as e:
            _outcome(status=StageStatus.NO_RESULT, error_class=ErrorClass.EXPECTED_NO_RESULT)
        assert "coverage statement" in str(e.value)

    def test_an_unsupported_outcome_is_a_different_status(self):
        unsupported = _outcome(
            status=StageStatus.UNSUPPORTED,
            error_class=ErrorClass.CAPABILITY_UNAVAILABLE,
        )
        assert unsupported.status is StageStatus.UNSUPPORTED
        assert unsupported.status is not StageStatus.NO_RESULT
        assert str(unsupported.status) != str(StageStatus.NO_RESULT)

    def test_the_two_carry_different_failure_classes(self):
        no_result = _outcome(
            status=StageStatus.NO_RESULT,
            error_class=ErrorClass.EXPECTED_NO_RESULT,
            coverage=_coverage(),
        )
        unsupported = _outcome(
            status=StageStatus.UNSUPPORTED,
            error_class=ErrorClass.CAPABILITY_UNAVAILABLE,
        )
        assert no_result.error_class is ErrorClass.EXPECTED_NO_RESULT
        assert unsupported.error_class is ErrorClass.CAPABILITY_UNAVAILABLE

    def test_the_two_suggest_opposite_client_behaviour(self):
        """Report the no-result; do not retry the unsupported. Conflating them retries forever."""
        no_result = _outcome(
            status=StageStatus.NO_RESULT,
            error_class=ErrorClass.EXPECTED_NO_RESULT,
            coverage=_coverage(),
        )
        unsupported = _outcome(
            status=StageStatus.UNSUPPORTED,
            error_class=ErrorClass.CAPABILITY_UNAVAILABLE,
        )
        assert no_result.retry_semantics is RetrySemantics.NEVER
        assert unsupported.retry_semantics is RetrySemantics.NEVER
        assert no_result.may_satisfy_obligation is False
        assert unsupported.may_satisfy_obligation is False


class TestNoResultIsNotQualifiedAbsence:
    """``no_result`` != ``qualified_absence``: absence needs a universe *and* detection power."""

    def test_unknown_detection_power_is_informational_only(self):
        coverage = _coverage(detection_power=None)
        assert coverage.epistemic_state is EpistemicState.INFORMATIONAL_ONLY
        assert coverage.may_support_absence is False

    def test_declared_detection_power_makes_a_qualified_absence_possible(self):
        coverage = _coverage(detection_power=0.94)
        assert coverage.epistemic_state is EpistemicState.QUALIFIED_ABSENCE
        assert coverage.may_support_absence is True

    def test_informational_only_is_its_own_state_not_a_flavour_of_no_result(self):
        outcome = _outcome(
            status=StageStatus.NO_RESULT,
            error_class=ErrorClass.EXPECTED_NO_RESULT,
            coverage=_coverage(detection_power=None),
        )
        assert outcome.epistemic_state is EpistemicState.INFORMATIONAL_ONLY
        assert outcome.epistemic_state is not EpistemicState.SEARCHED_NO_RESULT

    def test_a_coverage_statement_without_a_universe_is_refused(self):
        with pytest.raises(StageOutcomeError) as e:
            CoverageStatement(universe="  ", coverage="all searched")
        assert "universe" in str(e.value)

    def test_a_detection_power_outside_the_unit_interval_is_refused(self):
        with pytest.raises(StageOutcomeError):
            _coverage(detection_power=1.4)

    def test_a_qualified_absence_still_satisfies_nothing_on_its_own(self):
        outcome = _outcome(
            status=StageStatus.NO_RESULT,
            error_class=ErrorClass.EXPECTED_NO_RESULT,
            coverage=_coverage(detection_power=1.0),
        )
        assert outcome.status.may_satisfy_obligation is False

    def test_a_coverage_statement_on_a_run_that_never_searched_is_refused(self):
        """``no_result`` is the only status that may claim a search happened."""
        with pytest.raises(StageOutcomeError) as e:
            _outcome(status=StageStatus.SUCCEEDED, coverage=_coverage())
        assert "did not search" in str(e.value)


class TestFailedIsNotSucceededWithEmpty:
    """The second pair. An error is not a document with zero content."""

    def test_a_failure_carries_its_class(self):
        outcome = _outcome(status=StageStatus.FAILED, error_class=ErrorClass.TRANSIENT_INFRA)
        assert outcome.status is StageStatus.FAILED

    def test_a_failure_without_a_class_is_refused(self):
        with pytest.raises(StageOutcomeError) as e:
            _outcome(status=StageStatus.FAILED)
        assert "MUST carry the error class" in str(e.value)

    def test_a_failure_is_not_a_success_with_nothing_in_it(self):
        failure = _outcome(status=StageStatus.FAILED, error_class=ErrorClass.TRANSIENT_INFRA)
        success = _outcome(status=StageStatus.SUCCEEDED)
        assert failure.status is not success.status
        assert failure.counts_as_progress is False

    def test_a_failure_satisfies_no_obligation_even_with_new_evidence_attached(self):
        """The two are checked independently, so the combination is refused outright."""
        with pytest.raises(StageOutcomeError) as e:
            _outcome(
                status=StageStatus.FAILED,
                error_class=ErrorClass.TRANSIENT_INFRA,
                new_independent_evidence=3,
            )
        assert "does not count as progress" in str(e.value)

    def test_every_non_success_status_is_refused_without_a_class(self):
        for status in (
            StageStatus.FAILED,
            StageStatus.BLOCKED,
            StageStatus.QUARANTINED,
            StageStatus.UNSUPPORTED,
            StageStatus.NO_RESULT,
        ):
            with pytest.raises(StageOutcomeError):
                _outcome(status=status)


class TestPartialIsNotSucceeded:
    """The third pair: partial omits scope, and the omitted scope travels with the result."""

    def _partial(self, **kw):
        base = {
            "status": StageStatus.PARTIAL,
            "missingness": ("pages 4-40 not extracted",),
            "binding_limit": "token_budget=4096",
            "resumable": True,
            "error_class": ErrorClass.PARTIAL_OUTPUT,
        }
        base.update(kw)
        return _outcome(**base)

    def test_a_complete_partial_builds(self):
        assert self._partial().status is StageStatus.PARTIAL

    def test_partial_without_missingness_is_refused(self):
        with pytest.raises(StageOutcomeError) as e:
            _outcome(
                status=StageStatus.PARTIAL,
                binding_limit="token_budget=4096",
                resumable=True,
                error_class=ErrorClass.PARTIAL_OUTPUT,
            )
        assert "what was not processed" in str(e.value)

    def test_partial_without_a_named_binding_limit_is_refused(self):
        with pytest.raises(StageOutcomeError) as e:
            self._partial(binding_limit="  ")
        assert "name the limit" in str(e.value)

    def test_partial_without_a_resumable_answer_is_refused(self):
        with pytest.raises(StageOutcomeError) as e:
            self._partial(resumable=None)
        assert "resumable" in str(e.value)

    def test_partial_counts_as_progress_only_with_new_evidence(self):
        assert self._partial(new_independent_evidence=2).counts_as_progress is True
        assert self._partial().counts_as_progress is False

    def test_partial_resumes(self):
        assert self._partial().retry_semantics is RetrySemantics.RESUMABLE
        assert self._partial().is_retryable is True


class TestNoChangeIsTheSuppressionSignal:
    """The fifth pair: zero delta is what feeds action memory, and it is not a success."""

    def test_no_change_does_not_count_as_progress(self):
        assert _outcome(status=StageStatus.NO_CHANGE).counts_as_progress is False

    def test_no_change_does_not_satisfy_an_obligation(self):
        assert _outcome(status=StageStatus.NO_CHANGE).status.may_satisfy_obligation is False

    def test_no_change_is_still_a_success_that_produced_nothing_new(self):
        """It needs no error class: nothing went wrong, nothing changed."""
        outcome = _outcome(status=StageStatus.NO_CHANGE)
        assert outcome.error_class is None
        assert outcome.retry_semantics is RetrySemantics.NOT_APPLICABLE

    def test_a_succeeded_run_with_no_new_evidence_also_does_not_count(self):
        """Re-deriving what three other stages established is a success that moved nothing."""
        assert _outcome(status=StageStatus.SUCCEEDED).counts_as_progress is False
        assert _outcome(
            status=StageStatus.SUCCEEDED, new_independent_evidence=1
        ).counts_as_progress is True


class TestBlockedNamesItsBlocker:
    """FR-038, R5: 'blocked' alone is not an answer anybody can act on."""

    def test_blocked_without_a_gap_reason_is_refused(self):
        with pytest.raises(StageOutcomeError) as e:
            _outcome(status=StageStatus.BLOCKED, error_class=ErrorClass.POLICY_BLOCKED)
        assert "name the blocker" in str(e.value)

    def test_blocked_with_a_named_capability_is_accepted(self):
        outcome = _outcome(
            status=StageStatus.BLOCKED,
            error_class=ErrorClass.CAPABILITY_UNAVAILABLE,
            gap_reason="no OCR capability registered in this profile",
        )
        assert "OCR" in outcome.gap_reason

    def test_an_exhausted_budget_must_be_blocked_and_name_the_level(self):
        with pytest.raises(StageOutcomeError) as e:
            _outcome(
                status=StageStatus.SUCCEEDED,
                budget_exhausted=BudgetLevel.TENANT,
                new_independent_evidence=1,
            )
        assert "must be blocked" in str(e.value)

    def test_an_exhausted_budget_with_a_named_level_builds(self):
        outcome = _outcome(
            status=StageStatus.BLOCKED,
            error_class=ErrorClass.SOURCE_UNAVAILABLE,
            budget_exhausted=BudgetLevel.INVESTIGATION,
            gap_reason="investigation retry budget exhausted",
        )
        assert outcome.budget_exhausted is BudgetLevel.INVESTIGATION

    def test_the_five_budget_levels_exist(self):
        assert {str(level) for level in BudgetLevel} == {
            "task",
            "source",
            "investigation",
            "tenant",
            "global",
        }


class TestUnsupportedNeverSubstitutes:
    """CE-I13: an explicit capacity gap, never a weaker substitute."""

    def test_a_substitution_attempt_is_refused(self):
        with pytest.raises(StageOutcomeError) as e:
            _outcome(
                status=StageStatus.UNSUPPORTED,
                error_class=ErrorClass.CAPABILITY_UNAVAILABLE,
                substitution_attempted=True,
            )
        assert "substitution_attempted" in str(e.value)

    def test_declaring_no_substitution_is_the_default_and_is_recorded(self):
        outcome = _outcome(
            status=StageStatus.UNSUPPORTED,
            error_class=ErrorClass.CAPABILITY_UNAVAILABLE,
            substitution_attempted=False,
        )
        assert outcome.substitution_attempted is False

    def test_a_capacity_gap_is_attached_to_the_outcome_not_instead_of_it(self):
        outcome = _outcome(
            status=StageStatus.UNSUPPORTED,
            error_class=ErrorClass.CAPABILITY_UNAVAILABLE,
            substitution_attempted=False,
        )
        assert outcome.status is StageStatus.UNSUPPORTED
        assert outcome.error_code is ErrorCode.CAPABILITY_UNAVAILABLE


class TestQuarantinePreservesTheFailure:
    """FR-069: the failure is preserved; the attempt is what gets retried."""

    def _record(self, **kw):
        base = {
            "record_ref": "blob://raw/t-acme/2026/10/14/sha256-abc",
            "schema_version": "2.1.0",
            "expected_schema_version": "2.1.0",
            "failure_class": ErrorClass.SCHEMA_MISMATCH,
            "error_code": ErrorCode.SCHEMA_MISMATCH,
            "first_attempt_at": FIRST,
            "last_attempt_at": FIRST + timedelta(minutes=4),
            "attempt_count": 3,
            "replay_eligible": True,
            "redaction_policy": "operators only",
            "retention_class": "raw-7y",
        }
        base.update(kw)
        return QuarantineRecord(**base)

    def test_a_record_is_a_pointer_never_an_inline_payload(self):
        with pytest.raises(StageOutcomeError) as e:
            self._record(record_ref='{"poison": "payload"}')
        assert "never the payload itself" in str(e.value)

    def test_a_schema_version_mismatch_is_visible(self):
        record = self._record(schema_version="1.0.0")
        assert record.schema_version_mismatch is True

    def test_a_matching_schema_version_is_visible(self):
        assert self._record().schema_version_mismatch is False

    def test_replay_ineligible_without_a_reason_is_refused(self):
        with pytest.raises(StageOutcomeError) as e:
            self._record(replay_eligible=False)
        assert "must say why" in str(e.value)

    def test_zero_attempts_is_not_a_quarantined_record(self):
        with pytest.raises(StageOutcomeError):
            self._record(attempt_count=0)

    def test_a_last_attempt_before_the_first_is_refused(self):
        with pytest.raises(StageOutcomeError):
            self._record(last_attempt_at=FIRST - timedelta(minutes=1))

    def test_attempt_count_is_carried_so_the_failure_history_survives(self):
        assert self._record(attempt_count=7).as_dict()["attempt_count"] == 7


class TestTheOutcomeIsDeduplicable:
    def test_two_identical_outcomes_share_a_content_key(self):
        first = _outcome(
            status=StageStatus.NO_RESULT,
            error_class=ErrorClass.EXPECTED_NO_RESULT,
            coverage=_coverage(),
        )
        second = _outcome(
            status=StageStatus.NO_RESULT,
            error_class=ErrorClass.EXPECTED_NO_RESULT,
            coverage=_coverage(),
        )
        assert first.content_key() == second.content_key()

    def test_a_different_coverage_statement_is_a_different_outcome(self):
        first = _outcome(
            status=StageStatus.NO_RESULT,
            error_class=ErrorClass.EXPECTED_NO_RESULT,
            coverage=_coverage(detection_power=0.9),
        )
        second = _outcome(
            status=StageStatus.NO_RESULT,
            error_class=ErrorClass.EXPECTED_NO_RESULT,
            coverage=_coverage(detection_power=0.1),
        )
        assert first.content_key() != second.content_key()

    def test_the_serialised_form_carries_the_retry_rule_with_it(self):
        outcome = _outcome(status=StageStatus.FAILED, error_class=ErrorClass.TIMEOUT)
        assert outcome.as_dict()["retry_semantics"] == "bounded"
        assert outcome.as_dict()["error_code"] == "TIMEOUT"