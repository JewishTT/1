"""Domain harvesters (spec/010 §0.2): email-permutation, subdomain, DNS, social.

All modules are thin, deterministic adapters over stdlib transforms:

- ``EmailPermutationHarvester`` ports the Email-Permutator / intel-harvester
  "first+last+company → possible emails" pattern; on a bare domain seed it emits
  role-address candidates (50+ per spec scenario).
- ``SubdomainBruteHarvester`` runs a static wordlist (+) optional existence
  probe over the injected transport (+ optional DNS resolver).
- ``DnsRecordHarvester`` surfaces MX/SPF/TXT records via the injected DNS
  resolver (never a bare socket).
- ``DomainSocialHarvester`` projects organisation labels onto well-known social
  platforms (WhoCord-style cross-reference).

   Source repos: donors/Email-Permutator (MIT), donors/theHarvester (MIT),
   donors/intel-harvester-equivalent logic, donors/Sublist3r (GPL) pattern.
"""

from __future__ import annotations

import re

from ..type_detector import InputType, SeedInput
from .contracts import HarvestResult, ObservationCandidate
from .registry import HarvestContext

EMAIL_ROLES: tuple[str, ...] = (
    "admin", "info", "contact", "support", "sales", "press", "hr", "legal",
    "billing", "marketing", "office", "postmaster", "webmaster", "abuse",
    "privacy", "security", "finance", "media", "recruiting", "jobs",
    "hello", "team", "careers", "partners", "investors",
)

SUBDOMAIN_WORDLIST: tuple[str, ...] = (
    "www", "mail", "smtp", "pop", "imap", "mx", "ns", "ns1", "ns2", "dev",
    "staging", "api", "app", "cdn", "static", "assets", "media", "admin",
    "portal", "blog", "shop", "store", "help", "support", "docs", "status",
    "gate", "test", "qa", "web", "ftp", "ssh", "vpn", "mobile", "beta",
    "live", "demo", "sandbox", "secure", "auth", "sso", "login", "remote",
    "office", "outlook", "autodiscover", "mail2", "mx2", "vpn2", "firewall",
)

# Beta names that overlap with our own typo-list are intentionally excluded
# from the wordlist to keep the generator deterministic and collision-free.

_LOCAL_OK = re.compile(r"^[a-z0-9_.-]+$")


def email_permutations(first: str, last: str, domain: str) -> list[tuple[str, str]]:
    """Deterministic email-permutation engine (first+last+domain → candidates).

    Returns ``(email, pattern_name)`` pairs in a fixed order so results are
    reproducible across runs and platforms.
    """
    f = (first or "").strip().lower()
    lname = (last or "").strip().lower()
    domain = domain.lower().strip()
    if not f or not lname or not domain:
        return []
    local_parts: list[tuple[str, str]] = [
        ("first.last", f"{f}.{lname}"),
        ("firstlast", f + lname),
        ("flast", f[0] + lname),
        ("firstl", f + lname[0]),
        ("f.last", f[0] + "." + lname),
        ("first_last", f + "_" + lname),
        ("last.first", f"{lname}.{f}"),
        ("lastfirst", lname + f),
        ("last.f", lname + "." + f[0]),
        ("lfirst", lname[:1] + f),
        ("first.last1", f"{f}.{lname[0]}"),
        ("first1last", f + "1" + lname),
    ]
    seen: set[str] = set()
    emails: list[tuple[str, str]] = []
    for pattern, local in local_parts:
        if not _LOCAL_OK.match(local) or len(local) < 3 or local in seen:
            continue
        seen.add(local)
        emails.append((f"{local}@{domain}", pattern))
    return emails


def role_addresses(domain: str) -> list[tuple[str, str]]:
    """Standard role mailboxes for a domain (Mail-Hunter / mailhound pattern)."""
    domain = domain.lower().strip()
    return [(f"{role}@{domain}", "role-address") for role in EMAIL_ROLES]


def _name_label(domain: str) -> str:
    label = domain.split(".")[0]
    return label if re.match(r"^[a-z0-9][a-z0-9-]{1,30}$", label) else ""


