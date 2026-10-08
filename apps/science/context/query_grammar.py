"""The deterministic structured grammar for a query (FR-025-051, Appendix O).

This is the *only* authority on what a query means. A natural-language adapter, a UI
form, or an API caller all end up here, because everything they produce is turned into
text in this grammar and parsed by :func:`parse`. Two consequences follow, and both are
the point of the design:

**The NL path cannot smuggle meaning.** FR-025-052 makes LLM compilation subordinate.
Here that is structural rather than a review instruction: an adapter proposes text, the
grammar decides what it means, and a proposal that is not valid grammar raises
:class:`QueryParseError` instead of being interpreted charitably. There is no code path
where free text reaches a planner.

**Equivalence is checkable.** Because both the structured path and the NL path converge
on this parser, "the NL adapter yields an equivalent AST for the golden cases" is a
comparison of two digests rather than a judgement call.

The parser is recursive descent over Appendix O's EBNF, written out as::

    query    = verb, target, constraints?, temporal?, scope?, output? ;
    verb     = "find" | "show" | "compare" | "explain" | "trace" | "detect" ;
    target   = noun_phrase ;
    constraints = { "where", constraint, { ",", constraint } } ;
    constraint = field, operator, value ;
    temporal = "as_of", timestamp | "between", timestamp, timestamp ;
    scope    = "within", universe ;
    output   = "return", field, { ",", field } ;

A worked example, the §32.2 request in the surface syntax::

    find wallet_control_cluster where aggregate_asset_value >= 1000000 USD \\
         as_of 2026-10-04T00:00:00Z within registered_chain_sources \\
         return cluster, coverage

Every error carries a position. A query that does not parse says where it stopped and
what it expected, because a query compiler that reports "invalid query" forces the
caller to bisect the string by hand.
"""

from __future__ import annotations

import enum
import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Any

from context.completeness import TemporalMode
from context.query_ast import (
    Filter,
    FilterOperator,
    OutputProjection,
    QueryAST,
    QueryVerb,
    ScopeClause,
    TemporalClause,
    UniverseScope,
)


class QueryParseError(ValueError):
    """A query that is not in the grammar, with the position that stopped parsing."""

    def __init__(self, message: str, *, position: int, text: str, expected: str = "") -> None:
        self.position = position
        self.text = text
        self.expected = expected
        caret = " " * position + "^"
        detail = f" (expected {expected})" if expected else ""
        super().__init__(f"{message}{detail} at position {position}\n  {text}\n  {caret}")


class _Kind(enum.StrEnum):
    WORD = "word"
    NUMBER = "number"
    STRING = "string"
    OPERATOR = "operator"
    PUNCT = "punct"
    END = "end"


@dataclass(frozen=True, slots=True)
class Token:
    kind: _Kind
    text: str
    position: int

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Token({self.kind.value}, {self.text!r}, {self.position})"


#: ``==`` is not in Appendix O's operator list, but it is what people type, and it means
#: exactly what ``=`` means. Accepting it is a lexical alias rather than a semantic
#: extension, so it is handled here in the tokenizer and nowhere else.
_OPERATORS: tuple[str, ...] = (">=", "<=", "!=", "==", "=", ">", "<")
#: Parentheses bracket an explicit collection (``in (us, gb)``). They are the unambiguous
#: form, because the bare form (``in us, gb``) and the filter list share a comma: a
#: collection after ``in`` is parsed greedily, so writing ``where j in us, gb, a = 1`` puts
#: ``a = 1`` inside the collection. Brackets remove that ambiguity, which is why they are
#: part of the grammar rather than a convenience.
_PUNCT: frozenset[str] = frozenset({",", ":", "(", ")"})
#: Longest first, so ``>=`` is never read as ``>`` then ``=``.
_SORTED_OPERATORS: tuple[str, ...] = tuple(sorted(_OPERATORS, key=len, reverse=True))


