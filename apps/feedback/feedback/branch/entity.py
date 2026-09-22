"""T117: entity-resolution -> acquisition-hypothesis feedback branch.

Aliases / identifiers resolved for an entity become new RETRIEVAL KEYS, each
enqueued as a frontier pivot for the source that should look for them. Pivots
are deduplicated by the sink (unique (tenant_id, uri)); no bytes/observations
are written here (planner-side loop closing).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..frontier import FeedbackCandidate, retrieval_key_uri

PIVOT_KINDS = ("alias", "handle", "email", "phone", "domain", "identifier")


@dataclass
class EntityResolutionHints:
    entity_id: str
    tenant_id: str
    names: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    emails: list[str] = field(default_factory=list)
    phone_numbers: list[str] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)
    handles: list[str] = field(default_factory=list)
    confidence: float = 0.6
    investigation_id: str | None = None
    source_id: str | None = None
    work_id: str | None = None


def _pivots(hints: EntityResolutionHints) -> list[tuple[str, str]]:
    pivots: list[tuple[str, str]] = []
    for name in hints.names + hints.aliases:
        pivots.append(("alias", name))
    for handle in hints.handles:
        pivots.append(("handle", handle))
    for email in hints.emails:
        pivots.append(("email", email))
    for phone in hints.phone_numbers:
        pivots.append(("phone", phone))
    for domain in hints.domains:
        pivots.append(("domain", domain))
    return pivots


def run_entity_feedback(hints: EntityResolutionHints) -> list[FeedbackCandidate]:
    """Produce a frontier candidate per retrieval key (deduped by sink)."""
    candidates: list[FeedbackCandidate] = []
    seen: set[str] = set()
    for kind, key in _pivots(hints):
        if not key or not key.strip():
            continue
        normalized = f"{kind}:{key.strip().casefold()}"
        if normalized in seen:
            continue
        seen.add(normalized)
        priority = min(0.6, 0.2 + 0.4 * hints.confidence)
        candidates.append(
            FeedbackCandidate(
                uri=retrieval_key_uri("pivot", f"entity:{hints.entity_id}:{normalized}"),
                priority=priority,
                kind="pivot",
                tenant_id=hints.tenant_id,
                investigation_id=hints.investigation_id,
                source_id=hints.source_id,
                work_id=hints.work_id,
                reason=f"entity resolution: {kind} -> retrieval key",
                payload={"entity_id": hints.entity_id, "kind": kind, "key": key.strip()},
            )
        )
    return candidates
