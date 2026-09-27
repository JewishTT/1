"""Type-hypothesis and relation-affordance candidate blocking (FR-016, T017, SC-10).

Blocking is the difference between a comparison that costs ten thousand times and one that
costs a hundred. A mention resolves against a candidate universe; the mention's type
hypotheses and the relation operator's domain/range affordances narrow that universe, and the
platform reports what the narrowing bought as a **measurable outcome** -
``before_count``, ``after_count``, ``reduction_ratio`` and the blocking keys used - so the
saving is an observation about a query rather than a claim that a cheap query is possible.

**Pruning asserts nothing.** This is the load-bearing property, and it is structural rather
than a promise in a comment. A pruned candidate is not typed, re-typed, dis-typed or
otherwise annotated by being left out of a result set: it is simply not proposed for
*this* comparison, it stays in the store, and a later query with different hypotheses can
propose it again. Dropping a candidate is not a finding, is not a rejection, and is not
evidence of anything (FR-012). Accordingly this module never constructs a
:class:`~semantic.contracts.TypeAssertion` and does not import that type at all - a
pruned result is not a way to acquire a type, and the absence of the import is what makes
that checkable rather than merely stated. Pruned candidates are returned unchanged as the
original frozen objects in :attr:`BlockingResult.pruned_candidates`, so a caller can verify
byte-for-byte that nothing was written to them.

**Absent knowledge is not contrary knowledge.** The open world is load-bearing here, because
pruning is exactly where an open world gets quietly closed. A candidate with *no* declared kind
is not evidence that it is not organization-like; it is evidence that nobody has said. So the
default :attr:`UnknownKindPolicy.RETAIN` keeps untyped candidates in the result and exposes
``unknown_kind_retained`` as a visible, countable number, and the aggressive
``PRUNE`` policy has to be asked for explicitly. Symmetrically, a candidate that *does* declare
types and shares none of them with the hypotheses is pruned - that is a comparison about
recorded types, not an assertion that it is the wrong type.

**No cross-vocabulary guessing.** Hypotheses and candidate types are matched by normalised
reference only. Aligning a ``SKOS`` term with an ``INTERNAL`` one is a mapping assertion, and
mappings are recorded with provenance (FR-009), never inferred at query time. Two references
that are not recorded as aligned are treated as unrelated, which loses recall and asserts
nothing - the correct trade for a narrowing step.

**Reproducible.** The survivor ordering is canonical - ``(blocking_key, entity_ref)`` - and
independent of the order the candidate universe arrived in, so identical input yields
byte-identical output and a diff between two runs means something changed (constitution VI).
Survivors and pruned candidates are separated by object identity rather than by field
equality, so two distinct universe records that happen to carry identical fields stay two
records instead of one silently vanishing from the report.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from semantic.contracts import SemanticRef, content_key
from semantic.vocabularies import normalize_surface_form, normalize_type_ref

__all__ = [
    "AffordanceLike",
    "BlockingKeyFn",
    "BlockingResult",
    "BlockingStage",
    "Candidate",
    "RelationRole",
    "StageReduction",
    "TypeHypothesis",
    "UnknownKindPolicy",
    "affordance_kinds",
    "block_candidates",
    "block_for_relation",
    "blocking_key",
    "candidate_blocking_key",
    "normalize_kind",
]


def normalize_kind(value: str) -> str:
    """Canonical form of a blocking kind, for comparison only.

    Case-folded and whitespace-trimmed, so an operator that affords ``Person`` and a record
    that carries ``person`` meet. Kinds are coarse affordance classes ("organization-like"),
    not identifiers, so folding their case does not lose anything - unlike
    :func:`~semantic.vocabularies.normalize_type_ref`, which deliberately preserves it.
    """
    return normalize_surface_form(value)


def blocking_key(name: str, kind: str) -> str:
    """The deterministic block key for a normalised name and a normalised kind.

    Two things this key deliberately is **not**. It does not include the entity reference -
    including it would make every candidate its own block, which is the opposite of blocking
    and of any useful comparison cost. And it does not include anything about *why* the two
    candidates might match, because a blocking key is a collision bucket, not a similarity
    judgement: two records sharing this key are worth comparing, which is a question about
    cost and not a conclusion about identity.

    The name is length-prefixed so that no two distinct ``(name, kind)`` pairs can render the
    same key - without it, a name containing the separator would collide with a different
    split of the same characters, and a silent collision in a blocking key is a silently
    wrong comparison set. The form is a pure function of its arguments: no clock, no counter,
    no set iteration order, no locale (constitution VI).
    """
    normalized_name = normalize_surface_form(name)
    return f"{len(normalized_name)}:{normalized_name}|{normalize_kind(kind)}"


class BlockingKeyFn(Protocol):
    """The blocking-key strategy. A caller may substitute a domain-specific one."""

    def __call__(self, candidate: Candidate) -> str:
        """Return the key this candidate is blocked on."""


def candidate_blocking_key(candidate: Candidate) -> str:
    """The default blocking key of a candidate: its normalised name and kind."""
    return blocking_key(candidate.name, candidate.kind)


@dataclass(frozen=True)
class Candidate:
    """One record in a candidate universe, as blocking sees it.

    Frozen, because a candidate is an *input to a comparison*, not a place to record a
    conclusion - if blocking could write to its candidates, "pruning asserts nothing" would be
    a promise rather than a fact. ``kind`` is a coarse affordance class drawn from a relation
    operator's domain/range hints; ``type_refs`` are the concrete types already recorded about
    the record. Both may be empty, and empty means *unrecorded*, never *absent*.
    """

    entity_ref: str
    name: str = ""
    kind: str = ""
    type_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "entity_ref", str(self.entity_ref).strip())
        object.__setattr__(self, "name", str(self.name))
        object.__setattr__(self, "kind", str(self.kind))
        object.__setattr__(self, "type_refs", tuple(sorted(
            {ref for ref in (normalize_type_ref(t) for t in self.type_refs) if ref}
        )))

    def declares_kind(self) -> bool:
        """True when a kind is recorded. ``False`` means unrecorded, not "not organization"."""
        return bool(normalize_kind(self.kind))

    def declares_types(self) -> bool:
        return bool(self.type_refs)

    def shares_type(self, type_refs: frozenset[str]) -> bool:
        """Whether any recorded type of this candidate appears in ``type_refs``.

        A reference match is a *comparison* - "this record has been described as one of the
        things the mention might be" - and stops there. Two records sharing a type reference
        are not thereby the same entity, and nothing here could make them so.
        """
        return bool(frozenset(self.type_refs) & type_refs)

    def content_key(self) -> str:
        """Order-insensitive identity of the candidate as supplied to the comparison."""
        return content_key(
            {
                "entity": self.entity_ref,
                "name": self.name,
                "kind": self.kind,
                "types": list(self.type_refs),
            }
        )


@dataclass(frozen=True)
class TypeHypothesis:
    """One type a mention might be, with the vocabulary it was framed in and how strongly.

    This is a *hypothesis* about an unresolved mention, not a
    :class:`~semantic.contracts.TypeAssertion` about a record: no evidence, no scope, no status
    ladder, and no effect on any record at all. A hypothesis narrows a comparison and is
    discarded with it. ``scheme`` is recorded because the reference is meaningless without it -
    ``internal:Company`` and ``skos:Company`` are different strings that happen to collide -
    and it is recorded rather than resolved, because resolving it is a mapping assertion
    (FR-009).
    """

    type_ref: str
    scheme: SemanticRef = SemanticRef.INTERNAL
    confidence: float = 1.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "type_ref", str(self.type_ref).strip())
        object.__setattr__(self, "scheme", SemanticRef(self.scheme))
        object.__setattr__(self, "confidence", float(self.confidence))

    def reference(self) -> str:
        """The normalised reference this hypothesis blocks on."""
        return normalize_type_ref(self.type_ref)


class UnknownKindPolicy(StrEnum):
    """What to do with a candidate that records no kind at all.

    ``RETAIN`` is the default because pruning on an absent fact is an assertion by omission:
    the platform would be deciding "this is not organization-like" from "nobody typed it".
    ``PRUNE`` is available for callers who have already established that every record in the
    universe is typed, and its effect is reported separately in
    ``BlockingResult.unknown_kind_pruned`` so a caller can see whether it mattered.
    """

    RETAIN = "retain"
    PRUNE = "prune"


class RelationRole(StrEnum):
    """Which end of a relation an affordance applies to."""

    SUBJECT = "subject"
    OBJECT = "object"


class AffordanceLike(Protocol):
    """The part of a relation operator blocking reads: its declared endpoint kinds.

    Structural on purpose. :class:`semantic.operators.RelationOperator` satisfies it, but
    blocking does not import that module - the affordance contract is two fields wide and
    depending on the protocol keeps the narrowing step free of any cycle risk between
    operator definitions and vocabulary lookup.
    """

    subject_kinds: tuple[str, ...]
    object_kinds: tuple[str, ...]


class BlockingStage(StrEnum):
    """The narrowing steps, in the order they are applied and reported."""

    KIND = "kind"
    TYPE = "type"
    NAME = "name"

    def rank(self) -> int:
        return _STAGE_RANK[self]


_STAGE_RANK: dict[BlockingStage, int] = {
    BlockingStage.KIND: 0,
    BlockingStage.TYPE: 1,
    BlockingStage.NAME: 2,
}


@dataclass(frozen=True)
class StageReduction:
    """What one narrowing step cost and what it bought, in counts.

    Reported per stage because a single ratio hides which step did the work, and "blocking
    reduced the candidate set 99%" is only actionable if you can see that the type hypothesis
    did it and the name match did not.
    """

    stage: BlockingStage
    before_count: int
    after_count: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "stage", BlockingStage(self.stage))

    @property
    def pruned_count(self) -> int:
        return max(self.before_count - self.after_count, 0)

    @property
    def ratio(self) -> float:
        """Fraction pruned by this stage alone; ``0.0`` when there was nothing to prune."""
        if self.before_count <= 0:
            return 0.0
        return self.pruned_count / self.before_count


@dataclass(frozen=True)
class BlockingResult:
    """The measured outcome of one blocking operation.

    ``before_count`` and ``after_count`` are the universe sizes, ``reduction_ratio`` the
    fraction pruned (``1.0`` means everything, ``0.0`` means nothing or an empty universe),
    and ``stage_reductions`` attributes the saving to individual steps. ``blocking_keys`` are
    the distinct keys that selected the survivors and ``scanned_keys`` the distinct keys
    present in the input universe, so the two can be compared to see whether the saving came
    from narrowing or merely from a key function that collides.

    ``candidates`` is canonically ordered by ``(blocking_key, entity_ref)`` and so is
    ``pruned_candidates``; both are independent of the order the universe arrived in.
    ``pruned_candidates`` holds the *original* frozen objects, unaltered, and is the point at
    which "pruning asserts nothing" becomes something a caller can verify rather than take on
    trust.
    """

    before_count: int
    after_count: int
    candidates: tuple[Candidate, ...] = ()
    pruned_candidates: tuple[Candidate, ...] = ()
    blocking_keys: tuple[str, ...] = ()
    scanned_keys: tuple[str, ...] = ()
    stage_reductions: tuple[StageReduction, ...] = ()
    type_hypotheses: tuple[TypeHypothesis, ...] = ()
    allowed_kinds: tuple[str, ...] = ()
    query_name: str = ""
    unknown_kind_policy: UnknownKindPolicy = UnknownKindPolicy.RETAIN
    unknown_kind_retained: int = 0
    unknown_kind_pruned: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidates", tuple(self.candidates))
        object.__setattr__(self, "pruned_candidates", tuple(self.pruned_candidates))
        object.__setattr__(self, "blocking_keys", tuple(self.blocking_keys))
        object.__setattr__(self, "scanned_keys", tuple(self.scanned_keys))
        object.__setattr__(
            self,
            "stage_reductions",
            tuple(sorted(self.stage_reductions, key=lambda step: step.stage.rank())),
        )
        object.__setattr__(
            self,
            "type_hypotheses",
            tuple(sorted(self.type_hypotheses, key=lambda item: (item.type_ref, str(item.scheme)))),
        )
        object.__setattr__(self, "allowed_kinds", tuple(self.allowed_kinds))
        object.__setattr__(self, "unknown_kind_policy", UnknownKindPolicy(self.unknown_kind_policy))

    @property
    def pruned_count(self) -> int:
        return max(self.before_count - self.after_count, 0)

    @property
    def reduction_ratio(self) -> float:
        """Fraction of the universe this operation did not propose, in ``0.0..1.0``.

        ``0.0`` for an empty universe as well as for no pruning: "we pruned nothing we had"
        and "there was nothing" both mean there is no saving to report, and reporting ``0/0``
        as a number would invent one.
        """
        if self.before_count <= 0:
            return 0.0
        return self.pruned_count / self.before_count

    @property
    def reduction_factor(self) -> float | None:
        """How many times smaller the comparison set became; ``None`` when nothing was left."""
        if self.after_count <= 0:
            return None
        return self.before_count / self.after_count

    @property
    def pruned_refs(self) -> tuple[str, ...]:
        """References excluded from this comparison only - not deleted, not re-typed, not failed."""
        return tuple(candidate.entity_ref for candidate in self.pruned_candidates)

    def __contains__(self, entity_ref: object) -> bool:
        return any(candidate.entity_ref == str(entity_ref) for candidate in self.candidates)

    def stage(self, stage: BlockingStage) -> StageReduction | None:
        """One stage's reduction, or ``None`` when that narrowing did not run."""
        wanted = BlockingStage(stage)
        return next(
            (step for step in self.stage_reductions if step.stage is wanted),
            None,
        )

    def content_key(self) -> str:
        """Identity of the whole operation, via the shared canonical-JSON convention.

        Same universe, same hypotheses, same policy gives the same digest regardless of
        arrival order, which is what makes a blocking run reproducible from its record.
        """
        return content_key(
            {
                "before": self.before_count,
                "after": self.after_count,
                "candidates": [candidate.content_key() for candidate in self.candidates],
                "pruned": [candidate.content_key() for candidate in self.pruned_candidates],
                "keys": list(self.blocking_keys),
                "scanned": list(self.scanned_keys),
                "stages": [
                    [str(step.stage), step.before_count, step.after_count]
                    for step in self.stage_reductions
                ],
                "hypotheses": [
                    [item.type_ref, str(item.scheme), item.confidence]
                    for item in self.type_hypotheses
                ],
                "allowed_kinds": list(self.allowed_kinds),
                "query_name": self.query_name,
                "policy": str(self.unknown_kind_policy),
            }
        )


