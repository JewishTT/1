"""Ontology registry: the twelve declared entity types, and field→type resolution.

Why this module exists
----------------------
A structured record is a flat object with *typed fields*, and the platform was reading it
with a string heuristic: a value in a name-ish field became a person. So
``{"registrar": "Gazprom Neft", "domain": "gazprom-neft.ru", "asn": 12345}`` produced a
**person** named "Gazprom Neft" and silently dropped the ``asn``.

That is the §0.2 failure in its most ordinary form: a company was destroyed as a company by
losing its type, and a number that identifies a network was lost entirely. Both are worse
than an untyped mention, because the wrong type looks like knowledge.

What this module does
---------------------
1. Declares the twelve types (025 Appendix C / the owner's list) with the invariants that
   make them checkable rather than decorative.
2. Maps field names to types with a *declared, ordered* table, so ``registrar`` resolves to
   ``organization`` because the table says so, not because the string looked like a name.
3. Never coerces. An unmapped field yields ``UNKNOWN`` with the raw value preserved, which
   P11 requires: semantic uncertainty must not reduce structural observability.

Deliberate non-goals
--------------------
- It does not resolve identity, merge entities, or admit anything (P02, P12).
- It does not drop a value because its type is unknown. ``UNKNOWN`` is a first-class answer.
- It is pure domain: no IO, no settings, no clock. Deterministic and replayable.
"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass, replace
from typing import Any


class EntityType(str, enum.Enum):
    """The declared entity types. Nothing outside this enum may reach the world model.

    This enum is the **single authority** for entity typing. Eight disjoint vocabularies
    existed before it was given that role: this one, ``OntologyPack.entity_types``, the
    FollowTheMoney ``DEFAULT_REGISTRY``, ``document_adapter.TYPE_REFS``, the
    ``tool_catalog`` uppercase labels, ``RelationSchema.allowed_*_classes``, an
    ``ontology_packs`` JSONB column with no writer, and the webapp's own TypeScript union.
    The same concept was spelled five ways -- ``Website``/``WebSite``,
    ``Organization``/``Organisation``, ``crypto``/``ADDRESS`` -- and the Postgres columns
    carried no constraint at all, so a row could hold any string.

    Concretely: ``contacts.py`` emits ``ip`` and ``crypto`` mentions,
    ``document_adapter.TYPE_REFS`` has no entry for either, and the adapter drops them.
    Those two kinds existed in the pipeline and were discarded before persistence. That is
    the class of loss a single authority prevents.

    ``DOCUMENT`` remains here because a document *can* be a subject of a claim ("this
    document mentions X"). What kind of document it is -- text, image, log -- is
    :class:`StaticArtifactKind`, a separate axis. Conflating the two made ``content_type``
    and ``entity_type`` compete for the same column.
    """

    # -- things the world is made of ----------------------------------------
    PERSON = "person"
    ORGANIZATION = "organization"
    DOMAIN = "domain"
    SUBDOMAIN = "subdomain"
    WEBSITE = "website"
    PLACE = "place"
    EMAIL = "email"
    PHONE = "phone"
    HANDLE = "handle"
    IP = "ip"
    CRYPTO = "crypto"
    IDENTIFIER = "identifier"
    DOCUMENT = "document"
    UNKNOWN = "unknown"

    # -- infrastructure -----------------------------------------------------
    #: An autonomous system. Kept separate from ``ORGANIZATION``: Cloudflare's AS13335 and
    #: Cloudflare, Inc. are different claims about the world, and a BGP graph collapses them
    #: if one stands for the other. 26 of the 145 sources declare ``asn``.
    ASN = "asn"
    ISP = "isp"
    PREFIX = "prefix"
    NETWORK = "network"
    PORT = "port"
    NAMESERVER = "nameserver"
    REGISTRAR = "registrar"
    MAC_ADDRESS = "mac_address"
    BSSID = "bssid"
    CERTIFICATE = "certificate"
    CPE = "cpe"
    TECHNOLOGY = "technology"
    VENDOR = "vendor"
    REPOSITORY = "repository"
    SERVICE = "service"
    PLATFORM = "platform"

    # -- vulnerability and threat ------------------------------------------
    CVE = "cve"
    EXPLOIT = "exploit"
    MALWARE = "malware"
    THREAT_ACTOR = "threat_actor"
    SIGNATURE = "signature"
    IOC = "indicator"

    # -- breach and leak ---------------------------------------------------
    LEAK = "leak"
    BREACH = "breach"
    SECRET = "secret"
    CREDENTIAL = "credential"

    # -- scholarly and reference -------------------------------------------
    ARTICLE = "article"
    AUTHOR = "author"
    DOI = "doi"
    ORCID = "orcid"

    # -- social and community ----------------------------------------------
    SUBREDDIT = "subreddit"
    CHANNEL = "channel"
    REPUTATION = "reputation"

    # -- physical and spatial ----------------------------------------------
    VESSEL = "vessel"
    AIRCRAFT = "aircraft"
    SATELLITE = "satellite"
    GEOLOCATION = "geolocation"
    COUNTRY = "country"

    # -- hashes -------------------------------------------------------------
    HASH = "hash"
    #: ``SCORE``, ``AMOUNT`` and ``COUNT`` are deliberately absent. They are measurements a
    #: claim carries -- a CVSS base score, a wallet balance, a pwn count -- not things in the
    #: world, and putting them here would let a scope lattice claim a number inherits
    #: ``Thing``. They live on ``ValueKind`` instead, and
    #: ``test_value_kinds_are_not_entity_types`` pins the two axes disjoint.


#: The kinds a parsed field can be that are *not* entities.
#:
#: A separate axis, and the reason it exists: ``timestamp`` and ``description`` appeared 99
#: times across the 145 source declarations, and neither is a thing in the world -- they are
#: values a claim carries. Adding them to :class:`EntityType` would have let a scope lattice
#: claim a timestamp is an entity with an ``ASN`` parent, and would have written
#: ``entity_type='timestamp'`` into a column that means "what kind of thing is this".
#:
#: Parsed fields land on exactly one of the two axes, decided by :data:`FIELD_AXIS`.
class ValueKind(str, enum.Enum):
    """A value on a claim, rather than a thing the claim is about."""

    TIMESTAMP = "timestamp"
    DESCRIPTION = "description"
    STATUS = "status"
    TAG = "tag"
    LANGUAGE = "language"
    TITLE = "title"
    URL = "url"
    SCORE = "score"
    AMOUNT = "amount"
    COUNT = "integer"
    CATEGORY = "category"
    #: ``UNKNOWN`` is deliberately on both axes. It is not a kind of thing and not a kind of
    #: value; it is the absence of a classification, and a field can be unclassified on
    #: either side. :func:`axis_for` therefore returns ``"unknown"`` for it rather than
    #: picking one, and the disjointness test excludes it.
    UNKNOWN = "unknown"


#: Parser field kind -> the axis it belongs to.
#:
#: ``{"url", "timestamp", "description", "integer", "status", "tag", "language", "title",
#: "score", "amount", "category", "mimetype", "filetype", "signature"}`` land on
#: :class:`ValueKind`; everything else that is a known name lands on :class:`EntityType`.
#: An unknown name lands on neither and is carried as evidence -- see
#: :func:`axis_for`.
VALUE_KINDS: frozenset[str] = frozenset(v.value for v in ValueKind)


def axis_for(kind: str) -> str:
    """``"entity"``, ``"value"`` or ``"unknown"`` for one parsed field kind.

    The third answer is the load-bearing one. A source declaring a kind this ontology has
    never heard of has told us something about the world we cannot yet name, and the honest
    response is to carry the evidence and mark the kind unclassified -- not to promote it to
    an entity type and not to drop it. Promotion is what would let ``entity_type`` accept a
    string that means nothing; dropping is what loses the observation's content.
    """
    name = str(kind or "").strip().lower()
    if name in VALUE_KINDS:
        return "value"
    if name in {t.value for t in EntityType}:
        return "entity"
    return "unknown"


def value_kind_for(kind: str) -> ValueKind:
    """The :class:`ValueKind` a field kind denotes, or ``UNKNOWN``.

    Unknown rather than a default: a field declared ``timestamp`` and a field declared
    ``something-nobody-named`` are different facts, and the second must not be read as a
    timestamp.
    """
    return _VALUE_BY_NAME.get(str(kind or "").strip().lower(), ValueKind.UNKNOWN)


_VALUE_BY_NAME: dict[str, ValueKind] = {v.value: v for v in ValueKind}


#: Spellings the 145 sources use for kinds this ontology already has under another name.
#:
#: Every entry here was a live response being read as ``unknown`` and dropped at a
#: classification step. Kept explicit rather than guessed at read time so the mapping is one
#: table a reader can check, and so a new spelling fails visibly instead of quietly.
KIND_ALIASES: dict[str, str] = {
    "url": "url",
    "social_media_url": "url",
    "link": "url",
    "internal_url": "url",
    "cdn_endpoint": "url",
    "screenshot": "url",
    "image": "url",
    "logo": "url",
    "datetime": "timestamp",
    "last_seen": "timestamp",
    "first_seen": "timestamp",
    "last_online": "timestamp",
    "published": "timestamp",
    "gmt_offset": "timestamp",
    "eta": "timestamp",
    "abstract": "description",
    "summary": "description",
    "dek": "description",
    "extract": "description",
    "snippet": "description",
    "bio": "description",
    "biography": "description",
    "public_description": "description",
    "title": "description",
    "http_status": "status",
    "status_code": "status",
    "cache_status": "status",
    "access_level": "status",
    "classification": "reputation",
    "threat_type": "status",
    "abuse_category": "status",
    "keywords": "tag",
    "topics": "tag",
    "lang": "language",
    "filetype": "technology",
    "mimetype": "technology",
    "file_type": "technology",
    "cloud_bucket": "repository",
    "bucket": "repository",
    "gist": "repository",
    "paste": "leak",
    "paste_id": "leak",
    "breach_name": "breach",
    "yara": "signature",
    "indicator": "indicator",
    "ioc": "indicator",
    "btc_address": "crypto",
    "eth_address": "crypto",
    "token": "crypto",
    "username": "handle",
    "telegram_handle": "handle",
    "fediverse_handle": "handle",
    "text": "unknown",
    "txt_record": "unknown",
    "ipv4": "ip",
    "ipv6": "ip",
    "address": "address",
    "inetnum": "network",
    "org": "organization",
    "issuer": "organization",
    "tls_issuer": "organization",
    "registrant": "organization",
    "institution": "organization",
    "abuse_contact": "organization",
    "maintainer": "person",
    "actor": "threat_actor",
    "attacker": "threat_actor",
    "author": "author",
    "reporter": "person",
    "owner": "organization",
    "community": "organization",
    "server": "service",
    "mail_server": "service",
    "product": "technology",
    "device": "technology",
    "code": "technology",
    "exploit": "exploit",
    "vulnerability": "cve",
    "edb_id": "exploit",
    "ghsa": "cve",
    "cvss": "score",
    "confidence": "score",
    "karma": "score",
    "match_count": "count",
    "pwn_count": "count",
    "subscriber_count": "count",
    "work_count": "count",
    "tx_count": "count",
    "total_received": "amount",
    "balance": "amount",
    "value": "amount",
    "input": "amount",
    "output": "amount",
    "currency": "amount",
    "malware_family": "malware",
    "malicious": "malware",
    "threat_actor_type": "threat_actor",
    "type": "status",
    "category": "category",
    "work": "article",
    "paper": "article",
    "citation": "article",
    "references": "article",
    "submission": "article",
    "post": "article",
    "location": "place",
    "position": "geolocation",
    "gps": "geolocation",
    "exif": "geolocation",
    "og_metadata": "description",
    "metadata": "description",
    "selector": "email",
    "mac_prefix": "mac_address",
    "mail_server_address": "domain",
    "asn_hop": "asn",
    "registration": "identifier",
    "norad_id": "identifier",
    "mmsi": "identifier",
    "sha1_fingerprint": "hash",
    "sha256": "hash",
    "md5": "hash",
    "username_key": "handle",
    "screenshot_url": "url",
    "arctic": "unknown",
    # Left in the alias table only to say "this is a spelling we have seen and do not
    # classify". Every entry below is a name a source declared that is genuinely not a
    # thing in the world or not a claim about one -- a boolean, a count, a state name, a
    # descriptive phrase. Mapping them to ``unknown`` is not a gap; it is the correct
    # classification, and leaving them out would make ``unknown`` look like an oversight.
    "address": "address",
    "password": "credential",
    "keyword": "keyword",
    "public_key": "crypto",
    "social_proof": "social_media_url",
    "instance": "service",
    "board": "channel",
    "account_age": "timestamp",
    "blog": "url",
    "gravatar": "url",
    "pulse": "pulse",
    "attack_type": "attack_type",
    "brand": "organization",
    "target": "target",
    "phish_id": "identifier",
    "in_database": "in_database",
    "verified": "verified",
    "name": "name",
    "breach_date": "timestamp",
    "pwn_count": "count",
    "data_classes": "data_classes",
    "paste_source": "leak",
    "state": "status",
    "timezone": "timezone",
    "dst": "dst",
}


def classify_kind(kind: str) -> EntityType | None:
    """The entity type a source field kind denotes, or ``None`` if it is not an entity.

    ``None`` is returned for value kinds and for unknown kinds alike -- but
    :func:`axis_for` distinguishes those two, and a caller that cares must ask. This
    function's answer is only about entities.
    """
    name = KIND_ALIASES.get(str(kind or "").strip().lower(), str(kind or "").strip().lower())
    if axis_for(name) != "entity":
        return None
    return coerce_entity_type(name)


class StaticArtifactKind(str, enum.Enum):
    """What *kind of thing* a static artifact is (§0.2 "static objects are evidence").

    The owner asked specifically for document / text / photograph / log. These are the
    kinds the parsers can actually produce or refuse, so the vocabulary is drawn from the
    adapters rather than from imagination -- an artifact kind nothing can produce is a lie
    the UI would eventually offer.

    The axis is deliberately orthogonal to :class:`EntityType`. An ``image/jpeg`` is a
    ``StaticArtifactKind.PHOTO``; a ``Person`` extracted from a PDF is an
    ``EntityType.PERSON``. One artifact can yield many entities, and one entity can be
    evidenced by many artifacts, so collapsing the axes loses a real relation.
    """

    DOCUMENT = "document"
    TEXT = "text"
    MARKUP = "markup"
    PHOTO = "photo"
    LOG = "log"
    SPREADSHEET = "spreadsheet"
    STRUCTURED = "structured"
    ARCHIVE = "archive"
    BINARY = "binary"
    UNKNOWN = "unknown"


#: Media type prefix -> artifact kind. Prefix matching rather than a full table because the
#: parsers dispatch on ``type/subtype`` families (``parsers/documents.py:30-36``,
#: ``parsers/plaintext.py:34``), and a full table would drift from them on every addition.
MEDIA_KIND_PREFIXES: tuple[tuple[str, StaticArtifactKind], ...] = (
    ("application/pdf", StaticArtifactKind.DOCUMENT),
    ("application/msword", StaticArtifactKind.DOCUMENT),
    ("application/vnd.", StaticArtifactKind.DOCUMENT),
    ("application/vnd.openxmlformats-officedocument", StaticArtifactKind.DOCUMENT),
    ("application/zip", StaticArtifactKind.ARCHIVE),
    ("image/", StaticArtifactKind.PHOTO),
    ("text/html", StaticArtifactKind.MARKUP),
    ("application/xhtml", StaticArtifactKind.MARKUP),
    ("text/xml", StaticArtifactKind.MARKUP),
    ("application/xml", StaticArtifactKind.STRUCTURED),
    ("application/rss", StaticArtifactKind.STRUCTURED),
    ("application/atom", StaticArtifactKind.STRUCTURED),
    ("application/json", StaticArtifactKind.STRUCTURED),
    ("text/csv", StaticArtifactKind.SPREADSHEET),
    ("text/log", StaticArtifactKind.LOG),
    ("text/", StaticArtifactKind.TEXT),
    ("application/octet-stream", StaticArtifactKind.BINARY),
)


def kind_of_media_type(media_type: str) -> StaticArtifactKind:
    """Classify a content type into an artifact kind.

    Falls back to ``UNKNOWN`` rather than to ``TEXT``. A mis-typed artifact that reads as
    text is worse than one whose kind nobody established: the first silently loses
    everything not decodable as characters, and nothing reports that it happened.
    """
    value = str(media_type or "").split(";", 1)[0].strip().lower()
    if not value:
        return StaticArtifactKind.UNKNOWN
    for prefix, kind in MEDIA_KIND_PREFIXES:
        if value.startswith(prefix):
            return kind
    return StaticArtifactKind.UNKNOWN


def coerce_entity_type(value: str) -> EntityType:
    """Resolve an arbitrary spelling to an :class:`EntityType`, or ``UNKNOWN``.

    Accepts the aliases the historical vocabularies used, because those spellings are in
    stored rows and in the webapp's payloads. Rejecting them would orphan every entity
    typed before this enum became the authority; keeping them makes the consolidation a
    migration rather than a data loss.
    """
    text = str(value or "").strip().lower()
    if not text:
        return EntityType.UNKNOWN
    direct = {member.value: member for member in EntityType}
    if text in direct:
        return direct[text]
    # Historical spellings, keyed to the member they actually meant.
    #
    # ``address`` is deliberately absent. It was listed twice -- once as ``PLACE`` and once
    # as ``CRYPTO`` -- and the second silently won, so a postal address would have been
    # typed as a crypto wallet. The spelling is genuinely ambiguous across the vocabularies
    # being consolidated, and an ambiguous alias resolves to ``UNKNOWN`` rather than to
    # whichever meaning happened to be written last.
    aliases = {
        "organisation": EntityType.ORGANIZATION,
        "company": EntityType.ORGANIZATION,
        "org": EntityType.ORGANIZATION,
        "legalentity": EntityType.ORGANIZATION,
        "name": EntityType.PERSON,
        "person": EntityType.PERSON,
        "website": EntityType.WEBSITE,
        "web_site": EntityType.WEBSITE,
        "url": EntityType.WEBSITE,
        "location": EntityType.PLACE,
        "geowebentityfeature": EntityType.PLACE,
        "administrativearea": EntityType.PLACE,
        "contactpoint": EntityType.EMAIL,
        "onlineaccount": EntityType.HANDLE,
        "username": EntityType.HANDLE,
        "useraccount": EntityType.HANDLE,
        "user_account": EntityType.HANDLE,
        "ip_address": EntityType.IP,
        "ipv4": EntityType.IP,
        "ipv6": EntityType.IP,
        "crypto": EntityType.CRYPTO,
        "crypto_address": EntityType.CRYPTO,
        "cryptoaddress": EntityType.CRYPTO,
        "id_number": EntityType.IDENTIFIER,
        "identifier": EntityType.IDENTIFIER,
        "account": EntityType.HANDLE,
        "entity": EntityType.UNKNOWN,
        "": EntityType.UNKNOWN,
    }
    return aliases.get(text, EntityType.UNKNOWN)


#: Types that may be asserted about a natural person. Used by the inference policy gate
#: (025 §49.3) — attributing control to a named person is a sensitive class.
NATURAL_PERSON_TYPES = frozenset({EntityType.PERSON})

#: Values that are not entities in their own right and must be attached to one.
DEPENDENT_TYPES = frozenset({EntityType.EMAIL, EntityType.PHONE, EntityType.HANDLE})

# --- field → type ------------------------------------------------------------

# Ordered: the first matching key wins. Order is significant and declared, because
# ``name`` matches too broadly to lead and ``registrar`` must beat it.
FIELD_TYPE_MAP: tuple[tuple[str, EntityType], ...] = (
    # organisation-ish first: these are the fields that were being misread as people
    ("registrar", EntityType.ORGANIZATION),
    ("registrant", EntityType.ORGANIZATION),
    ("company", EntityType.ORGANIZATION),
    ("organization", EntityType.ORGANIZATION),
    ("organisation", EntityType.ORGANIZATION),
    ("publisher", EntityType.ORGANIZATION),
    ("owner_org", EntityType.ORGANIZATION),
    ("holder_org", EntityType.ORGANIZATION),
    ("brand", EntityType.ORGANIZATION),
    ("agency", EntityType.ORGANIZATION),
    # people
    ("person", EntityType.PERSON),
    ("director", EntityType.PERSON),
    ("officer", EntityType.PERSON),
    ("beneficiary", EntityType.PERSON),
    ("owner_person", EntityType.PERSON),
    ("holder_person", EntityType.PERSON),
    ("first_name", EntityType.PERSON),
    ("last_name", EntityType.PERSON),
    ("full_name", EntityType.PERSON),
    # network / address
    ("domain", EntityType.DOMAIN),
    ("hostname", EntityType.DOMAIN),
    ("domain_name", EntityType.DOMAIN),
    ("website", EntityType.WEBSITE),
    ("url", EntityType.WEBSITE),
    ("homepage", EntityType.WEBSITE),
    ("ip", EntityType.IP),
    ("ip_address", EntityType.IP),
    ("asn", EntityType.IDENTIFIER),
    ("lei", EntityType.IDENTIFIER),
    ("inn", EntityType.IDENTIFIER),
    ("ogrn", EntityType.IDENTIFIER),
    ("ticker", EntityType.IDENTIFIER),
    ("registration_number", EntityType.IDENTIFIER),
    ("registry", EntityType.IDENTIFIER),
    ("id", EntityType.IDENTIFIER),
    ("identifier", EntityType.IDENTIFIER),
    # contact
    ("email", EntityType.EMAIL),
    ("mail", EntityType.EMAIL),
    ("phone", EntityType.PHONE),
    ("telephone", EntityType.PHONE),
    ("handle", EntityType.HANDLE),
    ("nickname", EntityType.HANDLE),
    ("username", EntityType.HANDLE),
    # crypto
    ("wallet", EntityType.CRYPTO),
    ("wallet_address", EntityType.CRYPTO),
    ("address", EntityType.CRYPTO),
    ("crypto_address", EntityType.CRYPTO),
    ("tx_hash", EntityType.CRYPTO),
    # place
    ("country", EntityType.PLACE),
    ("city", EntityType.PLACE),
    ("region", EntityType.PLACE),
    ("locality", EntityType.PLACE),
    ("address_locality", EntityType.PLACE),
    ("place", EntityType.PLACE),
    # document
    ("document", EntityType.DOCUMENT),
    ("doc_id", EntityType.DOCUMENT),
    ("filing", EntityType.DOCUMENT),
)

_FIELD_INDEX: dict[str, EntityType] = {k: v for k, v in FIELD_TYPE_MAP}

# --- value validation -------------------------------------------------------

_DOMAIN_RE = re.compile(r"^(?=.{4,253}$)(?!-)[a-z0-9-]{1,63}(?<!-)(\.(?!-)[a-z0-9-]{1,63}(?<!-))+$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$")
_IPV4_RE = re.compile(r"^(\d{1,3}\.){3}\d{1,3}$")
_CRYPTO_RE = re.compile(
    r"^(0x)?[0-9a-fA-F]{40}$"          # EVM
    r"|^[13][a-km-zA-HJ-NP-Z1-9]{25,34}$"   # bech32 / base58
    r"|^bc1[0-9ac-hj-np-z]{11,71}$"         # bech32m segwit
)
_HANDLE_RE = re.compile(r"^@?[A-Za-z0-9_]{2,32}$")


@dataclass(frozen=True, slots=True)
class FieldReading:
    """One value read from a structured record, with its declared type.

    ``value_kept`` is true when the raw value survived even though the type is
    ``UNKNOWN``. That is the P11 guarantee: the signal is preserved, the semantics are not
    invented.
    """

    field: str
    raw_value: Any
    value: str
    type: EntityType
    declared: bool
    """True when the type came from the field table; False when it is UNKNOWN."""
    value_kept: bool

    def as_dict(self) -> dict:
        return {
            "field": self.field,
            "value": self.value,
            "type": self.type.value,
            "declared": self.declared,
            "value_kept": self.value_kept,
        }


def type_for_field(field: str) -> EntityType:
    return _FIELD_INDEX.get(field.strip().lower(), EntityType.UNKNOWN)


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return ""
    if isinstance(value, (int, float)):
        return repr(value) if isinstance(value, float) else str(value)
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (list, tuple)):
        return ", ".join(_stringify(v) for v in value if _stringify(v))
    if isinstance(value, dict):
        # A nested object is not a scalar identifier; keeping its repr would invent a value.
        return ""
    return ""


def validate(value: str, etype: EntityType) -> bool:
    """Shape check for the types where a wrong shape is detectable.

    A False here does NOT drop the reading: it downgrades confidence and is recorded. It
    never rewrites the type, because "this does not look like an email" is a reason to doubt
    the source, not a reason to re-label the field.
    """
    v = value.strip()
    if not v:
        return False
    if etype is EntityType.DOMAIN:
        return bool(_DOMAIN_RE.match(v.lower()))
    if etype is EntityType.EMAIL:
        return bool(_EMAIL_RE.match(v))
    if etype is EntityType.IP:
        return bool(_IPV4_RE.match(v))
    if etype is EntityType.CRYPTO:
        return bool(_CRYPTO_RE.match(v))
    if etype is EntityType.HANDLE:
        return bool(_HANDLE_RE.match(v.lstrip("@")))
    if etype is EntityType.IDENTIFIER:
        return True
    return True


def read_field(field: str, raw_value: Any) -> FieldReading | None:
    """Read one field. Returns None only when there is no value at all."""
    value = _stringify(raw_value)
    if not value:
        return None
    etype = type_for_field(field)
    declared = etype is not EntityType.UNKNOWN
    return FieldReading(
        field=field,
        raw_value=raw_value,
        value=value,
        type=etype,
        declared=declared,
        value_kept=True,
    )


def read_record(record: dict, *, prefix: str = "") -> tuple[FieldReading, ...]:
    """Read every field of a flat structured record.

    Nested objects are descended one level so ``{"address": {"city": "..."}}`` yields a
    place rather than being dropped; deeper nesting is not descended, because a value three
    levels down is no longer an identifier and flattening it would invent one.

    The reported ``field`` keeps the full dotted path (``address.postcode``). Without it a
    nested ``address.postcode`` and a top-level ``postcode`` are indistinguishable, and
    "which field was this" becomes unanswerable at exactly the point someone needs it.
    Type resolution still uses the leaf name, because that is what the table declares.
    """
    out: list[FieldReading] = []
    for key, value in record.items():
        field = str(key)
        reading = read_field(field, value)
        if reading is not None:
            if prefix:
                reading = replace(reading, field=f"{prefix}{field}")
            out.append(reading)
            continue
        if isinstance(value, dict):
            out.extend(read_record(value, prefix=f"{prefix}{field}."))
    return tuple(out)


def typed_mentions(record: dict) -> tuple[tuple[str, str], ...]:
    """``(type, value)`` pairs for everything the record declares.

    This is the shape the extraction layer consumes. Unknown-typed values are returned with
    ``unknown`` rather than omitted — the caller decides what to do with an untyped value,
    and it cannot decide on something it never received.
    """
    return tuple(
        (r.type.value, r.value)
        for r in read_record(record)
        if r.type is not EntityType.UNKNOWN
    )


def untyped_values(record: dict) -> tuple[FieldReading, ...]:
    """Values whose type could not be declared. Reported, never discarded."""
    return tuple(r for r in read_record(record) if r.type is EntityType.UNKNOWN)


__all__ = [
    "EntityType",
    "ValueKind",
    "VALUE_KINDS",
    "KIND_ALIASES",
    "axis_for",
    "classify_kind",
    "value_kind_for",
    "FieldReading",
    "FIELD_TYPE_MAP",
    "NATURAL_PERSON_TYPES",
    "DEPENDENT_TYPES",
    "type_for_field",
    "validate",
    "read_field",
    "read_record",
    "typed_mentions",
    "untyped_values",
    "StaticArtifactKind",
    "MEDIA_KIND_PREFIXES",
    "kind_of_media_type",
    "coerce_entity_type",
    "ENTITY_TYPE_SCHEMA",
    "schema_for",
    "entity_type_for",
    "type_closure_for",
    "is_subtype_of",
]


#: ``EntityType`` -> the FollowTheMoney schema it is stored as.
#:
#: Two vocabularies meet here on purpose. ``EntityType`` is the *narrow* one the platform
#: reasons with -- it is what a filter matches on and what the DB constrains -- while the
#: schema registry carries the *hierarchy* those types sit in. Before this map existed the
#: eight registries disagreed about spelling and nothing connected them, so a type could not
#: be checked against anything.
#:
#: Several ``EntityType`` members map to the same schema on purpose: ``DOMAIN`` and
#: ``WEBSITE`` are both FTM ``Document``/``Thing``-shaped for validation purposes, and
#: keeping them apart is the platform's business, not the schema's.
ENTITY_TYPE_SCHEMA: dict[EntityType, str] = {
    EntityType.PERSON: "Person",
    EntityType.ORGANIZATION: "Organization",
    EntityType.DOMAIN: "Document",
    EntityType.WEBSITE: "Document",
    EntityType.PLACE: "Location",
    EntityType.EMAIL: "Email",
    EntityType.PHONE: "Phone",
    EntityType.HANDLE: "UserAccount",
    EntityType.IP: "Thing",
    EntityType.CRYPTO: "CryptoAddress",
    EntityType.IDENTIFIER: "Thing",
    EntityType.DOCUMENT: "Document",
    EntityType.UNKNOWN: "Thing",
}

#: The inverse. Several types may map to one schema, so the first registrant wins and the
#: rest stay reachable through ``ENTITY_TYPE_SCHEMA``.
_SCHEMA_ENTITY_TYPE: dict[str, EntityType] = {}
for _entity_type, _schema in ENTITY_TYPE_SCHEMA.items():
    _SCHEMA_ENTITY_TYPE.setdefault(_schema, _entity_type)


def schema_for(entity_type: EntityType | str) -> str:
    """The schema an entity type is stored as, or ``"Thing"`` when unresolved.

    Falls back to ``Thing`` rather than raising: an unknown type is a gap in vocabulary,
    not a reason to refuse the entity. Refusing would lose the referent, and the referent
    is the one thing the platform must never lose.
    """
    resolved = coerce_entity_type(str(getattr(entity_type, "value", entity_type)))
    return ENTITY_TYPE_SCHEMA.get(resolved, "Thing")


def entity_type_for(schema_name: str) -> EntityType:
    """The narrow type a stored schema corresponds to, or ``UNKNOWN``."""
    return _SCHEMA_ENTITY_TYPE.get(str(schema_name), EntityType.UNKNOWN)


def type_closure_for(entity_type: EntityType | str) -> tuple[str, ...]:
    """The schema plus every supertype it inherits.

    This is the set a derived typing may assert. Empty input yields ``("Thing",)`` rather
    than an empty tuple: "we know nothing" still entails the root, and a caller receiving
    ``()`` has no valid type to store.
    """
    from domain.schema import DEFAULT_REGISTRY

    return DEFAULT_REGISTRY.type_closure(schema_for(entity_type))


def is_subtype_of(entity_type: EntityType | str, ancestor: str) -> bool:
    """Whether a stored type inherits from ``ancestor``, by way of the schema registry."""
    return ancestor in type_closure_for(entity_type)