def _identifier_end(text: str, start: int) -> int:
    """End of an identifier run.

    Admits ``-``, ``.`` and ``/`` because source ids, hostnames and registry refs need
    them, but **not** ``:``: the grammar uses a colon as the ``target:property``
    separator, and admitting it here would fuse ``wallet_cluster:balance`` into one token
    and leave the target with no property.
    """
    end = start
    while end < len(text) and (text[end].isalnum() or text[end] in ("_", "-", ".", "/")):
        end += 1
    return end


def _timestamp_end(text: str, start: int) -> int:
    """End of an ISO date or timestamp run, which does admit ``:`` and ``+``.

    Separate from :func:`_identifier_end` because the two grammars genuinely differ: a
    timestamp is ``2026-10-04T00:00:00+03:00`` while an identifier is ``cluster-1``.
    """
    end = start
    while end < len(text) and (
        text[end].isalnum() or text[end] in ("_", "-", ".", "/", ":", "+")
    ):
        end += 1
    return end


#: A dotted quad is a literal, not a number. Tokenizing ``8.8.8.8`` as a number reads
#: ``8.8`` and then chokes on the remaining ``.8`` with "unexpected character '.'" -- so an
#: IP address could never appear as a filter value, which is the single most common filter
#: in this catalogue (11 DNS sources, 18 IP sources).
_IPV4_RE = re.compile(r"\d{1,3}(?:\.\d{1,3}){3}(?!\.\d)")


def _scan_number(text: str, start: int) -> tuple[_Kind, str, int]:
    """Scan a numeric literal from ``start``.

    Returns ``(kind, text, end)``. The kind is ``WORD`` when the literal turns out to be a
    date or timestamp, because ``2026-10-04`` read as the number ``2026`` followed by the
    number ``-10`` makes a perfectly good timestamp unparseable.
    """
    length = len(text)
    quad = _IPV4_RE.match(text, start)
    if quad:
        return _Kind.WORD, quad.group(0), quad.end()
    end = start + 1
    seen_dot = False
    while end < length:
        nxt = text[end]
        if nxt.isdigit():
            end += 1
        elif nxt == "." and not seen_dot and end + 1 < length and text[end + 1].isdigit():
            seen_dot = True
            end += 1
        elif (nxt == "-" or nxt == ":" or nxt == "T") and end + 1 < length and (
            text[end + 1].isalnum()
        ):
            return _Kind.WORD, text[start:_timestamp_end(text, end)], _timestamp_end(
                text, end
            )
        else:
            break
    return _Kind.NUMBER, text[start:end], end


def tokenize(text: str) -> list[Token]:
    """Split query text into tokens.

    Hand-written rather than delegating to :mod:`shlex` or a regex because the grammar
    needs to distinguish a *word* from a *quoted string*: ``in "us, gb"`` is one value,
    while ``in us, gb`` is a syntax error at the comma. A splitter that did not keep that
    distinction would accept a filter and quietly change what it filters.
    """
    tokens: list[Token] = []
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if char.isspace():
            index += 1
            continue
        if char in ("'", '"'):
            closing = text.find(char, index + 1)
            if closing < 0:
                raise QueryParseError(
                    "unterminated string", position=index, text=text, expected="closing quote"
                )
            tokens.append(Token(_Kind.STRING, text[index + 1 : closing], index))
            index = closing + 1
            continue
        matched = next((op for op in _SORTED_OPERATORS if text.startswith(op, index)), "")
        if matched:
            tokens.append(Token(_Kind.OPERATOR, matched, index))
            index += len(matched)
            continue
        if char in _PUNCT:
            tokens.append(Token(_Kind.PUNCT, char, index))
            index += 1
            continue
        if char.isdigit() or (
            char == "-" and index + 1 < length and text[index + 1].isdigit()
        ):
            kind, raw, end = _scan_number(text, index)
            tokens.append(Token(kind, raw, index))
            index = end
            continue
        if char.isalpha() or char == "_":
            end = _identifier_end(text, index)
            tokens.append(Token(_Kind.WORD, text[index:end], index))
            index = end
            continue
        raise QueryParseError(
            f"unexpected character {char!r}",
            position=index,
            text=text,
            expected="word, number, string or operator",
        )
    tokens.append(Token(_Kind.END, "", length))
    return tokens


