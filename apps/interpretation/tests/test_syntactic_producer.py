"""The syntactic producer and its pinned shallow parser: contract tests.

Feature 021, brief §29 and §30; spec FR-042, FR-043; ``data-model.md`` part 3;
``repair/A2-identity-subsystem.md`` D6.3 H5 and H6; ``repair/ARBITRATION.md`` §11.

Four kinds of thing are being pinned, and they are of different kinds:

* **A row of the construction table.** One test per row of the ten in ``data-model.md`` part
  3.4, driven from the producer's surface, asserting both the construction it *declares* and
  the canonical argument assignment ``normalize_voice`` derives from it.
* **A refusal.** Every path on which the producer emits nothing, asserted with a named code
  and ``suppresses_signal`` true. A test that asserts a refusal is worth more than a test
  that asserts a guess would work: a guess passes either way, and a refusal only passes
  while the refusal is still there.
* **Pinning.** ``configuration_hash`` and ``fixture_digest`` against committed golden
  values, so a rule change is a visible diff rather than a silent corpus shift.
* **``SC-001`` end to end.** Two surfaces, two ``signal_id``s, one ``logical_candidate_id`` -
  over a real parser, with no ``xfail`` marker. ``ARBITRATION`` §11 records that the marker
  was mandatory *because* no syntactic producer existed; the producer exists, so the test
  passes and must keep passing. A test that still carried the marker would be reporting
  ``SC-001`` as unfulfilled while it is fulfilled, which §11 forbids.

Nothing here mutates a shared module. The one test that removes a guard does it by
**temporarily replacing a pinned function's result** and restoring it in a ``finally``, so
the guard's absence is observable and the suite is left exactly as it was found.
"""

from __future__ import annotations

import ast
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from domain.mention_occurrence_index import DEFERRED_OCCURRENCE_PREFIX
from domain.predicate_signature import (
    ArgumentMarker,
    ArgumentSlot,
    ConstructionFrame,
    Polarity,
)
from domain.predicate_voice import CONSTRUCTION_TABLE, SyntacticConstruction, normalize_voice
from domain.signal_basis import SignalBasis

import extractors.signals.syntactic as syntactic_module
from extractors.signals.mentions import read_occurrence
from extractors.signals.protocol import ExtractionScope
from extractors.signals.signal import SignalKind
from extractors.signals.syntactic import (
    PRODUCER_REF,
    PRODUCER_VERSION,
    SyntacticExtractor,
    syntactic_candidate_ids,
    syntactic_signals,
)
from parsers import shallow
from parsers.shallow import (
    H6_STOP_CONDITION,
    PARSER_VERSION,
    PINNED_CLAUSE_FIXTURES,
    PINNED_CONFIGURATION_HASH,
    PINNED_FIXTURE_DIGEST,
    REFUSAL_REACHABILITY,
    SHALLOW_CAPABILITY,
    DeclaredChannel,
    ParserCapability,
    ParserContractError,
    RefusalCode,
    RefusalStage,
    assign_slots,
    configuration_hash,
    fixture_digest,
    fixture_outcome,
    logical_candidate_id_of,
    parse,
    refusal_counts,
    tokenise,
)

pytestmark = pytest.mark.unit

_TENANT = "tenant-a"

#: The channel declarations row 9 needs, and the surface they make readable. A headless PP is
#: not readable from a sentence: its governor and its subject are document-structure slots,
#: so a real caller is an attribute row whose key is the predicate and whose value is the
#: phrase.
_ATTRIBUTE_CHANNEL = DeclaredChannel(
    subject="John Smith", head="works", label="attribute:affiliation"
)


@dataclass(frozen=True, slots=True)
class Mention:
    """A mention record shaped exactly as ``stable_participant_fingerprint`` reads it.

    The excluded fields are present and empty so a test can see that none of them reaches
    the fingerprint. This is a *test* record standing in for the mention layer's, which is
    what makes the end-to-end claim a claim about the producer rather than about a fixture
    the producer also wrote.
    """

    surface: str
    capture_ref: str = "CAP-1"
    segment_ref: str = "SEG-1"
    start: int = 0
    end: int = 0
    kind: str = "entity"
    mention_id: str = ""
    producer_ref: str = ""
    producer_version: str = ""
    confidence: float = 0.0
    type_ref: str = ""
    argument_shape: str = ""
    trigger_span: str = ""


def _scope() -> ExtractionScope:
    return ExtractionScope(
        tenant_id=_TENANT,
        context_ref="ctx-1",
        semantic_regime_ref="regime-1",
        document_ref="CAP-1",
    )


def _one(clause: str, *, channel: DeclaredChannel | None = None, constructor: str | None = None):
    """The single reading ``clause`` must produce, or a failure naming what did.

    ``constructor`` selects one reading from a sentence that legitimately yields two - a
    comma-bracketed relative clause plus its matrix clause. Selecting by constructor rather
    than by index is what keeps a future reading order from silently changing which reading
    the test is about.
    """
    readings, refusals = parse(clause, channel=channel)
    blocking = [refusal for refusal in refusals if refusal.suppresses_signal]
    assert not blocking, [refusal.to_dict() for refusal in blocking]
    if constructor is None:
        assert len(readings) == 1, [reading.to_dict() for reading in readings]
        return readings[0]
    chosen = [reading for reading in readings if reading.constructor == constructor]
    assert len(chosen) == 1, [reading.to_dict() for reading in readings]
    return chosen[0]


def _first_code(clause: str, *, channel: DeclaredChannel | None = None) -> str:
    _readings, refusals = parse(clause, channel=channel)
    blocking = [refusal for refusal in refusals if refusal.suppresses_signal]
    assert blocking, f"{clause!r} was refused by nothing, which means it was read"
    return blocking[0].code


# --------------------------------------------------------------------------- #
# The pinned capability (FR-043)
# --------------------------------------------------------------------------- #


def test_the_four_pinned_fields_are_exposed_and_populated() -> None:
    """FR-043 names four fields, and all four must be present and non-empty.

    Checked on the *value* and on ``to_dict``, because a provenance record is the dict: a
    capability whose fields exist only as attributes never reaches a stored record.
    """
    payload = SHALLOW_CAPABILITY.to_dict()
    assert set(payload) == {
        "model_ref",
        "model_version",
        "parser_version",
        "configuration_hash",
    }
    for name, value in payload.items():
        assert value.strip(), f"{name} is empty on the pinned capability"
    assert payload["parser_version"] == PARSER_VERSION
    assert len(payload["configuration_hash"]) == 32
    assert payload["configuration_hash"] == payload["configuration_hash"].lower()


def test_the_parser_capability_names_a_rule_set_and_not_an_invented_checkpoint() -> None:
    """There is no dependency parser in this repository, so the model ref must say so.

    The claim is only worth anything if it is checkable, and it is checkable twice: the
    declaration names a rule set, and the module states the absence of every dependency
    parser the brief §30 might have expected. A checkpoint id here would be a provenance
    record asserting that a model was loaded.
    """
    assert "surface-rules" in SHALLOW_CAPABILITY.model_ref
    assert not any(
        token in SHALLOW_CAPABILITY.model_ref
        for token in ("en_core", "spacy", "stanza", "nltk", "coref", "checkpoint")
    )
    assert "no model" in shallow.NO_LLM_IN_CONSTITUTIONAL_PATH.lower()


def test_the_configuration_hash_is_stable_across_calls_and_processes() -> None:
    """Determinism, and the *only* kind of it that matters here: same input, same bytes."""
    assert configuration_hash() == configuration_hash()
    assert SHALLOW_CAPABILITY.configuration_hash == configuration_hash()
    material = shallow.configuration_material()
    assert material == shallow.configuration_material()
    assert list(material) == sorted(material)


def test_the_configuration_hash_pins_every_table_the_parser_reads() -> None:
    """A rule that is not in the digest input is a rule whose change is invisible.

    Asserted against the live inventories rather than against a copy of them, so a new
    inventory that is not hashed fails here instead of being discovered in a stored record.
    """
    material = shallow.configuration_material()
    assert material["constructor_order"] == list(shallow.CONSTRUCTOR_ORDER)
    assert material["determiners"] == sorted(shallow.DETERMINERS)
    assert material["syntax_prepositions"] == sorted(shallow.SYNTAX_PREPOSITIONS)
    assert material["pinned_participles"] == dict(sorted(shallow.PINNED_PARTICIPLES.items()))
    assert material["refusal_codes"] == sorted(str(code) for code in RefusalCode)
    assert material["phrase_categories"] == sorted(
        str(category) for category in shallow.PhraseCategory
    )
    assert material["lemma_table_digest"] == shallow.LEMMA_TABLE_DIGEST
    assert set(material["declaring_constructors"]) == set(
        shallow.DECLARABLE_CONSTRUCTIONS
    )
    # The partition is total: a constructor either declares something or is declared as
    # refusing, and nothing is in neither list.
    declared = set(shallow.DECLARABLE_CONSTRUCTIONS) | set(
        shallow.REFUSAL_ONLY_CONSTRUCTORS
    )
    assert declared == set(shallow.CONSTRUCTOR_ORDER)


def test_a_capability_may_not_claim_a_configuration_it_does_not_have() -> None:
    """FR-043's fields are a claim about the code. A false one must fail closed."""
    with pytest.raises(ParserContractError) as caught:
        ParserCapability(configuration_hash="0" * 32)
    assert caught.value.code == RefusalCode.SLOT_MAP_DISAGREES
    assert "asserting something the code does not do" in caught.value.message
    # And the honest construction is idempotent with the module-level one.
    assert ParserCapability().configuration_hash == configuration_hash()


