"""SpecOps & Counterintelligence domain silo.

Operational context is read from the Intelligence Silo. This package deliberately
contains no discovery, recon, crawler, connector, or target-enumeration logic.
"""
from .domain import (
    AssessmentContext,
    AssessmentKind,
    EngagementAuthorization,
    build_assessment_context,
)

__all__ = [
    "AssessmentContext",
    "AssessmentKind",
    "EngagementAuthorization",
    "build_assessment_context",
]
