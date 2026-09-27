"""The epistemic state of a predicate: what was said, and whether we know what it means.

Feature 019, CD-6. This module exists because of one contradiction the previous
features could not express: the platform is required to preserve a relation whose
type nobody declares, and :class:`domain.relation_candidate.RelationCandidate`
required a :class:`semantic.contracts.RelationRef` to be constructed at all.

The tempting fix is a registry sentinel — an ``UNKNOWN_RELATION`` concept minted so
the unknown predicate has somewhere to point. That fix is wrong, and it is worth
saying why rather than only doing it: a sentinel makes unknown semantics into known
vocabulary, which is precisely the inversion this platform was built to prevent. The
next reader to look would find a concept and conclude the system understood the
relation. So unknown stays unknown, structurally, by having no ref at all.

A predicate therefore has three separable parts, and conflating them is what forced
the ref to be mandatory:

* the **surface** — what the observation actually said (``"originator of"``). Always
  available when the relation was read from anything at all, and the part that must
  survive regardless of what the platform later understands.
* the **resolution** — zero, one, or several operator refs, plus the state describing
  how confident that resolution is.
* the **evidence** for the resolution, so re-evaluating a mapping later is possible
  without re-reading the source.

Four states are durably representable and lossy in none of them::

    known       "works for"                  → ref = employment, no alternatives
    unknown     "originator of"              → ref = None,  surface retained
    ambiguous   "associated with"            → ref = ownership, alternatives = 2 more
    conflicting signal A → ownership, signal B → control

``unknown`` and ``ambiguous`` are the two that the old model could not express, and
they are the two that matter: the first is a relation nobody has named, the second is
a relation with several defensible names. Both are hypotheses, and both must reach a
durable candidate (CD-7, FR-024, SC-D).

The boundary this type draws is deliberate. A predicate hypothesis may have no ref; a
:class:`~domain.relation_claim_material.RelationClaimMaterial` may not. That is not
an inconsistency in the typing, it is the line between an open-world hypothesis
substrate and an admitted semantic assertion, and it is where the two are supposed to
meet.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

from semantic.contracts import RelationRef, content_key

__all__ = [
    "PREDICATE_PREFIX",
    "PredicateContractError",
    "PredicateHypothesis",
    "PredicateResolutionState",
]

#: A local namespace for predicates nobody has mapped. Prefixed rather than bare so
#: a bare word can never be mistaken for a resolved operator type.
PREDICATE_PREFIX = "local:predicate:"


class PredicateContractError(ValueError):
    """A predicate hypothesis is not coherent as stated.

    Carries a stable ``code`` like every other contract error in this package, so a
    caller can distinguish "we do not know what this relation is" (not an error at
    all, and never raised) from "this hypothesis asserts nothing whatsoever" (an
    error, because a relation hypothesis with neither a surface nor a ref describes
    nothing).
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message


class PredicateResolutionState(StrEnum):
    """How far the platform's vocabulary goes on a predicate.

    ``KNOWN`` is the only state that means the platform understands the relation.
    The other three are all legitimate outcomes, and collapsing any of them into
    ``UNKNOWN`` would lose a distinction a reader can act on: ``AMBIGUOUS`` has
    candidates to choose between, ``CONFLICTING`` has observations that disagree, and
    ``UNKNOWN`` has nothing at all.

    Who sets ``CONFLICTING`` rather than ``AMBIGUOUS`` is the assembler's judgement
    (they differ in whether the competing readings came from one reading or from
    disagreeing evidence), so this enum validates only what is checkable here and
    leaves that choice to the caller.
    """

    KNOWN = "known"
    UNKNOWN = "unknown"
    AMBIGUOUS = "ambiguous"
    CONFLICTING = "conflicting"


#: States that require at least one operator ref. A hypothesis in one of these knows
#: something; ``UNKNOWN`` is the only state that legitimately has none.
_RESOLVED_STATES = frozenset(
    {
        PredicateResolutionState.KNOWN,
        PredicateResolutionState.AMBIGUOUS,
        PredicateResolutionState.CONFLICTING,
    }
)