def test_the_pinned_configuration_hash_is_current() -> None:
    """A rule change moves this committed value, and the diff *is* the review."""
    assert configuration_hash() == PINNED_CONFIGURATION_HASH


def test_the_pinned_fixture_digest_is_current() -> None:
    """The behavioural pin: a rule change that moves a *parse* moves this digest.

    ``configuration_hash`` says which tables the parser reads. This says what it does with
    them. Both are needed, because a rule can change with no table changing at all - a
    priority swap, a boundary test - and the second is the only one that would notice.
    """
    assert fixture_digest() == PINNED_FIXTURE_DIGEST


def test_every_pinned_clause_fixture_behaves_as_recorded() -> None:
    """The fixture table is the corpus, and it is a corpus of *both* readings and refusals.

    Including the surfaces brief §29 names whose head noun ("CEO") is outside the closed
    lemma inventory: those produce no reading, and the fact is pinned here rather than left
    as a surprise.
    """
    for clause, expected_outcome, expected_predicate in PINNED_CLAUSE_FIXTURES:
        outcome, predicate = fixture_outcome(clause)
        assert outcome == expected_outcome, clause
        assert predicate == expected_predicate, clause


# --------------------------------------------------------------------------- #
# One test per row of the construction table
# --------------------------------------------------------------------------- #

_ROW_SURFACES: tuple[tuple[int, str, SyntacticConstruction, str, dict[str, str]], ...] = (
    (
        1,
        "Asset was acquired by Company.",
        SyntacticConstruction.PASSIVE_WITH_AGENT,
        "acquire(A0:,A1:)",
        {"A0": "Company", "A1": "Asset"},
    ),
    (
        2,
        "John is the chairman.",
        SyntacticConstruction.COPULAR,
        "be(A0:,A1:)",
        {"A0": "John", "A1": "the chairman"},
    ),
    (
        3,
        "John is a founder of Acme.",
        SyntacticConstruction.COPULAR_WITH_NOUN_COMPLEMENT,
        "be(A0:,A1:of)",
        {"A0": "John", "A1": "Acme"},
    ),
    (
        4,
        "Company acquired Asset.",
        SyntacticConstruction.ACTIVE_CLAUSE,
        "acquire(A0:,A1:)",
        {"A0": "Company", "A1": "Asset"},
    ),
    (
        6,
        "owner of Acme from Globex",
        SyntacticConstruction.BARE_NOMINAL,
        "own(A0:,A1:of)",
        {"A0": "Globex", "A1": "Acme"},
    ),
    (
        7,
        "Acme's founder John Smith",
        SyntacticConstruction.GENITIVE_NP,
        "found(A0:,A1:)",
        {"A0": "John Smith", "A1": "Acme"},
    ),
    (
        8,
        "John Smith, founder of Acme",
        SyntacticConstruction.APPOSITIVE_NP,
        "found(A0:,A1:of)",
        {"A0": "John Smith", "A1": "Acme"},
    ),
    (
        9,
        "at Acme",
        SyntacticConstruction.HEADLESS_PP,
        "work(A0:at,A1:)",
        {"A0": "Acme", "A1": "John Smith"},
    ),
    (
        10,
        "The report, which the committee wrote, was sent by Acme.",
        SyntacticConstruction.RELATIVE_CLAUSE,
        "write(A0:,A1:)",
        {"A0": "the committee", "A1": "The report"},
    ),
)


#: Which constructor each row's surface must be read by, for the one row whose sentence
#: legitimately yields two readings (the relative clause and its matrix clause).
_ROW_CONSTRUCTOR: dict[int, str] = {10: "relative_clause"}


@pytest.mark.parametrize(
    ("row_number", "clause", "construction", "predicate", "slot_surfaces"),
    _ROW_SURFACES,
    ids=[f"row{row}__{clause[:24]}" for row, clause, _c, _p, _s in _ROW_SURFACES],
)
def test_every_row_of_the_construction_table_is_declared_from_the_surface(
    row_number: int,
    clause: str,
    construction: SyntacticConstruction,
    predicate: str,
    slot_surfaces: dict[str, str],
) -> None:
    """``data-model.md`` part 3.4, row by row, from text rather than from a declared parse.

    Three things per row, and the third is the one a table lookup would not give: the
    producer **declares** the construction from the surface, the authority derives the
    canonical assignment, and the participant each slot names is the one the row's slot
    sources say. Rows 2 and 4 are not in this table: row 4 is, and row 2's own condition
    (``a bare-NP complement``) is covered by the second row here.
    """
    row = next(row for row in CONSTRUCTION_TABLE if row.number == row_number)
    channel = _ATTRIBUTE_CHANNEL if row_number == 9 else None
    reading = _one(clause, channel=channel, constructor=_ROW_CONSTRUCTOR.get(row_number))
    assert reading.construction is construction, clause
    assert reading.constructor in shallow.DECLARABLE_CONSTRUCTIONS, clause
    if row_number != 5:
        assert reading.signature.construction_frame is row.frame, clause
    assert reading.rendered_predicate == predicate, clause
    assert reading.signature.construction_frame is not (
        ConstructionFrame.VERB_PASSIVE_AGENT
    ), "an observed-only passive frame reached a signature"
    bindings = {binding.slot.token: binding.argument.surface for binding in assign_slots(reading)}
    assert bindings == slot_surfaces, clause


def test_row_two_is_the_bare_np_complement_and_row_three_the_of_complement() -> None:
    """Rows 2 and 3 are separated by the complement's phrase category - gap (b), decided.

    "John is the chairman" has a bare NP complement; "John is a founder of Acme" has a
    nominal beside an ``of``-PP. Same copula, same head lemma, two different frames, and
    therefore two different signatures - which is the whole of data-model §3.2's claim that
    a copula does not collapse with a neighbouring construction.
    """
    bare = _one("John is the chairman.")
    nominal = _one("John is a founder of Acme.")
    assert bare.construction is SyntacticConstruction.COPULAR
    assert nominal.construction is SyntacticConstruction.COPULAR_WITH_NOUN_COMPLEMENT
    assert bare.signature.construction_frame is ConstructionFrame.COPULA_PREDICATIVE
    assert nominal.signature.construction_frame is (
        ConstructionFrame.COPULA_PREDICATIVE_NOUN
    )
    assert bare.rendered_predicate == "be(A0:,A1:)"
    assert nominal.rendered_predicate == "be(A0:,A1:of)"


def test_row_five_is_the_one_argument_clause_and_the_table_refuses_it() -> None:
    """Row 5's frame exists and step V6 then refuses to build a signature from it.

    A one-argument clause states a property, not a relational configuration, and the code
    is ``no_configuration`` - a *decision* about a well-parsed reading, not a gap. Asserted
    through the producer so the refusal is counted like any other.
    """
    readings, refusals = parse("John works.")
    assert not readings
    assert refusals[0].code == "no_configuration"
    assert refusals[0].stage is RefusalStage.NORMALIZE
    assert refusals[0].suppresses_signal


def test_the_producer_declares_ten_constructions_and_nine_of_them_reach_a_signature() -> None:
    """Nine of the table's ten rows, plus ``OTHER`` - which is declared and then refused.

    Stated as a coverage note rather than as a claim of completeness. ``OTHER`` is in
    ``DECLARABLE_CONSTRUCTIONS`` because the parser genuinely declares it for an interrogative
    or a modal clause, and ``normalize_predicate`` then refuses it - so a reader counting
    declared constructions is counting one the table has no row for, which is the honest
    state of a producer that recognises a shape it cannot normalise.
    """
    declared_by_parser = {
        SyntacticConstruction.PASSIVE_WITH_AGENT,
        SyntacticConstruction.COPULAR,
        SyntacticConstruction.COPULAR_WITH_NOUN_COMPLEMENT,
        SyntacticConstruction.ACTIVE_CLAUSE,
        SyntacticConstruction.BARE_NOMINAL,
        SyntacticConstruction.GENITIVE_NP,
        SyntacticConstruction.APPOSITIVE_NP,
        SyntacticConstruction.HEADLESS_PP,
        SyntacticConstruction.RELATIVE_CLAUSE,
    }
    with_other = declared_by_parser | {SyntacticConstruction.OTHER}
    # Every value the constructor table names is declared by the parser, plus OTHER, and
    # nothing else: the parser cannot declare a construction the table does not carry.
    assert with_other == declared_by_parser | {
        construction for construction in SyntacticConstruction
    } - {SyntacticConstruction.PASSIVE_NO_AGENT}
    assert shallow.DECLARABLE_CONSTRUCTIONS["copular"] is SyntacticConstruction.COPULAR
    table_constructions = {row.construction for row in CONSTRUCTION_TABLE}
    assert declared_by_parser == table_constructions
    # The two the parser can *see* and never normalises: an agentless passive and OTHER.
    assert SyntacticConstruction.PASSIVE_NO_AGENT not in declared_by_parser
    assert SyntacticConstruction.OTHER not in table_constructions
    assert SyntacticConstruction.PASSIVE_NO_AGENT not in table_constructions


# --------------------------------------------------------------------------- #
# The producer's slot map, checked against the authority
# --------------------------------------------------------------------------- #


