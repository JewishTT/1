"""Public-document parser for the governed zero-layer person workflow.

This is intentionally narrower than the generic contact harvesters. It extracts
publicly presented names, professional roles, organisations and document metadata.
It never emits email addresses, phone numbers, home addresses, birth dates,
biometric fields or private account identifiers.
"""

from __future__ import annotations

import html.parser
import json
import re
from collections.abc import Mapping
from urllib.parse import urljoin, urlsplit, urlunsplit

from ..type_detector import InputType, SeedInput
from .contracts import HarvestResult, ObservationCandidate
from .registry import HarvestContext

_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_PHONE = re.compile(r"(?<!\w)(?:\+?\d[\d ()-]{7,}\d)(?!\w)")

# The reservation contract is eight derived records per public page. Keep
# JSON-LD traversal bounded before constructing candidate objects.
MAX_JSONLD_NODES = 64
MAX_CANDIDATES_PER_PAGE = 8
MAX_INTERNAL_LINKS_PER_PAGE = 2
MAX_SCANNED_LINKS_PER_PAGE = 200
_NON_HTML_SUFFIXES = (".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".css", ".js", ".zip", ".mp4", ".woff", ".woff2")


def _safe_text(value: object, limit: int = 500) -> str:
    text = " ".join(str(value or "").split())
    text = _EMAIL.sub("[redacted contact]", text)
    text = _PHONE.sub("[redacted contact]", text)
    return text[:limit].strip()


def _object_name(value: object) -> str:
    if isinstance(value, Mapping):
        return _safe_text(value.get("name") or value.get("legalName") or "")
    if isinstance(value, list):
        return "; ".join(filter(None, (_object_name(item) for item in value)))[:300]
    return _safe_text(value)


def same_origin_public_links(base_url: str, hrefs: list[str], *, limit: int = MAX_INTERNAL_LINKS_PER_PAGE) -> tuple[str, ...]:
    """Return a small deterministic set of same-origin HTTPS HTML links only.

    This is discovery, not URL authorization. The secure transport still repeats
    DNS/SSRF, HTTPS, robots and port checks immediately before each request.
    """
    try:
        base = urlsplit(str(base_url or ""))
        base_host = (base.hostname or "").encode("idna").decode("ascii").lower()
        if base.scheme.lower() != "https" or not base_host or base.port not in (None, 443):
            return ()
    except (UnicodeError, ValueError):
        return ()

    found: set[str] = set()
    for href in hrefs[:MAX_SCANNED_LINKS_PER_PAGE]:
        try:
            candidate = urlsplit(urljoin(base_url, str(href or "").strip()))
            host = (candidate.hostname or "").encode("idna").decode("ascii").lower()
            if (
                candidate.scheme.lower() != "https"
                or host != base_host
                or candidate.username
                or candidate.password
                or candidate.port not in (None, 443)
            ):
                continue
            path = candidate.path or "/"
            if path.lower().endswith(_NON_HTML_SUFFIXES):
                continue
            canonical = urlunsplit(("https", base_host, path, candidate.query, ""))
            if canonical != urlunsplit(("https", base_host, base.path or "/", base.query, "")):
                found.add(canonical)
        except (UnicodeError, ValueError):
            continue
        if len(found) >= limit:
            break
    return tuple(sorted(found))


class _DocumentScanner(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.h1_parts: list[str] = []
        self.meta: dict[str, str] = {}
        self.json_ld: list[str] = []
        self.links: list[str] = []
        self._in_title = False
        self._in_h1 = False
        self._in_json_ld = False
        self._script_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): value or "" for key, value in attrs}
        if tag == "title":
            self._in_title = True
        elif tag == "h1":
            self._in_h1 = True
        elif tag == "a" and values.get("href") and len(self.links) < MAX_SCANNED_LINKS_PER_PAGE:
            self.links.append(values["href"])
        elif tag == "meta":
            key = (values.get("name") or values.get("property") or "").lower()
            if key in {"description", "og:title", "og:description", "article:published_time"}:
                self.meta[key] = _safe_text(values.get("content"), 500)
        elif tag == "script" and values.get("type", "").split(";", 1)[0].strip().lower() == "application/ld+json":
            self._in_json_ld = True
            self._script_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        elif tag == "h1":
            self._in_h1 = False
        elif tag == "script" and self._in_json_ld:
            self.json_ld.append("".join(self._script_parts))
            self._script_parts = []
            self._in_json_ld = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title_parts.append(_safe_text(data))
        if self._in_h1:
            self.h1_parts.append(_safe_text(data))
        if self._in_json_ld:
            self._script_parts.append(data)


def _jsonld_nodes(value: object, *, limit: int = MAX_JSONLD_NODES):
    """Iterative, bounded JSON-LD walker; hostile nesting cannot recurse forever."""
    stack = [value]
    yielded = 0
    while stack and yielded < limit:
        item = stack.pop()
        if isinstance(item, list):
            stack.extend(reversed(item))
        elif isinstance(item, Mapping):
            graph = item.get("@graph")
            if graph is not None:
                stack.append(graph)
            else:
                yield item
                yielded += 1