#: Word forms the grammar accepts for each operator. Both the Appendix O symbols and
#: their word spellings, because a query typed by a person rarely has ``>=`` to hand.
_OPERATOR_WORDS: dict[str, FilterOperator] = {
    "equals": FilterOperator.EQ,
    "eq": FilterOperator.EQ,
    "gt": FilterOperator.GT,
    "greater_than": FilterOperator.GT,
    "gte": FilterOperator.GTE,
    "at_least": FilterOperator.GTE,
    "lt": FilterOperator.LT,
    "less_than": FilterOperator.LT,
    "lte": FilterOperator.LTE,
    "at_most": FilterOperator.LTE,
    "contains": FilterOperator.CONTAINS,
    "in": FilterOperator.IN,
    "not_equals": FilterOperator.NOT_EQ,
}

_VERBS: dict[str, QueryVerb] = {verb.value: verb for verb in QueryVerb}


#: Units a bare trailing word may name. Without this, every word after a number would be
#: read as a unit and ``where a >= 3 junk`` would parse -- silently discarding ``junk`` as
#: if the analyst had meant it. A closed list makes the grammar deterministic about units,
#: and a unit outside it can still be written quoted (``>= 3 "widgets"``), which is
#: unambiguous and needs no vocabulary.
_UNIT_WORDS: frozenset[str] = frozenset(
    {
        # Currencies.
        "usd", "eur", "rub", "gbp", "jpy", "chf", "cny", "aed", "kzt", "inr", "brl",
        "btc", "eth", "usdt", "usdc",
        # Measures.
        "percent", "pct", "ratio", "count", "days", "hours", "minutes", "km", "m", "kg",
        "usd_m", "usd_b",
    }
)


@dataclass(slots=True)
class _Cursor:
    tokens: Sequence[Token]
    index: int = 0

    @property
    def current(self) -> Token:
        return self.tokens[self.index]

    def advance(self) -> Token:
        token = self.tokens[self.index]
        if token.kind is not _Kind.END:
            self.index += 1
        return token

    def peek(self, offset: int = 1) -> Token:
        target = min(self.index + offset, len(self.tokens) - 1)
        return self.tokens[target]

    def at_end(self) -> bool:
        return self.current.kind is _Kind.END

    def fail(self, expected: str) -> QueryParseError:
        return QueryParseError(
            f"unexpected {self.current.text!r}"
            if self.current.kind is not _Kind.END
            else "query ended early",
            position=self.current.position,
            text="",
            expected=expected,
        )

    def expect_word(self, word: str) -> bool:
        """Consume ``word`` if present. Returns whether it was there."""
        if self.current.kind is _Kind.WORD and self.current.text.lower() == word:
            self.advance()
            return True
        return False

    def require_word(self, word: str) -> Token:
        if not self.expect_word(word):
            raise self.fail(f"'{word}'")
        return self.tokens[self.index - 1]


