"""Maltego-style entity→tool catalog for the SpecOps frontend (hermetic).

Maps every recon/OSINT/discovery capability onto the atomic-entity type labels
they consume: zero-layer harvest modules (one tool per module in
``zero.harvesters.modules``), vendored CLI worker *initializations* (never
executed in-process — same philosophy as the zero layer's ``CommandSpec``)
and manual platform actions. Recon/discovery ONLY: whois, subdomain
enumeration, username / email / phone / social presence lookup, cert streams,
search, ... No harassment, flooding or attack-launching tooling by design.

The control plane ships this as a standalone immutable table (no dependency on
the zero package) so determinism and provenance metadata hold under hermetic
tests. Entity type labels follow the ``InputType`` naming style (DOMAIN, EMAIL,
USERNAME, PHONE, URL, NAME, IMAGE, DOCUMENT, ORG, LOCATION, IPV4, CVE,
CRYPTO_ADDRESS).
"""

from __future__ import annotations

from dataclasses import dataclass

_ENTITY_TYPE_LABELS = frozenset(
    {
        "DOMAIN",
        "EMAIL",
        "USERNAME",
        "PHONE",
        "URL",
        "NAME",
        "IMAGE",
        "DOCUMENT",
        "ORG",
        "LOCATION",
        "IPV4",
        "CVE",
        "CRYPTO_ADDRESS",
    }
)


@dataclass(frozen=True)
class ToolSpec:
    """One catalogued recon/discovery tool applicable to entity type(s).

    ``run_mode`` is ``"harvester"`` (zero-layer module), ``"command"`` (vendored
    CLI worker init spec — never launched in-process) or ``"manual"`` (a
    platform-scheduled action). ``command_template`` is the init-only argv.
    """

    tool_id: str
    name: str
    category: str
    entity_types: tuple[str, ...]
    method: str
    source: str
    license: str
    attribution: str
    run_mode: str
    command_template: tuple[str, ...] = ()
    description: str = ""

    def as_dict(self) -> dict:
        return {
            "tool_id": self.tool_id,
            "name": self.name,
            "category": self.category,
            "entity_types": list(self.entity_types),
            "method": self.method,
            "source": self.source,
            "license": self.license,
            "attribution": self.attribution,
            "run_mode": self.run_mode,
            "command_template": list(self.command_template),
            "description": self.description,
        }


def _etypes(*types: str) -> tuple[str, ...]:
    unknown = sorted(set(types) - _ENTITY_TYPE_LABELS)
    if unknown:
        raise ValueError(f"unknown entity types: {sorted(unknown)}")
    return tuple(sorted(types))


def _spec(
    *,
    tool_id: str,
    name: str,
    category: str,
    entity_types: tuple[str, ...],
    method: str,
    source: str,
    license: str,
    attribution: str,
    run_mode: str,
    command_template: tuple[str, ...] = (),
    description: str = "",
) -> ToolSpec:
    return ToolSpec(
        tool_id=tool_id,
        name=name,
        category=category,
        entity_types=_etypes(*entity_types),
        method=method,
        source=source,
        license=license,
        attribution=attribution,
        run_mode=run_mode,
        command_template=command_template,
        description=description,
    )


