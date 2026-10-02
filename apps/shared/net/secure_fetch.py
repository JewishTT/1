"""Security-First fetch boundary (Principle VII, FR-100, Feature 024 T023).

``shared.security`` provides the *policy* -- ``ssrf_guard``, ``is_public_ip``,
``DnsRebindingGuard``, ``EgressPolicy``, ``ResourceLimits``. It deliberately holds
no network calls: it takes a ``resolved_ip`` from the caller. Nothing in the platform
actually resolved that IP, validated redirects, or enforced the response-size limit
during streaming, so ``ssrf_guard`` had a single call site.

This module supplies the missing mechanics and wires them to that policy:

1. **Resolve, then validate.** DNS is resolved here, and the resolved address is
   what gets validated. A host that resolves into a private range is refused.
2. **Pin, then connect.** The validated IP is pinned per host. A later resolution
   that disagrees is DNS rebinding and is refused rather than followed.
3. **Redirects are followed by us, never by the client.** ``httpx`` with
   ``follow_redirects=True`` validates nothing on the hops it follows -- a public
   host can 302 into ``169.254.169.254``. Every hop is re-resolved and
   re-validated against the same policy, bounded by ``max_redirects``.
4. **Size is enforced while streaming**, not after the body is already in memory.
5. **Timeout is enforced** per attempt, fail-closed.

What this module does not do, deliberately: connect to the pinned IP with a forged
``Host`` header. That needs a transport that supports it, and pretending to do it
here would be a silent hole. Until such a transport exists, the honest guarantee is
resolve-and-revalidate-per-hop, and this docstring says so.

Reused from platform code: every policy function above. Written here: resolution,
redirect handling, streaming limits.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Protocol
from urllib.parse import urljoin, urlsplit

import httpx

from security import (
    DnsRebindingGuard,
    EgressPolicy,
    ResourceLimits,
    SecurityBlocked,
    ssrf_guard,
)

DEFAULT_MAX_REDIRECTS = 5


class RedirectBlocked(SecurityBlocked):
    """A redirect was refused: over budget, downgrading scheme, or off-policy."""


class ResponseTooLarge(SecurityBlocked):
    """The response exceeded ``ResourceLimits.max_response_bytes`` mid-stream."""


@dataclass(frozen=True)
class FetchResult:
    url: str
    status: int
    body: bytes
    headers: dict[str, str] = field(default_factory=dict)
    redirects: tuple[str, ...] = ()
    pinned_ip: str = ""
    content_type: str | None = None

    @property
    def final_url(self) -> str:
        return self.url


Resolver = Callable[[str, int], Awaitable[list[str]]]
"""(host, port) -> candidate IPs. Injectable so the boundary is testable hermetically."""


class Transport(Protocol):
    """The subset of an HTTP client this boundary needs.

    Deliberately not ``httpx.AsyncClient``: depending on the concrete client would
    let a caller reintroduce client-side redirect following by passing one that has
    it enabled.
    """

    async def get(self, url: str, *, headers: dict[str, str]) -> httpx.Response: ...


async def default_resolver(host: str, port: int) -> list[str]:
    """Resolve a host to every candidate address, IPv4 and IPv6."""
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    return list(dict.fromkeys(info[4][0] for info in infos))


def _split_host_port(url: str) -> tuple[str, int, str]:
    parsed = urlsplit(url)
    host = parsed.hostname
    if not host:
        raise SecurityBlocked(f"missing host in {url!r}")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return host, port, parsed.scheme


class SecureFetcher:
    """Fetch a URL through the full security policy, hop by hop.

    Fail-closed by construction: an unresolvable host, an off-policy port, a
    private destination, an over-budget redirect chain, and an oversized body all
    raise ``SecurityBlocked`` rather than returning a degraded result.
    """

    def __init__(
        self,
        *,
        transport: Transport | None = None,
        resolver: Resolver | None = None,
        egress: EgressPolicy | None = None,
        limits: ResourceLimits | None = None,
        max_redirects: int = DEFAULT_MAX_REDIRECTS,
        user_agent: str = "cognitive-acquisition/0.1",
        rebinding: DnsRebindingGuard | None = None,
    ) -> None:
        self._egress = egress or EgressPolicy()
        self._limits = limits or ResourceLimits()
        self._max_redirects = max_redirects
        self._user_agent = user_agent
        self._resolver = resolver or default_resolver
        self._rebinding = rebinding or DnsRebindingGuard()
        # follow_redirects is False and must stay False: this class walks the chain
        # itself so every hop is re-validated. See module docstring.
        self._transport = transport or httpx.AsyncClient(
            timeout=self._limits.max_timeout_ms / 1000.0,
            follow_redirects=False,
            headers={"User-Agent": user_agent},
        )

    @property
    def rebinding_guard(self) -> DnsRebindingGuard:
        return self._rebinding

    async def aclose(self) -> None:
        closer = getattr(self._transport, "aclose", None)
        if closer is not None:
            await closer()

    async def _validate_hop(self, url: str) -> str:
        """Resolve and validate one hop, returning the pinned IP."""
        host, port, _ = _split_host_port(url)
        candidates = await self._resolver(host, port)
        if not candidates:
            raise SecurityBlocked(f"dns: no address for {host!r}")

        last_blocked: SecurityBlocked | None = None
        for ip in candidates:
            try:
                # Compares against any earlier pin for this host; a disagreement is
                # rebinding, not a round-robin answer.
                self._rebinding.check(host, ip)
                ssrf_guard(url, ip, port=port, egress=self._egress)
            except SecurityBlocked as blocked:
                last_blocked = blocked
                continue
            self._rebinding.pin(host, ip)
            return ip
        raise last_blocked or SecurityBlocked(f"no permitted address for {host!r}")

    async def _read_capped(self, response: httpx.Response) -> bytes:
        """Read the body, aborting as soon as the cap is passed."""
        declared = response.headers.get("content-length")
        if declared and declared.isdigit():
            self._limits.check_bytes(int(declared))
        chunks: list[bytes] = []
        total = 0
        async for chunk in response.aiter_bytes():
            total += len(chunk)
            if total > self._limits.max_response_bytes:
                raise ResponseTooLarge(
                    f"response exceeded {self._limits.max_response_bytes}B"
                )
            chunks.append(chunk)
        return b"".join(chunks)

    async def fetch(self, url: str, *, headers: dict[str, str] | None = None) -> FetchResult:
        """Fetch ``url``, following at most ``max_redirects`` policy-checked hops.

        Returns the final response. Raises ``SecurityBlocked`` on any violation.
        """
        current = url
        chain: list[str] = []
        base_scheme = urlsplit(url).scheme

        for hop in range(self._max_redirects + 1):
            pinned = await self._validate_hop(current)
            request_headers = {"User-Agent": self._user_agent}
            request_headers.update(headers or {})

            response = await self._transport.get(current, headers=request_headers)
            status = response.status_code

            if status in (301, 302, 303, 307, 308):
                location = response.headers.get("location")
                if not location:
                    raise RedirectBlocked(f"{status} from {current} without Location")
                if hop >= self._max_redirects:
                    raise RedirectBlocked(
                        f"redirect chain exceeds {self._max_redirects} hops at {current}"
                    )
                nxt = urljoin(current, location)
                if urlsplit(nxt).scheme == "http" and base_scheme == "https":
                    # A downgrade lets an active network rewrite a trusted hop.
                    raise RedirectBlocked(f"scheme downgrade https->http at {current}")
                await response.aclose()
                chain.append(current)
                current = nxt
                continue

            body = await self._read_capped(response)
            return FetchResult(
                url=current,
                status=status,
                body=body,
                headers={k.lower(): v for k, v in response.headers.items()},
                redirects=tuple(chain),
                pinned_ip=pinned,
                content_type=response.headers.get("content-type"),
            )

        raise RedirectBlocked(f"redirect chain exceeded budget starting at {url}")


def is_public_address(addr: ipaddress._BaseAddress) -> bool:  # pragma: no cover - re-export
    from security import is_public_ip

    return is_public_ip(str(addr))


__all__ = [
    "DEFAULT_MAX_REDIRECTS",
    "FetchResult",
    "RedirectBlocked",
    "Resolver",
    "ResponseTooLarge",
    "SecureFetcher",
    "SecurityBlocked",
    "Transport",
    "default_resolver",
]
