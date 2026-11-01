"""Security-first HTTP fetch boundary (Principle VII, FR-100, Feature 024 T023).

The policy layer resolves and validates every DNS answer. This module carries that
validated address all the way to the TCP connect call: HTTPCore connects to the IP
literal while retaining the original URL hostname for the HTTP Host header, TLS SNI
and certificate verification. The client never performs a second DNS lookup.

Redirects are handled here, not by the HTTP client. Every hop is independently
resolved, checked and connected to its validated address. Bodies are bounded while
streaming, and each hop has an explicit timeout. No environment proxy is consulted.

The network backend is intentionally single-host/single-address and rejects any
unexpected host requested by the HTTP stack. It cannot be repurposed to reach an
unvalidated proxy or redirect destination.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import urljoin, urlsplit

import httpcore

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
    """The response exceeded ResourceLimits.max_response_bytes mid-stream."""


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


@dataclass(frozen=True)
class _PinnedResponse:
    status_code: int
    headers: dict[str, str]
    body: bytes

    async def aiter_bytes(self):
        if self.body:
            yield self.body

    async def aclose(self) -> None:
        return None


def _normalise_host(host: str) -> str:
    token = str(host or "").strip().rstrip(".")
    try:
        return ipaddress.ip_address(token).compressed.lower()
    except ValueError:
        try:
            return token.encode("idna").decode("ascii").lower()
        except UnicodeError as exc:
            raise SecurityBlocked("invalid DNS hostname at the connect boundary") from exc


class PinnedNetworkBackend(httpcore.AsyncNetworkBackend):
    """Map exactly one already-validated origin hostname to its checked IP.

    HTTPCore still sees the original URL hostname, so it uses that name for Host and
    TLS SNI/certificate checks. Only the TCP destination is rewritten. A different
    hostname or Unix socket request is rejected instead of falling back to DNS.
    """

    def __init__(
        self,
        *,
        hostname: str,
        pinned_ip: str,
        delegate: httpcore.AsyncNetworkBackend | None = None,
    ) -> None:
        self.hostname = _normalise_host(hostname)
        self.pinned_ip = str(ipaddress.ip_address(pinned_ip))
        self._delegate = delegate or httpcore.AnyIOBackend()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Any = None,
    ) -> httpcore.AsyncNetworkStream:
        if _normalise_host(host) != self.hostname:
            raise SecurityBlocked("HTTP stack requested a host outside the validated origin")
        return await self._delegate.connect_tcp(
            self.pinned_ip,
            port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: Any = None,
    ) -> httpcore.AsyncNetworkStream:
        raise SecurityBlocked("Unix-domain socket access is not available to public fetches")

    async def sleep(self, seconds: float) -> None:
        await self._delegate.sleep(seconds)


class PinnedHttpcoreTransport:
    """Direct HTTP/1.1 transport whose TCP connection uses the validated IP literal."""

    def __init__(
        self,
        *,
        limits: ResourceLimits,
        backend_factory: Callable[[str, str], httpcore.AsyncNetworkBackend] | None = None,
    ) -> None:
        self._limits = limits
        self._backend_factory = backend_factory or (
            lambda hostname, pinned_ip: PinnedNetworkBackend(
                hostname=hostname,
                pinned_ip=pinned_ip,
            )
        )

    async def request_pinned(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        pinned_ip: str,
        timeout: float,
    ) -> _PinnedResponse:
        parsed = urlsplit(url)
        hostname = parsed.hostname
        if not hostname:
            raise SecurityBlocked("missing host at pinned transport boundary")
        expected_ip = str(ipaddress.ip_address(pinned_ip))
        backend = self._backend_factory(hostname, expected_ip)
        timeout_value = max(0.1, float(timeout))
        extensions = {
            "timeout": {
                "connect": timeout_value,
                "read": timeout_value,
                "write": timeout_value,
                "pool": timeout_value,
            }
        }

        chunks: list[bytes] = []
        total = 0
        async with httpcore.AsyncConnectionPool(
            network_backend=backend,
            max_connections=1,
            max_keepalive_connections=0,
            keepalive_expiry=0,
            retries=0,
            http1=True,
            http2=False,
        ) as pool:
            async with pool.stream(
                method,
                url,
                headers=headers,
                extensions=extensions,
            ) as response:
                response_headers = {
                    key.decode("latin-1").lower(): value.decode("latin-1")
                    for key, value in response.headers
                }
                declared = response_headers.get("content-length", "")
                if declared.isdigit() and int(declared) > self._limits.max_response_bytes:
                    raise ResponseTooLarge(
                        f"response exceeded {self._limits.max_response_bytes}B"
                    )
                async for chunk in response.aiter_stream():
                    total += len(chunk)
                    if total > self._limits.max_response_bytes:
                        raise ResponseTooLarge(
                            f"response exceeded {self._limits.max_response_bytes}B"
                        )
                    chunks.append(chunk)
                status = int(response.status)

        return _PinnedResponse(
            status_code=status,
            headers=response_headers,
            body=b"".join(chunks),
        )

    async def aclose(self) -> None:
        # A fresh, bounded pool is opened and closed for each validated hop.
        return None


class Transport(Protocol):
    """A transport must consume the validated IP; unpinned clients are not accepted."""

    async def request_pinned(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        pinned_ip: str,
        timeout: float,
    ) -> _PinnedResponse: ...

    async def aclose(self) -> None: ...


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

    The validated DNS address is passed to a transport that uses it for the TCP
    connect. If an injected transport cannot accept a pinned IP, it does not satisfy
    this protocol and the request is refused.
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
        self._max_redirects = int(max_redirects)
        self._user_agent = user_agent
        self._resolver = resolver or default_resolver
        self._rebinding = rebinding or DnsRebindingGuard()
        self._transport: Transport = transport or PinnedHttpcoreTransport(limits=self._limits)

    @property
    def rebinding_guard(self) -> DnsRebindingGuard:
        return self._rebinding

    async def aclose(self) -> None:
        await self._transport.aclose()

    async def _validate_hop(
        self, url: str, *, trusted_private_hosts: frozenset[str] = frozenset()
    ) -> str:
        """Resolve and validate one hop, returning the checked address.

        Private destinations are never accepted by a broad CIDR exception. A source
        may opt one exact internal DNS name in (e.g. the deployment's own SearXNG
        service); only RFC1918/ULA addresses for that name are accepted, and every
        redirect hop must independently match the same exact allow-list.
        """
        host, port, scheme = _split_host_port(url)
        candidates = await self._resolver(host, port)
        if not candidates:
            raise SecurityBlocked(f"dns: no address for {host!r}")

        last_blocked: SecurityBlocked | None = None
        for ip in candidates:
            try:
                self._rebinding.check(host, ip)
                if _normalise_host(host) in trusted_private_hosts:
                    if scheme not in self._egress.schemes or port not in self._egress.ports:
                        raise SecurityBlocked(f"scheme/port not allowed for trusted service {host!r}")
                    address = ipaddress.ip_address(ip)
                    if (
                        not address.is_private
                        or address.is_loopback
                        or address.is_link_local
                        or address.is_reserved
                        or address.is_multicast
                        or address.is_unspecified
                        or address in ipaddress.ip_network("100.64.0.0/10")
                    ):
                        raise SecurityBlocked(
                            f"trusted service {host!r} resolved outside private service ranges"
                        )
                else:
                    ssrf_guard(url, ip, port=port, egress=self._egress)
            except (SecurityBlocked, ValueError) as blocked:
                last_blocked = blocked if isinstance(blocked, SecurityBlocked) else SecurityBlocked("invalid DNS address")
                continue
            self._rebinding.pin(host, ip)
            return str(ipaddress.ip_address(ip))
        raise last_blocked or SecurityBlocked(f"no permitted address for {host!r}")

    async def _read_capped(self, response: _PinnedResponse) -> bytes:
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

    async def fetch(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        method: str = "GET",
        trusted_private_hosts: tuple[str, ...] | frozenset[str] = (),
    ) -> FetchResult:
        """Fetch url, following at most max_redirects policy-checked hops."""
        current = url
        current_method = str(method or "GET").upper()
        if current_method not in {"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"}:
            raise SecurityBlocked(f"HTTP method {current_method!r} is not supported")
        private_hosts = frozenset(
            _normalise_host(host) for host in trusted_private_hosts if str(host).strip()
        )
        chain: list[str] = []
        base_scheme = urlsplit(url).scheme.lower()

        for hop in range(self._max_redirects + 1):
            pinned = await self._validate_hop(current, trusted_private_hosts=private_hosts)
            request_headers = {"User-Agent": self._user_agent}
            request_headers.update(headers or {})
            response = await self._transport.request_pinned(
                current_method,
                current,
                headers=request_headers,
                pinned_ip=pinned,
                timeout=self._limits.max_timeout_ms / 1000.0,
            )
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
                if urlsplit(nxt).scheme.lower() == "http" and base_scheme == "https":
                    raise RedirectBlocked(f"scheme downgrade https->http at {current}")
                chain.append(current)
                if status == 303 or (status in {301, 302} and current_method not in {"GET", "HEAD"}):
                    current_method = "GET"
                current = nxt
                continue

            body = await self._read_capped(response)
            return FetchResult(
                url=current,
                status=status,
                body=body,
                headers=dict(response.headers),
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
    "PinnedNetworkBackend",
    "PinnedHttpcoreTransport",
    "RedirectBlocked",
    "Resolver",
    "ResponseTooLarge",
    "SecureFetcher",
    "SecurityBlocked",
    "Transport",
    "default_resolver",
]
