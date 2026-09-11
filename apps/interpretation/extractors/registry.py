"""Extractor registry (T033, FR-011).

Turn parser segments into typed entities: persons, orgs, indicators (IP/URL/hash/
email/domain/CVE), temporal expressions, geolocations. Each extractor returns
typed mentions; the registry fans a segment across all applicable extractors and
tags output with a stable source id.
"""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class Mention:
    kind: str
    value: str
    offset: int = 0
    confidence: float = 1.0
    attrs: dict[str, str] = field(default_factory=dict)


Extractor = Callable[[str], list[Mention]]


_PATTERNS: dict[str, re.Pattern[str]] = {
    "email": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "url": re.compile(r"https?://[^\s<>\"']+"),
    "ipv4": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    "domain": re.compile(r"\b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}\b"),
    "cve": re.compile(r"\bCVE-\d{4}-\d{4,7}\b", re.IGNORECASE),
    "sha256": re.compile(r"\b[a-f0-9]{64}\b", re.IGNORECASE),
    "md5": re.compile(r"\b[a-f0-9]{32}\b", re.IGNORECASE),
    "windows_file": re.compile(r"\b[A-Z]:\\[^\s\"'<>]+"),
    "gateway_ip": re.compile(r"\b(?:192\.168|10\.|172\.16\.|172\.31\.|169\.254\.)\d*\.\d*\d*\.\d*\.\d*\b"),
    "crypto_address": re.compile(
        r"\b(?:bc1[a-z0-9]{25,39}|1[a-zA-Z0-9]{25,34}|3[a-zA-Z0-9]{25,34})\b"
    ),
    "strong_token": re.compile(r"\b[A-Fa-f0-9]{40}\b"),
}


def _ipv4_valid(m: re.Match[str]) -> bool:
    try:
        ipaddress.ip_address(m.group(0))
        return True
    except ValueError:
        return False


class ExtractorRegistry:
    """Fan-out a segment to every registered extractor, dedup by kind+value.

    If an OntologyPack is bound, emits only mention types admissible by the
    pack (FR-012, kafSIEM pattern).
    """

    def __init__(self, ontology_pack=None) -> None:
        self._extractors: list[tuple[str, Extractor]] = []
        self._ontology = ontology_pack
        self.register_builtin()

    def register(self, name: str, extractor: Extractor) -> None:
        if name not in [n for n, _ in self._extractors]:
            self._extractors.append((name, extractor))

    def register_builtin(self) -> None:
        for kind, pat in _PATTERNS.items():
            def make(k: str, p: re.Pattern[str]) -> Extractor:
                def ex(text: str) -> list[Mention]:
                    out: list[Mention] = []
                    for m in p.finditer(text):
                        if k == "ipv4":
                            octets = m.group(0).split(".")
                            if not all(0 <= int(o) <= 255 for o in octets):
                                continue
                        out.append(Mention(kind=k, value=m.group(0), offset=m.start()))
                    return out
                return ex
            self.register(kind, make(kind, pat))

    def extract(self, text: str, source_id: str | None = None) -> list[Mention]:
        seen: set[tuple[str, str]] = set()
        out: list[Mention] = []
        for name, ex in self._extractors:
            for m in ex(text):
                if self._ontology is not None and not self._ontology.allows_type(m.kind):
                    continue  # FR-012: only types admissible by the ACTIVE pack
                key = (m.kind, m.value)
                if key in seen:
                    continue
                seen.add(key)
                m.attrs.setdefault("extractor", name)
                m.attrs.setdefault("source", source_id or "unknown")
                out.append(m)
        return out