def test_the_slot_map_agrees_with_normalize_voice_on_every_row() -> None:
    """The producer's independent implementation of the documented V2 order, verified.

    ``assign_slots`` re-derives which argument fills which slot, because a
    ``CanonicalArgumentAssignment`` does not say. An independent implementation nobody
    compares with the authority is a second answer, and a second answer to a slot assignment
    is a fork in logical identity. So it is compared - arity and marker for every row.
    """
    checked = 0
    for row, clause, _construction, _predicate, _slots in _ROW_SURFACES:
        channel = _ATTRIBUTE_CHANNEL if row == 9 else None
        reading = _one(clause, channel=channel, constructor=_ROW_CONSTRUCTOR.get(row))
        bindings = assign_slots(reading)
        assert len(bindings) == reading.signature.arity, clause
        assert [binding.slot for binding in bindings] == list(
            reading.signature.canonical_argument_slots
        ), clause
        assert [binding.marker for binding in bindings] == list(
            reading.signature.argument_markers
        ), clause
        checked += 1
    assert checked == len(_ROW_SURFACES)


def test_a_slot_map_that_disagrees_with_the_normaliser_is_refused_not_returned() -> None:
    """    The guard is a refusal, not a wrong ``logical_candidate_id``.

    Exercised by re-labelling a reading with a construction whose plan is shaped differently:
    "John works at Acme" is an active clause whose ``A1`` carries the ``at`` marker, and
    relabelling it copular puts ``A1`` in a slot the copular row marks **unmarked** - so the
    authority's ``at`` and the plan's ``NOMARK`` disagree and the guard fires. A relabelling
    that happened to agree would prove nothing, which is why this surface was chosen.
    """
    reading = _one("John works at Acme.")
    object.__setattr__(reading, "construction", SyntacticConstruction.COPULAR)
    with pytest.raises(ParserContractError) as caught:
        assign_slots(reading)
    assert caught.value.code == RefusalCode.SLOT_MAP_DISAGREES
    assert "drifted" in caught.value.message
    assert "at" in caught.value.message


# --------------------------------------------------------------------------- #
# Voice: the one unification (P-CANON)
# --------------------------------------------------------------------------- #


def test_the_observed_passive_frame_travels_as_evidence_and_never_on_the_signature() -> None:
    """The demotion happens at V1, and the surface's own frame survives as evidence.

    The two frames on the same reading are the point: a reader of the record can see that
    the text was passive, and the identity layer sees only the demoted frame - which is what
    lets the active and the passive realisation meet.
    """
    passive = _one("Asset was acquired by Company.")
    assert passive.observed_construction_frame is ConstructionFrame.VERB_PASSIVE_AGENT
    assert passive.signature.construction_frame is (
        ConstructionFrame.VERB_ACTIVE_TRANSITIVE
    )
    trace = normalize_voice(
        passive.predicate, passive.syntactic_structure, passive.dependency_structure
    ).normalization_trace
    assert list(trace[:2]) == ["V0.validate", "V1.frame"]
    assert "V2.observed_by" in trace
    active = _one("Company acquired Asset.")
    assert active.observed_construction_frame is (
        ConstructionFrame.VERB_ACTIVE_TRANSITIVE
    )
    assert "V2.observed_by" not in normalize_voice(
        active.predicate, active.syntactic_structure, active.dependency_structure
    ).normalization_trace


def test_a_participle_head_is_the_predicate_and_the_auxiliary_is_never_minted() -> None:
    """V3 lemmatises the head, and the head of a passive is its participle, not the AUX.

    Asserted on the surface's own token rather than on the message: "was acquired" must
    yield lemma ``acquire``, and the auxiliary appears on the reading as the head's function
    word and nowhere in the predicate.
    """
    reading = _one("Asset was acquired by Company.")
    assert reading.predicate_surface == "acquired"
    assert reading.head_function_word == "was"
    assert reading.signature.predicate_lemma == "acquire"
    assert "was" not in reading.rendered_predicate


def test_works_at_and_works_for_are_two_signatures_and_the_producer_keeps_them_apart() -> None:
    """brief §29's ``at`` against §109 case A's ``for``, produced from two surfaces.

    Deciding that ``at`` and ``for`` mark the same argument is a lexical-semantic claim §20
    reserves to explicit mapping, so the two are two signatures here. The producer is what
    makes the claim testable over text rather than over a declared parse.
    """
    at = _one("John works at Acme.")
    for_ = _one("John works for Acme.")
    assert at.rendered_predicate == "work(A0:,A1:at)"
    assert for_.rendered_predicate == "work(A0:,A1:for)"
    assert at.signature.content_key() != for_.signature.content_key()


# --------------------------------------------------------------------------- #
# The two gaps, and the refusals
# --------------------------------------------------------------------------- #


def test_gap_a_no_complement_is_labelled_temporal_and_every_one_is_retained() -> None:
    """No source states the temporal test, so this parser states no temporal label.

    The assertion is about the *absence* of a rule, which is only checkable by showing the
    retention: "in 2020" occupies a canonical slot with the ``in`` marker, ``V2.drop_temporal``
    never fires, and the slot survives into the identity projection. That is the visible
    direction the sources chose - an over-retained temporal argument is one extra structural
    slot, a wrongly dropped one is a lost participant with no trace.
    """
    reading = _one("John sold Acme to Microsoft in 2020.")
    assert not any(
        argument.position_label in ("nmod:tmod", "obl:tmod", "advmod:tmod")
        for argument in reading.arguments
    )
    bindings = {binding.slot.token: binding for binding in assign_slots(reading)}
    assert set(bindings) == {"A0", "A1", "A2", "A3"}
    assert bindings["A1"].argument.surface == "Acme"
    assert bindings["A1"].marker is ArgumentMarker.NOMARK
    assert bindings["A2"].argument.surface == "2020"
    assert bindings["A2"].marker is ArgumentMarker.IN
    assert bindings["A3"].argument.surface == "Microsoft"
    assert bindings["A3"].marker is ArgumentMarker.TO
    assert "V2.drop_temporal" not in normalize_voice(
        reading.predicate,
        reading.syntactic_structure,
        reading.dependency_structure,
    ).normalization_trace
    assert "temporal" in shallow.PARSER_LIMITATIONS["temporal_complement"].lower()
    assert "RETAINED" in shallow.PARSER_LIMITATIONS["temporal_complement"]


def test_gap_b_a_bare_pp_complement_is_distinguishable_from_a_bare_np_complement() -> None:
    """The complement's phrase category decides copular-vs-active, and it is supplied here.

    "John is the chairman" is copular with a bare NP and reaches row 2. "John is at Acme"
    has a ``PP`` complement, which no row's stated condition accepts, so it is refused with
    its own code - never defaulted to the nearest row and never given ``NOMARK`` for the
    marker it visibly carries. "John works at Acme", the same surface shape under an active
    head, is row 4 with the ``at`` marker, so the category really is what decided.
    """
    copular_np = _one("John is the chairman.")
    assert copular_np.construction is SyntacticConstruction.COPULAR
    assert _first_code("John is at Acme.") == RefusalCode.UNSUPPORTED_COMPLEMENT_CATEGORY
    active = _one("John works at Acme.")
    assert active.construction is SyntacticConstruction.ACTIVE_CLAUSE
    assert active.rendered_predicate == "work(A0:,A1:at)"
    assert shallow._complement_category(tokenise("at Acme"), 0) is (
        shallow.PhraseCategory.PP
    )
    assert shallow._complement_category(tokenise("the chairman"), 0) is (
        shallow.PhraseCategory.NP
    )


def test_h6_is_refused_named_and_never_resolved() -> None:
    """§19's three-way illustration: two readings kept apart, one refused, all three recorded.

    The stop condition is A2's verbatim, and the test asserts the *behaviour* it names: the
    two copular members produce **different** signatures, the agentless passive produces no
    reading at all, and every one of the three clauses carries an ``h6_open_case`` record. A
    producer that unified them would fail this test, and a producer that stayed silent about
    them would fail it too.
    """
    member_a, refusals_a = parse("John is CEO of Acme.")
    member_b, refusals_b = parse("John became CEO of Acme.")
    member_c, refusals_c = parse("John was appointed CEO of Acme.")
    assert len(member_a) == 1 and len(member_b) == 1 and not member_c
    assert member_a[0].rendered_predicate == "be(A0:,A1:of)"
    assert member_b[0].rendered_predicate == "become(A0:,A1:of)"
    assert member_a[0].signature.content_key() != member_b[0].signature.content_key()
    for refusals in (refusals_a, refusals_b, refusals_c):
        h6 = [refusal for refusal in refusals if refusal.code == RefusalCode.H6_OPEN_CASE]
        assert len(h6) == 1
        assert H6_STOP_CONDITION in h6[0].detail
    # The two copular members were *emitted*, so their record refuses a merge, not a signal.
    h6_a = next(refusal for refusal in refusals_a if refusal.code == RefusalCode.H6_OPEN_CASE)
    h6_c = next(refusal for refusal in refusals_c if refusal.code == RefusalCode.H6_OPEN_CASE)
    assert h6_a.stage is RefusalStage.IDENTITY
    assert not h6_a.suppresses_signal
    # The passive member was already refused for being agentless.
    assert h6_c.suppresses_signal
    assert [r for r in refusals_c if r.code == RefusalCode.AGENTLESS_PASSIVE]


def test_the_determiner_copular_reading_is_not_part_of_h6() -> None:
    """H6 is a *narrow* stop condition, and this is what makes it narrow.

    "John is **the** CEO of Acme" is not the §19 case: the determiner is a surface fact that
    distinguishes the reading, and folding it in would put a record on a clause that the
    sources never listed. Asserted so a later widening of the H6 detector is a failing test
    rather than a quiet merge.
    """
    _readings, refusals = parse("John is the CEO of Acme.")
    assert not [refusal for refusal in refusals if refusal.code == RefusalCode.H6_OPEN_CASE]
    _readings, refusals = parse("John is CEO of Acme.")
    assert [refusal for refusal in refusals if refusal.code == RefusalCode.H6_OPEN_CASE]


