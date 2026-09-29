"""S1 and S2: a type hypothesis must cite its basis, and only a declared table may propose one.

Feature 021 brief §16 (``SignalBasis`` answers "how do you know?"), §25 (a producer below mention
extraction); constitution IV (fail-closed) and VI (determinism, Domain Invariant 12).

**The defect this file is written against.** Upstream collapsed a regex hit, a key-name heuristic,
a type assertion and a mention into one ``Entity(type, value, source, context, confidence=1.0)``
row, so a payload that contained the word ``email`` once produced an *email entity at full
confidence*. The removal of that is only real if the two halves are separate and mechanical:

* **S1 — a hypothesis carries why it was proposed.** :class:`CitedHypothesis` pairs a
  :class:`semantic.blocking.TypeHypothesis` with the :class:`HypothesisCitation` that says which
  key path segment suggested it and *at which epistemic level* — a source-published schema, or the
  spelling of a word. The two survive into the output as
  :class:`extractors.payload.keytable.BasisOrigin` members, and a test pins that both reach the
  record when both fired.
* **S2 — the guessing prohibition is a table, not a heuristic.** ``user_email`` is not ``email``,
  ``email_verified`` is not ``email``, and ``email_count`` is not a count. The table matches a
  record's key segment by **equality and nothing else**, so a substring is a guess by construction
  and there is no fuzzy branch to fall back to. The three mutation tests below are the load-bearing
  part: a dropped ``confidence=``, a nearest-match fallback, and nothing else.

**No hypothesis may be emitted with an unset confidence.** :class:`semantic.blocking.TypeHypothesis`
defaults ``confidence`` to ``1.0`` — the very number whose inheritance this chain exists to remove.
Three separate guards close it, and the first is the one that makes the other two meaningful:
:func:`KeyTypeRule` **refuses** a row declaring ``1.0``, so a construction that forgets to name
its confidence cannot accidentally agree with a declared row.
"""

from __future__ import annotations

import ast
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from semantic.blocking import TypeHypothesis

from extractors.payload.hypotheses import (
    HYPOTHESIS_REFUSAL_CODES,
    HypothesisRefusal,
    HypothesisRefusalCode,
    read_type_hypotheses,
)
from extractors.payload.keytable import (
    DECLARED_SCHEMA_CONFIDENCE,
    DEFAULT_DECLARED_SCHEMAS,
    KEY_TYPE_RULES,
    KEY_TYPE_TABLE_VERSION,
    SPELLING_CONFIDENCE,
    BasisOrigin,
    DeclaredSchema,
    KeyTypeRule,
    KeyTypeRuleError,
    rule_for_key,
)
from parsers.payload import ValueType, default_registry

pytestmark = pytest.mark.unit

#: ``apps/`` — the root the service packages hang off.
APPS = Path(__file__).resolve().parents[2]
INTERPRETATION = APPS / "interpretation"
#: Everything a mutated child run has to import. ``extractors`` needs ``domain`` and ``parsers``;
#: ``domain`` needs ``semantic``.
_COPIED = (
    ("interpretation", ("extractors", "parsers", "semantic", "contracts.py")),
    ("shared", ("domain", "semantic")),
)

SCHEMA_REF = "https://example.invalid/schemas/registrant.json"

#: A schema a *source* published, and the only thing in this file allowed to make a number mean
#: something. Written out in full rather than imported from the package, because the package ships
#: none — see :func:`test_the_platform_publishes_no_declared_schema` — and a test that quietly
#: supplied the platform's own would be testing nothing.
SCHEMA = DeclaredSchema(
    schema_ref=SCHEMA_REF,
    version="2026-01",
    rules=(
        KeyTypeRule(
            key='$["registrant"]["email"]',
            type_ref="email_address",
            confidence=DECLARED_SCHEMA_CONFIDENCE,
            value_types=(ValueType.STRING,),
            rule_id="registrant.email",
            origin=BasisOrigin.DECLARED_SCHEMA,
            schema_ref=SCHEMA_REF,
        ),
        KeyTypeRule(
            key='$["registrant"]["email_count"]',
            type_ref="count",
            confidence=DECLARED_SCHEMA_CONFIDENCE,
            value_types=(ValueType.NUMBER,),
            rule_id="registrant.email_count",
            origin=BasisOrigin.DECLARED_SCHEMA,
            schema_ref=SCHEMA_REF,
        ),
    ),
)

RULES_BY_ID = {rule.rule_id: rule for rule in KEY_TYPE_RULES}