def affordance_kinds(operator: AffordanceLike | None, role: RelationRole) -> tuple[str, ...]:
    """The endpoint kinds a relation operator affords, canonically ordered.

    An operator that declares nothing affords nothing, and this returns ``()`` - which means
    "no narrowing", not "nothing matches". A relation with no domain/range hints is still a
    perfectly good relation (FR-013), and blocking must not read the absence of a hint as a
    restriction.
    """
    if operator is None:
        return ()
    declared = (
        operator.subject_kinds
        if RelationRole(role) is RelationRole.SUBJECT
        else operator.object_kinds
    )
    if isinstance(declared, str):
        declared = (declared,)
    return tuple(sorted({normalize_kind(kind) for kind in declared if str(kind).strip()}))


def block_candidates(
    candidates: Iterable[Candidate],
    type_hypotheses: Iterable[TypeHypothesis] = (),
    allowed_kinds: Iterable[str] = (),
    *,
    query_name: str | None = None,
    min_confidence: float = 0.0,
    unknown_policy: UnknownKindPolicy = UnknownKindPolicy.RETAIN,
    key_fn: Callable[[Candidate], str] = candidate_blocking_key,
) -> BlockingResult:
    """Narrow a candidate universe, and report exactly how much that cost and saved (FR-016).

    Three independent narrowings run in order, each one skipped when it has nothing to say -
    a stage with no hypotheses, no afforded kinds or no name query is not run and is not
    reported, so a reduction of ``0.0`` unambiguously means "no narrowing was even attempted"
    rather than "every narrowing failed":

    * ``KIND`` keeps candidates whose kind is afforded by the relation operator. This is
      "person-like mentions only block against person-like candidates" (US7).
    * ``TYPE`` keeps candidates sharing at least one recorded type reference with the
      mention's hypotheses, in any vocabulary the hypothesis set spans.
    * ``NAME`` keeps candidates whose normalised name equals the query's, which is the actual
      blocking operation - everything above it is pre-filtering so that this comparison is
      cheap.

    Ordering is canonical and input-order-independent: survivors are sorted by
    ``(blocking_key, entity_ref)``, so identical input yields identical output. Nothing about
    a candidate changes: see the module docstring, and note that this function has no way to
    attach a type even if it wanted to.
    """
    policy = UnknownKindPolicy(unknown_policy)
    hypotheses = _ordered_hypotheses(type_hypotheses, float(min_confidence))
    hypothesis_refs = frozenset(
        hypothesis.reference() for hypothesis in hypotheses if hypothesis.reference()
    )
    kinds = tuple(sorted({normalize_kind(kind) for kind in allowed_kinds if str(kind).strip()}))

    universe = tuple(candidates)
    order = sorted(universe, key=lambda candidate: (key_fn(candidate), candidate.entity_ref))

    kept = order
    steps: list[StageReduction] = []
    unknown_retained = 0
    unknown_pruned = 0

    if kinds:
        unknown_retained = sum(1 for candidate in kept if not candidate.declares_kind())
        before = len(kept)
        kept = tuple(
            candidate
            for candidate in kept
            if normalize_kind(candidate.kind) in kinds
            or (policy is UnknownKindPolicy.RETAIN and not candidate.declares_kind())
        )
        if policy is UnknownKindPolicy.PRUNE:
            unknown_pruned = unknown_retained
        steps.append(StageReduction(BlockingStage.KIND, before, len(kept)))

    if hypothesis_refs:
        before = len(kept)
        kept = tuple(
            candidate
            for candidate in kept
            if not candidate.declares_types() or candidate.shares_type(hypothesis_refs)
        )
        steps.append(StageReduction(BlockingStage.TYPE, before, len(kept)))

    wanted_name = normalize_surface_form(query_name) if query_name is not None else ""
    if wanted_name:
        before = len(kept)
        kept = tuple(
            candidate
            for candidate in kept
            if normalize_surface_form(candidate.name) == wanted_name
        )
        steps.append(StageReduction(BlockingStage.NAME, before, len(kept)))

    survivors = tuple(candidate for candidate in kept)
    kept_ids = {id(candidate) for candidate in survivors}
    pruned = tuple(candidate for candidate in order if id(candidate) not in kept_ids)

    return BlockingResult(
        before_count=len(universe),
        after_count=len(survivors),
        candidates=survivors,
        pruned_candidates=pruned,
        blocking_keys=tuple(sorted({key_fn(candidate) for candidate in survivors})),
        scanned_keys=tuple(sorted({key_fn(candidate) for candidate in universe})),
        stage_reductions=tuple(steps),
        type_hypotheses=hypotheses,
        allowed_kinds=kinds,
        query_name=query_name or "",
        unknown_kind_policy=policy,
        unknown_kind_retained=unknown_retained,
        unknown_kind_pruned=unknown_pruned,
    )


