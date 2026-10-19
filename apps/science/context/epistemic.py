"""Four-valued truth state, propositions and contradictions (spec 025 §13).

``plan.md`` records this as the single highest-discipline item in the whole
specification: "Do not exist. Zero donor hits -- research §3.7. **NEW.**
Highest-discipline item; truth-table gate is a release gate (R3)." There is no
donor to borrow from, so it is written here from the specification.

Why four values and not three. With three values -- true, false, unknown -- the
moment two sources disagree the engine must either pick a side or collapse to
"unknown", and both destroy information. §0.2 names the collapse explicitly:
"contradictory sources != overwrite one source". ``BOTH`` exists so that
disagreement is a *state the engine can be in* rather than information it has to
throw away to make progress.

**Two orders, and they are not the same lattice.** This is the part that is
usually got wrong, so it is stated explicitly:

* Knowledge order (``NEITHER`` < ``TRUE_ONLY`` / ``FALSE_ONLY`` < ``BOTH``) -- more
  *evidence* is higher. Its join is ``accumulate`` (disjunction of flags) and its
  meet is ``consensus`` (conjunction). ``BOTH`` is maximal because it means the
  most was learned.
* Truth order (``FALSE_ONLY`` < ``NEITHER`` / ``BOTH`` < ``TRUE_ONLY``) -- more
  *true* is higher. Here ``BOTH`` sits *below* ``TRUE_ONLY``: one-sided true
  evidence outranks conflicting evidence for the purposes of "is this true",
  which is why ``and``/``or`` use the other flag pairing.

Collapsing them into a single ordering produces operators that are individually
plausible and jointly wrong, so both are implemented and tested separately.

§13.4 is the rule that keeps this honest: ``truth_state`` and ``score`` are
independent fields and ``truth_state`` never converts to a probability. There is
therefore no ``to_probability`` on this type, deliberately.

Three additions below, all of which extend rather than replace what is here:

* :class:`ResearchState` -- FR-010's thirteen research states as six independent
  dimensions rather than a thirteenth enum, because the states are not thirteen
  points. ``SATURATED_WITH_SCOPE`` is the reason: it is ``EXHAUSTED`` composed with
  whatever the exhausted search found, and a flat member can say only one of those
  things. :class:`TruthState` is reused as one of the six axes so the four-valued
  algebra and the thirteen-state model cannot drift apart.
* :func:`attempt_resolution` -- FR-012's refusal, as a value rather than an absence
  of code paths.
* :class:`ScoreVector` -- FR-016's fourteen components, kept apart from everything
  above so no composite can absorb two of them (U1).
"""

from __future__ import annotations

import enum
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Any

from context.locality import _digest

# -- §13.1 the four states ----------------------------------------------------


class TruthState(enum.StrEnum):
    """The four-valued support state of a proposition."""

    NEITHER = "neither"
    TRUE_ONLY = "true_only"
    FALSE_ONLY = "false_only"
    BOTH = "both"

    @classmethod
    def from_flags(cls, positive: bool, negative: bool) -> TruthState:
        """§13.1 table, verbatim."""
        if positive and negative:
            return cls.BOTH
        if positive:
            return cls.TRUE_ONLY
        if negative:
            return cls.FALSE_ONLY
        return cls.NEITHER

    @property
    def positive(self) -> bool:
        return self in (TruthState.TRUE_ONLY, TruthState.BOTH)

    @property
    def negative(self) -> bool:
        return self in (TruthState.FALSE_ONLY, TruthState.BOTH)

    @property
    def flags(self) -> tuple[bool, bool]:
        return (self.positive, self.negative)

    @property
    def is_determined(self) -> bool:
        """True when exactly one side has support."""
        return self in (TruthState.TRUE_ONLY, TruthState.FALSE_ONLY)

    @property
    def is_conflicted(self) -> bool:
        """``BOTH``. §13.3: this state *must* have a Contradiction."""
        return self is TruthState.BOTH


# -- §13.1 the two orders -----------------------------------------------------
#
# Both orders are defined as *relations*, not rank maps, because a rank map cannot
# express incomparability -- and incomparability is the entire content of these
# two diamonds. Ranking ``TRUE_ONLY`` and ``FALSE_ONLY`` both at 1 would make each
# one less than the other, silently converting a diamond into a chain and breaking
# every monotonicity and least-upper-bound argument downstream.

#: Knowledge (information) order -- more evidence is higher. ``BOTH`` is maximal.
#:
#:     BOTH
#:    /    \
#: TRUE_ONLY  FALSE_ONLY
#:    \    /
#:    NEITHER
#:
#: ``TRUE_ONLY`` and ``FALSE_ONLY`` are incomparable; so is any element with itself
#: only via the diagonal.
_KNOWLEDGE_LESS: dict[TruthState, frozenset[TruthState]] = {
    TruthState.NEITHER: frozenset(TruthState),
    TruthState.TRUE_ONLY: frozenset({TruthState.TRUE_ONLY, TruthState.BOTH}),
    TruthState.FALSE_ONLY: frozenset({TruthState.FALSE_ONLY, TruthState.BOTH}),
    TruthState.BOTH: frozenset({TruthState.BOTH}),
}

#: Truth order -- more true is higher. ``BOTH`` sits *below* ``TRUE_ONLY``.
#:
#:        TRUE_ONLY
#:        /    \
#:   NEITHER   BOTH
#:        \    /
#:      FALSE_ONLY
#:
#: ``NEITHER`` and ``BOTH`` are incomparable here.
_TRUTH_LESS: dict[TruthState, frozenset[TruthState]] = {
    TruthState.FALSE_ONLY: frozenset(TruthState),
    TruthState.NEITHER: frozenset({TruthState.NEITHER, TruthState.TRUE_ONLY}),
    TruthState.BOTH: frozenset({TruthState.BOTH, TruthState.TRUE_ONLY}),
    TruthState.TRUE_ONLY: frozenset({TruthState.TRUE_ONLY}),
}


def knowledge_leq(left: TruthState, right: TruthState) -> bool:
    """``left <= right`` in the knowledge (information) order."""
    return right in _KNOWLEDGE_LESS[left]


def truth_leq(left: TruthState, right: TruthState) -> bool:
    """``left <= right`` in the truth order."""
    return right in _TRUTH_LESS[left]


def knowledge_less(left: TruthState, right: TruthState) -> bool:
    """Strict inequality in the knowledge order."""
    return left is not right and knowledge_leq(left, right)


def truth_less(left: TruthState, right: TruthState) -> bool:
    """Strict inequality in the truth order."""
    return left is not right and truth_leq(left, right)


# -- §13.2 the five normative operations --------------------------------------


def negate(state: TruthState) -> TruthState:
    """``(p, n) -> (n, p)``. Polarity inversion of a proposition."""
    positive, negative = state.flags
    return TruthState.from_flags(negative, positive)


def accumulate(left: TruthState, right: TruthState) -> TruthState:
    """``(p1 | p2, n1 | n2)``. Knowledge-join.

    Combining admitted evidence about the same proposition. Evidence on either
    side is retained, which is precisely why accumulating a true with a false
    yields ``BOTH`` instead of a coin flip.
    """
    return TruthState.from_flags(left.positive or right.positive, left.negative or right.negative)


def consensus(left: TruthState, right: TruthState) -> TruthState:
    """``(p1 & p2, n1 & n2)``. Knowledge-meet.

    What two bodies of evidence *agree* on. Both asserting the same thing is
    ``TRUE_ONLY``; one true and one false agree on nothing and meet at
    ``NEITHER``.
    """
    return TruthState.from_flags(left.positive and right.positive, left.negative and right.negative)