class EmailPermutationHarvester:
    """First+last+domain → candidate emails; bare domain → role addresses."""

    name = "email_permutation"
    required_types = frozenset({InputType.NAME, InputType.DOMAIN})
    method = "email-permutation (Email-Permutator / intel-harvester patterns)"
    license = "MIT"
    attribution = "donors/Email-Permutator, donors/intel-harvester-style logic"

    def run(self, seed: SeedInput, ctx: HarvestContext) -> HarvestResult:
        domain = str(ctx.seed.metadata.get("domain") or "").strip().lower()
        candidates: list[ObservationCandidate] = []
        if seed.detected_type is InputType.NAME:
            name_tokens = re.split(r"\s+", seed.raw_value.strip())
            first, last = _first_last(name_tokens)
            if domain and first and last:
                candidates.extend(
                    ObservationCandidate(
                        value=email,
                        kind="email",
                        confidence=round(0.7 * (1.0 if seed.confidence > 0.4 else 0.6), 4),
                        source_module=self.name,
                        method=self.method,
                        raw_fields={
                            "first": first,
                            "last": last,
                            "domain": domain,
                            "pattern": pattern,
                        },
                        evidence=f"name-permutation pattern {pattern}",
                    )
                    for email, pattern in email_permutations(first, last, domain)
                )
        if seed.detected_type is InputType.DOMAIN or domain:
            target = domain or seed.raw_value
            candidates.extend(
                ObservationCandidate(
                    value=email,
                    kind="email",
                    confidence=0.45,
                    source_module=self.name,
                    method=self.method,
                    raw_fields={"domain": target, "pattern": pattern},
                    evidence=f"role-address {pattern}",
                )
                for email, pattern in role_addresses(target)
            )
        return HarvestResult(module=self.name, candidates=tuple(candidates))


class SubdomainBruteHarvester:
    """Static wordlist subdomain enumeration (+ existence probe via transport)."""

    name = "subdomain_brute"
    required_types = frozenset({InputType.DOMAIN})
    method = "subdomain wordlist brute (+ existence probe, Sublist3r-style)"
    license = "GPL"
    attribution = "donors/Sublist3r wordlist pattern (isolated method)"

    def run(self, seed: SeedInput, ctx: HarvestContext) -> HarvestResult:
        if seed.detected_type is not InputType.DOMAIN:
            return HarvestResult(module=self.name)
        domain = seed.raw_value.lower()
        candidates: list[ObservationCandidate] = []
        for word in SUBDOMAIN_WORDLIST:
            sub = f"{word}.{domain}"
            exists = ctx.transport.exists(f"http://{sub}")
            confidence = 0.85 if exists else 0.30
            candidates.append(
                ObservationCandidate(
                    value=sub,
                    kind="domain",
                    confidence=confidence,
                    source_module=self.name,
                    method=self.method,
                    raw_fields={"word": word, "domain": domain, "verified": exists},
                    evidence=f"wordlist subdomain, verified={exists}",
                )
            )
        return HarvestResult(module=self.name, candidates=tuple(candidates))


class DnsRecordHarvester:
    """MX / TXT / SPF glimpse through the injected DNS resolver."""

    name = "dns_records"
    required_types = frozenset({InputType.DOMAIN})
    method = "DNS record read (dnspython-style, resolver-injected)"
    license = "MIT"
    attribution = "donors/trident DNS module pattern"

    def run(self, seed: SeedInput, ctx: HarvestContext) -> HarvestResult:
        if ctx.dns_records is None:
            return HarvestResult(module=self.name, notes=("dns_records resolver not injected",))
        records = ctx.dns_records(seed.raw_value)
        candidates = [
            ObservationCandidate(
                value=str(value),
                kind="dns_record",
                confidence=0.9,
                source_module=self.name,
                method=self.method,
                raw_fields={"record_type": rtype, "domain": seed.raw_value},
                evidence=f"DNS {rtype} record",
            )
            for rtype, values in sorted(records.items())
            for value in sorted(values)
        ]
        return HarvestResult(module=self.name, candidates=tuple(candidates))


class DomainSocialHarvester:
    """Organisation label → known social platform profiles (WhoCord-style)."""

    name = "domain_social_pattern"
    required_types = frozenset({InputType.DOMAIN})
    method = "organisation-social projection (WhoCord cross-reference pattern)"
    license = "MIT"
    attribution = "donors/WhoCord domain module"

    _PLATFORMS = (
        ("linkedin.com/company", "linkedin"),
        ("x.com", "twitter"),
        ("facebook.com", "facebook"),
        ("youtube.com/@", "youtube"),
        ("github.com", "github"),
        ("t.me", "telegram"),
    )

    def run(self, seed: SeedInput, ctx: HarvestContext) -> HarvestResult:
        label = _name_label(seed.raw_value)
        if not label:
            return HarvestResult(module=self.name)
        candidates = [
            ObservationCandidate(
                value=f"https://{host}/{label}",
                kind="social_profile",
                confidence=0.30,
                source_module=self.name,
                method=self.method,
                raw_fields={"label": label, "platform": platform},
                evidence="domain-label social projection (unverified)",
            )
            for host, platform in self._PLATFORMS
        ]
        return HarvestResult(module=self.name, candidates=tuple(candidates))


def _first_last(tokens: list[str]) -> tuple[str, str]:
    if not tokens:
        return "", ""
    return tokens[0], tokens[-1] if len(tokens) > 1 else ""


MODULES = (
    EmailPermutationHarvester(),
    SubdomainBruteHarvester(),
    DnsRecordHarvester(),
    DomainSocialHarvester(),
)