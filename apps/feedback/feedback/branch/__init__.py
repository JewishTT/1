"""Feedback plane branches (T116-T118): import to register them."""

from __future__ import annotations

from .entity import EntityResolutionHints, run_entity_feedback
from .finding import FindingCandidate, run_finding_feedback
from .source import SourceOutcomeFeedback, recommend_source_policy, run_source_feedback

__all__ = [
    "EntityResolutionHints",
    "FindingCandidate",
    "SourceOutcomeFeedback",
    "recommend_source_policy",
    "run_entity_feedback",
    "run_finding_feedback",
    "run_source_feedback",
]
