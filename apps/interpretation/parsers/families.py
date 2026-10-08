"""Declarative source parsing: six families, 145 definitions (spec 025 §33).

The catalogue declares 92 distinct ``parser:`` names and implements two. This module closes
that gap without writing 145 parsers, by noticing that a parser's job is determined by the
*shape of the response*, not by the endpoint: Shodan's ``hostnames`` and OpenAlex's
``authorships`` are both "walk a list, read named fields".

So a source names a **family** plus the paths it cares about, and this module does the rest.

**A family is a shape, not a vendor.** ``json_rows`` covers 84 sources across feeds, search
APIs, blockchain explorers and threat intel, because they all return a list of records under
some path. Keying on the shape is what keeps 145 integrations from becoming 145 code paths
that drift apart.

**An undeclared field is unresolved, never guessed.** ``resolve_path`` distinguishes a
missing path from a field the source reported as ``null``, because a schema change and an
empty result are different facts and collapsing them hides the first until someone notices
the second stopped arriving. Unresolved fields are counted and reported on
:class:`ParseOutcome`.

**Nothing is invented.** A family emits what it found. An IP-looking string in a field
declared ``country`` is carried through as ``country``, because deciding it is wrong is the
domain layer's job and this layer does not have the vocabulary to decide it. The one thing
this layer does insist on is that a value declared as a list is a list -- see
:class:`FieldSpec`.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from parsers.paths import MISSING, collect_path, resolve_path

__all__ = [
    "ALL_STATUSES",
    "FAMILIES",
    "LEGACY_FAMILIES",
    "FieldSpec",
    "ParseOutcome",
    "ParsedRecord",
    "SourceOutcome",
    "family_of",
    "parse_body",
    "parse_source",
]


@dataclass(frozen=True, slots=True)
class FieldSpec:
    """One declared field: where it is, and what kind of thing it should be.

    ``kind`` is the platform's own vocabulary (``domain``, ``ip``, ``asn``, ``person``,
    ``email`` ...). It is *not* validated against a schema here: an unknown kind is carried
    through so the domain layer can decide, which is the opposite of the document adapter's
    rule for unknown extractor kinds. The difference is deliberate and load-bearing -- there,
    an unknown kind means the extractor produced something the ontology has never seen and
    guessing a type would block a candidate; here, an unknown kind means the source declared
    a fact about the world the platform has not learned to name yet, and dropping it would
    lose evidence.

    ``many`` says the path yields a list rather than one value. Declaring ``many=False`` for
    a path that returns several is reported rather than silently taking the first: a source
    that changed its shape from one record per page to many is a real event.
    """

    name: str
    path: str
    kind: str = "unknown"
    many: bool = False
    required: bool = False
    #: Regex for the text families, compiled once at declaration time. Compiled here rather
    #: than at parse time so a bad pattern fails when the definition is read, not once per
    #: response -- and a spec without one takes the whole trimmed line.
    pattern: re.Pattern[str] | None = field(default=None, compare=False, repr=False)

    @classmethod
    def from_yaml(cls, raw: Mapping[str, Any] | str, name: str = "") -> FieldSpec:
        """Accept either ``{"name": ..., "path": ...}`` or the ``name: path`` shorthand."""
        if isinstance(raw, str):
            return cls(name=name, path=raw)
        pattern = raw.get("pattern") or raw.get("line_pattern")
        return cls(
            name=str(raw.get("name") or name),
            path=str(raw.get("path") or ""),
            kind=str(raw.get("kind") or "unknown"),
            many=bool(raw.get("many", False)),
            required=bool(raw.get("required", False)),
            pattern=_compile(pattern),
        )


def _compile(pattern: Any) -> re.Pattern[str] | None:
    """Accept a regex as text or as an already-compiled pattern.

    ``str(re.compile("x"))`` is ``"re.compile('x')"``, so accepting both matters: a caller
    building specs in Python passes a compiled pattern, and compiling its repr would produce
    a regex that never matches anything -- a silently empty parse.
    """
    if pattern is None:
        return None
    if isinstance(pattern, re.Pattern):
        return pattern
    return re.compile(str(pattern))


@dataclass(frozen=True, slots=True)
class ParsedRecord:
    """One record's fields. ``values`` is empty rather than full of ``None``.

    A ``many`` field holds a tuple, never a joined string. Joining ``CVE-1`` and ``CVE-2``
    into ``"CVE-1, CVE-2"`` would put a composite that exists in no source into the next
    layer as if it were one observed value -- the exact fiction this platform is built to
    avoid. A field is either one value or several, and the type says which.
    """

    values: Mapping[str, Any]
    kinds: Mapping[str, str]
    #: Fields the declaration promised and the payload did not contain.
    unresolved: tuple[str, ...] = ()

    def kind_of(self, name: str) -> str:
        return self.kinds.get(name, "unknown")

    def get(self, name: str, default: str = "") -> str:
        """The single value of a field, or ``default`` when it holds several.

        A caller that reads a ``many`` field through this gets the first value, which is only
        safe when it knows the declaration. :meth:`all_of` is the honest read.
        """
        value = self.values.get(name, default)
        if isinstance(value, tuple):
            return value[0] if value else default
        return value

    def all_of(self, name: str) -> tuple[str, ...]:
        """Every value of a field, whether it declared one or many."""
        value = self.values.get(name, ())
        if isinstance(value, tuple):
            return value
        return (value,) if value else ()

    def is_many(self, name: str) -> bool:
        return isinstance(self.values.get(name), tuple)

    def as_dict(self) -> dict[str, Any]:
        return {
            "values": {k: (list(v) if isinstance(v, tuple) else v)
                       for k, v in self.values.items()},
            "kinds": dict(self.kinds),
            "unresolved": list(self.unresolved),
        }


@dataclass(frozen=True, slots=True)
class ParseOutcome:
    """What one parse produced, and what it could not.

    ``status`` is the honest summary. ``empty`` means the source answered and the payload
    held nothing we declared -- a real answer, not a failure. ``failed`` means we could not
    read the response at all.
    """

    status: str
    records: tuple[ParsedRecord, ...] = ()
    #: Field names that resolved in no record.
    unresolved: tuple[str, ...] = ()
    #: Fields declared single-valued that returned several values.
    ambiguous: tuple[str, ...] = ()
    detail: str = ""
    family: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    @property
    def record_count(self) -> int:
        return len(self.records)

    def kinds_seen(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for record in self.records:
            for kind in record.kinds.values():
                counts[kind] = counts.get(kind, 0) + 1
        return dict(sorted(counts.items()))

    def values_for(self, kind: str) -> tuple[str, ...]:
        """Every distinct value this parse found of one kind, in order.

        Reads through :meth:`ParsedRecord.all_of`, so a ``many`` field contributes each of
        its values rather than a joined string that exists in no source.
        """
        seen: list[str] = []
        for record in self.records:
            for name, declared in record.kinds.items():
                if declared != kind:
                    continue
                for value in record.all_of(name):
                    if value and value not in seen:
                        seen.append(value)
        return tuple(seen)

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "family": self.family,
            "records": self.record_count,
            "unresolved": list(self.unresolved),
            "ambiguous": list(self.ambiguous),
            "detail": self.detail,
            "kinds": self.kinds_seen(),
        }


#: Every status this platform can report. A status outside this set is a bug: a new failure
#: mode that nobody taught the platform to recognise will otherwise be reported as ``ok`` by
#: whichever branch forgot to set it.
#:
#: Module level rather than a class attribute because ``SourceOutcome`` is a ``slots=True``
#: dataclass, where an annotated class attribute becomes a slot descriptor -- so
#: ``SourceOutcome.ALL_STATUSES`` returned a ``member_descriptor`` and iterating it raised
#: ``TypeError`` at the exact moment the check was supposed to catch an unknown status.
ALL_STATUSES: tuple[str, ...] = (
    "ok",                # fetched, parsed, produced records
    "empty",             # fetched and parsed; the payload declared nothing
    "needs_key",         # requires_key, and no credential was available
    "binary_missing",    # declares a local tool that is not installed
    "os_unsupported",    # declares an os_requirement this host does not meet
    "upstream_down",     # non-2xx, timeout, or a transport failure
    "parse_failed",      # 2xx body we could not read as the declared shape
    "budget_exhausted",  # refused before execution: rate limit, cost, pagination cap
    "disabled",          # enabled: false
)


@dataclass(frozen=True, slots=True)
class SourceOutcome:
    """A source's execution outcome, including the ones that are not successes.

    The status vocabulary is the point of this type. A source that needs a key, one whose
    upstream is down, and one that answered with nothing are three different facts, and the
    design that collapses them into "no results" is the design that reports an investigation
    as saturated while it has read nothing.
    """

    source_id: str
    source_name: str
    status: str
    records: int = 0
    observations: int = 0
    detail: str = ""
    parse_status: str = ""
    unresolved_fields: tuple[str, ...] = ()
    kinds: Mapping[str, int] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    @property
    def needs_credential(self) -> bool:
        """Sources parked on a missing key. Counted separately: they are runnable later."""
        return self.status == "needs_key"

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source_name": self.source_name,
            "status": self.status,
            "records": self.records,
            "observations": self.observations,
            "detail": self.detail,
            "parse_status": self.parse_status,
            "unresolved_fields": list(self.unresolved_fields),
            "kinds": dict(self.kinds),
        }


#: ``parser:`` names carried by the catalogue that are shapes rather than vendors, plus the
#: legacy names that already meant a shape. Mapping here is what lets a definition written
#: as ``parser: shodan_internetdb`` still run: the vendor name resolves to the family its
#: response actually has.
LEGACY_FAMILIES: dict[str, str] = {
    # json_rows
    "arxiv": "json_rows", "bgpview": "json_rows", "blockchain_btc": "json_rows",
    "blockchain_tx": "json_rows", "blockstream": "json_rows", "cisa_kev": "json_rows",
    "crossref": "json_rows", "cve_circl": "json_rows", "ddg_html": "json_rows",
    "dehashed": "json_rows", "dev_to": "json_rows", "ethplorer": "json_rows",
    "exif": "json_rows", "github_advisories": "json_rows", "github_search": "json_rows",
    "github_user": "json_rows", "greynoise": "json_rows", "hackernews": "json_rows",
    "hibp_breach": "json_rows", "hibp_paste": "json_rows", "holehe_text": "cali_text",
    "intelx": "json_rows", "ipapi": "json_rows", "ipapi_co": "json_rows",
    "ipinfo": "json_rows", "ipwhois": "json_rows", "keybase": "json_rows",
    "mailfy_text": "cali_text", "maigret_json": "cali_text", "malwarebazaar": "json_rows",
    "mastodon": "json_rows", "metagoofil_text": "cali_text", "microlink": "json_rows",
    "nominatim": "json_rows", "nvd_cve": "json_rows", "openalex": "json_rows",
    "openphish": "text_lines", "openweather_geo": "json_rows", "oscensky": "json_rows",
    "otx": "json_rows", "phonebook": "json_rows", "phishtank": "json_rows",
    "phonefy_text": "cali_text", "phoneinfoga_json": "cali_text",
    "reddit": "json_rows", "reddit_search": "json_rows", "ripe_stat": "json_rows",
    "searchfy_text": "cali_text", "sherlock_text": "cali_text", "screenshot": "json_rows",
    "tech_fingerprint": "json_rows", "theharvester_text": "cali_text",
    "threatfox": "json_rows", "timezone": "json_rows", "traceroute_text": "text_lines",
    "twitch_user": "json_rows", "twitter_user": "json_rows", "tineye_reverse": "json_rows",
    "urlcrazy_text": "cali_text", "urlhaus": "json_rows", "urlhaus_payloads": "json_rows",
    "usufy_text": "cali_text", "vt_domain": "json_rows", "vt_file": "json_rows",
    "vt_ip": "json_rows", "wafw00f_text": "cali_text", "wigle": "json_rows",
    "wikidata": "json_rows", "wikipedia": "json_rows", "youtube_user": "json_rows",
    "amass_json": "json_rows", "pass_through": "json_rows", "raw_text": "text_lines",
    # json_object
    "aircraft_registry": "json_object", "censys_certificates": "json_object",
    "crtsh_json": "json_object", "dehashed_email": "json_object",
    "discord_discovery": "json_object", "dns_json": "json_object",
    "dns_json_webhook": "json_object", "google_cache_check": "json_object",
    "hackertarget_whois": "json_object", "http_probe": "json_object",
    "n2yo": "json_object", "nominatim_reverse": "json_object",
    "opensky": "json_object", "phishhtank": "json_object",
    "rdap_domain": "json_object", "rdap_ip": "json_object",
    "shodan_internetdb": "json_object", "urlscan": "json_object",
    # text_lines
    "blocklist_de_all": "text_lines", "bssid_lookups_ieee": "text_lines",
    "dns_dumpster_subdomains": "text_lines", "emergingthreats_compromised": "text_lines",
    "exploitdb_search": "text_lines", "feodo_tracker": "text_lines",
    "http_headers": "text_lines", "http_probe_text": "text_lines",
    "nping_text": "text_lines", "sublist3r_lines": "text_lines",
    "text_lines": "text_lines", "whois_text": "cali_text",
    "cacerts_txt": "text_lines", "bgpview_text": "text_lines",
    "bgpview_asn_text": "text_lines", "memberships_text": "text_lines",
    "nmap_text": "cali_text", "macvendors_lookup": "json_object",
    "ipapi_free": "json_rows", "ipapi_co_full": "json_rows",
    "rdns_text": "text_lines", "sslbl_abuse_ch": "text_lines",
    "censys_certificates_text": "json_object", "hackertarget_dns": "text_lines",
    "hackertarget_findshareddns": "text_lines", "hackertarget_hostsearch": "text_lines",
    "hackertarget_aslookup": "text_lines", "hackertarget_geoip": "text_lines",
    "hackertarget_reverse_dns": "text_lines", "hackertarget_reverseiplookup": "text_lines",
    "wayback_avail": "json_object", "wayback_cdx": "text_lines",
    "pages_dev_meta": "json_object", "blockchain_btc_address": "json_object",
    "psbdmp_ws": "text_lines", "psbdmp_search": "text_lines",
    "leakcheck_public": "json_object", "leakix_leak": "json_rows",
    "opengraph": "text_lines", "kafka_connect_text": "text_lines",
    "alienvault_otx": "json_rows", "securitytrails_dns": "json_rows",
    "fullhunt_surface": "json_rows", "bucket_probe": "json_rows",
    "supply_chain_dns": "json_rows", "telegram_tginfo": "json_rows",
    "telegram_search_ligated": "json_rows", "marine_traffic": "json_rows",
    "satellite_pass": "json_rows", "pdns_crtsh": "json_rows",
    "pdns_certspotter": "json_rows", "robtex_ip": "json_rows",
    "l34rce_txt": "text_lines", "certstream": "json_rows",
    "censys_asn": "json_rows", "urlhaus_recent": "json_rows",
    "medianis_query": "json_object", "openphish_feed": "text_lines",
    "verify_email": "json_object", "scylla_email": "json_object",
    "emailrep_email": "json_object", "hibp_paste_json": "json_object",
    "gists_github_search": "json_rows", "github_code_search": "json_rows",
    "github_gists": "json_rows", "github_repos": "json_rows",
    "medium_public": "json_rows", "pinterest_public": "json_rows",
    "reddit_about": "json_object", "reddit_posts": "json_rows",
    "reddit_subreddit": "json_rows", "twitch_user_json": "json_object",
    "whatsmyname_username": "json_rows", "wordpress_profile": "text_lines",
    "duckduckgo_instant": "json_object", "keybase_lookup": "json_object",
    "blocklist_de": "text_lines", "emergingthreats": "text_lines",
    "wifi_lookup": "json_rows", "rdap_org": "json_object",
    "censys_search": "json_object", "alpine_cve": "json_object",
    "malwarebazaar_json": "json_object", "abuseipdb_check": "json_object",
    "exploit_db": "text_lines", "google_safe_browsing": "json_object",
    "archive_org": "json_object", "commoncrawl_index": "text_lines",
    "commoncrawl_coll_info": "json_rows",
    # cali_text -- the local-binary family, all of which defer without the tool
    "dmitry_text": "cali_text", "dnsenum_text": "cali_text", "dnsrecon_text": "cali_text",
    "fierce_text": "cali_text", "usufy_text2": "cali_text", "wafw00f_text2": "cali_text",
    "whatweb_text": "cali_text", "theharvester": "cali_text", "mailfy": "cali_text",
    "phonefy": "cali_text", "searchfy": "cali_text", "sherlock": "cali_text",
    "urlcrazy": "cali_text", "holehe": "cali_text", "amass": "cali_text",
    "sublist3r": "cali_text", "maigret": "cali_text", "metagoofil": "cali_text",
    "phoneinfoga": "cali_text", "cali": "cali_text",
}

#: The families themselves, keyed by the name a definition may use.
FAMILIES: tuple[str, ...] = (
    "json_rows",
    "json_object",
    "text_lines",
    "dns_json",
    "html_scrape",
    "cali_text",
    "binary_json",
)


def family_of(parser_name: str) -> str:
    """The family a ``parser:`` name resolves to.

    Falls back to ``json_rows`` for an unrecognised name rather than refusing. The catalogue
    carries names nobody has classified, and the overwhelmingly common shape for an
    unclassified JSON API is a list of records -- so the default is the most likely correct
    one, and :attr:`ParseOutcome.status` still says ``parse_failed`` when it is not.
    """
    name = str(parser_name or "").strip()
    if name in FAMILIES:
        return name
    return LEGACY_FAMILIES.get(name, "json_rows")


def _record_from(mapping: Mapping[str, Any], specs: Sequence[FieldSpec]) -> tuple[ParsedRecord, tuple[str], tuple[str]]:
    """Read every spec from one record."""
    values: dict[str, str] = {}
    kinds: dict[str, str] = {}
    unresolved: list[str] = []
    ambiguous: list[str] = []
    for spec in specs:
        found = collect_path(mapping, spec.path)
        if not found:
            if spec.required:
                unresolved.append(spec.name)
            continue
        if spec.many:
            picked = tuple(dict.fromkeys(
                str(v).strip() for v in found if v is not None and str(v).strip()
            ))
            if picked:
                # A tuple even for one match: ``many`` is a property of the declaration, and
                # a caller that branches on it must not have to special-case the length.
                values[spec.name] = picked
                kinds[spec.name] = spec.kind
            elif spec.required:
                unresolved.append(spec.name)
            continue
        if len(found) > 1:
            # Reported, not silently collapsed. See FieldSpec: a shape change is an event.
            ambiguous.append(spec.name)
        value = found[0]
        # A list at a single-valued path is a list, whatever the declaration said. Rendering
        # it with ``str()`` produced the literal ``[443]`` for a port, which is a value that
        # exists in no source -- the same defect as joining many values into a comma string,
        # reached by a different route.
        if isinstance(value, (list, tuple)):
            ambiguous.append(spec.name)
            picked = tuple(dict.fromkeys(
                str(v).strip() for v in value if v is not None and str(v).strip()
            ))
            if picked:
                values[spec.name] = picked
                kinds[spec.name] = spec.kind
            elif spec.required:
                unresolved.append(spec.name)
            continue
        if value is None:
            if spec.required:
                unresolved.append(spec.name)
            continue
        text = str(value).strip()
        if not text:
            if spec.required:
                unresolved.append(spec.name)
            continue
        values[spec.name] = text
        kinds[spec.name] = spec.kind
    return ParsedRecord(values, kinds, tuple(unresolved)), tuple(unresolved), tuple(ambiguous)


def _decode(body: bytes) -> tuple[Any, str]:
    """Decode a response body as JSON, or say why it could not be."""
    if not body:
        return None, "empty body"
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = body.decode("latin-1")
        except UnicodeDecodeError as exc:
            return None, f"undecodable: {exc}"
    stripped = text.lstrip()
    if not stripped:
        return None, "blank body"
    if stripped[0] not in "[{":
        return None, "body is not JSON"
    try:
        return json.loads(stripped), ""
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON: {exc.msg} at line {exc.lineno}"


def _iter_records(document: Any, root: str) -> tuple[list[Any], str]:
    """The records under ``root``, or the document itself when ``root`` is empty."""
    if not root:
        if isinstance(document, list):
            return list(document), ""
        if isinstance(document, Mapping):
            return [document], ""
        return [], "document is neither a list nor an object"
    value = resolve_path(document, root)
    if value is MISSING:
        return [], f"list_path {root!r} not found"
    if isinstance(value, list):
        return list(value), ""
    # A single object where a list was expected is the most common real shape change, and it
    # is handled rather than refused: the one record is the whole answer.
    if isinstance(value, Mapping):
        return [value], ""
    return [], f"list_path {root!r} is a {type(value).__name__}, not a list"


def _specs_from(raw: Any) -> tuple[FieldSpec, ...]:
    """Field declarations from a definition's ``parse:`` block.

    Three accepted shapes, in increasing explicitness:

    ``fields: {org: org}`` plus ``kinds: {org: organization}``
        The common case in two short lines. The shorthand ``name: path`` carries the path,
        and a sibling ``kinds`` block carries the types -- because ``org: organization``
        alone is genuinely ambiguous (is ``organization`` a JSON path or a type?) and
        resolving that guess silently is how a source starts declaring types it does not
        have.
    ``fields: {org: {path: org, kind: organization}}``
        Everything in one place, when a field needs ``many`` or ``required``.
    ``fields: [{name: ..., path: ...}, ...]``
        A list, for definitions that prefer one declaration per row.
    """
    if not isinstance(raw, Mapping):
        return ()
    block = raw.get("fields")
    kinds = raw.get("kinds") if isinstance(raw.get("kinds"), Mapping) else {}

    def build(name: str, spec: Any) -> FieldSpec:
        field_spec = FieldSpec.from_yaml(spec, name=name)
        declared = kinds.get(field_spec.name)
        if declared and field_spec.kind == "unknown":
            # The sibling ``kinds`` block wins over a default, never over an explicit
            # ``kind:`` on the field itself.
            field_spec = replace(field_spec, kind=str(declared))
        return field_spec

    if isinstance(block, Mapping):
        return tuple(build(name, spec) for name, spec in block.items())
    if isinstance(block, list):
        return tuple(build(str(spec.get("name") or ""), spec)
                     for spec in block if isinstance(spec, Mapping))
    return ()


def parse_body(
    body: bytes,
    *,
    parser: str = "json_rows",
    fields: Sequence[FieldSpec] = (),
    list_path: str = "",
) -> ParseOutcome:
    """Parse a response body into records, by declared family.

    ``fields`` empty yields an ``empty`` outcome rather than an error: a definition that
    declares no fields has asked for nothing, and reporting that as a parse failure would
    blame the source for the definition's silence.
    """
    family = family_of(parser)
    if not fields:
        return ParseOutcome(status="empty", detail="no fields declared", family=family)

    if family == "text_lines" or family == "cali_text":
        return _parse_text(body, family=family, fields=fields)

    document, error = _decode(body)
    if error:
        return ParseOutcome(status="parse_failed", detail=error, family=family)

    records_raw, error = _iter_records(document, list_path)
    if error and not records_raw:
        return ParseOutcome(status="parse_failed", detail=error, family=family)

    if family == "json_object" and not list_path and isinstance(document, Mapping):
        # An object-shaped source: recurse so nested records are reachable by path.
        records_raw = [document]

    records: list[ParsedRecord] = []
    unresolved: set[str] = set()
    ambiguous: set[str] = set()
    for raw_record in records_raw:
        if not isinstance(raw_record, Mapping):
            continue
        record, missed, ambiguous_names = _record_from(raw_record, fields)
        if not record.values:
            continue
        records.append(record)
        unresolved.update(missed)
        ambiguous.update(ambiguous_names)

    if not records:
        return ParseOutcome(
            status="empty",
            detail=f"{len(records_raw)} records, none carried a declared field",
            family=family,
            unresolved=tuple(sorted(unresolved)),
        )
    return ParseOutcome(
        status="ok",
        records=tuple(records),
        unresolved=tuple(sorted(unresolved)),
        ambiguous=tuple(sorted(ambiguous)),
        family=family,
    )


_LINE_SKIP = re.compile(r"^\s*(#|//|;)")


def parse_source(
    definition: Any,
    body: bytes,
    *,
    status_code: int = 200,
) -> ParseOutcome:
    """Parse one fetched response for a catalogue definition.

    Reads the definition's own ``parse:`` block, so the family, the paths and the fields live
    with the source rather than in a table here. A definition without a ``parse:`` block is
    ``empty`` with that reason stated -- not ``parse_failed``, which would blame the endpoint
    for a declaration that was never written.
    """
    if status_code < 200 or status_code >= 300:
        return ParseOutcome(
            status="upstream_down",
            detail=f"HTTP {status_code}",
            family=family_of(getattr(definition, "parser", "")),
        )
    raw = getattr(definition, "definition", None) or {}
    parse_block = raw.get("parse") if isinstance(raw, Mapping) else None
    if not isinstance(parse_block, Mapping):
        return ParseOutcome(
            status="empty",
            detail="definition declares no parse block",
            family=family_of(getattr(definition, "parser", "")),
        )
    specs = _specs_from(parse_block)
    return parse_body(
        body,
        parser=str(parse_block.get("family") or getattr(definition, "parser", "")),
        fields=specs,
        list_path=str(parse_block.get("list_path") or ""),
    )





def _parse_text(body: bytes, *, family: str, fields: Sequence[FieldSpec]) -> ParseOutcome:
    """Parse a text body line by line, honouring per-field line patterns.

    Every declared field may carry a ``line_pattern``; a field with none takes the whole
    trimmed line. Comments are skipped -- feed files are full of them, and treating
    ``# comment`` as a hostname is worse than not parsing that line.

    A field's regex travels on its own ``FieldSpec``, so the family layer needs no side
    table that could fall out of step with the declarations.
    """
    try:
        text = body.decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        return ParseOutcome(status="parse_failed", detail=f"undecodable: {exc}", family=family)

    records: list[ParsedRecord] = []
    lines = text.splitlines()
    for raw_line in lines:
        line = raw_line.strip()
        if not line or _LINE_SKIP.match(line):
            continue
        values: dict[str, str] = {}
        kinds: dict[str, str] = {}
        for spec in fields:
            matcher = spec.pattern
            if matcher is None:
                if spec.name not in values:
                    values[spec.name] = line
                    kinds[spec.name] = spec.kind
                continue
            found = matcher.search(line)
            if not found:
                continue
            value = (found.group(1) if found.groups() else found.group(0)).strip()
            if value:
                values[spec.name] = value
                kinds[spec.name] = spec.kind
        if values:
            records.append(ParsedRecord(values, kinds))

    if not records:
        return ParseOutcome(
            status="empty",
            detail=f"{len(lines)} lines, none matched a declared field",
            family=family,
        )
    return ParseOutcome(status="ok", records=tuple(records), family=family)