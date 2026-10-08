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


def to_signal(finding: Finding) -> GapSignal:
    """Translate one finding, or fail loudly on an unmapped kind."""
    trigger = _TRIGGER_BY_KIND.get(finding.kind)
    knowledge = _KNOWLEDGE_BY_KIND.get(finding.kind)
    if trigger is None or knowledge is None:
        raise KeyError(
            f"finding kind {finding.kind.value!r} has no declared translation; add it "
            "to _TRIGGER_BY_KIND and _KNOWLEDGE_BY_KIND rather than defaulting"
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