def and_(left: TruthState, right: TruthState) -> TruthState:
    """``(p1 & p2, n1 | n2)``. Truth-order conjunction for compound propositions."""
    return TruthState.from_flags(left.positive and right.positive, left.negative or right.negative)


def or_(left: TruthState, right: TruthState) -> TruthState:
    """``(p1 | p2, n1 & n2)``. Truth-order disjunction."""
    return TruthState.from_flags(left.positive or right.positive, left.negative and right.negative)


OPERATIONS = (negate, accumulate, consensus, and_, or_)

#: The join and meet of each order, named so the two lattices can be referred to
#: without ambiguity. They are deliberately different pairs: ``accumulate`` and
#: ``consensus`` are the lattice operations of the knowledge order, ``or_`` and
#: ``and_`` are truth-functional composition operators (see below).
KNOWLEDGE_JOIN = accumulate
KNOWLEDGE_MEET = consensus
TRUTH_JOIN = or_
TRUTH_MEET = and_


# -- §3.13 proposition --------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Proposition:
    """A normalised claim with attachable polarity (§3.13).

    Identity is content-addressed over subject, predicate, object, scope and the
    temporal qualifier -- deliberately **not** over polarity. Two polarities of the
    same proposition are the same proposition with different support, which is what
    makes ``accumulate`` on evidence about one fact accumulate rather than fork.
    """

    subject: str
    predicate: str
    object: str
    scope: str = ""
    temporal_qualifier: str = ""
    proposition_id: str = ""
    truth_state: TruthState = TruthState.NEITHER
    #: Kept separate and never derived: §13.4.
    score: Any = None

    def __post_init__(self) -> None:
        if not self.subject or not self.predicate:
            raise ValueError("a proposition needs a subject and a predicate")
        object.__setattr__(self, "truth_state", TruthState(self.truth_state))
        if self.proposition_id and self.proposition_id != self.address():
            raise ValueError(
                f"declared proposition_id {self.proposition_id!r} but material "
                f"addresses to {self.address()}"
            )
        if not self.proposition_id:
            object.__setattr__(self, "proposition_id", self.address())

    def _material(self) -> dict[str, Any]:
        return {
            "subject": self.subject,
            "predicate": self.predicate,
            "object": self.object,
            "scope": self.scope,
            "temporal_qualifier": self.temporal_qualifier,
        }

    def address(self) -> str:
        return f"PRP-{_digest(self._material())}"

    @property
    def negated_id(self) -> str:
        """Identity of the same proposition under inverted polarity."""
        return Proposition(
            subject=self.subject,
            predicate=self.predicate,
            object=self.object,
            scope=self.scope,
            temporal_qualifier=self.temporal_qualifier,
        ).address()

    def with_truth(self, state: TruthState) -> Proposition:
        from dataclasses import replace

        return replace(self, truth_state=state)

    def as_dict(self) -> dict[str, Any]:
        return {
            "proposition_id": self.proposition_id,
            "subject": self.subject,
            "predicate": self.predicate,
            "object": self.object,
            "scope": self.scope,
            "temporal_qualifier": self.temporal_qualifier,
            "truth_state": self.truth_state.value,
            "score": self.score,
        }


# -- §13.2 truth_state derivation ---------------------------------------------


@dataclass(frozen=True, slots=True)
class EvidenceContribution:
    """One admissible evidence item's contribution to a proposition.

    §13.2: "A contribution requires an *admissible* evidence item (passed
    admission, not a coverage-qualified absence)". ``admissible`` is therefore a
    field, not a filter applied by the caller -- a caller who forgets the filter
    would otherwise silently fold a coverage-qualified absence into support.
    """

    evidence_id: str
    #: True when the item supports the proposition, False when it refutes it.
    positive: bool
    admissible: bool = True
    #: True when the item is a coverage-qualified absence (§13A). Never support.
    coverage_qualified: bool = False
    weight: float = 1.0
    #: True when the source *denied* the proposition outright, as distinct from
    #: observing something that leans against it. FR-010 lists ``negative support`` and
    #: ``refuted`` as separate states, so the distinction has to reach the algebra and a
    #: bare ``positive=False`` cannot carry it. Defaulted so every existing construction
    #: keeps meaning "leaning negative".
    explicit_denial: bool = False


def derive_truth_state(contributions: Iterable[EvidenceContribution]) -> TruthState:
    """``truth_state(P) = accumulate`` over admissible contributions (§13.2).

    Inadmissible and coverage-qualified items contribute nothing. They are not
    refutations either: "we searched and found nothing" is not evidence of
    falsity, and treating it as such would make every absence a negation.
    """
    state = TruthState.NEITHER
    for item in contributions:
        if not item.admissible or item.coverage_qualified:
            continue
        state = accumulate(state, TruthState.from_flags(item.positive, not item.positive))
    return state


# -- §23 contradictions -------------------------------------------------------


class ContradictionStatus(enum.StrEnum):
    """§23.3 lifecycle."""

    OPEN = "open"
    EXPLAINED = "explained"
    RESOLVED = "resolved"
    SUPERSEDED = "superseded"


class ContradictionKind(enum.StrEnum):
    """Why the contradiction exists. §13.3 allows these beyond ``BOTH``."""

    SUPPORT = "support"
    NUMERIC = "numeric"
    STRUCTURAL = "structural"
    IDENTITY = "identity"
    TEMPORAL = "temporal"


@dataclass(frozen=True, slots=True)
class Contradiction:
    """§23.1, built from a ``BOTH`` state.

    §13.3 governs the lifecycle: resolving a contradiction "never deletes support
    flags: it records an explanation". So resolution here changes status and adds
    an explanation, and the proposition's truth state is left alone.
    """

    proposition_id: str
    kind: ContradictionKind
    detail: str
    contradiction_id: str = ""
    status: ContradictionStatus = ContradictionStatus.OPEN
    #: §23.2: independence of the two sides, via dependency groups (§14A).
    independent: bool = False
    explanation: str = ""
    #: Both sides are retained. §0.2: contradictory sources != overwrite one.
    sides: tuple[dict[str, Any], ...] = ()
    subject_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.detail:
            raise ValueError("a contradiction must say what disagrees")
        object.__setattr__(self, "status", ContradictionStatus(self.status))
        object.__setattr__(self, "kind", ContradictionKind(self.kind))
        if not self.sides:
            raise ValueError(
                "a contradiction must retain both sides; overwriting one is the "
                "§0.2 violation"
            )
        if self.contradiction_id and self.contradiction_id != self.address():
            raise ValueError(
                f"declared contradiction_id {self.contradiction_id!r} but material "
                f"addresses to {self.address()}"
            )
        if not self.contradiction_id:
            object.__setattr__(self, "contradiction_id", self.address())

    def _material(self) -> dict[str, Any]:
        return {
            "proposition_id": self.proposition_id,
            "kind": self.kind.value,
            "detail": self.detail,
            "sides": [dict(side) for side in self.sides],
        }

    def address(self) -> str:
        return f"CTR-{_digest(self._material())}"

    def resolve(self, explanation: str) -> Contradiction:
        """Record an explanation. Support flags are never deleted (§13.3)."""
        if not explanation:
            raise ValueError("resolving a contradiction requires an explanation")
        if self.status is ContradictionStatus.OPEN:
            status = ContradictionStatus.EXPLAINED
        else:
            status = ContradictionStatus.RESOLVED
        return Contradiction(
            proposition_id=self.proposition_id,
            kind=self.kind,
            detail=self.detail,
            status=status,
            independent=self.independent,
            explanation=explanation,
            sides=self.sides,
            subject_refs=self.subject_refs,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "contradiction_id": self.contradiction_id,
            "proposition_id": self.proposition_id,
            "kind": self.kind.value,
            "status": self.status.value,
            "detail": self.detail,
            "independent": self.independent,
            "explanation": self.explanation,
            "sides": [dict(side) for side in self.sides],
            "subject_refs": list(self.subject_refs),
        }


