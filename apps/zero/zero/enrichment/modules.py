"""Enricher modules (spec/010 §0.9 table, T131) — 10+ deterministic transforms.

Every enricher is a pure function ``(SeedInput, context-dict) → candidates``.
Network-dependent steps (DNS, HTML) consume context injected by the caller
(transport result / resolver), never make a bare socket call, so the whole
layer is testable offline. Breach / geo / influence lookups are deterministic
stubs over fixed local tables — the same shape a live DeHashed / MaxMind /
Name-Prism adapter would fill.

   Source repos (methods only): donors/maigret (reverse_username), donors/
   GitHubEmailFinder/gitsnitch (username_to_github), donors/PhoneInfoga
   (whatsapp), donors/Name2Email (name patterns), donors/erfert estimator.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlparse

from ..harvesters.contracts import ObservationCandidate
from ..harvesters.domain import email_permutations
from ..type_detector import InputType, SeedInput

_MOCK_BREACH_INDEX: dict[str, list[tuple[str, str]]] = {
    "acme.com": [
        ("2021-03", "Marriott (mock)"),
        ("2019-01", "LinkedIn scrape (mock)"),
    ],
    "exemple.org": [
        ("2017-06", "Spammers' delight (mock)"),
    ],
    "corp.co": [
        ("2020-12", "Hudson Rock leak (mock)"),
    ],
}

_MOCK_GEO: dict[str, tuple[str, float, float]] = {
    "8.8.8.8": ("Mountain View, US", 37.3860, -122.0838),
    "1.1.1.1": ("Sydney, AU", -33.8688, 151.2093),
    "4.4.4.4": ("Los Angeles, US", 34.0522, -118.2437),
}

_TECH_SIGNALS: tuple[tuple[str, str], ...] = (
    ("wp-content", "WordPress"),
    ("cloudflare", "Cloudflare"),
    ("react", "React"),
    ("next", "Next.js"),
    ("drupal", "Drupal"),
    ("shopify", "Shopify"),
    ("google-analytics", "Google Analytics"),
    ("vite", "Vite"),
)

_SOCIAL_HOSTS = (
    ("github.com", "github"),
    ("gitlab.com", "gitlab"),
    ("twitter.com", "twitter"),
    ("x.com", "twitter"),
    ("linkedin.com", "linkedin"),
    ("t.me", "telegram"),
    ("reddit.com", "reddit"),
    ("instagram.com", "instagram"),
    ("facebook.com", "facebook"),
)

_HANDLE_RE = re.compile(r"^[a-zA-Z0-9_.-]{1,40}$")


@dataclass(frozen=True)
class Enricher:
    """A deterministic enrichment transform with provenance metadata."""

    name: str
    input_types: frozenset[InputType]
    license: str
    attribution: str
    method: str
    enrich: Callable[[SeedInput, dict], tuple[ObservationCandidate, ...]]


# -- enricher bodies ---------------------------------------------------------


def _reverse_email_username(seed: SeedInput, _ctx: dict) -> tuple[ObservationCandidate, ...]:
    if "@" not in seed.raw_value:
        return ()
    local, domain = seed.raw_value.rsplit("@", 1)
    return (
        ObservationCandidate(
            value=local,
            kind="username",
            confidence=0.9,
            source_module="reverse_email_username",
            method="email local-part → username (Maigret-style)",
            raw_fields={"domain": domain, "seed": seed.raw_value},
            evidence="local part of an email address",
        ),
    )


def _email_to_breach(seed: SeedInput, _ctx: dict) -> tuple[ObservationCandidate, ...]:
    if "@" not in seed.raw_value:
        return ()
    _, domain = seed.raw_value.rsplit("@", 1)
    hits = _MOCK_BREACH_INDEX.get(domain.lower(), [])
    return tuple(
        ObservationCandidate(
            value=f"{when}:{name}",
            kind="breach",
            confidence=0.75,
            source_module="email_to_breach",
            method="breach index lookup (deterministic mock, user-scanner/Holehe shape)",
            raw_fields={"breach": name, "date": when, "seed": seed.raw_value},
            evidence=f"mock breach hit {name}",
        )
        for when, name in hits
    )


def _domain_to_dns(seed: SeedInput, ctx: dict) -> tuple[ObservationCandidate, ...]:
    resolver = ctx.get("dns_records")
    if resolver is None:
        return ()
    records = resolver(seed.raw_value)
    return tuple(
        ObservationCandidate(
            value=str(value),
            kind="dns_record",
            confidence=0.9,
            source_module="domain_to_dns",
            method="DNS record enrichment (dnspython-style resolver)",
            raw_fields={"record_type": rtype, "domain": seed.raw_value},
            evidence="DNS record from injected resolver",
        )
        for rtype, values in sorted(records.items())
        for value in sorted(values)
    )


def _url_to_social(seed: SeedInput, _ctx: dict) -> tuple[ObservationCandidate, ...]:
    parsed = urlparse(seed.raw_value)
    host = (parsed.hostname or "").lower()
    platform = None
    for known, platform_name in _SOCIAL_HOSTS:
        if host == known or host.endswith("." + known):
            platform = platform_name
            break
    if platform is None:
        return ()
    path = parsed.path.strip("/")
    handle = path.split("/")[0] if path else ""
    if not _HANDLE_RE.match(handle):
        return ()
    return (
        ObservationCandidate(
            value=f"https://{host}/{handle}",
            kind="social_profile",
            confidence=0.7,
            source_module="url_to_social",
            method="URL → social profile projection (intellyweave/erfert-style)",
            raw_fields={"platform": platform, "handle": handle, "seed": seed.raw_value},
            evidence="recognized social host in URL",
        ),
    )


def _phone_to_whatsapp(seed: SeedInput, _ctx: dict) -> tuple[ObservationCandidate, ...]:
    return (
        ObservationCandidate(
            value=f"whatsapp:{''.join(ch for ch in seed.raw_value if ch.isdigit())}",
            kind="presence",
            confidence=0.5,
            source_module="phone_to_whatsapp",
            method="WhatsApp ID projection (PhoneInfoga/whatsapp enumerators)",
            raw_fields={"seed": seed.raw_value},
            evidence="unverified WhatsApp presence projection",
        ),
    )


def _username_to_github(seed: SeedInput, _ctx: dict) -> tuple[ObservationCandidate, ...]:
    return (
        ObservationCandidate(
            value=f"https://github.com/{seed.raw_value}",
            kind="social_profile",
            confidence=0.55,
            source_module="username_to_github",
            method="username → GitHub profile (gitsnitch / gh-mailto)",
            raw_fields={"username": seed.raw_value},
            evidence="GitHub profile projection",
        ),
    )


def _name_to_email_patterns(seed: SeedInput, ctx: dict) -> tuple[ObservationCandidate, ...]:
    domain = str(ctx.get("domain") or "").strip()
    tokens = re.split(r"\s+", seed.raw_value.strip())
    if not domain or len(tokens) < 2:
        return ()
    first, last = tokens[0], tokens[-1]
    return tuple(
        ObservationCandidate(
            value=email,
            kind="email",
            confidence=0.35,
            source_module="name_to_email_patterns",
            method="name+company → email permutations (Name2Email / Email-Permutator)",
            raw_fields={"first": first, "last": last, "domain": domain, "pattern": pattern},
            evidence=f"name-permutation pattern {pattern}",
        )
        for email, pattern in email_permutations(first, last, domain)
    )


def _email_to_linkedin(seed: SeedInput, _ctx: dict) -> tuple[ObservationCandidate, ...]:
    if "@" not in seed.raw_value:
        return ()
    local, _ = seed.raw_value.rsplit("@", 1)
    return (
        ObservationCandidate(
            value=f"https://linkedin.com/in/{local}",
            kind="social_profile",
            confidence=0.4,
            source_module="email_to_linkedin",
            method="email local-part → LinkedIn profile (Hunter.io-style exchange)",
            raw_fields={"local_part": local, "seed": seed.raw_value},
            evidence="prospective LinkedIn handle from email",
        ),
    )


def _ip_to_geo(seed: SeedInput, ctx: dict) -> tuple[ObservationCandidate, ...]:
    ip = seed.raw_value if seed.detected_type is InputType.URL else str(ctx.get("ip") or "")
    if seed.detected_type is InputType.UNKNOWN:
        ip = seed.raw_value
    if "@" in ip or "/" in ip or "." not in ip:
        return ()
    candidate_ip = ip.split("@")[-1].split("/")[0]
    location = _MOCK_GEO.get(candidate_ip)
    if location is None:
        return ()
    label, lat, lon = location
    return (
        ObservationCandidate(
            value=f"{label} ({lat},{lon})",
            kind="geo",
            confidence=0.95,
            source_module="ip_to_geo",
            method="IP → geo/ISP stub (MaxMind-style table)",
            raw_fields={"ip": candidate_ip},
            evidence="deterministic mock geo lookup",
        ),
    )


def _domain_to_technologies(seed: SeedInput, ctx: dict) -> tuple[ObservationCandidate, ...]:
    html_body = str(ctx.get("html") or seed.metadata.get("html") or "")
    if not html_body:
        return ()
    html_lower = html_body.lower()
    hits = [(tech, needle) for needle, tech in _TECH_SIGNALS if needle in html_lower]
    return tuple(
        ObservationCandidate(
            value=tech,
            kind="technology",
            confidence=0.8,
            source_module="domain_to_technologies",
            method="tech-stack signature match (Wappalyzer-style signal table)",
            raw_fields={"signal": needle, "domain": seed.raw_value},
            evidence=f"web-signal {needle!r} present in HTML",
        )
        for tech, needle in hits
    )


def _social_to_influencer_score(seed: SeedInput, _ctx: dict) -> tuple[ObservationCandidate, ...]:
    handle = seed.raw_value
    score = min(1.0, 0.25 + 0.04 * len(handle))
    return (
        ObservationCandidate(
            value=f"{score:.2f}",
            kind="influence_score",
            confidence=0.3,
            source_module="social_to_influencer_score",
            method="social influence proxy (erfert social-score)",
            raw_fields={"handle": handle},
            evidence="deterministic size-based popularity proxy",
        ),
    )


ENRICHERS: tuple[Enricher, ...] = (
    Enricher(
        "reverse_email_username", frozenset({InputType.EMAIL}), "MIT",
        "donors/maigret", "email local-part → username",
        _reverse_email_username,
    ),
    Enricher(
        "email_to_breach", frozenset({InputType.EMAIL}), "MIT",
        "donors/user-scanner, donors/Holehe", "breach check (mock index)",
        _email_to_breach,
    ),
    Enricher(
        "domain_to_dns", frozenset({InputType.DOMAIN}), "MIT",
        "dnspython (optional), donors/trident", "DNS record enrichment",
        _domain_to_dns,
    ),
    Enricher(
        "url_to_social", frozenset({InputType.URL}), "BSD-3",
        "donors/intellyweave, donors/estorides", "URL → social profile",
        _url_to_social,
    ),
    Enricher(
        "phone_to_whatsapp", frozenset({InputType.PHONE}), "MIT",
        "donors/PhoneInfoga, donors/ignorant", "WhatsApp ID projection",
        _phone_to_whatsapp,
    ),
    Enricher(
        "username_to_github", frozenset({InputType.USERNAME}), "MIT",
        "donors/gitsnitch, donors/gh-mailto", "username → GitHub profile",
        _username_to_github,
    ),
    Enricher(
        "name_to_email_patterns", frozenset({InputType.NAME}), "MIT",
        "donors/Name2Email, donors/Email-Permutator", "name → email permutations",
        _name_to_email_patterns,
    ),
    Enricher(
        "email_to_linkedin", frozenset({InputType.EMAIL}), "MIT",
        "Hunter.io-style exchange (method only)", "email → LinkedIn profile",
        _email_to_linkedin,
    ),
    Enricher(
        "ip_to_geo", frozenset({InputType.UNKNOWN, InputType.URL}), "MIT",
        "MaxMind-style stub (method only)", "IP → geo stub",
        _ip_to_geo,
    ),
    Enricher(
        "domain_to_technologies", frozenset({InputType.DOMAIN}), "MIT",
        "donors/intellyweave signal words", "tech-stack signature match",
        _domain_to_technologies,
    ),
    Enricher(
        "social_to_influencer_score", frozenset({InputType.USERNAME}), "MIT",
        "donors/estorides social-score estimator", "social influence proxy",
        _social_to_influencer_score,
    ),
)


def run_enrichers(seed: SeedInput, ctx: dict | None = None) -> list[ObservationCandidate]:
    """Run every enricher whose input type matches the seed (name-sorted)."""
    ctx = ctx or {}
    matched = sorted(
        (enricher for enricher in ENRICHERS if seed.detected_type in enricher.input_types),
        key=lambda e: e.name,
    )
    candidates: list[ObservationCandidate] = []
    for enricher in matched:
        try:
            candidates.extend(enricher.enrich(seed, ctx))
        except Exception:
            pass  # enrichment never takes the wave down
    return candidates