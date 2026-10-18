"""Stage outcomes and failure classification: nine statuses, seventeen classes, one retry rule.

Spec 030 contract 03 / FR-047, FR-068, FR-069, FR-100 / task T030.

``status`` says what happened. ``error_code`` says **why**, and the code is what drives retry.
Keeping them apart is the whole design: a system that stores one field for both cannot
distinguish "the query ran and matched nothing" from "the system could not express the query",
and those two need opposite client behaviour.

**Five pairs that must never collapse.** Each is a correctness defect when it does, and each is
refused at construction rather than at read time:

* ``no_result`` != ``unsupported`` -- the query ran and matched nothing, versus the system could
  not express the query. A parser that cannot process a format returns ``unsupported``; it does
  not return a zero-length document with ``status = succeeded``.
* ``failed`` != ``succeeded`` with empty output -- an error is not a document with no content.
* ``partial`` != ``succeeded`` -- partial omits scope, and that scope travels with the result.
* ``no_change`` != ``succeeded`` -- zero delta is the suppression signal that feeds action
  memory (FR-045), and it is worth nothing if ``succeeded`` means the same thing.
* ``no_result`` != ``qualified_absence`` -- absence requires a declared universe **and** declared
  detection power. Without the detection power the result serialises as
  ``INFORMATIONAL_ONLY``, which is its own epistemic state, not a flavour of ``no_result``.

**A status never implies progress.** :attr:`StageOutcome.counts_as_progress` is a separate
question with a separate answer, because ``succeeded`` counts only when it produced *new
independent evidence*. A stage that re-derives what three other stages already established has
advanced nothing, and reporting that as progress is how an investigation loops without moving.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from contracts.canonical import digest_of, instant_text, normalize_instant
from contracts.error_codes import ErrorCategory, ErrorCode

__all__ = [
    "BudgetLevel",
    "CoverageStatement",
    "ErrorClass",
    "QuarantineRecord",
    "RetrySemantics",
    "StageOutcome",
    "StageOutcomeError",
    "StageStatus",
    "EpistemicState",
    "TIME_PRECISIONS",
]


class StageOutcomeError(ValueError):
    """A stage outcome says something its own fields do not support.

    Raised rather than defaulted. The default reading of a malformed outcome is the status it
    names, and the statuses here are mutually exclusive claims about the world -- defaulting
    between them manufactures a fact.
    """


class StageStatus(StrEnum):
    """The nine outcomes. Closed, because each names a different state of the world."""

    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    NO_RESULT = "no_result"
    UNSUPPORTED = "unsupported"
    BLOCKED = "blocked"
    FAILED = "failed"
    QUARANTINED = "quarantined"
    ABSTAINED = "abstained"
    NO_CHANGE = "no_change"

    @property
    def counts_as_progress(self) -> bool:
        """Whether this status *may* count as progress, before any evidence is weighed.

        Only ``succeeded`` and ``partial`` may. Everything else is a statement that the run
        produced no new independent evidence, and FR-045's suppression signal depends on that
        being true of ``no_change`` in particular.
        """
        return self in (StageStatus.SUCCEEDED, StageStatus.PARTIAL)

    @property
    def may_satisfy_obligation(self) -> bool:
        """Whether this status may discharge an obligation.

        Only ``succeeded`` (against its declared acceptance criteria) and ``partial`` (against
        the subset it met). Everything else, including ``no_result`` with a qualified-absence
        coverage statement, satisfies nothing on its own.
        """
        return self in (StageStatus.SUCCEEDED, StageStatus.PARTIAL)


class RetrySemantics(StrEnum):
    """How a failure class may be retried. The distinction contract 03 draws, kept explicit."""

    NEVER = "never"
    BOUNDED = "bounded"
    AFTER_BACKOFF = "after_backoff"
    RESUMABLE = "resumable"
    REPLAY_ONLY = "replay_only"
    FAILS_LOUDLY = "fails_loudly"
    NOT_APPLICABLE = "not_applicable"


class ErrorClass(StrEnum):
    """The seventeen failure classes, finer than ``status``. ``error_code`` picks one.

    Each carries :attr:`retry` and :attr:`contract07_code`, so a handler never has to remember
    which failures are safe to repeat and never has to translate between the two documents'
    vocabularies by hand.
    """

    EXPECTED_NO_RESULT = "EXPECTED_NO_RESULT"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    RATE_LIMITED = "RATE_LIMITED"
    POLICY_BLOCKED = "POLICY_BLOCKED"
    CAPABILITY_UNAVAILABLE = "CAPABILITY_UNAVAILABLE"
    UNSUPPORTED_QUERY = "UNSUPPORTED_QUERY"
    MALFORMED_INPUT = "MALFORMED_INPUT"
    PARTIAL_OUTPUT = "PARTIAL_OUTPUT"
    TIMEOUT = "TIMEOUT"
    RESOURCE_CAP = "RESOURCE_CAP"
    TRANSIENT_INFRA = "TRANSIENT_INFRA"
    PERMANENT_OPERATOR_ERROR = "PERMANENT_OPERATOR_ERROR"
    SCHEMA_MISMATCH = "SCHEMA_MISMATCH"
    ADMISSION_REJECTED = "ADMISSION_REJECTED"
    QUARANTINED = "QUARANTINED"
    REPLAY_MISMATCH = "REPLAY_MISMATCH"
    HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"

    @property
    def retry(self) -> RetrySemantics:
        return _RETRY[self]

    @property
    def contract07_code(self) -> ErrorCode:
        """The contract-07 code this class serialises as.

        The two documents use different names for some of the same things
        (``EXPECTED_NO_RESULT`` / ``NO_RESULT``). One mapping, held here, so a client never
        has to know that.
        """
        return _CONTRACT_07[self]

    @property
    def category(self) -> ErrorCategory:
        return self.contract07_code.category


_RETRY: dict[ErrorClass, RetrySemantics] = {
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
    # Fails loudly with both fingerprints. Never resolved by accepting the newer output: that
    # silently discards reproducibility, which is the property the replay mode exists for.
    ErrorClass.REPLAY_MISMATCH: RetrySemantics.FAILS_LOUDLY,
    ErrorClass.HUMAN_REVIEW_REQUIRED: RetrySemantics.NEVER,
}

_CONTRACT_07: dict[ErrorClass, ErrorCode] = {
    ErrorClass.EXPECTED_NO_RESULT: ErrorCode.EXPECTED_NO_RESULT,
    ErrorClass.SOURCE_UNAVAILABLE: ErrorCode.SOURCE_UNAVAILABLE,
    ErrorClass.RATE_LIMITED: ErrorCode.RATE_LIMITED,
    ErrorClass.POLICY_BLOCKED: ErrorCode.POLICY_BLOCKED,
    ErrorClass.CAPABILITY_UNAVAILABLE: ErrorCode.CAPABILITY_UNAVAILABLE,
    ErrorClass.UNSUPPORTED_QUERY: ErrorCode.UNSUPPORTED_QUERY,
    ErrorClass.MALFORMED_INPUT: ErrorCode.MALFORMED_INPUT,
    ErrorClass.PARTIAL_OUTPUT: ErrorCode.PARTIAL_OUTPUT,
    ErrorClass.TIMEOUT: ErrorCode.TIMEOUT,
    ErrorClass.RESOURCE_CAP: ErrorCode.RESOURCE_CAP,
    ErrorClass.TRANSIENT_INFRA: ErrorCode.TRANSIENT_INFRA,
    ErrorClass.PERMANENT_OPERATOR_ERROR: ErrorCode.PERMANENT_OPERATOR_ERROR,
    ErrorClass.SCHEMA_MISMATCH: ErrorCode.SCHEMA_MISMATCH,
    ErrorClass.ADMISSION_REJECTED: ErrorCode.ADMISSION_REJECTED,
    ErrorClass.QUARANTINED: ErrorCode.QUARANTINED,
    ErrorClass.REPLAY_MISMATCH: ErrorCode.REPLAY_MISMATCH,
    ErrorClass.HUMAN_REVIEW_REQUIRED: ErrorCode.HUMAN_REVIEW_REQUIRED,
}

# Both tables are total. A class with no retry rule is a class a caller has to guess about,
# and a class with no contract-07 code is a failure a client cannot parse. Checked here rather
# than in a test because `assert` disappears under -O and this is load-bearing.
if set(_RETRY) != set(ErrorClass):  # pragma: no cover - guard that must never fire
    raise RuntimeError(
        f"failure classes with no retry rule: "
        f"{sorted(str(c) for c in set(ErrorClass) - set(_RETRY))}"
    )
if set(_CONTRACT_07) != set(ErrorClass):  # pragma: no cover - guard that must never fire
    raise RuntimeError(
        f"failure classes with no contract-07 code: "
        f"{sorted(str(c) for c in set(ErrorClass) - set(_CONTRACT_07))}"
    )


class BudgetLevel(StrEnum):
    """FR-068: retry budgets exist at five levels and the exhausted one is named."""

    TASK = "task"
    SOURCE = "source"
    INVESTIGATION = "investigation"
    TENANT = "tenant"
    GLOBAL = "global"


class EpistemicState(StrEnum):
    """What kind of claim a ``no_result`` is allowed to make.

    ``QUALIFIED_ABSENCE`` requires a declared universe *and* declared detection power.
    Without the detection power the result is ``INFORMATIONAL_ONLY`` -- a different epistemic
    state, not a weaker flavour of the same one. Presenting it as absence is a release blocker.
    """

    SEARCHED_NO_RESULT = "SEARCHED_NO_RESULT"
    INFORMATIONAL_ONLY = "INFORMATIONAL_ONLY"
    QUALIFIED_ABSENCE = "QUALIFIED_ABSENCE"


#: Declared time precisions, coarsest last. A source fact at day precision does not become a
#: timestamp when it is stored (FR-020's eight clocks; contract 01's ``source_times``).
TIME_PRECISIONS = ("year", "month", "day", "hour", "minute", "second", "microsecond")


@dataclass(frozen=True, slots=True)
class CoverageStatement:
    """The statement that produced a ``no_result``. Mandatory whenever the status is one.

    An absence claim is only as good as the universe it searched and the power with which it
    searched. ``detection_power=None`` is the honest "we did not measure this", and it forces
    :attr:`epistemic_state` to ``INFORMATIONAL_ONLY`` rather than letting a caller read the
    other fields as a qualified absence.
    """

    universe: str
    coverage: str
    residual: str = ""
    detection_power: float | None = None
    freshness: str = ""

    def __post_init__(self) -> None:
        for name in ("universe", "coverage"):
            value = str(getattr(self, name)).strip()
            if not value:
                raise StageOutcomeError(
                    f"a coverage statement must declare its {name}; 'no result' without the "
                    "universe that produced it is indistinguishable from a query that was never "
                    "run (FR-014, FR-035)"
                )
            object.__setattr__(self, name, value)
        if self.detection_power is not None:
            power = float(self.detection_power)
            if not 0.0 <= power <= 1.0:
                raise StageOutcomeError(
                    f"detection_power must be within 0.0..1.0, got {self.detection_power!r}; a "
                    "power outside that range is not a measurement"
                )
            object.__setattr__(self, "detection_power", power)

    @property
    def epistemic_state(self) -> EpistemicState:
        """``QUALIFIED_ABSENCE`` only with declared detection power. Never inferred."""
        if self.detection_power is None:
            return EpistemicState.INFORMATIONAL_ONLY
        return EpistemicState.QUALIFIED_ABSENCE

    @property
    def may_support_absence(self) -> bool:
        return self.epistemic_state is EpistemicState.QUALIFIED_ABSENCE

    def as_dict(self) -> dict[str, object]:
        return {
            "universe": self.universe,
            "coverage": self.coverage,
            "residual": self.residual,
            "detection_power": self.detection_power,
            "freshness": self.freshness,
            "epistemic_state": str(self.epistemic_state),
        }


@dataclass(frozen=True, slots=True)
class QuarantineRecord:
    """The FR-069 envelope. The failure is preserved; the attempt is what is retried.

    ``record_ref`` is a pointer, never inline raw content -- a poison payload stored inline in
    a quarantine row is a poison payload stored in the one table nobody inspects.
    """

    record_ref: str
    schema_version: str
    expected_schema_version: str
    failure_class: ErrorClass
    error_code: ErrorCode
    first_attempt_at: datetime
    last_attempt_at: datetime
    attempt_count: int
    replay_eligible: bool
    replay_ineligible_reason: str = ""
    redaction_policy: str = ""
    retention_class: str = ""

    def __post_init__(self) -> None:
        for name in ("record_ref", "schema_version", "expected_schema_version"):
            value = str(getattr(self, name)).strip()
            if not value:
                raise StageOutcomeError(f"quarantine requires {name}")
            object.__setattr__(self, name, value)
        if (
            not str(self.record_ref).strip()
            or self.record_ref.lstrip().startswith(("{", "<", "PK"))
        ):
            raise StageOutcomeError(
                "quarantine.record_ref must be a pointer to the payload, never the payload "
                "itself; an inline poison record is stored in the one table nobody inspects"
            )
        object.__setattr__(self, "failure_class", ErrorClass(self.failure_class))
        object.__setattr__(self, "error_code", ErrorCode(self.error_code))
        object.__setattr__(
            self,
            "first_attempt_at",
            normalize_instant(self.first_attempt_at),
        )
        object.__setattr__(self, "last_attempt_at", normalize_instant(self.last_attempt_at))
        if self.last_attempt_at < self.first_attempt_at:
            raise StageOutcomeError(
                f"quarantine last_attempt_at {instant_text(self.last_attempt_at)} precedes "
                f"first_attempt_at {instant_text(self.first_attempt_at)}"
            )
        if isinstance(self.attempt_count, bool) or self.attempt_count < 1:
            raise StageOutcomeError(
                f"quarantine attempt_count must be at least 1, got {self.attempt_count!r}; 0 "
                "attempts is not a quarantined record"
            )
        if not self.replay_eligible and not str(self.replay_ineligible_reason).strip():
            raise StageOutcomeError(
                "a record marked replay-ineligible must say why; an unexplained ineligibility "
                "reads as a decision nobody made (FR-069)"
            )

    @property
    def schema_version_mismatch(self) -> bool:
        return self.schema_version != self.expected_schema_version

    def as_dict(self) -> dict[str, object]:
        return {
            "record_ref": self.record_ref,
            "schema_version": self.schema_version,
            "expected_schema_version": self.expected_schema_version,
            "failure_class": str(self.failure_class),
            "error_code": str(self.error_code),
            "first_attempt_at": instant_text(self.first_attempt_at),
            "last_attempt_at": instant_text(self.last_attempt_at),
            "attempt_count": self.attempt_count,
            "replay_eligible": self.replay_eligible,
            "replay_ineligible_reason": self.replay_ineligible_reason,
            "redaction_policy": self.redaction_policy,
            "retention_class": self.retention_class,
        }


@dataclass(frozen=True, slots=True)
class StageOutcome:
    """One stage's result: exactly one status, one error class when applicable, one reason.

    Every conditional requirement in contract 03's validation table is enforced here rather
    than at read time, because a consumer that has to re-check them will eventually not.
    """

    status: StageStatus
    error_class: ErrorClass | None = None
    detail: str = ""
    coverage: CoverageStatement | None = None
    missingness: tuple[str, ...] = ()
    binding_limit: str = ""
    resumable: bool | None = None
    gap_reason: str = ""
    budget_exhausted: BudgetLevel | None = None
    substitution_attempted: bool | None = None
    new_independent_evidence: int | None = None
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", StageStatus(self.status))
        if self.error_class is not None:
            object.__setattr__(self, "error_class", ErrorClass(self.error_class))
        object.__setattr__(self, "detail", str(self.detail))
        object.__setattr__(self, "gap_reason", str(self.gap_reason).strip())
        object.__setattr__(self, "binding_limit", str(self.binding_limit).strip())
        object.__setattr__(self, "missingness", tuple(str(item) for item in self.missingness))
        object.__setattr__(self, "warnings", tuple(str(item) for item in self.warnings))
        if self.budget_exhausted is not None:
            object.__setattr__(self, "budget_exhausted", BudgetLevel(self.budget_exhausted))
        if self.substitution_attempted is not None:
            object.__setattr__(
                self, "substitution_attempted", bool(self.substitution_attempted)
            )
        if self.new_independent_evidence is not None and self.new_independent_evidence < 0:
            raise StageOutcomeError(
                f"new_independent_evidence cannot be negative, got "
                f"{self.new_independent_evidence!r}"
            )
        self._validate()

    def _validate(self) -> None:
        status = self.status

        # Rule 1: a status that means "it did not happen" carries why it did not happen.
        needs_class = status in (
            StageStatus.FAILED,
            StageStatus.BLOCKED,
            StageStatus.QUARANTINED,
            StageStatus.UNSUPPORTED,
            StageStatus.NO_RESULT,
        )
        if needs_class and self.error_class is None:
            raise StageOutcomeError(
                f"status {status.value} means the run did not produce its normal result and MUST "
                "carry the error class saying why; 'unsupported' with no reason is a blank"
            )

        # Rule 5 + validation row: `blocked` names its blocker.
        if status is StageStatus.BLOCKED and not self.gap_reason:
            raise StageOutcomeError(
                "status blocked must name the blocker -- which capability, which policy, which "
                "approval, which budget -- so the obligation can be re-opened when the condition "
                "clears (FR-038, R5)"
            )

        # Validation row: retryable class + exhausted budget => blocked, level named.
        if self.budget_exhausted is not None and status is not StageStatus.BLOCKED:
            raise StageOutcomeError(
                f"budget level {self.budget_exhausted.value} is exhausted, so the status must be "
                f"blocked; {status.value} reports it as anything else, and an exhausted budget "
                "is never a silent success (FR-068)"
            )
        if (
            status is StageStatus.BLOCKED
            and self.budget_exhausted is not None
            and not self.gap_reason
        ):
            raise StageOutcomeError(
                f"status blocked on budget level {self.budget_exhausted.value} must name the "
                "level in its blocker, not only in the level field (FR-068)"
            )

        # Rule 2 + validation row: no_result carries the coverage statement that produced it.
        if status is StageStatus.NO_RESULT and self.coverage is None:
            raise StageOutcomeError(
                "status no_result MUST carry the coverage statement that produced it; a bare "
                "no_result is indistinguishable from a query that was never run (FR-014, FR-035)"
            )

        # Rule 3 + validation row: partial carries what it did, what it did not, the binding
        # limit, and whether it resumes.
        if status is StageStatus.PARTIAL:
            if not self.missingness:
                raise StageOutcomeError(
                    "status partial MUST record what was not processed; partial and succeeded "
                    "differ only by whether the omitted scope travels with the result"
                )
            if not self.binding_limit:
                raise StageOutcomeError(
                    "status partial MUST name the limit that bounded it; 'partial' with no "
                    "named limit cannot be resumed and cannot be re-planned"
                )
            if self.resumable is None:
                raise StageOutcomeError(
                    "status partial MUST say whether the residual is resumable; an unestimated "
                    "boolean is an omission, not an answer (FR-068)"
                )

        # Validation row: unsupported => no substitution was attempted.
        if self.substitution_attempted:
            raise StageOutcomeError(
                "a CapacityGap must record substitution_attempted = false; a registry lookup "
                "that cannot satisfy a requirement returns an explicit gap, never a weaker "
                "substitute (CE-I13)"
            )

        # Rule 4: a status never implies a progress delta, and the two directions are checked.
        if not status.counts_as_progress and self.new_independent_evidence:
            raise StageOutcomeError(
                f"status {status.value} does not count as progress, so it cannot carry "
                f"new_independent_evidence={self.new_independent_evidence}; a progress delta is "
                "computed separately and inferred from the status it is not (FR-045)"
            )

        if status in (
            StageStatus.SUCCEEDED,
            StageStatus.NO_CHANGE,
            StageStatus.ABSTAINED,
        ) and self.coverage is not None:
            raise StageOutcomeError(
                f"status {status.value} did not search; a coverage statement on it is a claim "
                "about a search that did not happen"
            )

    # -- derived questions ---------------------------------------------------

    @property
    def counts_as_progress(self) -> bool:
        """Whether this outcome advanced the investigation.

        ``succeeded`` counts only when it produced **new independent evidence**. Re-deriving
        what three other stages already established is a successful run that moved nothing, and
        reporting it as progress is how a loop iterates without converging.
        """
        if not self.status.counts_as_progress:
            return False
        if self.status is StageStatus.PARTIAL:
            return bool(self.new_independent_evidence)
        return bool(self.new_independent_evidence)

    @property
    def may_satisfy_obligation(self) -> bool:
        """Whether this outcome may discharge an obligation.

        Only ``succeeded`` -- against its declared acceptance criteria -- and ``partial``,
        against the subset it met. Everything else satisfies nothing on its own, ``no_result``
        included: a qualified absence is admissible *evidence* of absence, not a discharge of
        the obligation that asked the question.
        """
        return self.status.may_satisfy_obligation

    @property
    def retry_semantics(self) -> RetrySemantics:
        """How this failure may be retried. Derived from the class, never from the status."""
        if self.error_class is None:
            return RetrySemantics.NOT_APPLICABLE
        return self.error_class.retry

    @property
    def is_retryable(self) -> bool:
        return self.retry_semantics in (
            RetrySemantics.BOUNDED,
            RetrySemantics.AFTER_BACKOFF,
            RetrySemantics.RESUMABLE,
            RetrySemantics.REPLAY_ONLY,
        )

    @property
    def error_code(self) -> ErrorCode | None:
        """The contract-07 code this outcome serialises as, or None when nothing went wrong."""
        return self.error_class.contract07_code if self.error_class is not None else None

    @property
    def epistemic_state(self) -> EpistemicState | None:
        return self.coverage.epistemic_state if self.coverage is not None else None

    def content_key(self) -> str:
        """Content address of the outcome, so duplicate detection is a set membership test."""
        return digest_of(
            {
                "status": str(self.status),
                "error_class": str(self.error_class) if self.error_class else None,
                "coverage": self.coverage.as_dict() if self.coverage else None,
                "missingness": list(self.missingness),
                "binding_limit": self.binding_limit,
                "gap_reason": self.gap_reason,
                "budget": str(self.budget_exhausted) if self.budget_exhausted else None,
                "new_independent_evidence": self.new_independent_evidence,
            }
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "status": str(self.status),
            "error_class": str(self.error_class) if self.error_class else None,
            "error_code": str(self.error_code) if self.error_code else None,
            "detail": self.detail,
            "coverage": self.coverage.as_dict() if self.coverage else None,
            "missingness": list(self.missingness),
            "binding_limit": self.binding_limit,
            "resumable": self.resumable,
            "gap_reason": self.gap_reason,
            "budget_exhausted": (
                str(self.budget_exhausted) if self.budget_exhausted else None
            ),
            "retry_semantics": str(self.retry_semantics),
            "counts_as_progress": self.counts_as_progress,
        }