def parse(body: bytes, **over: object):
    arguments: dict[str, object] = {
        "body": body,
        "content_type": "application/json",
        "declared_parser": "structured_fields",
    }
    arguments.update(over)
    return default_registry().parse(**arguments)


def hypotheses_for(body: bytes, **over: object):
    return read_type_hypotheses(parse(body).records, **over)


# --------------------------------------------------------------------------- #
# S1: no hypothesis is ever emitted with an inherited 1.0
# --------------------------------------------------------------------------- #


def test_the_typehypothesis_default_really_is_one_so_the_guards_measure_something() -> None:
    """The other half of every guard below, and the half that is easy to skip.

    If the dataclass default moved, "no hypothesis carries 1.0" would be guarding a number no
    construction could inherit any more, and the mutation below would prove nothing. So the trap
    is asserted to exist, in the same file, first.
    """
    assert TypeHypothesis(type_ref="anything").confidence == 1.0


def test_a_hypothesis_is_never_emitted_with_the_inherited_typehypothesis_default() -> None:
    """Every emitted hypothesis names the confidence its cited row declared, and none is ``1.0``.

    Two assertions because they catch different mistakes. ``!= 1.0`` catches a construction that
    dropped its ``confidence=`` (it inherits the default). The equality against the cited row
    catches a construction that invented a number of its own, which ``!= 1.0`` would wave through.
    """
    result = hypotheses_for(
        b'{"registrant": {"email": "a@b.c", "email_verified": true, "email_count": 4}}',
        schemas=(SCHEMA,),
    )
    assert result.hypotheses, "the fixture must propose at least one hypothesis or nothing follows"
    for cited in result.hypotheses:
        rule = rule_of(cited.citation.rule_id)
        assert cited.hypothesis.confidence == rule.confidence
        assert cited.hypothesis.confidence != TypeHypothesis(type_ref="x").confidence


def rule_of(rule_id: str) -> KeyTypeRule:
    """The declared row a citation names, from whichever table it came from."""
    for rule in KEY_TYPE_RULES:
        if rule.rule_id == rule_id:
            return rule
    for rule in SCHEMA.rules:
        if rule.rule_id == rule_id:
            return rule
    raise AssertionError(f"no declared rule named {rule_id!r}")


def test_the_key_table_declares_no_confidence_equal_to_the_typehypothesis_default() -> None:
    """The guard that makes the first one falsifiable rather than decorative.

    A declared row may never carry ``1.0``, so a construction which forgot to pass its confidence
    (and therefore got the dataclass default) cannot coincide with any row in the table. Written as
    a property of the *table* because that is where the rule lives: the number is not a parameter
    of a call site, it is a row of a versioned table, and the table is where it is forbidden.
    """
    assert TypeHypothesis(type_ref="x").confidence == 1.0
    assert KEY_TYPE_RULES, "the shipped table is empty, so the assertions below are vacuous"
    assert all(rule.confidence != 1.0 for rule in KEY_TYPE_RULES)
    assert SPELLING_CONFIDENCE != 1.0
    assert DECLARED_SCHEMA_CONFIDENCE != 1.0


def test_a_row_that_declares_certainty_is_refused_on_construction() -> None:
    """``1.0`` is refused at the row, not merely discouraged in prose.

    A key-name rule — or even a source-published schema — is evidence about what the source *says
    the field is for*. Neither is a certainty that the mention is of that type, so neither may be
    recorded as one. ``KeyTypeRule`` enforces that at the only place a number enters the system.
    """
    with pytest.raises(KeyTypeRuleError) as raised:
        KeyTypeRule(key="email", type_ref="email_address", confidence=1.0)
    assert raised.value.code == "key_rule_confidence_is_a_certainty"


def test_a_row_with_no_confidence_is_a_type_error_and_not_a_defaulted_one() -> None:
    """``confidence`` has no default, so the inherited ``1.0`` is unreachable from a row."""
    with pytest.raises(TypeError):
        KeyTypeRule(key="email", type_ref="email_address")  # type: ignore[call-arg]


def test_every_hypothesis_cites_the_key_path_segment_that_suggested_it() -> None:
    result = hypotheses_for(b'{"registrant": {"email": "a@b.c"}}', schemas=(SCHEMA,))
    cited = result.hypotheses[0]
    assert cited.citation.key_path == '$["registrant"]["email"]'
    assert cited.citation.segment == "email"
    assert cited.citation.table_version == KEY_TYPE_TABLE_VERSION
    assert cited.citation.rule_id


