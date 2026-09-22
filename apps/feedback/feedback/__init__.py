"""Feedback plane: adaptive loop closing (T116-T118)."""

from __future__ import annotations

from .branch import (
    EntityResolutionHints,
    FindingCandidate,
    SourceOutcomeFeedback,
    run_entity_feedback,
    run_finding_feedback,
    run_source_feedback,
)
from .frontier import (
    FeedbackCandidate,
    FrontierSink,
    MemoryFrontierSink,
    PgFrontierSink,
    retrieval_key_uri,
)

__all__ = [
    "EntityResolutionHints",
    "FeedbackCandidate",
    "FindingCandidate",
    "FrontierSink",
    "MemoryFrontierSink",
    "PgFrontierSink",
    "SourceOutcomeFeedback",
    "retrieval_key_uri",
    "run_entity_feedback",
    "run_finding_feedback",
    "run_source_feedback",
]