def block_for_relation(
    candidates: Iterable[Candidate],
    type_hypotheses: Iterable[TypeHypothesis] = (),
    operator: AffordanceLike | None = None,
    role: RelationRole = RelationRole.OBJECT,
    *,
    query_name: str | None = None,
    min_confidence: float = 0.0,
    unknown_policy: UnknownKindPolicy = UnknownKindPolicy.RETAIN,
    key_fn: Callable[[Candidate], str] = candidate_blocking_key,
) -> BlockingResult:
    """:func:`block_candidates` with the relation's own affordances as the kind filter.

    The convenience wiring for US7: "person-like mentions only block against person-like
    candidates" is not something each caller should re-derive from the operator, and a caller
    that re-derived it could re-derive it wrongly. ``role`` picks the end that applies -
    ``OBJECT`` is the default because the expensive, most often pruned side of a relation is
    its object. An operator with no declared kinds simply narrows by type and name.
    """
    return block_candidates(
        candidates,
        type_hypotheses,
        affordance_kinds(operator, role),
        query_name=query_name,
        min_confidence=min_confidence,
        unknown_policy=unknown_policy,
        key_fn=key_fn,
    )


def _ordered_hypotheses(
    type_hypotheses: Iterable[TypeHypothesis], min_confidence: float
) -> tuple[TypeHypothesis, ...]:
    """Hypotheses above the confidence floor, most confident first then canonically by ref.

    Ordering is total and value-based rather than insertion-based so that the recorded
    hypothesis list - and therefore the result's content key - cannot depend on the order a
    caller happened to build its hypotheses in.
    """
    unique: dict[tuple[str, str], TypeHypothesis] = {}
    for hypothesis in type_hypotheses:
        if hypothesis.confidence < min_confidence or not hypothesis.type_ref.strip():
            continue
        unique.setdefault((hypothesis.type_ref, str(hypothesis.scheme)), hypothesis)
    return tuple(
        sorted(
            unique.values(),
            key=lambda hypothesis: (
                -hypothesis.confidence,
                hypothesis.type_ref,
                str(hypothesis.scheme),
            ),
        )
    )
