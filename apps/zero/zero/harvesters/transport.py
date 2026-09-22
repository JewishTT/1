"""Injectable transport for harvesters (spec/010, hermetic-by-default).

Harvest modules must never reach the network by themselves: they take a
``Transport`` whose default is ``OfflineTransport`` (deterministic, no sockets).
Tests inject a ``FakeTransport``; live deployments inject an egress-controlled
implementation (proxy pool / pacing, per spec §0.11 OPSEC note).
"""

from __future__ import annotations

from typing import Protocol


class Transport(Protocol):
    """Minimal fetch/existence probe a harvester module may use."""

    def fetch(self, url: str, timeout: float = 5.0) -> str:
        """Return the response body as text (never raises)."""
        ...

    def exists(self, url: str, timeout: float = 5.0) -> bool:
        """Whether the URL is reachable / the resource exists (never raises)."""
        ...


class OfflineTransport:
    """Default deterministic transport: no network, no data.

    This is the fallback that keeps every harvester deterministic when the
    binary / network is not available (spec §0.5 "deterministic fallbacks").
    """

    def fetch(self, url: str, timeout: float = 5.0) -> str:
        return ""

    def exists(self, url: str, timeout: float = 5.0) -> bool:
        return False


class DictTransport:
    """Deterministic fake transport backed by an explicit URL→body map."""

    def __init__(
        self, bodies: dict[str, str] | None = None, existing: set[str] | None = None
    ) -> None:
        self._bodies = dict(bodies or {})
        self._existing = set(existing or set(self._bodies))

    def fetch(self, url: str, timeout: float = 5.0) -> str:
        return self._bodies.get(url, "")

    def exists(self, url: str, timeout: float = 5.0) -> bool:
        return url in self._existing