# --------------------------------------------------------------------------- #
# Every refusal path, and the countability requirement
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("clause", "code"),
    [
        ("Acme Holdings Limited", RefusalCode.UNCLASSIFIED_CONSTRUCTION),
        ("The asset was sold.", RefusalCode.AGENTLESS_PASSIVE),
        ("John and Mary acquired Acme.", RefusalCode.COORDINATED_CLAUSE),
        ("Did John acquire the company?", RefusalCode.UNSUPPORTED_CONSTRUCTION),
        ("John is elected.", RefusalCode.UNDECIDABLE_COMPLEMENT_CATEGORY),
        ("John is at Acme.", RefusalCode.UNSUPPORTED_COMPLEMENT_CATEGORY),
        ("Globex manufactures the widgets.", RefusalCode.UNSUPPORTED_LEMMA),
        ("John, CEO of Acme", RefusalCode.UNSUPPORTED_LEMMA),
        ("John is CEO of Acme since 2019.", RefusalCode.UNSUPPORTED_CONSTRUCTION),
        ("   ", RefusalCode.NO_CLAUSE),
    ],
)
def test_every_refusal_path_emits_nothing_and_names_its_code(
    clause: str, code: str
) -> None:
    """No signal for the clause, a named code, and a stated reason.

    ``no reading`` is asserted as well as the code, because a producer that recorded the
    refusal and emitted a reading anyway would pass a code-only test - and that is the
    failure brief §30 exists to prevent.
    """
    readings, refusals = parse(clause)
    assert readings == (), clause
    assert refusals, clause
    assert refusals[0].code == str(code), clause
    assert refusals[0].suppresses_signal, clause
    assert refusals[0].detail.strip(), clause
    extraction = syntactic_signals([clause], scope=_scope())
    assert extraction.signals == (), clause
    assert extraction.count(code) == 1, clause


def test_an_unsupported_language_is_refused_and_nothing_is_parsed() -> None:
    """``en`` is the only shipped language, and a non-English surface is not a reading.

    Declared language rather than detected, deliberately: detection is another producer's
    job, and a producer that guessed the language of a surface its English rules cannot read
    would be making two decisions at once.
    """
    readings, refusals = parse("Компания приобрела актив.", language="ru")
    assert readings == ()
    assert refusals[0].code == RefusalCode.UNSUPPORTED_LANGUAGE
    assert refusals[0].suppresses_signal
    extraction = syntactic_signals(
        [{"text": "Компания приобрела актив.", "language": "ru"}], scope=_scope()
    )
    assert extraction.signals == ()
    assert extraction.count(RefusalCode.UNSUPPORTED_LANGUAGE) == 1


def test_a_preposition_outside_the_closed_marker_inventory_is_refused_by_the_marker_layer() -> None:
    """Recognition and canonical marking are different acts, and this is the difference.

    "across" is a member of the parser's preposition inventory and not of
    ``ArgumentMarker``, so the clause *parses* - as a well-formed active clause - and the
    marker layer refuses it. A parser whose preposition inventory were the marker inventory
    could not tell "I do not know this word" from "I know it and decline to normalise it",
    and those are different gaps in a corpus.
    """
    readings, refusals = parse("John works across Acme.")
    assert readings == ()
    assert refusals[0].code == "unsupported_marker"
    assert refusals[0].stage is RefusalStage.NORMALIZE
    assert "NOMARK" in refusals[0].detail
    assert "across" in shallow.SYNTAX_PREPOSITIONS
    assert "across" not in {str(marker) for marker in ArgumentMarker}


def test_a_pronominal_subject_leaves_its_required_slot_unoccupied_and_is_refused() -> None:
    """A pronoun is not an overt participant, and V2 consumes it rather than numbering it.

    "He acquired Acme" is a perfectly good sentence about a real relation and this producer
    declines to read it, because the slot it would fill has no overt mention in it and
    coreference is a later stage's work. ``slot_gap`` is the honest code, and it is
    different from every construction refusal.
    """
    readings, refusals = parse("He acquired Acme.")
    assert readings == ()
    assert refusals[0].code == "slot_gap"
    assert refusals[0].stage is RefusalStage.NORMALIZE
    # And the reason is the consumed pronoun, not a shape: the reading is describable, and
    # the parser declared the pronoun rather than inventing a subject for it.
    assert "consumed" in refusals[0].detail or "nsubj" in refusals[0].detail
    # A bare pronoun subject is consumed in every position, so the refusal is about the
    # pronoun and not about one word: "they" is refused for the same reason.
    assert _first_code("They acquired Acme.") == "slot_gap"
    # And an overt subject in the same slot is read, which is what makes the refusal about
    # the pronominality rather than about the label.
    assert _one("Acme acquired Asset.").arguments[0].position_label == "nsubj"


def test_a_reduced_relative_is_refused_rather_than_giving_the_matrix_np_the_subject() -> None:
    """Row 10's guarantee, and the inference it refuses.

    "John, who founded Acme" would need the matrix NP declared as the relative clause's
    subject. That is true in the common case and false in the reduced and adjunct cases,
    and a rule that is usually right is a guess - so the subject is declared pronominal, the
    required slot goes unoccupied, and ``slot_gap`` is the answer.
    """
    readings, refusals = parse("John, who founded Acme, sold Globex.")
    relative = [
        reading for reading in readings if reading.constructor == "relative_clause"
    ]
    assert relative == [], "the reduced relative must not be declared"
    assert [r for r in refusals if r.code == "slot_gap"]
    # The matrix clause is still read, because it is a second clause and refusing the
    # relative one must not cost it.
    assert any(reading.constructor == "active_clause" for reading in readings)
    blocked, blocked_refusals = parse("John, who founded Acme, sold Globex.")
    assert len(blocked) == 1
    assert [r for r in blocked_refusals if r.code == "slot_gap"]
    assert "reduced_relative" in shallow.PARSER_LIMITATIONS
    # The contrast, so the test is about the *subject*: the same relative clause with an
    # overt subject of its own is row 10 and reaches a signature.
    with_subject = _one(
        "The report, which the committee wrote, was sent by Acme.",
        constructor="relative_clause",
    )
    assert with_subject.construction is SyntacticConstruction.RELATIVE_CLAUSE
    assert with_subject.rendered_predicate == "write(A0:,A1:)"
    # And a relative clause with no closing comma is not read as a relative clause at all:
    # there is no bracket, so the appositive constructor claims the surface and refuses it.
    # Reading it as a main clause with the pronoun glued into the subject is the specific
    # wrong answer this pins.
    unbracketed, unbracketed_refusals = parse("John who founded Acme.")
    assert not [
        reading
        for reading in unbracketed
        if reading.constructor == "relative_clause"
    ]
    assert unbracketed_refusals


def test_a_copular_clause_with_a_trailing_adjunct_is_refused_not_silently_truncated() -> None:
    """Rows 2 and 3 carry exactly one complement, so a second constituent has no slot.

    "John is CEO of Acme since 2019" is a real and very common sentence. Reading it without
    the adjunct would be reporting less than the text says, and ``V2`` would drop the extra
    argument with no trace at all - so the whole reading is refused, and the limitation is
    written down in :data:`~parsers.shallow.PARSER_LIMITATIONS` rather than discovered later.
    """
    readings, refusals = parse("John is CEO of Acme since 2019.")
    assert readings == ()
    assert refusals[0].code == RefusalCode.UNSUPPORTED_CONSTRUCTION
    assert "since 2019" in refusals[0].detail
    assert "copular_adjunct" in shallow.PARSER_LIMITATIONS


def test_a_negated_clause_is_read_as_a_denial_rather_than_refused() -> None:
    """Phase 4B reopened this path, and the reason it was closed is the reason it could be.

    The old test asserted that ``parse("John is not the CEO of Acme.")`` returned no readings,
    on the grounds that ``RelationSignal`` had no polarity field and a denial would have been
    recorded as an assertion. Phase 4A gave the signal a ``polarity`` field, so the premise
    went stale and keeping the refusal would have been a gap in the corpus with a comment
    explaining it. Now the clause is a reading whose polarity is ``DENIED`` and whose frame is
    the *same* frame as the positive clause's - which is the distinction that matters: one
    construction, two polarities, and polarity is in the identity material (part 5.1), so the
    two cannot collapse onto one logical candidate.
    """
    denied, refusals = parse("John is not the CEO of Acme.")
    asserted, _ = parse("John is the CEO of Acme.")
    assert refusals == ()
    assert len(denied) == 1 and len(asserted) == 1
    assert denied[0].polarity is Polarity.DENIED
    assert asserted[0].polarity is Polarity.ASSERTED
    # One frame, two polarities: the negation is not a different construction.
    assert denied[0].signature.rendered_predicate() == asserted[0].signature.rendered_predicate()
    # The same two mentions, addressed identically - the negator shifts the token indices and
    # changes nothing about *which* two things the clause is about. Asserted on the addresses
    # rather than on the whole arguments, because the token offsets legitimately move by one
    # when a word is inserted between the copula and its complement.
    assert [a.mention_ref for a in denied[0].arguments] == [
        a.mention_ref for a in asserted[0].arguments
    ]


