"""Natural language to query text, deterministically (temporary adapter, per FR-025-052).

This exists because the platform currently has no way to answer "найди всех крипто-китов
с состоянием от $1M" in the grammar's own surface syntax, and the analysis it does run
cannot start without a query. It is a **bridge, not a parser**: it recognises a closed set
of shapes and emits text that :mod:`context.query_grammar` then parses. Anything it does not
recognise is emitted verbatim and rejected *by the grammar*, so this module can never be the
reason a query means something other than what it says.

Three rules keep it honest:

**It rewrites wording, never meaning.** Every rule maps a phrasing to a grammar keyword or
extracts a literal that was already in the text. Nothing here infers a field that was not
named, and nothing supplies a value the analyst did not type.

**It refuses rather than guesses.** An unrecognised question yields the input unchanged,
which the grammar rejects. A fuzzy matcher that produced a plausible query for an
unrecognised sentence would be worse than no adapter, because the failure would only be
visible in the result.

**It is replaceable.** Every rule is a :class:`RewriteRule` with a stated pattern, and the
whole set is reported by :func:`declared_rules`. When a locally deployed LLM compiler
replaces this, the contract it must satisfy is already pinned by the grammar and by
:mod:`context.query_proposal` -- including the requirement that it propose *text*, never an
AST.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

#: How each supported intent phrase maps onto a grammar keyword. Deliberately short and
#: closed: a keyword table the user can read is a contract they can rely on, and an open
#: synonym set would make the accepted vocabulary impossible to state.
_VERB_FORMS: dict[str, str] = {
    "найди": "find",
    "найти": "find",
    "покажи": "show",
    "показать": "show",
    "сравни": "compare",
    "сравнить": "compare",
    "объясни": "explain",
    "объяснить": "explain",
    "проследи": "trace",
    "проследить": "trace",
    "выяви": "detect",
    "выявить": "detect",
    "найди и покажи": "find",
    "find": "find",
    "show": "show",
    "compare": "compare",
    "explain": "explain",
    "trace": "trace",
    "detect": "detect",
}

#: Comparison phrases to a grammar operator. Longest-first matching is done by alternation
#: order, so "не меньше" must precede "не" and "больше" precedes "больше или равно".
_COMPARATORS: tuple[tuple[str, str], ...] = (
    ("не меньше", ">="),
    ("не менее", ">="),
    ("больше или равно", ">="),
    ("не больше", "<="),
    ("не более", "<="),
    ("меньше или равно", "<="),
    ("больше чем", ">"),
    ("больше", ">"),
    ("меньше чем", "<"),
    ("меньше", "<"),
    ("равно", "="),
    ("равна", "="),
    ("равны", "="),
    ("ровно", "="),
    (">=", ">="),
    ("<=", "<="),
    ("<", "<"),
    (">", ">"),
    ("=", "="),
)

#: Currency and measure words the grammar accepts as a bare unit. Kept aligned with the
#: grammar's ``_UNIT_WORDS`` rather than duplicated loosely: a synonym here that the grammar
#: rejects turns a working question into a parse error with a confusing position.
_UNIT_ALIASES: dict[str, str] = {
    "$": "USD",
    "долларов": "USD",
    "доллара": "USD",
    "доллар": "USD",
    "долл": "USD",
    "usd": "USD",
    "евро": "EUR",
    "eur": "EUR",
    "₽": "RUB",
    "рублей": "RUB",
    "рубля": "RUB",
    "рубль": "RUB",
    "руб": "RUB",
    "процентов": "percent",
    "процента": "percent",
    "процент": "percent",
    "%": "percent",
    "биткоин": "BTC",
    "btc": "BTC",
    "ethereum": "ETH",
    "eth": "ETH",
}

#: Words that mark a universal claim. Appended to the query as a literal marker the
#: completeness layer reads, because "find all" is a claim about the *answer* and the
#: grammar has no production for it.
_UNIVERSAL_FORMS: tuple[str, ...] = (
    "всех",
    "все",
    "всё",
    "всеми",
    "каждый",
    "каждая",
    "любой",
    "any",
    "all",
    "every",
    "global",
)

_SCOPED_WORDS: tuple[str, ...] = (
    "в рамках",
    "в пределах",
    "по",
    "within",
    "in",
)

_AS_OF_RE = re.compile(
    r"(?:на|по|as of|as_of)\s+(\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?Z?)?)",
    re.IGNORECASE,
)
_BETWEEN_RE = re.compile(
    r"(?:с|между|between)\s+(\d{4}-\d{2}-\d{2})\s+(?:по|и|до|and|to)\s+(\d{4}-\d{2}-\d{2})",
    re.IGNORECASE,
)
_NUMBER_RE = re.compile(r"(\d[\d\s]*(?:[.,]\d+)?)")
_CURRENCY_PREFIX_RE = re.compile(
    r"([$€₽])\s*(\d[\d\s]*(?:[.,]\d+)?[kmb]?)|(\d[\d\s]*(?:[.,]\d+)?[kmb]?)\s*([$€₽])",
    re.IGNORECASE | re.UNICODE,
)
_FIELD_HINT_RE = re.compile(r"[A-Za-zА-я][A-Za-z0-9_]*(?:-[A-Za-z0-9_]+)*", re.UNICODE)

#: Words that join clauses rather than name anything. Removed before the target is chosen,
#: because a conjunction would otherwise be read as the thing being searched for.
_CONNECTIVES: tuple[str, ...] = (
    "с", "от", "по", "к", "у", "о", "об", "для", "и",
    "или", "а", "но",
    "с совокупным состоянием",
    "с состоянием",
    "по транзакциям", "по данным",
    "связанные с", "связанных с",
    "имеющие", "имеющих",
)


def _lower_aligned(text: str) -> str:
    """A lowercase copy that keeps a 1:1 character correspondence with ``text``.

    Every match in :func:`_assemble` is found in this copy and then sliced out of the
    *original*. Lowering the string and slicing the lowered one was what turned ``5000 USD``
    into ``5000 usd`` and ``CLUSTER-1`` into ``cluster-1`` -- a registry ref whose case
    changes names a different entity. Per-character lowering, with any character whose
    lowercase form is a different length replaced by a same-length filler, keeps the indices
    valid by construction rather than by hope.
    """
    out: list[str] = []
    for char in text:
        lowered_char = char.lower()
        out.append(lowered_char if len(lowered_char) == 1 else char)
    return "".join(out)


def _assemble(text: str) -> str:
    """Rearrange a rewritten sentence into the grammar's clause order.

    The grammar has a fixed order -- ``verb target constraints? temporal? scope? output?`` --
    while a natural sentence puts the subject last and the numbers first. Rather than
    translate word order, this takes the parts it recognises and emits them in the order the
    grammar wants: the verb; the content words before the first comparison as the target;
    from that comparison onward as ``where ...``; and an ``as_of``/``between`` clause last.

    The subject is the words between the verb and the first comparison, with connectives and
    a stray ``where`` removed. A long subject is truncated at the first connective, which is
    a real loss and is accepted: a bounded rewrite that sometimes searches less precisely
    beats an unbounded one that invents a target nobody typed.
    """
    for connective in sorted(_CONNECTIVES, key=len, reverse=True):
        text = re.sub(
            rf"(?<!\w){re.escape(connective)}(?!\w)", " ", text, flags=re.UNICODE
        )
    text = re.sub(r"\s+", " ", text).strip()
    lowered = _lower_aligned(text)

    verb_match = re.match(r"^(find|show|compare|explain|trace|detect)\s+", lowered)
    verb = "find"
    body = text
    if verb_match:
        verb = verb_match.group(1)
        body = text[verb_match.end() :]
        lowered_body = lowered[verb_match.end() :]
    else:
        lowered_body = lowered

    temporal = ""
    for marker in (" as_of ", " between "):
        if marker in lowered_body:
            # The marker is already in the body -- ``_rewrite_between`` put it there -- so it
            # is carried over, not re-emitted. Re-emitting produced "between between".
            cut = lowered_body.index(marker)
            temporal = body[cut:].strip()
            body = body[:cut].strip()
            lowered_body = lowered_body[:cut].strip()
            break

    constraint_start = None
    for operator in (">=", "<=", "!=", "=", ">", "<"):
        found = re.search(
            r"([A-Za-z\u0410-\u044f][A-Za-z0-9_]*(?:-[A-Za-z0-9_]+)*)\s*"
            + re.escape(operator)
            + r"\s",
            lowered_body,
        )
        if found and (constraint_start is None or found.start() < constraint_start):
            constraint_start = found.start()

    target = body[:constraint_start].strip() if constraint_start is not None else body.strip()
    # A leftover ``where`` sat in the target and made the grammar read the target as the
    # constraint keyword. Removed here because the assembler adds its own.
    target = re.sub(r"(?<!\w)where(?!\w)\s*", "", target, flags=re.IGNORECASE).strip()

    if constraint_start is None:
        bare = re.search(
            r"(\d[\d\s]*(?:[.,]\d+)?)\s+([A-Za-z\u0410-\u044f]{2,})", body
        )
        if bare:
            # An amount with no field named. ``compile_ast`` already resolves this by
            # defaulting the field to ``value``; doing the same here keeps the two
            # compilation paths producing one AST rather than two.
            parts = [
                verb,
                target,
                f"where value >= {bare.group(1)} {bare.group(2)}",
            ] + ([temporal] if temporal else [])
            return " ".join(part for part in parts if part)
        parts = [verb, target] + ([temporal] if temporal else [])
        return " ".join(part for part in parts if part)

    constraints = body[constraint_start:].strip()
    parts = [verb, target, f"where {constraints}"] + ([temporal] if temporal else [])
    return " ".join(part for part in parts if part)


@dataclass(frozen=True, slots=True)
class RewriteRule:
    """One named rewrite, so a change to behaviour is a visible list entry."""

    name: str
    apply: Callable[[str], str]
    description: str


def _rewrite_verbs(text: str) -> str:
    """A leading intent word becomes a grammar verb.

    Only a leading word is considered. Replacing ``найди`` anywhere in the sentence would
    rewrite a quoted phrase inside the analyst's own terms.
    """
    stripped = text.strip()
    lowered = stripped.lower()
    # Longest form first, so "найди и покажи" is not consumed by "найди".
    for form in sorted(_VERB_FORMS, key=len, reverse=True):
        if lowered.startswith(form) and (
            len(lowered) == len(form) or not lowered[len(form)].isalnum()
        ):
            remainder = stripped[len(form) :].lstrip(" ,.:;-—")
            verb = _VERB_FORMS[form]
            return f"{verb} {remainder}".strip()
    return stripped


def _rewrite_amounts(text: str) -> str:
    """Currency-prefixed amounts become ``number UNIT``.

    This is the rule that makes a Russian question parseable at all: ``$1M`` becomes
    ``1000000 USD``, because ``1M`` is not a number the grammar can read and a silent
    reinterpretation would be a guess. Suffixes are expanded explicitly (``k``, ``m``,
    ``b``) and an unrecognised suffix is left alone, so the grammar rejects it.
    """
    def _expand(value: str) -> str:
        text_value = value.replace(" ", "").replace(",", ".")
        match = re.fullmatch(r"(\d+(?:\.\d+)?)([kmb]?)", text_value, re.IGNORECASE)
        if not match:
            return value
        number = match.group(1)
        suffix = match.group(2).lower()
        multiplier = {"": 1, "k": 1_000, "m": 1_000_000, "b": 1_000_000_000}[suffix]
        if multiplier == 1:
            return number
        scaled = float(number) * multiplier
        return str(int(scaled)) if scaled.is_integer() else str(scaled)

    def _replace(match: re.Match[str]) -> str:
        prefix, prefixed_number, bare_number, bare_sign = match.groups()
        if prefix or bare_sign:
            unit = _UNIT_ALIASES.get(prefix or bare_sign, "")
            number = _expand(prefixed_number or bare_number or "")
        else:  # pragma: no cover - the pattern guarantees one branch
            unit, number = "", ""
        return f"{number} {unit}".strip() if unit else number

    return _CURRENCY_PREFIX_RE.sub(_replace, text)


def _rewrite_comparators(text: str) -> str:
    """A comparison phrase becomes its operator.

    Substitution is case-insensitive but **case-preserving** everywhere else: an earlier
    version returned ``lowered``, which silently rewrote ``5000 USD`` to ``5000 usd`` and
    ``CLUSTER-1`` to ``cluster-1``. The unit vocabulary is uppercase and the grammar matches
    it case-insensitively, but a target that is a registry ref must keep its spelling --
    case folding an identifier changes which entity it names.
    """
    for phrase, operator in _COMPARATORS:
        pattern = re.compile(re.escape(phrase), re.IGNORECASE | re.UNICODE)
        if pattern.search(text):
            return pattern.sub(operator, text)
    return text


def _rewrite_units(text: str) -> str:
    """A bare amount followed by a unit word becomes the canonical unit."""
    def _replace(match: re.Match[str]) -> str:
        number, tail = match.group(1), match.group(2)
        words = re.findall(r"[A-Za-zА-Яа-я$€₽%]+", tail)
        if not words:
            return match.group(0)
        first = words[0]
        unit = _UNIT_ALIASES.get(first.lower(), "")
        if not unit:
            return match.group(0)
        rest = tail[match.group(2).find(first) + len(first) :]
        return f"{number} {unit}{rest}"

    return re.sub(r"(\d[\d\s.]*)\s*([A-Za-zА-Яа-я$€₽%]+)", _replace, text)


def _rewrite_universal(text: str) -> str:
    """Remove a universal claim from the query text.

    The word is *removed*, not appended as a marker. Leaving it in place made it the target
    noun phrase -- ``find всех крипто-китов`` is a search for the word "всех" -- and universality is a property of the answer, not a clause of
    the request. It is detected here but conveyed by the *original* question, which the
    grammar records as ``QueryAST.question``; :func:`context.completeness.implies_universal`
    reads it from there.

    Matched on word boundaries. A substring test reads "wallets" as universal because it
    contains "all", which is the same defect already fixed once in
    :mod:`context.completeness`.
    """
    out = text
    for form in _UNIVERSAL_FORMS:
        out = re.sub(
            rf"(?<![\w]){re.escape(form)}(?![\w])", " ", out, flags=re.IGNORECASE | re.UNICODE
        )
    return re.sub(r"\s+", " ", out).strip(" ,.:;-—")


def _rewrite_as_of(text: str) -> str:
    """``на 2026-01-02`` becomes the grammar's ``as_of``."""
    match = _AS_OF_RE.search(text)
    if not match:
        return text
    stamp = match.group(1).replace(" ", "T")
    return f"{text[: match.start()]} as_of {stamp} {text[match.end() :]}".strip()


