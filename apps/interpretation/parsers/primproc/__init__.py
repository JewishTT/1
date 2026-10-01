"""Primary content processing: the stage that turns a captured payload into addressable content.

**What lives here and why it is not in the transport.** :mod:`apps.acquisition` keeps raw bytes
and publishes their ``content_digest`` (§61). If the transport cleaned first, that digest would
describe cleaned bytes, the original could never be re-fetched or re-parsed, and §94's "reparse
without HTTP" becomes impossible. So raw bytes live in ``AcquisitionArtifact.body``, the sink
stores them, and **this stage consumes them** — producing a derived, separately-addressable
artefact with its own digest and its own version. The transport also makes no semantic decisions:
the existing precedent is that JSON detection was moved *out* of the HTTP client for exactly this
reason, and this stage is the same kind of move.

**The three claims this package makes, and how each is checkable.**

*Parse, do not pattern-match.* A ``re.sub("<.*?>", "", …)`` cannot tell ``<div>`` from a
comparison operator, mangles ``a < b > c`` into ``ac`` and destroys ``<<SEE>>``. Every result here
comes from :class:`html.parser.HTMLParser`, which is why ``a < b > c`` survives verbatim and why a
``<script>`` element is removed with its **content** rather than with its tags.

*Every byte is accounted for.* :class:`~parsers.primproc.result.SourceSpan` is a partition of the
decoded source: the spans tile it exactly, each with one verdict and, when removed, one reason.
:attr:`~parsers.primproc.result.PrimaryResult.removed_bytes_by_reason` is that partition summed by
reason over a closed vocabulary. A cleaning stage whose effect cannot be measured is
indistinguishable from a stage that eats content, so the measurement is part of the return value.

*The result points back at the source.* :class:`~parsers.primproc.result.OutputLine` gives, for every
line of the cleaned text, the **raw-body byte range** it came from — in the codec the payload
declared, not in UTF-8. That is what lets ``apps/webapp/src/evidence/rawPayload.ts``'s line↔observation
mapping resolve against a cleaned artefact instead of a guess.

**Where the boundaries are.** This stage produces cleaner content and stops. There is no entity, no
claim, no type and no relation anywhere in this package, and no field on any type here that could
hold one — §3's boundary is enforced by the shape of the return value rather than by convention.

**What was borrowed, and what is new.** AGENTS.md §1 requires searching the donors before writing.
Two donors already ship stdlib-``HTMLParser`` text extractors and both were read before this was
written: ``donors/SYNINT/agents/commoncrawl_ingest_agent.py``'s ``_StdlibTextExtractor`` (skip tags,
``convert_charrefs``, a skip-depth counter) and
``donors/adversarygraph/backend/app/api/routes/analyze.py``'s ``_ReportHTMLParser`` (a wider skip set,
irrelevant-container heuristics, ``article``/``main`` content containers, and the ``_CONTENT_RE``
content-class pattern reused verbatim as :data:`~parsers.primproc.reasons.CONTENT_CLASS_PATTERN`).
**What no donor has** is the part this stage exists for: none of them preserves a byte offset, and
none of them accounts for its removals. The exact-span machinery, the ledger and the
strategy-with-a-name are written here.
"""

from __future__ import annotations

from parsers.primproc.decode import (
    META_PROBE_WINDOW,
    DecodeDecision,
    charset_parameter,
    decode_body,
    probe_meta_charset,
)
from parsers.primproc.markup import (
    BLOCK_TAGS,
    Construct,
    ElementSpan,
    MarkupDocument,
    Note,
    SourceIndex,
    TilingError,
    assert_tiling,
    attribute_is_dropped,
    parse_markup,
)
from parsers.primproc.processor import (
    HTML_MEDIA_TYPES,
    NDJSON_MEDIA_TYPES,
    WHITESPACE_CHARS,
    XML_MEDIA_TYPES,
    PrimaryProcessor,
    scan_tag_attributes,
    select_region,
)
from parsers.primproc.reasons import (
    CONTENT_CLASS_PATTERN,
    DONOR_IRRELEVANT_PATTERN,
    DONOR_IRRELEVANT_TAGS,
    ENTITY_SYNTAX_REASON,
    EXTRACT_STRATEGIES,
    NOTE_CODES,
    PRIMARY_PROC_RULE_DIGEST_INPUTS,
    PRIMARY_PROC_SCHEMA,
    PRIMARY_PROC_VERSION,
    REMOVAL_REASONS,
    REPLACEMENT_REASONS,
    SKIP_TAGS,
    DecodeRefusal,
    DecodeRule,
    ExtractStrategy,
    NoteCode,
    RemovalReason,
    Route,
    SpanVerdict,
)
from parsers.primproc.result import (
    OutputLine,
    PrimProcContractError,
    PrimaryResult,
    SourceSpan,
    zero_removals,
)

__all__ = [
    "BLOCK_TAGS",
    "CONTENT_CLASS_PATTERN",
    "DECODE_REFUSALS",
    "DECODE_RULES",
    "DONOR_IRRELEVANT_PATTERN",
    "DONOR_IRRELEVANT_TAGS",
    "ENTITY_SYNTAX_REASON",
    "EXTRACT_STRATEGIES",
    "HTML_MEDIA_TYPES",
    "META_PROBE_WINDOW",
    "NDJSON_MEDIA_TYPES",
    "NOTE_CODES",
    "PRIMARY_PROC_RULE_DIGEST_INPUTS",
    "PRIMARY_PROC_SCHEMA",
    "PRIMARY_PROC_VERSION",
    "REMOVAL_REASONS",
    "REPLACEMENT_REASONS",
    "SKIP_TAGS",
    "WHITESPACE_CHARS",
    "XML_MEDIA_TYPES",
    "Construct",
    "DecodeDecision",
    "DecodeRefusal",
    "DecodeRule",
    "ElementSpan",
    "ExtractStrategy",
    "MarkupDocument",
    "Note",
    "NoteCode",
    "OutputLine",
    "PrimProcContractError",
    "PrimaryProcessor",
    "PrimaryResult",
    "RemovalReason",
    "Route",
    "SourceIndex",
    "SourceSpan",
    "SpanVerdict",
    "TilingError",
    "assert_tiling",
    "attribute_is_dropped",
    "charset_parameter",
    "decode_body",
    "parse_markup",
    "probe_meta_charset",
    "scan_tag_attributes",
    "select_region",
    "zero_removals",
]
