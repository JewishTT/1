"""The runner: one fabric pass, persisted, translated into engine signals.

This is the seam between the pure fabric and the live engine. It does four things in
order, and the order is the point:

1. **Load** the context's existing cells and hypotheses, so this pass continues the
   previous one instead of restarting. Without the load, cells never deepen.
2. **Run** the fabric over the incoming batch.
3. **Persist** cells, propositions, contradictions and the report, so the next pass and
   any later reader can see what was concluded and why.
4. **Translate** findings into ``GapSignal`` for the obligation generator.

The runner is injected into ``CognitiveLoop`` as a ``Protocol`` rather than imported,
for the same reason ``ObservationSource`` is: the loop must be testable with no
database and no science layer loaded, and a hard dependency on either would make that
impossible.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from context.dialectics import Hypothesis
from context.fabric import (
    FabricInput,
    FabricReport,
    Observation,
    run_fabric,
)

from context_engine.engine import GapSignal
from context_engine.fabric_bridge import describe, to_signals


class FabricRunner(Protocol):
    """What the loop needs from a fabric pass."""

    async def run(
        self,
        *,
        context_id: str,
        observations: Sequence[Observation] = (),
        hypotheses: Sequence[Hypothesis] = (),
        question: str = "",
        coverage_evidence: Mapping[str, bool] | None = None,
        revision_id: str = "",
        root_scope: Any = None,
    ) -> tuple[tuple[GapSignal, ...], FabricReport | None]:
        """Produce signals for this tick, and the report behind them.

        ``root_scope`` warrants the first cell and is ignored once cells exist.
        ``revision_id`` ties the persisted report to the engine revision it ran beside.
        """
        ...


class InMemoryFabricRunner:
    """A runner with no persistence, for tests and for a dry tick.

    Cells still accumulate across calls within one instance, so depth behaviour is
    exercised without a database -- the growth semantics are identical to the durable
    runner's; only the writing differs.
    """

    def __init__(self, *, parity=None, gluing_profile=None) -> None:
        self._cells: dict[str, list] = {}
        self._hypotheses: dict[str, tuple[Hypothesis, ...]] = {}
        self._parity = parity
        self._gluing_profile = gluing_profile
        self.passes = 0

    async def run(
        self,
        *,
        context_id: str,
        observations: Sequence[Observation] = (),
        hypotheses: Sequence[Hypothesis] = (),
        question: str = "",
        coverage_evidence: Mapping[str, bool] | None = None,
        revision_id: str = "",
        root_scope: Any = None,
    ) -> tuple[tuple[GapSignal, ...], FabricReport | None]:
        report = run_fabric(
            FabricInput(
                context_id=context_id,
                observations=tuple(observations),
                existing_cells=tuple(self._cells.get(context_id, ())),
                hypotheses=tuple(hypotheses) or self._hypotheses.get(context_id, ()),
                question=question,
                coverage_evidence=dict(coverage_evidence or {}),
                parity=self._parity,
                gluing_profile=self._gluing_profile,
                root_scope=root_scope,
            )
        )
        self.passes += 1
        self._cells[context_id] = list(report.growth.cells if report.growth else ())
        self._hypotheses[context_id] = tuple(hypotheses)
        return to_signals(report), report

    def cells_for(self, context_id: str) -> tuple:
        return tuple(self._cells.get(context_id, ()))


class DurableFabricRunner:
    """The production runner: loads prior state, persists everything, returns signals.

    Persisting before translating is deliberate. If the translation raised, the pass
    would be lost and the next tick would silently re-derive from older cells; writing
    first means a failed translation leaves the evidence of the pass on record.
    """

    def __init__(self, fabric_store: Any, *, tenant_id: str = "", parity=None) -> None:
        self._store = fabric_store
        self._tenant_id = tenant_id
        self._parity = parity
        self._last_report_id: dict[str, str] = {}

    async def run(
        self,
        *,
        context_id: str,
        observations: Sequence[Observation] = (),
        hypotheses: Sequence[Hypothesis] = (),
        question: str = "",
        coverage_evidence: Mapping[str, bool] | None = None,
        revision_id: str = "",
        root_scope: Any = None,
    ) -> tuple[tuple[GapSignal, ...], FabricReport | None]:
        existing_cells = await self._store.load_cells(context_id)
        report = run_fabric(
            FabricInput(
                context_id=context_id,
                observations=tuple(observations),
                existing_cells=existing_cells,
                hypotheses=tuple(hypotheses),
                question=question,
                coverage_evidence=dict(coverage_evidence or {}),
                parity=self._parity,
                root_scope=root_scope,
            )
        )
        if report.growth is not None:
            await self._store.save_cells(report.growth.cells)
        await self._store.save_propositions(report.propositions, context_id=context_id)
        await self._store.save_contradictions(report.contradictions, context_id=context_id)
        report_id = await self._store.save_report(report, revision_id=revision_id)
        self._last_report_id[context_id] = report_id
        return to_signals(report), report

    async def link_revision(self, context_id: str, revision_id: str) -> None:
        """Attribute the last pass for this context to the revision that consumed it.

        Optional on purpose: the loop calls this through ``getattr`` so an injected
        runner that does not persist has nothing to link and is not forced to implement
        a method it has no use for.
        """
        report_id = self._last_report_id.get(context_id, "")
        if not report_id or not revision_id:
            return
        link = getattr(self._store, "link_report_revision", None)
        if link is not None:
            await link(report_id, revision_id)


def observations_from_outcomes(
    outcomes: Sequence[Any],
    *,
    scopes: Mapping[str, Sequence[str]] | None = None,
    support: Mapping[str, Sequence[str]] | None = None,
    refutation: Mapping[str, Sequence[str]] | None = None,
    revealed_by: Mapping[str, str] | None = None,
) -> tuple[Observation, ...]:
    """Build fabric observations from the loop's existing outcome shape.

    ``ObservationOutcome`` carries observation ids but no scope, and a scope is the
    one thing the fabric cannot invent -- §0.2 forbids assuming membership nobody
    established. So a caller with no scope mapping gets an *undetermined* scope, which
    the fabric refuses and records, rather than a guess that would silently attach the
    observation to whatever cell happened to be first.
    """
    scope_map = dict(scopes or {})
    support_map = dict(support or {})
    refutation_map = dict(refutation or {})
    reveal_map = dict(revealed_by or {})

    built: list[Observation] = []
    for outcome in outcomes:
        for observation_id in getattr(outcome, "produced_observations", ()) or ():
            built.append(
                Observation(
                    observation_id=observation_id,
                    entities=tuple(scope_map.get(observation_id, ())),
                    supporting=tuple(support_map.get(observation_id, ())),
                    refuting=tuple(refutation_map.get(observation_id, ())),
                    revealed_by=reveal_map.get(observation_id, ""),
                )
            )
    return tuple(built)


def summarise(report: FabricReport | None) -> dict[str, Any]:
    """A log-sized description, or an empty record when no pass ran."""
    return describe(report) if report is not None else {}