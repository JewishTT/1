"""Normalization stage (T081, NFR-108).

Mentions carry raw values that differ by surface form. Canonicalization compares
values case-insensitively, resolves IDN/punycode hostnames, strips trailing
slashes from URLs, normalizes IPv4/mac/hashes to lowercase, and folds Windows
drive-letter casing. Deduplication uses the canonical key; original values are
preserved as aliases so the fingerprint can be traced back.
"""

from __future__ import annotations

import ipaddress
import unicodedata
import urllib.parse
from dataclasses import dataclass, field


@dataclass
class CanonicalMention:
    kind: str
    canonical: str
    alias: str | None = None
    attrs: dict[str, str] = field(default_factory=dict)


def _norm_host(host: str) -> str:
    try:
        return host.encode("idna").decode("ascii").lower()
    except Exception:  # noqa: BLE001 - invalid IDNA host degrades to lowercase form
        return host.lower().rstrip(".")


def normalize_url(raw: str) -> str:
    parsed = urllib.parse.urlsplit(raw)
    scheme = (parsed.scheme or "http").lower()
    host = _norm_host(parsed.netloc.split("@")[-1].split(":")[0])
    port = ""
    netloc = parsed.netloc
    if ":" in netloc.split("@")[-1] and not host.endswith("]") and parsed.port:
        port = f":{parsed.port}"
    path = parsed.path or "/"
    while path.endswith("/") and path != "/":
        path = path[:-1]
    query = f"?{parsed.query}" if parsed.query else ""
    fragment = f"#{parsed.fragment}" if parsed.fragment else ""
    return f"{scheme}://{host}{port}{path}{query}{fragment}"


class Normalizer:
    """Value normalizer per mention kind (T081)."""

    def keyword(self, value: str) -> str:
        return unicodedata.normalize("NFKC", value).strip().lower()

    def normalize(self, mention) -> CanonicalMention:
        kind = mention.kind
        raw = str(mention.value)
        canonical = raw
        if kind in {"email", "domain"}:
            canonical = _norm_host(raw.lstrip("@")) if kind == "domain" else raw.lower()
        elif kind in {"url"}:
            canonical = normalize_url(raw)
        elif kind in {"ipv4", "ipv6", "mac"}:
            try:
                canonical = str(ipaddress.ip_address(raw))
            except Exception:  # noqa: BLE001 - non-IP still normalized to lowercase
                canonical = raw.lower()
        elif kind in {"md5", "sha256", "sha1", "strong_token", "crypto_address"}:
            canonical = raw.lower()
        elif kind in {"hostname"}:
            canonical = _norm_host(raw)
        elif kind in {"windows_file"}:
            canonical = raw.replace("\\", "/").lower()
        elif kind in {"gateway_ip"}:
            canonical = raw
        else:
            canonical = self.keyword(raw)
        return CanonicalMention(kind=kind, canonical=canonical, alias=raw if raw != canonical else None)