def test_a_hypothesis_records_which_epistemic_level_proposed_it_and_both_survive() -> None:
    """A schema says *this path holds this type*; a spelling says *this word names a thing*.

    ``$["registrant"]["email"]`` is governed by both, so both hypotheses are emitted and each
    carries its own origin. Collapsing them to the stronger one would lose the fact that the
    platform also had a word-level reading, and collapsing to the weaker one would lose the fact
    that a source published a schema at all.
    """
    result = hypotheses_for(b'{"registrant": {"email": "a@b.c"}}', schemas=(SCHEMA,))
    origins = sorted(cited.citation.origin.value for cited in result.hypotheses)
    assert origins == ["declared_schema", "key_spelling"]
    by_origin = {cited.citation.origin: cited for cited in result.hypotheses}
    declared = by_origin[BasisOrigin.DECLARED_SCHEMA]
    spelling = by_origin[BasisOrigin.KEY_SPELLING]
    assert declared.hypothesis.type_ref == spelling.hypothesis.type_ref == "email_address"
    assert declared.citation.schema_ref == SCHEMA_REF
    assert spelling.citation.schema_ref == ""
    assert declared.hypothesis.confidence > spelling.hypothesis.confidence
    assert declared.citation.key_path == spelling.citation.key_path
    assert declared.citation.rule_id != spelling.citation.rule_id


def test_a_whole_table_rule_cannot_be_applied_to_a_spelling_and_vice_versa() -> None:
    """The two levels are structurally different, not a flag on the same row.

    A schema binds a **place** (a whole key path); a spelling binds a **word** (one key segment).
    ``KeyTypeRule`` refuses a row that breaks the correspondence, so a schema cannot be consulted
    with a segment and a spelling cannot be consulted with a path.
    """
    with pytest.raises(KeyTypeRuleError) as schema_bare:
        KeyTypeRule(
            key="email",
            type_ref="email_address",
            confidence=SPELLING_CONFIDENCE,
            origin=BasisOrigin.DECLARED_SCHEMA,
            schema_ref=SCHEMA_REF,
        )
    assert schema_bare.value.code == "key_rule_key_shape_mismatch"
    with pytest.raises(KeyTypeRuleError) as spelling_path:
        KeyTypeRule(
            key='$["registrant"]["email"]',
            type_ref="email_address",
            confidence=SPELLING_CONFIDENCE,
        )
    assert spelling_path.value.code == "key_rule_key_shape_mismatch"


def test_a_declared_schema_may_not_carry_another_schemas_rows() -> None:
    """A schema holding somebody else's rows is a schema nobody maintains."""
    with pytest.raises(KeyTypeRuleError) as raised:
        DeclaredSchema(
            schema_ref=SCHEMA_REF,
            version="2026-01",
            rules=(
                KeyTypeRule(
                    key='$["a"]',
                    type_ref="t",
                    confidence=DECLARED_SCHEMA_CONFIDENCE,
                    rule_id="x",
                    origin=BasisOrigin.DECLARED_SCHEMA,
                    schema_ref="https://elsewhere.invalid/other.json",
                ),
            ),
        )
    assert raised.value.code == "declared_schema_foreign_rule"


def test_a_rule_whose_key_is_not_its_own_normalised_form_is_refused() -> None:
    """A row that could never match its own key is a typo, and a typo in a lookup table is a
    silent absence: the key it was meant to govern gets no hypothesis and nobody can see why."""
    with pytest.raises(KeyTypeRuleError) as raised:
        KeyTypeRule(key="Email", type_ref="email_address", confidence=SPELLING_CONFIDENCE)
    assert raised.value.code == "key_rule_key_not_canonical"


def test_a_rule_whose_key_contains_a_wildcard_is_refused() -> None:
    """``*`` and ``%`` are refused, so a pattern can never be typed into a table by accident."""
    for wildcard in ("*", "%"):
        with pytest.raises(KeyTypeRuleError) as raised:
            KeyTypeRule(key=f"user_{wildcard}", type_ref="t", confidence=SPELLING_CONFIDENCE)
        assert raised.value.code == "key_rule_wildcard_refused"


# --------------------------------------------------------------------------- #
# S2, the ambiguity case, pinned key by key
# --------------------------------------------------------------------------- #


def test_the_ambiguity_case_user_email_is_not_an_email_hypothesis() -> None:
    """``"email"`` is a substring of ``"user_email"`` and that is precisely the defect.

    A producer that substring-matched would mint an email mention from a field whose name says the
    *user's* email is one attribute among several — the field may be a hash, a redacted token, a
    list index, or nothing at all. Equality on the whole key segment is the treatment, and the
    treatment is a **named refusal**, so the absence is countable rather than invisible.
    """
    result = hypotheses_for(b'{"user_email": "a@b.c"}')
    assert result.hypotheses == ()
    codes = [r.code for r in result.refusals if r.key_path == '$["user_email"]']
    assert codes == [HypothesisRefusalCode.KEY_RULE_ABSENT]
    assert "user_email" in next(r for r in result.refusals if r.key_path == '$["user_email"]').detail