_TOOLS: tuple[ToolSpec, ...] = (
    # -- zero-layer harvest modules (one tool per harvest module) -------------
    _spec(
        tool_id="dns_records",
        name="DNS Record Read",
        category="harvester",
        entity_types=("DOMAIN",),
        method="DNS record read (dnspython-style, resolver-injected)",
        source="zero.harvesters.modules:dns_records",
        license="MIT",
        attribution="donors/trident DNS module pattern",
        run_mode="harvester",
        description="MX / TXT / SPF glimpse through the injected DNS resolver.",
    ),
    _spec(
        tool_id="domain_social_pattern",
        name="Domain Social Projection",
        category="harvester",
        entity_types=("DOMAIN",),
        method="organisation-social projection (WhoCord cross-reference pattern)",
        source="zero.harvesters.modules:domain_social_pattern",
        license="MIT",
        attribution="donors/WhoCord domain module",
        run_mode="harvester",
        description="Projects an organisation label onto known social platform profiles.",
    ),
    _spec(
        tool_id="email_permutation",
        name="Email Permutation",
        category="harvester",
        entity_types=("DOMAIN", "NAME"),
        method="email-permutation (Email-Permutator / intel-harvester patterns)",
        source="zero.harvesters.modules:email_permutation",
        license="MIT",
        attribution="donors/Email-Permutator, donors/intel-harvester-style logic",
        run_mode="harvester",
        description="First+last+domain → candidate emails; bare domain → role addresses.",
    ),
    _spec(
        tool_id="embedded_contacts",
        name="Embedded Contacts",
        category="harvester",
        entity_types=("URL",),
        method="embedded-contacts extractor (BeautifulSoup-style, stdlib html.parser)",
        source="zero.harvesters.modules:embedded_contacts",
        license="MIT",
        attribution="donors/BeautifulSoup pattern (vendored method only)",
        run_mode="harvester",
        description="Scrapes a page for embedded emails, phones and outbound domains.",
    ),
    _spec(
        tool_id="git_commit_email",
        name="Git Commit Email",
        category="harvester",
        entity_types=("EMAIL", "USERNAME"),
        method="git-commit email extractor (gitsnitch / gh-mailto / GitFive)",
        source="zero.harvesters.modules:git_commit_email",
        license="MIT",
        attribution="donors/gitsnitch, donors/gh-mailto (codeGROOVE-dev), donors/GitFive",
        run_mode="harvester",
        description="Extracts author/committer emails from a supplied git-log blob.",
    ),
    _spec(
        tool_id="maigret_worker",
        name="Maigret Worker (harvest)",
        category="harvester",
        entity_types=("EMAIL", "USERNAME"),
        method="vendored maigret worker command (3000+ site dossier by username/email)",
        source="zero.harvesters.modules:maigret_worker",
        license="MIT",
        attribution="donors/maigret (soxoj/maigret)",
        run_mode="harvester",
        description="Initiates the vendored Maigret dossier worker (init spec only).",
    ),
    _spec(
        tool_id="phone_dorks",
        name="Phone Dorks",
        category="harvester",
        entity_types=("PHONE",),
        method="PhoneInfoga-style Google dork generation",
        source="zero.harvesters.modules:phone_dorks",
        license="MIT",
        attribution="donors/PhoneInfoga dork pattern",
        run_mode="harvester",
        description="Generates deterministic search dork variants for a phone number.",
    ),
    _spec(
        tool_id="qr_exif",
        name="QR + EXIF Extract",
        category="harvester",
        entity_types=("IMAGE",),
        method="QR decode (pyzbar) + EXIF (struct) + OCR worker init",
        source="zero.harvesters.modules:qr_exif",
        license="MIT",
        attribution=(
            "donors/pyzbar (MIT), donors/Pillow+piexif (HPNS) EXIF pattern, "
            "tesseract (Apache-2.0) worker"
        ),
        run_mode="harvester",
        description="Image bytes → QR payloads, EXIF metadata and GPS coordinates.",
    ),
    _spec(
        tool_id="sherlock_worker",
        name="Sherlock Worker (harvest)",
        category="harvester",
        entity_types=("USERNAME",),
        method="vendored sherlock worker command (username enumeration, 400+ sites)",
        source="zero.harvesters.modules:sherlock_worker",
        license="MIT",
        attribution="donors/sherlock (sherlock-project/sherlock)",
        run_mode="harvester",
        description="Initiates the vendored Sherlock username worker (init spec only).",
    ),
    _spec(
        tool_id="social_link_extractor",
        name="Social Link Extractor",
        category="harvester",
        entity_types=("URL",),
        method="social-profile link extractor (intellyweave/erfert-style projection)",
        source="zero.harvesters.modules:social_link_extractor",
        license="BSD-3",
        attribution="donors/intellyweave (vendored method), donors/estorides erfert module",
        run_mode="harvester",
        description="Recognises social hosts in page links and derives handles.",
    ),
    _spec(
        tool_id="social_pattern",
        name="Social Profile Pattern",
        category="harvester",
        entity_types=("USERNAME",),
        method="social-profile pattern projection (Sherlock-style)",
        source="zero.harvesters.modules:social_pattern",
        license="MIT",
        attribution="donors/sherlock profile template data",
        run_mode="harvester",
        description="Username → probable social profile URLs (sherlock-style patterns).",
    ),
    _spec(
        tool_id="subdomain_brute",
        name="Subdomain Brute",
        category="harvester",
        entity_types=("DOMAIN",),
        method="subdomain wordlist brute (+ existence probe, Sublist3r-style)",
        source="zero.harvesters.modules:subdomain_brute",
        license="GPL",
        attribution="donors/Sublist3r wordlist pattern (isolated method)",
        run_mode="harvester",
        description="Static wordlist subdomain enumeration with existence probing.",
    ),
    _spec(
        tool_id="telegram_presence",
        name="Telegram Presence",
        category="harvester",
        entity_types=("PHONE",),
        method="Telegram enumeration via t.me (Ignorant style)",
        source="zero.harvesters.modules:telegram_presence",
        license="MIT",
        attribution="donors/ignorant",
        run_mode="harvester",
        description="Phone → Telegram messenger presence probe via the injected transport.",
    ),
    _spec(
        tool_id="whatsapp_presence",
        name="WhatsApp Presence",
        category="harvester",
        entity_types=("PHONE",),
        method="WhatsApp enumeration via wa.me (Ignorant / DIGI-NETRA style)",
        source="zero.harvesters.modules:whatsapp_presence",
        license="MIT",
        attribution="donors/ignorant, donors/DIGI-NETRA",
        run_mode="harvester",
        description="Phone → WhatsApp messenger presence probe via the injected transport.",
    ),
    # -- vendored CLI worker initializations (init specs only, never executed) --
    _spec(
        tool_id="amass",
        name="Amass",
        category="worker",
        entity_types=("DOMAIN",),
        method="attack-surface subdomain discovery (vendored CLI) — init spec only",
        source="owasp-amass",
        license="Apache-2.0",
        attribution="OWASP Amass (vendored binary, never launched in-process)",
        run_mode="command",
        command_template=("python", "-m", "amass"),
        description="Ancillary subdomain / attack-surface discovery worker.",
    ),
    _spec(
        tool_id="maigret",
        name="Maigret",
        category="worker",
        entity_types=("USERNAME",),
        method="username dossier across 3000+ sites (vendored CLI) — init spec only",
        source="soxoj/maigret",
        license="MIT",
        attribution="donors/maigret (soxoj/maigret)",
        run_mode="command",
        command_template=("python", "-m", "maigret"),
        description="Vendored Maigret dossier worker initialization (username).",
    ),
    _spec(
        tool_id="sherlock",
        name="Sherlock",
        category="worker",
        entity_types=("USERNAME",),
        method="username enumeration across 400+ sites (vendored CLI) — init spec only",
        source="sherlock-project/sherlock",
        license="MIT",
        attribution="donors/sherlock (sherlock-project/sherlock)",
        run_mode="command",
        command_template=("python", "-m", "sherlock"),
        description="Vendored Sherlock username enumeration worker initialization.",
    ),
    _spec(
        tool_id="subfinder",
        name="Subfinder",
        category="worker",
        entity_types=("DOMAIN",),
        method="passive subdomain enumeration (vendored CLI) — init spec only",
        source="projectdiscovery/subfinder",
        license="MIT",
        attribution="ProjectDiscovery subfinder (vendored binary, never launched in-process)",
        run_mode="command",
        command_template=("python", "-m", "subfinder"),
        description="Passive subdomain enumeration worker initialization.",
    ),
    _spec(
        tool_id="tesseract",
        name="Tesseract OCR",
        category="worker",
        entity_types=("IMAGE",),
        method="OCR worker (vendored binary) — init spec only",
        source="tesseract-ocr",
        license="Apache-2.0",
        attribution="tesseract (Apache-2.0) as worker command only",
        run_mode="command",
        command_template=("tesseract", "stdout"),
        description="Vendored Tesseract OCR worker initialization for image text.",
    ),
    _spec(
        tool_id="theharvester",
        name="theHarvester",
        category="worker",
        entity_types=("DOMAIN", "EMAIL"),
        method="domain/email reconnaissance (vendored CLI) — init spec only",
        source="laramies/theHarvester",
        license="GPL-2.0",
        attribution="donors/theHarvester (vendored binary, never launched in-process)",
        run_mode="command",
        command_template=("python", "-m", "theHarvester"),
        description="Vendored theHarvester reconnaissance worker initialization.",
    ),
    # -- manual OSINT / discovery actions (platform-scheduled) ----------------
    _spec(
        tool_id="certstream",
        name="Certstream",
        category="certificates",
        entity_types=("DOMAIN",),
        method="live certificate transparency stream scan for the domain",
        source="certificate transparency logs",
        license="public data",
        attribution="certificate transparency ecosystem",
        run_mode="manual",
        description="Live CT-log scan for certificates issued to the domain.",
    ),
    _spec(
        tool_id="dns_fetch",
        name="DNS Fetch",
        category="infrastructure",
        entity_types=("DOMAIN",),
        method="full DNS record fetch (A / AAAA / MX / TXT / NS / CNAME)",
        source="public DNS",
        license="public data",
        attribution="public DNS resolver data",
        run_mode="manual",
        description="Fetch all available DNS record families for the domain.",
    ),
    _spec(
        tool_id="geo_ip",
        name="Geo-IP",
        category="infrastructure",
        entity_types=("IPV4",),
        method="IP geolocation / ASN attribution lookup",
        source="public GeoIP feeds",
        license="public data",
        attribution="public GeoIP / ASN feeds",
        run_mode="manual",
        description="Geolocation and network attribution for an IPv4 address.",
    ),
    _spec(
        tool_id="github_scrape",
        name="GitHub Scrape",
        category="social",
        entity_types=("USERNAME",),
        method="GitHub profile / repo scrape by username",
        source="GitHub public data",
        license="public data, ToS-dependent",
        attribution="GitHub public profile data",
        run_mode="manual",
        description="Recon of a GitHub account and its public repositories.",
    ),
    _spec(
        tool_id="haveibeenpwned",
        name="Have I Been Pwned",
        category="breaches",
        entity_types=("EMAIL",),
        method="known-breach lookup by email address",
        source="Have I Been Pwned public breach corpus",
        license="public breach data",
        attribution="Have I Been Pwned (breach corpus)",
        run_mode="manual",
        description="Reports known public breaches associated with the email.",
    ),
    _spec(
        tool_id="phone_carrier",
        name="Phone Carrier Lookup",
        category="telecom",
        entity_types=("PHONE",),
        method="phone number carrier / mobile network lookup",
        source="public numbering plan data",
        license="public data",
        attribution="public telecom numbering plan feeds",
        run_mode="manual",
        description="Carrier and mobile network attribution for a phone number.",
    ),
    _spec(
        tool_id="reverse_whois",
        name="Reverse Whois",
        category="infrastructure",
        entity_types=("DOMAIN",),
        method="reverse whois — registrant-to-domain mapping search",
        source="reverse whois indexes",
        license="public registry data",
        attribution="public whois reverse-index services",
        run_mode="manual",
        description="Find domains registered by the same registrant as the seed.",
    ),
    _spec(
        tool_id="social_presence",
        name="Social Presence",
        category="social",
        entity_types=("PHONE",),
        method="cross-platform social presence probe for a phone number",
        source="public messenger presence",
        license="public data",
        attribution="public presence probes",
        run_mode="manual",
        description="Cross-platform social / messenger presence lookup by phone.",
    ),
    _spec(
        tool_id="wayback_cdx",
        name="Wayback CDX",
        category="archives",
        entity_types=("DOMAIN", "URL"),
        method="Wayback Machine CDX index query for archived snapshots",
        source="Internet Archive CDX API",
        license="public archive data",
        attribution="Internet Archive",
        run_mode="manual",
        description="Historical snapshot index for the domain or URL.",
    ),
    _spec(
        tool_id="whois",
        name="Whois",
        category="infrastructure",
        entity_types=("DOMAIN", "IPV4"),
        method="whois / RDAP registration record lookup",
        source="whois / RDAP",
        license="public registry data",
        attribution="public registry data",
        run_mode="manual",
        description="Registration record lookup for a domain or IPv4 address.",
    ),
)