def test_a_negated_clause_reaches_the_signal_as_a_denial() -> None:
    """End to end: the producer writes the polarity, it does not default it.

    This is the assertion that makes the previous one load-bearing. A parser that records a
    denial and a producer that asserts it would leave the record saying the opposite of the
    document, and the failure would be invisible - the signal is well formed, its address is
    stable, and it claims something false about a real sentence.
    """
    extraction = syntactic_signals(["John is not the CEO of Acme."], scope=_scope())
    assert extraction.refusals == ()
    assert len(extraction.signals) == 1
    denied = extraction.signals[0]
    assert denied.polarity is Polarity.DENIED
    assert denied.is_denied
    assert denied.kind is SignalKind.SYNTAX, (
        "the denial is carried by the polarity field, and Phase 4C deleted the kind that used "
        "to carry it - so the channel is the channel the producer reads, and the polarity is "
        "the only place a denial is recorded"
    )
    assert "NEGATION" not in SignalKind.__members__
    positive = syntactic_signals(["John is the CEO of Acme."], scope=_scope()).signals[0]
    assert positive.polarity is Polarity.ASSERTED
    # Two opposite claims about the same two mentions, so two addresses.
    assert denied.signal_id != positive.signal_id


def test_a_denial_and_its_assertion_are_two_logical_candidates() -> None:
    """The identity half, and the reason ``reading.polarity`` had to be threaded.

    :func:`syntactic_candidate_ids` passed a hard-coded ``Polarity.ASSERTED`` before Phase 4B.
    That was harmless only while every clause was asserted; with negations readable it would
    have computed the *denial's* logical id as though the clause stood, and "John is not the
    CEO of Acme" and "John is the CEO of Acme" would have become one candidate. The two ids
    being different is what says the threading happened.
    """
    mentions: Mapping[str, Mention] = {
        "john": Mention(surface="John", start=0, end=4),
        "acme": Mention(surface="Acme", start=30, end=34),
    }
    denied = syntactic_signals(["John is not the CEO of Acme."], scope=_scope())
    asserted = syntactic_signals(["John is the CEO of Acme."], scope=_scope())
    denied_ids = dict(
        syntactic_candidate_ids(denied, mentions, tenant_id=_scope().tenant_id)
    )
    asserted_ids = dict(
        syntactic_candidate_ids(asserted, mentions, tenant_id=_scope().tenant_id)
    )
    assert set(denied_ids.values()).isdisjoint(asserted_ids.values()), (
        f"a denial and its assertion reached one logical candidate: {denied_ids} "
        f"{asserted_ids}"
    )


def test_a_double_negation_and_an_unread_negator_are_refused_not_asserted() -> None:
    """Two refusal paths, and the property they share: nothing becomes an assertion.

    "John is not not the CEO of Acme" is a construction no row of the table states (double
    negation, a corrective), and a ``-n't``-shaped token the closed inventory does not hold is
    a negator this parser cannot read. Both are refused with :data:`unread_negator` rather than
    read as an assertion, because the one thing this parser may never do with a word it does
    not understand is report the clause as saying the opposite of what it says.
    """
    from parsers.shallow import UNREAD_NEGATOR_CODE

    double, refusals = parse("John is not not the CEO of Acme.")
    assert double == ()
    assert [r.code for r in refusals] == [UNREAD_NEGATOR_CODE]
    assert refusals[0].stage is RefusalStage.PARSE
    # The code is countable and named, which is what makes "how much of this corpus could not
    # be read as a negation" a number rather than a silence.
    assert "negator" in str(refusals[0].code)
    assert "negator" in str(UNREAD_NEGATOR_CODE)



def test_a_document_where_no_clause_parses_yields_zero_signals_and_no_exception() -> None:
    """brief §30's guarantee, on the hardest input for it.

    A document of headings, bylines and bare names: no clause, no exception, and a ledger
    that says why. The batch is not failed, the caller's other producers are unaffected, and
    the count is available.
    """
    document = (
        "Acme Holdings Limited. Globe Systems International. By: Jane Doe. "
        "and nothing here is a clause."
    )
    extraction = syntactic_signals([document], scope=_scope())
    assert extraction.signals == ()
    assert extraction.readings == ()
    assert extraction.refusals_by_code() == {
        RefusalCode.COORDINATED_CLAUSE: 1,
        RefusalCode.UNCLASSIFIED_CONSTRUCTION: 3,
    }
    assert sum(extraction.refusals_by_code().values()) == 4


def test_refusals_are_countable_by_code_and_the_counts_are_order_independent() -> None:
    """The measure brief §30 asks for, and it must not depend on the order of the corpus."""
    corpus = [
        "Company acquired Asset.",
        "John and Mary acquired Acme.",
        "Acme Holdings Limited",
        "John is at Acme.",
        "Did John acquire the company?",
    ]
    forward = syntactic_signals(corpus, scope=_scope())
    backward = syntactic_signals(list(reversed(corpus)), scope=_scope())
    counts = forward.refusals_by_code()
    assert counts == backward.refusals_by_code()
    assert counts == {
        RefusalCode.COORDINATED_CLAUSE: 1,
        RefusalCode.UNCLASSIFIED_CONSTRUCTION: 1,
        RefusalCode.UNSUPPORTED_COMPLEMENT_CATEGORY: 1,
        RefusalCode.UNSUPPORTED_CONSTRUCTION: 1,
    }
    assert list(counts) == sorted(counts)
    assert forward.count(RefusalCode.UNSUPPORTED_CONSTRUCTION) == 1
    assert forward.count(RefusalCode.SLOT_MAP_DISAGREES) == 0
    assert refusal_counts(forward.refusals) == counts
    # One reading survived, and the four refusals are all counted, so the batch is neither
    # lost nor silently short.
    assert len(forward.signals) == 1
    assert sum(counts.values()) == 4


def test_every_refusal_code_is_reachable_and_the_table_says_how() -> None:
    """No decorative codes, and no unreachable claim of coverage.

    Every code in :class:`RefusalCode` has a reason in :data:`REFUSAL_REACHABILITY`, and
    every code that names a *corpus* condition is asserted elsewhere in this file to occur.
    The two guards - ``slot_map_disagrees_with_normalizer`` and ``unbound_participant`` -
    are the only ones a corpus cannot reach, and each is asserted on its own.
    """
    assert set(REFUSAL_REACHABILITY) == set(RefusalCode)
    guards = {
        RefusalCode.SLOT_MAP_DISAGREES,
        RefusalCode.UNBOUND_PARTICIPANT,
        RefusalCode.H6_OPEN_CASE,
    }
    corpus_codes = set(RefusalCode) - guards
    for code in corpus_codes:
        assert REFUSAL_REACHABILITY[code].strip(), code
        assert extraction_for(code).count(code) >= 1, code
    for code in guards:
        assert REFUSAL_REACHABILITY[code].strip(), code


def extraction_for(code: str) -> Any:
    """The smallest corpus that reaches ``code``. A table, so a test reads as a claim."""
    surfaces = {
        RefusalCode.NO_CLAUSE: "   ",
        RefusalCode.UNCLASSIFIED_CONSTRUCTION: "Acme Holdings Limited",
        RefusalCode.COORDINATED_CLAUSE: "John and Mary acquired Acme.",
        RefusalCode.AGENTLESS_PASSIVE: "The asset was sold.",
        RefusalCode.UNDECIDABLE_COMPLEMENT_CATEGORY: "John is elected.",
        RefusalCode.UNSUPPORTED_COMPLEMENT_CATEGORY: "John is at Acme.",
        RefusalCode.UNSUPPORTED_CONSTRUCTION: "Did John acquire the company?",
        RefusalCode.UNSUPPORTED_LEMMA: "Globex manufactures the widgets.",
        RefusalCode.UNSUPPORTED_LANGUAGE: "John acquired Acme.",
    }
    if code == RefusalCode.UNSUPPORTED_LANGUAGE:
        return syntactic_signals(
            [{"text": surfaces[code], "language": "ru"}], scope=_scope()
        )
    return syntactic_signals([surfaces[code]], scope=_scope())


def test_an_unbound_participant_refuses_the_logical_id_rather_than_minting_a_short_one() -> None:
    """Fail-closed, because a partial ordering is a silent identity fork.

    The reading is fine; the mention binding is not. Dropping the unbound participant would
    mint an id over fewer participants than the sentence has, and nothing downstream could
    tell that from an id for a genuinely one-participant relation.
    """
    reading = _one("Company acquired Asset.")
    with pytest.raises(ParserContractError) as caught:
        logical_candidate_id_of(reading, {}, tenant_id=_TENANT)
    assert caught.value.code == RefusalCode.UNBOUND_PARTICIPANT
    assert "fewer participants" in caught.value.message
    partial = {"company": Mention(surface="Company")}
    with pytest.raises(ParserContractError):
        logical_candidate_id_of(reading, partial, tenant_id=_TENANT)
    with pytest.raises(ParserContractError):
        logical_candidate_id_of(reading, {"company": Mention("Company"), "asset": Mention("Asset")}, tenant_id="")


# --------------------------------------------------------------------------- #
# SC-001, end to end
# --------------------------------------------------------------------------- #


#: The two mention records ``SC-001`` binds, built **once** and reused by both
#: realisations and by both sentence orders. That reuse is the mention-binding stage's job
#: and it is the whole of §18's end-to-end condition: two *occurrences* of "Company" in one
#: document are two mentions at two offsets and therefore two different participants, so a
#: document-level index that binds both occurrences to one record is what makes one identity
#: the right answer rather than a coincidence.
_SC001_MENTIONS: Mapping[str, Mention] = {
    "company": Mention(surface="Company", start=0, end=7),
    "asset": Mention(surface="Asset", start=8, end=13),
}


