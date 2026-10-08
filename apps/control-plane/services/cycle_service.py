"""One pass of the assembled cycle, end to end.

This is where the pieces meet, and it is deliberately the only place that knows their
order:

1. **Read what is unanswered.** The context's open obligations and the fabric's findings
   are the question set. Deriving questions from the obligation ledger rather than from the
   context's free-text question is what makes the loop converge: a question already answered
   raises no obligation, so it stops being asked.
2. **Compile questions into queries.** Natural-language wording becomes a
   :class:`~context.query_ast.QueryAST` through the grammar. Unparseable wording is recorded
   and skipped, never guessed at -- a fabricated query spends acquisition budget against a
   question nobody asked.
3. **Plan the searches.** Only questions not already planned, so a settled question is not
   re-asked and its cost is not repaid.
4. **Drain what came back.** Frontier items already acquired by the worker become outcomes
   with membership resolved from the entity stream.
5. **Tick the context.** The loop ingests the outcomes, the fabric grows the cells, and the
   report is persisted and attributed to the revision.

The failure mode this is written against is a half-completed step. Each phase returns
rather than raises for anything it cannot do, and the report says which phase stopped and
why -- so a platform that has no sources configured reports "no queries compiled" instead
of failing a request that otherwise succeeded.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PhaseResult:
    """What one phase did."""

    name: str
    ok: bool
    detail: str = ""
    count: int = 0


@dataclass(slots=True)
class TickReport:
    """The result of one full pass, in a form a caller can act on or assert on."""

    context_id: str
    revision: int = 0
    phases: list[PhaseResult] = field(default_factory=list)
    ast_ids: tuple[str, ...] = ()
    requests: tuple[str, ...] = ()
    unparsed: tuple[str, ...] = ()
    #: Observation/entity refs an obligation named, to be resolved locally.
    subjects: tuple[str, ...] = ()
    grounded: tuple[str, ...] = ()
    unplaced: tuple[str, ...] = ()
    cell_ids: tuple[str, ...] = ()
    feedback_signals: int = 0
    obligations: int = 0
    saturated: str = ""
    #: Scope closure over the entity stream: entities, observations it can reach, and how
    #: much was read but could not be placed. ``None`` when the phase could not run -- which
    #: is different from an empty lattice, and reporting both as empty is how an
    #: investigation reports "nothing in scope" when in fact nothing was read.
    lattice: dict[str, Any] | None = None
    gradient: dict[str, Any] | None = None

    @property
    def ok(self) -> bool:
        return all(phase.ok for phase in self.phases)

    @property
    def moved(self) -> bool:
        """Whether this pass changed the context in either direction.

        The useful signal. A tick that compiles no queries and grounds nothing looks
        identical to a healthy one in a log, and reporting ``ok`` for both is how an
        investigation appears to be running while making no progress.
        """
        return bool(self.grounded or self.cell_ids or self.requests)

    def as_dict(self) -> dict[str, Any]:
        return {
            "context_id": self.context_id,
            "revision": self.revision,
            "phases": [
                {"name": p.name, "ok": p.ok, "detail": p.detail, "count": p.count}
                for p in self.phases
            ],
            "ast_ids": list(self.ast_ids),
            "requests": list(self.requests),
            "unparsed": list(self.unparsed),
            "subjects": list(self.subjects),
            "grounded": list(self.grounded),
            "unplaced": list(self.unplaced),
            "cell_ids": list(self.cell_ids),
            "obligations": self.obligations,
            "feedback_signals": self.feedback_signals,
            "saturated": self.saturated,
            "lattice": self.lattice,
            "gradient": self.gradient,
            "ok": self.ok,
            "moved": self.moved,
        }


class CycleService:
    """Runs the assembled cycle for one context per call.

    Every collaborator is injected. The service owns ordering and reporting, not
    construction -- the platform is what decides which of these exist, and a service that
    built its own would hide a missing component behind a working local one.
    """

    def __init__(
        self,
        *,
        store: Any,
        fabric_store: Any,
        loop: Any,
        cycle: Any,
        ledger: Any,
        bridge: Any = None,
        session_factory: Any = None,
        frontier_factory: Any = None,
    ) -> None:
        self._store = store
        self._fabric_store = fabric_store
        self._loop = loop
        self._cycle = cycle
        self._ledger = ledger
        self._bridge = bridge
        self._session_factory = session_factory
        self._frontier_factory = frontier_factory

    # -- questions ------------------------------------------------------------

    async def _read_lattice(
        self, context: Any, report: TickReport, *, tenant_id: str
    ) -> None:
        """Close the entity-scope lattice over what this tenant has actually read.

        The last phase on purpose: the gradient it produces is only meaningful once the tick
        has decided what to ask, so reporting it first would describe a widening computed
        before anything changed.

        Read by tenant, not by context. The stream is tenant-wide, and a lattice built from
        another tenant's entities would answer a question this context never asked.
        """
        from context.lattice import ScopeLattice

        try:
            rows = await self._store.observation_entity_rows(tenant_id or str(context.context_id))
        except Exception as exc:  # noqa: BLE001 - a phase, not a crash
            log.warning("cannot read entity stream for lattice: %s", exc)
            report.phases.append(PhaseResult("scope_lattice", False, str(exc)))
            return
        if rows is None:
            report.phases.append(
                PhaseResult("scope_lattice", True, "entity stream unavailable", 0)
            )
            return

        observations: dict[str, list[dict[str, str]]] = {}
        for row in rows:
            observations.setdefault(row["observation_ref"], []).append(
                {"entity_ref": row["entity_ref"], "entity_type": row["entity_type"]}
            )
        lattice = ScopeLattice.from_observations(
            (
                {"observation_ref": ref, "entities": members}
                for ref, members in sorted(observations.items())
            )
        )
        report.lattice = lattice.snapshot()
        report.lattice["conflicts"] = {
            ref: sorted(t.value for t in types)
            for ref, types in sorted(lattice.conflicts().items())
        }
        report.gradient = lattice.gradient(lattice.top()).as_dict()
        report.phases.append(
            PhaseResult(
                "scope_lattice",
                True,
                f"{report.lattice['entities']} entities, "
                f"{report.lattice['unplaced']} unplaced, "
                f"gradient {len(report.gradient['members'])}",
                report.lattice["entities"],
            )
        )

    async def _open_obligations(self, context: Any) -> tuple[Any, ...]:
        """The obligations this context has not answered yet.

        Read from the ledger. The ledger is what makes the cycle converge: an obligation is
        created when a question is raised and closed when it is answered, so an answered
        question drops out here on its own without anything tracking "what have I asked".
        """
        try:
            obligations = await self._store.obligations(context.context_id)
        except Exception as exc:  # noqa: BLE001 - reported as a phase, not a crash
            log.warning("cannot read obligations for %s: %s", context.context_id, exc)
            return ()
        return tuple(
            obligation
            for obligation in obligations
            if getattr(obligation.status, "value", obligation.status) == "open"
        )

    async def open_questions(self, context: Any) -> tuple[str, ...]:
        """The open obligations' question text. For callers that only need the strings."""
        return tuple(
            obligation.question for obligation in await self._open_obligations(context)
        )

    def compile_obligations(
        self, obligations: Sequence[Any]
    ) -> tuple[tuple[Any, ...], tuple[str, ...], tuple[str, ...]]:
        """Turn open obligations into work. Returns ``(asts, refs, unresolved)``.

        Compiled from each obligation's **structured** fields, not its prose. The question
        text is a rendering for a human reader; parsing it as a query produced nothing --
        every real obligation came back "not in grammar", and the forward direction was
        silent while the loop looked healthy.

        Three kinds, because the obligation ledger does not hold one kind of thing:

        * A **subject reference** -- an observation or entity id in the question or the
          satisfaction criteria. This is not a web search; it is a local resolution, and
          routing it through acquisition would spend source budget to learn something the
          entity stream already holds. Returned in ``refs``.
        * A **source-expansion** obligation, named by its rule (a saturation shortfall
          means "the evidence is not independent, search elsewhere"). This *is* a query,
          built with no filters because no field was named -- a constrained query would
          invent a constraint nobody asked for.
        * Anything else is **unresolved** and reported. Not dropped and not guessed at.
        """
        from context.query_ast import (
            OutputProjection,
            QueryAST,
            QueryVerb,
            ScopeClause,
            UniverseScope,
        )

        from context_engine.obligations import KnowledgeType

        asts: list[Any] = []
        refs: list[str] = []
        unresolved: list[str] = []
        seen_asts: set[str] = set()
        seen_refs: set[str] = set()

        for obligation in obligations:
            text = f"{obligation.question} {obligation.rationale}"
            found = _subject_refs(text, obligation.satisfaction_criteria)
            rule = _rule_of(obligation.created_by)

            if found and rule in _LOCAL_RULES:
                for ref in found:
                    if ref not in seen_refs:
                        seen_refs.add(ref)
                        refs.append(ref)
                continue

            if rule in _EXPANSION_RULES:
                ast = QueryAST(
                    verb=QueryVerb.FIND,
                    concept=_EXPANSION_RULES[rule],
                    subject_class=str(getattr(obligation.target_knowledge_type, "value", "entity")),
                    scope=ScopeClause(universe=UniverseScope.AVAILABLE_SOURCES, terms=tuple(found)),
                    output=OutputProjection(),
                    question=obligation.question,
                )
                if ast.ast_id not in seen_asts:
                    seen_asts.add(ast.ast_id)
                    asts.append(ast)
                continue

            if obligation.target_knowledge_type is KnowledgeType.ENTITY and found:
                for ref in found:
                    if ref not in seen_refs:
                        seen_refs.add(ref)
                        refs.append(ref)
                continue

            unresolved.append(obligation.question)

        return tuple(asts), tuple(refs), tuple(unresolved)

    def compile_questions(
        self, questions: Sequence[str], *, context_question: str = ""
    ) -> tuple[tuple[Any, ...], tuple[str, ...]]:
        """Compile questions into ASTs. Returns ``(asts, unparsed)``.

        A question that does not compile is reported, not dropped. Obligations are written in
        prose, so some will not be in the grammar -- and the count of those is a measure of
        how much of the obligation vocabulary the compiler actually covers.
        """
        from context.query_grammar import QueryParseError, parse
        from context.query_proposal import compile_proposal

        compiled: list[Any] = []
        unparsed: list[str] = []
        for question in questions:
            proposal = compile_proposal(
                question, _as_query(question), adapter_ref="obligation"
            )
            if proposal.accepted and proposal.ast is not None:
                compiled.append(proposal.ast)
                continue
            # The grammar is the authority; a second attempt with the raw wording through
            # ``parse`` covers a question that was never proposed in grammar form.
            try:
                compiled.append(parse(question))
            except QueryParseError:
                unparsed.append(question)
        if not compiled and context_question:
            try:
                compiled.append(parse(context_question))
            except QueryParseError:
                unparsed.append(context_question)
        return tuple(compiled), tuple(unparsed)

    # -- acquisition ----------------------------------------------------------

    def plan_requests(self, context: Any, asts: Sequence[Any]) -> tuple[Any, ...]:
        """Plan the searches for the questions not yet asked."""
        if not asts:
            return ()
        return self._ledger.pending(context, list(asts), self._cycle)

    def drain_frontier(
        self, *, tenant_id: str, investigation_id: str, limit: int = 10
    ) -> list[Any]:
        """Collect finished frontier items as acquisition results.

        Returns rather than raises. A platform with no frontier, or a tenant whose frontier
        is empty, has simply acquired nothing yet -- which is the normal state of a fresh
        investigation and not an error worth propagating into the HTTP layer.
        """
        if self._frontier_factory is None:
            return []
        try:
            frontier = self._frontier_factory()
        except Exception as exc:  # noqa: BLE001
            log.debug("frontier unavailable: %s", exc)
            return []
        if frontier is None:
            return []
        results: list[Any] = []
        try:
            for _ in range(max(1, int(limit))):
                item = frontier.pop_next(tenant_id=tenant_id)
                if item is None:
                    break
                results.append(
                    _result_from_item(item, investigation_id=investigation_id)
                )
        except Exception as exc:  # noqa: BLE001
            log.warning("frontier drain failed for %s: %s", investigation_id, exc)
        return results

    # -- the pass -------------------------------------------------------------

    async def run_tick(
        self,
        context: Any,
        *,
        results: Sequence[Any] = (),
        tenant_id: str = "",
    ) -> TickReport:
        """Run every phase and report what moved.

        Never raises for a phase that could not run. The context's own id supplies the
        tenant when none is given, because these are two views of the same scope and a
        mismatch would resolve membership against the wrong tenant -- which returns nothing
        and looks exactly like an investigation that gathered no evidence.
        """
        scope = tenant_id or str(getattr(context, "tenant_id", "") or "")
        report = TickReport(context_id=context.context_id)

        obligations = await self._open_obligations(context)
        questions = tuple(
            obligation.question
            for obligation in obligations
            if str(getattr(obligation.question, "strip", lambda: "")()).strip()
        )
        report.phases.append(
            PhaseResult(
                "read_obligations",
                True,
                f"{len(obligations)} open",
                len(obligations),
            )
        )

        asts, refs, unresolved = self.compile_obligations(obligations)
        # The grammar path still runs, for questions written as queries rather than raised
        # by a rule. Structural compilation is the primary path because obligations are
        # machine records; this one handles analyst phrasing.
        prose_asts, unparsed = self.compile_questions(
            (q for q in questions if q in unresolved),
            context_question=str(getattr(context, "question", "") or ""),
        )
        # De-duplicated by ``ast_id``, not by identity: ``QueryAST`` is a frozen dataclass
        # whose evidence_requirements mapping makes it unhashable, and hashing the node
        # instead would deduplicate nothing while raising TypeError.
        by_id: dict[str, Any] = {}
        for ast in (*asts, *prose_asts):
            by_id.setdefault(ast.ast_id, ast)
        asts = tuple(by_id[key] for key in sorted(by_id))
        report.unparsed = unparsed
        report.subjects = refs
        # An empty obligation set is the normal state of a context that has just been
        # created -- the first tick raises them, it does not find them. Reporting that as a
        # failed phase would mark a healthy fresh investigation as broken.
        report.phases.append(
            PhaseResult(
                "compile_queries",
                True,
                f"{len(asts)} queries, {len(refs)} local subjects, "
                f"{len(unresolved)} unresolved",
                len(asts),
            )
        )
        report.ast_ids = tuple(ast.ast_id for ast in asts)

        try:
            plans = self.plan_requests(context, asts)
            report.requests = self._cycle.requests_for(plans)
            report.phases.append(
                PhaseResult("plan_searches", True, f"{len(report.requests)} requests", len(report.requests))
            )
        except Exception as exc:  # noqa: BLE001
            report.phases.append(PhaseResult("plan_searches", False, str(exc)))

        if results:
            try:
                outcomes = await self._cycle.apply(context, list(results), tenant_id=scope)
            except Exception as exc:  # noqa: BLE001
                report.phases.append(PhaseResult("resolve_membership", False, str(exc)))
                outcomes = ()
        else:
            report.phases.append(PhaseResult("resolve_membership", True, "no results", 0))
            outcomes = ()

        step = None
        try:
            step = await self._loop.tick(context, outcomes=outcomes)
            # ``LoopStep.feedback_signals`` is a count, not a list: the signals themselves
            # were already consumed by the engine to create obligations, and they are
            # reported through the obligation phase. Reading it as a sequence raises
            # ``TypeError: object of type 'int' has no len()`` and loses the tick.
            report.feedback_signals = int(getattr(step, "feedback_signals", 0) or 0)
            report.revision = int(getattr(getattr(step, "revision", None), "revision", 0) or 0)
            report.obligations = len(getattr(step, "obligations_created", ()) or ())
            report.phases.append(
                PhaseResult(
                    "tick_context",
                    True,
                    f"{report.feedback_signals} signals, {report.obligations} obligations",
                )
            )
        except Exception as exc:  # noqa: BLE001
            report.phases.append(PhaseResult("tick_context", False, str(exc)))

        if outcomes:
            from context_engine.return_path import newly_grounded, unplaced

            report.grounded = newly_grounded((), outcomes)
            report.unplaced = unplaced(outcomes)

        try:
            cells = await self._fabric_store.load_cells(context.context_id)
            report.cell_ids = tuple(cell.cell_id for cell in cells)
            report.phases.append(
                PhaseResult("load_cells", True, f"{len(cells)} cells", len(cells))
            )
        except Exception as exc:  # noqa: BLE001
            report.phases.append(PhaseResult("load_cells", False, str(exc)))

        await self._read_lattice(context, report, tenant_id=scope)

        try:
            fabric_report = await self._fabric_store.latest_report(context.context_id)
            saturation = (fabric_report or {}).get("saturation") or {}
            report.saturated = str(saturation.get("verdict", "") or "")
        except Exception as exc:  # noqa: BLE001
            log.debug("no fabric report for %s: %s", context.context_id, exc)

        return report


