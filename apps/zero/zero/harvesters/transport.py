"""Injectable transport for harvesters (spec/010, hermetic-by-default).

Harvest modules must never reach the network by themselves: they take a
``Transport`` whose default is ``OfflineTransport`` (deterministic, no sockets).
Tests inject a ``FakeTransport``; live deployments inject an egress-controlled
implementation (proxy pool / pacing, per spec §0.11 OPSEC note).
"""

from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Callable, Protocol
from urllib.parse import urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

from net.secure_fetch import SecureFetcher
from security import DnsRebindingGuard, EgressPolicy, ResourceLimits, SecurityBlocked


class Transport(Protocol):
    """Minimal fetch/existence probe a harvester module may use."""

    def fetch(self, url: str, timeout: float = 5.0) -> str:
        """Return the response body as text (never raises)."""
        ...

    def exists(self, url: str, timeout: float = 5.0) -> bool:
        """Whether the URL is reachable / the resource exists (never raises)."""
        ...


@dataclass(frozen=True)
class PublicFetchCapture:
    """Raw successful response, retained until canonical persistence."""

    url: str
    status: int
    body: bytes
    content_type: str
    fetched_at: datetime
    pinned_ip: str
    redirects: tuple[str, ...] = ()
    parent_observation_id: str = ""
    discovery_source_id: str = ""
    action_ref: str = ""


SecureFetcherFactory = Callable[..., SecureFetcher]


