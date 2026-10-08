"""SpecOps engagement catalog: PAP levels, ATT&CK techniques, engagements, operations.

Adapted from donors/trident (Go, GPL-3.0) — the Permissible Actions Protocol: an
ordered detectability ladder where every service carries a MIN/MAX PAP level and a
run is refused when the service exceeds the caller's ceiling. Changes: the ladder is
an IntEnum rather than four string flags; the ceiling lives on the engagement
rather than a CLI flag, because the platform is multi-tenant and the ceiling has to
travel with the authorization record, not with the process. The refusal is a value
(`GateDecision`) rather than an exit code, because the caller is an HTTP route.

Adapted from donors/estorides (AGPL-3.0) — `scope` semantics: an in-scope list and
an out-of-scope list, and OUT-OF-SCOPE WINS. Changes: reduced to two frozen tuples
on the engagement; the AGPL CLI plumbing, proxy/Tor transport and source registry
are not carried (licence: method only, per specs/022 repair/LICENCE-ANALYSIS.md).

Adapted from donors/caldera (Apache-2.0) — the seven-phase operation model and the
adversary profile. Changes: phases are a closed enum so a typo cannot become a new
phase; adversaries are static records, not plugin-loaded objects, because the
control plane does not own the Caldera process.

Written here: the ATT&CK technique table, the engagement/operation records, the
coverage computation and the gate itself.

The gate is the reason this module exists. A technique is executable only when
`technique.pap_min <= engagement.pap_ceiling` AND its target host is in scope AND
no out-of-scope entry matches. Anything else is refused with a reason the UI
renders. §99: a refusal names what is missing; it never degrades to a zero.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

# ── PAP ladder ─────────────────────────────────────────────────────


class PapLevel(IntEnum):
    """Ordered detectability ladder (trident: `--pap-limit red|amber|green|white`).

    WHITE  no contact with the target whatsoever — public sources, archives, leaks
    GREEN  passive interaction — DNS, CT logs, leaked-credential corpora
    AMBER  active interaction — scanning, phishing simulation, exploitation attempts
    RED    execution or impact inside the target estate
    """

    WHITE = 0
    GREEN = 1
    AMBER = 2
    RED = 3

    @classmethod
    def parse(cls, raw: str) -> PapLevel:
        try:
            return cls[raw.strip().upper()]
        except KeyError as exc:
            raise ValueError(f"unknown PAP level: {raw!r}") from exc


PAP_LADDER: tuple[PapLevel, ...] = tuple(sorted(PapLevel, key=lambda p: int(p)))


# ── Kill chain ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class Phase:
    """One Caldera operation phase (Apache-2.0 vocabulary, static here)."""

    key: str
    label: str
    ordinal: int


_PHASE_ROWS = (
    ("reconnaissance", "Reconnaissance", 0),
    ("weaponization", "Weaponization", 1),
    ("delivery", "Delivery", 2),
    ("exploitation", "Exploitation", 3),
    ("installation", "Installation", 4),
    ("command_and_control", "Command & Control", 5),
    ("actions_on_objectives", "Actions on Objectives", 6),
)

PHASES: tuple[Phase, ...] = tuple(
    sorted((Phase(*row) for row in _PHASE_ROWS), key=lambda p: p.ordinal)
)

_PHASES_BY_KEY = {p.key: p for p in PHASES}


def phase(key: str) -> Phase | None:
    return _PHASES_BY_KEY.get(key)


# ── ATT&CK tactics ─────────────────────────────────────────────────

#: Enterprise ATT&CK tactic order. Used to lay out the coverage matrix.
TACTIC_ORDER: tuple[str, ...] = (
    "reconnaissance",
    "resource_development",
    "initial_access",
    "execution",
    "persistence",
    "privilege_escalation",
    "defense_evasion",
    "credential_access",
    "discovery",
    "lateral_movement",
    "collection",
    "command_and_control",
    "exfiltration",
    "impact",
)


@dataclass(frozen=True)
class Technique:
    """One ATT&CK technique as the platform plans it.

    ``pap_min`` is the lowest PAP level at which the technique is permitted, and it
    is the only thing that decides authorization. ``osint_inputs`` names the entity
    types the OSINT core must already hold for the technique to be plannable at
    all — a technique with no OSINT inputs cannot be planned from this platform's
    evidence, and the coverage report says so rather than implying otherwise.
    ``detection`` is the signal a defender should see; it is what makes the coverage
    report a defensive artefact and not only an offensive one.
    """

    technique_id: str
    name: str
    tactic: str
    pap_min: PapLevel
    osint_inputs: tuple[str, ...]
    detection: str
    source: str
    license: str
    attribution: str

    def as_dict(self) -> dict:
        return {
            "technique_id": self.technique_id,
            "name": self.name,
            "tactic": self.tactic,
            "pap_min": self.pap_min.name,
            "pap_rank": int(self.pap_min),
            "osint_inputs": list(self.osint_inputs),
            "detection": self.detection,
            "source": self.source,
            "license": self.license,
            "attribution": self.attribution,
        }


def _t(
    technique_id: str,
    name: str,
    tactic: str,
    pap_min: PapLevel,
    osint_inputs: tuple[str, ...],
    detection: str,
    source: str,
    license: str,
    attribution: str,
) -> Technique:
    if tactic not in TACTIC_ORDER:
        raise ValueError(f"unknown tactic: {tactic!r} for {technique_id}")
    return Technique(
        technique_id=technique_id,
        name=name,
        tactic=tactic,
        pap_min=pap_min,
        osint_inputs=osint_inputs,
        detection=detection,
        source=source,
        license=license,
        attribution=attribution,
    )


_W = PapLevel.WHITE
_G = PapLevel.GREEN
_A = PapLevel.AMBER
_R = PapLevel.RED

_ATTACK = ("MITRE ATT&CK Enterprise", "Apache-2.0", "mitre-attack/attack-stix-data")

_TECHNIQUES: tuple[Technique, ...] = (
    # ── Reconnaissance ──────────────────────────────────────────────
    _t("T1595", "Active Scanning", "reconnaissance", _A, ("DOMAIN", "IPV4"),
       "Outbound scan bursts from operator infrastructure", *_ATTACK),
    _t("T1592", "Gather Victim Host Information", "reconnaissance", _G, ("DOMAIN", "IPV4"),
       "Passive DNS / CT log pivot by an unfamiliar party", *_ATTACK),
    _t("T1589", "Gather Victim Identity Information", "reconnaissance", _G,
       ("EMAIL", "USERNAME", "NAME", "ORG"),
       "Bulk lookups of employee records against third-party people-search", *_ATTACK),
    _t("T1590", "Gather Victim Network Information", "reconnaissance", _G, ("DOMAIN", "IPV4"),
       "WHOIS/RDAP and DNS enumeration of the target's registered space", *_ATTACK),
    _t("T1596", "Search Open Websites/Domains", "reconnaissance", _W,
       ("DOMAIN", "ORG", "NAME"),
       "Search-engine referrers for internal document names", *_ATTACK),
    _t("T1597", "Search Closed Sources", "reconnaissance", _W,
       ("EMAIL", "USERNAME", "DOMAIN"),
       "Credential-dump corpus access overlapping the target's domain", *_ATTACK),
    # ── Resource Development ────────────────────────────────────────
    _t("T1583", "Acquire Infrastructure: Domains", "resource_development", _W,
       ("DOMAIN",), "Newly registered domain resolving near target brand", *_ATTACK),
    _t("T1584", "Compromise Infrastructure", "resource_development", _A,
       ("DOMAIN", "IPV4", "EMAIL"), "Third-party host with new outbound TLS to target", *_ATTACK),
    _t("T1588", "Obtain Capabilities", "resource_development", _W, (),
       "Shared tooling fingerprint across unrelated infrastructure", *_ATTACK),
    _t("T1586", "Compromise Accounts", "resource_development", _A,
       ("EMAIL", "USERNAME"), "Valid-accounts login from an unfamiliar ASN", *_ATTACK),
    # ── Initial Access ──────────────────────────────────────────────
    _t("T1566", "Phishing", "initial_access", _A, ("EMAIL", "USERNAME", "NAME"),
       "Mail-gateway link detonation; user report", *_ATTACK),
    _t("T1190", "Exploit Public-Facing Application", "initial_access", _A,
       ("DOMAIN", "URL", "CVE"),
       "WAF/IPS rule hit followed by a request pattern, not a single payload", *_ATTACK),
    _t("T1133", "External Remote Services", "initial_access", _A, ("IPV4", "ORG"),
       "VPN/SSH/RDP logon outside the operator's known geo set", *_ATTACK),
    _t("T1078", "Valid Accounts", "initial_access", _A, ("EMAIL", "USERNAME"),
       "Impossible-travel authentication; token issued to a new device", *_ATTACK),
    # ── Execution ───────────────────────────────────────────────────
    _t("T1059", "Command and Scripting Interpreter", "execution", _R, ("IPV4", "DOMAIN"),
       "Signed-script host spawning an interpreter with encoded arguments", *_ATTACK),
    _t("T1204", "User Execution", "execution", _A, ("EMAIL", "NAME", "DOCUMENT"),
       "Mark-of-the-web bypass plus a child process of a user-opened document", *_ATTACK),
    _t("T1053", "Scheduled Task/Job", "execution", _R, ("IPV4",),
       "Task creation event with a remote-path action", *_ATTACK),
    _t("T1569", "System Services", "execution", _R, ("IPV4",),
       "Service install / scm change outside the change window", *_ATTACK),
    # ── Persistence ─────────────────────────────────────────────────
    _t("T1547", "Boot or Logon Autostart Execution", "persistence", _R, ("IPV4",),
       "Run-key / autostart write not from a deployment tool", *_ATTACK),
    _t("T1136", "Create Account", "persistence", _R, ("EMAIL", "USERNAME", "NAME"),
       "Net-user-add event outside the identity provider", *_ATTACK),
    _t("T1098", "Account Manipulation", "persistence", _R, ("EMAIL", "USERNAME"),
       "IdP group-membership change without a ticket", *_ATTACK),
    _t("T1505.003", "Server Software Component: Web Shell", "persistence", _R,
       ("DOMAIN", "URL", "IPV4"), "New executable under a web root", *_ATTACK),
    _t("T1543", "Create or Modify System Process", "persistence", _R, ("IPV4",),
       "Service creation with an ImagePath outside standard locations", *_ATTACK),
    # ── Privilege Escalation ────────────────────────────────────────
    _t("T1068", "Exploitation for Privilege Escalation", "privilege_escalation", _R,
       ("CVE", "IPV4", "DOMAIN"), "Kernel/EDR telemetry on an exploit primitive", *_ATTACK),
    _t("T1134", "Access Token Manipulation", "privilege_escalation", _R, ("IPV4",),
       "Duplicate-token handle opened against a privileged process", *_ATTACK),
    _t("T1548", "Abuse Elevation Control Mechanism", "privilege_escalation", _R, ("IPV4",),
       "UAC bypass artefact or sudo abuse outside an admin session", *_ATTACK),
    # ── Defense Evasion ─────────────────────────────────────────────
    _t("T1070", "Indicator Removal", "defense_evasion", _R, ("IPV4",),
       "Log gap on a host that otherwise reports normally", *_ATTACK),
    _t("T1027", "Obfuscated Files or Information", "defense_evasion", _R, ("IPV4", "DOCUMENT"),
       "High-entropy payload dropped; decode-before-scan gap", *_ATTACK),
    _t("T1036", "Masquerading", "defense_evasion", _R, ("IPV4",),
       "Binary name colliding with a system binary in a non-standard path", *_ATTACK),
    _t("T1562", "Impair Defenses", "defense_evasion", _R, ("IPV4",),
       "Security-agent stop/disable event, or Defender exclusion added", *_ATTACK),
    _t("T1218", "System Binary Proxy Execution", "defense_evasion", _R, ("IPV4",),
       "rundll32/mshta spawned by an unexpected parent", *_ATTACK),
    # ── Credential Access ───────────────────────────────────────────
    _t("T1110", "Brute Force", "credential_access", _A, ("EMAIL", "USERNAME", "IPV4"),
       "Failed-login rate spike against one account", *_ATTACK),
    _t("T1003", "OS Credential Dumping", "credential_access", _R, ("IPV4",),
       "LSASS access by a non-system process", *_ATTACK),
    _t("T1552", "Unsecured Credentials", "credential_access", _G,
       ("EMAIL", "DOMAIN", "DOCUMENT"), "Secret material found in a public store", *_ATTACK),
    _t("T1558", "Steal or Forge Kerberos Tickets", "credential_access", _R,
       ("IPV4", "ORG"), "Anomalous service-ticket request volume", *_ATTACK),
    _t("T1621", "MFA Request Generation", "credential_access", _A, ("EMAIL", "USERNAME"),
       "Repeated MFA push to a single user with no successful login", *_ATTACK),
    # ── Discovery ───────────────────────────────────────────────────
    _t("T1087", "Account Discovery", "discovery", _R, ("IPV4", "DOMAIN"),
       "Directory enumeration from a single host in a burst", *_ATTACK),
    _t("T1018", "Remote System Discovery", "discovery", _R, ("IPV4", "DOMAIN"),
       "Sweep of the RFC1918 space from one segment", *_ATTACK),
    _t("T1135", "Network Share Discovery", "discovery", _R, ("IPV4",),
       "Share enumeration touching many hosts", *_ATTACK),
    _t("T1046", "Network Service Discovery", "discovery", _R, ("IPV4", "DOMAIN"),
       "Port sweep across more than a handful of hosts", *_ATTACK),
    # ── Lateral Movement ────────────────────────────────────────────
    _t("T1021", "Remote Services: SMB/Windows Admin Shares", "lateral_movement", _R,
       ("IPV4", "DOMAIN"), "Admin-share authentication to a peer workstation", *_ATTACK),
    _t("T1570", "Lateral Tool Transfer", "lateral_movement", _R, ("IPV4",),
       "Copy into a remote admin share followed by execution there", *_ATTACK),
    _t("T1550", "Use Alternate Authentication Material", "lateral_movement", _R,
       ("IPV4", "DOMAIN"), "Pass-the-hash style NTLM without a matching logon", *_ATTACK),
    # ── Collection ──────────────────────────────────────────────────
    _t("T1005", "Data from Local System", "collection", _R, ("IPV4", "DOMAIN"),
       "Bulk file read by a process with no prior read pattern", *_ATTACK),
    _t("T1074", "Email Collection", "collection", _R, ("EMAIL", "DOMAIN"),
       "Mailbox-access API outside the user's own client", *_ATTACK),
    _t("T1560", "Archive Collected Data", "collection", _R, ("IPV4",),
       "Archive utility run over a user or share directory", *_ATTACK),
    # ── Command and Control ─────────────────────────────────────────
    _t("T1071", "Application Layer Protocol", "command_and_control", _R, ("IPV4", "DOMAIN"),
       "Beaconing periodicity in proxy logs; rare-UA egress", *_ATTACK),
    _t("T1573", "Encrypted Channel", "command_and_control", _R, ("DOMAIN", "IPV4"),
       "TLS to an unregistered SNI, or a self-signed chain pinned by the client", *_ATTACK),
    _t("T1219", "Remote Access Software", "command_and_control", _R, ("IPV4",),
       "Known RASTool binary or its JA3 on an unusual port", *_ATTACK),
    _t("T1090", "Proxy", "command_and_control", _R, ("IPV4",),
       "Multi-hop egress with a single relay reused across sessions", *_ATTACK),
    # ── Exfiltration ────────────────────────────────────────────────
    _t("T1041", "Exfiltration Over C2 Channel", "exfiltration", _R, ("IPV4",),
       "Outbound volume on the same channel as command traffic", *_ATTACK),
    _t("T1567", "Exfiltration Over Web Service", "exfiltration", _R, ("DOMAIN", "IPV4"),
       "Large upload to a cloud-storage domain with no business justification", *_ATTACK),
    _t("T1048", "Exfiltration Over Alternative Protocol", "exfiltration", _R, ("IPV4",),
       "Outbound on a protocol with no matching service on the host", *_ATTACK),
    _t("T1030", "Data Transfer Size Limits", "exfiltration", _R, ("IPV4",),
       "Chunked transfer sized just under a proxy/DLP threshold", *_ATTACK),
    # ── Impact ──────────────────────────────────────────────────────
    _t("T1486", "Data Encrypted for Impact", "impact", _R, ("IPV4", "DOMAIN"),
       "Mass file rename + ransom-note drop", *_ATTACK),
    _t("T1490", "Inhibit System Recovery", "impact", _R, ("IPV4",),
       "Shadow-copy deletion / backup catalogue truncation", *_ATTACK),
    _t("T1489", "Service Stop", "impact", _R, ("IPV4",),
       "Security service stop event outside a maintenance window", *_ATTACK),
)

TECHNIQUES: tuple[Technique, ...] = tuple(sorted(_TECHNIQUES, key=lambda t: t.technique_id))

_TECHNIQUES_BY_ID = {t.technique_id: t for t in TECHNIQUES}


def all_techniques() -> tuple[Technique, ...]:
    """Every catalogued technique, id-sorted (deterministic)."""
    return TECHNIQUES


def technique(technique_id: str) -> Technique | None:
    return _TECHNIQUES_BY_ID.get(technique_id)


def techniques_for_tactic(tactic: str) -> tuple[Technique, ...]:
    """Techniques in one tactic, id-sorted."""
    return tuple(t for t in TECHNIQUES if t.tactic == tactic)


# ── Adversaries ────────────────────────────────────────────────────


@dataclass(frozen=True)
class Adversary:
    """A Caldera adversary profile (Apache-2.0), as a static record.

    ``plan_source`` names the donor whose emulation plan supplies the ability
    sequence. MITRE CTID AEL is the reference: its plans are published for use
    under prior explicit authorization, which is the same precondition this module
    enforces with the PAP gate.
    """

    adversary_id: str
    name: str
    description: str
    technique_ids: tuple[str, ...]
    plan_source: str
    license: str

    def as_dict(self) -> dict:
        return {
            "adversary_id": self.adversary_id,
            "name": self.name,
            "description": self.description,
            "technique_ids": list(self.technique_ids),
            "technique_count": len(self.technique_ids),
            "plan_source": self.plan_source,
            "license": self.license,
        }


_AEL = "donors/adversary_emulation_library (MITRE CTID AEL)"
_ATK = "Apache-2.0"

ADVERSARIES: tuple[Adversary, ...] = tuple(
    sorted(
        (
            Adversary(
                adversary_id="ael-apt29",
                name="APT29 emulation plan",
                description=(
                    "Full-plan emulation of a long-horizon state actor: workforce "
                    "credential phishing, web-shell staging, OAuth persistence and "
                    "low-and-slow C2."
                ),
                technique_ids=(
                    "T1589", "T1566", "T1190", "T1059", "T1505.003", "T1078",
                    "T1552", "T1558", "T1071", "T1573", "T1041", "T1560",
                ),
                plan_source=_AEL,
                license=_ATK,
            ),
            Adversary(
                adversary_id="ael-blind-eagle",
                name="Blind Eagle emulation plan",
                description=(
                    "Latin-American retail and banking intrusion chain: phishing to "
                    "VPN, credential theft, discovery and staged exfiltration."
                ),
                technique_ids=(
                    "T1566", "T1555", "T1110", "T1087", "T1018", "T1005",
                    "T1071", "T1041",
                ),
                plan_source=_AEL,
                license=_ATK,
            ),
            Adversary(
                adversary_id="ael-oceanlotus",
                name="OceanLotus emulation plan",
                description=(
                    "Long-dwell targeted intrusion: spearphishing, supply-chain "
                    "installer abuse and macro-delivered payloads."
                ),
                technique_ids=(
                    "T1566", "T1204", "T1059", "T1547", "T1027", "T1016",
                    "T1071", "T1041",
                ),
                plan_source=_AEL,
                license=_ATK,
            ),
            Adversary(
                adversary_id="micro-plan-compound",
                name="Compound micro-plan set",
                description=(
                    "The twelve cross-actor micro plans (enum, exfil, DLL sideload, "
                    "injection, webshell, registry, log clearing) used for targeted "
                    "detection validation rather than end-to-end adversary emulation."
                ),
                technique_ids=(
                    "T1087", "T1005", "T1041", "T1059", "T1057", "T1027",
                    "T1547", "T1070", "T1505.003", "T1204", "T1053",
                ),
                plan_source=_AEL,
                license=_ATK,
            ),
        ),
        key=lambda a: a.adversary_id,
    )
)

_ADVERSARIES_BY_ID = {a.adversary_id: a for a in ADVERSARIES}


def all_adversaries() -> tuple[Adversary, ...]:
    return ADVERSARIES


def adversary(adversary_id: str) -> Adversary | None:
    return _ADVERSARIES_BY_ID.get(adversary_id)


# ── Engagements ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class Engagement:
    """A named, authorized engagement with a PAP ceiling and a scope.

    ``pap_ceiling`` is the highest PAP level any technique may reach under this
    authorization. ``in_scope`` / ``out_of_scope`` are host or domain patterns;
    out-of-scope WINS on conflict (estorides `scope` semantics), so adding a host
    to both lists resolves to denied rather than to allowed.
    """

    engagement_id: str
    name: str
    client: str
    authorization_ref: str
    pap_ceiling: PapLevel
    in_scope: tuple[str, ...]
    out_of_scope: tuple[str, ...]
    status: str
    window_start: str
    window_end: str
    notes: str = ""

    def as_dict(self) -> dict:
        return {
            "engagement_id": self.engagement_id,
            "name": self.name,
            "client": self.client,
            "authorization_ref": self.authorization_ref,
            "pap_ceiling": self.pap_ceiling.name,
            "pap_ceiling_rank": int(self.pap_ceiling),
            "in_scope": list(self.in_scope),
            "out_of_scope": list(self.out_of_scope),
            "status": self.status,
            "window_start": self.window_start,
            "window_end": self.window_end,
            "notes": self.notes,
        }


ENGAGEMENTS: tuple[Engagement, ...] = tuple(
    sorted(
        (
            Engagement(
                engagement_id="ENG-2026-014",
                name="Northwind external validation",
                client="Northwind Group",
                authorization_ref="SOW-2026-014 · signed 2026-01-12",
                pap_ceiling=PapLevel.AMBER,
                in_scope=("northwind.example", "*.northwind.example"),
                out_of_scope=("mail.northwind.example", "*.gov", "*.health"),
                status="ACTIVE",
                window_start="2026-02-02",
                window_end="2026-02-27",
                notes=(
                    "Ceiling is AMBER: exploitation attempts and phishing simulation "
                    "permitted, execution inside the estate is not. Production mail "
                    "gateway is explicitly out of scope for delivery."
                ),
            ),
            Engagement(
                engagement_id="ENG-2026-021",
                name="Helix internal purple team",
                client="Helix Financial",
                authorization_ref="SOW-2026-021 · signed 2026-02-03",
                pap_ceiling=PapLevel.RED,
                in_scope=("lab.helix.example", "*.lab.helix.example"),
                out_of_scope=(),
                status="ACTIVE",
                window_start="2026-02-10",
                window_end="2026-03-06",
                notes=(
                    "Full-ceiling authorization confined to a purpose-built lab range. "
                    "The production estate is out of the engagement by construction."
                ),
            ),
            Engagement(
                engagement_id="ENG-2025-088",
                name="Atrium detection validation",
                client="Atrium Logistics",
                authorization_ref="SOW-2025-088 · closed 2025-12-19",
                pap_ceiling=PapLevel.GREEN,
                in_scope=("atrium.example",),
                out_of_scope=("*",),
                status="CLOSED",
                window_start="2025-11-24",
                window_end="2025-12-19",
                notes=(
                    "Detection-validation engagement with no active interaction "
                    "permitted. Out-of-scope `*` reflects a recon-only scope."
                ),
            ),
        ),
        key=lambda e: e.engagement_id,
    )
)

_ENGAGEMENTS_BY_ID = {e.engagement_id: e for e in ENGAGEMENTS}


def all_engagements() -> tuple[Engagement, ...]:
    return ENGAGEMENTS


def engagement(engagement_id: str) -> Engagement | None:
    return _ENGAGEMENTS_BY_ID.get(engagement_id)


# ── Operations ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class Operation:
    """One planned operation inside an engagement, bound to a kill-chain phase."""

    operation_id: str
    engagement_id: str
    name: str
    phase: str
    adversary_id: str
    technique_ids: tuple[str, ...]
    status: str
    objective: str

    def as_dict(self) -> dict:
        return {
            "operation_id": self.operation_id,
            "engagement_id": self.engagement_id,
            "name": self.name,
            "phase": self.phase,
            "adversary_id": self.adversary_id,
            "technique_ids": list(self.technique_ids),
            "technique_count": len(self.technique_ids),
            "status": self.status,
            "objective": self.objective,
        }


_OPERATIONS: tuple[Operation, ...] = (
    Operation(
        operation_id="OP-014-01",
        engagement_id="ENG-2026-014",
        name="Workforce credential pretext",
        phase="delivery",
        adversary_id="ael-apt29",
        technique_ids=("T1589", "T1566", "T1621"),
        status="PLANNED",
        objective=(
            "Measure MFA-push fatigue resistance across the finance and support "
            "org units using consented internal participants only."
        ),
    ),
    Operation(
        operation_id="OP-014-02",
        engagement_id="ENG-2026-014",
        name="Public-facing exposure sweep",
        phase="reconnaissance",
        adversary_id="micro-plan-compound",
        technique_ids=("T1595", "T1592", "T1590", "T1190"),
        status="RUNNING",
        objective=(
            "Confirm the AMBER ceiling blocks execution techniques while allowing "
            "active probing of in-scope hosts."
        ),
    ),
    Operation(
        operation_id="OP-014-03",
        engagement_id="ENG-2026-014",
        name="Lookalike domain monitoring",
        phase="reconnaissance",
        adversary_id="ael-apt29",
        technique_ids=("T1583", "T1596"),
        status="PLANNED",
        objective=(
            "Detect newly registered domains resolving near the Northwind brand."
        ),
    ),
    Operation(
        operation_id="OP-021-01",
        engagement_id="ENG-2026-021",
        name="Macro-delivered payload chain",
        phase="delivery",
        adversary_id="ael-oceanlotus",
        technique_ids=("T1204", "T1059", "T1547"),
        status="RUNNING",
        objective=(
            "Validate EDR coverage for macro-initiated execution against the "
            "lab range's synthetic fixtures."
        ),
    ),
    Operation(
        operation_id="OP-021-02",
        engagement_id="ENG-2026-021",
        name="Lateral movement detection",
        phase="actions_on_objectives",
        adversary_id="ael-blind-eagle",
        technique_ids=("T1087", "T1018", "T1021", "T1570"),
        status="PLANNED",
        objective=(
            "Confirm administrative-share authentication to lab peers raises the "
            "expected detections."
        ),
    ),
    Operation(
        operation_id="OP-021-03",
        engagement_id="ENG-2026-021",
        name="Exfiltration path rehearsal",
        phase="exfiltration",
        adversary_id="ael-apt29",
        technique_ids=("T1041", "T1567", "T1030"),
        status="PLANNED",
        objective=(
            "Exercise proxy DLP thresholds in the lab range so the chunked-transfer "
            "detection has a known-good baseline."
        ),
    ),
    Operation(
        operation_id="OP-088-01",
        engagement_id="ENG-2025-088",
        name="Passive exposure baseline",
        phase="reconnaissance",
        adversary_id="ael-blind-eagle",
        technique_ids=("T1592", "T1590", "T1597", "T1552"),
        status="COMPLETED",
        objective="Establish the green-ceiling baseline from public sources only.",
    ),
)

OPERATIONS: tuple[Operation, ...] = tuple(sorted(_OPERATIONS, key=lambda o: o.operation_id))

_OPERATIONS_BY_ID = {o.operation_id: o for o in OPERATIONS}


def all_operations() -> tuple[Operation, ...]:
    return OPERATIONS


def operation(operation_id: str) -> Operation | None:
    return _OPERATIONS_BY_ID.get(operation_id)


def operations_for(engagement_id: str) -> tuple[Operation, ...]:
    """Operations belonging to one engagement, phase-ordered then id-ordered."""
    return tuple(
        sorted(
            (o for o in OPERATIONS if o.engagement_id == engagement_id),
            key=lambda o: (int(_PHASES_BY_KEY[o.phase].ordinal), o.operation_id),
        )
    )


# ── The gate ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class GateDecision:
    """Result of an authorization check. `allowed` is never inferred from the rest."""

    allowed: bool
    reason_code: str
    reason: str
    required_pap: str
    ceiling_pap: str

    def as_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "reason_code": self.reason_code,
            "reason": self.reason,
            "required_pap": self.required_pap,
            "ceiling_pap": self.ceiling_pap,
        }


#: Engagement states in which nothing may be executed regardless of the ceiling.
_BLOCKING_STATUSES = frozenset({"CLOSED", "SUSPENDED"})


def _matches(pattern: str, host: str) -> bool:
    """Glob match restricted to one leading wildcard segment.

    Deliberately narrower than fnmatch: a scope pattern is a host authorization,
    and ``*`` must not be allowed to span a dot and silently widen a scope to every
    subdomain tree. ``*.example`` matches ``a.example`` and ``a.b.example``;
    ``*`` alone matches only a bare single-label host.
    """
    if pattern == host:
        return True
    if pattern.startswith("*."):
        return host.endswith(pattern[1:])
    return False


def gate_technique(eng: Engagement, tech: Technique) -> GateDecision:
    """PAP + engagement-state check for one technique. No scope check here.

    Scope is host-dependent and belongs to :func:`gate_execution`, which has the
    target in hand. Splitting them keeps the ceiling check answerable for a whole
    plan without a target — which is what the coverage matrix needs.
    """
    if eng.status in _BLOCKING_STATUSES:
        return GateDecision(
            allowed=False,
            reason_code="engagement_not_active",
            reason=f"engagement {eng.engagement_id} is {eng.status}; nothing is executable",
            required_pap=tech.pap_min.name,
            ceiling_pap=eng.pap_ceiling.name,
        )
    if tech.pap_min > eng.pap_ceiling:
        return GateDecision(
            allowed=False,
            reason_code="pap_ceiling_exceeded",
            reason=(
                f"{tech.technique_id} requires PAP {tech.pap_min.name}; "
                f"{eng.engagement_id} is authorized to {eng.pap_ceiling.name}"
            ),
            required_pap=tech.pap_min.name,
            ceiling_pap=eng.pap_ceiling.name,
        )
    return GateDecision(
        allowed=True,
        reason_code="authorized",
        reason=f"{tech.technique_id} is within the {eng.pap_ceiling.name} ceiling",
        required_pap=tech.pap_min.name,
        ceiling_pap=eng.pap_ceiling.name,
    )


def gate_execution(eng: Engagement, tech: Technique, target_host: str) -> GateDecision:
    """Full gate: engagement state, PAP ceiling, then scope with out-of-scope-wins."""
    decision = gate_technique(eng, tech)
    if not decision.allowed:
        return decision

    host = target_host.strip().lower()
    if not host:
        return GateDecision(
            allowed=False,
            reason_code="target_required",
            reason=f"{tech.technique_id} needs a target host to be scope-checked",
            required_pap=tech.pap_min.name,
            ceiling_pap=eng.pap_ceiling.name,
        )

    for pattern in eng.out_of_scope:
        if _matches(pattern.lower(), host):
            return GateDecision(
                allowed=False,
                reason_code="out_of_scope",
                reason=f"{host} matches out-of-scope pattern {pattern!r} (out-of-scope wins)",
                required_pap=tech.pap_min.name,
                ceiling_pap=eng.pap_ceiling.name,
            )
    if not any(_matches(p.lower(), host) for p in eng.in_scope):
        return GateDecision(
            allowed=False,
            reason_code="not_in_scope",
            reason=f"{host} matches no in-scope pattern of {eng.engagement_id}",
            required_pap=tech.pap_min.name,
            ceiling_pap=eng.pap_ceiling.name,
        )
    return GateDecision(
        allowed=True,
        reason_code="authorized",
        reason=f"{tech.technique_id} → {host} is in scope and within {eng.pap_ceiling.name}",
        required_pap=tech.pap_min.name,
        ceiling_pap=eng.pap_ceiling.name,
    )


# ── Coverage ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class TacticCoverage:
    """Per-tactic planability for one engagement."""

    tactic: str
    total: int
    authorized: int
    gated: int
    plannable_from_osint: int

    def as_dict(self) -> dict:
        return {
            "tactic": self.tactic,
            "total": self.total,
            "authorized": self.authorized,
            "gated": self.gated,
            "plannable_from_osint": self.plannable_from_osint,
        }


def coverage(eng: Engagement) -> tuple[TacticCoverage, ...]:
    """Per-tactic coverage for an engagement, in TACTIC_ORDER.

    ``authorized`` counts techniques the PAP ceiling permits. ``plannable_from_osint``
    counts those whose ``osint_inputs`` are non-empty — i.e. which this platform's
    evidence base can actually reach. The gap between the two is the interesting
    number: a technique can be perfectly authorized and still unplannable because
    the OSINT core never produced the entities it consumes.
    """
    rows: list[TacticCoverage] = []
    for tactic in TACTIC_ORDER:
        techs = techniques_for_tactic(tactic)
        authorized = [t for t in techs if gate_technique(eng, t).allowed]
        rows.append(
            TacticCoverage(
                tactic=tactic,
                total=len(techs),
                authorized=len(authorized),
                gated=len(techs) - len(authorized),
                plannable_from_osint=sum(1 for t in authorized if t.osint_inputs),
            )
        )
    return tuple(rows)


def coverage_summary(eng: Engagement) -> dict:
    """Headline numbers for the console header. Sums the per-tactic rows."""
    rows = coverage(eng)
    total = sum(r.total for r in rows)
    authorized = sum(r.authorized for r in rows)
    return {
        "engagement_id": eng.engagement_id,
        "pap_ceiling": eng.pap_ceiling.name,
        "techniques_total": total,
        "techniques_authorized": authorized,
        "techniques_gated": total - authorized,
        "techniques_plannable_from_osint": sum(r.plannable_from_osint for r in rows),
        "tactics_fully_authorized": sum(1 for r in rows if r.authorized == r.total),
        "tactics_fully_gated": sum(1 for r in rows if r.authorized == 0),
    }


def unplannable(eng: Engagement) -> tuple[Technique, ...]:
    """Authorized techniques this platform cannot yet plan from OSINT evidence.

    The exclusion is ``osint_inputs`` being empty, not a missing adapter: every
    non-empty input names an entity type the OSINT core already produces, so these
    are the techniques that need an acquisition source, not engineering.
    """
    return tuple(
        sorted(
            (t for t in TECHNIQUES if gate_technique(eng, t).allowed and not t.osint_inputs),
            key=lambda t: t.technique_id,
        )
    )