def contradiction_for_both(
    proposition: Proposition,
    *,
    positive_refs: Sequence[str] = (),
    negative_refs: Sequence[str] = (),
    independent: bool = False,
    kind: ContradictionKind = ContradictionKind.SUPPORT,
) -> Contradiction | None:
    """§13.3: ``truth_state = BOTH`` implies a ``Contradiction`` must exist.

    Returns ``None`` for any non-``BOTH`` state. That is the whole point of
    modelling the state: a disagreement is a first-class thing the engine holds,
    and it is created automatically in the same revision rather than waiting for
    something downstream to notice.
    """
    if proposition.truth_state is not TruthState.BOTH:
        return None
    return Contradiction(
        proposition_id=proposition.proposition_id,
        kind=kind,
        detail=(
            f"proposition {proposition.proposition_id} has support on both sides "
            f"({len(positive_refs)} supporting, {len(negative_refs)} refuting)"
        ),
        independent=independent,
        sides=(
            {"side": "supporting", "refs": tuple(positive_refs)},
            {"side": "refuting", "refs": tuple(negative_refs)},
        ),
        subject_refs=tuple(positive_refs) + tuple(negative_refs),
    )


# ============================================================================
# FR-010 -- the thirteen research states, as structured dimensions
# ============================================================================
#
# Why dimensions and not a thirteenth enum. FR-010 lists thirteen states that must
# stay "mutually distinguishable". A single flat enum can hold thirteen distinct
# *values*, and would still be the wrong shape, because the states are not
# thirteen points -- they are the reachable corners of a product of independent
# questions:
#
#   * was the effort made at all, and how did it end   -> SearchDisposition
#   * did a query actually execute                     -> QueryAxis
#   * what do the sources say about the claim          -> TruthState (the four values)
#   * how strong a negative finding is this             -> AbsenceAxis
#   * what kind of evidence stands behind it            -> EvidenceAxis
#   * was the scope the exhaustion was measured in declared -> ScopeAxis
#
# The most load-bearing consequence is ``SATURATED_WITH_SCOPE``. It is not one
# state; it is ``SearchDisposition.EXHAUSTED`` *composed with* whatever the search
# found. An investigation that exhausted a declared universe having found three
# supporting sources and one contradicting one is saturated-with-scope **and**
# contradictory, and an enum with a ``SATURATED_WITH_SCOPE`` member can only say one
# of those things. The record says both, and says them in fields rather than in a
# label, so nothing has to be decoded on the way back out.
#
# The five separations below are the ones that collapse under pressure:
#   SOURCE_UNAVAILABLE vs SEARCHED_NO_RESULT  -- the plumbing failed vs nothing was there
#   SEARCHED_NO_RESULT vs QUALIFIED_ABSENCE   -- no matches vs no matches *with declared power*
#   NO_OBSERVATIONS vs SEARCHED_NO_RESULT     -- nothing was collected vs a query ran and matched none
#   QUERY_UNSUPPORTED vs SOURCE_UNAVAILABLE   -- cannot express it vs could not reach it
#   NEGATIVE_SUPPORT vs REFUTED               -- evidence leans false vs the claim was checked and denied
#
# ``ResearchStateName`` exists only to *name* the thirteen anchor points so a test
# and a UI label can address them. It is never the storage format.


class SearchDisposition(enum.StrEnum):
    """Axis 1 -- what happened to the effort. Not a ladder; the members are peers."""

    #: Nothing was ever done about this question. Distinct from every "we looked and
    #: found nothing" reading, which is the collapse FR-010's first member forbids.
    NOT_INVESTIGATED = "not_investigated"
    #: The system cannot express the request at all (contract 03 ``unsupported``).
    UNREPRESENTABLE = "unrepresentable"
    #: The request was expressible and the plumbing failed (contract 03 ``failed``).
    FAILED = "failed"
    #: The run stopped at a declared limit -- budget, cap, deadline, truncation.
    BOUNDED = "bounded"
    #: The run finished on its declared scope and was not cut short.
    COMPLETED = "completed"
    #: The run finished *and* the search cannot teach anything further.
    EXHAUSTED = "exhausted"


class QueryAxis(enum.StrEnum):
    """Axis 2 -- whether a query actually executed."""

    NOT_RUN = "not_run"
    #: Could not have run: the request is outside what this operator/source represents.
    UNRUNNABLE = "unrunnable"
    RAN_ZERO_MATCH = "ran_zero_match"
    RAN_MATCHED = "ran_matched"


class AbsenceAxis(enum.StrEnum):
    """Axis 4 -- how strong a negative finding this is. FR-014's whole subject."""

    NOT_APPLICABLE = "not_applicable"
    #: Detection power was not declared, so the result may not claim an absence.
    INFORMATIONAL_ONLY = "informational_only"
    #: A query ran and matched nothing. Says what it saw, not what does not exist.
    SEARCHED_NO_RESULT = "searched_no_result"
    #: Zero matches from a source that *declared* it would have found one.
    QUALIFIED_ABSENCE = "qualified_absence"


class EvidenceAxis(enum.StrEnum):
    """Axis 5 -- what kind of evidence stands behind the record."""

    NONE = "none"
    OBSERVED = "observed"
    #: Evidence is present and does not settle the question either way.
    INCONCLUSIVE = "inconclusive"
    #: Support on both sides. FR-012: this may not be resolved away.
    CONFLICTED = "conflicted"
    #: An explicit denial, as distinct from evidence that merely leans negative.
    REFUTED = "refuted"


class ScopeAxis(enum.StrEnum):
    """Axis 6 -- was the boundary of the claim declared rather than assumed."""

    UNDECLARED = "undeclared"
    DECLARED = "declared"


class ResearchStateName(enum.StrEnum):
    """The thirteen named anchor points of FR-010.

    A *name*, never a storage format. Two facts that share a name here are still two
    records with two dimension tuples; two facts that do not share a name may still
    be one record, because the names do not partition the space. Reading a name as
    the state is the bug T070 exists to prevent.
    """

    UNKNOWN_NOT_INVESTIGATED = "unknown_not_investigated"
    NO_OBSERVATIONS = "no_observations"
    SOURCE_UNAVAILABLE = "source_unavailable"
    QUERY_UNSUPPORTED = "query_unsupported"
    SEARCHED_NO_RESULT = "searched_no_result"
    QUALIFIED_ABSENCE = "qualified_absence"
    POSITIVE_SUPPORT = "positive_support"
    NEGATIVE_SUPPORT = "negative_support"
    BOTH_CONTRADICTION = "both_contradiction"
    INCONCLUSIVE = "inconclusive"
    BLOCKED_PARTIAL = "blocked_partial"
    REFUTED = "refuted"
    SATURATED_WITH_SCOPE = "saturated_with_scope"


