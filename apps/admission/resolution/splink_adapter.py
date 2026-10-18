"""Splink as a linkage *proposer*, behind the platform's resolution contract.

Spec 030 CE-001 §15.5, DON-ER-003/005, task T105. ADR-030-06.

**Upstream**   : https://github.com/moj-analytical-services/splink
**Revision**   : 4.0.10 (pinned)
**Licence**    : MIT (code). Model weights: none shipped.
**Mode**       : B — upstream package behind a COGNITIVE contract.

**The one rule this module exists to enforce.** Splink proposes; it does not decide. Its output
is a :class:`ResolutionCandidate` with a comparison vector and a score whose *semantics* are
named. Nothing here writes identity, and nothing here is wired to write identity.

That is not caution, it is the finding from the 029 audit: the existing matcher was able to
commit a merge on a threshold whose own profile declared itself uncalibrated. A second engine
that could do the same would not be an improvement, it would be a second way to be wrong.

**Baseline this must beat** (ADR-030-06): the existing Fellegi-Sunter implementation at
``apps/zero/zero/resolution/fellegi_sunter.py``. Until ``benchmarks/er-baseline.md`` records a
comparison on the same labelled pairs, this adapter stays benchmark-only and no production
caller is wired to it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - import shape documented, not exercised at runtime
    from resolution.candidate import Candidate

__all__ = [
    "SPLINK_VERSION_PINNED",
    "ComparisonVectorEntry",
    "ResolutionCandidate",
    "ScoreSemantics",
    "SplinkAdapter",
    "SplinkResult",
    "SplinkUnavailable",
]

# The supported range, not a single release. An exact pin here went stale the moment the
# lockfile resolved 4.0.17, and a stale constant is worse than a range: it looks like a
# verified version while describing one that is no longer installed. `version()` reports the
# version actually imported, and the tests check that against the declared range.
SPLINK_VERSION_PINNED = "4.0.10"
SPLINK_VERSION_SUPPORTED = ">=4.0.10,<5"


class SplinkUnavailable(RuntimeError):
    """Splink is not installed in this environment.

    Raised rather than degraded. An absent linker is a capability gap with a named cause, and
    reporting it as "no matches found" would turn a missing dependency into a finding about the
    data.
    """


class ScoreSemantics(StrEnum):
    """What a score means, so a decision cannot read it as something else.

    ``match_probability`` is Splink's calibrated probability that two records match, given the
    trained model. ``uncalibrated_weight`` is a match weight with no probability interpretation.
    ``blocking_only`` means the pair was surfaced by a blocking rule and never scored.
    """

    MATCH_PROBABILITY = "match_probability"
    UNCALIBRATED_WEIGHT = "uncalibrated_weight"
    BLOCKING_ONLY = "blocking_only"


@dataclass(frozen=True, slots=True)
class ComparisonVectorEntry:
    """One field comparison, preserved in Splink's own terms.

    Kept even though the platform does not read it today: a merge an analyst cannot interrogate
    is a merge they have to take on faith, and the vector is the only thing that makes it
    interrogable.
    """

    field: str
    comparison_level: str | None
    value_l: Any
    value_r: Any


@dataclass(frozen=True, slots=True)
class ResolutionCandidate:
    """What Splink proposes, in platform vocabulary. Never a decision."""

    pair_key: str
    left_id: str
    right_id: str
    score: float | None
    score_semantics: ScoreSemantics
    comparison_vector: tuple[ComparisonVectorEntry, ...]
    model_fingerprint: str
    """Identifies the trained model and the blocking rules. Without it a score cannot be
    compared with another score, because two runs may have trained on different data."""
    splink_version: str = SPLINK_VERSION_PINNED
    notes: dict[str, Any] = field(default_factory=dict)

    @property
    def decision_weight(self) -> float:
        """A usable priority number, or ``0.0`` when nothing was scored.

        Deliberately not usable as a merge threshold by itself. It exists for *ordering*
        candidates for review, which is the one thing a proposal may legitimately do.
        """
        return float(self.score) if self.score is not None else 0.0

    def requires_human_or_policy_decision(self) -> bool:
        """Always True. Present so that a caller cannot forget the check."""
        return True

    def to_candidate(self) -> Candidate:
        """Adapt to the existing candidate record without deciding anything.

        Lands as ``OPEN`` with the pair's evidence written into ``reasons`` so a reviewer sees
        which field comparisons produced the proposal. There is no code path from here to
        ``ACCEPTED``; that transition belongs to the resolution decision service, which records
        who or what decided and why.
        """
        from resolution.candidate import Candidate, CandidateState

        reasons = [
            (
                f"splink/{self.splink_version} score={self.score} "
                f"semantics={self.score_semantics} model={self.model_fingerprint}"
            ),
        ]
        for entry in self.comparison_vector:
            reasons.append(
                f"{entry.field}:{entry.comparison_level or '-'} "
                f"l={entry.value_l!r} r={entry.value_r!r}"
            )
        return Candidate(
            pair_key=self.pair_key,
            candidate_a=self.left_id,
            candidate_b=self.right_id,
            raw_pair_score=float(self.score) if self.score is not None else 0.0,
            reasons=reasons,
            state=CandidateState.OPEN,
        )


@dataclass(frozen=True, slots=True)
class SplinkResult:
    """One run's output, with enough context to reproduce or challenge it."""

    candidates: tuple[ResolutionCandidate, ...]
    model_fingerprint: str
    training_row_count: int | None = None
    """Rows the model was trained on. A score from a model trained on nine rows and a score from
    a model trained on ninety thousand are different claims."""
    calibrated: bool = False
    notes: dict[str, Any] = field(default_factory=dict)

    @property
    def is_comparable_to_another_run(self) -> bool:
        """Whether another run's scores can be laid beside these.

        False for an uncalibrated run, because an uncalibrated match weight is a distance in an
        arbitrary space and two such spaces are not the same space.
        """
        return self.calibrated