@dataclass(frozen=True)
class PredicateHypothesis:
    """One reading of a predicate: its surface, its resolution, and the evidence for it.

    :attr:`resolution_state` is derived from the refs unless it is explicitly
    ``CONFLICTING``. The asymmetry is intentional and worth knowing: a caller claiming
    ``KNOWN`` beside two alternatives is *corrected* to ``AMBIGUOUS``, because the refs
    already say so and the caller's label adds nothing, whereas a caller claiming
    ``CONFLICTING`` with no ref is *refused*, because that state records something the
    refs cannot — that the competing readings came from disagreeing observations — and
    overriding it would discard the only trace of the disagreement.

    A bare string at :attr:`relation_ref` is **refused**, and a bare string at
    :attr:`alternative_refs` is accepted as a type. That is not an inconsistency: the
    primary ref is the one position where a string might be an unresolved surface, and
    ``"owner of"`` and ``"works_for"`` are indistinguishable by shape, so the platform
    would be guessing. Guessing here means inventing an operator type, which is the one
    thing constitution 4 forbids outright. An alternative, by contrast, is by definition a
    type already being offered, so there is nothing to guess.

    The two legitimate ways to say "a relation, typed" and "a relation, not yet typed" are
    therefore :attr:`relation_ref` (a :class:`RelationRef`) and :attr:`surface_form` (the
    words), and a reader who wants to know which is present should ask
    :attr:`is_resolved` rather than test either field for truthiness.
    """

    surface_form: str = ""
    normalized_form: str = ""
    relation_ref: RelationRef | None = None
    alternative_refs: tuple[RelationRef, ...] = ()
    resolution_state: PredicateResolutionState | None = None
    mapping_evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "relation_ref",
            _coerce_primary_ref(self.relation_ref),
        )
        object.__setattr__(self, "surface_form", str(self.surface_form or ""))
        object.__setattr__(
            self, "normalized_form", str(self.normalized_form or self.surface_form or "")
        )
        object.__setattr__(
            self,
            "alternative_refs",
            tuple(
                dict.fromkeys(
                    r
                    for r in (
                        _coerce_alternative_ref(x) for x in self.alternative_refs
                    )
                    if r
                )
            ),
        )
        object.__setattr__(
            self,
            "resolution_state",
            _resolve_state(self.resolution_state, self.relation_ref, self.alternative_refs),
        )
        object.__setattr__(
            self,
            "mapping_evidence_refs",
            tuple(sorted({str(r) for r in self.mapping_evidence_refs if str(r).strip()})),
        )
        if self.relation_ref is not None and self.relation_ref in self.alternative_refs:
            raise PredicateContractError(
                "predicate_ref_in_alternatives",
                f"relation_ref {self.relation_ref} is also listed as an alternative; the "
                "primary reading and the alternatives must be distinguishable",
            )
        if self.resolution_state in _RESOLVED_STATES and self.relation_ref is None:
            raise PredicateContractError(
                "predicate_resolution_without_ref",
                f"resolution_state={self.resolution_state} asserts the platform resolved "
                "this predicate, so a relation_ref is required",
            )
        if (
            self.resolution_state is PredicateResolutionState.UNKNOWN
            and self.relation_ref is not None
        ):
            raise PredicateContractError(
                "predicate_unknown_with_ref",
                f"resolution_state=unknown means nothing was resolved, but "
                f"{self.relation_ref!r} is a resolved operator type; use ambiguous or "
                "conflicting if the platform has candidates",
            )
        if not self.surface_form and self.relation_ref is None:
            raise PredicateContractError(
                "predicate_asserts_nothing",
                "a predicate hypothesis needs a surface form, a relation_ref, or both; "
                "this one describes no predicate at all",
            )

    @classmethod
    def from_candidate_field(cls, value: object) -> PredicateHypothesis:
        """Build from whatever a call site used to put in ``relation_ref``.

        The three shapes that have ever appeared at that position — a ``RelationRef``,
        a raw string, and ``None`` — are all accepted, so a candidate constructed under
        the old contract keeps its meaning instead of failing to load.
        """
        if isinstance(value, PredicateHypothesis):
            return value
        if value is None:
            return cls()
        if isinstance(value, str):
            return cls(surface_form=value)
        return cls(relation_ref=RelationRef(value))  # type: ignore[arg-type]

    @property
    def is_resolved(self) -> bool:
        """Whether the platform knows at least one operator type for this predicate."""
        return self.relation_ref is not None

    @property
    def all_refs(self) -> tuple[RelationRef, ...]:
        """Primary first, then alternatives in declaration order."""
        return (() if self.relation_ref is None else (self.relation_ref,)) + self.alternative_refs

    def with_alternatives(self, *refs: RelationRef) -> PredicateHypothesis:
        """Add competing readings, promoting the state when the surface was unknown.

        The promotion is the point: a signal set that first knew nothing and then
        accumulated a second reading is ``ambiguous``, not ``unknown``. Forcing a
        caller to recompute the state by hand is how a hypothesis ends up claiming it
        is unknown while carrying two refs.
        """
        state = self.resolution_state
        if state is PredicateResolutionState.UNKNOWN and self.relation_ref is not None:
            state = PredicateResolutionState.AMBIGUOUS
        return replace(
            self,
            alternative_refs=self.alternative_refs + tuple(refs),
            resolution_state=state,
        )

    def with_conflict(self, *refs: RelationRef) -> PredicateHypothesis:
        """Record that competing readings came from *disagreeing* evidence.

        Distinct from :meth:`with_alternatives` on purpose: several names for one
        observation is ambiguity, while several names asserted by observations that
        contradict each other is a conflict, and a reader reconstructing why a
        hypothesis stalled needs to tell those apart.
        """
        return replace(
            self,
            alternative_refs=self.alternative_refs + tuple(refs),
            resolution_state=PredicateResolutionState.CONFLICTING,
        )

    def as_surface(self) -> str:
        """The surface a producer would have written, whichever resolution state this is.

        The point of the whole module in one method: even a fully resolved predicate
        still reports the words that produced it, so a reader can compare a relation's
        meaning against what the document actually said.
        """
        return self.surface_form or (str(self.relation_ref) if self.relation_ref else "")

    def content_key(self) -> str:
        """Order-insensitive digest of the whole reading."""
        return content_key(
            {
                "surface": self.surface_form,
                "normalized": self.normalized_form,
                "ref": str(self.relation_ref) if self.relation_ref else "",
                "alternatives": [str(r) for r in self.alternative_refs],
                "state": str(self.resolution_state),
                "evidence": list(self.mapping_evidence_refs),
            }
        )

    def with_id(self) -> PredicateHypothesis:
        """A copy carrying its own content address, if it has none.

        No id field on this type: the predicate is part of the candidate's identity
        material rather than a separately addressable object, and a half-stable id here
        would invite someone to treat it as one.
        """
        return self