def test_the_ambiguity_case_email_verified_is_not_an_email_hypothesis() -> None:
    """``"email_verified"`` contains ``"email"`` and states a *fact about* an address.

    Even a hypothetical table row for ``email`` would refuse it, because the row admits
    ``ValueType.STRING`` and this record is a ``bool``: the mismatch is recorded under its own code
    so a reader can tell "no rule names this key" from "a rule names it and the value disagrees".
    """
    result = hypotheses_for(b'{"email_verified": true}')
    assert result.hypotheses == ()
    codes = [r.code for r in result.refusals if r.key_path == '$["email_verified"]']
    assert codes == [HypothesisRefusalCode.KEY_RULE_ABSENT]


def test_the_ambiguity_case_a_key_whose_rule_exists_but_the_value_disagrees_is_a_mismatch() -> None:
    """The other side of the same pair, and the reason the two codes are separate.

    A ``bool`` under ``email`` isolates the value-type guard: the key has a rule, the rule does not
    admit a boolean, and the record is refused under ``key_rule_value_type_mismatch`` rather than
    the generic ``key_rule_absent`` — so a reader can tell "nobody has a rule for this key" from
    "a rule names it and the value disagrees", which are different gaps with different fixes.
    """
    result = hypotheses_for(b'{"email": true}')
    assert result.hypotheses == ()
    codes = [r.code for r in result.refusals if r.key_path == '$["email"]']
    assert codes == [HypothesisRefusalCode.KEY_RULE_VALUE_TYPE_MISMATCH]
    assert [r.rule_id for r in result.refusals if r.key_path == '$["email"]'] == ["spelling.email"]


def test_a_number_under_a_governed_key_also_gets_the_numeric_semantics_refusal() -> None:
    """Refusals stack, and here both are true for two different reasons.

    ``{"email": 5}`` breaks the value-type guard *and* declares nothing about what the number
    means. Reporting one would lose a fact: the key is governed by a rule and the value still does
    not fit, and separately nobody has said that this path holds a measurement.
    """
    result = hypotheses_for(b'{"email": 5}')
    assert result.hypotheses == ()
    codes = sorted(r.code for r in result.refusals if r.key_path == '$["email"]')
    assert codes == [
        HypothesisRefusalCode.KEY_RULE_VALUE_TYPE_MISMATCH,
        HypothesisRefusalCode.NUMERIC_SEMANTICS_REQUIRE_DECLARED_SCHEMA,
    ]


def test_the_ambiguity_case_email_count_gets_both_named_refusals_and_no_numeric_hypothesis() -> None:
    """A number is not a licence to call something a count, a port or a latitude.

    Two refusals, and both are true for two different reasons: no key rule governs the segment, and
    **nothing declares what the number means**. The second is the load-bearing one — it is the
    answer to "the bytes are a number, so what?", and it is a refusal by name rather than a
    default type.
    """
    result = hypotheses_for(b'{"email_count": 4}')
    assert result.hypotheses == ()
    codes = sorted(r.code for r in result.refusals if r.key_path == '$["email_count"]')
    assert codes == [
        HypothesisRefusalCode.KEY_RULE_ABSENT,
        HypothesisRefusalCode.NUMERIC_SEMANTICS_REQUIRE_DECLARED_SCHEMA,
    ]


def test_an_unknown_key_yields_zero_hypotheses_and_a_named_record() -> None:
    result = hypotheses_for(b'{"zebra": "stripes", "a": 1}')
    assert result.hypotheses == ()
    refusals = [r for r in result.refusals if r.key_path == '$["zebra"]']
    assert len(refusals) == 1
    assert refusals[0].code == HypothesisRefusalCode.KEY_RULE_ABSENT
    assert refusals[0].segment == "zebra"
    assert refusals[0].value_type == "string"
    assert "zebra" in refusals[0].detail
    assert refusals[0].to_dict()["code"] == "key_rule_absent"