class PublicDocumentHarvester:
    """Extract a small allowlisted public-professional record from one HTTPS page."""

    name = "public_document_metadata"
    required_types = frozenset({InputType.URL})
    method = "deterministic public-document HTML + schema.org metadata extraction"
    license = "Apache-2.0"
    attribution = "first-party bounded parser; schema.org vocabulary"

    def run(self, seed: SeedInput, ctx: HarvestContext) -> HarvestResult:
        body = ctx.transport.fetch(seed.raw_value, timeout=8.0)
        if not body:
            return HarvestResult(
                module=self.name,
                notes=("public document not fetched; see secure transport refusal ledger",),
            )
        scanner = _DocumentScanner()
        try:
            scanner.feed(body)
            scanner.close()
        except Exception as exc:  # noqa: BLE001
            return HarvestResult(module=self.name, notes=(f"HTML parse failed: {type(exc).__name__}",))

        candidates: list[ObservationCandidate] = []
        url = seed.raw_value
        title = _safe_text(" ".join(scanner.title_parts) or " ".join(scanner.h1_parts))
        if title:
            candidates.append(ObservationCandidate(
                value=title,
                kind="public_document_title",
                confidence=0.65,
                source_module=self.name,
                method=self.method,
                raw_fields={"url": url},
                evidence="title/H1 from the fetched public document",
            ))

        description = scanner.meta.get("og:description") or scanner.meta.get("description")
        if description:
            candidates.append(ObservationCandidate(
                value=description,
                kind="public_document_summary",
                confidence=0.55,
                source_module=self.name,
                method=self.method,
                raw_fields={"url": url, "field": "description"},
                evidence="redacted public page metadata",
            ))

        published = scanner.meta.get("article:published_time")
        if published:
            candidates.append(ObservationCandidate(
                value=published,
                kind="public_document_published_at",
                confidence=0.6,
                source_module=self.name,
                method=self.method,
                raw_fields={"url": url, "field": "article:published_time"},
                evidence="publisher-provided publication timestamp",
            ))

        # Same-origin links create bounded discovery candidates for the next wave;
        # they are not fetched here and cannot escape this page's host.
        for linked_url in same_origin_public_links(url, scanner.links):
            candidates.append(ObservationCandidate(
                value=linked_url,
                kind="public_page_link",
                confidence=0.85,
                source_module=self.name,
                method=self.method,
                raw_fields={"parent_url": url},
                evidence="same-origin HTTPS page link discovered in public HTML",
            ))

        for raw in scanner.json_ld:
            try:
                root = json.loads(raw)
            except (ValueError, TypeError):
                continue
            for node in _jsonld_nodes(root):
                raw_type = node.get("@type") or ""
                types = {str(item).lower() for item in (raw_type if isinstance(raw_type, list) else [raw_type])}
                if "person" in types:
                    name = _safe_text(node.get("name"), 200)
                    role = _safe_text(node.get("jobTitle"), 240)
                    if name:
                        candidates.append(ObservationCandidate(
                            value=name, kind="public_name", confidence=0.8,
                            source_module=self.name, method=self.method,
                            raw_fields={"url": url, "schema_type": "Person", "field": "name"},
                            evidence="schema.org Person.name on a public page",
                        ))
                    if role:
                        candidates.append(ObservationCandidate(
                            value=role, kind="public_role", confidence=0.8,
                            source_module=self.name, method=self.method,
                            raw_fields={"url": url, "schema_type": "Person", "field": "jobTitle"},
                            evidence="schema.org Person.jobTitle on a public page",
                        ))
                    for field in ("worksFor", "affiliation"):
                        organisation = _object_name(node.get(field))
                        if organisation:
                            candidates.append(ObservationCandidate(
                                value=organisation, kind="public_affiliation", confidence=0.75,
                                source_module=self.name, method=self.method,
                                raw_fields={"url": url, "schema_type": "Person", "field": field},
                                evidence=f"schema.org Person.{field} on a public page",
                            ))
                elif types.intersection({"organization", "governmentorganization"}):
                    organisation = _safe_text(node.get("name"), 240)
                    if organisation:
                        candidates.append(ObservationCandidate(
                            value=organisation, kind="public_organization", confidence=0.75,
                            source_module=self.name, method=self.method,
                            raw_fields={"url": url, "schema_type": "Organization", "field": "name"},
                            evidence="schema.org Organization.name on a public page",
                        ))
                elif types.intersection({"article", "newsarticle", "report", "webpage"}):
                    headline = _safe_text(node.get("headline") or node.get("name"), 300)
                    if headline and headline != title:
                        candidates.append(ObservationCandidate(
                            value=headline, kind="public_document_title", confidence=0.7,
                            source_module=self.name, method=self.method,
                            raw_fields={"url": url, "schema_type": sorted(types)[0]},
                            evidence="schema.org public document headline",
                        ))

        # Stable deduplication and a hard per-page record ceiling. The budget
        # reservation is sized for this maximum; excess schema.org fan-out is
        # recorded rather than silently materialized without reservation.
        unique: dict[tuple[str, str], ObservationCandidate] = {}
        for candidate in sorted(candidates, key=lambda item: (item.kind, item.value, item.method)):
            unique.setdefault((candidate.kind, candidate.value.casefold()), candidate)
        keys = sorted(unique)
        # Preserve the link-discovery budget even on schema-rich pages.
        link_keys = [key for key in keys if key[0] == "public_page_link"][:MAX_INTERNAL_LINKS_PER_PAGE]
        fact_keys = [key for key in keys if key[0] != "public_page_link"]
        selected_keys = sorted(fact_keys[:MAX_CANDIDATES_PER_PAGE - len(link_keys)] + link_keys)
        notes = ()
        if len(keys) > len(selected_keys):
            notes = (f"candidate limit reached ({MAX_CANDIDATES_PER_PAGE}); additional public metadata was not emitted",)
        return HarvestResult(
            module=self.name,
            candidates=tuple(unique[key] for key in selected_keys),
            notes=notes,
        )
