"""The query intent AST (Appendix O.1) -- one canonical form for a search request.

FR-025-050 requires that natural-language queries compile to a common AST; FR-025-051
that a deterministic grammar exists for supported queries; FR-025-052 that any LLM
compilation is subordinate. This module is that common form. Everything else is a way
of *producing* a ``QueryAST``: the structured grammar in :mod:`context.query_grammar`
and any natural-language adapter both emit this and nothing else, which is what makes
"the NL adapter yields an equivalent AST" a checkable claim rather than a hope.

Three properties are load-bearing, and each costs something to keep:

**The AST is content-addressed.** ``ast_id`` is a digest over the semantic material, so
two requests that mean the same thing are the same node. That is what lets a frontier
obligation point at "the query" rather than at a paraphrase of it, and it is what makes
a replayed pass comparable against the pass it replays.

**Unresolved terms survive compilation.** §32.1 says the compiler must preserve
unresolved cases rather than silently dropping them, and Appendix O's ``target.concept``
is a *concept*, not a string. A term the registry cannot bind is recorded in
``unresolved`` with the reason, and the AST still compiles. Dropping it would produce a
narrower query that looks like an answer; keeping it turns the gap into an obligation.

**A universal request is marked, never granted.** Appendix P requires every query that
implies universality to be checked, and forbids claiming literal completeness the
coverage model cannot support. ``QueryAST`` therefore records ``requested_mode`` as a
*request* and leaves ``feasible_mode`` to
:func:`context.completeness.assess_completeness`, which derives it from conditions. The
AST cannot assert a completeness it has not earned.

The AST is pure data. It reads no store, resolves no registry, and executes nothing --
that is :mod:`context.query_binding`, which takes an AST plus the outside world and
returns a plan.
"""

from __future__ import annotations

import enum
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from context.completeness import (
    Objective,
    QueryIntent,
    RequestedMode,
    Target,
    TemporalMode,
    implies_universal,
)
from context.locality import _digest


class QueryVerb(enum.StrEnum):
    """Appendix O's ``verb`` production. The verb decides the output shape, not the search."""

    FIND = "find"
    SHOW = "show"
    COMPARE = "compare"
    EXPLAIN = "explain"
    TRACE = "trace"
    DETECT = "detect"


class FilterOperator(enum.StrEnum):
    """Appendix O's ``operator`` production."""

    EQ = "="
    GT = ">"
    GTE = ">="
    LT = "<"
    LTE = "<="
    CONTAINS = "contains"
    IN = "in"
    NOT_EQ = "!="


class UniverseScope(enum.StrEnum):
    """Appendix O's ``scope.universe``.

    Deliberately distinct from :class:`context.completeness.UniverseDefinition`: that
    enum names *how* completeness is judged, this one names *what is searched*. A query
    can search the registered catalogue and still fail the conditions for claiming
    enumeration over it, and collapsing the two would make the failure unreachable.
    """

    REGISTERED_CHAIN_SOURCES = "registered_chain_sources"
    REGISTERED_CATALOGUE = "registered_catalogue"
    AVAILABLE_SOURCES = "available_sources"
    EXPLICIT_UNIVERSE = "explicit_universe"


#: What a result carries back. Appendix O's ``output.include``; the default set is the
#: one §33.1 says a global result must expose, so a caller cannot accidentally return a
#: bare confident array.
DEFAULT_OUTPUT_INCLUDE: tuple[str, ...] = (
    "subject",
    "supporting_evidence",
    "coverage",
    "blind_spots",
    "contradictions",
    "qualified_absences",
)


@dataclass(frozen=True, slots=True)
class Filter:
    """One ``constraint`` from Appendix O: a field, an operator, a value.

    ``value`` stays untyped on purpose. The grammar accepts ``>= 1000000``, and turning
    that into a float here would lose ``USD``, which is a separate ``unit`` field precisely
    because a magnitude without a currency is not a constraint. ``numeric_value`` offers
    the float when a planner needs one, and returns ``None`` when there is not one rather
    than coercing a string to ``0.0`` -- FR-025-064.
    """

    field: str
    operator: FilterOperator
    value: Any = None
    unit: str = ""

    def __post_init__(self) -> None:
        if not self.field:
            raise ValueError("a filter must name the field it constrains")
        object.__setattr__(self, "operator", FilterOperator(self.operator))
        if self.operator in (FilterOperator.IN, FilterOperator.CONTAINS) and not isinstance(
            self.value, (list, tuple, set, frozenset)
        ):
            raise ValueError(
                f"{self.operator.value} needs a collection; "
                f"{self.value!r} is a single value"
            )
        if self.operator not in (FilterOperator.IN, FilterOperator.CONTAINS) and isinstance(
            self.value, (list, tuple, set, frozenset)
        ):
            raise ValueError(
                f"{self.operator.value} compares against one value; "
                f"{self.value!r} is a collection"
            )

    @property
    def numeric_value(self) -> float | None:
        """The value as a number, or ``None`` when it is not one."""
        if isinstance(self.value, bool):
            return None
        if isinstance(self.value, (int, float)):
            return float(self.value)
        return None

    def as_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "operator": self.operator.value,
            "value": list(self.value)
            if isinstance(self.value, (set, frozenset, tuple))
            else self.value,
            "unit": self.unit,
        }


