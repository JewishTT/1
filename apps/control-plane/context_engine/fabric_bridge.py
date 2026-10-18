"""Control-plane bridge: fabric findings into the engine's own signal vocabulary.

``apps/science`` sits above ``control-plane`` in ``LAYER_ORDER``, so the fabric
cannot import ``context_engine.engine`` and therefore emits neutral ``Finding``
objects. This module is the single place the two vocabularies meet -- the same
reasoning that removed the duplicated ``ScienceFeedback`` dataclass in W0.

Keeping one translation point matters more than it looks. The engine's
``TriggerKind`` has six members and the fabric's ``FindingKind`` has seven; if each
layer decided for itself how to phrase a question, the same conflict would produce
different questions depending on which code path observed it, and the obligation
ledger would no longer be a record of what the investigation was actually told.

Every finding maps to exactly one ``TriggerKind`` and one ``KnowledgeType``, and the
mapping is total: an unmapped kind raises rather than silently defaulting to a
low-priority entity question, which is how a contradiction ends up filed as trivia.
"""

from __future__ import annotations

from typing import Any

from context.fabric import FabricReport, Finding, FindingKind

from context_engine.engine import GapSignal, TriggerKind
from context_engine.obligations import KnowledgeType
from context_engine.obligations import SaturationState as EngineSaturationState

#: Total mapping. A kind absent from this table is a bug in the fabric, not a
#: reason to invent a default trigger.
_TRIGGER_BY_KIND: dict[FindingKind, TriggerKind] = {
    FindingKind.CONTRADICTION: TriggerKind.CONTRADICTION,
    FindingKind.COVERAGE_GAP: TriggerKind.COVERAGE_GAP,
    FindingKind.OPERATOR_INTENT: TriggerKind.OPERATOR_INTENT,
    FindingKind.ANOMALY: TriggerKind.ANOMALY,
    FindingKind.LOW_CONFIDENCE: TriggerKind.LOW_CONFIDENCE,
    FindingKind.SATURATION_SHORTFALL: TriggerKind.SATURATION_SHORTFALL,
    FindingKind.UNRESOLVED_IDENTITY: TriggerKind.COVERAGE_GAP,
    FindingKind.CONTESTED_LOCALITY: TriggerKind.CONTRADICTION,
}

#: What kind of knowledge the question is asking for. A contradiction asks for an
#: explanation, a coverage gap asks for a fact, a locality contest asks for an
#: adjudication -- filing them all as ENTITY would flatten the ledger.
_KNOWLEDGE_BY_KIND: dict[FindingKind, KnowledgeType] = {
    FindingKind.CONTRADICTION: KnowledgeType.CONTRADICTION,
    FindingKind.CONTESTED_LOCALITY: KnowledgeType.RELATION,
    FindingKind.COVERAGE_GAP: KnowledgeType.ATTRIBUTE,
    FindingKind.OPERATOR_INTENT: KnowledgeType.ENTITY,
    FindingKind.ANOMALY: KnowledgeType.ATTRIBUTE,
    FindingKind.LOW_CONFIDENCE: KnowledgeType.ATTRIBUTE,
    FindingKind.SATURATION_SHORTFALL: KnowledgeType.ENTITY,
    FindingKind.UNRESOLVED_IDENTITY: KnowledgeType.ENTITY,
}


class UnanchoredFinding(ValueError):
    """A science finding arrived with nothing to point at.

    Spec 030 FR-066. A finding becomes a ``ResearchObligation`` through this module, and an
    obligation is what the investigation treats as knowledge it still owes. Letting a finding
    with no ``refs`` through produced an obligation that no evidence, no snapshot and no
    operator could ever satisfy -- and, worse, one that read like a grounded demand rather
    than an unanchored guess.

    This is raised, not defaulted. ``refs=()`` is a legitimate state for an exploratory note
    inside the science layer; it is not a legitimate state at the boundary where research
    state is created from it.
    """


def to_signal(finding: Finding) -> GapSignal:
    """Translate one anchored finding, or fail loudly on an unmapped or unanchored kind."""
    trigger = _TRIGGER_BY_KIND.get(finding.kind)
    knowledge = _KNOWLEDGE_BY_KIND.get(finding.kind)
    if trigger is None or knowledge is None:
        raise KeyError(
            f"finding kind {finding.kind.value!r} has no declared translation; add it "
            "to _TRIGGER_BY_KIND and _KNOWLEDGE_BY_KIND rather than defaulting"
        )
    if not tuple(finding.refs):
        raise UnanchoredFinding(
            f"finding kind {finding.kind.value!r} carries no refs and cannot become a "
            f"research obligation (rule={finding.rule_id or 'unset'!r}, "
            f"question={finding.question[:80]!r}). Anchor it to observations or a snapshot, "
            "or record it as an exploratory note rather than an obligation (FR-066)"
        )
    return GapSignal(
        kind=trigger,
        question=finding.question,
        rationale=(
            f"{finding.rationale} [rule={finding.rule_id}]" if finding.rule_id else finding.rationale
        ),
        knowledge_type=knowledge,
        priority=max(0.0, min(1.0, finding.priority)),
        evidence_refs=finding.refs,
    )


