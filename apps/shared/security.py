"""Security hardening policy (T072, FR-029 review pass).

Fail-closed controls reviewed against FR-029:

- SSRF / DNS-rebinding guard: resolve a host ONCE to an IP, require it to be a
  public address, and pin the connection to that IP (deny-by-default). Any
  resolution/parse anomaly blocks the fetch — matching the OWASP cheat sheet
  (re-resolve + compare) with a singleton-pinning hardening step.
- Egress allowlist policy: permitted schemes, ports, and optional CIDR allowlist.
- Resource limits: CPU/mem/timeout/size/archive-depth/file-count caps enforced
  at the point of task construction (fail closed, never silently truncated).

These are pure policy functions so workers (Rust), parsers, and the browser
fabric can each apply them via the same rules.
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass, field
from urllib.parse import unquote, urlsplit

# IPs that must never be fetched (metadata endpoints, loopback, private/ULA/LinkLocal).
_BLOCKED = (
    ipaddress.ip_network("0.0.0.0/32"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("100.64.0.0/10"),  # CGNAT (metadata/egress proxies)
    ipaddress.ip_network("169.254.0.0/16"),  # link-local
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),  # ULA
    ipaddress.ip_network("fe80::/10"),  # link-local v6
)
# RFC 1918 not the only private range: also document unique-local (fc00::/7) above.

_ALLOWED_SCHEMES = {"http", "https"}
_ALLOWED_PORTS = {80, 443, 8080, 8443}


class SecurityBlocked(Exception):
    """Raised when a fetch/task violates a fail-closed security policy."""


@dataclass
class EgressPolicy:
    schemes: set[str] = field(default_factory=lambda: set(_ALLOWED_SCHEMES))
    ports: set[int] = field(default_factory=lambda: set(_ALLOWED_PORTS))
    allow_cidrs: list[str] = field(default_factory=list)  # empty = any public egress

    def to_dict(self) -> dict:
        return {
            "schemes": sorted(self.schemes),
            "ports": sorted(self.ports),
            "allow_cidrs": self.allow_cidrs,
        }


def parse_host(host: str) -> tuple[str, str] | None:
    """Split host:port -> (host, port) honoring v6 brackets; None if malformed."""
    if host.startswith("["):
        # bracketed IPv6 literal [::1]:443
        m = re.match(r"^\[([0-9a-fA-F:.]+)\](?::(\d+))?$", host)
        if not m:
            return None
        return m.group(1), m.group(2) or "80"
    if ":" in host:
        h, _, port = host.rpartition(":")
        if not port.isdigit():
            return None
        return h, port
    return host, "80"


def is_public_ip(ip: str) -> bool:
    """True iff the resolved address is globally routable (deny-by-default)."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if (
        addr.is_loopback
        or addr.is_link_local
        or addr.is_private
        or addr.is_reserved
        or addr.is_multicast
    ):
        return False
    if addr.is_unspecified:
        return False
    for net in _BLOCKED:
        if addr in net:
            return False
    return True


def ssrf_guard(
    url: str, resolved_ip: str, port: int | None = None, egress: EgressPolicy | None = None
) -> None:
    """Validate a fetch URL against SSRF/DNS-rebinding + egress policy.

    `resolved_ip` must be the IP the DNS lookup returned (single-resolution
    pinning: fetch against THAT ip with Host header, defeating classic rebinding
    by re-resolving). Raises SecurityBlocked on any violation.
    """
    egress = egress or EgressPolicy()
    parsed = urlsplit(url)
    if parsed.scheme not in egress.schemes:
        raise SecurityBlocked(f"scheme {parsed.scheme!r} not allowed")
    if parsed.scheme in _ALLOWED_SCHEMES and not parsed.hostname:
        raise SecurityBlocked(f"missing host in {url!r}")
    host, port_str = parse_host(parsed.netloc.split("@")[-1])
    port = port or int(port_str)
    if port not in egress.ports:
        raise SecurityBlocked(f"port {port} not allowed")
    if egress.allow_cidrs and not any(
        ipaddress.ip_address(resolved_ip) in ipaddress.ip_network(c) for c in egress.allow_cidrs
    ):
        raise SecurityBlocked(f"ip {resolved_ip} not in egress allowlist")
    if not is_public_ip(resolved_ip):
        raise SecurityBlocked(f"non-public destination ip {resolved_ip}")


class DnsRebindingGuard:
    """Multi-resolution compare guard: a DNS rebinding attack is detected when
    a second resolution at fetch time disagrees with the validated first one."""

    def __init__(self) -> None:
        self._pinned: dict[str, str] = {}

    def pin(self, host: str, ip: str) -> None:
        self._pinned[host.lower()] = ip

    def check(self, host: str, live_ip: str) -> None:
        pinned = self._pinned.get(host.lower())
        if pinned is not None and pinned != live_ip:
            raise SecurityBlocked(f"dns rebinding: {host} resolved to {live_ip} after pin {pinned}")


@dataclass(frozen=True)
class ResourceLimits:
    """Fail-closed resource limits enforced at task construction (FR-029)."""

    max_response_bytes: int = 10 * 1024 * 1024
    max_timeout_ms: int = 30_000
    max_cpu_millis: int = 10_000
    max_mem_mb: int = 512
    max_archive_depth: int = 8
    max_file_count: int = 50_000
    max_filename_len: int = 255

    def check_bytes(self, size: int) -> None:
        if size > self.max_response_bytes:
            raise SecurityBlocked(f"response {size}B exceeds limit {self.max_response_bytes}B")

    def check_timeout(self, ms: int) -> None:
        if ms > self.max_timeout_ms:
            raise SecurityBlocked(f"timeout {ms}ms exceeds limit {self.max_timeout_ms}ms")

    def check_archive_depth(self, depth: int) -> None:
        if depth > self.max_archive_depth:
            raise SecurityBlocked(f"archive depth {depth} exceeds limit {self.max_archive_depth}")


def validate_seed_url(url: str, egress: EgressPolicy | None = None) -> str:
    """Admission-time seed check (no DNS): scheme, port, host parseability.

    The IP/SRRF half is enforced by the fetcher (worker DnsRebindingGuard /
    ssrf_guard) where resolution happens; this catches malformed/forbidden
    inputs fail-closed at the API edge. Returns the canonical url.
    """
    egress = egress or EgressPolicy()
    parsed = urlsplit(url)
    if parsed.scheme not in egress.schemes:
        raise SecurityBlocked(f"scheme {parsed.scheme!r} not allowed")
    if not parsed.hostname:
        raise SecurityBlocked(f"missing host in {url!r}")
    if parsed.port is not None and parsed.port not in egress.ports:
        raise SecurityBlocked(f"port {parsed.port} not allowed")
    return url


def sanitize_archive_path(entry: str, limits: ResourceLimits) -> str:
    """Reject traversal / over-long archive (zip/tar) entry names (zip-slip)."""
    if not entry or len(entry) > limits.max_filename_len:
        raise SecurityBlocked("archive entry name invalid")
    parts = [p for p in unquote(entry).replace("\\", "/").split("/") if p not in ("", ".")]
    if ".." in parts:
        raise SecurityBlocked(f"archive traversal: {entry!r}")
    return "/".join(parts)