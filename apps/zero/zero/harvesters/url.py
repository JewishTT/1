"""URL harvesters (spec/010 §0.6): content scrape + embedded contacts.

``EmbeddedContactsHarvester`` fetches a page through the injected transport,
scans its textual content for emails/phones and its ``href`` attrs for outbound
domains (BeautifulSoup-style content extraction on stdlib ``html.parser``).
``SocialLinkHarvester`` recognises well-known social hosts and derives the
handles from their URLs. Both are strictly deterministic given the transport.
"""

from __future__ import annotations

import html.parser
import re
from urllib.parse import urlparse

from ..type_detector import InputType, SeedInput
from .contracts import HarvestResult, ObservationCandidate
from .registry import HarvestContext

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?[1-9][\d\s().-]{7,18})(?!\d)")

_SOCIAL_HOSTS: dict[str, str] = {
    "github.com": "github",
    "gitlab.com": "gitlab",
    "twitter.com": "twitter",
    "x.com": "twitter",
    "linkedin.com": "linkedin",
    "t.me": "telegram",
    "telegram.me": "telegram",
    "reddit.com": "reddit",
    "instagram.com": "instagram",
    "facebook.com": "facebook",
    "discord.gg": "discord",
    "medium.com": "medium",
    "youtube.com": "youtube",
}

_DOMAIN_OK = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z]{2,})+$")


def _match_social_host(host: str) -> str | None:
    for prefix, platform in _SOCIAL_HOSTS.items():
        if host == prefix or host.endswith("." + prefix):
            return platform
    return None


class _HTMLScanner(html.parser.HTMLParser):
    """Collects text nodes, hrefs and linked domain hosts in one pass."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.text_parts: list[str] = []
        self.hrefs: list[str] = []

    def handle_data(self, data: str) -> None:
        self.text_parts.append(data)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for key, value in attrs:
            if key == "href" and value:
                self.hrefs.append(value)


def _clean_href(href: str) -> str:
    return href if href.startswith(("http://", "https://")) else ""


def _host_domains(hrefs: list[str]) -> list[str]:
    domains: list[str] = []
    seen: set[str] = set()
    for href in hrefs:
        parsed = urlparse(_clean_href(href))
        host = (parsed.hostname or "").lower()
        if ":" in host:
            host = host.split(":")[0]
        if _DOMAIN_OK.match(host) and host not in seen:
            seen.add(host)
            domains.append(host)
    return domains


def _social_from_hrefs(hrefs: list[str], module: str, method: str) -> list[ObservationCandidate]:
    candidates: list[ObservationCandidate] = []
    for href in hrefs:
        parsed = urlparse(_clean_href(href))
        host = (parsed.hostname or "").lower()
        platform = _match_social_host(host)
        if platform is None:
            continue
        path = parsed.path.strip("/")
        if path.startswith("in/") and "/" in path:
            handle = path.split("/")[1]
        else:
            handle = path.split("/")[0] if path else ""
        if handle and re.match(r"^[a-zA-Z0-9_.-]{1,40}$", handle):
            candidates.append(
                ObservationCandidate(
                    value=f"https://{host}/{handle}",
                    kind="social_profile",
                    confidence=0.65,
                    source_module=module,
                    method=method,
                    raw_fields={"platform": platform, "handle": handle},
                    evidence="social URL embedded in page links",
                )
            )
    return candidates


class EmbeddedContactsHarvester:
    """Page content → embedded emails / phones / linked domains."""

    name = "embedded_contacts"
    required_types = frozenset({InputType.URL})
    method = "embedded-contacts extractor (BeautifulSoup-style, stdlib html.parser)"
    license = "MIT"
    attribution = "donors/BeautifulSoup pattern (vendored method only)"

    def run(self, seed: SeedInput, ctx: HarvestContext) -> HarvestResult:
        body = ctx.transport.fetch(seed.raw_value, timeout=8.0)
        if not body:
            return HarvestResult(
                module=self.name,
                notes=("page fetch returned empty (offline transport)",),
            )
        scanner = _HTMLScanner()
        try:
            scanner.feed(body)
        except html.parser.HTMLParseError:  # pragma: no cover - stdlib edge
            return HarvestResult(module=self.name, notes=("unparsable html",))
        text = " ".join(scanner.text_parts)

        candidates: list[ObservationCandidate] = []
        seen_emails: set[str] = set()
        for raw in _EMAIL_RE.findall(text):
            email = raw.lower()
            if email in seen_emails:
                continue
            seen_emails.add(email)
            candidates.append(
                ObservationCandidate(
                    value=email,
                    kind="email",
                    confidence=0.8,
                    source_module=self.name,
                    method=self.method,
                    raw_fields={"seed_url": seed.raw_value},
                    evidence="email embedded in page text",
                )
            )
        seen_phones: set[str] = set()
        for raw in _PHONE_RE.findall(text):
            digits = "".join(ch for ch in raw if ch.isdigit())
            if len(digits) < 9 or digits in seen_phones:
                continue
            seen_phones.add(digits)
            candidates.append(
                ObservationCandidate(
                    value=digits,
                    kind="phone",
                    confidence=0.7,
                    source_module=self.name,
                    method=self.method,
                    raw_fields={"seed_url": seed.raw_value, "raw_text": raw},
                    evidence="phone-like token in page text",
                )
            )
        for domain in _host_domains(scanner.hrefs):
            candidates.append(
                ObservationCandidate(
                    value=domain,
                    kind="domain",
                    confidence=0.5,
                    source_module=self.name,
                    method=self.method,
                    raw_fields={"seed_url": seed.raw_value},
                    evidence="outbound link host",
                )
            )
        return HarvestResult(module=self.name, candidates=tuple(candidates))


class SocialLinkHarvester:
    """Page links → recognised social profiles with handles."""

    name = "social_link_extractor"
    required_types = frozenset({InputType.URL})
    method = "social-profile link extractor (intellyweave/erfert-style projection)"
    license = "BSD-3"
    attribution = "donors/intellyweave (vendored method), donors/estorides erfert module"

    def run(self, seed: SeedInput, ctx: HarvestContext) -> HarvestResult:
        body = ctx.transport.fetch(seed.raw_value, timeout=8.0)
        if not body:
            return HarvestResult(
                module=self.name, notes=("page fetch returned empty (offline transport)",)
            )
        scanner = _HTMLScanner()
        scanner.feed(body)
        candidates = _social_from_hrefs(scanner.hrefs, self.name, self.method)
        return HarvestResult(module=self.name, candidates=tuple(candidates))


MODULES = (
    EmbeddedContactsHarvester(),
    SocialLinkHarvester(),
)