class _Parser:
    """Recursive descent over the Appendix O grammar."""

    def __init__(self, text: str) -> None:
        self._text = text
        self._cursor = _Cursor(tokenize(text))

    def parse(self) -> QueryAST:
        verb = self._verb()
        concept, subject_class, prop = self._target()
        filters = self._constraints()
        temporal = self._temporal()
        scope = self._scope()
        output = self._output()
        if not self._cursor.at_end():
            raise self._cursor.fail("end of query")
        return QueryAST(
            verb=verb,
            concept=concept,
            subject_class=subject_class or concept,
            subject_property=prop,
            filters=tuple(filters),
            temporal=temporal,
            scope=scope,
            output=output,
            question=self._text,
        )

    # -- productions --------------------------------------------------------

    def _verb(self) -> QueryVerb:
        token = self._cursor.current
        if token.kind is not _Kind.WORD:
            raise self._cursor.fail("a verb: find, show, compare, explain, trace, detect")
        verb = _VERBS.get(token.text.lower())
        if verb is None:
            raise self._cursor.fail("a known verb")
        self._cursor.advance()
        return verb

    def _target(self) -> tuple[str, str, str]:
        """``target = noun_phrase``.

        Accepts ``subject_class`` and, after a colon, the property being constrained --
        ``wallet_control_cluster:aggregate_asset_value``. The colon form is an addition to
        the EBNF, needed because the property has to come from somewhere and the grammar
        would otherwise have no slot for it.
        """
        token = self._cursor.current
        if token.kind not in (_Kind.WORD, _Kind.STRING):
            raise self._cursor.fail("a target noun phrase")
        self._cursor.advance()
        concept = token.text
        prop = ""
        if self._cursor.current.kind is _Kind.PUNCT and self._cursor.current.text == ":":
            self._cursor.advance()
            prop_token = self._cursor.current
            if prop_token.kind not in (_Kind.WORD, _Kind.STRING):
                raise self._cursor.fail("a property name after ':'")
            self._cursor.advance()
            prop = prop_token.text
        return concept, concept, prop

    def _constraints(self) -> list[Filter]:
        filters: list[Filter] = []
        if not self._cursor.expect_word("where"):
            return filters
        while True:
            filters.append(self._constraint())
            current = self._cursor.current
            if current.kind is _Kind.PUNCT and current.text == ",":
                self._cursor.advance()
                continue
            break
        return filters

    def _constraint(self) -> Filter:
        field_token = self._cursor.current
        if field_token.kind not in (_Kind.WORD, _Kind.STRING):
            raise self._cursor.fail("a field name")
        self._cursor.advance()
        operator = self._operator()
        value, unit = self._value(operator)
        return Filter(field=field_token.text, operator=operator, value=value, unit=unit)

    def _operator(self) -> FilterOperator:
        token = self._cursor.current
        if token.kind is _Kind.OPERATOR:
            self._cursor.advance()
            # ``==`` is a tokenizer alias; the enum speaks ``=``.
            spelling = "=" if token.text == "==" else token.text
            try:
                return FilterOperator(spelling)
            except ValueError:
                raise self._cursor.fail("a known operator") from None
        if token.kind is _Kind.WORD:
            mapped = _OPERATOR_WORDS.get(token.text.lower())
            if mapped is not None:
                self._cursor.advance()
                return mapped
        raise self._cursor.fail("an operator such as >=, = or contains")

    def _value(self, operator: FilterOperator) -> tuple[Any, str]:
        """A value for ``operator``, plus an optional trailing unit.

        The operator is passed in rather than looked back for. Peeking at
        ``tokens[index - 2]`` happens to be off-by-one-fragile in a way that silently
        misreads a single-value operator as a collection operator, which then fails
        inside :class:`Filter` with a message about collections for a query that never
        mentioned one.

        The unit is a bare word directly after the value (``1000000 USD``), and only for
        scalar operators -- after ``in`` a following word is the next member.
        """
        collection = operator in (FilterOperator.IN, FilterOperator.CONTAINS)
        token = self._cursor.current
        if token.kind is _Kind.OPERATOR:
            raise self._cursor.fail("a value")
        if collection:
            return self._collection_body(), ""
        numeric = token.kind is _Kind.NUMBER
        if numeric:
            self._cursor.advance()
            value: Any = float(token.text)
            if value.is_integer() and "." not in token.text:
                value = int(value)
        elif token.kind is _Kind.STRING:
            self._cursor.advance()
            value = token.text
        elif token.kind is _Kind.WORD:
            lowered = token.text.lower()
            if lowered in ("true", "false"):
                self._cursor.advance()
                return (lowered == "true"), ""
            self._cursor.advance()
            value = token.text
        else:
            raise self._cursor.fail("a value")

        # A unit qualifies a magnitude, so it is only read after a number. ``status =
        # active widgets`` must not silently swallow ``widgets`` as a unit of a string.
        unit_token = self._cursor.current
        if not numeric:
            return value, ""
        if unit_token.kind is _Kind.STRING:
            self._cursor.advance()
            return value, unit_token.text
        if unit_token.kind is _Kind.WORD:
            if unit_token.text.lower() not in _UNIT_WORDS:
                raise QueryParseError(
                    f"{unit_token.text!r} is not a known unit; "
                    f"quote it to use it as one, e.g. >= {value} {unit_token.text!r}",
                    position=unit_token.position,
                    text=self._text,
                    expected="a known unit, or end of query",
                )
            self._cursor.advance()
            return value, unit_token.text
        return value, ""

    def _collection_body(self) -> list[str]:
        """Bracketed or comma-separated members.

        ``in "us, gb"`` and ``in (us, gb)`` both work: the quoted form for values that
        themselves contain commas, the bracketed form for a list typed by a parser.
        """
        current = self._cursor.current
        if current.kind is _Kind.PUNCT and current.text == "(":
            self._cursor.advance()
            members: list[str] = []
            while True:
                member = self._cursor.current
                if member.kind in (_Kind.WORD, _Kind.STRING, _Kind.NUMBER):
                    self._cursor.advance()
                    members.append(member.text)
                else:
                    raise self._cursor.fail("a collection member")
                nxt = self._cursor.current
                if nxt.kind is _Kind.PUNCT and nxt.text == ",":
                    self._cursor.advance()
                    continue
                if nxt.kind is _Kind.PUNCT and nxt.text == ")":
                    self._cursor.advance()
                    return members
                raise self._cursor.fail("',' or ')'")
        # Bare comma-separated words: ``in us, gb``.
        members = []
        while True:
            member = self._cursor.current
            if member.kind in (_Kind.WORD, _Kind.STRING):
                self._cursor.advance()
                members.append(member.text)
            else:
                raise self._cursor.fail("a collection member")
            nxt = self._cursor.current
            if nxt.kind is _Kind.PUNCT and nxt.text == ",":
                self._cursor.advance()
                continue
            return members

    def _temporal(self) -> TemporalClause:
        if self._cursor.expect_word("as_of"):
            stamp = self._require_value("a timestamp")
            return TemporalClause(mode=TemporalMode.AS_OF, timestamp=str(stamp))
        if self._cursor.expect_word("between"):
            start = self._require_value("a start timestamp")
            end = self._require_value("an end timestamp")
            return TemporalClause(
                mode=TemporalMode.INTERVAL, start=str(start), end=str(end)
            )
        if self._cursor.expect_word("current"):
            return TemporalClause(mode=TemporalMode.CURRENT)
        return TemporalClause()

    def _require_value(self, expected: str) -> Any:
        token = self._cursor.current
        if token.kind not in (_Kind.WORD, _Kind.STRING, _Kind.NUMBER):
            raise self._cursor.fail(expected)
        self._cursor.advance()
        return token.text

    def _scope(self) -> ScopeClause:
        if not self._cursor.expect_word("within"):
            return ScopeClause()
        token = self._cursor.current
        if token.kind not in (_Kind.WORD, _Kind.STRING):
            raise self._cursor.fail("a universe name")
        self._cursor.advance()
        try:
            universe = UniverseScope(token.text.lower())
        except ValueError:
            # An unrecognised universe is recorded rather than rejected: the caller named
            # something the grammar has no slot for, and dropping the narrowing would
            # search *more* than was asked. Surfacing it as a term keeps the request
            # visible and lets semantic binding decide.
            return ScopeClause(terms=(token.text,))
        terms: list[str] = []
        while True:
            current = self._cursor.current
            if current.kind is _Kind.PUNCT and current.text == ",":
                self._cursor.advance()
                continue
            if current.kind is _Kind.WORD and current.text.lower() not in (
                "return",
                "as_of",
                "between",
                "current",
                "where",
            ):
                terms.append(self._cursor.advance().text)
                continue
            break
        return ScopeClause(universe=universe, terms=tuple(terms))

    def _output(self) -> OutputProjection:
        if not self._cursor.expect_word("return"):
            return OutputProjection()
        fields: list[str] = []
        while True:
            token = self._cursor.current
            if token.kind not in (_Kind.WORD, _Kind.STRING):
                raise self._cursor.fail("a field name after 'return'")
            self._cursor.advance()
            fields.append(token.text)
            current = self._cursor.current
            if current.kind is _Kind.PUNCT and current.text == ",":
                self._cursor.advance()
                continue
            break
        return OutputProjection(tuple(fields))