class SecurePublicTransport:
    """Explicit case-scoped HTTPS transport for public documents only.

    It rejects private/local destinations via SecureFetcher, pins DNS answers,
    refuses redirects, applies a response/time ceiling, honors robots.txt and
    paces requests per host. Successful raw bytes are exposed through captures.
    """

    def __init__(
        self,
        *,
        user_agent: str = "COGNITIVE-PublicResearch/1.0",
        max_response_bytes: int = 2_000_000,
        minimum_host_interval_s: float = 1.0,
        max_requests: int = 64,
        max_concurrency: int = 4,
        fetcher_factory: SecureFetcherFactory | None = None,
    ) -> None:
        if max_response_bytes < 1024:
            raise ValueError("max_response_bytes must be at least 1024")
        if minimum_host_interval_s < 0:
            raise ValueError("minimum_host_interval_s cannot be negative")
        if not 1 <= int(max_requests) <= 512:
            raise ValueError("max_requests must be between 1 and 512")
        if not 1 <= int(max_concurrency) <= 16:
            raise ValueError("max_concurrency must be between 1 and 16")
        self.max_requests = int(max_requests)
        self.max_concurrency = int(max_concurrency)
        self.user_agent = user_agent
        self.max_response_bytes = int(max_response_bytes)
        self.minimum_host_interval_s = float(minimum_host_interval_s)
        self._fetcher_factory = fetcher_factory or SecureFetcher
        self._rebinding = DnsRebindingGuard()
        self._lock = threading.RLock()
        self._last_host_request: dict[str, float] = {}
        self._body_cache: dict[str, str] = {}
        self._captures: list[PublicFetchCapture] = []
        self._failures: list[dict[str, str]] = []
        self._source_metadata: dict[str, dict[str, str]] = {}
        self._network_requests_used = 0
        self._request_slots = threading.BoundedSemaphore(self.max_concurrency)
        self._pending_fetches: dict[str, threading.Event] = {}
        self._exists_cache: dict[str, bool] = {}

    @property
    def captures(self) -> tuple[PublicFetchCapture, ...]:
        with self._lock:
            return tuple(self._captures)

    @property
    def failures(self) -> tuple[dict[str, str], ...]:
        with self._lock:
            return tuple(dict(item) for item in self._failures)

    @property
    def requests_used(self) -> int:
        """Physical HTTP requests used, including robots.txt checks."""
        with self._lock:
            return self._network_requests_used

    def _reserve_request(self, url: str) -> None:
        with self._lock:
            if self._network_requests_used >= self.max_requests:
                raise SecurityBlocked(f"public fetch request budget exhausted ({self.max_requests})")
            self._network_requests_used += 1

    @staticmethod
    def _canonical_public_url(url: str) -> tuple[str, str]:
        parsed = urlsplit(str(url or "").strip())
        if parsed.scheme.lower() != "https":
            raise SecurityBlocked("public document fetch requires HTTPS")
        if not parsed.hostname or parsed.username or parsed.password:
            raise SecurityBlocked("public document URL has an invalid authority")
        if parsed.port not in (None, 443):
            raise SecurityBlocked("public document fetch permits HTTPS port 443 only")
        host = parsed.hostname.encode("idna").decode("ascii").lower()
        if not host or host.endswith(".local") or host == "localhost":
            raise SecurityBlocked("local hostnames are not public web sources")
        return urlunsplit(("https", host, parsed.path or "/", parsed.query, "")), host

    def set_source_metadata(
        self,
        url: str,
        *,
        parent_observation_id: str,
        discovery_source_id: str,
        action_ref: str,
    ) -> None:
        canonical, _host = self._canonical_public_url(url)
        with self._lock:
            self._source_metadata[canonical] = {
                "parent_observation_id": str(parent_observation_id),
                "discovery_source_id": str(discovery_source_id),
                "action_ref": str(action_ref),
            }

    def _pace(self, host: str) -> None:
        with self._lock:
            now = time.monotonic()
            previous = self._last_host_request.get(host)
            delay = 0.0 if previous is None else max(
                0.0, self.minimum_host_interval_s - (now - previous)
            )
            self._last_host_request[host] = now + delay
        if delay:
            time.sleep(delay)

    def _record_failure(self, url: str, code: str, detail: str) -> None:
        with self._lock:
            self._failures.append({
                "url": url[:2048],
                "code": code[:120],
                "detail": detail[:1000],
            })

    async def _fetch_async(
        self, url: str, timeout: float, *, method: str = "GET"
    ) -> PublicFetchCapture:
        canonical, host = self._canonical_public_url(url)
        limits = ResourceLimits(
            max_timeout_ms=max(1000, min(int(float(timeout) * 1000), 15000)),
            max_response_bytes=self.max_response_bytes,
        )
        egress = EgressPolicy(schemes=frozenset({"https"}), ports=frozenset({443}))
        fetcher = self._fetcher_factory(
            egress=egress,
            limits=limits,
            max_redirects=0,
            user_agent=self.user_agent,
            rebinding=self._rebinding,
        )
        try:
            robots_url = f"https://{host}/robots.txt"
            self._reserve_request(robots_url)
            robots = await fetcher.fetch(robots_url, headers={"Accept": "text/plain"})
            if robots.status in (404, 410):
                permitted = True
            elif robots.status == 200:
                parser = RobotFileParser()
                parser.set_url(robots_url)
                parser.parse(robots.body.decode("utf-8", errors="replace").splitlines())
                permitted = parser.can_fetch(self.user_agent, canonical)
            else:
                permitted = False
            if not permitted:
                raise SecurityBlocked("robots policy does not permit this fetch")
            self._pace(host)
            self._reserve_request(canonical)
            request_headers = {"Accept": "text/html,application/xhtml+xml,text/plain;q=0.8"}
            if method == "GET":
                response = await fetcher.fetch(canonical, headers=request_headers)
            else:
                response = await fetcher.fetch(
                    canonical,
                    method=method,
                    headers=request_headers,
                )
            if response.status < 200 or response.status >= 300:
                raise SecurityBlocked(f"origin returned HTTP {response.status}")
            with self._lock:
                metadata = dict(self._source_metadata.get(canonical, {}))
            return PublicFetchCapture(
                url=response.url,
                status=response.status,
                body=response.body,
                content_type=str(response.content_type or "application/octet-stream").split(";", 1)[0].strip().lower(),
                fetched_at=datetime.now(UTC),
                pinned_ip=response.pinned_ip,
                redirects=response.redirects,
                parent_observation_id=metadata.get("parent_observation_id", ""),
                discovery_source_id=metadata.get("discovery_source_id", ""),
                action_ref=metadata.get("action_ref", ""),
            )
        finally:
            await fetcher.aclose()

    def fetch(self, url: str, timeout: float = 8.0) -> str:
        try:
            canonical, _host = self._canonical_public_url(url)
            with self._lock:
                cached = self._body_cache.get(canonical)
                if cached is not None:
                    return cached
                pending = self._pending_fetches.get(canonical)
                leader = pending is None
                if leader:
                    pending = threading.Event()
                    self._pending_fetches[canonical] = pending
            if not leader:
                if not pending.wait(timeout=max(1.0, float(timeout) + 2.0)):
                    raise SecurityBlocked("coalesced fetch wait exceeded timeout")
                with self._lock:
                    return self._body_cache.get(canonical, "")
            if not self._request_slots.acquire(blocking=False):
                raise SecurityBlocked("public fetch concurrency budget exhausted")
            try:
                capture = asyncio.run(self._fetch_async(canonical, timeout, method="GET"))
                text_body = capture.body.decode("utf-8", errors="replace")
                with self._lock:
                    self._captures.append(capture)
                    self._body_cache[canonical] = text_body
                return text_body
            finally:
                self._request_slots.release()
        except Exception as exc:  # noqa: BLE001 - refusals are explicit ledger entries
            self._record_failure(str(url), type(exc).__name__, str(exc))
            return ""
        finally:
            # Only the leader owns the pending slot. A waiter must not wake another
            # waiter before the leader has stored the response in the shared cache.
            if locals().get("leader", False):
                with self._lock:
                    event = self._pending_fetches.pop(canonical, None)
                    if event is not None:
                        event.set()

    def exists(self, url: str, timeout: float = 5.0) -> bool:
        try:
            canonical, _host = self._canonical_public_url(url)
            with self._lock:
                if canonical in self._exists_cache:
                    return self._exists_cache[canonical]
            if not self._request_slots.acquire(blocking=False):
                raise SecurityBlocked("public fetch concurrency budget exhausted")
            try:
                result = asyncio.run(self._fetch_async(canonical, timeout, method="HEAD"))
                found = 200 <= result.status < 400
                with self._lock:
                    self._exists_cache[canonical] = found
                return found
            finally:
                self._request_slots.release()
        except Exception as exc:  # noqa: BLE001 - refusals are explicit ledger entries
            self._record_failure(str(url), type(exc).__name__, str(exc))
            return False


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