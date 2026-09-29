"""The parser layer: a captured payload's bytes in, **records of observed structure** out.

Feature 021 brief §25 (producers sit below mention extraction and report what the bytes say),
§26 (:mod:`domain.mention_occurrence_index` is the mention seam); ``ARBITRATION`` §8;
constitution IV (fail-closed, a finding is a finding) and VI (determinism, Domain Invariant 12).

**The gap this package fills.** The transport keeps a page's bytes raw
(:class:`sources.executor.CapturePage`), which is right, and then upstream collapsed the read
into one record: a regex hit, a key-name heuristic, a type assertion, a mention and a
resolution result all arrive as ``Entity(type, value, source, context, confidence, attributes,
sources)`` with ``confidence`` defaulted to ``1.0``. Six epistemic levels in one row, with a
number nobody measured. And 23 of 146 definitions declare a parser that is the identity
function, so for those the "structured view" is the payload itself.

So this package is the instrumentation layer between the bytes and everything that would like
to believe something about them. Five modules, each with one job:

:mod:`~parsers.payload.records`
    what a record **is** — ``field | value | value_type | byte_span`` plus depth, a closed
    position label, and either a deferred occurrence address or the named reason there is none.
:mod:`~parsers.payload.detect`
    whether this payload is JSON text, decided from the **declared** content type first and a
    **declared** probe second, with the rule that decided carried on the result.
:mod:`~parsers.payload.structured`
    the generic walk: one record per value a JSON payload states, with exact byte spans, under
    three recorded ceilings.
:mod:`~parsers.payload.text`
    the route for payloads nobody declared a structure for: one record per line, claiming
    nothing about what a line means.
:mod:`~parsers.payload.binding`
    the seam: each addressable record becomes a deferred occurrence that
    :class:`domain.mention_occurrence_index.MentionOccurrenceIndex` resolves to a real ``MN-``.

**What this package will not do, stated as a list because each is a temptation a later stage
will feel.** It does not decide a type: ``value_type`` is one of five names for what the bytes
are, never "email" or "ipv4". It does not score: there is no confidence field, because upstream
defaulted one to ``1.0`` and a fabricated number is worse than an absent one. It does not
resolve: no ``MN-`` is minted here, no ``RES-``, and no graph, claim, admission or projection
symbol is imported — the records sit below the mention layer and address positions, not things.
And it does not filter: a field nobody anticipated is emitted, because a parser that decides
which fields are interesting has begun deciding what the source said.

**Determinism is structural, not a convention.** No clock, no randomness, no ``set`` and no dict
ordering on any path from bytes to records: the walk appends in document order, dispatch is over
a sorted name list, and every ``to_dict`` is in declared field order. The same body parsed twice
in two processes yields the same records in the same order — which is the property that makes an
``MN-`` usable as a join key at all (constitution VI, Domain Invariant 12).

**Where it sits.** Below the transport and below mention extraction, and therefore **not**
importing :mod:`sources` (acquisition publishes ``observation.created``; this layer reads the
published fields). The one seam it shares with the catalogue is
:data:`~parsers.payload.registry.IDENTITY_PARSER_NAMES`, which mirrors
:data:`sources.catalogue.IDENTITY_PARSERS` and is pinned against it by a test rather than
imported, because a second *definition* of the same rule in the same layer is the drift every
other module in this repository is written against.
"""

from __future__ import annotations

from parsers.payload.binding import (
    BINDING_REFUSAL_CODES,
    PAYLOAD_OCCURRENCE_KIND,
    BoundField,
    BoundPayload,
    bind_records,
    occurrence_index,
)
from parsers.payload.detect import (
    DETECTION_RULES,
    Detection,
    DetectionRule,
    declares_json,
    detect_json_text,
    media_type_essence,
    probe_json_text,
)
from parsers.payload.records import (
    ADDRESS_REFUSAL_CODES,
    ADDRESSABLE_VALUE_TYPES,
    BOUND_NAMES,
    DEFAULT_BOUNDS,
    OBSERVED_FIELD_KEY_COUNT,
    PAYLOAD_RECORD_VERSION,
    VALUE_TYPES,
    BoundHit,
    ExtractorResult,
    ObservedField,
    ParseBounds,
    ParsedPayload,
    PayloadContractError,
    PayloadLabel,
    PayloadRefusal,
    ValueType,
    address_for,
)
from parsers.payload.registry import (
    IDENTITY_PARSER_NAMES,
    ROUTING_REFUSAL_CODES,
    ParserTotality,
    PayloadParserRegistry,
    RegisteredParser,
    default_registry,
)
from parsers.payload.structured import STRUCTURED_PRODUCER, parse_structured_fields
from parsers.payload.text import TEXT_PRODUCER, parse_text_lines

__all__ = [
    "ADDRESSABLE_VALUE_TYPES",
    "ADDRESS_REFUSAL_CODES",
    "BINDING_REFUSAL_CODES",
    "BOUND_NAMES",
    "DEFAULT_BOUNDS",
    "DETECTION_RULES",
    "IDENTITY_PARSER_NAMES",
    "OBSERVED_FIELD_KEY_COUNT",
    "PAYLOAD_OCCURRENCE_KIND",
    "PAYLOAD_RECORD_VERSION",
    "ROUTING_REFUSAL_CODES",
    "STRUCTURED_PRODUCER",
    "TEXT_PRODUCER",
    "VALUE_TYPES",
    "BoundField",
    "BoundHit",
    "BoundPayload",
    "Detection",
    "DetectionRule",
    "ExtractorResult",
    "ObservedField",
    "ParseBounds",
    "ParsedPayload",
    "ParserTotality",
    "PayloadContractError",
    "PayloadLabel",
    "PayloadParserRegistry",
    "PayloadRefusal",
    "RegisteredParser",
    "ValueType",
    "address_for",
    "bind_records",
    "declares_json",
    "default_registry",
    "detect_json_text",
    "media_type_essence",
    "occurrence_index",
    "parse_structured_fields",
    "parse_text_lines",
    "probe_json_text",
]
