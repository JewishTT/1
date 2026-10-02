"""Research lineage: Context -> Obligation -> Action -> Task -> Result -> ContextRevision.

Feature 024 FR-079/FR-080. The other two lineages already exist -- ``evidence_lineage``
provides ``EVIDENCE_BACKWARD_CHAIN`` and ``DERIVATION_FORWARD_CHAIN`` -- but neither
mentions research: the word does not appear in the module, and ``HopKind`` has no
obligation, action, or question hop. So the chain "what did we set out to learn, and
what did we actually learn" is not traversable anywhere in the platform.

This is the third dimension, not a variant of the others:

* **evidence** answers "where did this come from" (backwards, to raw bytes);
* **derivation** answers "what did this produce" (forwards, from raw bytes);
* **research** answers "why was this looked for, and did looking answer it" --
  which crosses from intent to outcome, a direction neither of the others spans.

Reused, not reinvented: ``evidence_lineage.EvidenceHop`` and ``LineageTrace`` are used
as-is for the result side, so a research trace composes with the existing ones instead
of introducing a parallel tracing vocabulary.
"""

from __future__ import annotations

import enum
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

RESEARCH_HOP_ORDER = (
    "context",
    "obligation",
    "action",
    "task",
    "result",
    "context_revision",
)


class ResearchHopKind(enum.StrEnum):
    """The six research hops. Ordered, not ranked: the chain is a sequence."""

    CONTEXT = "context"
    OBLIGATION = "obligation"
    ACTION = "action"
    TASK = "task"
    RESULT = "result"
    CONTEXT_REVISION = "context_revision"


@dataclass(frozen=True, slots=True)
class ResearchHop:
    kind: ResearchHopKind
    ref: str
    label: str = ""
    detail: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", ResearchHopKind(self.kind))
        if not self.ref:
            raise ValueError("a research hop must reference something")

    @property
    def order(self) -> int:
        return RESEARCH_HOP_ORDER.index(self.kind.value)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "ref": self.ref,
            "label": self.label,
            "detail": dict(self.detail),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ResearchHop:
        return cls(
            kind=ResearchHopKind(payload["kind"]),
            ref=payload["ref"],
            label=payload.get("label", ""),
            detail=dict(payload.get("detail", {})),
        )


@dataclass(frozen=True, slots=True)
class ResearchTrace:
    """One complete research chain.

    ``complete`` is reported rather than assumed: a broken chain names where it broke,
    exactly as ``evidence_lineage.LineageTrace`` does. A research trace that quietly
    truncated would read as "we asked and found nothing", which is the specific
    dishonesty input.md §36.5 warns about.
    """

    context_id: str
    hops: tuple[ResearchHop, ...]
    outcome: str = "open"
    break_at: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "hops", tuple(self.hops))
        kinds = [h.kind.value for h in self.hops]
        if kinds != [k for k in RESEARCH_HOP_ORDER if k in kinds]:
            raise ValueError(f"research hops are out of order: {kinds}")

    @property
    def complete(self) -> bool:
        return len(self.hops) == len(RESEARCH_HOP_ORDER)

    @property
    def obligation_ids(self) -> tuple[str, ...]:
        return tuple(h.ref for h in self.hops if h.kind is ResearchHopKind.OBLIGATION)

    @property
    def action_ids(self) -> tuple[str, ...]:
        return tuple(h.ref for h in self.hops if h.kind is ResearchHopKind.ACTION)

    def to_dict(self) -> dict[str, Any]:
        return {
            "context_id": self.context_id,
            "hops": [h.to_dict() for h in self.hops],
            "outcome": self.outcome,
            "break_at": self.break_at,
            "complete": self.complete,
        }