def test_a_number_under_an_unknown_key_yields_no_numeric_semantic_hypothesis() -> None:
    """The table's numeric rows are empty, and that is a decision rather than an oversight.

    ``value_type="number"`` says what the bytes are. It does not say the number is a port, a
    latitude, a count or a price, and a producer that read the digits and chose a semantic is the
    defect this whole chain exists to remove. The only way to a numeric hypothesis is a
    source-published schema that names the path.
    """
    assert all(ValueType.NUMBER not in rule.value_types for rule in KEY_TYPE_RULES), (
        "the shipped table grew a numeric row: a number is not a licence to name a measurement"
    )
    result = hypotheses_for(b'{"port": 8080, "lat": 51.5, "count": 3}')
    assert result.hypotheses == ()
    numeric_paths = {
        r.key_path
        for r in result.refusals
        if r.code == HypothesisRefusalCode.NUMERIC_SEMANTICS_REQUIRE_DECLARED_SCHEMA
    }
    assert numeric_paths == {'$["port"]', '$["lat"]', '$["count"]'}


def test_a_declared_schema_is_the_only_way_a_number_gets_a_numeric_hypothesis() -> None:
    """The one lawful route, and it goes through a whole key path.

    A schema that binds a *word* cannot make a number mean anything, because a word is shared by
    every payload that uses it; a schema binds a place, and a place is what makes ``4`` a count
    *here* rather than there.
    """
    without = hypotheses_for(b'{"registrant": {"email_count": 4}}')
    assert without.hypotheses == ()
    with_schema = hypotheses_for(b'{"registrant": {"email_count": 4}}', schemas=(SCHEMA,))
    assert [h.hypothesis.type_ref for h in with_schema.hypotheses] == ["count"]
    cited = with_schema.hypotheses[0]
    assert cited.citation.origin is BasisOrigin.DECLARED_SCHEMA
    assert cited.citation.key_path == '$["registrant"]["email_count"]'
    assert cited.citation.schema_ref == SCHEMA_REF
    assert ValueType.NUMBER in rule_of(cited.citation.rule_id).value_types


def test_a_declared_schema_cannot_be_read_off_a_bare_word() -> None:
    """``{"email_count": 4}`` is a different place from the schema's row, so the row does not apply."""
    result = hypotheses_for(b'{"email_count": 4}', schemas=(SCHEMA,))
    assert result.hypotheses == ()


# --------------------------------------------------------------------------- #
# S2, the matching rule itself: equality, and nothing weaker
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "key",
    [
        "user_email",
        "email_verified",
        "email_count",
        "emails",
        "emailaddress",
        "primary_email",
        "email2",
        "e_mail",
        "user-email",
        "email.",
        "emailaddress2",
        "notemail",
    ],
)
def test_no_key_is_matched_by_substring_prefix_suffix_or_stem(key: str) -> None:
    """The mechanical form of the guessing prohibition, one near-miss at a time.

    Every key here either contains ``email`` or is one edit away from it. Under a substring, a
    prefix, a suffix, a stemmer or a nearest-match fallback, at least one of them would propose an
    ``email_address``. Under equality on the whole normalised key segment, none of them does, and
    :func:`extractors.payload.keytable.rule_for_key` is one dictionary lookup with no branch to
    delete.
    """
    assert rule_for_key(key) is None, (
        f"{key!r} matched a rule; the table matched something other than a whole key"
    )
    result = hypotheses_for(("{" + f'"{key}": "a@b.c"' + "}").encode("utf-8"))
    assert result.hypotheses == (), f"{key!r} produced a hypothesis"


def test_case_and_width_are_canonicalised_and_nothing_else_is() -> None:
    """Casefolding and whitespace are canonicalisation of one word; a tokeniser is a guess.

    ``Email``, ``EMAIL`` and `` email `` are three spellings of the key the table governs and the
    platform's own ``normalize_surface_form`` treats them as one. Splitting ``user_email`` into
    ``user`` and ``email`` is a *different operation*: it invents a token the payload did not
    contain, and it is the upstream defect wearing a tokeniser.
    """
    for spelling in ("email", "Email", "EMAIL", " email "):
        assert rule_for_key(spelling) is not None, f"{spelling!r} did not canonicalise onto the row"
    for spelling in ("user_email", "user.email", "user-email", "emailaddress"):
        assert rule_for_key(spelling) is None


def test_the_table_is_closed_declared_versioned_and_globally_unique() -> None:
    assert KEY_TYPE_TABLE_VERSION == "1"
    identifiers = [rule.rule_id for rule in KEY_TYPE_RULES]
    assert all(identifiers), "a row with no rule_id cannot be cited"
    assert len(set(identifiers)) == len(identifiers), "two rows share a rule_id"
    keys = [rule.key for rule in KEY_TYPE_RULES]
    assert len(set(keys)) == len(keys), "two rows govern the same key; which one wins is a coin toss"
    assert all(rule.origin is BasisOrigin.KEY_SPELLING for rule in KEY_TYPE_RULES)