TOOLS: tuple[ToolSpec, ...] = tuple(sorted(_TOOLS, key=lambda t: t.tool_id))

_TOOLS_BY_ID = {t.tool_id: t for t in TOOLS}


def all_tools() -> tuple[ToolSpec, ...]:
    """Every catalogued tool, name-sorted by ``tool_id`` (deterministic)."""
    return TOOLS


def tools_for(entity_type: str) -> tuple[ToolSpec, ...]:
    """Tools applicable to ``entity_type``, sorted by ``tool_id``."""
    return tuple(
        sorted(
            (t for t in TOOLS if entity_type in t.entity_types),
            key=lambda t: t.tool_id,
        )
    )


def tool(tool_id: str) -> ToolSpec | None:
    """Look up a single tool by id (``None`` when unknown)."""
    return _TOOLS_BY_ID.get(tool_id)


_IDENTITY_KEY_TYPES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("account", "handle", "username"), "USERNAME"),
    (("email",), "EMAIL"),
    (("phone", "telephone"), "PHONE"),
    (("domain", "host"), "DOMAIN"),
    (("url",), "URL"),
    (("name", "full_name", "person"), "NAME"),
    (("org", "company"), "ORG"),
    (("location", "city", "country"), "LOCATION"),
    (("ip", "ipv4"), "IPV4"),
    (("id_number",), "DOCUMENT"),
)


def infer_entity_type(identity: dict) -> str:
    """Map a canonical_identity dict onto an entity type label (deterministic).

    First non-empty matching key wins, in the fixed order above; unknown or
    empty identities fall back to ``"UNKNOWN"``. Pure, no IO.
    """
    for keys, entity_type in _IDENTITY_KEY_TYPES:
        if any(identity.get(key) for key in keys):
            return entity_type
    return "UNKNOWN"