def _resolve_state(
    stated: PredicateResolutionState | str | None,
    relation_ref: RelationRef | None,
    alternative_refs: tuple[RelationRef, ...],
) -> PredicateResolutionState:
    """Derive the resolution state, honouring an explicit ``CONFLICTING`` and nothing else.

    The state is derived rather than demanded because the three common answers are
    already implied by the refs: nothing is ``unknown``, one is ``known``, several are
    ``ambiguous``. A caller who had to pass the state would have to restate what the
    arguments say, and every restatement is a chance to say it wrong — a hypothesis with
    two refs and a state of ``unknown`` is a contradiction a reader would have to detect
    for themselves.

    ``CONFLICTING`` is the exception and must be explicit, because it records something
    the refs cannot: that the competing readings came from *disagreeing observations*
    rather than from one reading with several defensible names.
    """
    if (
        stated is not None
        and PredicateResolutionState(stated) is PredicateResolutionState.CONFLICTING
    ):
        return PredicateResolutionState.CONFLICTING
    if relation_ref is None:
        return PredicateResolutionState.UNKNOWN
    if alternative_refs:
        return PredicateResolutionState.AMBIGUOUS
    return PredicateResolutionState.KNOWN


def _coerce_primary_ref(value: object) -> RelationRef | None:
    """Coerce the *primary* ref position, refusing a bare string.

    A string here is refused rather than read as a type, and the reason is that the two
    readings are indistinguishable by shape: ``"owner of"`` and ``"works_for"`` are both
    strings, and only the caller knows which was meant. Choosing for them would mean
    inventing an operator type in the one case where the platform has not earned one,
    which is a committed falsehood about the world wearing a reference's clothing.

    So the caller states which they mean. ``RelationRef("works_for")`` is a type.
    ``surface_form="owner of"`` is an unresolved relation, preserved as words. The
    refusal exists to make that choice explicit, and its message says where to put the
    other one, because a gate that only says "no" is a gate people route around by
    guessing.

    Legacy data whose provenance really is unknown is handled where that fact is
    knowable: :meth:`PredicateHypothesis.from_candidate_field` reads a string of unknown
    origin as a **surface**, and that is the only place in this module permitted to guess.
    """
    if value is None or value == "":
        return None
    if isinstance(value, RelationRef):
        return value
    if isinstance(value, str):
        raise PredicateContractError(
            "predicate_string_ref_refused",
            f"relation_ref={value!r} is a bare string, and the platform cannot tell whether it "
            "is a relation type or an unresolved surface - it will not guess, because guessing "
            f"here would fabricate an operator. If it is a type, wrap it: "
            f"RelationRef({value!r}). If it is a surface the vocabulary has no entry for, pass "
            f"surface_form={value!r} and leave relation_ref None, which is what CD-6 means by "
            "an unknown predicate.",
        )
    raise PredicateContractError(
        "predicate_ref_type",
        f"relation_ref must be a RelationRef or None; got {type(value).__name__}",
    )


def _coerce_alternative_ref(value: object) -> RelationRef | None:
    """Coerce an alternative ref, accepting a bare string as a type.

    Here the string is unambiguous. An alternative is by definition a type the caller is
    *offering* as a competing reading, so there is no unresolved surface it could be
    mistaken for and nothing to guess.
    """
    if value is None or value == "":
        return None
    if isinstance(value, RelationRef):
        return value
    if isinstance(value, str):
        return RelationRef(value)
    raise PredicateContractError(
        "predicate_alternative_ref_type",
        f"an alternative ref must be a RelationRef, a relation-type string, or None; got "
        f"{type(value).__name__}",
    )
