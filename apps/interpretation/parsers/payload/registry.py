"""P1: the parser registry, and the totality contract it enforces rather than trusts.

Feature 021 brief §25; constitution IV (fail-closed) and VI (determinism, Domain Invariant 12).

**The contract, quoted from what it replaces.** ``donors/estorides/estorides_core/parsers.py``
says it in one comment: *"A parser takes whatever the HTTP client produced (dict / list / str /
None) and returns the structured view. Parsers MUST be total: any unrecognised input must
return an empty container, not raise. The orchestrator trusts this contract."* It is honoured
for roughly five of the 55 entries; the rest raise on a payload shaped differently from the
one they were written against, and the orchestrator trusts them anyway. Two failures follow:
the run dies on a source's bad day, and — worse — the unknown-name path
(``PARSERS.get(name, parse_raw_text)``) turns a **typo** into a *quiet* fallback that produces
"a less-structured observation" nobody was told about.

**What this registry does about both.**

*Totality is enforced at the seam, not asserted by comment.* :meth:`PayloadParserRegistry.parse`
wraps every extractor call, and an exception of any kind becomes a refusal with the exception's
**class name** and a zero record set — still a :class:`~parsers.payload.records.ParsedPayload`,
so a caller holding a registry cannot be handed a traceback by a payload. The exception's
*message* is deliberately not recorded: it can carry a path or an address, and this layer's
output has to be reproducible in a second process.

*Totality is also measured, so a non-total parser is visible before it runs.*:meth:`totality_report`
runs every registered parser over a caller-supplied corpus and reports, per parser and per
input, whether it returned or raised. That is the difference between a contract and a comment:
the comment is believed, the report is read. A test asserts every registered parser is total
over a hostile corpus — and a second test registers a parser that raises on purpose and
asserts the report *catches* it, because a guard that has never been observed to fail has not
been shown to guard anything.

*An unknown parser name is refused by name.* ``parser_name_unknown`` is recorded and the payload
is routed to the **text** extractor, which reports the payload's lines and claims no structure.
The alternative — the upstream fallback — reports "a less-structured observation" with nothing
saying a declared parser went missing; this one says it in a countable code. Note what this is
*not*: the registry does not substitute a parser the caller did not ask for and call it normal.
The refusal is in the record set.

**Routing, in one table, and the table is the contract.**

============================================  ==================  ======================
declared                                       detection           route
============================================  ==================  ======================
identity (flag or name)                        JSON                structured walk, + a refusal
identity (flag or name)                        not JSON            text lines
a registered parser name                       JSON                that parser
a registered parser name                       not JSON            text lines + a refusal
unregistered name                              any                 text lines + a refusal
============================================  ==================  ======================

The identity rows are P5's answer for the 23 definitions whose declared parser is the identity
function: they are recorded as identity and routed to a text extractor **unless the transport
declared a JSON media type**, in which case the structured walk reports the key paths the
payload itself states — and says, in ``declared_parser_is_identity_content_type_is_json``, that
the definition declared no parser and the transport declared the grammar. Nothing is claimed
that the bytes and the header do not state, and nothing is hidden about which rule fired.

**Determinism.** Parser dispatch iterates a sorted name list, refusals are appended in the order
the rules above are evaluated, and no clock, no randomness and no set iteration is on the path.
The same page and the same definition give the same :class:`ParsedPayload` in a second process
(constitution VI, Domain Invariant 12).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from parsers.payload.detect import Detection, detect_json_text
from parsers.payload.records import (
    DEFAULT_BOUNDS,
    ExtractorResult,
    ObservedField,
    ParseBounds,
    ParsedPayload,
    PayloadContractError,
    PayloadRefusal,
)
from parsers.payload.structured import STRUCTURED_PRODUCER, parse_structured_fields
from parsers.payload.text import TEXT_PRODUCER, parse_text_lines

#: The parser names the catalogue's :data:`sources.catalogue.IDENTITY_PARSERS` treats as "the
#: payload comes back unparsed". Mirrored here rather than imported because the parser layer
#: must not depend on the acquisition package — it runs *below* acquisition's transport, reading
#: the published observation — and a second definition of the same set in the same layer would be
#: the drift this comment exists to prevent. So the mirror is pinned: a test reads the catalogue's
#: own constant and asserts the two are equal, which makes the mirror a checked copy rather than
#: a competing rule.
IDENTITY_PARSER_NAMES: frozenset[str] = frozenset({"raw_text", "raw", "identity", "json"})

#: An extractor: bytes plus the detection decision plus the bounds in force, and records out.
#: **Total by contract** — any input returns an :class:`ExtractorResult`, never raises.
PayloadExtractor = Callable[..., ExtractorResult]

#: Every refusal this registry can add, as a closed vocabulary. The extractors have their own;
#: these are the ones only the registry can say, because they are about the *declaration*
#: rather than about the bytes.
ROUTING_REFUSAL_CODES: tuple[str, ...] = (
    "parser_name_unknown",
    "parser_name_empty",
    "parser_identity_flag_disagrees_with_name",
    "declared_parser_content_type_is_not_json",
    "declared_parser_is_identity_content_type_is_json",
    "parser_raised",
)


@dataclass(frozen=True, slots=True)
class RegisteredParser:
    """One extractor, under one name, with the totality report for it.

    ``name`` is what a definition's ``parser:`` field selects and what lands on
    :attr:`~parsers.payload.records.ParsedPayload.routed_to`, so a reader of a record always
    knows which instrument produced it.

    ``extract`` takes keyword arguments only (``body``, ``detection``, ``bounds``) so that the
    registry can call any registered extractor the same way — the alternative is a registry that
    knows each parser's signature, which is a registry that breaks when a parser is added.
    """

    name: str
    extract: PayloadExtractor

    def __post_init__(self) -> None:
        name = str(self.name).strip()
        if not name:
            raise PayloadContractError(
                "parser_name_required",
                "a registered parser with no name cannot be selected by a definition and "
                "cannot be reported on, so registering one is a mistake rather than a default",
            )
        object.__setattr__(self, "name", name)
        if not callable(self.extract):
            raise PayloadContractError(
                "parser_not_callable",
                f"the parser registered as {name!r} is {type(self.extract).__name__}, which "
                "cannot be called. The totality contract is a statement about a callable",
            )


@dataclass(frozen=True, slots=True)
class ParserTotality:
    """One measurement: this parser, this input, did it return or did it raise?

    ``raised_as`` is the exception's **class name**, not its message: a message can carry a path
    or a memory address, and a measurement of totality that cannot be reproduced in a second
    process is not a measurement.
    """

    parser: str
    corpus_index: int
    byte_length: int
    total: bool
    raised_as: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "parser": self.parser,
            "corpus_index": self.corpus_index,
            "byte_length": self.byte_length,
            "total": self.total,
            "raised_as": self.raised_as,
        }


class PayloadParserRegistry:
    """Named, total extractors, and one routing decision that records itself.

    **The registry holds extractors, not judgements.** It does not know what a domain is, does
    not know what an entity is, and cannot: it takes a body, a declared parser name, the
    definition's own identity flag and the transport's content type, and returns records of
    observed structure. There is no attribute on this class for a type hypothesis, a confidence
    or a resolution, and adding one would be the layer crossing into the next stage.

    **The two built-ins are always registered, at construction, not on first use.** A registry
    whose contents depend on whether anybody has parsed anything yet is a registry whose
    ``names()`` is a function of its own history, and a totality report taken before the first
    parse would measure a different registry from the one taken after it. So
    :meth:`names` is fixed the moment the object exists, and :func:`default_registry` is simply
    :class:`PayloadParserRegistry` with nothing added.

    Registration of anything further is explicit and a duplicate name is refused by name — two
    parsers under one name means the winner depends on import order, and a routing decision that
    depends on import order is not reproducible (constitution VI).
    """

    __slots__ = ("_parsers",)

    def __init__(self, parsers: Iterable[RegisteredParser] = ()) -> None:
        self._parsers: dict[str, RegisteredParser] = {
            name: parser for name, parser in _BUILT_INS.items()
        }
        for parser in parsers:
            self.register(parser)

    # -- registration ------------------------------------------------------ #

    def register(self, parser: RegisteredParser) -> None:
        """Add one extractor. A duplicate name is refused rather than overwritten."""
        if not isinstance(parser, RegisteredParser):
            raise PayloadContractError(
                "invalid_registered_parser",
                "register takes a RegisteredParser, got "
                f"{type(parser).__name__}",
            )
        existing = self._parsers.get(parser.name)
        if existing is not None:
            raise PayloadContractError(
                "parser_name_already_registered",
                f"{parser.name!r} is already registered. Overwriting would make the routing "
                "decision depend on import order, so the two parsers would not be a choice any "
                "caller could see or repeat. Rename one, or register it in a registry of its "
                "own",
            )
        self._parsers[parser.name] = parser

    def names(self) -> tuple[str, ...]:
        """Every registered name, sorted — the dispatch order, so it cannot depend on insertion."""
        return tuple(sorted(self._parsers))

    def get(self, name: str) -> RegisteredParser | None:
        return self._parsers.get(str(name).strip())

    # -- the totality contract --------------------------------------------- #

    def totality_report(
        self,
        corpus: Sequence[bytes],
        *,
        bounds: ParseBounds = DEFAULT_BOUNDS,
    ) -> tuple[ParserTotality, ...]:
        """Run every registered parser over ``corpus`` and report what raised.

        **Asserts totality, not success.** A parser that returns the wrong records for a hostile
        input still passes — this is a measurement of the *contract* (any input returns), not of
        the quality of the answer, and conflating the two would mean the corpus had to encode
        every expectation a parser has, which is a second specification of it.

        The report is ordered by ``(parser, corpus_index)`` over a sorted name list, so two
        processes measuring the same registry and corpus produce the same report in the same
        order.
        """
        measurements: list[ParserTotality] = []
        detection = detect_json_text(content_type="application/json", body=b"{}")
        for name in self.names():
            parser = self._parsers[name]
            for index, sample in enumerate(corpus):
                payload = bytes(sample)
                try:
                    parser.extract(body=payload, detection=detection, bounds=bounds)
                except BaseException as exc:  # noqa: BLE001 - totality is measured, not assumed
                    measurements.append(
                        ParserTotality(
                            parser=name,
                            corpus_index=index,
                            byte_length=len(payload),
                            total=False,
                            raised_as=type(exc).__name__,
                        )
                    )
                else:
                    measurements.append(
                        ParserTotality(
                            parser=name,
                            corpus_index=index,
                            byte_length=len(payload),
                            total=True,
                        )
                    )
        return tuple(measurements)

    # -- routing ------------------------------------------------------------ #

    def parse(
        self,
        *,
        body: bytes,
        content_type: str | None = None,
        declared_parser: str = "",
        parser_is_identity: bool = False,
        probe_when_undeclared: bool = False,
        bounds: ParseBounds = DEFAULT_BOUNDS,
    ) -> ParsedPayload:
        """Read one payload into records. Total: any body, any declaration, raises nothing.

        The order is the contract and is stated once, in the module docstring's table:
        **detect**, then **route**, then **extract under the bounds**, with every refusal
        appended in the order its rule was evaluated. Nothing in this method decides what a value
        *is*.
        """
        payload, refusals = _as_bytes(body)
        name = str(declared_parser or "").strip()
        detection = detect_json_text(
            content_type=content_type,
            body=payload,
            probe_when_undeclared=probe_when_undeclared,
        )
        routing: list[PayloadRefusal] = list(refusals)

        identity = bool(parser_is_identity)
        if name in IDENTITY_PARSER_NAMES and not identity:
            routing.append(
                PayloadRefusal(
                    "parser_identity_flag_disagrees_with_name",
                    f"the definition declares parser {name!r}, which is an identity parser name, "
                    "but it does not set parser_is_identity. The flag is taken as given and the "
                    "disagreement is recorded rather than resolved: picking one of the two would "
                    "be deciding what the source declared",
                )
            )
        if identity and name and name not in IDENTITY_PARSER_NAMES:
            routing.append(
                PayloadRefusal(
                    "parser_identity_flag_disagrees_with_name",
                    f"the definition sets parser_is_identity but declares parser {name!r}, "
                    "which is not an identity parser name. The flag is taken as given and the "
                    "disagreement is recorded",
                )
            )

        chosen, routing_refusals = self._route(
            name=name,
            identity=identity,
            detection=detection,
            declared_present=bool(name),
        )
        routing.extend(routing_refusals)

        result = self._extract(
            chosen, body=payload, detection=detection, bounds=bounds
        )
        return ParsedPayload(
            declared_parser=name,
            parser_is_identity=identity,
            routed_to=chosen.name,
            detection=detection,
            bounds=bounds,
            byte_length=len(payload),
            records=result.records,
            refusals=(*routing, *result.refusals),
            bound_hit=result.bound_hit,
        )

    def _route(
        self,
        *,
        name: str,
        identity: bool,
        detection: Detection,
        declared_present: bool,
    ) -> tuple[RegisteredParser, tuple[PayloadRefusal, ...]]:
        """Pick the extractor, and say everything that decided it. Sorted names, never a guess."""
        refusals: list[PayloadRefusal] = []
        text = self._parser(TEXT_PRODUCER)
        structured = self._parser(STRUCTURED_PRODUCER)
        if not declared_present:
            refusals.append(
                PayloadRefusal(
                    "parser_name_empty",
                    "the observation declares no parser name. The payload is read as text and "
                    "the missing declaration is recorded, rather than a default parser being "
                    "chosen for it",
                )
            )
        registered = self._parsers.get(name)
        unknown_name = (
            registered is None
            and declared_present
            and not identity
            and name not in IDENTITY_PARSER_NAMES
        )
        if unknown_name:
            refusals.append(
                PayloadRefusal(
                    "parser_name_unknown",
                    f"no parser is registered under {name!r}, so this definition's declared "
                    "parser has no implementation here. The payload is read as text — one record "
                    "per line, no structure claimed — and this refusal is why. Upstream fell "
                    "back to its raw-text parser silently for unknown names; a name that reaches "
                    "this registry unregistered is a missing parser, not a lesser observation",
                )
            )
        if identity:
            if detection.is_json:
                refusals.append(
                    PayloadRefusal(
                        "declared_parser_is_identity_content_type_is_json",
                        f"the definition declares parser {name or '(none)'!r}, which parses "
                        f"nothing, and the transport declared {detection.declared!r}. The "
                        "records below are the key paths the payload states and the grammar the "
                        "header declared — not a schema this source published — and the "
                        "definition is recorded as identity so nothing downstream mistakes them "
                        "for a declared structure",
                    )
                )
                return structured, tuple(refusals)
            return text, tuple(refusals)
        if registered is None:
            return text, tuple(refusals)
        if not detection.is_json:
            refusals.append(
                PayloadRefusal(
                    "declared_parser_content_type_is_not_json",
                    f"the definition declares parser {name!r} and the transport declared "
                    f"{detection.declared or '(nothing)'!r}, which the detection seam ruled "
                    f"{detection.rule}. A declared structured parser is not applied to a body "
                    "nobody declared to be JSON, so the payload is read as text and the "
                    "mismatch is recorded",
                )
            )
            return text, tuple(refusals)
        return registered, tuple(refusals)

    def _parser(self, name: str) -> RegisteredParser:
        """One of this registry's own two extractors.

        A **read**, not a lazy registration: both are registered at construction, so this cannot
        change what :meth:`names` returns and a registry built by hand behaves exactly like
        :func:`default_registry`. That is what makes "any registry is total" testable with a bare
        ``PayloadParserRegistry()``.
        """
        parser = self._parsers.get(name)
        if parser is None:  # pragma: no cover - unreachable while the built-ins are registered
            parser = _built_in(name)
        return parser

    def _extract(
        self,
        parser: RegisteredParser,
        *,
        body: bytes,
        detection: Detection,
        bounds: ParseBounds,
    ) -> ExtractorResult:
        """Call the extractor, and convert anything it raises into a refusal.

        **This is where totality is enforced rather than trusted**, and the conversion keeps the
        exception's class name and drops its message: a message can carry a path or an address,
        and this layer's output has to be reproducible in a second process (constitution VI).
        """
        try:
            result = parser.extract(body=body, detection=detection, bounds=bounds)
        except BaseException as exc:  # noqa: BLE001 - the totality contract is enforced here
            return ExtractorResult(
                records=(),
                refusals=(
                    PayloadRefusal(
                        "parser_raised",
                        f"the parser registered as {parser.name!r} raised "
                        f"{type(exc).__name__}. The parser-layer contract is total — any input "
                        "returns records — so the read is recorded as a refusal with no records "
                        "rather than propagated. Its message is not recorded: it can carry a "
                        "path or an address, and this output must be reproducible",
                    ),
                ),
                bound_hit=None,
            )
        if not isinstance(result, ExtractorResult):
            return ExtractorResult(
                records=(),
                refusals=(
                    PayloadRefusal(
                        "parser_raised",
                        f"the parser registered as {parser.name!r} returned "
                        f"{type(result).__name__}, which is not an ExtractorResult. A parser "
                        "that returns something the registry cannot read is a parser the "
                        "contract does not cover, and it is refused rather than coerced",
                    ),
                ),
                bound_hit=None,
            )
        return result


def _built_in(name: str) -> RegisteredParser:
    """The two extractors this layer ships, by name."""
    parser = _BUILT_INS.get(name)
    if parser is None:
        raise PayloadContractError(
            "parser_not_built_in",
            f"{name!r} is not one of this layer's own extractors "
            f"({TEXT_PRODUCER!r}, {STRUCTURED_PRODUCER!r})",
        )
    return parser


#: The two extractors this layer ships, built once at import so every registry holds the same
#: two objects and its ``names()`` never depends on what anybody has parsed yet.
_BUILT_INS: Mapping[str, RegisteredParser] = MappingProxyType(
    {
        TEXT_PRODUCER: RegisteredParser(name=TEXT_PRODUCER, extract=parse_text_lines),
        STRUCTURED_PRODUCER: RegisteredParser(
            name=STRUCTURED_PRODUCER, extract=parse_structured_fields
        ),
    }
)


def default_registry() -> PayloadParserRegistry:
    """The registry this layer ships: the structured walk and the text route, both total.

    **Two parsers, not ninety-two.** Every other declared name is a refusal
    (``parser_name_unknown``) and its payload is read as text. Writing one parser per source
    would be writing down what 92 APIs *probably* return — the key-name heuristic and the
    defaulted type this layer exists to remove — and a generic walk needs no hypothesis about
    any of them, because the key paths are in the payload.
    """
    return PayloadParserRegistry()


def _as_bytes(body: object) -> tuple[bytes, tuple[PayloadRefusal, ...]]:
    """``(payload, refusals)`` — coerce the body to bytes, or say why it could not be read.

    ``str`` is encoded as UTF-8 (an exact, declared encoding), ``bytes``-like is copied, and
    ``None`` is an empty payload. Anything else is refused as ``payload_not_bytes`` and read as
    empty, because the alternative — raising — is the failure this layer's contract forbids, and
    the alternative — guessing at a ``__bytes__`` — would be reading an object the caller did not
    say was a payload.
    """
    refusals: list[PayloadRefusal] = []
    if isinstance(body, bytes):
        return body, ()
    if isinstance(body, str):
        return body.encode("utf-8"), ()
    if isinstance(body, bytearray | memoryview):
        return bytes(body), ()
    if body is None:
        return b"", (
            PayloadRefusal(
                "payload_not_bytes",
                "the payload was None. That is a missing payload, not an empty one, and the "
                "difference is countable",
            ),
        )
    refusals.append(
        PayloadRefusal(
            "payload_not_bytes",
            f"the payload is {type(body).__name__}, which carries no bytes. It is read as "
            "empty and this refusal says so; coercing it would be reading an object the caller "
            "did not present as a payload",
        )
    )
    return b"", tuple(refusals)


def observed_fields_of(payload: ParsedPayload) -> tuple[ObservedField, ...]:
    """The payload's records — named so a caller never reaches into ``.records`` for the type."""
    return tuple(payload.records)


__all__ = [
    "IDENTITY_PARSER_NAMES",
    "ROUTING_REFUSAL_CODES",
    "ParseBounds",
    "ParsedPayload",
    "ParserTotality",
    "PayloadContractError",
    "PayloadParserRegistry",
    "RegisteredParser",
    "default_registry",
    "observed_fields_of",
]