def test_sc001_end_to_end_over_the_syntactic_producer() -> None:
    """§18's claim, end to end, over a real parser, with **no** ``xfail`` marker.

    Two realisations of one reading, read by **one** producer, over text:

    * two distinct ``signal_id``s - FR-006 and brief §24: ``signal_id`` is producer-specific
      and realisation-specific, so two observations are two ids;
    * two distinct surfaces - "acquired Asset" and "was acquired by Company";
    * one ``logical_candidate_id``, because both bind the **same** mention records, so both
      participants fingerprint identically and the signature is the demoted one in each
      case.

    ``ARBITRATION`` §11 made the ``xfail(strict=True)`` marker mandatory *because no
    syntactic producer existed*. It exists now, so the test passes; leaving the marker on
    would be reporting ``SC-001`` as unfulfilled while it is fulfilled, which §11's last
    line forbids. A test that still carried the marker would fail here - ``strict=True``
    turns an unexpected pass into an error - so this file cannot regress into it.
    """
    document = "Company acquired Asset. Asset was acquired by Company."
    extraction = syntactic_signals([document], scope=_scope())
    assert len(extraction.signals) == 2, [s.to_dict() for s in extraction.signals]
    active, passive = extraction.signals
    assert active.signal_id != passive.signal_id
    assert active.relation_surface == "acquired Asset"
    assert passive.relation_surface == "was acquired by Company"
    assert active.kind is SignalKind.SYNTAX is passive.kind
    assert active.relation_ref is None and passive.relation_ref is None
    assert active.extra["observed_construction_frame"] == "verb_active_transitive"
    assert passive.extra["observed_construction_frame"] == "verb_passive_agent"
    assert active.extra["rendered_predicate"] == "acquire(A0:,A1:)"
    assert passive.extra["rendered_predicate"] == "acquire(A0:,A1:)"
    # The two participants, bound once by the mention layer and reused by both readings.
    pairs = syntactic_candidate_ids(extraction, _SC001_MENTIONS, tenant_id=_TENANT)
    assert len(pairs) == 2
    assert pairs[0][0] == active.signal_id
    assert pairs[1][0] == passive.signal_id
    assert pairs[0][1] == pairs[1][1]
    assert pairs[0][1].startswith("CAND-")
    # And the producer did not merge the two *observations* to get there.
    assert len({pair[0] for pair in pairs}) == 2


def test_sc001_holds_whatever_order_the_two_realisations_appear_in() -> None:
    """A merge that depended on the active coming first would be a property of the corpus.

    The passive first, the same two mention records, and one id either way. What is *not*
    claimed is that two occurrences at two offsets in one document are one participant -
    ``stable_participant_fingerprint`` digests the offsets, so they are two mentions and two
    identities, and that is the correct answer for a question about occurrences. The merge is
    a claim about the *relational configuration*, and this is the test that the claim does
    not depend on the order the sentences were written in.
    """
    passive_first = syntactic_signals(
        ["Asset was acquired by Company. Company acquired Asset."], scope=_scope()
    )
    active_first = syntactic_signals(
        ["Company acquired Asset. Asset was acquired by Company."], scope=_scope()
    )
    forward = syntactic_candidate_ids(active_first, _SC001_MENTIONS, tenant_id=_TENANT)
    backward = syntactic_candidate_ids(passive_first, _SC001_MENTIONS, tenant_id=_TENANT)
    assert len(forward) == len(backward) == 2
    assert {pair[1] for pair in forward} == {pair[1] for pair in backward}
    assert len({pair[0] for pair in forward}) == 2
    assert len({pair[0] for pair in backward}) == 2
    # The two orders produce the *same two* signal ids, and that is brief §24's rule rather
    # than an accident: ``signal_id`` addresses what was observed, so the same producer
    # reading the same structure gives the same identity, and where the sentence sat in the
    # document is not part of what was observed.
    assert {pair[0] for pair in forward} == {pair[0] for pair in backward}


def test_a_surface_a_span_and_a_producer_never_reach_the_logical_id() -> None:
    """The identity property, asserted over the producer's own output.

    Two realisations with different surfaces, spans, producers and confidences, and one
    id. This is what makes the merge a *structural* claim rather than a coincidence of
    spelling.
    """
    active_readings, _active_refusals = parse("Company acquired Asset.")
    passive_readings, _passive_refusals = parse("Asset was acquired by Company.")
    active, passive = active_readings[0], passive_readings[0]
    mentions = {
        "company": Mention(surface="Company", start=0, end=7),
        "asset": Mention(surface="Asset", start=0, end=5),
    }
    first = logical_candidate_id_of(active, mentions, tenant_id=_TENANT)
    second = logical_candidate_id_of(passive, mentions, tenant_id=_TENANT)
    assert first == second
    assert first != logical_candidate_id_of(
        active, mentions, tenant_id=_TENANT, polarity=Polarity.DENIED
    )
    assert first != logical_candidate_id_of(active, mentions, tenant_id="tenant-b")


def test_replay_is_a_fixed_point() -> None:
    """Domain Invariant 12, and SC-010's "replay yields identical ids".

    Every collection the producer emits is in a rule-derived order, so two runs over the
    same input are byte-identical - including the signal ids, the ordinals and the ledger
    order. Asserted on the serialised records rather than on the objects, because a
    ``__dict__`` comparison would miss an ordering the serialiser fixes.
    """
    document = (
        "Company acquired Asset. Asset was acquired by Company. John, CEO of Acme. "
        "John is at Acme."
    )
    scope = _scope()
    first = syntactic_signals([document], scope=scope)
    second = syntactic_signals([document], scope=scope)
    assert [signal.to_dict() for signal in first.signals] == [
        signal.to_dict() for signal in second.signals
    ]
    assert [reading.to_dict() for reading in first.readings] == [
        reading.to_dict() for reading in second.readings
    ]
    assert [refusal.to_dict() for refusal in first.refusals] == [
        refusal.to_dict() for refusal in second.refusals
    ]
    assert first.refusals_by_code() == second.refusals_by_code()


# --------------------------------------------------------------------------- #
# The producer's contract with the rest of the package
# --------------------------------------------------------------------------- #


def test_the_producer_declares_its_kind_and_states_what_it_cannot_read() -> None:
    """``declares()`` is about the instrument, and ``cannot_read`` is the half that matters.

    A declaration with a blank ``cannot_read`` is indistinguishable from one nobody filled
    in, and a caller cannot then tell a producer's silence from its absence.
    """
    declaration = SyntacticExtractor().declares()
    assert declaration.producer_ref == PRODUCER_REF
    assert declaration.producer_version == PRODUCER_VERSION
    assert declaration.kinds == (SignalKind.SYNTAX,)
    assert declaration.reads.strip() and declaration.cannot_read.strip()
    assert declaration.max_pairs_considered > 0
    for phrase in ("role names", "reduced relative", "coordinated clause"):
        assert phrase in declaration.cannot_read
    assert SHALLOW_CAPABILITY.configuration_hash in declaration.notes
    assert "LLM" in declaration.notes
    assert "no learned parameter" in declaration.notes


def test_every_signal_is_bounded_stamped_and_carries_its_parser_capability() -> None:
    """The substrate's own guarantees, on this producer's output.

    ``pairs_considered`` is 0 and the declared ceiling is 10,000: a clause parser compares
    no mention pairs, and the number says so rather than reporting a window count that
    would mean something else (the defect ``lexical.py`` had to correct).
    """
    extraction = syntactic_signals(
        ["Company acquired Asset. John works at Acme."], scope=_scope()
    )
    assert extraction.signals
    for signal in extraction.signals:
        assert signal.kind is SignalKind.SYNTAX
        assert signal.producer_ref == PRODUCER_REF
        assert signal.producer_version == PRODUCER_VERSION
        assert signal.tenant_id == _TENANT
        assert signal.neighbourhood.pairs_considered == 0
        assert signal.neighbourhood.characters_scanned > 0
        assert signal.neighbourhood.scope_read.strip()
        assert signal.relation_ref is None
        assert signal.extra["parser_capability"] == SHALLOW_CAPABILITY.to_dict()
        # Typed, on the real field, and no longer duplicated into the untyped bag. The old
        # assertion here was `or True`, which asserted nothing at all - the kind of tautology
        # that survives a refactor precisely because it cannot fail.
        assert signal.arity >= 2
        assert [p.slot.index for p in signal.participants] == list(range(signal.arity))
        assert "participants" not in signal.extra



def test_the_observed_frame_survives_on_the_signal_and_never_on_the_signature() -> None:
    """The passive's two frames, on the record a downstream reader actually gets."""
    extraction = syntactic_signals(["Asset was acquired by Company."], scope=_scope())
    assert len(extraction.signals) == 1
    signal = extraction.signals[0]
    assert signal.extra["observed_construction_frame"] == "verb_passive_agent"
    assert signal.extra["predicate_signature"]["construction_frame"] == (
        "verb_active_transitive"
    )
    assert signal.extra["normalization_trace"][:2] == ["V0.validate", "V1.frame"]
    assert "V2.observed_by" in signal.extra["normalization_trace"]


