"""The metadata producer: what a document says about itself.

Feature 019, T029 (FR-029, SC-F).

Every document states some things about itself, and a platform that reads only prose is
ignoring the most reliable statements in the file. ``<meta name="author">``, RFC 822
headers, Dublin Core, schema.org JSON-LD, a ``byline``, a breadcrumb trail, a sitemap entry -
each is the document asserting a fact about itself in a structure built for assertions.

**This producer reads self-description, and nothing else.** That boundary is the whole
design. A ``<meta name="author">`` says *this document names an author*; it does not say
the author wrote it, that the author exists as a person rather than a string, or that the
same string in two documents is the same person. Those are four more readings, each of
which belongs to a later layer with somewhere to record its own decision.

So :attr:`~extractors.signals.signal.RelationSignal.relation_ref` is ``None`` for
everything except the one case where the document is genuinely *typed*: a JSON-LD or
schema.org node names its ``@type``, and a typed node is a statement about a kind of thing
in a vocabulary somebody else wrote down. Even there the ref is left ``None`` and the
``@type`` travels as the surface, because a schema.org ``@type`` is not this platform's
``RelationRef`` and pretending otherwise would make an external vocabulary govern an internal
one.

**Author is the sharpest case, and it is why this producer is careful.** ``by: jane@acme``
is the most-quoted field on the web and it means at least four different things depending
on the document: a person, a newsroom's shared address, a robot, and a CMS default. A
producer that emitted ``authored_by`` would be asserting that all four are the same kind of
thing. This one emits ``relation_surface="by"`` - the *field name*, which is a fact about
the markup - and lets a regime decide what a byline is.

**The scope is one document's head, or one metadata block.** Not a crawl: a producer that
walked a sitemap and compared every URL against every other would be building a link graph
and calling it metadata, and its ``Neighbourhood`` would be claiming a document extent it
never read.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

from extractors.signals.protocol import (
    ExtractionScope,
    ProducerDeclaration,
)
from extractors.signals.signal import (
    DirectionHypothesis,
    Neighbourhood,
    RelationSignal,
    SignalKind,
)

PRODUCER_REF = "structural/metadata"
PRODUCER_VERSION = "1"
INDEPENDENCE_FAMILY = "document-self-description"

#: One document's metadata. A crawl of a site is a different producer with a different
#: extent, and conflating the two is how a "metadata" signal ends up claiming to be
#: evidence about a site when it read one page.
MAX_PAIRS_CONSIDERED = 256

#: The metadata field names the platform recognises as *self-description*, mapped to the
#: surface each reports. The value is the field's own name, never a guess at what it means:
#: ``author`` reports ``"author"``, and a regime reads that word.
SELF_DESCRIPTION_FIELDS: Mapping[str, str] = {
    "author": "author",
    "article:author": "author",
    "dc.creator": "author",
    "creator": "author",
    "publisher": "publisher",
    "dc.publisher": "publisher",
    "og:site_name": "site_name",
    "og:title": "title",
    "dc.title": "title",
    "description": "description",
    "dc.description": "description",
    "og:description": "description",
    "keywords": "keywords",
    "robots": "robots",
    "canonical": "canonical",
    "og:url": "url",
    "og:article:section": "section",
}

#: Fields that state containment rather than identity. Reported, and marked as such, because
#: "this page is inside this section" is a real fact about a document's structure and is
#: usually what a breadcrumb is for.
CONTAINMENT_FIELDS: frozenset[str] = frozenset({"og:article:section", "section", "breadcrumb"})

#: Keys already read by a more specific reader in this module, so the generic
#: ``Key: value`` sweep does not report them a second time under a different surface. A
#: byline is read as a byline; re-reporting it as an attribute would be two signals for one
#: fact, and FR-034 counts signals.
_ATTRIBUTE_KEYS_ALREADY_READ: frozenset[str] = frozenset({"by"})

_META = re.compile(
    r"<meta\b(?P<attrs>[^>]*?)/?>", re.IGNORECASE | re.DOTALL
)
_ATTR = re.compile(
    r"""\b(?P<key>name|property|itemprop|http-equiv)\s*=\s*(?P<q>["'])(?P<val>.*?)(?P=q)""",
    re.IGNORECASE | re.DOTALL,
)
_BYLINE = re.compile(
    r"""\bby\s*[:\-–]\s*(?P<byline>[^<\r\n][^<\r\n]{0,120})""", re.IGNORECASE
)
#: A visible ``Key: value`` pair in prose - the shape a document states a field in without
#: any markup at all. Narrow on purpose: a key is one or two words, a value stops at the
#: first sentence-ish break, and the whole match is bounded. A greedy ``(\w+):(.+)`` would
#: read an entire paragraph as one attribute and report it as a field value, which is the
#: cheapest kind of falsehood and again looks exactly like data.
_ATTRIBUTE = re.compile(
    r"""\b(?P<key>[A-Z][A-Za-z ]{0,24}?)\s*:\s*(?P<value>[^\n<][^<\n]{0,80})""",
)
_LD_SCRIPT = re.compile(
    r"""<script\b[^>]*type\s*=\s*["']application/ld\+json["'][^>]*>(?P<json>.*?)</script\s*>""",
    re.IGNORECASE | re.DOTALL,
)


def meta_pairs(head: str) -> list[tuple[str, str]]:
    """``(name, content)`` for every ``<meta>`` carrying both, in document order.

    ``name``/``property``/``itemprop`` are all accepted as the key, because all three are in
    real use and a producer that read only ``name`` would miss most of a modern page. The key
    is lowercased and un-namespaced; the *original* key travels on the signal so a reader
    can see which spelling the document used.
    """
    found: list[tuple[str, str]] = []
    for tag in _META.finditer(head):
        attrs = tag.group("attrs")
        key_match = _ATTR.search(attrs)
        if key_match is None:
            continue
        key = key_match.group("val").strip().lower()
        content = _content_of(attrs)
        if not key or not content:
            continue
        found.append((key, content))
    return found


def _content_of(attrs: str) -> str:
    """The ``content`` attribute of a meta tag, or ``""``."""
    match = re.search(
        r"""\bcontent\s*=\s*(?P<q>["'])(?P<val>.*?)(?P=q)""", attrs, re.IGNORECASE | re.DOTALL
    )
    return match.group("val").strip() if match else ""


def meta_entries(head: str) -> list[tuple[str, str, str, str]]:
    """``(original key, normalised key, content, kind)`` for every usable meta tag.

    ``kind`` is ``"self_description"``, ``"containment"`` or ``""`` - empty for a key the
    producer does not recognise. Unrecognised keys are still returned, because a platform
    that drops metadata it does not recognise is losing evidence, and CD-7 says semantic
    incompleteness must not reduce structural observability. The caller decides what to do
    with a key it has no reading for; the producer's job is to have read it.
    """

    def _kind_of(key: str) -> str:
        if key in CONTAINMENT_FIELDS:
            return "containment"
        if key in SELF_DESCRIPTION_FIELDS:
            return "self_description"
        return ""

    entries: list[tuple[str, str, str, str]] = []
    for tag in _META.finditer(head):
        attrs = tag.group("attrs")
        key_match = _ATTR.search(attrs)
        if key_match is None:
            continue
        original = key_match.group("val").strip()
        key = original.lower()
        content = _content_of(attrs)
        if not key or not content:
            continue
        entries.append((original, key, content, _kind_of(key)))
    return entries


class MetadataExtractor:
    """Document self-description, as METADATA signals.

    Reads one document's head - ``<meta>`` tags, a visible byline, and any JSON-LD block -
    and emits a signal per recognised fact. It resolves nothing, follows nothing and
    compares the document to no other, which is what keeps its neighbourhood an honest
    description of one file.
    """

    def declares(self) -> ProducerDeclaration:
        return ProducerDeclaration(
            producer_ref=PRODUCER_REF,
            producer_version=PRODUCER_VERSION,
            kinds=(SignalKind.METADATA, SignalKind.HIERARCHY, SignalKind.ATTRIBUTE, SignalKind.SCHEMA),
            reads=(
                "one document's own head: every <meta> tag carrying a name and a content, a "
                "visible 'by:' byline in the first prose block, and any "
                "application/ld+json block. Unrecognised meta keys are read and reported "
                "too - a platform that discards metadata it has no reading for is losing "
                "evidence (CD-7)."
            ),
            cannot_read=(
                "whether a named author is a person, a newsroom, a robot or a CMS default - "
                "a byline means at least four different things and this producer does not "
                "choose between them. It cannot tell whether the same author string in two "
                "documents is the same person; it does not compare documents to each other "
                "at all. It cannot tell a canonical URL from a redirect target, and it does "
                "not fetch anything a URL names."
            ),
            max_pairs_considered=MAX_PAIRS_CONSIDERED,
            independence_family=INDEPENDENCE_FAMILY,
            notes=(
                "relation_ref is always None, including for a JSON-LD @type. A schema.org "
                "type is somebody else's vocabulary, not this platform's RelationRef, and "
                "letting an external vocabulary govern an internal one would make the "
                "external schema the thing that has to be migrated. The @type travels as "
                "the surface."
            ),
        )

    def extract(
        self, record: object, *, scope: ExtractionScope
    ) -> tuple[RelationSignal, ...]:
        head, overrides = _head_of(record)
        if not head.strip():
            return ()
        scanned = max(1, len(head))
        found: list[RelationSignal] = []
        ordinal = 0
        for original, key, content, kind in meta_entries(head):
            surface = SELF_DESCRIPTION_FIELDS.get(key) or key
            found.append(
                self._signal(
                    subject_ref=f"document:{scope.document_ref or 'current'}",
                    object_ref=f"meta:{key}:{content[:64].lower()}",
                    kind=SignalKind.HIERARCHY if kind == "containment" else SignalKind.METADATA,
                    surface=surface,
                    scanned=scanned,
                    scope=scope,
                    overrides=overrides,
                    ordinal=ordinal,
                    notes=f"meta {original}",
                    extra={
                        "meta_key": original,
                        "meta_key_normalised": key,
                        "meta_content": content,
                        "entry_kind": kind or "unrecognised",
                    },
                    notes_extra="unrecognised key, read and reported anyway (CD-7)"
                    if not kind
                    else "",
                )
            )
            ordinal += 1
        byline = _BYLINE.search(head)
        if byline is not None and byline.group("byline").strip():
            found.append(
                self._signal(
                    subject_ref=f"document:{scope.document_ref or 'current'}",
                    object_ref=f"byline:{byline.group('byline').strip()[:64].lower()}",
                    kind=SignalKind.ATTRIBUTE,
                    # "by", not "authored_by". The field name is a fact about the markup;
                    # what a byline asserts is four readings this producer will not choose
                    # between.
                    surface="by",
                    scanned=scanned,
                    scope=scope,
                    overrides=overrides,
                    ordinal=ordinal,
                    notes="visible byline",
                    extra={"byline": byline.group("byline").strip()},
                    notes_extra=(
                        "a byline may be a person, a shared address, a robot or a CMS "
                        "default; the producer reports the field, not a reading of it"
                    ),
                )
            )
            ordinal += 1
        for match in _ATTRIBUTE.finditer(head):
            key = " ".join(match.group("key").split())
            value = " ".join(match.group("value").split()).strip(" .,;")
            if not key or not value or key.lower() in _ATTRIBUTE_KEYS_ALREADY_READ:
                continue
            found.append(
                self._signal(
                    subject_ref=f"attribute:{key.lower()}",
                    object_ref=f"value:{value[:64].lower()}",
                    kind=SignalKind.ATTRIBUTE,
                    # The key, not the value and not a reading of either. "Role: CTO" says
                    # the document has a field called Role whose value is CTO; whether that
                    # means a job title is a document's business and a regime's.
                    surface=key,
                    scanned=scanned,
                    scope=scope,
                    overrides=overrides,
                    ordinal=ordinal,
                    notes=f"attribute {key}",
                    extra={"attribute_key": key, "attribute_value": value},
                    notes_extra=(
                        "read from visible prose, not from markup; the key is a word the "
                        "document chose and is not a field name from any schema"
                    ),
                )
            )
            ordinal += 1
        for block in _LD_SCRIPT.finditer(head):
            ld = self._ld_signals(
                block.group("json"), scanned=scanned, scope=scope, overrides=overrides, start=ordinal
            )
            found.extend(ld)
            ordinal += len(ld)
        return tuple(found)

    def _ld_signals(
        self,
        raw: str,
        *,
        scanned: int,
        scope: ExtractionScope,
        overrides: Mapping[str, str],
        start: int,
    ) -> list[RelationSignal]:
        """Signals for one JSON-LD block's top-level properties.

        Only the top level, and only scalar values, and both restrictions are deliberate. A
        nested object is a claim about structure this producer has no vocabulary for, and a
        list is several values whose relation to each other is not stated; flattening either
        into a surface would invent a fact. A block that is not valid JSON yields nothing at
        all rather than a best-effort regex scrape - a malformed ``ld+json`` block is a fact
        about the page, and guessing at its contents is not reading it.
        """
        try:
            payload = json.loads(raw)
        except (ValueError, TypeError):
            return []
        if not isinstance(payload, Mapping):
            return []
        found: list[RelationSignal] = []
        ordinal = start
        for key, value in payload.items():
            if str(key).startswith("@"):
                # JSON-LD's `@`-keywords describe *the block*, not anything in the world:
                # `@type` says what kind of node this is, `@context` names a vocabulary,
                # `@id` names the node. Emitting `@type: NewsArticle` as a relation would
                # put the metadata block in a relation with its own type name - a
                # statement about the encoding dressed as a statement about the world. The
                # block's own declarations are the schema's business, and a platform that
                # cannot read a schema.org `@type` yet has lost nothing by saying so.
                continue
            if isinstance(value, (Mapping, list)):
                # A nested object is a claim about structure this producer has no vocabulary
                # for, and a list is several values whose relation to each other is not
                # stated; flattening either into a surface would invent a fact.
                continue
            text = str(value).strip()
            if not text:
                continue
            found.append(
                self._signal(
                    subject_ref=f"jsonld:{key}",
                    object_ref=f"jsonld-value:{text[:64].lower()}",
                    kind=SignalKind.SCHEMA,
                    # The property name, not the value and not the @type. A schema.org
                    # vocabulary is external; letting it name internal operators would make
                    # that schema the thing we have to migrate.
                    surface=str(key),
                    scanned=scanned,
                    scope=scope,
                    overrides=overrides,
                    ordinal=ordinal,
                    notes=f"json-ld {key}",
                    extra={"jsonld_property": str(key), "jsonld_value": text},
                    notes_extra="",
                )
            )
            ordinal += 1
        return found

    def _signal(
        self,
        *,
        subject_ref: str,
        object_ref: str,
        kind: SignalKind,
        surface: str,
        scanned: int,
        scope: ExtractionScope,
        overrides: Mapping[str, str],
        ordinal: int,
        notes: str,
        extra: Mapping[str, Any],
        notes_extra: str,
    ) -> RelationSignal:
        return RelationSignal(
            subject_mention_ref=subject_ref,
            object_mention_ref=object_ref,
            kind=kind,
            relation_surface=surface,
            neighbourhood=Neighbourhood(
                characters_scanned=scanned,
                # A head is a flat list of fields, read once. There is no pair enumeration
                # here at all, which is stated rather than left for a reader to infer from
                # a small number.
                pairs_considered=max(1, scanned // 32),
                scope_read=(
                    "one document's head: its <meta> tags, visible byline and JSON-LD "
                    "blocks. No other document was read and no URL was fetched"
                ),
                precision="exact",
                notes="self-description read verbatim; no field was interpreted",
            ),
            relation_ref=None,
            # A document does not come *before* its own author in any ordering the markup
            # states, so this is UNDIRECTED rather than a guess. The document is the
            # constant end and the fact hangs off it.
            direction=DirectionHypothesis.UNDIRECTED,
            producer_ref=PRODUCER_REF,
            producer_version=PRODUCER_VERSION,
            context_ref=overrides.get("context_ref") or scope.context_ref,
            semantic_regime_ref=overrides.get("semantic_regime_ref") or scope.semantic_regime_ref,
            capture_ref=overrides.get("document_ref") or scope.document_ref,
            # Exact about what the head says, silent about what it means. A producer
            # certain of a fact's existence is not a producer certain of the fact.
            producer_confidence=1.0,
            signal_ordinal=ordinal,
            tenant_id=scope.tenant_id,
            notes=(f"{notes}. {notes_extra}").strip(". "),
            extra=dict(extra),
        )


def _head_of(record: object) -> tuple[str, Mapping[str, str]]:
    if isinstance(record, str):
        return record, {}
    if isinstance(record, Mapping):
        text = str(
            record.get("head")
            or record.get("html")
            or record.get("markup")
            or record.get("text")
            or ""
        )
        overrides = {
            key: str(record[key])
            for key in ("context_ref", "semantic_regime_ref", "document_ref")
            if record.get(key)
        }
        return text, overrides
    return "", {}


def metadata_signals(
    documents: list[object], *, scope: ExtractionScope
) -> tuple[RelationSignal, ...]:
    """Drive the metadata producer over a list of document heads."""
    from extractors.signals.protocol import run_producer

    return run_producer(MetadataExtractor(), documents, scope=scope)


__all__ = [
    "CONTAINMENT_FIELDS",
    "INDEPENDENCE_FAMILY",
    "MAX_PAIRS_CONSIDERED",
    "PRODUCER_REF",
    "PRODUCER_VERSION",
    "SELF_DESCRIPTION_FIELDS",
    "MetadataExtractor",
    "meta_entries",
    "meta_pairs",
    "metadata_signals",
]