class SplinkAdapter:
    """Adapter over ``splink`` that produces proposals, not decisions.

    The heavy lifting is done by Splink's own ``Linker``. This class owns three things Splink has
    no opinion about: that the output is a proposal, that the score carries its semantics, and
    that the model that produced it is named.
    """

    def __init__(self, *, version: str = SPLINK_VERSION_PINNED) -> None:
        self._version = version

    @staticmethod
    def _require() -> Any:
        try:
            import splink
        except ImportError as exc:  # pragma: no cover - environment-dependent
            raise SplinkUnavailable(
                "splink is not installed; the linkage backend is unavailable. This is a "
                "capability gap, not a finding about the data (see CE-001 §15.5)"
            ) from exc
        return splink

    def available(self) -> bool:
        try:
            self._require()
        except SplinkUnavailable:
            return False
        return True

    def version(self) -> str:
        splink = self._require()
        return str(getattr(splink, "__version__", self._version))

    @staticmethod
    def pair_key(left_id: str, right_id: str) -> str:
        """Order-independent pair identity.

        Sorted, because ``(a,b)`` and ``(b,a)`` are one pair and two ids for one pair means one
        candidate is proposed twice and reviewed twice.
        """
        return "|".join(sorted((str(left_id), str(right_id))))

    def to_candidate(
        self,
        *,
        left_id: str,
        right_id: str,
        score: float | None,
        score_semantics: ScoreSemantics,
        comparison_vector: tuple[ComparisonVectorEntry, ...],
        model_fingerprint: str,
        **notes: Any,
    ) -> ResolutionCandidate:
        return ResolutionCandidate(
            pair_key=self.pair_key(left_id, right_id),
            left_id=str(left_id),
            right_id=str(right_id),
            score=score,
            score_semantics=score_semantics,
            comparison_vector=comparison_vector,
            model_fingerprint=model_fingerprint,
            splink_version=self._version,
            notes=dict(notes),
        )

    def to_result(
        self,
        candidates: tuple[ResolutionCandidate, ...],
        *,
        model_fingerprint: str,
        training_row_count: int | None = None,
        calibrated: bool = False,
        **notes: Any,
    ) -> SplinkResult:
        """Wrap a run. Ordered by descending score so a review queue starts at the top.

        Ties break on ``pair_key`` so two runs over the same model produce the same order.
        """
        ordered = tuple(
            sorted(candidates, key=lambda c: (-c.decision_weight, c.pair_key))
        )
        return SplinkResult(
            candidates=ordered,
            model_fingerprint=model_fingerprint,
            training_row_count=training_row_count,
            calibrated=calibrated,
            notes=dict(notes),
        )