@dataclass(frozen=True, slots=True)
class TemporalClause:
    """Appendix O's ``temporal``. ``mode`` decides which of the bounds mean anything."""

    mode: TemporalMode = TemporalMode.CURRENT
    timestamp: str = ""
    start: str = ""
    end: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "mode", TemporalMode(self.mode))
        if self.mode is TemporalMode.AS_OF and not self.timestamp:
            raise ValueError("AS_OF needs the timestamp it is as of")
        if self.mode is TemporalMode.INTERVAL and not (self.start or self.end):
            raise ValueError("INTERVAL needs at least one bound")

    @property
    def is_defined(self) -> bool:
        """Appendix P's ``temporal_scope_defined`` condition, read off the clause itself."""
        if self.mode is TemporalMode.CURRENT:
            return True
        return bool(self.timestamp or self.start or self.end)

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "timestamp": self.timestamp,
            "start": self.start,
            "end": self.end,
        }


@dataclass(frozen=True, slots=True)
class ScopeClause:
    """Appendix O's ``scope``: what is being searched over."""

    universe: UniverseScope = UniverseScope.REGISTERED_CATALOGUE
    #: Free-form narrowing the caller declared ("within Russia", "for CLUSTER-1"). Carried
    #: as text rather than as a ``Scope``, because narrowing is a *search restriction* and
    #: conflating it with a context cell's scope would let a search filter silently
    #: relocate the question.
    terms: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "universe", UniverseScope(self.universe))

    def as_dict(self) -> dict[str, Any]:
        return {
            "universe": self.universe.value,
            "terms": list(self.terms),
        }


@dataclass(frozen=True, slots=True)
class OutputProjection:
    """Appendix O's ``output.include``."""

    include: tuple[str, ...] = DEFAULT_OUTPUT_INCLUDE

    def __post_init__(self) -> None:
        object.__setattr__(self, "include", tuple(self.include) or DEFAULT_OUTPUT_INCLUDE)

    @property
    def exposes_coverage(self) -> bool:
        """Whether this projection can honestly carry a result.

        §33.1 requires coverage and blind spots on a global result. A projection that
        omits them cannot render one, and the check belongs here so a caller finds out
        before the query runs rather than after the UI silently lies.
        """
        return "coverage" in self.include and "blind_spots" in self.include

    def as_dict(self) -> dict[str, Any]:
        return {"include": list(self.include)}


@dataclass(frozen=True, slots=True)
class UnresolvedTerm:
    """A term the compiler could not bind, kept with the reason (§32.1).

    Retained rather than raised because the request is still executable in narrowed form,
    and the narrowing is the finding: the gap becomes an obligation instead of vanishing.
    """

    term: str
    slot: str
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {"term": self.term, "slot": self.slot, "reason": self.reason}


