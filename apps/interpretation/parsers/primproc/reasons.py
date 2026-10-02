"""The vocabularies of primary processing: closed, versioned, and counted by.

Every enum here is **closed**, and that is the whole of the design. A reader asking "why was
this byte dropped?" gets exactly one of :data:`REMOVAL_REASONS`; a reader asking "why was this
payload not decoded?" gets exactly one of :data:`DECODE_REFUSALS`; a reader asking "how do you
know this text is the main content?" gets exactly one of :data:`EXTRACT_STRATEGIES`. A
vocabulary that can grow silently is a vocabulary nobody can histogram, and the question these
enums exist to answer is always asked as a count.

**Why the reasons are closed at the level of *source bytes* and not of steps.** The
alternative — recording "we removed the head, then collapsed whitespace, then dropped a nav" —
produces a report whose numbers do not add up, because the same source byte can be inside the
head *and* be whitespace. So :class:`~parsers.primproc.result.SourceSpan` is a **partition**:
every character of the decoded source is claimed by exactly one span with exactly one verdict,
and the first rule to claim a byte is the one that is recorded. The whole ledger is published,
which is what makes "this stage did not quietly eat content" a checkable claim rather than a
promised one.

**The one asymmetry, stated rather than hidden.** :attr:`RemovalReason.ENTITY_SYNTAX` is not a
removal at all — ``&amp;`` becomes ``&``, which *adds* bytes to the output. It is carried as its
own verdict (:attr:`~parsers.primproc.result.SpanVerdict.REPLACED`) so that the ledger stays a
partition, and its byte count is reported separately as
:attr:`~parsers.primproc.result.PrimaryResult.entity_expansion_bytes` rather than being mixed
into a "removed" total that would then not reconcile. That is why the span type has three
verdicts and not two.

**Provenance.** :data:`PRIMARY_PROC_VERSION` is this stage's own version and it travels on the
output and in the derived artifact's ``schema``, because §133's question — the same raw bytes
through parser v1 versus v2 — has nowhere else to put an answer. :data:`PRIMARY_PROC_SCHEMA` is
the record shape, separate from the version, so a shape change and a rule change stay
distinguishable in a stored record.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final

#: This stage's own version. Bumped when a rule changes in a way
#: :data:`PRIMARY_PROC_RULE_DIGEST_INPUTS` does not already pin, and carried on every
#: :class:`~parsers.primproc.result.PrimaryResult` and on the derived artifact's ``schema``.
PRIMARY_PROC_VERSION: Final[str] = "primproc-1"

#: The record shape a consumer reads. Separate from the version so that "the rules moved" and
#: "the fields moved" are two different facts about two stored records.
PRIMARY_PROC_SCHEMA: Final[str] = "primary-content/v1"


class RemovalReason(StrEnum):
    """Why source bytes are not in the output. Six members, closed.

    Each member is a *fact about the source*, so a caller can predict when it will fire by
    reading the source. None of them is a stage name, and none of them can absorb another's
    bytes: the partition in :mod:`parsers.primproc.result` guarantees a byte is counted once.
    """

    #: The whole element — its start tag, its text, its end tag — of an element this stage
    #: does not read. ``script``/``style``/``noscript``/``template``/``svg``/``head`` by
    #: default; the count is attributable to :data:`SKIP_TAGS` as a whole.
    SKIP_ELEMENT = "skip_element"

    #: An HTML comment, ``<!--`` and ``-->`` included. A comment is markup, not content, and a
    #: comment inside a comment (``<!-- <!-- --``) is still one comment as far as the
    #: tokenizer is concerned, so the whole span goes.
    HTML_COMMENT = "html_comment"

    #: A doctype, a processing instruction or another declaration: ``<!DOCTYPE …>``, ``<?xml …?>``
    #: and ``<!ENTITY …>``. Not a comment and not an element, so it gets its own code rather
    #: than being folded into either.
    MARKUP_DECLARATION = "markup_declaration"

    #: An attribute dropped from a kept element: ``style=`` and every ``on*=`` handler by
    #: default. Counted over the attribute's **own source span**, leading whitespace included,
    #: so the count is the bytes that left and not an estimate.
    ATTRIBUTE = "attribute"

    #: Text that was well-formed, inside the document, and outside the region the extraction
    #: strategy selected. This is the code that makes "we picked ``article``" expensive and
    #: visible instead of free and invisible — the boilerplate a content region excludes is
    #: exactly as much a transformation as a ``<script>`` is.
    OUTSIDE_MAIN = "outside_main"

    #: The angle-bracketed tag of an element whose **text** was kept: ``<div class="x">`` and
    #: its ``</div>``. Its own code rather than being folded into :attr:`ATTRIBUTE` or
    #: :attr:`SKIP_ELEMENT`, because it is the single largest transformation a markup cleaner
    #: performs and a reader asking "how much of that page was text?" needs it counted apart
    #: from the parts that were thrown away with their text.
    ELEMENT_MARKUP = "element_markup"

    #: Whitespace a kept text run lost: non-breaking spaces folded to ``U+0020``, runs of
    #: spaces and tabs collapsed to one, and the blank lines between blocks dropped. Counted
    #: on the **decoded** characters, because that is where collapsing happens.
    WHITESPACE = "whitespace"


#: Every removal reason, in declaration order. The order is also the tie-break order used when
#: two rules would claim the same byte, and it is a tuple rather than a set so no output can
#: depend on set-iteration order (constitution VI, Domain Invariant 12).
REMOVAL_REASONS: Final[tuple[RemovalReason, ...]] = tuple(RemovalReason)

#: The reason carried by a :attr:`~parsers.primproc.reasons.SpanVerdict.REPLACED` span. **Not a
#: member of** :data:`REMOVAL_REASONS`, and that exclusion is deliberate: ``&amp;`` becoming
#: ``&`` removes five source characters and *adds* one, so counting it as "removed" would make
#: ``sum(removed_bytes_by_reason)`` a number that means nothing. It is reported on its own
#: counter, :attr:`~parsers.primproc.result.PrimaryResult.entity_expansion_bytes`, and lives in
#: a one-member vocabulary of its own so that "which reasons exist" and "which counters exist"
#: stay two answerable questions.
ENTITY_SYNTAX_REASON: Final[str] = "entity_syntax"

#: Every reason a span can carry that is **not** a removal. One member, closed for the same
#: reason :data:`REMOVAL_REASONS` is.
REPLACEMENT_REASONS: Final[tuple[str, ...]] = (ENTITY_SYNTAX_REASON,)


class SpanVerdict(StrEnum):
    """What happened to one span of the decoded source. Three members, closed.

    ``KEPT`` and ``REMOVED`` are the obvious pair. ``REPLACED`` is the third because entity
    unescaping is neither: ``&amp;`` is five source characters that leave, and one output
    character that arrives. Collapsing that into ``REMOVED`` would make the byte totals lie,
    and calling it ``KEPT`` would hide a real transformation from the reader.
    """

    #: Survives into the output, possibly after whitespace normalisation, and contributes
    #: :attr:`~parsers.primproc.result.SourceSpan.output_chars` characters.
    KEPT = "kept"
    #: Left the output, counted under exactly one :class:`RemovalReason`.
    REMOVED = "removed"
    #: An entity reference's source syntax, replaced by its expansion. Carries
    #: :data:`ENTITY_SYNTAX_REASON`, which is deliberately not a :class:`RemovalReason`.
    REPLACED = "replaced"


class Route(StrEnum):
    """Which per-type path a payload took. Six members, closed.

    The point of the split is that every member is a **recorded outcome**, not an absence.
    :attr:`JSON`, :attr:`NDJSON` and :attr:`TEXT` are routes that *decided to change nothing*, and
    :attr:`PASSTHROUGH` is a route that declined to have an opinion. A cleaner that rewrites a
    JSON payload has corrupted evidence, so those four return the bytes untouched and the record
    says so, and only :attr:`HTML` and :attr:`XML` do work.
    """

    #: Real markup parsing: elements removed, main content selected, whitespace collapsed.
    HTML = "html"
    #: Real markup parsing with XML's rules — no void elements, no implied end tags, CDATA
    #: kept as text.
    XML = "xml"
    #: A JSON payload. Returned byte-identical.
    JSON = "json"
    #: Line-delimited JSON. Byte-identical.
    NDJSON = "ndjson"
    #: Declared as text. Byte-identical.
    TEXT = "text"
    #: A media type no cleaning route claims — an image, an archive, anything unaddressed here.
    #: Byte-identical, and named rather than silently treated as text, because "we did not touch
    #: this" and "we read this as text" are different statements about the same bytes.
    PASSTHROUGH = "passthrough"


class ExtractStrategy(StrEnum):
    """Which rule chose the main content. Six members, closed, and the order *is* the search.

    "We picked ``article``" and "we guessed the densest div" are different epistemic states,
    and a consumer that cannot tell them apart cannot weigh the extraction. So the strategy is
    carried on every result, the strategies are tried in :data:`EXTRACT_STRATEGIES` order, and
    the last two members are the honest admission that a guess happened:
    :attr:`DENSITY` picked a container by measuring it, and :attr:`WHOLE_DOCUMENT` found
    nothing to pick.
    """

    #: A ``<article>`` element. The page said where the content is.
    ARTICLE = "article"
    #: A ``<main>`` element. The page said where the content is.
    MAIN = "main"
    #: An element carrying ``role="main"``. The page said, by ARIA rather than by tag.
    ROLE_MAIN = "role_main"
    #: An element whose ``id``/``class`` matches the pinned content-name pattern. Borrowed from
    #: the ``adversarygraph`` donor's ``_CONTENT_RE``; the page hinted at where the content is.
    CONTENT_CLASS = "content_class"
    #: The container with the most text, measured. **A guess**, and recorded as one: the page
    #: declared nothing and the platform picked.
    DENSITY = "density"
    #: Nothing matched, so the whole document is the content. The weakest possible claim, and
    #: said out loud rather than presented as an extraction.
    WHOLE_DOCUMENT = "whole_document"


#: The search order, and the tie-break order. First match in this sequence wins, and within one
#: strategy the first element in **document order** wins — so no comparison is ever between two
#: candidates whose order depends on anything but their positions in the source.
EXTRACT_STRATEGIES: Final[tuple[ExtractStrategy, ...]] = tuple(ExtractStrategy)


class DecodeRule(StrEnum):
    """Which rule decided the charset. Three members, closed.

    There is no fourth member that guesses. That absence is the point of this module's decode
    stage: a payload nobody described, in an encoding nobody declared, is **refused by name**
    rather than run through a statistical detector that returns a plausible-looking answer
    about evidence.
    """

    #: The declared ``content_type`` carried a ``charset=`` parameter. The transport stated it.
    CONTENT_TYPE_CHARSET = "content_type_charset"
    #: No declared charset, the caller declared a probe, and a ``<meta charset>`` /
    #: ``<meta http-equiv="content-type">`` in the first bytes stated one.
    META_CHARSET = "meta_charset"
    #: Nothing was declared and the bytes are valid UTF-8. The one default, and it is stated
    #: on the record rather than assumed invisibly.
    UTF8_DEFAULT = "utf8_default"


#: Every decode rule, in precedence order.
DECODE_RULES: Final[tuple[DecodeRule, ...]] = tuple(DecodeRule)


class DecodeRefusal(StrEnum):
    """Every way decoding is refused, by name. Six members, closed.

    A refusal is a result, not an exception: :class:`~parsers.primproc.result.PrimaryResult`
    carries one and ``ok`` is ``False``, so a caller can count refusals across a corpus instead
    of catching them one at a time. :meth:`~parsers.primproc.result.PrimaryResult.require_text`
    is the fail-closed door for a caller that would rather have raised.
    """

    #: The ``charset=`` the content type declared is not a codec this interpreter knows.
    CHARSET_UNKNOWN_IN_CONTENT_TYPE = "decode_charset_unknown_in_content_type"
    #: The declared charset is known and the bytes do not decode under it.
    CHARSET_FAILED_IN_CONTENT_TYPE = "decode_charset_failed_in_content_type"
    #: A ``<meta>`` stated a charset this interpreter does not know.
    CHARSET_UNKNOWN_IN_META = "decode_charset_unknown_in_meta"
    #: The ``<meta>`` charset is known and the bytes do not decode under it.
    CHARSET_FAILED_IN_META = "decode_charset_failed_in_meta"
    #: Nothing declared a charset and the bytes are not valid UTF-8. **The mojibake refusal**:
    #: this is the case a heuristic detector would "handle" by returning a guess, and a guess
    #: about the encoding of evidence is a corruption nobody can see.
    CHARSET_UNDECLARED = "decode_charset_undeclared_and_undecodable"
    #: The body is not ``bytes``. Recorded rather than coerced, for the same reason
    #: :func:`parsers.payload.registry._as_bytes` records ``payload_not_bytes``.
    BODY_NOT_BYTES = "decode_body_not_bytes"


#: Every decode refusal, in declaration order.
DECODE_REFUSALS: Final[tuple[DecodeRefusal, ...]] = tuple(DecodeRefusal)


class NoteCode(StrEnum):
    """What the parser saw that a well-formed document would not contain.

    These are **notes, not reasons**: nothing is removed because of one, and none of them
    appears in :data:`REMOVAL_REASONS`. They are the "still yields usable text, and here is
    what was wrong with it" channel — a truncated page must produce readable text *and* be
    visibly truncated, and neither half alone is honest.
    """

    #: The source ended with elements still open.
    HTML_UNCLOSED_ELEMENT = "html_unclosed_element"
    #: An end tag arrived with no matching open element.
    HTML_UNMATCHED_END_TAG = "html_unmatched_end_tag"
    #: A start tag closed an open element by the pinned implied-end-tag table rather than by
    #: an end tag of its own. Recorded because the element's source span is then approximate,
    #: and "approximate" must be visible.
    HTML_IMPLIED_END_TAG = "html_implied_end_tag"
    #: A ``<!``, ``<?`` or ``</`` sequence survived inside a text run, which means the
    #: tokenizer did not recognise it as markup. The text is kept — it is text as far as the
    #: evidence is concerned — and the fact is recorded. Reachable because ``html.parser``
    #: hands back a declined ``<`` as a data run of its own, so the signature is a ``<`` run
    #: immediately followed by a run starting with ``!``, ``?`` or ``/``: none of those three
    #: is valid HTML outside a construct, so their appearance in text is a fact rather than
    #: a guess about the author's intent.
    HTML_MARKUP_LEFT_AS_TEXT = "html_markup_left_as_text"
    #: An element's attributes could not be matched exactly against the ones the tokenizer
    #: reported, so the whole tag was counted as markup rather than split. Every byte is
    #: still counted; the note says the split was not justified rather than presenting a
    #: number that looks like it was. The reachable trigger is a **disagreement** between
    #: this stage's attribute scanner and :mod:`html.parser` — if one of them is wrong about
    #: which attributes a tag carries, counting them individually would be counting the
    #: wrong ones.
    HTML_ATTRIBUTE_SCAN_INCOMPLETE = "html_attribute_scan_incomplete"
    #: A CDATA section, kept as text. Only reachable on the XML route; named because "the CDATA
    #: was dropped" and "the CDATA was read" are different results.
    XML_CDATA_KEPT = "xml_cdata_kept"
    #: The parser was handed a page larger than the declared bound and stopped reading it.
    #: Recorded rather than silent, for the reason :class:`BoundHit` exists.
    SOURCE_BOUND_HIT = "source_bound_hit"


#: Every note code, in declaration order.
NOTE_CODES: Final[tuple[NoteCode, ...]] = tuple(NoteCode)


#: The elements whose entire source span is removed, per the directive. ``head`` is in this set
#: because ``<title>`` is a document label rather than content, and a page whose only text
#: survives because it sat inside ``<head>`` is a page this stage should not be extracting from.
SKIP_TAGS: Final[frozenset[str]] = frozenset(
    {"script", "style", "noscript", "template", "svg", "head"}
)

#: The donor's extra "this is chrome, not content" tags (``adversarygraph``'s
#: ``_is_irrelevant_container``) and its boilerplate-name pattern, held **outside** the default
#: :data:`SKIP_TAGS` and available only when a caller opts in.
#:
#: Deliberately not the default, and that is a decision reported rather than taken silently:
#: dropping ``<nav>``/``<aside>``/``<footer>`` and every element whose class name contains
#: ``sidebar`` is a *semantic* judgement about what a page means, and the directive did not
#: authorise it. A stage that guesses about content is the failure this whole feature exists to
#: remove, so the capability is present and off. See :data:`OPT_IN_IRRELEVANT_TAGS`.
DONOR_IRRELEVANT_TAGS: Final[frozenset[str]] = frozenset({"nav", "aside"})

#: Class/id tokens the ``adversarygraph`` donor treats as chrome. Pattern text is theirs; the
#: decision to keep it off by default is this module's, and is stated in the report.
DONOR_IRRELEVANT_PATTERN: Final[str] = (
    r"\b(?:ad|ads|advert|advertisement|banner|breadcrumb|cookie|consent|footer|header|hero|"
    r"masthead|menu|nav|newsletter|promo|recommend|related|share|sidebar|social|sponsor|"
    r"subscribe|toolbar|widget)\b"
)

#: The fewest characters of surviving text an element must hold before the density strategy will
#: choose it. Pinned because "the densest container" without a floor picks the container around a
#: single character — and then reports :attr:`ExtractStrategy.DENSITY`, which reads as a measurement
#: of the page's main content when nothing was measured. Below the floor the answer is
#: :attr:`ExtractStrategy.WHOLE_DOCUMENT`, which is the honest one: no container claimed to be the
#: content, so the whole document is it.
MIN_DENSITY_CHARS: Final[int] = 24

#: The content-name pattern, borrowed from the ``adversarygraph`` donor's ``_CONTENT_RE``.
#: Matched against ``id``/``class``/``role``/``itemprop``/``data-testid`` and counted as
#: :attr:`ExtractStrategy.CONTENT_CLASS` — a hint the page gave, which is a weaker fact than a
#: tag name and is recorded as such.
CONTENT_CLASS_PATTERN: Final[str] = (
    r"\b(?:article|body-content|content-body|entry-content|main-content|markdown|post-content|"
    r"report|report-body|research|rich-text|story|threat-report)\b"
)


#: Everything this stage's output depends on, other than the bytes. Bumping any entry here is a
#: visible diff against a committed golden value rather than a silent corpus shift — the
#: mechanism ``parsers.shallow.CONFIGURATION_HASH`` uses for its rule set, applied to a cleaner
#: so that "the numbers moved" can always be answered with "a rule moved" or "it did not".
PRIMARY_PROC_RULE_DIGEST_INPUTS: Final[tuple[str, ...]] = (
    PRIMARY_PROC_VERSION,
    PRIMARY_PROC_SCHEMA,
    ",".join(str(reason) for reason in REMOVAL_REASONS),
    ENTITY_SYNTAX_REASON,
    ",".join(str(rule) for rule in DECODE_RULES),
    ",".join(str(refusal) for refusal in DECODE_REFUSALS),
    ",".join(str(code) for code in NOTE_CODES),
    ",".join(str(strategy) for strategy in EXTRACT_STRATEGIES),
    ",".join(sorted(SKIP_TAGS)),
    ",".join(sorted(DONOR_IRRELEVANT_TAGS)),
    DONOR_IRRELEVANT_PATTERN,
    CONTENT_CLASS_PATTERN,
    f"min_density_chars={MIN_DENSITY_CHARS}",
)


__all__ = [
    "CONTENT_CLASS_PATTERN",
    "DECODE_REFUSALS",
    "DECODE_RULES",
    "DONOR_IRRELEVANT_PATTERN",
    "DONOR_IRRELEVANT_TAGS",
    "ENTITY_SYNTAX_REASON",
    "EXTRACT_STRATEGIES",
    "NOTE_CODES",
    "PRIMARY_PROC_RULE_DIGEST_INPUTS",
    "PRIMARY_PROC_SCHEMA",
    "PRIMARY_PROC_VERSION",
    "REMOVAL_REASONS",
    "REPLACEMENT_REASONS",
    "SKIP_TAGS",
    "DecodeRefusal",
    "DecodeRule",
    "ExtractStrategy",
    "NoteCode",
    "RemovalReason",
    "Route",
    "SpanVerdict",
]