#: The thirteen, each as its full dimension tuple. Written out rather than derived so
#: that the mapping is one table a reviewer can check by eye, and so that a change to
#: any tuple is a visible diff rather than a refactor that silently renumbers states.
#:
#: The guard below asserts two properties of this table: it is total over
#: :class:`ResearchStateName`, and its thirteen tuples are pairwise distinct. The
#: second is the whole of "no collapse": if two of these ever agree, two different
#: facts round-trip to one value and the platform is lying.
_CANO13: dict[ResearchStateName, tuple[Any, ...]] = {
    ResearchStateName.UNKNOWN_NOT_INVESTIGATED: (
        SearchDisposition.NOT_INVESTIGATED,
        QueryAxis.NOT_RUN,
        TruthState.NEITHER,
        AbsenceAxis.NOT_APPLICABLE,
        EvidenceAxis.NONE,
        ScopeAxis.UNDECLARED,
    ),
    ResearchStateName.NO_OBSERVATIONS: (
        SearchDisposition.COMPLETED,
        QueryAxis.NOT_RUN,
        TruthState.NEITHER,
        AbsenceAxis.NOT_APPLICABLE,
        EvidenceAxis.NONE,
        ScopeAxis.UNDECLARED,
    ),
    ResearchStateName.SOURCE_UNAVAILABLE: (
        SearchDisposition.FAILED,
        QueryAxis.NOT_RUN,
        TruthState.NEITHER,
        AbsenceAxis.INFORMATIONAL_ONLY,
        EvidenceAxis.NONE,
        ScopeAxis.UNDECLARED,
    ),
    ResearchStateName.QUERY_UNSUPPORTED: (
        SearchDisposition.UNREPRESENTABLE,
        QueryAxis.UNRUNNABLE,
        TruthState.NEITHER,
        AbsenceAxis.NOT_APPLICABLE,
        EvidenceAxis.NONE,
        ScopeAxis.UNDECLARED,
    ),
    ResearchStateName.SEARCHED_NO_RESULT: (
        SearchDisposition.COMPLETED,
        QueryAxis.RAN_ZERO_MATCH,
        TruthState.NEITHER,
        AbsenceAxis.SEARCHED_NO_RESULT,
        EvidenceAxis.NONE,
        ScopeAxis.UNDECLARED,
    ),
    ResearchStateName.QUALIFIED_ABSENCE: (
        SearchDisposition.COMPLETED,
        QueryAxis.RAN_ZERO_MATCH,
        TruthState.NEITHER,
        AbsenceAxis.QUALIFIED_ABSENCE,
        EvidenceAxis.NONE,
        ScopeAxis.UNDECLARED,
    ),
    ResearchStateName.POSITIVE_SUPPORT: (
        SearchDisposition.COMPLETED,
        QueryAxis.RAN_MATCHED,
        TruthState.TRUE_ONLY,
        AbsenceAxis.NOT_APPLICABLE,
        EvidenceAxis.OBSERVED,
        ScopeAxis.UNDECLARED,
    ),
    ResearchStateName.NEGATIVE_SUPPORT: (
        SearchDisposition.COMPLETED,
        QueryAxis.RAN_MATCHED,
        TruthState.FALSE_ONLY,
        AbsenceAxis.NOT_APPLICABLE,
        EvidenceAxis.OBSERVED,
        ScopeAxis.UNDECLARED,
    ),
    ResearchStateName.BOTH_CONTRADICTION: (
        SearchDisposition.COMPLETED,
        QueryAxis.RAN_MATCHED,
        TruthState.BOTH,
        AbsenceAxis.NOT_APPLICABLE,
        EvidenceAxis.CONFLICTED,
        ScopeAxis.UNDECLARED,
    ),
    ResearchStateName.INCONCLUSIVE: (
        SearchDisposition.COMPLETED,
        QueryAxis.RAN_MATCHED,
        TruthState.NEITHER,
        AbsenceAxis.NOT_APPLICABLE,
        EvidenceAxis.INCONCLUSIVE,
        ScopeAxis.UNDECLARED,
    ),
    ResearchStateName.BLOCKED_PARTIAL: (
        SearchDisposition.BOUNDED,
        QueryAxis.RAN_MATCHED,
        TruthState.NEITHER,
        AbsenceAxis.INFORMATIONAL_ONLY,
        EvidenceAxis.INCONCLUSIVE,
        ScopeAxis.UNDECLARED,
    ),
    ResearchStateName.REFUTED: (
        SearchDisposition.COMPLETED,
        QueryAxis.RAN_MATCHED,
        TruthState.FALSE_ONLY,
        AbsenceAxis.NOT_APPLICABLE,
        EvidenceAxis.REFUTED,
        ScopeAxis.UNDECLARED,
    ),
    # The interesting one. ``EXHAUSTED`` is the claim; the rest of the tuple records
    # what the exhausted search found, which is the information a flat member would
    # have thrown away. An exhausted search that found supporting evidence is this
    # tuple with ``TRUE_ONLY``/``OBSERVED`` -- a different record, and a name that
    # ``SATURATED_WITH_SCOPE`` would have had to be wrong about.
    ResearchStateName.SATURATED_WITH_SCOPE: (
        SearchDisposition.EXHAUSTED,
        QueryAxis.RAN_ZERO_MATCH,
        TruthState.NEITHER,
        AbsenceAxis.SEARCHED_NO_RESULT,
        EvidenceAxis.NONE,
        ScopeAxis.DECLARED,
    ),
}


class EpistemicStateError(ValueError):
    """A research state asserts something its own dimensions do not support."""


#: FR-014's absence thresholds, read once here so :meth:`ResearchState.resolve` and
#: :meth:`ResearchState.for_detection_power` cannot drift apart. They are the same numbers
#: as :class:`context.coverage.CoverageThresholds` -- re-derived there because importing
#: at module scope would make ``coverage`` import ``epistemic``, and the dependency runs
#: the other way. :func:`_thresholds_agree` is checked at import so a change to one
#: without the other fails loudly.
_COVERAGE_THRESHOLD = 0.8
_DETECTION_THRESHOLD = 0.5


def _thresholds_agree() -> None:
    from context.coverage import CoverageThresholds

    thresholds = CoverageThresholds()
    if (thresholds.min_coverage, thresholds.min_detection_power) != (
        _COVERAGE_THRESHOLD,
        _DETECTION_THRESHOLD,
    ):
        raise EpistemicStateError(
            "CoverageThresholds and this module's FR-014 constants disagree: "
            f"({thresholds.min_coverage}, {thresholds.min_detection_power}) vs "
            f"({_COVERAGE_THRESHOLD}, {_DETECTION_THRESHOLD}). One of them was edited "
            "without the other and an absence claim would now pass in one layer and fail "
            "in the next"
        )


_thresholds_agree()