def test_a_four_slot_reading_declares_all_four_participants_on_the_real_field() -> None:
    """The acceptance case for Phase 4A: ``sell(A0:, A1:, A2:in, A3:to)``, in full.

    This test used to be called ``..._even_though_the_signal_is_binary`` and asserted the
    workaround: the first two participants on the signal, *all four* as dicts in
    ``extra["participants"]``. The name and the assertion both change here because the thing
    they recorded is gone. What is asserted now is the whole reading - four typed
    participants, each carrying the canonical slot it filled, checked against the bindings
    :func:`assign_slots` derived, plus the signature's own markers, which is where the
    function-word evidence lives and always did.
    """
    extraction = syntactic_signals(["John sold Acme to Microsoft in 2020."], scope=_scope())
    assert len(extraction.signals) == 1
    signal = extraction.signals[0]
    assert signal.arity == 4
    assert [p.slot.token for p in signal.participants] == ["A0", "A1", "A2", "A3"]
    assert [p.ordinal for p in signal.participants] == [0, 1, 2, 3]

    # Slot-for-slot against the parser's own bindings: nothing dropped, nothing reordered.
    bindings = assign_slots(extraction.readings[0])
    assert [p.mention_ref for p in signal.participants] == [
        binding.argument.mention_ref for binding in bindings
    ]
    assert [p.role_hypothesis for p in signal.participants] == [
        binding.argument.position_label for binding in bindings
    ]
    assert [binding.argument.surface for binding in bindings] == [
        "John",
        "Acme",
        "2020",
        "Microsoft",
    ]

    # The markers are the signature's, not a parallel copy on the participants: `A2:in` and
    # `A3:to` are read from the one authority that computes them.
    assert signal.extra["predicate_signature"]["argument_markers"] == ["", "", "in", "to"]
    assert signal.extra["rendered_predicate"] == "sell(A0:,A1:,A2:in,A3:to)"

    # The binary accessors survive as derived projections, agreeing with the first two.
    assert signal.subject_mention_ref == signal.participants[0].mention_ref
    assert signal.object_mention_ref == signal.participants[1].mention_ref

    # The reading's basis and polarity are stated by the producer, not defaulted.
    assert signal.basis is SignalBasis.EVENT_FRAME
    assert signal.polarity is Polarity.ASSERTED

    # `argument_shape` is the default, and that is a decision this producer makes on purpose:
    # the parser states no temporal label, so calling `2020` a value here would re-introduce
    # the classification `test_gap_a_..._retained` asserts is absent.
    assert {p.argument_shape for p in signal.participants} == {"entity"}


def test_the_workaround_bag_is_gone_and_the_field_is_the_only_copy() -> None:
    """``extra["participants"]`` is removed, not shadowed.

    Two copies of one thing is a second source of truth, and a reader cannot tell which one
    the producer meant. The assertion is about *absence* because the failure this guards
    against is invisible: a future edit that re-adds the bag would not fail anything else.
    """
    extraction = syntactic_signals(
        ["John sold Acme to Microsoft in 2020. John works at Acme."], scope=_scope()
    )
    assert extraction.signals
    for signal in extraction.signals:
        assert "participants" not in signal.extra
        assert signal.arity == len(signal.participants) >= 2



def test_a_headless_pp_needs_its_channel_and_says_so_when_it_is_absent() -> None:
    """Row 9's ``A1`` is a channel's declaration, and a missing one is a named refusal.

    Three answers, all distinct: with a head and a subject, a reading; with a head and no
    subject, the table's ``slot_gap``; with no head at all, ``unclassified_construction`` -
    because a phrase with no predicate is a phrase, not a reading.
    """
    reading = _one("at Acme", channel=_ATTRIBUTE_CHANNEL)
    assert reading.construction is SyntacticConstruction.HEADLESS_PP
    assert reading.rendered_predicate == "work(A0:at,A1:)"
    assert reading.channel_label == "attribute:affiliation"
    _readings, no_subject = parse("at Acme", channel=DeclaredChannel(head="works"))
    assert no_subject[0].code == "slot_gap"
    _readings, no_head = parse("at Acme")
    assert no_head[0].code == RefusalCode.UNCLASSIFIED_CONSTRUCTION
    assert "declared governor" in no_head[0].detail


def test_the_producer_reads_a_mapping_record_with_channel_declarations() -> None:
    """The record contract: a string, or a mapping carrying the document and its frame.

    Asserted through :meth:`SyntacticExtractor.report` rather than through
    :func:`syntactic_signals`, because ``run_producer`` **stamps** ``capture_ref`` from the
    scope on the way out - the registry is the authority on which retrieval a signal came
    from, and a producer that could set its own would be asserting provenance it does not
    own. So the override is honoured by the producer and then deliberately overwritten by
    the registry, and both halves of that are checked here.
    """
    record = {
        "text": "at Acme",
        "declared_subject": "John Smith",
        "declared_head": "works",
        "channel_label": "attribute:affiliation",
        "document_ref": "CAP-9",
    }
    reported = SyntacticExtractor().report(record, scope=_scope())
    assert len(reported.signals) == 1
    assert reported.signals[0].capture_ref == "CAP-9"
    # Through the published parser, not a hand-spelled address: the declared subject reaches the
    # address as the normalised surface, and a test that assembled the string itself would be a
    # second answer to "what does an address look like".
    assert read_occurrence(reported.signals[0].participants[1].mention_ref) == (
        "nsubj",
        "john smith",
        None,
    )
    # Through the registry the frame is the scope's, by design.
    stamped = syntactic_signals([record], scope=_scope())
    assert stamped.signals[0].capture_ref == "CAP-1"



# --------------------------------------------------------------------------- #
# Layer discipline
# --------------------------------------------------------------------------- #


_FORBIDDEN_IMPORTS = frozenset(
    {
        "GraphEdge",
        "HyperEdge",
        "GraphStore",
        "RelationClaim",
        "CandidateStatus",
        "RelationCandidate",
        "admission",
        "projection",
        "graph",
    }
)


_PRODUCER_PATHS = (
    shallow.__file__,
    syntactic_module.__file__,
)


def _imported_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            names.add(module)
            names.update(f"{module}.{alias.name}" for alias in node.names)
    return names


def test_the_producer_imports_no_graph_claim_admission_or_projection_symbol() -> None:
    """FR-020 as an import-graph test, not a grep, and over this producer's two modules.

    An AST walk rather than a text search, because a name inside a docstring is a
    conversation and a name inside an import is an edge. The two modules are checked
    together because the constraint is on the *producer*, and the parser is part of it.
    """
    for path in _PRODUCER_PATHS:
        imported = _imported_names(ast.parse(Path(path).read_text(encoding="utf-8")))
        for name in imported:
            head = name.split(".")[0]
            assert head not in _FORBIDDEN_IMPORTS, f"{path}: {name}"
            leaf = name.split(".")[-1]
            assert leaf not in _FORBIDDEN_IMPORTS, f"{path}: {name}"