@dataclass(frozen=True, slots=True)
class QueryAST:
    """The compiled request. Appendix O.1, with the honesty fields §33 requires."""

    verb: QueryVerb
    #: The concept being looked for, before registry binding. Kept even when it binds:
    #: a bound AST that cannot show what the caller actually asked for is unauditable.
    concept: str
    subject_class: str = ""
    #: Appendix O calls this ``target.property`` -- the property of the target being
    #: constrained, e.g. ``aggregate_asset_value``. Renamed in Python because a field
    #: called ``property`` shadows the decorator inside this class body and every
    #: ``@property`` below would resolve to a string. The wire name stays ``property``.
    subject_property: str = ""
    filters: tuple[Filter, ...] = ()
    temporal: TemporalClause = field(default_factory=TemporalClause)
    scope: ScopeClause = field(default_factory=ScopeClause)
    output: OutputProjection = field(default_factory=OutputProjection)
    objective: Objective = Objective.IDENTIFY_COHORT
    identity_requirement: str = ""
    allow_unresolved: bool = True
    evidence_requirements: Mapping[str, int] = field(default_factory=dict)
    requested_mode: RequestedMode = RequestedMode.BEST_EFFORT
    unresolved: tuple[UnresolvedTerm, ...] = ()
    #: The wording this AST came from, kept for provenance and for the UI's banner.
    question: str = ""
    ast_id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "verb", QueryVerb(self.verb))
        object.__setattr__(self, "objective", Objective(self.objective))
        object.__setattr__(self, "requested_mode", RequestedMode(self.requested_mode))
        object.__setattr__(self, "filters", tuple(self.filters))
        object.__setattr__(self, "unresolved", tuple(self.unresolved))
        if not self.concept and not self.subject_class:
            raise ValueError("a query must name a concept or a subject class")
        if self.requested_mode is RequestedMode.UNIVERSAL and self.unresolved:
            # A universal claim over a query the compiler could not fully bind is exactly
            # the overclaim Appendix P exists to prevent, so it is refused at construction
            # rather than downgraded later where it could be missed.
            raise ValueError(
                "a universal request cannot carry unresolved terms: "
                f"{[u.term for u in self.unresolved]}"
            )
        if not self.ast_id:
            object.__setattr__(self, "ast_id", self.address())

    # -- identity ----------------------------------------------------------

    def _material(self) -> dict[str, Any]:
        """The semantic material ``ast_id`` digests.

        Excludes ``question``: two wordings of the same request are the same node, and
        the wording is provenance, not meaning.
        """
        return {
            "verb": self.verb.value,
            "concept": self.concept,
            "subject_class": self.subject_class,
            "property": self.subject_property,
            "filters": [f.as_dict() for f in self.filters],
            "temporal": self.temporal.as_dict(),
            "scope": self.scope.as_dict(),
            "output": self.output.as_dict(),
            "objective": self.objective.value,
            "identity_requirement": self.identity_requirement,
            "allow_unresolved": self.allow_unresolved,
            "evidence_requirements": dict(sorted(self.evidence_requirements.items())),
            "requested_mode": self.requested_mode.value,
            "unresolved": [u.as_dict() for u in self.unresolved],
        }

    def address(self) -> str:
        return f"QAST-{_digest(self._material())}"

    def with_unresolved(self, terms: Iterable[UnresolvedTerm]) -> QueryAST:
        """A copy carrying additional unresolved terms.

        Returns a copy rather than mutating because an AST is content-addressed: editing
        one in place would leave its ``ast_id`` describing content it no longer has.
        """
        return QueryAST(
            verb=self.verb,
            concept=self.concept,
            subject_class=self.subject_class,
            subject_property=self.subject_property,
            filters=self.filters,
            temporal=self.temporal,
            scope=self.scope,
            output=self.output,
            objective=self.objective,
            identity_requirement=self.identity_requirement,
            allow_unresolved=self.allow_unresolved,
            evidence_requirements=self.evidence_requirements,
            requested_mode=self.requested_mode,
            unresolved=self.unresolved + tuple(terms),
            question=self.question,
        )

    # -- queries ------------------------------------------------------------

    @property
    def claims_universality(self) -> bool:
        """Whether the wording implies a universal claim (Appendix P).

        Read from the question text rather than only from ``requested_mode``, because a
        caller can request best-effort over the words "find all ..." -- and the words are
        what the result will be read as.

        Detection is delegated to :func:`context.completeness.implies_universal`. A
        substring check here would read "wallet_control_cluster" as universal, because
        "wallet" contains "all"; that module already pinned the word-boundary rule, and a
        second implementation would drift from it.
        """
        if self.requested_mode is RequestedMode.UNIVERSAL:
            return True
        return implies_universal(self.question)

    @property
    def is_executable(self) -> bool:
        """Whether this AST can be turned into a plan at all."""
        return bool(self.concept or self.subject_class) and bool(self.filters or self.concept)

    def filters_on(self, field_name: str) -> tuple[Filter, ...]:
        return tuple(f for f in self.filters if f.field == field_name)

    def numeric_bounds(self, field_name: str) -> tuple[Filter, ...]:
        """Filters on ``field_name`` that carry a number.

        A planner asking "what range is this field in" must not treat a ``contains``
        string filter as a bound, so the numeric ones are selected explicitly.
        """
        return tuple(f for f in self.filters_on(field_name) if f.numeric_value is not None)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ast_id": self.ast_id,
            **self._material(),
            "question": self.question,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> QueryAST:
        """Rebuild an AST from :meth:`as_dict`.

        ``ast_id`` is recomputed rather than trusted, and a mismatch is an error: a
        payload whose digest disagrees with its content is either corrupted or forged, and
        both must not pass as an addressable node.
        """
        material = dict(payload)
        stated = str(material.pop("ast_id", "") or "")
        question = str(material.pop("question", "") or "")
        ast = cls(
            verb=material["verb"],
            concept=material["concept"],
            subject_class=material.get("subject_class", ""),
            subject_property=material.get("property", ""),
            filters=tuple(
                Filter(
                    field=item["field"],
                    operator=FilterOperator(item["operator"]),
                    value=item.get("value"),
                    unit=item.get("unit", ""),
                )
                for item in material.get("filters", ())
            ),
            temporal=TemporalClause(**material.get("temporal", {})),
            scope=ScopeClause(**material.get("scope", {})),
            output=OutputProjection(tuple(material.get("output", {}).get("include", ()))),
            objective=material.get("objective", Objective.IDENTIFY_COHORT),
            identity_requirement=material.get("identity_requirement", ""),
            allow_unresolved=material.get("allow_unresolved", True),
            evidence_requirements=dict(material.get("evidence_requirements", {})),
            requested_mode=material.get("requested_mode", RequestedMode.BEST_EFFORT),
            unresolved=tuple(
                UnresolvedTerm(**item) for item in material.get("unresolved", ())
            ),
            question=question,
        )
        if stated and stated != ast.ast_id:
            raise ValueError(
                f"ast_id {stated} does not match content digest {ast.ast_id}"
            )
        return ast


