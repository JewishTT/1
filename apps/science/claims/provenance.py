"""Evidence-chain validation (T087, FR-001 / Constitution II).

Every claim must trace ``Claim -> EvidenceLink -> Observation -> Raw``. This
module validates that chain structurally: links are resolved to immutable,
content-addressed observations (``raw_sha256``) via an injected resolver, so
the fabric never registers a claim whose probability floats free of durable
evidence. Raises ``ProvenanceRequiredError`` on empty/unresolved chains.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from claims.model import EvidenceLink
from errors import ProvenanceRequiredError


class Observation(Protocol):
    """Immutable observation the link must resolve to."""

    observation_id: str
    raw_sha256: str


class ObservationResolver(Protocol):
    """Resolves an immutable observation by id (injected, never assumed global)."""

    def __call__(self, observation_id: str) -> Observation | None: ...


@dataclass(frozen=True)
class ResolvedLink:
    link: EvidenceLink
    observation: Observation
    raw_present: bool


def validate_provenance(
    links: list[EvidenceLink],
    resolver: ObservationResolver,
) -> list[ResolvedLink]:
    """Validate a claim's provenance chain; returns resolved links.

    Raises:
        ProvenanceRequiredError: empty chain, orphan observation, or raw content
            missing / address mismatch (FR-001, Constitution II).
    """
    if not links:
        raise ProvenanceRequiredError()

    resolved: list[ResolvedLink] = []
    for link in links:
        observation = resolver(link.observation_id)
        if observation is None:
            raise ProvenanceRequiredError(link.observation_id)
        if observation.raw_sha256 != link.raw_sha256:
            raise ProvenanceRequiredError(
                f"{link.observation_id}: raw_sha256 mismatch ("
                f"link={link.raw_sha256[:12]} obs={observation.raw_sha256[:12]})"
            )
        resolved.append(ResolvedLink(link=link, observation=observation, raw_present=True))
    return resolved