"""Semantic binding and planner compilation: an AST plus a context becomes a plan.

This is the forward direction of the cycle -- context in, relevant search requests out --
and it is where FR-025-053's completeness rule and FR-025-054's coverage rule attach.

Four jobs, in the order they must happen:

**Bind.** A query's ``concept`` is a term, and a term is not yet a thing the platform can
query. :func:`bind_ast` resolves it against a registry and records what it could not
resolve, per §32.1. Binding does not fail the query: an unbound concept narrows what can
be asked and becomes an obligation, because a silently dropped term produces a *broader*
search than the analyst asked for, which is the one error direction that cannot be noticed
from the result.

**Constrain.** Each filter compiles into a :class:`PlannerRequest` -- a constraint on a
named property, in a form a planner can apply. T025-098. A filter the planner has no
handler for is recorded as an unhandled constraint rather than dropped, so the gap is
visible in the plan.

**Aggregate.** T025-100: a cohort query needs to say what it is aggregating over, because
``aggregate_asset_value >= 1000000`` with no population is a number, not a cohort.

**Qualify.** T025-099: the plan carries a
:class:`~context.completeness.CompletenessRequirement` *derived* by
:func:`context.completeness.assess_completeness`. The plan cannot assert a completeness
mode, so a caller asking for enumeration receives the downgrade with its unmet conditions
named -- the same rule the rest of the platform already follows, applied here where the
request is actually formed.

Context enters through :func:`plan_from_context`, which is the entry point the live cycle
uses: it takes an existing context and its open gaps, and produces the search requests that
address them.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from context.completeness import (
    CompletenessRequirement,
    RequestedMode,
    UniverseDefinition,
    assess_completeness,
)
from context.query_ast import (
    Filter,
    FilterOperator,
    QueryAST,
    UnresolvedTerm,
)


class ConceptRegistry(Protocol):
    """Resolves a query term to something addressable.

    Separate from the ontology registry on purpose. A concept registry answers "what does
    this word denote here", which is a narrower question than "what exists", and a search
    planner needs the narrower one: an unresolved concept is a gap in vocabulary, not
    necessarily a gap in the world.
    """

    def resolve(self, term: str) -> str | None: ...


@dataclass(frozen=True, slots=True)
class StaticConceptRegistry:
    """A registry over a fixed mapping. For tests, for bootstrapping, for a closed domain."""

    entries: Mapping[str, str]

    def resolve(self, term: str) -> str | None:
        return self.entries.get(term.strip().lower())


@dataclass(frozen=True, slots=True)
class BoundQuery:
    """An AST with its terms resolved, or the reasons they were not.

    ``resolved`` maps the term as written to its registry ref. ``unresolved`` keeps every
    term that did not bind, and the query is still executable in narrowed form -- which is
    the point: the plan says what it can search and what it could not.

    ``attempted`` distinguishes "nothing was unresolved" from "nothing was resolved".
    Without it a caller supplying no registry reads ``is_fully_bound`` as an identity
    resolution that never ran, and reports completeness it did not establish.
    """

    ast: QueryAST
    resolved: Mapping[str, str] = field(default_factory=dict)
    unresolved: tuple[UnresolvedTerm, ...] = ()
    attempted: bool = True

    @property
    def is_fully_bound(self) -> bool:
        return self.attempted and not self.unresolved

    @property
    def ast_id(self) -> str:
        return self.ast.ast_id

    def as_dict(self) -> dict[str, Any]:
        return {
            "ast_id": self.ast.ast_id,
            "resolved": dict(sorted(self.resolved.items())),
            "unresolved": [term.as_dict() for term in self.unresolved],
        }


def bind_ast(ast: QueryAST, registry: ConceptRegistry | None = None) -> BoundQuery:
    """Resolve an AST's terms, preserving what did not resolve (§32.1).

    An unbound *concept* does not block execution -- the term is still a usable search
    string -- so the returned query keeps the original AST rather than failing. An unbound
    concept is only fatal to a universal claim, and :class:`QueryAST` already refuses that
    combination at construction.
    """
    if registry is None:
        return BoundQuery(ast=ast, attempted=False)

    resolved: dict[str, str] = {}
    unresolved: list[UnresolvedTerm] = list(ast.unresolved)

    for slot, term in (("concept", ast.concept), ("subject_class", ast.subject_class)):
        if not term:
            continue
        ref = registry.resolve(term)
        if ref:
            resolved[term] = ref
        elif not any(item.term == term and item.slot == slot for item in unresolved):
            unresolved.append(
                UnresolvedTerm(
                    term=term,
                    slot=slot,
                    reason="not in the concept registry; searched as written",
                )
            )

    # A filter field is a property name, not a vocabulary term, so it binds through the
    # same registry but a miss is informational: the field is still usable as a string.
    for item in ast.filters:
        ref = registry.resolve(item.field)
        if ref:
            resolved[item.field] = ref
        elif not any(u.term == item.field for u in unresolved):
            unresolved.append(
                UnresolvedTerm(
                    term=item.field,
                    slot="filter.field",
                    reason="property is not registered; applied as a literal field name",
                )
            )

    return BoundQuery(ast=ast, resolved=dict(resolved), unresolved=tuple(unresolved))


@dataclass(frozen=True, slots=True)
class PlannerRequest:
    """One constraint handed to a planner (T025-098).

    ``operator`` is kept symbolic rather than compiled into a predicate string: a planner
    that cannot apply a constraint must be able to *say* which one it could not, and a
    compiled predicate has already lost that.
    """

    field: str
    operator: FilterOperator
    value: Any
    unit: str = ""
    #: The bound ref for ``field``, when the registry had one.
    field_ref: str = ""

    @property
    def is_numeric_bound(self) -> bool:
        return isinstance(self.value, (int, float)) and not isinstance(self.value, bool)

    def as_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "field_ref": self.field_ref,
            "operator": self.operator.value,
            "value": list(self.value)
            if isinstance(self.value, (set, frozenset, tuple))
            else self.value,
            "unit": self.unit,
        }


@dataclass(frozen=True, slots=True)
class AggregationRequirement:
    """T025-100. What a cohort or aggregate query needs before it may aggregate.

    ``population`` is what is being summarised. Absent one, ``aggregate_asset_value >=
    1000000`` is a threshold on an unnamed set, and the engine cannot report a cohort it
    cannot name.
    """

    aggregate_field: str
    population: str = ""
    minimum_members: int = 0
    #: Whether an empty population is an acceptable answer. It is not for a cohort
    #: request, which is why the default is False rather than "whatever the caller says".
    allow_empty_population: bool = False

    @property
    def is_satisfied(self) -> bool:
        if self.population:
            return True
        return self.allow_empty_population

    def as_dict(self) -> dict[str, Any]:
        return {
            "aggregate_field": self.aggregate_field,
            "population": self.population,
            "minimum_members": self.minimum_members,
            "allow_empty_population": self.allow_empty_population,
            "satisfied": self.is_satisfied,
        }


@dataclass(frozen=True, slots=True)
class QueryPlan:
    """A bound query, its constraints, its completeness, and what could not be planned."""

    ast_id: str
    question: str
    search_terms: tuple[str, ...] = ()
    requests: tuple[PlannerRequest, ...] = ()
    aggregation: AggregationRequirement | None = None
    completeness: CompletenessRequirement | None = None
    resolved: Mapping[str, str] = field(default_factory=dict)
    unresolved: tuple[UnresolvedTerm, ...] = ()
    #: Filters the caller supplied but the plan could not turn into a request.
    unhandled: tuple[Filter, ...] = ()
    #: The context this plan was compiled against, when it came from one.
    context_id: str = ""
    revision: int = 0

    @property
    def is_actionable(self) -> bool:
        """Whether this plan can be executed as it stands.

        False when nothing survived compilation. A plan with no requests and no search
        terms would otherwise look like a plan, and a caller would wait for a result that
        was never going to be searched for.
        """
        return bool(self.search_terms or self.requests)

    @property
    def claims_universality(self) -> bool:
        completeness = self.completeness
        if completeness is None:
            return False
        return completeness.requested_mode is RequestedMode.UNIVERSAL

    @property
    def overclaims(self) -> bool:
        """Whether the request asks for more than the conditions support.

        The single check a caller needs before rendering a result: if this is true the
        result must carry the downgrade and its unmet conditions.
        """
        completeness = self.completeness
        if completeness is None:
            return False
        return bool(completeness.unmet)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ast_id": self.ast_id,
            "question": self.question,
            "context_id": self.context_id,
            "revision": self.revision,
            "search_terms": list(self.search_terms),
            "requests": [request.as_dict() for request in self.requests],
            "aggregation": self.aggregation.as_dict() if self.aggregation else None,
            "completeness": self.completeness.as_dict() if self.completeness else None,
            "resolved": dict(sorted(self.resolved.items())),
            "unresolved": [term.as_dict() for term in self.unresolved],
            "unhandled": [item.as_dict() for item in self.unhandled],
            "is_actionable": self.is_actionable,
            "overclaims": self.overclaims,
        }


#: Operator handlers a planner may declare. A filter whose operator is absent lands in
#: ``unhandled`` rather than being silently dropped: an unapplied constraint widens the
#: result set, which is the dangerous direction.
_HANDLED_OPERATORS: frozenset[FilterOperator] = frozenset(FilterOperator)


def compile_plan(
    ast: QueryAST,
    *,
    registry: ConceptRegistry | None = None,
    universe: UniverseDefinition = UniverseDefinition.REGISTERED_SOURCES,
    conditions: Mapping[str, bool] | None = None,
    aggregation: AggregationRequirement | None = None,
    context_id: str = "",
    revision: int = 0,
) -> QueryPlan:
    """Bind, constrain, aggregate and qualify one AST (T025-097…100).

    ``conditions`` are the Appendix P.1 facts, passed in rather than assumed. They default
    to all-false, which yields the weakest mode -- so a caller that knows nothing gets
    ``OPEN_WORLD_DISCOVERY`` instead of a claim it did not earn.
    """
    bound = bind_ast(ast, registry)

    requests: list[PlannerRequest] = []
    unhandled: list[Filter] = []
    for item in ast.filters:
        if item.operator not in _HANDLED_OPERATORS:
            unhandled.append(item)
            continue
        requests.append(
            PlannerRequest(
                field=item.field,
                field_ref=bound.resolved.get(item.field, ""),
                operator=item.operator,
                value=item.value,
                unit=item.unit,
            )
        )

    # The search terms are what a source is actually asked for. The bound concept ref is
    # preferred where one exists, because a registry ref is what sources index on; the
    # written term is kept alongside so the request stays legible to a human reading the
    # frontier.
    terms: list[str] = []
    for term in (ast.concept, ast.subject_class):
        if not term:
            continue
        for candidate in (bound.resolved.get(term, ""), term):
            if candidate and candidate not in terms:
                terms.append(candidate)
    for narrowing in ast.scope.terms:
        if narrowing not in terms:
            terms.append(narrowing)

    facts = {
        "catalogue_exhausted": False,
        "temporal_scope_defined": ast.temporal.is_defined,
        "identity_resolution_complete": bound.is_fully_bound,
        "pagination_complete": False,
        "source_errors_zero_or_accounted": False,
    }
    facts.update(dict(conditions or {}))
    completeness = assess_completeness(
        universe=universe,
        requested_mode=ast.requested_mode,
        **facts,
    )

    return QueryPlan(
        ast_id=ast.ast_id,
        question=ast.question,
        search_terms=tuple(terms),
        requests=tuple(requests),
        aggregation=aggregation,
        completeness=completeness,
        resolved=dict(bound.resolved),
        unresolved=bound.unresolved,
        unhandled=tuple(unhandled),
        context_id=context_id,
        revision=revision,
    )


def plan_from_context(
    context: Any,
    ast: QueryAST,
    *,
    registry: ConceptRegistry | None = None,
    universe: UniverseDefinition = UniverseDefinition.REGISTERED_SOURCES,
    conditions: Mapping[str, bool] | None = None,
    aggregation: AggregationRequirement | None = None,
) -> QueryPlan:
    """Compile a plan against an existing context -- the forward direction's entry point.

    The context contributes three things a bare AST does not have: its identity and
    revision, so the plan is attributable to the state it was compiled against; its
    declared scope, which narrows the search to what the investigation is about; and its
    question, which is used when the AST carries no wording of its own.

    The scope is added as search terms rather than as a universe, so narrowing by
    investigation does not change the *kind* of completeness being claimed. Choosing
    ``EXPLICITLY_ENUMERABLE`` because a single investigation names two entities would let
    any narrow query claim a global result.
    """
    scope_refs = tuple(getattr(context, "scope_refs", ()) or ())
    merged = QueryAST(
        verb=ast.verb,
        concept=ast.concept,
        subject_class=ast.subject_class,
        subject_property=ast.subject_property,
        filters=ast.filters,
        temporal=ast.temporal,
        scope=ast.scope,
        output=ast.output,
        objective=ast.objective,
        identity_requirement=ast.identity_requirement,
        allow_unresolved=ast.allow_unresolved,
        evidence_requirements=ast.evidence_requirements,
        requested_mode=ast.requested_mode,
        unresolved=ast.unresolved,
        question=ast.question or str(getattr(context, "question", "") or ""),
    )
    terms = tuple(dict.fromkeys(merged.scope.terms + scope_refs))
    contextual = QueryAST(
        verb=merged.verb,
        concept=merged.concept,
        subject_class=merged.subject_class,
        subject_property=merged.subject_property,
        filters=merged.filters,
        temporal=merged.temporal,
        scope=type(merged.scope)(universe=merged.scope.universe, terms=terms),
        output=merged.output,
        objective=merged.objective,
        identity_requirement=merged.identity_requirement,
        allow_unresolved=merged.allow_unresolved,
        evidence_requirements=merged.evidence_requirements,
        requested_mode=merged.requested_mode,
        unresolved=merged.unresolved,
        question=merged.question,
    )
    return compile_plan(
        contextual,
        registry=registry,
        universe=universe,
        conditions=conditions,
        aggregation=aggregation,
        context_id=str(getattr(context, "context_id", "") or ""),
        revision=int(getattr(context, "revision", 0) or 0),
    )


def merge_plans(plans: Iterable[QueryPlan], *, context_id: str = "") -> tuple[QueryPlan, ...]:
    """Deduplicate plans that ask the same thing.

    Two gaps in one context often reduce to the same request once bound -- "who owns A"
    and "who owns B" against a shared registry ref -- and acquiring both would double the
    cost for no additional coverage. Identity is the AST, so this merges only genuinely
    identical asks and leaves similar-but-different ones alone.
    """
    seen: dict[str, QueryPlan] = {}
    for plan in plans:
        existing = seen.get(plan.ast_id)
        if existing is None:
            seen[plan.ast_id] = plan
            continue
        # Keep the union of search terms: identical meaning can still have been reached
        # from different contexts, and dropping one set of terms would narrow the search.
        merged_terms = tuple(dict.fromkeys(existing.search_terms + plan.search_terms))
        seen[plan.ast_id] = QueryPlan(
            ast_id=existing.ast_id,
            question=existing.question or plan.question,
            search_terms=merged_terms,
            requests=existing.requests or plan.requests,
            aggregation=existing.aggregation or plan.aggregation,
            completeness=existing.completeness or plan.completeness,
            resolved={**plan.resolved, **existing.resolved},
            unresolved=existing.unresolved or plan.unresolved,
            unhandled=existing.unhandled or plan.unhandled,
            context_id=context_id or existing.context_id or plan.context_id,
            revision=max(existing.revision, plan.revision),
        )
    return tuple(sorted(seen.values(), key=lambda plan: plan.ast_id))


def search_queries(plan: QueryPlan) -> tuple[str, ...]:
    """The concrete strings to hand to a source, one per term.

    Kept separate from the plan because the plan is the record of *what was asked*, while
    these are what an adapter sends. Building them here means the constraint never reaches
    a source as free text: a source that cannot apply ``>= 1000000 USD`` says so, rather
    than being handed the number and guessing.
    """
    return plan.search_terms


def describe_filters(plan: QueryPlan) -> tuple[str, ...]:
    """Rendered constraints, for a source that can express them inline."""
    rendered: list[str] = []
    for request in plan.requests:
        value = (
            ",".join(str(item) for item in request.value)
            if isinstance(request.value, (set, frozenset, tuple, list))
            else str(request.value)
        )
        unit = f" {request.unit}" if request.unit else ""
        rendered.append(f"{request.field} {request.operator.value} {value}{unit}")
    return tuple(rendered)


def constraints_for(plan: QueryPlan, field_name: str) -> tuple[PlannerRequest, ...]:
    """Requests touching one field. For a planner that can only apply some properties."""
    return tuple(request for request in plan.requests if request.field == field_name)


def as_sequence(value: Any) -> Sequence[Any]:
    """Normalise a scalar-or-collection into a sequence, for handlers that iterate."""
    if isinstance(value, (set, frozenset, tuple, list)):
        return tuple(value)
    return (value,)