def test_the_platform_publishes_no_declared_schema() -> None:
    """Empty on purpose, and pinned so it stays a decision.

    The 146 source definitions publish no machine-readable schema this layer can read, so the
    ``declared_schema`` level is reachable only by a caller who has one. Shipping an invented one
    would be the same forgery as a heuristic, wearing a version number.
    """
    assert DEFAULT_DECLARED_SCHEMAS == ()


def test_every_record_is_either_hypothesised_or_refused_by_name() -> None:
    """No record is silently skipped, which is the property a table makes easy to lose.

    A lookup that returns ``None`` for an unknown key is right; a lookup that returns ``None`` for
    a *malformed* path, an *array index* or the *root* is a silent drop, and a silent drop of a
    record is a field the caller cannot tell was ever read.
    """
    payload = parse(b'{"a": 1, "xs": ["p", 2], "b": {"c": "d"}, "e": null, "f": {}}')
    result = read_type_hypotheses(payload.records)
    hypothesised = {h.citation.key_path for h in result.hypotheses}
    refused = {r.key_path for r in result.refusals}
    assert hypothesised | refused == {record.field for record in payload.records}
    assert hypothesised & refused == set()


def test_an_array_element_has_no_key_and_says_so() -> None:
    result = hypotheses_for(b'{"xs": ["p"]}')
    codes = {r.code for r in result.refusals if r.key_path == '$["xs"][0]'}
    assert codes == {HypothesisRefusalCode.MEMBER_IS_ARRAY_INDEXED}


def test_the_document_root_has_no_key_and_says_so() -> None:
    result = hypotheses_for(b'{"a": 1}')
    codes = {r.code for r in result.refusals if r.key_path == "$"}
    assert codes == {HypothesisRefusalCode.DOCUMENT_ROOT_HAS_NO_KEY}


def test_a_key_path_this_stage_cannot_read_is_refused_rather_than_guessed() -> None:
    """A record whose ``field`` is not in the parser's path grammar is a caller bug.

    Reading it anyway would mean splitting the string somewhere convenient, and a key containing
    ``[`` makes every convenient split wrong for a payload the platform really will see.
    """
    from parsers.payload import ObservedField, PayloadLabel

    record = ObservedField(
        field='$["a"]["weird',
        value="x",
        value_type=ValueType.STRING,
        byte_span=(0, 3),
        depth=2,
        label=PayloadLabel.JSON_FIELD,
    )
    result = read_type_hypotheses((record,))
    assert result.hypotheses == ()
    assert [r.code for r in result.refusals] == [HypothesisRefusalCode.KEY_PATH_UNREADABLE]


def test_the_refusal_vocabulary_is_closed_and_published() -> None:
    assert set(HypothesisRefusalCode) <= set(HYPOTHESIS_REFUSAL_CODES)
    assert len(HYPOTHESIS_REFUSAL_CODES) == len(set(HYPOTHESIS_REFUSAL_CODES))
    assert HypothesisRefusalCode.KEY_RULE_ABSENT.value == "key_rule_absent"


def test_a_refusal_is_a_countable_record_with_a_code_and_a_detail() -> None:
    payload = parse(b'{"zebra": 1}')
    refusals = read_type_hypotheses(payload.records).refusals
    assert all(isinstance(refusal, HypothesisRefusal) for refusal in refusals)
    for refusal in refusals:
        entry = refusal.to_dict()
        assert set(entry) == {"code", "key_path", "segment", "value_type", "rule_id", "detail"}
        assert entry["code"] in HYPOTHESIS_REFUSAL_CODES
        assert entry["detail"]


def test_two_readings_of_one_payload_are_byte_identical() -> None:
    body = b'{"registrant": {"email": "a@b.c", "email_count": 4}, "xs": ["p", "q"]}'
    first = hypotheses_for(body, schemas=(SCHEMA,))
    second = hypotheses_for(body, schemas=(SCHEMA,))
    assert first.to_dict() == second.to_dict()
    assert first.content_key() == second.content_key()
    assert [c.hypothesis.type_ref for c in first.hypotheses] == [
        c.hypothesis.type_ref for c in second.hypotheses
    ]