class ResearchLineage:
    """Traversable research chains, both directions.

    Backwards answers "why did we look at this result"; forwards answers "what came of
    that obligation".
    """

    def __init__(self, traces: Iterable[ResearchTrace] = ()) -> None:
        self._traces: list[ResearchTrace] = list(traces)
        self._by_result: dict[str, ResearchTrace] = {}
        self._by_obligation: dict[str, list[ResearchTrace]] = {}
        self._by_action: dict[str, list[ResearchTrace]] = {}
        self._by_revision: dict[str, ResearchTrace] = {}
        for trace in self._traces:
            self._index(trace)

    def _index(self, trace: ResearchTrace) -> None:
        by_kind = {h.kind: h.ref for h in trace.hops}
        result = by_kind.get(ResearchHopKind.RESULT)
        if result:
            self._by_result[result] = trace
        revision = by_kind.get(ResearchHopKind.CONTEXT_REVISION)
        if revision:
            self._by_revision[revision] = trace
        for obligation in trace.obligation_ids:
            self._by_obligation.setdefault(obligation, []).append(trace)
        for action in trace.action_ids:
            self._by_action.setdefault(action, []).append(trace)

    def add(self, trace: ResearchTrace) -> None:
        self._traces.append(trace)
        self._index(trace)

    # -- forward -------------------------------------------------------------

    def for_obligation(self, obligation_id: str) -> tuple[ResearchTrace, ...]:
        return tuple(self._by_obligation.get(obligation_id, ()))

    def for_action(self, action_id: str) -> tuple[ResearchTrace, ...]:
        return tuple(self._by_action.get(action_id, ()))

    def obligations_for(self, context_id: str) -> tuple[str, ...]:
        refs = {
            obligation
            for trace in self._traces
            if trace.context_id == context_id
            for obligation in trace.obligation_ids
        }
        return tuple(sorted(refs))

    # -- backward ------------------------------------------------------------

    def explain_result(self, result_ref: str) -> ResearchTrace | None:
        """Why was this result sought, and by which obligation?"""
        return self._by_result.get(result_ref)

    def what_revised(self, revision_ref: str) -> ResearchTrace | None:
        return self._by_revision.get(revision_ref)

    # -- whole-context -------------------------------------------------------

    def context_traces(self, context_id: str) -> tuple[ResearchTrace, ...]:
        return tuple(t for t in self._traces if t.context_id == context_id)

    def unanswered(self, context_id: str) -> tuple[str, ...]:
        """Obligations with no result hop. The research analogue of unknown-vs-empty."""
        return tuple(
            sorted(
                {
                    obligation
                    for trace in self.context_traces(context_id)
                    if trace.outcome != "answered"
                    for obligation in trace.obligation_ids
                }
            )
        )

    def __len__(self) -> int:
        return len(self._traces)


def build_trace(
    *,
    context_id: str,
    obligation_id: str,
    action_id: str | None = None,
    task_id: str | None = None,
    result_ref: str | None = None,
    revision_ref: str | None = None,
    outcome: str = "open",
    labels: Mapping[ResearchHopKind, str] | None = None,
) -> ResearchTrace:
    """Assemble a chain, recording precisely where it stops.

    Every hop is optional except context and obligation, because a chain that never
    reached an action is a real state -- and hiding it would make an unstarted
    obligation indistinguishable from one that produced nothing.
    """
    labels = labels or {}
    hops: list[ResearchHop] = [
        ResearchHop(
            kind=ResearchHopKind.CONTEXT,
            ref=context_id,
            label=labels.get(ResearchHopKind.CONTEXT, ""),
        )
    ]
    break_at = ""
    plan = (
        (ResearchHopKind.OBLIGATION, obligation_id),
        (ResearchHopKind.ACTION, action_id),
        (ResearchHopKind.TASK, task_id),
        (ResearchHopKind.RESULT, result_ref),
        (ResearchHopKind.CONTEXT_REVISION, revision_ref),
    )
    for kind, ref in plan:
        if ref:
            hops.append(ResearchHop(kind=kind, ref=ref, label=labels.get(kind, "")))
        elif not break_at:
            break_at = kind.value
    return ResearchTrace(
        context_id=context_id,
        hops=tuple(hops),
        outcome=outcome if not break_at else "open",
        break_at=break_at,
    )


__all__ = [
    "RESEARCH_HOP_ORDER",
    "ResearchHop",
    "ResearchHopKind",
    "ResearchLineage",
    "ResearchTrace",
    "build_trace",
]
