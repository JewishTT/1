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
"""

from __future__ import annotations

import enum
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
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