def _rewrite_between(text: str) -> str:
    """``с X по Y`` becomes the grammar's ``between``."""
    match = _BETWEEN_RE.search(text)
    if not match:
        return text
    return (
        f"{text[: match.start()]} between {match.group(1)} {match.group(2)}"
        f" {text[match.end() :]}"
    ).strip()


def _strip_filler(text: str) -> str:
    """Remove words that carry no query structure.

    Question words and politeness. Left in place they become the target noun phrase, so
    "кто владеет CLUSTER-1" compiles to a search for the word "кто".
    """
    filler = (
        "кто",
        "что",
        "где",
        "который",
        "которая",
        "которые",
        "пожалуйста",
        "please",
        "мне",
        "нам",
        "нужно",
        "надо",
        "требуется",
        "can you",
        "i need",
        "i want",
    )
    out = text
    for word in filler:
        out = re.sub(rf"(?<![A-Za-zА-Яа-я]){re.escape(word)}(?![A-Za-zА-Яа-я])", " ", out, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", out).strip(" ,.:;-—")


#: Applied in order. The order is the design: the currency rewrite must precede the unit
#: rewrite so ``$1M`` becomes a number first, and the comparator rewrite must follow the
#: amount rewrite so the operator sits next to the number it belongs to.
_RULES: tuple[RewriteRule, ...] = (
    RewriteRule("between", _rewrite_between, "``с X по Y`` -> ``between X Y``"),
    RewriteRule("as_of", _rewrite_as_of, "``на <дата>`` -> ``as_of <stamp>``"),
    RewriteRule("verbs", _rewrite_verbs, "leading intent word -> grammar verb"),
    RewriteRule("strip_filler", _strip_filler, "question and politeness words removed"),
    RewriteRule("amounts", _rewrite_amounts, "``$1M`` -> ``1000000 USD``"),
    RewriteRule("units", _rewrite_units, "amount followed by a unit word -> canonical unit"),
    RewriteRule("comparators", _rewrite_comparators, "comparison phrase -> operator"),
    RewriteRule("universal", _rewrite_universal, "universal claim word removed from the target"),
    RewriteRule("assemble", _assemble, "parts reordered into the grammar's clause order"),
)


def declared_rules() -> tuple[RewriteRule, ...]:
    """Every rule, in application order. The replaceable surface of this adapter."""
    return _RULES


def compile_natural_language(question: str) -> str:
    """Rewrite a natural-language question into grammar text.

    Returns the rewritten text, which may still be rejected by the grammar. That is
    deliberate: this adapter proposes, and :mod:`context.query_grammar` disposes. A caller
    that wants the AST must go through :func:`context.query_proposal.compile_proposal`.
    """
    text = str(question or "").strip()
    if not text:
        return ""
    for rule in _RULES:
        text = rule.apply(text)
    return re.sub(r"\s+", " ", text).strip()


def compile_to_ast(question: str) -> tuple[Any, ...]:
    """Compile and parse in one step. Returns ``(ast, rewritten_text)``.

    ``ast`` is ``None`` when the grammar rejected the rewrite. Returning both lets a caller
    record *what* it proposed alongside the refusal, which is what
    :mod:`context.query_proposal` needs to make a natural-language compile replayable.
    """
    from context.query_grammar import QueryParseError, parse

    rewritten = compile_natural_language(question)
    if not rewritten:
        return None, rewritten
    try:
        # The original wording is recorded on the AST, so a universal claim survives the
        # rewrite even though the word itself is removed from the query text.
        return parse(rewritten, question=question), rewritten
    except QueryParseError:
        return None, rewritten


def candidate_terms(question: str) -> tuple[str, ...]:
    """Identifier-shaped words in the question, for use as a fallback target.

    A word that looks like an identifier or a proper noun is a plausible thing to search
    for, and naming it as the target lets a question like "кто владеет CLUSTER-1" produce
    ``find CLUSTER-1`` instead of nothing. Deliberately conservative: a bare lowercase word
    is not treated as a term, because guessing those produces searches nobody asked for.
    """
    terms: list[str] = []
    for token in re.split(r"[\s,.;:!?()\[\]{}\"'«»]+", str(question or "")):
        candidate = token.strip("«»\"'")
        if not candidate:
            continue
        looks_like_field = _FIELD_HINT_RE.fullmatch(candidate) and (
            candidate.isupper() or any(ch.isdigit() for ch in candidate)
        )
        if looks_like_field and candidate not in terms:
            terms.append(candidate)
    return tuple(terms)


def fallback_query_text(question: str) -> str:
    """A grammar query built from an identifier-shaped term, when rewriting is not enough.

    Still a proposal, still subject to the grammar. It exists so a question naming a concrete
    subject produces *some* search rather than none -- and it is deliberately minimal, so a
    fallback never becomes the primary path by being more capable.
    """
    terms = candidate_terms(question)
    if not terms:
        return compile_natural_language(question)
    rewritten = compile_natural_language(question)
    for term in terms:
        if re.search(rf"(?<![A-Za-z0-9_]){re.escape(term)}(?![A-Za-z0-9_])", rewritten):
            return rewritten
    return f"find {terms[0]}"


def compile_with_fallback(question: str) -> tuple[Any, ...]:
    """``compile_to_ast``, then the fallback, returning ``(ast, text)``.

    Reported honestly: the caller can tell which path produced the AST because the returned
    text differs, so a question that only ever works through the fallback is visible rather
    than silently degrading.
    """
    ast, rewritten = compile_to_ast(question)
    if ast is not None:
        return ast, rewritten
    text = fallback_query_text(question)
    if not text or text == rewritten:
        return None, rewritten
    from context.query_grammar import QueryParseError, parse

    try:
        return parse(text, question=question), text
    except QueryParseError:
        return None, rewritten


def rules_table() -> list[dict[str, str]]:
    """The rules as data, for documentation and for a golden-case report."""
    return [
        {"name": rule.name, "description": rule.description, "order": str(index)}
        for index, rule in enumerate(_RULES)
    ]


def known_verbs() -> Sequence[str]:
    return tuple(sorted(_VERB_FORMS))


def known_units() -> Sequence[str]:
    return tuple(sorted(set(_UNIT_ALIASES.values())))
