"""The AST cycle in one place: context in, search requests out, results back in.

The two directions meet here. Forward, a context's open questions compile into
:class:`~context.query_binding.QueryPlan` objects -- and therefore into concrete search
strings a source can be asked for. Backward, what acquisition produced comes back through
:meth:`cycle.run`, is grounded in the entity stream, and deepens the context.

Keeping both directions in one runner is the point rather than a convenience: a cycle
whose halves are wired separately drifts, and the drift shows up as a context that grows
without bound in one direction while the other quietly produces nothing.

What this does *not* do is execute acquisition. It produces the requests, applies the
returned outcomes, and reports what moved. Acquisition remains behind Kafka and the
Temporal worker, and this module never calls a runtime directly -- a cycle step that
executed sources itself would make the context's growth depend on how long a subprocess
took, and the loop would stop being replayable.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from context.query_ast import QueryAST
from context.query_binding import (
    ConceptRegistry,
    QueryPlan,
    merge_plans,
    plan_from_context,
    search_queries,
)

from context_engine.return_path import (
    AcquisitionResult,
    EntityMembershipReader,
    newly_grounded,
    resolve_outcomes,
    unplaced,
)


@dataclass(frozen=True, slots=True)
class CycleStep:
    """What one pass of the cycle produced, in both directions."""

    context_id: str
    revision: int
    plans: tuple[QueryPlan, ...] = ()
    #: The concrete strings to hand to acquisition, in plan order.
    requests: tuple[str, ...] = ()
    outcomes: tuple[Any, ...] = ()
    #: Observations that arrived with no established membership.
    unplaced: tuple[str, ...] = ()
    #: Observations this pass established membership for that was absent before.
    grounded: tuple[str, ...] = ()
    gap_signals: tuple[Any, ...] = ()

    @property
    def is_closed(self) -> bool:
        """Whether the cycle moved in both directions.

        Forward-only progress is not progress on an investigation: a pass that produces
        requests but grounds nothing has spent acquisition budget without teaching the
        context anything.
        """
        return bool(self.requests) and bool(self.grounded)

    def as_dict(self) -> dict[str, Any]:
        return {
            "context_id": self.context_id,
            "revision": self.revision,
            "plans": [plan.as_dict() for plan in self.plans],
            "requests": list(self.requests),
            "unplaced": list(self.unplaced),
            "grounded": list(self.grounded),
            "is_closed": self.is_closed,
            "gap_signals": [
                signal.to_dict() if hasattr(signal, "to_dict") else str(signal)
                for signal in self.gap_signals
            ],
        }


class QueryCycle:
    """Compiles a context into search requests, and applies what comes back."""

    def __init__(
        self,
        *,
        registry: ConceptRegistry | None = None,
        reader: EntityMembershipReader | None = None,
        known_observations: Sequence[str] = (),
    ) -> None:
        self._registry = registry
        self._reader = reader
        self._known = tuple(known_observations)

    # -- forward -------------------------------------------------------------

    def plan(
        self,
        context: Any,
        asts: Sequence[QueryAST],
        *,
        conditions: Mapping[str, bool] | None = None,
    ) -> tuple[QueryPlan, ...]:
        """Compile every query for this context into deduplicated plans.

        Merged by AST identity, so two questions that mean the same thing cost one search
        rather than two -- and the merge widens the search terms instead of picking a
        winner, because dropping one question's terms would narrow the acquisition.
        """
        plans = [
            plan_from_context(context, ast, registry=self._registry, conditions=conditions)
            for ast in asts
        ]
        context_id = str(getattr(context, "context_id", "") or "")
        return merge_plans(plans, context_id=context_id)

    def requests_for(self, plans: Sequence[QueryPlan]) -> tuple[str, ...]:
        """Every search string the plans ask for, in order, without duplicates."""
        terms: list[str] = []
        for plan in plans:
            if not plan.is_actionable:
                continue
            for term in search_queries(plan):
                if term not in terms:
                    terms.append(term)
        return tuple(terms)

    # -- backward ------------------------------------------------------------

    async def apply(
        self,
        context: Any,
        results: Sequence[AcquisitionResult],
        *,
        tenant_id: str = "",
    ) -> tuple[Any, ...]:
        """Ground acquisition results and return loop-ready outcomes.

        Needs a reader: without one there is no membership to resolve, and returning
        empty outcomes would report "nothing produced" for a batch that did produce.
        """
        if self._reader is None:
            raise ValueError(
                "applying results needs an EntityMembershipReader; "
                "without one the observations would carry no scope"
            )
        outcomes = await resolve_outcomes(
            results, self._reader, tenant_id=tenant_id or str(getattr(context, "tenant_id", ""))
        )
        self._known = tuple(dict.fromkeys(self._known + tuple(
            observation_id
            for outcome in outcomes
            for observation_id in outcome.produced_observations
        )))
        return outcomes

    # -- both ----------------------------------------------------------------

    async def step(
        self,
        context: Any,
        asts: Sequence[QueryAST],
        results: Sequence[AcquisitionResult] = (),
        *,
        conditions: Mapping[str, bool] | None = None,
        tenant_id: str = "",
    ) -> CycleStep:
        """Run both directions and report what moved.

        The forward half always runs; the backward half only when results are supplied. A
        step with no results is a legitimate state -- the first tick of an investigation
        has nothing to apply -- so it is reported as forward-only rather than as a failure.
        """
        plans = self.plan(context, asts, conditions=conditions)
        requests = self.requests_for(plans)

        outcomes: tuple[Any, ...] = ()
        missing: tuple[str, ...] = ()
        grounded: tuple[str, ...] = ()
        if results:
            outcomes = await self.apply(context, results, tenant_id=tenant_id)
            missing = unplaced(outcomes)
            grounded = newly_grounded((), outcomes)

        return CycleStep(
            context_id=str(getattr(context, "context_id", "") or ""),
            revision=int(getattr(context, "revision", 0) or 0),
            plans=plans,
            requests=requests,
            outcomes=outcomes,
            unplaced=missing,
            grounded=grounded,
        )


@dataclass(slots=True)
class CycleLedger:
    """Remembers what has been asked, so the cycle does not re-ask it.

    A query the investigation already ran and that produced nothing is not worth repeating
    on the next tick: saturation is only meaningful if the same request stops being issued
    once it stops paying.

    Keyed on the *question's* ``ast_id``, not the plan's. They differ whenever a context
    narrows the query -- ``plan_from_context`` folds ``scope_refs`` into the scope clause,
    so the plan for the same question in a different context is a different node. Keying on
    the plan would re-ask the question the moment the context changed, which is precisely
    when a settled question should stay settled.
    """

    planned: set[str] = field(default_factory=set)

    def record(self, plans: Sequence[QueryPlan]) -> None:
        self.planned.update(plan.ast_id for plan in plans)

    def record_questions(self, asts: Sequence[QueryAST]) -> None:
        self.planned.update(ast.ast_id for ast in asts)

    def pending(
        self, context: Any, asts: Sequence[QueryAST], cycle: QueryCycle
    ) -> tuple[QueryPlan, ...]:
        """Plans for the questions not yet planned, recorded as asked.

        Recording happens here rather than being left to the caller, because a ledger that
        only fills when someone remembers to fill it silently re-asks every query on every
        tick -- which reads as "the investigation is working hard" and is the opposite.
        """
        fresh = [ast for ast in asts if not self.has_run(ast.ast_id)]
        self.record_questions(fresh)
        return cycle.plan(context, fresh)

    def has_run(self, ast_id: str) -> bool:
        return ast_id in self.planned