def to_signals(report: FabricReport) -> tuple[GapSignal, ...]:
    """Translate a whole pass, strongest first.

    Ordering is by priority because the obligation generator consumes signals in
    order and the frontier is built from what comes out; a contradiction filed behind
    a coverage question is a contradiction nobody reaches this tick.

    One unanchored finding fails the whole pass. Silently skipping it would let a fabric
    that is losing its inputs keep producing obligations from the remainder, which is how
    a degrading detector becomes a quiet one.
    """
    signals = [to_signal(finding) for finding in report.findings]
    signals.sort(key=lambda signal: (-signal.priority, signal.question))
    return tuple(signals)


def describe(report: FabricReport) -> dict[str, Any]:
    """A compact summary for a revision note or a loop log line."""
    return {
        "context_id": report.context_id,
        "cells": len(report.cell_ids),
        "findings": len(report.findings),
        "contradictions": len(report.contradictions),
        "raw_sources": report.independence.raw_count if report.independence else 0,
        "n_eff": report.independence.n_eff if report.independence else 0.0,
        "gluing": report.gluing.verdict.value if report.gluing else "",
        "saturation": report.saturation.verdict.value if report.saturation else "",
        "completeness": report.completeness.feasible_mode.value if report.completeness else "",
    }


# ---------------------------------------------------------------------------
# Saturation translation
# ---------------------------------------------------------------------------
#
# The fabric decides whether a *pass* has stopped teaching us anything, on measured
# coverage, measured independence and measured marginal gain, with a reason code for
# every verdict. The engine decides whether *one obligation* is settled. Those are
# different questions and this function is the only place they are allowed to meet.
#
# Two rules govern the translation:
#
# 1. An unknown input stays unknown. The fabric leaves ``coverage`` as None when its
#    completeness conditions were not all satisfied, and leaves ``marginal_gain`` as
#    None when nothing measured it. Both arrive here as ``*_known=False``. Writing
#    them as 0.0 would be the worst possible reading: 0.0 coverage is a measurement
#    of nothing, and 0.0 gain satisfies ``<= marginal_gain_threshold``, so a pass
#    that measured nothing at all would read as the most-settled pass possible.
#
# 2. A blocked verdict is carried, not flattened. ``BLOCKED`` names an unresolved
#    obstruction, and that obstruction is the reason the obligation stays open -- it
#    is precisely the information the loop needs in order to stop spinning on work
#    that cannot succeed.


def to_engine_saturation(
    report: FabricReport,
    *,
    coverage_threshold: float = 0.9,
    marginal_gain_threshold: float = 0.05,
) -> EngineSaturationState | None:
    """The pass-level verdict in the engine's vocabulary, or None if there is none.

    ``None`` is an honest answer, not a failure: it means this pass produced no
    saturation verdict, and the caller must then fall back to whatever evidence it
    actually holds rather than to a default that would decide the question for it.
    """
    verdict = report.saturation
    if verdict is None:
        return None

    coverage = verdict.coverage
    marginal_gain = verdict.marginal_gain

    return EngineSaturationState(
        coverage=float(coverage) if coverage is not None else 0.0,
        coverage_known=coverage is not None,
        marginal_gain=float(marginal_gain) if marginal_gain is not None else 0.0,
        marginal_gain_known=marginal_gain is not None,
        distinct_sources=int(verdict.distinct_sources),
        source_diversity=int(verdict.source_families),
        stopping_condition=(
            f"fabric:{verdict.verdict.value}"
            f"[{','.join(sorted(code.value for code in verdict.reason_codes))}]"
        ),
        coverage_threshold=coverage_threshold,
        marginal_gain_threshold=marginal_gain_threshold,
        # The fabric's own independence gate, carried across so the engine cannot
        # close an obligation the fabric refused to call broad. ``n_eff`` is a float
        # because it is a fractional effective count; the engine's field is an int, so
        # the requirement is the floor it enforced. Two effective sources were always
        # the minimum the fabric considered non-syndicated.
        required_independent_sources=(
            int(verdict.effective_independent_sources)
            if verdict.verdict.value in ("saturated", "blocked")
            else 0
        ),
        required_source_families=(
            int(verdict.source_families) if verdict.verdict.value == "saturated" else 0
        ),
    )