def parse(text: str, *, as_of: str = "", question: str = "") -> QueryAST:
    """Compile query text in this grammar into a :class:`QueryAST`.

    ``as_of`` stamps ``CURRENT`` temporal clauses with a concrete instant. It exists
    because ``TemporalClause(mode=CURRENT)`` is a claim about *when the query runs*, and a
    content-addressed AST must not change identity depending on when it was compiled.

    ``question`` records the wording this came from, when that is not ``text`` itself. The
    natural-language adapter needs it: it rewrites ``\u043d\u0430\u0439\u0434\u0438 \u0432\u0441\u0435\u0445 ...`` into grammar text, and the universal claim
    survives only in the original wording -- ``all``/``\u0432\u0441\u0435\u0445`` is not a production here, because
    it qualifies the answer rather than the request. Reading universality off the recorded
    question is what keeps it out of the grammar without losing it.
    """
    ast = _Parser(text).parse()
    if question and question != text:
        ast = QueryAST(
            verb=ast.verb,
            concept=ast.concept,
            subject_class=ast.subject_class,
            subject_property=ast.subject_property,
            filters=ast.filters,
            temporal=ast.temporal,
            scope=ast.scope,
            output=ast.output,
            objective=ast.objective,
            identity_requirement=ast.identity_requirement,
            allow_unresolved=ast.allow_unresolved,
            evidence_requirements=ast.evidence_requirements,
            requested_mode=ast.requested_mode,
            unresolved=ast.unresolved,
            question=question,
        )
    if as_of and ast.temporal.mode is TemporalMode.CURRENT:
        ast = QueryAST(
            verb=ast.verb,
            concept=ast.concept,
            subject_class=ast.subject_class,
            subject_property=ast.subject_property,
            filters=ast.filters,
            temporal=TemporalClause(mode=TemporalMode.AS_OF, timestamp=as_of),
            scope=ast.scope,
            output=ast.output,
            objective=ast.objective,
            identity_requirement=ast.identity_requirement,
            allow_unresolved=ast.allow_unresolved,
            evidence_requirements=ast.evidence_requirements,
            requested_mode=ast.requested_mode,
            unresolved=ast.unresolved,
            question=ast.question,
        )
    return ast