@dataclass(frozen=True, slots=True)
class ResearchState:
    """One epistemic fact, held as six independent quantities plus what limited it.

    Frozen and content-shaped: two records that say the same thing about the world are
    the same record, and two that differ on any single axis are different records.
    :attr:`fingerprint` is that identity and it is the thing that round-trips -- not a
    label, and not a ``TruthState``.

    ``confidence`` is a seventh field and is deliberately inert: it is stored, reported
    and never consulted. §13.4 makes truth state and score independent, and the only
    way to keep that true is for nothing in this module to read it.
    """

    disposition: SearchDisposition
    query: QueryAxis
    truth_state: TruthState
    absence: AbsenceAxis
    evidence: EvidenceAxis
    scope: ScopeAxis = ScopeAxis.UNDECLARED
    confidence: float | None = None
    #: Declared detection power, or ``None`` for "we did not measure this". The single
    #: field the centre of this story turns on: ``None`` here forbids
    #: ``QUALIFIED_ABSENCE`` and the constructor refuses to build the combination.
    detection_power: float | None = None
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name, enum_type in (
            ("disposition", SearchDisposition),
            ("query", QueryAxis),
            ("truth_state", TruthState),
            ("absence", AbsenceAxis),
            ("evidence", EvidenceAxis),
            ("scope", ScopeAxis),
        ):
            try:
                object.__setattr__(self, name, enum_type(getattr(self, name)))
            except ValueError as exc:
                raise EpistemicStateError(
                    f"{name}={getattr(self, name)!r} is not a member of {enum_type.__name__}"
                ) from exc
        object.__setattr__(
            self, "limitations", tuple(str(item) for item in self.limitations)
        )
        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            raise EpistemicStateError(
                f"confidence must be in [0, 1] or None, got {self.confidence!r}"
            )
        if self.detection_power is not None and not 0.0 <= self.detection_power <= 1.0:
            raise EpistemicStateError(
                f"detection_power must be in [0, 1] or None, got {self.detection_power!r}"
            )
        self._validate()

    def _validate(self) -> None:
        """Refuse every combination that would let one fact wear another's label.

        Each rule closes a specific collapse named in FR-010/FR-014. They are
        constructor rules rather than reader rules because the default reading of a
        malformed record is the status it names, and every status here is a claim
        about the world.
        """
        if self.absence is AbsenceAxis.QUALIFIED_ABSENCE and self.detection_power is None:
            raise EpistemicStateError(
                "a QUALIFIED_ABSENCE requires declared detection power; a source that has "
                "not said it would have found the thing cannot support a claim that the "
                "thing does not exist (FR-014, contract 03 rule 2). The honest state here is "
                "INFORMATIONAL_ONLY"
            )
        if self.disposition is SearchDisposition.UNREPRESENTABLE:
            if self.query is not QueryAxis.UNRUNNABLE:
                raise EpistemicStateError(
                    "an unrepresentable request did not run, so its query axis is UNRUNNABLE; "
                    "QUERY_UNSUPPORTED and SOURCE_UNAVAILABLE are different failures and "
                    "must not share a record"
                )
            if self.absence is not AbsenceAxis.NOT_APPLICABLE:
                raise EpistemicStateError(
                    "a query that could not be expressed produced no coverage and therefore "
                    "has no absence axis to report; claiming searched_no_result here would say "
                    "we looked when we never could"
                )
        if self.disposition is SearchDisposition.FAILED and (
            self.absence is not AbsenceAxis.INFORMATIONAL_ONLY
        ):
            raise EpistemicStateError(
                "a failed run never saw the world, so its result is INFORMATIONAL_ONLY; a "
                "failed source is the commonest way a manufactured negative enters an "
                "investigation (FR-014)"
            )
        if self.truth_state is not TruthState.NEITHER:
            if self.query is not QueryAxis.RAN_MATCHED:
                raise EpistemicStateError(
                    "support on either side requires a query that actually matched something; "
                    "absence of positive support is not negative support (FR-011)"
                )
            if self.evidence is EvidenceAxis.NONE:
                raise EpistemicStateError(
                    "a determined truth state must say what evidence produced it"
                )
        if self.evidence is EvidenceAxis.CONFLICTED and self.truth_state is not TruthState.BOTH:
            raise EpistemicStateError(
                "conflicted evidence is support on both sides, so truth_state must be BOTH; "
                "collapse to a boolean here is what FR-011 forbids"
            )
        if self.evidence is EvidenceAxis.REFUTED and self.truth_state is not TruthState.FALSE_ONLY:
            raise EpistemicStateError(
                "a refutation is one-sided negative support, so truth_state must be "
                "FALSE_ONLY and not BOTH"
            )
        if self.disposition is SearchDisposition.EXHAUSTED:
            if self.scope is not ScopeAxis.DECLARED:
                raise EpistemicStateError(
                    "saturation is only meaningful against a declared scope; 'we searched a "
                    "lot' over an undeclared universe is not exhaustion (FR-015)"
                )
        elif self.scope is ScopeAxis.DECLARED:
            raise EpistemicStateError(
                "a declared search scope belongs to an exhausted search; attaching it to a "
                "run that stopped early would let a truncated run claim a bounded scope"
            )

    # -- identity ------------------------------------------------------------

    @property
    def fingerprint(self) -> tuple[str, ...]:
        """The six-axis identity. What round-trips, and what two states are compared on."""
        return (
            self.disposition.value,
            self.query.value,
            self.truth_state.value,
            self.absence.value,
            self.evidence.value,
            self.scope.value,
        )

    @property
    def name(self) -> ResearchStateName | None:
        """The anchor-point name for this exact tuple, or ``None`` off the anchors.

        ``None`` is a normal answer, not a failure. ``EXHAUSTED`` + supporting
        evidence is a perfectly good record that no single member of
        :class:`ResearchStateName` describes, and the honest response to "what is its
        name" is "it has none" rather than a label borrowed from a neighbouring state.
        """
        for candidate, axes in _CANO13.items():
            if axes == self.fingerprint:
                return candidate
        return None

    @classmethod
    def for_name(
        cls,
        name: ResearchStateName | str,
        *,
        detection_power: float | None = None,
    ) -> ResearchState:
        """The canonical record for one of the thirteen.

        ``QUALIFIED_ABSENCE`` needs ``detection_power`` and gets no default. That is
        not an ergonomic complaint, it is the rule: the anchor for a qualified absence
        is *"a source that declared it would have found one"*, and supplying the
        declaration's value is the caller's to do or not do. A default here would put
        a number in the record that nobody measured, which is the fabrication this
        module exists to make hard.
        """
        return cls(*_CANO13[ResearchStateName(name)], detection_power=detection_power)

    @classmethod
    def for_detection_power(
        cls,
        *,
        detection_power: float | None,
        coverage: float | None = None,
        extra_limitations: Sequence[str] = (),
        **overrides: Any,
    ) -> ResearchState:
        """A zero-result state, chosen by declared detection power and coverage.

        This is the decision the whole user story turns on, so it is one function with
        one rule and no argument for anything else: an undeclared power gives
        ``INFORMATIONAL_ONLY`` and can only be raised by declaring the power.

        It never produces ``QUALIFIED_ABSENCE``. FR-014 lists six preconditions --
        declared universe, coverage, freshness, capability availability, budget and
        detection power -- and a function with six keyword arguments deciding a
        release-gate claim is the same class of bug one layer up. The ceiling here is
        ``SEARCHED_NO_RESULT``; :meth:`resolve` is the only place that checks all six
        and is therefore the only place that can raise it.

        The missing precondition is named in :attr:`limitations`, so the record says
        *why* it is informational only rather than leaving a reader to guess which
        half of the coverage statement was absent.
        """
        from context.coverage import CoverageThresholds

        thresholds = CoverageThresholds()
        missing: list[str] = [str(item) for item in extra_limitations]
        if detection_power is None:
            missing.append("detection_power not declared")
        elif detection_power < thresholds.min_detection_power:
            missing.append(
                f"detection_power {detection_power:g} below threshold "
                f"{thresholds.min_detection_power:g}"
            )
        if coverage is None:
            missing.append("coverage not declared")
        elif coverage < thresholds.min_coverage:
            missing.append(
                f"coverage {coverage:g} below threshold {thresholds.min_coverage:g}"
            )
        base: dict[str, Any] = {
            "disposition": SearchDisposition.COMPLETED,
            "query": QueryAxis.RAN_ZERO_MATCH,
            "truth_state": TruthState.NEITHER,
            "absence": (
                AbsenceAxis.SEARCHED_NO_RESULT if not missing else AbsenceAxis.INFORMATIONAL_ONLY
            ),
            "evidence": EvidenceAxis.NONE,
            "scope": ScopeAxis.UNDECLARED,
            "detection_power": detection_power,
            "limitations": tuple(missing),
        }
        base.update(overrides)
        return cls(**base)

    # -- derived questions ---------------------------------------------------

    @property
    def may_claim_absence(self) -> bool:
        """Whether this record supports "it does not exist", as opposed to "not seen"."""
        return self.absence is AbsenceAxis.QUALIFIED_ABSENCE

    @property
    def is_inconclusive(self) -> bool:
        return self.truth_state is TruthState.NEITHER

    @property
    def contradiction_required(self) -> bool:
        """§13.3/FR-012: ``BOTH`` obliges the caller to hold a ``Contradiction``."""
        return self.truth_state is TruthState.BOTH

    def as_dict(self) -> dict[str, Any]:
        return {
            "disposition": self.disposition.value,
            "query": self.query.value,
            "truth_state": self.truth_state.value,
            "absence": self.absence.value,
            "evidence": self.evidence.value,
            "scope": self.scope.value,
            "confidence": self.confidence,
            "detection_power": self.detection_power,
            "limitations": list(self.limitations),
            "name": self.name.value if self.name is not None else None,
            #: The one boolean this record carries, and it is derived from the absence
            #: axis alone. Present on the wire so a consumer cannot reach it by
            #: re-deriving the rule -- and derived rather than stored so it cannot drift
            #: from the axis it summarises. :meth:`from_dict` ignores it on the way in,
            #: which is what keeps it a projection rather than a seventh axis.
            "may_claim_absence": self.may_claim_absence,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ResearchState:
        """Rebuild from :meth:`as_dict`. Exact inverse, or it raises.

        A read path that could silently drop an axis would defeat the point of
        holding six of them, so a missing or misspelled key is an error rather than a
        default.
        """
        expected = {
            "disposition",
            "query",
            "truth_state",
            "absence",
            "evidence",
            "scope",
            "confidence",
            "detection_power",
            "limitations",
        }
        missing = expected - set(payload)
        if missing:
            raise EpistemicStateError(
                f"research state is missing axes {sorted(missing)}; a state read back with a "
                "field defaulted is a state that has collapsed"
            )
        return cls(**{key: payload[key] for key in expected})

    # -- resolution ----------------------------------------------------------

    @classmethod
    def resolve(
        cls,
        *,
        source_reachable: bool = True,
        supports_query_kind: bool = True,
        capability_available: bool = True,
        query_executed: bool = True,
        collection_completed: bool = False,
        observations_read: int = 0,
        inconclusive_evidence: bool = False,
        contributions: Sequence[EvidenceContribution] = (),
        detection_power: float | None = None,
        coverage_estimate: float | None = None,
        freshness_declared: bool = True,
        universe_declared: bool = True,
        errors_accounted: bool = True,
        budget_truncated: bool = False,
        exhausted_within_declared_scope: bool = False,
        limitations: Sequence[str] = (),
        confidence: float | None = None,
    ) -> ResearchState:
        """Resolve what a stage actually did into the one record that describes it.

        This is the function the fixture corpus is checked against, so it lives here
        rather than in a test: a test that recomputed the expected answer with its own
        logic would agree with itself no matter what the platform did.

        The decision order is the order in which the claims become weaker, and it is
        fixed:

        1. **Could we have looked at all?** An unreachable source or a request no operator
           can express is a statement about the platform, and it precedes every claim
           about the world.
        2. **Was anything collected, and did a query run?** Neither "nobody has looked" nor
           "the collection ran and produced nothing" is "a query matched nothing", and the
           three are separated here rather than in the caller's arithmetic.
        3. **What do the contributions say?** Through :func:`derive_truth_state`, so this
           shares its admissibility rules rather than restating them.
        4. **Was the run cut short?** A truncated search bounds the search, not the world.
        5. **Is the universe exhausted?** Only then is a declared scope meaningful.
        6. **What may be claimed about absence?** Only from the declared universe,
           coverage, freshness, capability, budget and detection power, in that order.

        ``errors_accounted=False`` forces the absence to informational-only. A search
        whose errors were dropped did not complete, and a completion nobody can account
        for is not a completion.
        """
        notes: list[str] = [str(item) for item in limitations]

        if not source_reachable:
            return cls(
                disposition=SearchDisposition.FAILED,
                query=QueryAxis.NOT_RUN,
                truth_state=TruthState.NEITHER,
                absence=AbsenceAxis.INFORMATIONAL_ONLY,
                evidence=EvidenceAxis.NONE,
                scope=ScopeAxis.UNDECLARED,
                confidence=confidence,
                limitations=(*notes, "source did not respond; nothing was searched"),
            )

        if not supports_query_kind or not capability_available:
            return cls(
                disposition=SearchDisposition.UNREPRESENTABLE,
                query=QueryAxis.UNRUNNABLE,
                truth_state=TruthState.NEITHER,
                absence=AbsenceAxis.NOT_APPLICABLE,
                evidence=EvidenceAxis.NONE,
                scope=ScopeAxis.UNDECLARED,
                confidence=confidence,
                limitations=(
                    *notes,
                    "no operator represents this query; it did not run and matched nothing",
                ),
            )

        if not query_executed:
            # "Nothing has been looked for" and "the collection ran and the subject
            # yielded nothing" share an empty evidence set and are different states.
            # ``collection_completed`` is what tells them apart, and it has to be an
            # input rather than something inferred: a source that was reachable and
            # returned nothing is not evidence that a collection ran over the subject.
            if collection_completed or observations_read:
                return cls(
                    disposition=SearchDisposition.COMPLETED,
                    query=QueryAxis.NOT_RUN,
                    truth_state=TruthState.NEITHER,
                    absence=AbsenceAxis.NOT_APPLICABLE,
                    evidence=EvidenceAxis.NONE,
                    scope=ScopeAxis.UNDECLARED,
                    confidence=confidence,
                    limitations=(
                        *notes,
                        "collection completed; the subject yielded no records",
                    ),
                )
            return cls(
                disposition=SearchDisposition.NOT_INVESTIGATED,
                query=QueryAxis.NOT_RUN,
                truth_state=TruthState.NEITHER,
                absence=AbsenceAxis.NOT_APPLICABLE,
                evidence=EvidenceAxis.NONE,
                scope=ScopeAxis.UNDECLARED,
                confidence=confidence,
                limitations=(*notes, "no query has been run against this question"),
            )

        truth = derive_truth_state(contributions)
        denied = any(item.explicit_denial for item in contributions)

        if truth is TruthState.BOTH:
            evidence = EvidenceAxis.CONFLICTED
        elif truth is TruthState.TRUE_ONLY:
            evidence = EvidenceAxis.OBSERVED
        elif truth is TruthState.FALSE_ONLY:
            evidence = EvidenceAxis.REFUTED if denied else EvidenceAxis.OBSERVED
        else:
            evidence = (
                EvidenceAxis.INCONCLUSIVE
                if (inconclusive_evidence or observations_read)
                else EvidenceAxis.NONE
            )

        # A query either matched something (settling or not) or it matched nothing.
        # Everything below splits on this one question, and the two sides of it are
        # exactly the states FR-010 keeps apart.
        if truth is not TruthState.NEITHER or evidence is not EvidenceAxis.NONE:
            disposition = (
                SearchDisposition.EXHAUSTED
                if exhausted_within_declared_scope
                else SearchDisposition.COMPLETED
            )
            if exhausted_within_declared_scope:
                notes.append("search exhausted within a declared scope")
            return cls(
                disposition=disposition,
                query=QueryAxis.RAN_MATCHED,
                truth_state=truth,
                absence=AbsenceAxis.NOT_APPLICABLE,
                evidence=evidence,
                scope=(
                    ScopeAxis.DECLARED if exhausted_within_declared_scope else ScopeAxis.UNDECLARED
                ),
                confidence=confidence,
                limitations=tuple(notes),
            )

        if budget_truncated:
            notes.append("search was truncated before the universe was exhausted")
            return cls(
                disposition=SearchDisposition.BOUNDED,
                query=QueryAxis.RAN_MATCHED,
                truth_state=TruthState.NEITHER,
                absence=AbsenceAxis.INFORMATIONAL_ONLY,
                evidence=EvidenceAxis.INCONCLUSIVE,
                scope=ScopeAxis.UNDECLARED,
                confidence=confidence,
                limitations=tuple(notes),
            )

        if not errors_accounted:
            notes.append("source errors were not accounted for; the run did not complete")

        base = cls.for_detection_power(
            detection_power=detection_power,
            coverage=coverage_estimate,
            extra_limitations=notes,
        )
        preconditions_met = (
            universe_declared
            and freshness_declared
            and capability_available
            and not budget_truncated
            and errors_accounted
            and detection_power is not None
            and coverage_estimate is not None
            and coverage_estimate >= _COVERAGE_THRESHOLD
            and detection_power >= _DETECTION_THRESHOLD
        )
        scope = (
            ScopeAxis.DECLARED if exhausted_within_declared_scope else ScopeAxis.UNDECLARED
        )
        disposition = (
            SearchDisposition.EXHAUSTED
            if exhausted_within_declared_scope
            else SearchDisposition.COMPLETED
        )
        if not preconditions_met:
            # Saturation and absence strength are two separate questions. An exhausted
            # search over a declared scope is still only ``SEARCHED_NO_RESULT`` when the
            # remaining preconditions are unmet, and conflating the two would let
            # "we finished" stand in for "we finished and may say it does not exist".
            if exhausted_within_declared_scope:
                notes.append("search exhausted within a declared scope")
            return replace(
                base,
                disposition=disposition,
                scope=scope,
                confidence=confidence,
                limitations=tuple(notes),
            )
        # Every FR-014 precondition holds. This is the *only* route to a qualified
        # absence, and it is reached by satisfying six conditions rather than by passing
        # a flag -- a flag would let a caller assert the conclusion directly.
        return replace(
            base,
            disposition=disposition,
            absence=AbsenceAxis.QUALIFIED_ABSENCE,
            scope=scope,
            confidence=confidence,
            limitations=(
                *notes,
                (
                    "universe, coverage, freshness, capability, budget and detection "
                    "power all declared and met"
                ),
            ),
        )


#: A stand-in used *only* by :func:`verify_canonical_states` to prove the qualified-absence
#: anchor is constructible at all. It is not a default, no caller reads it, and no test
#: asserts a detection power from it: the fixture tests pass a power a source declared.
_DECLARED_POWER = 1.0


def verify_canonical_states() -> None:
    """Check the thirteen are total, distinct, and buildable.

    Called at import rather than left to a test, for the same reason the two tables in
    :mod:`contracts.stage_outcome` are checked there: ``assert`` disappears under ``-O``
    and this is load-bearing. Raises :class:`EpistemicStateError` rather than
    ``AssertionError`` because a caller has no reason to special-case the latter.
    """
    if set(_CANO13) != set(ResearchStateName):
        raise EpistemicStateError(
            f"canonical states missing: {sorted(str(n) for n in set(ResearchStateName) - set(_CANO13))}"
        )
    seen: dict[tuple[Any, ...], ResearchStateName] = {}
    for name, axes in _CANO13.items():
        if len(axes) != 6:
            raise EpistemicStateError(
                f"{name} is defined on {len(axes)} axes; the record has six and every one of "
                "them must be stated, or a reader has to guess which was left out"
            )
        if axes in seen:
            raise EpistemicStateError(
                f"{name} and {seen[axes]} share the same dimension tuple "
                f"({[str(a) for a in axes]}) -- two distinct epistemic facts round-trip to one "
                "value, which is the collapse FR-010 forbids"
            )
        seen[axes] = name
        # Construction is the check: a canonical tuple that trips a validation rule is
        # a tuple the thirteen disagree with the record about. Only the qualified
        # absence needs a power; the informational anchors must *not* carry one.
        built = ResearchState.for_name(
            name,
            detection_power=(
                _DECLARED_POWER if AbsenceAxis.QUALIFIED_ABSENCE in axes else None
            ),
        )
        if built.fingerprint != tuple(a.value for a in axes):
            raise EpistemicStateError(
                f"{name} does not round-trip: built {built.fingerprint}, declared "
                f"{[a.value for a in axes]}"
            )
        if built.name is not name:
            raise EpistemicStateError(
                f"{name} reads back as {built.name!r}; a name that does not survive its own "
                "record is not a name"
            )

    # The central refusal, checked here so the table and the rule cannot disagree.
    try:
        ResearchState.for_name(ResearchStateName.QUALIFIED_ABSENCE)
    except EpistemicStateError:
        pass
    else:  # pragma: no cover - guard that must never fire
        raise EpistemicStateError(
            "QUALIFIED_ABSENCE was buildable without declared detection power; the one "
            "inference this module exists to refuse became reachable (FR-014)"
        )




verify_canonical_states()


# ============================================================================
# FR-012 -- contradiction survives; resolution heuristics are recorded, not obeyed
# ============================================================================


class ResolutionHeuristic(enum.StrEnum):
    """The five ways a contradiction gets closed by accident.

    Named because the honest response to each is *the same*: the contradiction stays
    open and the attempt is recorded. FR-012 forbids resolving by recency, document
    count, a single high score or last-write-wins, and FR-011 forbids reading absence
    of positive support as negative support. A module that merely lacked those code
    paths would be one refactor away from having them.
    """

    RECENCY = "recency"
    DOCUMENT_MAJORITY = "document_majority"
    SINGLE_HIGH_SCORE = "single_high_score"
    LAST_WRITE_WINS = "last_write_wins"
    ABSENCE_OF_POSITIVE_AS_NEGATIVE = "absence_of_positive_as_negative"


@dataclass(frozen=True, slots=True)
class ResolutionAttempt:
    """The record of someone trying to close a contradiction, and the refusal.

    ``resolved`` is ``False`` for every value this type can hold. It is a field rather
    than an absence so that a caller cannot pass ``True`` by assertion: the only way to
    obtain ``True`` would be to build the object without the constructor, which is
    what :meth:`attempt_resolution` exists to make unnecessary.
    """

    contradiction_id: str
    declared_state: TruthState
    offered: tuple[ResolutionHeuristic, ...]
    reason: str
    resolved: bool = False
    sides_retained: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "declared_state", TruthState(self.declared_state))
        object.__setattr__(
            self, "offered", tuple(dict.fromkeys(ResolutionHeuristic(h) for h in self.offered))
        )
        if self.resolved:
            raise EpistemicStateError(
                "FR-012: contradiction state is not resolved by recency, document count, a "
                "single high score or last-write-wins; an attempt records which heuristic was "
                "offered and leaves the contradiction open"
            )
        if not self.sides_retained:
            raise EpistemicStateError(
                "FR-012/§0.2: both sides are retained; an attempt that drops one is the "
                "violation this type exists to prevent"
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "contradiction_id": self.contradiction_id,
            "declared_state": self.declared_state.value,
            "resolved": self.resolved,
            "sides_retained": self.sides_retained,
            "ignored_heuristics": [item.value for item in self.offered],
            "reason": self.reason,
        }


