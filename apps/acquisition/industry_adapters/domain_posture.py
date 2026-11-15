"""Authorized-domain TLS posture probe inspired by safe BigBrother capabilities.

This is a single SNI-aware TLS handshake to port 443 for a hostname explicitly
listed in an unexpired authorization record. It does not scan ports, follow
redirects, or use certificate SANs to expand target scope.
"""
from __future__ import annotations

import hashlib
import socket
import ssl
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Callable

from .theharvester import AuthorizationScope


@dataclass(frozen=True)
class TlsPosture:
    hostname: str
    observed_at: str
    tls_version: str
    cipher: str | None
    issuer: dict[str, str]
    subject: dict[str, str]
    not_before: str | None
    not_after: str | None
    expired: bool | None
    certificate_sha256: str
    in_scope_sans: tuple[str, ...]


def _name_pairs(value: Any) -> dict[str, str]:
    output: dict[str, str] = {}
    for group in value or ():
        for pair in group:
            if isinstance(pair, tuple) and len(pair) == 2:
                output[str(pair[0])] = str(pair[1])
    return output


def probe_authorized_tls(
    hostname: str,
    scope: AuthorizationScope,
    *,
    timeout_seconds: float = 4.0,
    socket_factory: Callable[..., Any] = socket.create_connection,
    context_factory: Callable[[], Any] = ssl.create_default_context,
) -> TlsPosture:
    target = scope.assert_tls_probe(hostname)
    if not 0 < timeout_seconds <= 5:
        raise ValueError("TLS timeout must be in (0, 5]")
    context = context_factory()
    with socket_factory((target, 443), timeout=timeout_seconds) as raw_socket:
        with context.wrap_socket(raw_socket, server_hostname=target) as tls_socket:
            cert = tls_socket.getpeercert()
            der = tls_socket.getpeercert(binary_form=True)
            if not der:
                raise RuntimeError("peer did not present a certificate")
            sans = []
            for kind, value in cert.get("subjectAltName", ()):
                if kind != "DNS":
                    continue
                candidate = str(value).lower().rstrip(".")
                if scope.contains_domain(candidate):
                    sans.append(candidate)
            not_after = cert.get("notAfter")
            expired = None
            if not_after:
                try:
                    expiry = ssl.cert_time_to_seconds(str(not_after))
                    expired = expiry < datetime.now(UTC).timestamp()
                except (ValueError, TypeError):
                    expired = None
            cipher_info = tls_socket.cipher()
            return TlsPosture(
                hostname=target,
                observed_at=datetime.now(UTC).isoformat(),
                tls_version=str(tls_socket.version() or "unknown"),
                cipher=str(cipher_info[0]) if cipher_info else None,
                issuer=_name_pairs(cert.get("issuer")),
                subject=_name_pairs(cert.get("subject")),
                not_before=str(cert.get("notBefore")) if cert.get("notBefore") else None,
                not_after=str(not_after) if not_after else None,
                expired=expired,
                certificate_sha256=hashlib.sha256(der).hexdigest(),
                in_scope_sans=tuple(sorted(set(sans))),
            )