# -- compilation from intent ---------------------------------------------------


def compile_ast(
    intent: QueryIntent,
    *,
    verb: QueryVerb = QueryVerb.FIND,
    scope: ScopeClause | None = None,
    output: OutputProjection | None = None,
    requested_mode: RequestedMode | None = None,
) -> QueryAST:
    """Compile a :class:`QueryIntent` into the Appendix O AST (FR-025-050).

    The intent already holds the target, temporal mode, identity requirement and
    evidence requirements; this turns those into the AST's shape and derives the
    filters. A target that names a ``value`` becomes an equality filter, which is the one
    case where a bare number is unambiguous -- a threshold with no operator reads as
    equality, and the AST records it as such rather than guessing a direction.

    ``requested_mode`` defaults to the intent's own request. It is *not* upgraded: a
    best-effort intent does not become universal because it was compiled.
    """
    filters: list[Filter] = []
    target = intent.target
    if target.value is not None:
        filters.append(
            Filter(
                field=target.property or "value",
                operator=FilterOperator.EQ,
                value=target.value,
                unit=target.unit,
            )
        )

    temporal = TemporalClause(mode=intent.temporal_scope)
    return QueryAST(
        verb=verb,
        concept=target.subject_class,
        subject_class=target.subject_class,
        subject_property=target.property,
        filters=tuple(filters),
        temporal=temporal,
        scope=scope or ScopeClause(),
        output=output or OutputProjection(),
        objective=intent.objective,
        identity_requirement=intent.identity_requirement,
        allow_unresolved=intent.allow_unresolved,
        evidence_requirements=dict(intent.evidence_requirements),
        requested_mode=requested_mode or intent.requested_mode,
        question=intent.question,
    )


def ast_from_target(
    target: Target,
    *,
    verb: QueryVerb = QueryVerb.FIND,
    filters: Sequence[Filter] = (),
    question: str = "",
    objective: Objective = Objective.IDENTIFY_COHORT,
    identity_requirement: str = "",
    allow_unresolved: bool = True,
    evidence_requirements: Mapping[str, int] | None = None,
    temporal: TemporalClause | None = None,
    scope: ScopeClause | None = None,
    output: OutputProjection | None = None,
    requested_mode: RequestedMode | None = None,
) -> QueryAST:
    """Build an AST directly from a :class:`Target` plus explicit filters.

    For callers that already hold a target and the constraints, and have no reason to
    round-trip through ``QueryIntent``. Every field :func:`compile_ast` derives from an
    intent is accepted here, because the point of having two paths is that they agree: an
    AST built this way and one built from the same intent carry the same ``ast_id``, and
    that equivalence is what makes FR-025-050 checkable rather than asserted.
    """
    return QueryAST(
        verb=verb,
        concept=target.subject_class,
        subject_class=target.subject_class,
        subject_property=target.property,
        filters=tuple(filters),
        temporal=temporal or TemporalClause(),
        scope=scope or ScopeClause(),
        output=output or OutputProjection(),
        objective=objective,
        identity_requirement=identity_requirement,
        allow_unresolved=allow_unresolved,
        evidence_requirements=dict(evidence_requirements or {}),
        requested_mode=requested_mode or RequestedMode.UNIVERSAL,
        question=question,
    )