def attempt_resolution(
    contradiction: Contradiction,
    *,
    offered: Sequence[ResolutionHeuristic | str] = (),
    declared_state: TruthState | str = TruthState.BOTH,
) -> ResolutionAttempt:
    """Offer a contradiction to a resolution heuristic; it comes back open.

    The ``declared_state`` argument exists so a caller that has been tempted to pass
    ``TRUE_ONLY`` -- because the newest document says so, or because nine of ten say so,
    or because one scored 0.97 -- records the state it was about to assert. The
    returned attempt says ``BOTH``, keeps both sides, and returns; the contradiction
    itself is untouched.
    """
    state = TruthState(declared_state)
    heuristics = tuple(ResolutionHeuristic(item) for item in offered)
    reason = (
        f"contradiction {contradiction.contradiction_id} stays "
        f"{TruthState.BOTH.value}: both sides are retained and "
        + (
            f"{len(heuristics)} resolution heuristic(s) declined "
            f"({', '.join(h.value for h in heuristics)})"
            if heuristics
            else "no resolution heuristic was applied"
        )
        + ". A caller declaring "
        f"{state.value} records what it wanted to assert, not what the platform accepts."
    )
    return ResolutionAttempt(
        contradiction_id=contradiction.contradiction_id,
        declared_state=TruthState.BOTH,
        offered=heuristics,
        reason=reason,
    )