#: Rules whose obligations are answered by resolving a subject locally, not by searching.
#: An undetermined scope is the clear case: the evidence exists and its membership is
#: unestablished, so the answer is in the entity stream rather than at another source.
_LOCAL_RULES: frozenset[str] = frozenset({"coverage_gap", "unresolved_identity", "obstruction"})

#: Rules whose obligation *is* a search, and what concept to search for. A saturation
#: shortfall means the evidence is not independent, which asks for breadth, not a filter --
#: so the query carries the concept and nothing else.
_EXPANSION_RULES: dict[str, str] = {
    "saturation_shortfall": "source_expansion",
    "counter_hypothesis_search": "counter_hypothesis",
    "discriminating_test": "discriminating_evidence",
}

#: Prefixes of the subject refs this platform mints. Matched on a prefix rather than parsed
#: out of free text, so an id-shaped string in a rationale cannot be mistaken for a ref.
_REF_PREFIXES: tuple[str, ...] = ("OBS-", "ENT-", "SRC-", "REL-", "RES-")


def _rule_of(created_by: str) -> str:
    """The rule name from ``created_by``.

    ``created_by`` is the only machine-readable handle an obligation carries -- it is
    written as ``...#rule_name`` -- so it is what decides which of the three obligation
    kinds this is. Falling back to the bare rule name keeps an already-bare value working.
    """
    text = str(created_by or "")
    return text.rsplit("#", 1)[-1].strip()