def test_this_stage_imports_no_graph_claim_admission_projection_or_resolution_symbol() -> None:
    """The hard requirement, checked over the AST of every module in the package.

    Docstrings are excluded, for the reason the parser layer's own boundary test says: this
    package's documentation names ``RelationSignal``, ``TypeAssertion`` and ``MN-`` constantly,
    because a boundary nobody can name is a boundary nobody will argue about when the first change
    comes for it.
    """
    forbidden_roots = frozenset(
        {
            "admission",
            "claims",
            "coreference",
            "events",
            "graph",
            "projection",
            "resolution",
            "scoring",
            "sources",
            "storage",
        }
    )
    forbidden_names = frozenset(
        {
            "Entity",
            "RelationClaim",
            "ResolutionDecisionRecord",
            "CandidateStatus",
            "TypeAssertion",
            "bind_producer_signals",
        }
    )
    forbidden_literals = frozenset({"ENT-", "RES-", "REL-"})
    package = INTERPRETATION / "extractors" / "payload"
    offenders: list[str] = []
    for module in sorted(package.rglob("*.py")):
        tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
        prose = _docstrings(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in forbidden_roots:
                        offenders.append(f"{module.name}:{node.lineno} import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                if (node.module or "").split(".")[0] in forbidden_roots:
                    offenders.append(f"{module.name}:{node.lineno} from {node.module}")
            elif isinstance(node, ast.Name) and node.id in forbidden_names:
                offenders.append(f"{module.name}:{node.lineno} name {node.id}")
            elif isinstance(node, ast.Attribute) and node.attr in forbidden_names:
                offenders.append(f"{module.name}:{node.lineno} attribute {node.attr}")
            elif (
                isinstance(node, ast.Constant)
                and node.value in forbidden_literals
                and node.value not in prose
            ):
                offenders.append(f"{module.name}:{node.lineno} literal {node.value!r}")
    assert not offenders, "the hypothesis stage reached above itself:\n  " + "\n  ".join(offenders)


def _docstrings(tree: ast.AST) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            body = getattr(node, "body", [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                found.add(body[0].value.value)
    return found


# --------------------------------------------------------------------------- #
# Mutation: drop the explicit confidence
# --------------------------------------------------------------------------- #


def _mutated(find: str, replace_with: str, *, target_name: str = "hypotheses.py") -> Path:
    """A throwaway copy of the packages with one edit applied, mirroring the harness in
    ``test_signal_kind_channels``. Flat, because one ``PYTHONPATH`` entry is all a child needs."""
    root = Path(tempfile.mkdtemp(prefix="payload-hypothesis-mutation-"))
    for package, members in _COPIED:
        for member in members:
            source = APPS / package / member
            if source.is_dir():
                shutil.copytree(source, root / source.name, ignore=shutil.ignore_patterns("__pycache__"))
            elif source.exists():
                shutil.copy2(source, root / source.name)
    target = (root / "extractors" / "payload" / target_name).resolve()
    text = target.read_text(encoding="utf-8")
    assert find in text, f"mutation anchor not found in {target_name}: {find[:70]!r}"
    target.write_text(text.replace(find, replace_with, 1), encoding="utf-8")
    return root


_CONFIDENCE_GUARD = """
import sys
from extractors.payload.hypotheses import read_type_hypotheses
from extractors.payload.keytable import (
    KEY_TYPE_RULES,
    BasisOrigin,
    DeclaredSchema,
    KeyTypeRule,
)
from parsers.payload import ValueType, default_registry

ref = "https://example.invalid/s.json"
schema = DeclaredSchema(
    schema_ref=ref,
    version="1",
    rules=(
        KeyTypeRule(
            key='$["registrant"]["email"]',
            type_ref="email_address",
            confidence=0.9,
            value_types=(ValueType.STRING,),
            rule_id="r.email",
            origin=BasisOrigin.DECLARED_SCHEMA,
            schema_ref=ref,
        ),
    ),
)
payload = default_registry().parse(
    body=b'{"registrant": {"email": "a@b.c"}}',
    content_type="application/json",
    declared_parser="structured_fields",
)
result = read_type_hypotheses(payload.records, schemas=(schema,))
failures = []
if not result.hypotheses:
    failures.append("the fixture produced no hypothesis, so the guard proved nothing")
declared = {rule.rule_id: rule.confidence for rule in KEY_TYPE_RULES}
declared.update({rule.rule_id: rule.confidence for rule in schema.rules})
for cited in result.hypotheses:
    if cited.hypothesis.confidence == 1.0:
        failures.append(f"{cited.citation.rule_id} carries the inherited TypeHypothesis default 1.0")
    if cited.hypothesis.confidence != declared.get(cited.citation.rule_id):
        failures.append(
            f"{cited.citation.rule_id} carries {cited.hypothesis.confidence!r} and its cited row "
            f"declares {declared.get(cited.citation.rule_id)!r}"
        )
print("GUARD_OK" if not failures else "GUARD_FAIL " + "; ".join(failures))
raise SystemExit(0 if not failures else 1)
"""


def _child_env(root: Path) -> dict[str, str]:
    """The current environment with only ``PYTHONPATH`` redirected, for the Windows reason the
    other mutation harnesses record: a hand-built env without ``System32`` breaks Winsock."""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root)
    return env


def test_the_unmutated_hypothesis_stage_satisfies_the_confidence_guard() -> None:
    completed = subprocess.run(
        [sys.executable, "-c", _CONFIDENCE_GUARD],
        capture_output=True,
        text=True,
        cwd=str(INTERPRETATION),
        env=_child_env(INTERPRETATION),
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr[-2000:]
    assert "GUARD_OK" in completed.stdout, completed.stdout


def test_dropping_the_explicit_confidence_fails_the_guard() -> None:
    """The mutation, and the reason the guard is written against the cited row rather than 1.0.

    Removing ``confidence=rule.confidence`` makes the construction inherit
    :attr:`TypeHypothesis.confidence`'s default of ``1.0``. Nothing at the call site fails, no test
    that checks *whether* a hypothesis exists fails, and the platform goes on reporting typed
    mentions at full certainty — which is the upstream defect, reintroduced through a refactor.
    """
    root = _mutated("            confidence=rule.confidence,\n", "")
    try:
        completed = subprocess.run(
            [sys.executable, "-c", _CONFIDENCE_GUARD],
            capture_output=True,
            text=True,
            cwd=str(root),
            env=_child_env(root),
            check=False,
        )
    finally:
        shutil.rmtree(root, ignore_errors=True)
    assert completed.returncode != 0, (
        f"dropping the explicit confidence did NOT fail the guard, so the guard is decorative: "
        f"{completed.stdout!r}"
    )
    assert "inherited TypeHypothesis default" in completed.stdout, completed.stdout
    assert "its cited row declares" in completed.stdout, completed.stdout


# --------------------------------------------------------------------------- #
# Mutation: nearest-match fallback in the key table
# --------------------------------------------------------------------------- #


_NEAREST_GUARD = """
from extractors.payload.hypotheses import read_type_hypotheses
from extractors.payload.keytable import rule_for_key
from parsers.payload import default_registry

failures = []
for key in ("user_email", "email_verified", "email_count"):
    if rule_for_key(key) is not None:
        failures.append(f"{key} matched a rule by something other than equality")
payload = default_registry().parse(
    body=b'{"user_email": "a@b.c", "email_verified": true, "email_count": 4}',
    content_type="application/json",
    declared_parser="structured_fields",
)
result = read_type_hypotheses(payload.records)
if result.hypotheses:
    failures.append(
        "the payload produced hypotheses: "
        + ",".join(h.citation.key_path for h in result.hypotheses)
    )
print("GUARD_OK" if not failures else "GUARD_FAIL " + "; ".join(failures))
raise SystemExit(0 if not failures else 1)
"""


def test_a_nearest_match_fallback_in_the_key_table_fails_the_guard() -> None:
    """Restoring the upstream heuristic, in the exact shape it had.

    The mutation makes :func:`rule_for_key` return the first table row whose key is a **substring**
    of the record's key — the one-line heuristic that made ``Entity(type="email", confidence=1.0)``
    out of a payload that said the word once. The guard is behavioural, not a restatement of the
    implementation: it asks the table about three keys and asks the stage for the hypotheses those
    keys produce.
    """
    root = _mutated(
        "    return KEY_RULE_LOOKUP.get(normalised)",
        "    if normalised in KEY_RULE_LOOKUP:\n"
        "        return KEY_RULE_LOOKUP[normalised]\n"
        "    for row in KEY_TYPE_RULES:\n"
        "        if row.key in normalised:\n"
        "            return row\n"
        "    return None",
        target_name="keytable.py",
    )
    try:
        completed = subprocess.run(
            [sys.executable, "-c", _NEAREST_GUARD],
            capture_output=True,
            text=True,
            cwd=str(root),
            env=_child_env(root),
            check=False,
        )
    finally:
        shutil.rmtree(root, ignore_errors=True)
    assert completed.returncode != 0, (
        f"a substring fallback did NOT fail the guard, so the table is not enforcing equality: "
        f"{completed.stdout!r}"
    )
    assert "something other than equality" in completed.stdout, completed.stdout
    assert "produced hypotheses" in completed.stdout, completed.stdout