# ============================================================================
# FR-016 / obligation U1 -- fourteen components, never a bare scalar
# ============================================================================


class ScoreComponent(enum.StrEnum):
    """The fourteen action-utility components, quoted from obligation.md and data-model §6.7.

    All fourteen, individually addressable. A composite that folded two of these into
    one number would be unrecoverable -- there is no arithmetic that gets the inputs
    back out of it -- which is why the vector is the stored truth and the scalar is
    derived (U1).
    """

    EXPECTED_INFORMATION_GAIN = "expected_information_gain"
    HYPOTHESIS_DISCRIMINATION = "hypothesis_discrimination"
    RELEVANCE = "relevance"
    SOURCE_QUALITY = "source_quality"
    EVIDENCE_INDEPENDENCE_GAIN = "evidence_independence_gain"
    NOVELTY = "novelty"
    TEMPORAL_FRESHNESS = "temporal_freshness"
    PROBABILITY_OF_SUCCESS = "probability_of_success"
    ESTIMATED_COST = "estimated_cost"
    LATENCY = "latency"
    REPEAT_PENALTY = "repeat_penalty"
    SOURCE_FAILURE_RATE = "source_failure_rate"
    RESOURCE_RISK = "resource_risk"
    POLICY_PENALTY = "policy_penalty"


