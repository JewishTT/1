"""The metadata producer: what a document says about itself.

Feature 019, T029 (FR-029, FR-049, FR-094, SC-F).

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
in a vocabulary somebody else wrote down. Even here the ref is left ``None`` and the
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

**FR-094, and this was the worst producer defect in the repository.** Every signal this
module emitted before Phase 4B had two ends and *neither of them was a thing the document
contained*:

* the subject was ``document:current`` - or, when a ``document_ref`` was supplied,
  ``document:<whatever>`` - and the literal word ``current`` names no retrieval, so two
  documents' self-descriptions addressed **one** participant and every "this document has
  an author" observation in the corpus collapsed onto one end;
* for a visible ``Role: CTO`` line the subject was ``attribute:role`` and the object
  ``value:cto``: the **field name** as a participant, the **value** as another, both
  lowercased, i.e. the schema posing as the data;
* for a JSON-LD block they were ``jsonld:name`` and ``jsonld-value:acme`` - the **property
  name** as a participant. A ``<meta>`` tag's object was ``meta:author:jane@acme.example`` -
  the tag's own key plus the first **64 characters** of its content, silently cut, so two
  values sharing a 64-character prefix were one participant and one longer value was not
  what the document said.

What replaces it, and the rule behind the rule: **a document-scoped observation has the
retrieval on one end and the value's own text on the other.** The retrieval is required and
addressed by its real capture ref - :func:`~extractors.signals.mentions.deferred_capture`
refuses a blank one with ``participant_capture_ref_required`` rather than filling it with
``current`` - and the value is addressed by its own surface, **whole**, at its own character
offset. A field name, a property name and a URL are still read, and all three are still the
signal's :attr:`RelationSignal.relation_surface`, which is where a fact about the *markup*
belongs; none of them is a participant any more. :data:`NO_CAPTURE_REF_CODE` is the named
refusal for a document this producer will not address.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

from domain.predicate_signature import ArgumentSlot, Polarity
from domain.relation_participant import RelationParticipant
from domain.signal_basis import SignalBasis

from extractors.signals.mentions import deferred_capture, deferred_occurrence
from extractors.signals.protocol import (
    ExtractionScope,
    ProducerDeclaration,
)
from extractors.signals.signal import (
    DirectionHypothesis,
    Neighbourhood,
    RelationSignal,
    SignalContractError,
    SignalKind,
)

PRODUCER_REF = "structural/metadata"
PRODUCER_VERSION = "2"
INDEPENDENCE_FAMILY = "document-self-description"

#: One document's metadata. A crawl of a site is a different producer with a different
#: extent, and conflating the two is how a "metadata" signal ends up claiming to be
#: evidence about a site when it read one page.
MAX_PAIRS_CONSIDERED = 256

#: The named refusal for a document with no retrieval behind it. This producer is scoped to
#: one document's own head, and "which document" is a question only the caller can answer -
#: without a ``document_ref`` there is no addressable end, and the old code answered it with
#: the string ``current``, which named every document at once (FR-094, I-3).
NO_CAPTURE_REF_CODE = "metadata_document_ref_required"

#: The two ends' labels, read off the markup that declares the positions. The document end
#: is a retrieval rather than an occurrence and is addressed by
#: :func:`~extractors.signals.mentions.deferred_capture`; the value end is the value's own
#: text at its own offset. Before Phase 4B they were ``attribute:``/``value:``/``meta:``/
#: ``byline:``/``jsonld:``/``jsonld-value:`` - six namespaces for what is one shape.
VALUE_LABEL = "meta_value"
ATTRIBUTE_VALUE_LABEL = "attribute_value"
BYLINE_LABEL = "byline_text"
JSONLD_VALUE_LABEL = "jsonld_value"

#: The basis each of the four read paths declares, and the distinction is not cosmetic.
#: ``<meta name="author">`` is a **field the document states about itself**; a visible
#: ``Role: CTO`` and a JSON-LD scalar are a **key/value pair**; none of the three is
#: `metadata_field` in the first sense, and calling a schema.org property a "metadata
#: field" is how an external vocabulary gets to describe the internal one.
BASIS_META = SignalBasis.METADATA_FIELD
BASIS_ATTRIBUTE = SignalBasis.ATTRIBUTE_KEY
BASIS_JSONLD = SignalBasis.ATTRIBUTE_KEY


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
#: any markup at all. Narrow on purpose: a key is one or two words and a value stops at the
#: first tag or line break, so a greedy ``(\w+):(.+)`` would read an entire paragraph as one
#: attribute and report it as a field value, which is the cheapest kind of falsehood and again
#: looks exactly like data.
#:
#: The value is bounded by **structure, not by a character count**. It used to be
#: ``[^<\n]{0,80}``, which is a second truncation nobody had noticed behind the 64-character
#: one: a 94-character value was cut to 81 by the pattern and the cut was invisible, because
#: the producer had no position to compare the cut against. ``[^<\n]*`` stops at the same two
#: characters that give the pattern its meaning - a tag or a newline - and admits a value of
#: any length, so the only thing standing between this producer and a whole paragraph is the
#: one rule the pattern states out loud.
_ATTRIBUTE = re.compile(
    r"""\b(?P<key>[A-Z][A-Za-z ]{0,24}?)\s*:\s*(?P<value>[^\n<][^<\n]*)""",
)
_CONTENT = re.compile(
    r"""\bcontent\s*=\s*(?P<q>["'])(?P<val>.*?)(?P=q)""", re.IGNORECASE | re.DOTALL
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

    The four-tuple is the historical shape and is kept: :meth:`MetadataExtractor.extract`
    needs the two elements :func:`_meta_records` carries - where the value's own text begins
    and ends in ``head`` - and it reads *that* function rather than widening this one,
    because a helper whose callers index its returns positionally is a helper whose shape is
    load-bearing.
    """
    return [
        (original, key, content, kind)
        for original, key, content, kind, _start, _end in _meta_records(head)
    ]


def _meta_records(head: str) -> list[tuple[str, str, str, str, int, int]]:
    """:func:`meta_entries`, plus where the value's own text starts and ends in ``head``.

    The span is what makes the value's deferred reference an *occurrence's* address rather
    than a string match, and it is the reason both truncations could be removed honestly: a
    cut at 64 characters, and a regex that stopped at 80, were how this producer used to keep
    two long values apart. A position distinguishes them without cutting anything.
    """
    entries: list[tuple[str, str, str, str, int, int]] = []
    for tag in _META.finditer(head):
        key_match = _ATTR.search(tag.group("attrs"))
        if key_match is None:
            continue
        original = key_match.group("val").strip()
        key = original.lower()
        content_match = _CONTENT.search(tag.group("attrs"))
        if content_match is None:
            continue
        content, start, end = _trimmed_span(
            content_match.group("val"), tag.start("attrs") + content_match.start("val")
        )
        if not key or not content:
            continue
        entries.append((original, key, content, _kind_of(key), start, end))
    return entries


def _kind_of(key: str) -> str:
    if key in CONTAINMENT_FIELDS:
        return "containment"
    if key in SELF_DESCRIPTION_FIELDS:
        return "self_description"
    return ""


def _trimmed_span(raw: str, start: int) -> tuple[str, int, int]:
    """One value's own text, and the span of the *trimmed* region inside the document.

    Three offsets have to be reconciled and getting it wrong is a silently wrong address
    rather than a refusal: the value inside its attribute, the value with surrounding
    whitespace removed, and the value's position in the document. Returning the trimmed span
    means every caller that passes ``value_start``/``value_end`` gets offsets that index
    exactly the string it is addressing, so ``document[start:end] == value`` is a property a
    test can assert rather than an accident.
    """
    lead = len(raw) - len(raw.lstrip())
    text = raw.strip()
    return text, start + lead, start + lead + len(text)


def _locate_value(raw: str, text: str) -> tuple[int, int] | None:
    """Where a JSON-LD scalar's own text begins and ends inside the serialised block.

    The first occurrence, found by search, and that is a real limit rather than a shrug: a
    block that contains the same string twice has two occurrences of it and this producer
    cannot say which one the key is bound to without a JSON parser that reports spans, which
    :mod:`json` does not. The address still resolves - to the first occurrence of the exact
    string the key carried - and :func:`deferred_occurrence` is being asked to name a *real*
    thing, not a unique one. ``None`` is returned rather than a guess when the serialised text
    does not contain the value at all, which happens when :mod:`json` unescaped it, and the
    caller then addresses the value **without** a position rather than with a wrong one.
    """
    index = raw.find(text)
    return (index, index + len(text)) if index >= 0 else None




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
        """Every self-description in ``record``, as signals.

        **A record with no ``document_ref`` is refused with :data:`NO_CAPTURE_REF_CODE`**, per
        record rather than per signal. The old code substituted the literal ``current`` and
        emitted; the result was a participant that resolved against no capture, so a corpus
        of ten thousand documents shared one document end and no reader could tell which
        document any of the ten thousand observations was about. A refusal is the only answer
        that does not lie, and a producer that cannot name the document it is describing
        should not describe it (FR-094).
        """
        head, overrides = _head_of(record)
        if not head.strip():
            return ()
        document_ref = overrides.get("document_ref") or scope.document_ref
        if not document_ref.strip():
            raise SignalContractError(
                NO_CAPTURE_REF_CODE,
                "this producer describes ONE document's own head, and it was given no "
                "document_ref to describe. 'current' used to stand in here and it addressed "
                "every document at once: two pages' bylines became one participant, and a "
                "signal claimed a document nobody retrieved. Supply the capture id, or do "
                "not run the producer (FR-094, I-3)",
            )
        scanned = max(1, len(head))
        found: list[RelationSignal] = []
        ordinal = 0
        for original, key, content, kind, content_start, content_end in _meta_records(head):
            surface = SELF_DESCRIPTION_FIELDS.get(key) or key
            found.append(
                self._signal(
                    document_ref=document_ref,
                    value_label=VALUE_LABEL,
                    value_surface=content,
                    value_start=content_start,
                    value_end=content_end,
                    basis=BASIS_META,
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
        if byline is not None:
            byline_text, byline_start, byline_end = _trimmed_span(
                byline.group("byline"), byline.start("byline")
            )
        if byline is not None and byline.group("byline").strip():
            found.append(
                self._signal(
                    document_ref=document_ref,
                    value_label=BYLINE_LABEL,
                    value_surface=byline_text,
                    value_start=byline_start,
                    value_end=byline_end,
                    basis=BASIS_ATTRIBUTE,
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
            raw_value = match.group("value")
            value, value_start, value_end = _trimmed_span(raw_value, match.start("value"))
            value = value.strip(" .,;")
            value_end = value_start + len(value)
            if not key or not value or key.lower() in _ATTRIBUTE_KEYS_ALREADY_READ:
                continue
            found.append(
                self._signal(
                    document_ref=document_ref,
                    value_label=ATTRIBUTE_VALUE_LABEL,
                    value_surface=value,
                    value_start=value_start,
                    value_end=value_end,
                    basis=BASIS_ATTRIBUTE,
                    kind=SignalKind.ATTRIBUTE,
                    # The key, not the value and not a reading of either. "Role: CTO" says
                    # the document has a field called Role whose value is CTO; whether that
                    # means a job title is a document's business and a regime's. The key
                    # was a *participant* here before Phase 4B, as ``attribute:<key>``, which
                    # put a field name in the world where a value belonged (FR-094).
                    surface=key,
                    scanned=scanned,
                    scope=scope,
                    overrides=overrides,
                    ordinal=ordinal,
                    notes=f"attribute {key}",
                    extra={
                        "attribute_key": key,
                        "attribute_value": value,
                        "attribute_value_char_start": value_start,
                        "attribute_value_char_end": value_end,
                    },
                    notes_extra=(
                        "read from visible prose, not from markup; the key is a word the "
                        "document chose and is not a field name from any schema, and it is "
                        "the signal's surface rather than one of its participants"
                    ),
                )
            )
            ordinal += 1
        for block in _LD_SCRIPT.finditer(head):
            ld = self._ld_signals(
                block.group("json"),
                scanned=scanned,
                scope=scope,
                overrides=overrides,
                start=ordinal,
                document_ref=document_ref,
                block_start=block.start("json"),
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
        document_ref: str,
        block_start: int,
    ) -> list[RelationSignal]:
        """Signals for one JSON-LD block's top-level properties.

        Only the top level, and only scalar values, and both restrictions are deliberate. A
        nested object is a claim about structure this producer has no vocabulary for, and a
        list is several values whose relation to each other is not stated; flattening either
        into a surface would invent a fact. A block that is not valid JSON yields nothing at
        all rather than a best-effort regex scrape - a malformed ``ld+json`` block is a fact
        about the page, and guessing at its contents is not reading it.

        **The property name is not a participant and the value is not truncated.** Before
        Phase 4B these were ``jsonld:<property>`` and ``jsonld-value:<first 64 chars>``,
        which is a schema.org property name in the world where a value belongs, next to a
        value cut at a character boundary the schema knows nothing about. The property is the
        :attr:`RelationSignal.relation_surface` - a fact about the vocabulary the document
        used - and the value is a deferred occurrence of its own text.
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
            # The position of the *serialised* value inside the block, which is where the
            # document put these words. Exact rather than searched where the serialised form
            # matches the parsed one, and **absent** where it does not - :mod:`json` unescapes,
            # so a value containing a quote is in the block as `a\"b` and `find` would either
            # miss it or find it somewhere else. Absent is a weaker address, not a wrong one,
            # and the function that consumes it says so.
            span = _locate_value(raw, text)
            found.append(
                self._signal(
                    document_ref=document_ref,
                    value_label=JSONLD_VALUE_LABEL,
                    value_surface=text,
                    value_start=span[0] + block_start if span else None,
                    value_end=span[1] + block_start if span else None,
                    basis=BASIS_JSONLD,
                    kind=SignalKind.SCHEMA,
                    # The property name, not the value and not the @type. A schema.org
                    # vocabulary is external; letting it name internal operators would make
                    # that schema the thing we have to migrate. It is the surface, and it
                    # was a participant here before Phase 4B as ``jsonld:<property>``.
                    surface=str(key),
                    scanned=scanned,
                    scope=scope,
                    overrides=overrides,
                    ordinal=ordinal,
                    notes=f"json-ld {key}",
                    extra={
                        "jsonld_property": str(key),
                        "jsonld_value": text,
                        "jsonld_value_positioned": span is not None,
                    },
                    notes_extra="",
                )
            )
            ordinal += 1
        return found

    def _signal(
        self,
        *,
        document_ref: str,
        value_label: str,
        value_surface: str,
        value_start: int | None,
        value_end: int | None,
        basis: SignalBasis,
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
        """One self-description as one signal: **the retrieval, and the value's own text**.

        Both parameters are things the document really contains, and neither is a field
        name, a property name, a URL or a truncated string. The old signature took two
        pre-baked reference strings and the four fabrications above were built by the four
        call sites; passing the *value* and the *document* instead is what makes the
        fabrication impossible to reintroduce by editing a format string, because there is no
        format string here to edit.

        ``value_start``/``value_end`` are both ``None`` together or neither, and the ``None``
        case is legal: :func:`~extractors.signals.mentions.deferred_occurrence` then produces
        an address with no position, which is weaker - the same words elsewhere in the
        document would be one participant - and strictly better than a position that resolves
        to a different value. The JSON-LD path is the one caller that uses it, and it records
        which happened in ``extra``.
        """
        return RelationSignal(
            participants=(
                RelationParticipant(
                    mention_ref=deferred_capture(capture_ref=document_ref),
                    slot=ArgumentSlot(0),
                    # The document is the constant end; the fact hangs off it, and the
                    # markup does not order the two.
                    role_hypothesis="document",
                    ordinal=0,
                    confidence=1.0,
                ),
                RelationParticipant(
                    mention_ref=deferred_occurrence(
                        label=value_label,
                        surface=value_surface,
                        start=value_start,
                        end=value_end,
                    ),
                    slot=ArgumentSlot(1),
                    role_hypothesis=value_label,
                    ordinal=1,
                    confidence=1.0,
                ),
            ),
            kind=kind,
            relation_surface=surface,
            # Stated per read path, and the three bases are not interchangeable: a `<meta>`
            # tag is the document describing itself, a visible `Key: value` and a JSON-LD
            # scalar are key/value pairs. Passing the basis in rather than defaulting it is
            # what stops the schema.org path being filed as self-description.
            basis=basis,
            # Stated, not defaulted: a metadata field asserts nothing to deny.
            polarity=Polarity.ASSERTED,
            neighbourhood=Neighbourhood(
                characters_scanned=scanned,
                # A head is a flat list of fields, read once. No mention pair is compared at
                # all, so the honest count is a stated 0; the old `scanned // 32` counted
                # nothing anybody could check, since the 32 had no unit (FR-093).
                pairs_considered=0,
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
    "ATTRIBUTE_VALUE_LABEL",
    "BASIS_ATTRIBUTE",
    "BASIS_JSONLD",
    "BASIS_META",
    "BYLINE_LABEL",
    "CONTAINMENT_FIELDS",
    "INDEPENDENCE_FAMILY",
    "JSONLD_VALUE_LABEL",
    "MAX_PAIRS_CONSIDERED",
    "NO_CAPTURE_REF_CODE",
    "PRODUCER_REF",
    "PRODUCER_VERSION",
    "SELF_DESCRIPTION_FIELDS",
    "VALUE_LABEL",
    "MetadataExtractor",
    "meta_entries",
    "meta_pairs",
    "metadata_signals",
]