def _subject_refs(text: str, criteria: Sequence[str] = ()) -> tuple[str, ...]:
    """The subject refs named in an obligation.

    Scanned for the platform's own id prefixes. Deliberately not a general word extractor:
    turning every capitalised token in a rationale into a search term would issue queries
    for ``rule`` and ``saturation.reason@1.0``.
    """
    import re

    found: list[str] = []
    haystack = f"{text} {' '.join(criteria or ())}"
    for match in re.finditer(r"[A-Z]{2,}-[A-Za-z0-9_.:-]+", haystack):
        ref = match.group(0).rstrip(".,;:")
        if ref.startswith(_REF_PREFIXES) and ref not in found:
            found.append(ref)
    for item in criteria or ():
        text_item = str(item)
        if text_item.startswith(_REF_PREFIXES) and text_item not in found:
            found.append(text_item)
    return tuple(found)


def _as_query(question: str) -> str:
    """The question, passed through unchanged for the grammar to accept or reject.

    No attempt to reshape prose into the grammar here. The grammar is the sole authority on
    what a query means, and a shim that rewrote wording would put a second, looser reader in
    front of it -- which is how a query ends up meaning something nobody typed.
    """
    return question.strip()


def _result_from_item(item: Any, *, investigation_id: str) -> Any:
    """Turn a finished frontier item into an acquisition result."""
    from context_engine.return_path import AcquisitionResult

    observation_id = str(getattr(item, "observation_id", "") or "")
    return AcquisitionResult(
        action_id=str(getattr(item, "frontier_id", "") or ""),
        task_id=str(getattr(item, "frontier_id", "") or ""),
        observation_ids=(observation_id,) if observation_id else (),
        coverage_delta=1.0 if observation_id else 0.0,
        provenance={
            "uri": str(getattr(item, "uri", "") or ""),
            "source_id": str(getattr(item, "source_id", "") or ""),
            "investigation_id": investigation_id,
        },
    )
