"""SpecOps & CI application service: consume an Intelligence snapshot, never recon it."""
from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from shared.contracts.intelligence_feed import IntelligenceQuery, IntelligenceReadPort
from .domain import (
    AssessmentContext,
    AssessmentKind,
    EngagementAuthorization,
    build_assessment_context,
)

SPECOPS_CI_PURPOSE = "authorized_security_assessment"


async def prepare_assessment(
    intelligence: IntelligenceReadPort,
    query: IntelligenceQuery,
    authorization: EngagementAuthorization,
    target_entity_ids: Iterable[str],
    assessment_kind: AssessmentKind,
    *,
    at: datetime | None = None,
) -> AssessmentContext:
    """Read the approved intel context and validate it before a downstream executor.

    Execution is intentionally outside this context-preparation service. No network
    probing, target discovery, crawling, or recon is performed by this silo.
    """
    if query.purpose != SPECOPS_CI_PURPOSE:
        raise ValueError(f"SpecOps&CI requests must use purpose={SPECOPS_CI_PURPOSE!r}")
    snapshot = await intelligence.get_snapshot(query)
    return build_assessment_context(
        snapshot=snapshot,
        authorization=authorization,
        target_entity_ids=target_entity_ids,
        assessment_kind=assessment_kind,
        at=at,
    )