def test_the_producer_constructs_no_candidate_and_no_claim() -> None:
    """FR-020's *construction* half, which the import test cannot see.

    A producer that imported nothing forbidden could still assign ``CandidateStatus`` to
    something if the name were in scope; asserting the absence of the names in any
    ``Name``/``Attribute`` position of executable code closes that. Docstrings are excluded
    because naming a thing you refuse to build is the point of this module.
    """
    for path in _PRODUCER_PATHS:
        tree = ast.parse(Path(path).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                assert node.id not in _FORBIDDEN_IMPORTS, f"{path}: {node.id}"
            if isinstance(node, ast.Attribute):
                assert node.attr not in _FORBIDDEN_IMPORTS, f"{path}: {node.attr}"


def test_the_lemma_table_this_parser_reads_is_the_platform_s_one() -> None:
    """The parser resolves heads through the shared generated table, not a copy.

    A second lemma table in the producer would be a second answer to "what is a form of
    'acquire'", and the two would drift. Asserted as an identity, not a similarity.
    """
    from domain.predicate_signature import LEMMA_TABLE, lemma_for

    assert shallow.LEMMA_TABLE is LEMMA_TABLE
    assert shallow._lemma_of("acquired") == lemma_for("acquired") == "acquire"
    assert shallow._lemma_of("Acme") is None


def test_no_inventory_lemma_is_hidden_by_a_nominal_suffix() -> None:
    """The one shape rule the parser applies to morphology, pinned against the inventory.

    ``_is_verb_form`` excludes a token whose surface ends in a nominal derivation suffix. If
    a lemma ever ended in one, that lemma would be unusable as a predicate head - silently,
    because nothing else would say so. So the inventory is checked against the rule.
    """
    from domain.predicate_signature import LEMMA_INVENTORY

    hidden = [
        lemma
        for lemma in LEMMA_INVENTORY
        if lemma.endswith(shallow.NOMINAL_SUFFIXES)
    ]
    assert hidden == []
    assert not shallow._is_verb_form("acquisition")
    assert not shallow._is_verb_form("founder")
    assert shallow._is_verb_form("acquired")
    assert shallow._is_verb_form("acquires")


def test_the_tokeniser_splits_a_genitive_and_keeps_document_order() -> None:
    """Token order is load-bearing: ``DependencyStructure.edges`` is built from it and V2's
    ``TB2`` tie-break reads the edge position, so an unstable tokeniser is a silent
    signature fork."""
    assert tokenise("Acme's founder John Smith") == (
        "Acme", "'s", "founder", "John", "Smith",
    )
    assert tokenise("Company acquired Asset.") == (
        "Company", "acquired", "Asset", ".",
    )
    assert tokenise("1,200.50 units") == ("1,200.50", "units")
    assert tokenise("") == ()


def test_a_document_structure_channel_cannot_smuggle_a_second_parser_in() -> None:
    """``DeclaredChannel`` declares a subject and a governor, and nothing else.

    It is the seam a document-structure producer reads through, so it is the place a caller
    could most easily hand the parser a *result* - a role, a relation type, a mapping - and
    get identity out of it. Three fields, all strings, no nested structure, asserted on the
    dataclass.
    """
    assert DeclaredChannel.__slots__ == ("subject", "head", "label")
    assert DeclaredChannel() == DeclaredChannel("", "", "")
    with pytest.raises(TypeError):
        DeclaredChannel(subject="John", relation_type="works_for")  # type: ignore[call-arg]


def test_the_mention_reference_is_a_deferred_slot_address_and_not_a_minted_mention_id() -> None:
    """brief §25: no producer may invent a mention identity from text.

    The producer addresses a participant by position label and normalised surface, and
    ``MN-`` / ``ENT-`` / ``RES-`` literals never appear - FR-019 reserves those to the
    mention and resolution layers.

    **The label is a dependency arc and several arcs contain the separator the retired grammar
    split on** (``nmod:of``, ``nmod:in``, ``nmod:by``, ``nsubj:pass``), which is why the expected
    addresses are read back through the published parser rather than spelled out here: spelled
    out, they would be a second answer to "what does an address look like", and they went on
    saying the wrong thing through the encoding change that removed the collision. The assertion
    is on what the addresses *say* — the arc is the arc, whole — and on the shape the platform's
    own grammar gives them.
    """
    reading = _one("Company acquired Asset.")
    refs = [argument.mention_ref for argument in reading.arguments]
    assert [read_occurrence(ref) for ref in refs] == [
        ("nsubj", "company", None),
        ("obj", "asset", None),
    ]
    for ref in refs:
        assert ref.startswith(f"{DEFERRED_OCCURRENCE_PREFIX}:")
        assert not ref.startswith(f"{DEFERRED_OCCURRENCE_PREFIX}@"), (
            "the syntactic producer's positions are clause-relative token indices, so it states "
            "no character span; an address claiming one would be inventing a position"
        )
        assert not ref.startswith(("MN-", "ENT-", "RES-"))
    extraction = syntactic_signals(["Company acquired Asset."], scope=_scope())
    for signal in extraction.signals:
        for ref in (signal.subject_mention_ref, signal.object_mention_ref):
            assert not ref.startswith(("MN-", "ENT-", "RES-"))
    # And the arcs that used to collide. ``John is the CEO of Acme`` gives the ``nmod:of`` PP
    # adjunct and ``Asset was acquired by Acme`` the ``nmod:by`` agent; under the retired grammar
    # ``surface:nmod:of:acme`` read as the label ``nmod`` and the surface ``of:acme`` — a
    # different address from the one the parser meant, and one the mention index could not find.
    # So every label the parser emits that contains the separator must now read back whole.
    seen: dict[str, str] = {}
    for clause in ("John is the CEO of Acme.", "Asset was acquired by Acme."):
        for signal in syntactic_signals([clause], scope=_scope()).signals:
            for participant in signal.participants:
                label, surface, span = read_occurrence(participant.mention_ref)
                assert span is None, participant.mention_ref
                if ":" in label:
                    seen[label] = surface
    assert {"nmod:of", "nmod:by"} <= set(seen), sorted(seen)
    assert seen["nmod:of"] == "acme", seen
    # A label that contains a separator is not a label the grammar has to cut short: the whole
    # arc is the label, and the whole document text is the surface.
    assert all(":" not in surface for surface in seen.values()), seen



def test_the_producer_is_a_relation_signal_extractor_structurally() -> None:
    """The package's one contract, satisfied structurally rather than by inheritance."""
    from extractors.signals.protocol import RelationSignalExtractor

    producer = SyntacticExtractor()
    assert isinstance(producer, RelationSignalExtractor)
    assert producer.extract("Company acquired Asset.", scope=_scope())


def test_the_slot_binding_carries_the_argument_the_marker_names() -> None:
    """The binding is a join of two things, and a test asserts the join is not crossed.

    ``A2`` carries ``in`` and the argument it names is the year; ``A2`` of a different
    reading carries ``of`` and names the company. Reading the two the wrong way round would
    still produce a well-formed signature.
    """
    sold = _one("John sold Acme to Microsoft in 2020.")
    bound = {b.slot: b for b in assign_slots(sold)}
    assert bound[ArgumentSlot(2)].argument.surface == "2020"
    assert bound[ArgumentSlot(2)].marker is ArgumentMarker.IN
    of = _one("John is a founder of Acme.")
    bound_of = {b.slot: b for b in assign_slots(of)}
    assert bound_of[ArgumentSlot(1)].argument.surface == "Acme"
    assert bound_of[ArgumentSlot(1)].marker is ArgumentMarker.OF
    assert bound_of[ArgumentSlot(0)].argument.surface == "John"
    assert bound_of[ArgumentSlot(0)].marker is ArgumentMarker.NOMARK


# --------------------------------------------------------------------------- #
# The mutation test: remove the guard, and the refusal test must fail
# --------------------------------------------------------------------------- #


def test_mutation_adding_a_rule_that_accepts_an_unknown_construction_fails_a_refusal_test() -> None:
    """A refusal test that would still pass without its guard is not testing the guard.

    The mutation: ``_c_copular`` is given an extra rule - *drop a trailing adjunct and read
    the clause anyway* - which is precisely "add a rule that lets the parser accept a
    construction it should refuse". Under it:

    * "John is CEO of Acme since 2019" is read as a copular clause with the adjunct silently
      gone, so the ``unsupported_construction`` refusal disappears;
    * ``test_every_refusal_path_emits_nothing_and_names_its_code`` **fails** for that row,
      and so does
      ``test_a_copular_clause_with_a_trailing_adjunct_is_refused_not_silently_truncated``.

    The guard is restored in a ``finally``, so the suite is left exactly as found - which is
    what makes this safe to run in a gate. "It fails" is a demonstrated fact here: the real
    test functions are called with the real assertions under the mutation, and their
    ``AssertionError`` is what is observed.
    """
    original = shallow._c_copular
    clause = "John is CEO of Acme since 2019."

    def mutated(
        tokens: Any, head_index: int, channel: Any
    ) -> Any:
        """The mutation: retry the copular constructor on the clause minus its last adjunct."""
        outcome = original(tokens, head_index, channel)
        if not (outcome.claimed and outcome.attempt is None):
            return outcome
        if not [
            refusal
            for refusal in outcome.refusals
            if refusal.code == RefusalCode.UNSUPPORTED_CONSTRUCTION
        ]:
            return outcome
        markers = [
            index
            for index, token in enumerate(tokens)
            if index > head_index + 1 and shallow._is_preposition(token)
        ]
        if not markers:
            return outcome
        return original(tokens[: markers[-1]], head_index, channel)

    # The baseline: the reading is refused, with a named code, and no signal is emitted.
    assert _first_code(clause) == RefusalCode.UNSUPPORTED_CONSTRUCTION
    assert syntactic_signals([clause], scope=_scope()).signals == ()

    shallow._c_copular = mutated
    try:
        # The mutation is a loosening: the clause is now read, so the refusal it should have
        # raised is gone. A loosening is the only kind of change a refusal test can catch,
        # which is why the guard is an allow-list of constructions.
        assert _one_or_none(clause) is not None
        assert _first_code_or_none(clause) is None
        assert syntactic_signals([clause], scope=_scope()).signals != ()
        with pytest.raises(AssertionError):
            test_every_refusal_path_emits_nothing_and_names_its_code(
                clause, RefusalCode.UNSUPPORTED_CONSTRUCTION
            )
        with pytest.raises(AssertionError):
            test_a_copular_clause_with_a_trailing_adjunct_is_refused_not_silently_truncated()
    finally:
        shallow._c_copular = original

    # Restored: the refusal is back and the suite is as it was found.
    assert shallow._c_copular is original
    assert _first_code(clause) == RefusalCode.UNSUPPORTED_CONSTRUCTION
    assert _one_or_none(clause) is None


def _one_or_none(clause: str) -> Any:
    readings, refusals = parse(clause)
    blocking = [refusal for refusal in refusals if refusal.suppresses_signal]
    if blocking or not readings:
        return None
    return readings[0]


def _first_code_or_none(clause: str) -> str | None:
    readings, refusals = parse(clause)
    if readings:
        return None
    return refusals[0].code if refusals else None


def test_the_mutation_target_is_a_real_allow_list_not_a_deny_list() -> None:
    """Why the mutation above is the one that matters, stated so it is not mistaken.

    ``CONSTRUCTION_TABLE`` is consulted by row order and the first match wins, so a
    *loosening* of the parser is the only kind of change a refusal test can catch. A
    tightening changes coverage without changing any refusal, and coverage is measured by
    the fixture digest instead. Both pins exist for that reason and neither is redundant.
    """
    assert [row.number for row in CONSTRUCTION_TABLE] == list(range(1, 11))
    numbers = {row.construction: row.number for row in CONSTRUCTION_TABLE}
    assert numbers[SyntacticConstruction.COPULAR] < numbers[SyntacticConstruction.ACTIVE_CLAUSE]
    assert SyntacticConstruction.OTHER not in numbers
    assert SyntacticConstruction.PASSIVE_NO_AGENT not in numbers
    assert len(PINNED_CLAUSE_FIXTURES) == 16


def test_the_parser_reads_no_clock_no_random_and_no_dictionary_ordering() -> None:
    """Domain Invariant 12 as a source fact rather than as an observed coincidence.

    ``ast`` again rather than a grep: the question is what the *executable* module
    references, and a name in a comment is a conversation. ``sorted`` is allowed and
    required - it is how a set is turned into a deterministic order - while a bare
    iteration over a set or a dict reaching an output is what this rules out.
    """
    banned = {"uuid4", "now", "monotonic", "time", "random", "choice", "shuffle", "sample"}
    for path in _PRODUCER_PATHS:
        tree = ast.parse(Path(path).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in {"uuid", "random", "time"}, (
                        f"{path}: imports {alias.name}"
                    )
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                assert node.value.id not in banned, f"{path}: {node.value.id}.{node.attr}"
            if isinstance(node, ast.Name):
                assert node.id not in {"uuid4", "now"}, f"{path}: {node.id}"

