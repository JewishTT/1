"""Request coalescing + canonical fan-out (T077, FR-008).

Coalesce identical acquisition intents across investigations: many intents that
resolve to the same canonical URL → one acquisition → one observation → fan-out
the observation to all waiters. Saves network + compute; prevents duplicate
acquisition of the same canonical content.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass


@dataclass
class AcquisitionIntent:
    intent_id: str
    uri: str
    canonical_url: str
    tenant_id: str
    investigation_id: str
    callback: asyncio.Future | None = None

    def __post_init__(self) -> None:
        ...


class RequestCoalescer:
    """Dedupes in-flight acquisition intents by canonical URL + fan-out (FR-008)."""

    def __init__(self) -> None:
        self._inflight: dict[str, list[AcquisitionIntent]] = {}
        self._completed: dict[str, str] = {}  # canonical_url -> observation_id

    def register(
        self, *, uri: str, canonical_url: str, tenant_id: str, investigation_id: str
    ) -> AcquisitionIntent:
        intent = AcquisitionIntent(
            intent_id="INT-" + uuid.uuid4().hex[:12],
            uri=uri,
            canonical_url=canonical_url,
            tenant_id=tenant_id,
            investigation_id=investigation_id,
            callback=asyncio.get_event_loop().create_future(),
        )
        self._inflight.setdefault(canonical_url, []).append(intent)
        return intent

    def first_intent(self, canonical_url: str) -> AcquisitionIntent | None:
        group = self._inflight.get(canonical_url)
        return group[0] if group else None

    def waiters(self, canonical_url: str) -> list[AcquisitionIntent]:
        return list(self._inflight.get(canonical_url, []))

    def complete(self, canonical_url: str, observation_id: str) -> list[AcquisitionIntent]:
        """Resolve all waiters with the observation; return them for fan-out."""
        self._completed[canonical_url] = observation_id
        group = self._inflight.pop(canonical_url, [])
        for intent in group:
            if intent.callback and not intent.callback.done():
                intent.callback.set_result(observation_id)
        return group

    def is_inflight(self, canonical_url: str) -> bool:
        return canonical_url in self._inflight

    def already_completed(self, canonical_url: str) -> str | None:
        return self._completed.get(canonical_url)