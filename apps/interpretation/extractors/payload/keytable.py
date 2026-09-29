"""The type-hypothesis table: **a declared, versioned, inspectable list, and no fuzzy fallback**.

Feature 021 brief §16 (how do you know?), §25 (a producer below mention extraction);
constitution IV (fail-closed) and VI (determinism, Domain Invariant 12).

**What this table replaces.** Upstream decided a field's type from its *name*: the defect this
whole chain exists to remove is one regex hit on a key producing an ``Entity(type="email", …,
confidence=1.0)`` row. A heuristic is the wrong shape for that constraint in two separate ways, and
this module answers each.

**A key is one token, and matching is equality.** :func:`rule_for_key` normalises (NFKC, casefold,
trim) and does one dictionary lookup. There is no substring test, no prefix, no suffix, no stemmer,
no edit distance and no nearest-match fallback — so ``"email" in "user_email"`` is not a near
miss, it is a different key, and the three ambiguity cases (``user_email``, ``email_verified``,
``email_count``) all yield **no hypothesis and a named refusal**. Splitting ``user_email`` into
``user`` and ``email`` would look like parsing and is the same match wearing a tokeniser; the
platform has no standing to invent a token the payload did not contain. Casefolding and trimming
canonicalise *one word* — the platform's own :func:`semantic.vocabularies.normalize_surface_form`
folds case for the same reason — and are the only normalisation applied.

**Two epistemic levels, and they are structurally different rather than differently labelled.**
:attr:`BasisOrigin.KEY_SPELLING` binds a **word** (one key segment): a rule of this kind says "the
platform has seen sources call this field ``email``", which is a reading of a name and nothing
more. :attr:`BasisOrigin.DECLARED_SCHEMA` binds a **place** (a whole key path): a rule of this kind
says "this source publishes a schema saying that path holds that type", which is a declaration by
the source about itself. :meth:`KeyTypeRule.__post_init__` refuses a row whose key shape does not
match its origin, so a schema can never be consulted with a word and a spelling can never be
consulted with a path.

:data:`DEFAULT_DECLARED_SCHEMAS` is **empty**: the catalogue's 146 definitions publish no
machine-readable schema this layer can read, so the schema level is reachable only by a caller who
has been handed one. Shipping an invented schema would be the same forgery as a heuristic, wearing a
version number and a URL nobody could fetch.

**A number is not a licence.** No shipped row admits :attr:`ValueType.NUMBER`, and
:func:`extractors.payload.hypotheses.read_type_hypotheses` records
``numeric_semantics_require_declared_schema`` for every number the tables did not cover. ``8080``
under a key ``port`` is a number; calling it a port needs a source-published schema saying that
path is a port, and nothing else will do.

**Every row names its own confidence, and ``1.0`` is refused.** :attr:`KeyTypeRule.confidence` has
**no default** — it is a required field, so the inherited ``1.0`` on
:class:`semantic.blocking.TypeHypothesis` is unreachable from a row. Beyond that, a row declaring
``1.0`` is refused with ``key_rule_confidence_is_a_certainty``, which is the mechanical reason a
construction that forgets to pass its confidence cannot accidentally agree with a declared row.
The reason is principled rather than superstitious: a key-name rule, or even a source-published
schema, is evidence about what the source *says the field is for*, and neither is proof that the
mention is of that type. That sentence is what upstream wrote as ``confidence=1.0``.

**The numbers are declared, not measured, and saying so is the point.**
:data:`SPELLING_CONFIDENCE` and :data:`DECLARED_SCHEMA_CONFIDENCE` are the two constants the
shipped rows and the documented schema rows use. Nothing here measures how often a key named
``email`` holds an address, and a number that pretended otherwise would be the same defect one
level up. They are published so they can be argued with and overridden row by row, and a schema
outranks a spelling because a source's declaration about one of its own paths is stronger evidence
than a word anybody chose — a claim about the *evidence*, not a number anybody earned.

**Versioning.** :data:`KEY_TYPE_TABLE_VERSION` is in every citation, so a stored hypothesis can be
checked against the table that produced it. Adding a row, retracting one or moving a number is a
table change and bumps it. A retraction is not a deletion: a rule that stops applying simply stops
matching, and the refusal says so by name.

**Determinism is structural.** :data:`KEY_TYPE_RULES` is a tuple in declaration order,
:data:`KEY_RULE_LOOKUP` is a read-only mapping built once from it and never iterated, and no value
on any path is derived from a clock, a random source or a ``set``.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from semantic.contracts import SemanticRef

from parsers.payload import ValueType

#: The version of :data:`KEY_TYPE_RULES`. It is in every ``HypothesisCitation``, so a stored
#: hypothesis can be checked against the table that produced it. Bump it on any change to a row: a
#: new key, a retracted key, a moved number, a widened value-type set.
KEY_TYPE_TABLE_VERSION = "1"

#: What a whole key segment is matched **on** — equality, and nothing weaker. Published as a name
#: so the property can be asserted rather than the implementation: the prohibition is "only
#: ``EQUALITY`` is permitted", and a second match mode added later becomes a reviewable act.
KEY_MATCH_EQUALITY = "equality"

#: The whole match vocabulary. A closed one-member enumeration, so "a match mode was added" is a
#: change to a list a reader can print rather than a diff buried in a function body.
KEY_MATCH_MODES: tuple[str, ...] = (KEY_MATCH_EQUALITY,)

#: Characters that would turn a spelling key into a pattern. Refused in every **spelling** row, so
#: a table cannot grow a glob by typing one into a string literal, and so "the table matches
#: patterns" can be ruled out by inspecting one rule rather than by reading the matcher. A
#: *declared-schema* row is exempt: its key is a path compared by equality, a ``*`` inside one of
#: its quoted segments is a character the source published, and inventing a pattern there would
#: mean the source published one.
KEY_WILDCARDS: frozenset[str] = frozenset({"*", "?", "%", "|"})

#: The prefix a **key path** begins with, in the grammar
#: :func:`parsers.payload.structured.child_path` writes. Structural rather than a flag: the two
#: levels differ by what they bind, and "binds a place" is exactly "is a path".
_PATH_PREFIX = "$["

#: The confidence a **key-spelling** row declares. Exposed because a caller comparing two
#: hypotheses needs to know what the weaker level is worth, and hiding it in a literal would make
#: the two levels indistinguishable in the output.
#:
#: **A declared constant, not a measurement.** Nothing in this repository measures how often a key
#: named ``email`` holds an address, and a number that pretended to have been measured would be the
#: defect this table exists to remove, one level up. It is published so it can be argued with and
#: overridden row by row, and it is strictly below certainty because no row may be a certainty.
SPELLING_CONFIDENCE = 0.5

#: The confidence a **declared schema** row declares. Higher than :data:`SPELLING_CONFIDENCE`
#: because the evidence is stronger: a source's declaration about one of its own paths outranks a
#: word somebody chose. **Also not a measurement**, and also not ``1.0`` — see
#: :meth:`KeyTypeRule.__post_init__`, which refuses a certainty.
DECLARED_SCHEMA_CONFIDENCE = 0.9


class KeyTypeRuleError(ValueError):
    """A row of the type-hypothesis table is not usable, and is refused with a stable code.

    A ``ValueError`` carrying snake_case ``.code``, matching
    :class:`parsers.payload.records.PayloadContractError`,
    :class:`domain.predicate_hypothesis.PredicateContractError` and the rest of the platform, so a
    caller can switch on any of them by ``.code`` rather than by type. Every code here is
    fail-closed: the alternative to a named refusal is a row that silently never matches, and a
    rule that never matches is a field the platform reports as having no type hypothesis for a
    reason nobody can see.
    """

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")


def normalise_key(key: str) -> str:
    """The canonical form of a key **for matching**: NFKC, casefold, trim — and nothing else.

    Three operations, each canonicalising one word rather than searching for a relation between
    words:

    * NFKC, so ``ｅｍａｉｌ`` (fullwidth) meets ``email``. The two render identically and a payload
      writing the fullwidth form is writing the same word.
    * casefold, so ``Email`` and ``EMAIL`` meet — one word in two cases, and the platform's own
      :func:`semantic.vocabularies.normalize_surface_form` folds case for the same reason.
    * trim, so a key with a stray space is the key without it.

    Deliberately **not** done, each because it is the upstream defect wearing different clothes:
    splitting on ``_`` or ``-``, stripping affixes, stemming, substring search, and any notion of
    distance. ``user_email`` is one token and is not ``email``.
    """
    return unicodedata.normalize("NFKC", str(key or "")).strip().casefold()


def looks_like_path(key: str) -> bool:
    """Whether ``key`` is a key **path** rather than a bare key segment.

    The grammar is :func:`parsers.payload.structured.child_path`'s: ``$`` then a bracketed segment.
    Reading it as a shape rather than asking the origin is what makes the two levels a structural
    distinction — a row cannot claim to be about a place while carrying a word.
    """
    return str(key or "").startswith(_PATH_PREFIX)


class BasisOrigin(StrEnum):
    """Which epistemic level proposed a type, in the vocabulary a reader needs to weigh it.

    Closed, and closed for the reason :class:`domain.signal_basis.SignalBasis` is: a level nobody
    can enumerate is a level nobody can audit. This is the same question one step earlier in the
    chain — "how do you know this is an email?" before "how do you know these two are related?".

    - :attr:`KEY_SPELLING` — a whole key segment equals a word the platform has a rule for. The
      evidence is a *name*. ``{"user_email": …}`` is not covered, because the segment is not the
      word and the platform did not write the key.
    - :attr:`DECLARED_SCHEMA` — a whole key **path** is bound by a schema the source published. The
      evidence is the source's own declaration about that place.
    """

    KEY_SPELLING = "key_spelling"
    DECLARED_SCHEMA = "declared_schema"


@dataclass(frozen=True, slots=True)
class KeyTypeRule:
    """One row: ``this word`` or ``this path`` proposes ``this type``, this strongly.

    ``key``, ``type_ref`` and ``confidence`` are **required and have no defaults**, and the reason
    is the whole of :attr:`confidence`: a row cannot exist without a number, and the number lives
    in a versioned, inspectable table rather than at a call site. A reader can open this file,
    read every confidence in it, and disagree with any of them without reading a function.

    :attr:`value_types` is the second guard, and it is the one people forget: a rule for ``email``
    admits ``string`` only, so ``{"email": 5}`` is a named mismatch rather than an email whose
    value happens to be a number.
    """

    key: str
    type_ref: str
    confidence: float
    value_types: tuple[ValueType, ...] = (ValueType.STRING,)
    scheme: SemanticRef = SemanticRef.INTERNAL
    rule_id: str = ""
    origin: BasisOrigin = BasisOrigin.KEY_SPELLING
    schema_ref: str = ""
    note: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "key", str(self.key or ""))
        object.__setattr__(self, "type_ref", str(self.type_ref or "").strip())
        object.__setattr__(self, "rule_id", str(self.rule_id or "").strip())
        object.__setattr__(self, "schema_ref", str(self.schema_ref or "").strip())
        object.__setattr__(self, "note", str(self.note or ""))
        object.__setattr__(self, "origin", BasisOrigin(self.origin))
        object.__setattr__(self, "scheme", SemanticRef(self.scheme))
        if not self.key:
            raise KeyTypeRuleError(
                "key_rule_key_required",
                "a row governs a key or a path, and '' governs nothing. A row that can never match "
                "is a field the platform reports as having no hypothesis for a reason nobody can "
                "see",
            )
        if not self.type_ref:
            raise KeyTypeRuleError(
                "key_rule_type_ref_required",
                f"the row for {self.key!r} proposes no type reference",
            )
        path_shaped = looks_like_path(self.key)
        if self.origin is BasisOrigin.KEY_SPELLING:
            stray = sorted(KEY_WILDCARDS & set(self.key))
            if stray:
                raise KeyTypeRuleError(
                    "key_rule_wildcard_refused",
                    f"the spelling row {self.rule_id!r} binds {self.key!r}, which contains "
                    f"{stray}. A key is one token compared by equality; a wildcard makes it a "
                    "pattern, and a pattern in this table is the key-name heuristic this layer "
                    "exists to remove",
                )
        if self.origin is BasisOrigin.DECLARED_SCHEMA and not path_shaped:
            raise KeyTypeRuleError(
                "key_rule_key_shape_mismatch",
                f"the declared-schema row {self.rule_id!r} binds {self.key!r}, which is a bare "
                "key. A schema declares things about places in a document, so its rows are whole "
                "key paths; a bare key is a word, and a word is shared by every payload that uses "
                "it. If the source really publishes this for one field only, publish its path",
            )
        if self.origin is BasisOrigin.KEY_SPELLING and path_shaped:
            raise KeyTypeRuleError(
                "key_rule_key_shape_mismatch",
                f"the key-spelling row {self.rule_id!r} binds the path {self.key!r}. A spelling "
                "rule is about a word the key is written with and applies wherever that word "
                "appears; binding a place is a declaration about a document, which is what a "
                "published schema does",
            )
        if self.origin is BasisOrigin.DECLARED_SCHEMA and not self.schema_ref:
            raise KeyTypeRuleError(
                "key_rule_schema_ref_required",
                f"the declared-schema row {self.rule_id!r} names no schema_ref, so a hypothesis "
                "would cite a level of evidence with nothing behind it. Name the document the "
                "source published",
            )
        if self.key != normalise_key(self.key):
            raise KeyTypeRuleError(
                "key_rule_key_not_canonical",
                f"the row for {self.key!r} is not in canonical form "
                f"({normalise_key(self.key)!r}). A row that can never match its own key is a "
                "typo, and a typo in a lookup table is a silent absence",
            )
        if not self.value_types:
            raise KeyTypeRuleError(
                "key_rule_value_types_required",
                f"the row {self.rule_id!r} admits no value type, so it cannot govern any record. "
                "A row with nothing to apply to is a rule that was retracted by accident; delete "
                "it and bump the table version",
            )
        object.__setattr__(self, "value_types", tuple(ValueType(v) for v in self.value_types))
        try:
            confidence = float(self.confidence)
        except (TypeError, ValueError) as exc:
            raise KeyTypeRuleError(
                "key_rule_confidence_type",
                f"the row {self.rule_id!r} declares confidence={self.confidence!r}, which is not "
                "a number. A strength-of-suggestion nobody can compare is not a strength",
            ) from exc
        if not 0.0 < confidence < 1.0:
            raise KeyTypeRuleError(
                "key_rule_confidence_is_a_certainty",
                f"the row {self.rule_id!r} declares confidence={confidence!r}. No type hypothesis "
                "in this platform is a certainty: a key-name rule, or even a source-published "
                "schema, is evidence about what the source *says the field is for*, and neither "
                "is proof that the mention is of that type. This is the number upstream wrote as "
                "Entity(confidence=1.0) on a regex hit, and 0.0 is not the answer either - a "
                "hypothesis nobody holds is an absent hypothesis, not a certain non-hypothesis. "
                "Declare a strength strictly between 0 and 1",
            )
        object.__setattr__(self, "confidence", confidence)
        # Last, and the order is the argument: a row is checked for whether it is *usable* before
        # it is checked for whether it is *labelled*. A row declaring ``1.0`` is reported as
        # declaring ``1.0`` rather than as missing a name, so the refusal a caller reads names the
        # actual defect — and ``rule_id`` being defaulted-and-then-refused is deliberate, the same
        # shape as ``ObservedField.address`` / ``address_refusal``: an empty value that a
        # constructor check turns into a named refusal rather than a silent default.
        if not self.rule_id:
            raise KeyTypeRuleError(
                "key_rule_id_required",
                f"the row for {self.key!r} has no rule_id, and a citation that cannot name its row "
                "is a claim with no evidence attached",
            )

    @property
    def path_bound(self) -> bool:
        """Whether this row binds a place rather than a word. Mirrors the origin, derived."""
        return looks_like_path(self.key)

    def admits(self, value_type: ValueType) -> bool:
        """Whether the row governs a record of this observed value type.

        The second guard against a confident wrong answer: a rule for ``email`` that also admitted
        ``number`` would let ``{"email": 5}`` produce an address hypothesis, and a hypothesis about
        a mention of what the platform cannot see is worse than none.
        """
        return ValueType(value_type) in self.value_types

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "key": self.key,
            "type_ref": self.type_ref,
            "scheme": str(self.scheme),
            "confidence": self.confidence,
            "value_types": [str(v) for v in self.value_types],
            "origin": str(self.origin),
            "schema_ref": self.schema_ref,
            "admissible_value_types": len(self.value_types),
            "note": self.note,
            "table_version": KEY_TYPE_TABLE_VERSION,
        }

    def __str__(self) -> str:  # pragma: no cover - a rendering, not behaviour
        return f"{self.rule_id}:{self.key}->{self.type_ref}@{self.confidence}"


@dataclass(frozen=True, slots=True)
class DeclaredSchema:
    """A schema **a source published**, and the only thing that may bind a number's meaning.

    Three facts make this a distinct object rather than a flag on :class:`KeyTypeRule`:

    * It is somebody else's document. ``schema_ref`` is required and is the citation a hypothesis
      carries, because "the source says this path is an address" is a claim about a document the
      platform did not write, and a reader must be able to fetch it.
    * It is versioned independently of the platform's table, so a source may revise its schema
      without a platform release, and a stored citation can say which revision was read.
    * Its rows may not name another schema and may not be spelling rules. A schema carrying
      somebody else's rows is a schema nobody maintains, and two documents claiming one ref is the
      collision the ref exists to prevent.
    """

    schema_ref: str
    version: str
    rules: tuple[KeyTypeRule, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "schema_ref", str(self.schema_ref or "").strip())
        object.__setattr__(self, "version", str(self.version or "").strip())
        if not self.schema_ref:
            raise KeyTypeRuleError(
                "declared_schema_ref_required",
                "a schema is somebody else's document and a hypothesis that cites one must name "
                "it. '' names a document nobody can fetch, which is the same as citing nothing",
            )
        if not self.version:
            raise KeyTypeRuleError(
                "declared_schema_version_required",
                f"the schema {self.schema_ref!r} states no version, so a stored citation cannot "
                "say which revision of it was read",
            )
        object.__setattr__(self, "rules", tuple(self.rules or ()))
        for rule in self.rules:
            if rule.origin is not BasisOrigin.DECLARED_SCHEMA:
                raise KeyTypeRuleError(
                    "declared_schema_rule_is_not_declared",
                    f"the row {rule.rule_id!r} in schema {self.schema_ref!r} is a key-spelling "
                    "rule. A published schema declares places in a document; a word is the "
                    "platform's own reading, and putting it here would credit a source's document "
                    "with a guess the platform made",
                )
            if rule.schema_ref != self.schema_ref:
                raise KeyTypeRuleError(
                    "declared_schema_foreign_rule",
                    f"the row {rule.rule_id!r} in schema {self.schema_ref!r} cites "
                    f"{rule.schema_ref!r}. A schema holding another schema's rows is a schema "
                    "nobody maintains, and two documents claiming one ref is the collision the "
                    "ref exists to prevent",
                )

    def rules_for(self, key_path: str) -> tuple[KeyTypeRule, ...]:
        """The rows binding ``key_path`` exactly, in declaration order.

        Equality on the whole path, by the same rule and for the same reason as
        :func:`rule_for_key`: a schema is a document about places, and a place is a whole path. A
        path-prefix match would be a guess with a uniform on it, and the key's whole reason for
        existing is that it is not one.
        """
        return tuple(rule for rule in self.rules if rule.key == str(key_path or ""))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_ref": self.schema_ref,
            "version": self.version,
            "rules": [rule.to_dict() for rule in self.rules],
        }


# --------------------------------------------------------------------------- #
# The table
# --------------------------------------------------------------------------- #

#: Every key whose spelling the platform is licensed to read, at version
#: :data:`KEY_TYPE_TABLE_VERSION`.
#:
#: **Every row admits :attr:`ValueType.STRING` only, and not one of them admits
#: :attr:`ValueType.NUMBER`.** The first half is the value-type guard. The second half is a
#: decision, and a test pins it: a number under an unknown key yields
#: ``numeric_semantics_require_declared_schema`` and nothing else, because ``8080`` is a number and
#: calling it a port needs a source that says so.
#:
#: **What is deliberately absent, and why each absence was worth a row.** ``name`` (a person's
#: name in perhaps half the payloads that use it, a company's in the rest), ``id`` (an identifier,
#: a primary key, an OAuth client id, a database id), ``type``, ``title``, and every measurement
#: word: ``count``, ``port``, ``lat``, ``lon``, ``size``, ``price``, ``score``, ``ratio``,
#: ``timeout``. Each would have been a row with a number attached to a guess, and each is the
#: exact shape of the defect.
#:
#: The rows that *are* here are the ones where the key is the lexical name of a thing the platform
#: already has an inventory of and the alternative readings are not on the table: a field called
#: ``email`` is an address or it is a field called ``email``. That is a weaker claim than it sounds
#: and :data:`SPELLING_CONFIDENCE` says so — not certainty.
KEY_TYPE_RULES: tuple[KeyTypeRule, ...] = (
    KeyTypeRule(
        key="email",
        type_ref="email_address",
        confidence=SPELLING_CONFIDENCE,
        value_types=(ValueType.STRING,),
        rule_id="spelling.email",
        note="the whole key segment is the lexical name of an address",
    ),
    KeyTypeRule(
        key="email_address",
        type_ref="email_address",
        confidence=SPELLING_CONFIDENCE,
        value_types=(ValueType.STRING,),
        rule_id="spelling.email_address",
        note="the long spelling of the same word; a separate row because the table compares whole "
        "segments and these are two keys a source may use",
    ),
    KeyTypeRule(
        key="url",
        type_ref="url",
        confidence=SPELLING_CONFIDENCE,
        value_types=(ValueType.STRING,),
        rule_id="spelling.url",
    ),
    KeyTypeRule(
        key="uri",
        type_ref="uri",
        confidence=SPELLING_CONFIDENCE,
        value_types=(ValueType.STRING,),
        rule_id="spelling.uri",
    ),
    KeyTypeRule(
        key="hostname",
        type_ref="dns_hostname",
        confidence=SPELLING_CONFIDENCE,
        value_types=(ValueType.STRING,),
        rule_id="spelling.hostname",
    ),
    KeyTypeRule(
        key="ipv4",
        type_ref="ipv4_address",
        confidence=SPELLING_CONFIDENCE,
        value_types=(ValueType.STRING,),
        rule_id="spelling.ipv4",
    ),
    KeyTypeRule(
        key="ipv6",
        type_ref="ipv6_address",
        confidence=SPELLING_CONFIDENCE,
        value_types=(ValueType.STRING,),
        rule_id="spelling.ipv6",
    ),
    KeyTypeRule(
        key="phone",
        type_ref="phone_number",
        confidence=SPELLING_CONFIDENCE,
        value_types=(ValueType.STRING,),
        rule_id="spelling.phone",
    ),
)

#: Read-only view of :data:`KEY_TYPE_RULES` by key, built once and **never iterated**. It exists
#: so :func:`rule_for_key` is a single lookup with no branch to delete, which is the mechanical
#: form of the guessing prohibition rather than a promise in a comment.
KEY_RULE_LOOKUP: MappingProxyType[str, KeyTypeRule] = MappingProxyType(
    {rule.key: rule for rule in KEY_TYPE_RULES}
)

#: The schemas the platform itself publishes. **Empty, and pinned by a test.**
#:
#: The catalogue's 146 source definitions publish no machine-readable schema this layer can read,
#: so the ``declared_schema`` level is reachable only by a caller who has been handed one. Shipping
#: an invented schema would be the same forgery as a heuristic, wearing a version number and a URL
#: nobody could fetch.
DEFAULT_DECLARED_SCHEMAS: tuple[DeclaredSchema, ...] = ()


def rule_for_key(key: str) -> KeyTypeRule | None:
    """The spelling row governing this whole key segment, or ``None``.

    **One normalisation and one lookup. There is no second branch.** That is the prohibition
    stated as code: a substring, a prefix, a suffix, a stem, an edit distance and a nearest-match
    fallback are all absent because there is nowhere to put them — the function has one statement
    after the local binding. :func:`extractors.payload.hypotheses.read_type_hypotheses` records the
    absence under ``key_rule_absent`` so the gap is a countable refusal rather than a silence.

    The mutation test ``test_a_nearest_match_fallback_in_the_key_table_fails_the_guard`` puts the
    substring heuristic back into exactly this line and shows the three ambiguity cases producing
    address hypotheses again.
    """
    normalised = normalise_key(key)
    return KEY_RULE_LOOKUP.get(normalised)


def schema_rules_for_path(
    key_path: str, schemas: Iterable[DeclaredSchema] = ()
) -> tuple[KeyTypeRule, ...]:
    """The declared rows binding this whole key path, in schema order then row order.

    Deterministic by construction: ``schemas`` is iterated in the order the caller supplied and each
    schema's rows in declaration order, so two runs over one schema list produce the same sequence
    and the same citations.
    """
    wanted = str(key_path or "")
    found: list[KeyTypeRule] = []
    for schema in schemas:
        found.extend(schema.rules_for(wanted))
    return tuple(found)


def matching_rules(
    *, key_path: str, segment: str, schemas: Iterable[DeclaredSchema] = ()
) -> tuple[KeyTypeRule, ...]:
    """Every row governing one record, **declared rows first and the spelling row last**.

    The order is the claim: a source's declaration about a path is stronger evidence than a word
    the platform chose, so a reader meets the better-founded hypothesis first. The two levels do not
    compete — both are emitted, and each citation says which level produced it.
    """
    declared = schema_rules_for_path(key_path, schemas)
    spelling = rule_for_key(segment)
    return declared + ((spelling,) if spelling is not None else ())


__all__ = [
    "DECLARED_SCHEMA_CONFIDENCE",
    "DEFAULT_DECLARED_SCHEMAS",
    "KEY_MATCH_EQUALITY",
    "KEY_MATCH_MODES",
    "KEY_RULE_LOOKUP",
    "KEY_TYPE_RULES",
    "KEY_TYPE_TABLE_VERSION",
    "KEY_WILDCARDS",
    "SPELLING_CONFIDENCE",
    "BasisOrigin",
    "DeclaredSchema",
    "KeyTypeRule",
    "KeyTypeRuleError",
    "matching_rules",
    "normalise_key",
    "rule_for_key",
    "schema_rules_for_path",
]