#: How FR-016's ten named dimensions land on the fourteen.
#:
#: Deliberately partial, and the ``None`` entries are the point. Four of FR-016's ten
#: are one component each. The other six are not score components at all and folding
#: them in is precisely the defect FR-016 is written against: claim support and
#: uncertainty are :class:`TruthState`, identity match is a resolution decision,
#: structural centrality is a candidate-generation input, and action utility is the
#: composite these fourteen constitute. Recording that here means a caller looking for
#: a home for "claim support" finds a refusal rather than a fourth column.
FR016_ROLE_COMPONENT: Mapping[str, ScoreComponent | None] = MappingProxyType(
    {
        "relevance": ScoreComponent.RELEVANCE,
        "source_reliability": ScoreComponent.SOURCE_QUALITY,
        "novelty": ScoreComponent.NOVELTY,
        "freshness": ScoreComponent.TEMPORAL_FRESHNESS,
        "independence": ScoreComponent.EVIDENCE_INDEPENDENCE_GAIN,
        "claim_support": None,
        "identity_match": None,
        "centrality": None,
        "uncertainty": None,
        "action_utility": None,
    }
)


@dataclass(frozen=True, slots=True)
class ScoreVector:
    """The fourteen components, each absent meaning *not measured*.

    ``None`` and ``0.0`` are different facts and are stored differently: ``None`` is
    "nobody measured this", ``0.0`` is "measured, and it is zero". A vector that
    defaulted the unmeasured to zero would report fourteen confident numbers where
    there were three measurements.

    Constructing a vector requires naming components as keyword arguments, so two
    components cannot be supplied to the same field and a typo is a ``TypeError``
    rather than a silently dropped score.
    """

    expected_information_gain: float | None = None
    hypothesis_discrimination: float | None = None
    relevance: float | None = None
    source_quality: float | None = None
    evidence_independence_gain: float | None = None
    novelty: float | None = None
    temporal_freshness: float | None = None
    probability_of_success: float | None = None
    estimated_cost: float | None = None
    latency: float | None = None
    repeat_penalty: float | None = None
    source_failure_rate: float | None = None
    resource_risk: float | None = None
    policy_penalty: float | None = None
    #: U3: an uncalibrated heuristic is labelled as one. A bare number here would be a
    #: number without semantics, which obligation.md calls a fabrication.
    probability_semantics: str = "uncalibrated_score"
    policy_version: str = ""

    def __post_init__(self) -> None:
        for component in ScoreComponent:
            value = getattr(self, component.value)
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise EpistemicStateError(
                    f"{component.value} must be a float or None (not measured), got {value!r}"
                )
            object.__setattr__(self, component.value, float(value))
        if self.probability_of_success is not None and not self.probability_semantics.strip():
            raise EpistemicStateError(
                "U3: probability_of_success carries its semantics; an uncalibrated "
                "heuristic is labelled 'uncalibrated_score', not reported as a bare number"
            )

    def get(self, component: ScoreComponent | str) -> float | None:
        return getattr(self, ScoreComponent(component).value)

    def measured(self) -> tuple[ScoreComponent, ...]:
        """Which components were actually measured, in declaration order."""
        return tuple(c for c in ScoreComponent if getattr(self, c.value) is not None)

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {c.value: getattr(self, c.value) for c in ScoreComponent}
        payload["probability_semantics"] = self.probability_semantics
        payload["policy_version"] = self.policy_version
        return payload

    def composite(self, weights: Mapping[ScoreComponent | str, float], *, policy_version: str) -> CompositeScore:
        """Fold the vector into one number under a **named policy**.

        The result keeps :attr:`vector` and the policy version, so the scalar is always
        traceable back to the fourteen and to the weights that produced it. A composite
        without a ``policy_version`` is refused rather than stored: an unattributed
        scalar cannot be audited, re-derived or invalidated when the policy changes,
        and the whole of U1 is that it must be.
        """
        if not policy_version.strip():
            raise EpistemicStateError(
                "U1/P5: a composite MUST carry the policy version that produced it; an "
                "unattributed scalar cannot be re-derived or invalidated when the policy "
                "changes"
            )
        total = 0.0
        for key, weight in weights.items():
            component = ScoreComponent(key)
            value = getattr(self, component.value)
            if value is None:
                raise EpistemicStateError(
                    f"cannot weigh {component.value} as {weight!r}: it was not measured. "
                    "Dropping it would let an unmeasured component read as a zero and "
                    "silently reweight the rest"
                )
            total += float(weight) * value
        return CompositeScore(
            value=total,
            vector=self,
            weights={ScoreComponent(k): float(v) for k, v in weights.items()},
            policy_version=policy_version.strip(),
        )


@dataclass(frozen=True, slots=True)
class CompositeScore:
    """A scalar that remembers the fourteen and the policy behind it.

    Holding :attr:`vector` by reference is the mechanism, not a convenience: there is
    no constructor path that produces a composite without one, so a composite cannot
    outlive its components.
    """

    value: float
    vector: ScoreVector
    weights: Mapping[ScoreComponent, float]
    policy_version: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "weights", MappingProxyType(dict(self.weights)))
        if not self.policy_version.strip():
            raise EpistemicStateError("a composite must carry its policy version (U1)")
        if not self.weights:
            raise EpistemicStateError("a composite must declare the weights that produced it")

    def as_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "policy_version": self.policy_version,
            "weights": {c.value: w for c, w in sorted(
                self.weights.items(), key=lambda item: item[0].value
            )},
            "components": self.vector.as_dict(),
        }