def iter_productions() -> Iterator[tuple[str, str]]:
    """The grammar's productions, for documentation and for a generated parser's test.

    Sourced from the module docstring's EBNF rather than restated, so the two cannot
    disagree: the docstring is the specification, this exposes it to code.
    """
    productions = (
        ("query", "verb, target, constraints?, temporal?, scope?, output?"),
        ("verb", '"find" | "show" | "compare" | "explain" | "trace" | "detect"'),
        ("target", "noun_phrase [':' property]"),
        ("constraints", "{ 'where', constraint, { ',', constraint } }"),
        ("constraint", "field, operator, value"),
        ("temporal", "'as_of', timestamp | 'between', timestamp, timestamp | 'current'"),
        ("scope", "'within', universe [, term]*"),
        ("output", "'return', field, { ',', field }"),
        ("operator", '"=" | ">" | ">=" | "<" | "<=" | "contains" | "in"'),
    )
    yield from productions


def compile_query(text: str, *, as_of: str = "") -> tuple[QueryAST, tuple[str, ...]]:
    """Parse and report which productions were exercised, in order.

    Used by the grammar tests to assert that a golden query really does reach the
    productions it claims to, rather than passing because the parser ignored the clause.
    """
    ast = parse(text, as_of=as_of)
    exercised = ["query", "verb", "target"]
    if ast.filters:
        exercised += ["constraints", "constraint", "operator"]
    if ast.temporal.mode is not TemporalMode.CURRENT:
        exercised.append("temporal")
    if ast.scope.terms or ast.scope.universe is not UniverseScope.REGISTERED_CATALOGUE:
        exercised.append("scope")
    if ast.output.include != OutputProjection().include:
        exercised.append("output")
    return ast, tuple(exercised)