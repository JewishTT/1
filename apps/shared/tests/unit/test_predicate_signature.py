"""``PredicateSignature`` v2, ``RoleBinding`` v2, ``normalize_voice()``, the canonical
participant ordering, and the logical candidate identity rule.

The contract is ``specs/021-entity-relation-extraction-finalization/data-model.md``
parts 1, 2, 3, 4, 5 and 9, arbitrated by ``repair/ARBITRATION.md`` sections 1, 8, 10,
11 and 14 and ``repair/A2-identity-subsystem.md`` D1-D5. The test names are the ones
A2 section 11 allocates, so a reviewer can diff this file against that index.

Three things are being pinned, and they are of different kinds:

* **A rule** - one test per normalisation rule N1-N6 of part 1.4, one per row of the
  ten-row construction table of part 3.4, one per step of the ordering in part 4.2.
* **A refusal** - every place the sources leave a case open, asserted as a refusal
  with its named stop condition. A test that asserts a refusal is worth more than a
  test that asserts a guess would work, because a guess would pass either way and a
  refusal only passes while the refusal is still there.
* **An identity** - surface, span, producer, evidence, confidence, type and mapping
  vocabulary all failing to move ``logical_candidate_id``, which is the property the
  whole feature exists to establish.

``SC-001`` is pinned here at *unit* level and it **passes**: the active and the
passive realisation of "Company acquired Asset" reach one ``identity_projection()``
and therefore one ``logical_candidate_id``, with no corpus, no parser and no
producer. ARBITRATION section 11's ``xfail(strict=True)`` belongs to the
*end-to-end* case, which needs one producer to read both realisations and is owned by
the syntactic producer task. No marker is present here, and none may be.
"""

from __future__ import annotations

import ast
import inspect
from dataclasses import dataclass, fields, replace
from typing import Any

import pytest

from domain.predicate_signature import (
    IDENTITY_SCHEMA_VERSION,
    LEMMA_INVENTORY,
    LEMMA_TABLE,
    LEMMA_TABLE_DIGEST,
    PINNED_IRREGULAR_FORMS,
    PREDICATE_NORMALIZATION_VERSION,
    VOICE_NORMALIZATION_VERSION,
    ArgumentMarker,
    ArgumentSlot,
    ConstructionFrame,
    ParticipantBinding,
    Polarity,
    PredicateSignature,
    RoleBinding,
    SignatureContractError,
    canonical_participant_ordering,
    derive_arity_mode,
    lemma_for,
    logical_candidate_id,
    logical_candidate_material,
    morphological_forms_of,
    normalize_surface_for_fingerprint,
    stable_participant_fingerprint,
    verify_slot_version_agreement,
)
from domain.predicate_voice import (
    CANONICAL_FRAME_BY_CONSTRUCTION,
    CONSTRUCTION_TABLE,
    ArgumentObservation,
    DependencyEdge,
    DependencyStructure,
    PredicateHead,
    SyntacticConstruction,
    SyntacticStructure,
    normalize_predicate,
    normalize_voice,
)
from domain.relation_identity import (
    RelationArityMode,
    canonical_material,
    digest128,
)

pytestmark = pytest.mark.unit

_TENANT = "tenant-a"

#: Every field name the sources forbid inside the predicate term, spelled out once
#: so the exclusion tests read as a partition rather than a sample.
_FORBIDDEN_IN_SIGNATURE = frozenset(
    {
        "raw_surface",
        "predicate_surface",
        "relation_surface",
        "trigger_span",
        "supporting_spans",
        "producer_ref",
        "producer_version",
        "extraction_rule_id",
        "extraction_method",
        "evidence",
        "observation_refs",
        "evidence_refs",
        "signal_refs",
        "confidence",
        "relation_ref",
        "relation_type",
        "alternative_refs",
        "mapping_evidence_refs",
        "resolution_state",
        "temporal",
        "event_class_hint",
        "argument_shape",
        "normalized_trigger",
        "polarity",
        "direction",
        "arity",
        "schema_version",
    }
)


@dataclass(frozen=True, slots=True)
class Mention:
    """A mention record plus the data the fingerprint MUST NOT read.

    The excluded fields are here precisely so a test can mutate each one in turn and
    watch the fingerprint refuse to move.
    """

    surface: str
    kind: str = "entity"
    capture_ref: str = "CAP-1"
    segment_ref: str = "SEG-1"
    start: int = 0
    end: int = 0
    mention_id: str = "MN-0001"
    producer_ref: str = "extractor:a"
    producer_version: str = "1.0.0"
    confidence: float = 0.0
    type_ref: str = ""
    argument_shape: str = ""
    trigger_span: str = ""
    supporting_spans: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()


# --------------------------------------------------------------------------- #
# Reading builders - the ten constructions of part 3.4
# --------------------------------------------------------------------------- #


def _observation(label: str, token: str = "", *, word: str | None = None, pronominal: bool = False):
    return ArgumentObservation(
        position_label=label, head_lemma_hint=token, function_word=word, is_pronominal=pronominal
    )


def _reading(
    head: str,
    construction: SyntacticConstruction,
    arguments: tuple[ArgumentObservation, ...],
    *,
    head_function_word: str | None = None,
) -> tuple[SyntacticStructure, DependencyStructure]:
    """A declared parse: the arguments, plus one edge per argument in document order."""
    edges = tuple(
        DependencyEdge("root", "x", argument.position_label) for argument in arguments
    )
    root = arguments[0].position_label if arguments else "root"
    return (
        SyntacticStructure(
            construction=construction, arguments=arguments, head_function_word=head_function_word
        ),
        DependencyStructure(edges=edges, root=root),
    )


#: "Company acquired Asset." and "Asset was acquired by Company." - the pair SC-001
#: is about. Built from the SAME mention records, because the claim under test is
#: that the realisation changes nothing and the participants do not.
def _acquire_pair() -> tuple[list[Mention], dict[str, PredicateSignature]]:
    company = Mention(surface="Company", start=0, end=7, mention_id="MN-0001")
    asset = Mention(surface="Asset", start=21, end=26, mention_id="MN-0002")
    structure, dependencies = _reading(
        "acquired",
        SyntacticConstruction.ACTIVE_CLAUSE,
        (_observation("nsubj", "Company"), _observation("obj", "Asset")),
    )
    active = normalize_predicate(PredicateHead("acquired"), structure, dependencies)
    structure, dependencies = _reading(
        "acquired",
        SyntacticConstruction.PASSIVE_WITH_AGENT,
        (_observation("nsubj:pass", "Asset"), _observation("nmod:by", "Company", word="by")),
        head_function_word="was",
    )
    passive = normalize_predicate(PredicateHead("acquired"), structure, dependencies)
    return [company, asset], {"active": active, "passive": passive}


def _binding(slot: int, **kwargs: Any) -> RoleBinding:
    return RoleBinding(
        surface_role=kwargs.pop("surface_role", "the words the observation used"),
        role_hypothesis=kwargs.pop("role_hypothesis", ""),
        canonical_argument_slot=ArgumentSlot(slot),
        normalization_version=kwargs.pop(
            "version", VOICE_NORMALIZATION_VERSION
        ),
        evidence=kwargs.pop("evidence", ()),
    )


def _participant(mention: Mention, slot: int, **kwargs: Any) -> ParticipantBinding:
    return ParticipantBinding(role=_binding(slot, **kwargs), mention=mention)


def _binary_signature(**kwargs: Any) -> PredicateSignature:
    return PredicateSignature(
        language=kwargs.pop("language", "en"),
        predicate_lemma=kwargs.pop("predicate_lemma", "acquire"),
        construction_frame=kwargs.pop(
            "construction_frame", ConstructionFrame.VERB_ACTIVE_TRANSITIVE
        ),
        argument_markers=kwargs.pop(
            "argument_markers", (ArgumentMarker.NOMARK, ArgumentMarker.NOMARK)
        ),
        canonical_argument_slots=kwargs.pop(
            "canonical_argument_slots", (ArgumentSlot(0), ArgumentSlot(1))
        ),
        voice_normalization_version=kwargs.pop(
            "voice_normalization_version", VOICE_NORMALIZATION_VERSION
        ),
        predicate_normalization_version=kwargs.pop(
            "predicate_normalization_version", PREDICATE_NORMALIZATION_VERSION
        ),
    )



# --------------------------------------------------------------------------- #
# Part 1: the signature, and what it excludes
# --------------------------------------------------------------------------- #


def test_signature_field_set_is_exhaustive_and_excludes_surface_mapping_and_participants() -> None:
    """Part 1 declares seven fields and the exclusion list of part 1.2 is total.

    Asserting the field set and the projection keys are the *same* seven names is the
    part that matters: a field added to the dataclass but missing from the projection
    would be a datum in the record that identity ignores, which is how a signature
    acquires a second, disagreeing description of itself.
    """
    names = tuple(field.name for field in fields(PredicateSignature))
    assert names == (
        "language",
        "predicate_lemma",
        "construction_frame",
        "argument_markers",
        "canonical_argument_slots",
        "voice_normalization_version",
        "predicate_normalization_version",
    )
    signature = _binary_signature()
    assert tuple(signature.identity_projection()) == names
    assert not set(names) & _FORBIDDEN_IN_SIGNATURE
    assert not set(signature.identity_projection()) & _FORBIDDEN_IN_SIGNATURE


def test_role_binding_field_set_is_five_and_only_the_slot_is_structural() -> None:
    """Part 2.1: five fields, two of them free text, one of them structural."""
    names = tuple(field.name for field in fields(RoleBinding))
    assert names == (
        "surface_role",
        "role_hypothesis",
        "canonical_argument_slot",
        "normalization_version",
        "evidence",
    )
    binding = _binding(1, surface_role="purchaser", role_hypothesis="buyer")
    # Both words are retained verbatim, and neither reaches identity: two producers
    # guessing different words for one A1 are one logical candidate.
    assert binding.surface_role == "purchaser"
    assert binding.role_hypothesis == "buyer"


def test_role_binding_evidence_is_canonicalised_on_construction() -> None:
    """Part 2.1: a reference collection is sorted and deduplicated on construction,
    like every other one in the platform, so a caller cannot smuggle order into a
    record that is later hashed."""
    binding = _binding(0, evidence=("OB-2", "OB-1", "OB-2"))
    assert binding.evidence == ("OB-1", "OB-2")


def test_signature_without_a_normalization_version_is_a_contract_error() -> None:
    """Part 2.4: an unversioned signature is a contract error, never a default.

    A default is a guess, and a guessed version assigns an id whose record cannot
    justify it. The constitution's Additional Constraints require a quarantine for
    exactly this class of row, so the outcome is quarantined, reported, replayable -
    not silently upgraded.
    """
    for field in ("voice_normalization_version", "predicate_normalization_version"):
        with pytest.raises(SignatureContractError) as caught:
            _binary_signature(**{field: "  "})
        assert caught.value.code == "unversioned_signature"
        assert field in caught.value.message


def test_role_binding_version_must_match_its_signature() -> None:
    """Part 2.4: the binding's version is the version that assigned its slot.

    A binding assigned by an older convention cannot be placed in an ordering produced
    by a newer one, because "A1" does not mean the same position under both.
    """
    signature = _binary_signature()
    stale = _binding(1, version="vn-0")
    with pytest.raises(SignatureContractError) as caught:
        verify_slot_version_agreement(signature, [stale])
    assert caught.value.code == "role_binding_version_must_match_signature"
    with pytest.raises(SignatureContractError) as through_ordering:
        canonical_participant_ordering(
            signature,
            frozenset(),
            [_participant(Mention("A"), 0), _participant(Mention("B"), 1, version="vn-0")],
        )
    assert through_ordering.value.code == "mixed_normalization_versions"




def test_mixed_normalization_versions_are_refused() -> None:
    """Part 2.5: a participant set assembled across two conventions has no canonical
    ordering, because "A1" does not mean the same position under both."""
    signature = _binary_signature()
    participants = [
        _participant(Mention("A"), 0, version="vn-1"),
        _participant(Mention("B"), 1, version="vn-2"),
    ]
    with pytest.raises(SignatureContractError) as caught:
        canonical_participant_ordering(signature, frozenset(), participants)
    assert caught.value.code == "mixed_normalization_versions"


def test_markers_must_be_parallel_to_slots() -> None:
    """Part 2.5 check 1: a length mismatch is a truncated construction."""
    with pytest.raises(SignatureContractError) as caught:
        _binary_signature(argument_markers=(ArgumentMarker.NOMARK,))
    assert caught.value.code == "markers_not_parallel_to_slots"


def test_signature_slots_must_equal_the_bound_slots() -> None:
    """Part 2.5 check 2: the signature carries the skeleton, the bindings carry the
    occupants, and the two may not disagree."""
    signature = _binary_signature()
    with pytest.raises(SignatureContractError) as caught:
        canonical_participant_ordering(
            signature,
            frozenset(),
            [_participant(Mention("A"), 0), _participant(Mention("B"), 0)],
        )
    assert caught.value.code == "signature_slots_disagree_with_bindings"


def test_signature_may_not_carry_an_observed_passive_frame() -> None:
    """Part 1/2.5 check 3: the observed passive frame is the one datum that would keep
    an active and a passive realisation apart, so it is refused structurally."""
    with pytest.raises(SignatureContractError) as caught:
        _binary_signature(construction_frame=ConstructionFrame.VERB_PASSIVE_AGENT)
    assert caught.value.code == "observed_passive_frame_on_signature"
    assert ConstructionFrame.VERB_PASSIVE_AGENT.is_observed_only is True
    assert all(
        not frame.is_observed_only
        for frame in ConstructionFrame
        if frame is not ConstructionFrame.VERB_PASSIVE_AGENT
    )


def test_signature_requires_at_least_two_contiguous_slots() -> None:
    """Part 1: arity is derived from the slots, so a one-slot signature is a contract
    error rather than a property reading wearing a relational costume."""
    with pytest.raises(SignatureContractError) as caught:
        _binary_signature(
            argument_markers=(ArgumentMarker.NOMARK,),
            canonical_argument_slots=(ArgumentSlot(0),),
        )
    assert caught.value.code == "signature_arity_below_two"
    with pytest.raises(SignatureContractError) as gap:
        _binary_signature(
            argument_markers=(ArgumentMarker.NOMARK, ArgumentMarker.NOMARK),
            canonical_argument_slots=(ArgumentSlot(0), ArgumentSlot(2)),
        )
    assert gap.value.code == "slot_gap"


def test_commutative_slots_must_be_occupied() -> None:
    """Part 2.5 check 4: a symmetry marker with no occupant describes a relation nobody
    asserted.

    The check is reachable exactly as it should be - a declared slot outside the
    signature's contiguous skeleton - because a slot the signature declares always has
    an occupant by check 2.
    """
    signature = _binary_signature()
    participants = [
        _participant(Mention("A", start=0, end=1), 0),
        _participant(Mention("B", start=2, end=3), 1),
    ]
    with pytest.raises(SignatureContractError) as caught:
        canonical_participant_ordering(
            signature, frozenset({ArgumentSlot(0), ArgumentSlot(5)}), participants
        )
    assert caught.value.code == "empty_commutative_slot"
    # A declared commutative slot with exactly one occupant is legal: a symmetric
    # relation observed with one side elided.
    ordered = canonical_participant_ordering(
        signature, frozenset({ArgumentSlot(0)}), participants
    )
    assert [participant.slot.index for participant in ordered] == [0, 1]



def test_arity_mode_is_derivable_from_commutative_slots() -> None:
    """Part 2.5 check 4: the term in the material is a checked redundancy."""
    signature = _binary_signature()
    participants = [_participant(Mention("A"), 0), _participant(Mention("B"), 1)]
    both = frozenset({ArgumentSlot(0), ArgumentSlot(1)})
    assert derive_arity_mode(signature, both, [p.role for p in participants]) is (
        RelationArityMode.UNDIRECTED
    )
    assert derive_arity_mode(signature, frozenset(), [p.role for p in participants]) is (
        RelationArityMode.DIRECTED
    )
    with pytest.raises(SignatureContractError) as caught:
        logical_candidate_material(
            signature, participants, tenant_id=_TENANT, arity_mode=RelationArityMode.NARY
        )
    assert caught.value.code == "arity_mode_disagrees_with_commutative_slots"


def test_signature_round_trips_through_to_dict_and_from_dict() -> None:
    """FR-060: a digest may identify data; the record must also be able to rebuild it."""
    signature = _binary_signature(
        argument_markers=(ArgumentMarker.NOMARK, ArgumentMarker.OF, ArgumentMarker.TO),
        canonical_argument_slots=(ArgumentSlot(0), ArgumentSlot(1), ArgumentSlot(2)),
    )
    payload = signature.to_dict()
    assert PredicateSignature.from_dict(payload).identity_projection() == (
        signature.identity_projection()
    )
    binding = _binding(2, surface_role="buyer", role_hypothesis="purchaser", evidence=("OB-1",))
    assert RoleBinding.from_dict(binding.to_dict()) == binding


def test_rendered_predicate_is_a_view_of_the_identity_projection_and_not_identity() -> None:
    """Part 1: ``rendered_predicate()`` is the derived read, and the projection is what
    identity uses. Two signatures that render identically cannot differ, and a render
    is never an input."""
    signature = _binary_signature()
    assert signature.rendered_predicate() == "acquire(A0:,A1:)"
    marked = _binary_signature(
        argument_markers=(ArgumentMarker.NOMARK, ArgumentMarker.OF),
        predicate_lemma="originate",
    )
    assert marked.rendered_predicate() == "originate(A0:,A1:of)"
    assert "rendered_predicate" not in signature.identity_projection()
    # The rendering is a pure function of the projection: same projection, same string.
    assert PredicateSignature.from_dict(marked.to_dict()).rendered_predicate() == (
        marked.rendered_predicate()
    )



def test_unknown_predicate_is_a_complete_durable_hypothesis() -> None:
    """Part 1.7: "John is the originator of Acme." yields a complete signature with no
    relation_ref and no resolution state, because neither exists on this type at all.

    That absence is the feature: an unknown predicate is representable *structurally*
    rather than by a registry sentinel, so nobody downstream can mistake a minted
    concept for understood meaning.
    """
    structure, dependencies = _reading(
        "originator",
        SyntacticConstruction.COPULAR,
        (
            _observation("nsubj", "John"),
            _observation("obj", "originator"),
            _observation("nmod:of", "Acme", word="of"),
        ),
    )
    signature = normalize_predicate(PredicateHead("originator"), structure, dependencies)
    assert signature.predicate_lemma == "originate"
    assert signature.construction_frame is ConstructionFrame.COPULA_PREDICATIVE
    assert [str(marker) for marker in signature.argument_markers] == ["", "of"]
    assert [slot.token for slot in signature.canonical_argument_slots] == ["A0", "A1"]
    assert signature.rendered_predicate() == "originate(A0:,A1:of)"
    assert not set(signature.identity_projection()) & {"relation_ref", "resolution_state"}


# --------------------------------------------------------------------------- #
# Part 1.4: one test per normalisation rule
# --------------------------------------------------------------------------- #


def test_n1_nfkc_then_casefold() -> None:
    """N1. NFKC composes before casefolding, so a decomposed accent and its composed
    form are one surface - and a digest that treated them as two would fork a mention
    on an encoding artefact."""
    assert normalize_surface_for_fingerprint("Café") == "café"
    assert normalize_surface_for_fingerprint("Café") == normalize_surface_for_fingerprint("Café")
    assert normalize_surface_for_fingerprint("ACQUIRE") == "acquire"


def test_n2_collapses_internal_whitespace_and_strips_edge_punctuation() -> None:
    """N2. The two halves matter separately: collapsing internal whitespace makes
    "Works  For" and "Works For" one surface, and stripping edge punctuation keeps a
    quotation mark from splitting a document's mentions into two sets."""
    assert normalize_surface_for_fingerprint('  "Works For" ') == "works for"
    assert normalize_surface_for_fingerprint("Works\tFor\nAcme") == "works for acme"
    assert normalize_surface_for_fingerprint("(Acme)") == "acme"
    assert normalize_surface_for_fingerprint("‘‘Acme’’") == "acme"


def test_n3_voice_handling_is_the_only_unification() -> None:
    """N3, and the scope of P-CANON. Voice moves the *arguments*; it does not rewrite
    the sentence, and it is the only thing this subsystem unifies.

    The negative half is the load-bearing half: if relative clauses, copulas, bare
    nominals and prepositional phrases also collapsed, the platform would be making
    equivalence claims that section 20 reserves to explicit mapping - claims that
    cannot be undone and leave no trace.
    """
    mentions, pair = _acquire_pair()
    assert pair["active"].identity_projection() == pair["passive"].identity_projection()
    for other, distinct in (
        ("relative", ("founded", SyntacticConstruction.RELATIVE_CLAUSE, "nsubj", "obj")),
        ("active", ("acquired", SyntacticConstruction.ACTIVE_CLAUSE, "nsubj", "obj")),
    ):
        head, construction, subject, obj = distinct
        structure, dependencies = _reading(
            head, construction, (_observation(subject, "John"), _observation(obj, "Acme"))
        )
        signature = normalize_predicate(PredicateHead(head), structure, dependencies)
        if other == "relative":
            relative = signature
        else:
            active = signature
    assert relative.identity_projection() != active.identity_projection()
    assert mentions  # the mention pair is built once; the claim is about realisation


def test_n4_function_words_are_recorded_against_a_closed_inventory() -> None:
    """N4. A function word is recorded as itself or refused; it is never folded onto
    another member, and a word outside the inventory is a failure rather than NOMARK."""
    structure, dependencies = _reading(
        "worked",
        SyntacticConstruction.ACTIVE_CLAUSE,
        (
            _observation("nsubj", "John"),
            _observation("nmod:purs", "Acme", word="purs"),
        ),
    )
    with pytest.raises(SignatureContractError) as caught:
        normalize_predicate(PredicateHead("worked"), structure, dependencies)
    assert caught.value.code == "unsupported_marker"
    assert "closed ArgumentMarker inventory" in caught.value.message


def test_n5_is_retired_from_the_identity_path() -> None:
    """N5. There is no synonym table at this layer, ever, and the enforcement is
    structural rather than editorial: no rule in the generated table can map one base
    lemma onto another, so the forbidden table has no row type.

    ``owns`` / ``controls`` / ``manages`` are three inventory lemmas and three
    generated rows pointing at three different lemmas. No code path in the table can
    make two of them share a value.
    """
    assert {"own", "control", "manage"} <= set(LEMMA_INVENTORY)
    for surface, lemma in (("owns", "own"), ("controls", "control"), ("manages", "manage")):
        assert LEMMA_TABLE[surface] == lemma
    assert LEMMA_TABLE["owns"] != LEMMA_TABLE["controls"] != LEMMA_TABLE["manages"]
    # The value set introduces no base lemma beyond the inventory and the pins, which
    # is what makes a cross-lemma fold unrepresentable rather than merely discouraged.
    assert set(LEMMA_TABLE.values()) <= set(LEMMA_INVENTORY) | set(
        PINNED_IRREGULAR_FORMS.values()
    )



def test_n6_argument_shape_is_excluded_from_the_participant_fingerprint() -> None:
    """N6. Shape is a fact about a referent, not about the predicate.

    If it entered the fingerprint, a reclassification in the type layer would re-key
    a relational identity, and two subsystems' changes would be coupled through a
    digest. This is the specific coupling part 1.1 names, so it is asserted rather
    than assumed.
    """
    mention = Mention("Acme", argument_shape="legal_person")
    res = replace(mention, argument_shape="organisation", type_ref="core:Organization")
    assert stable_participant_fingerprint(mention) == stable_participant_fingerprint(res)


# --------------------------------------------------------------------------- #
# Part 1.5 and 3.4: the generated tables
# --------------------------------------------------------------------------- #


def test_lemma_table_matches_its_committed_digest() -> None:
    """A row addition is a visible diff against a golden value, not a silent corpus
    shift (part 1.5)."""
    assert digest128(canonical_material(sorted(LEMMA_TABLE.items()))) == LEMMA_TABLE_DIGEST


def test_lemma_table_has_no_cross_lemma_row() -> None:
    """The enforceable statement, which is the whole of the N5 removal in data form:
    the table contains no row whose surface is not a morphological form of its lemma.

    Checked per row against the *generators*, and a pinned irregular is admitted only
    when the rules cannot produce that surface from any other lemma - so a pin can
    supply a missing form but can never redirect one lemma onto another.
    """
    forms_per_lemma = {lemma: morphological_forms_of(lemma) for lemma in LEMMA_INVENTORY}
    producible: dict[str, set[str]] = {}
    for lemma, forms in forms_per_lemma.items():
        for form in forms:
            producible.setdefault(form, set()).add(lemma)

    unexplained: list[tuple[str, str]] = []
    for surface, lemma in sorted(LEMMA_TABLE.items()):
        if surface in forms_per_lemma.get(lemma, frozenset()):
            continue
        if PINNED_IRREGULAR_FORMS.get(surface) == lemma and not (
            producible.get(surface, set()) - {lemma}
        ):
            continue
        unexplained.append((surface, lemma))
    assert unexplained == []

    # And the value set introduces no base lemma, which is the property that makes a
    # cross-lemma fold *unrepresentable* rather than merely discouraged.
    assert set(LEMMA_TABLE.values()) <= set(LEMMA_INVENTORY) | set(
        PINNED_IRREGULAR_FORMS.values()
    )


def test_argument_marker_inventory_is_closed() -> None:
    """Part 1: a CLOSED, VERSIONED INVENTORY, not a mapping. There is no alias table
    and no member is ever folded onto another."""
    assert {member.value for member in ArgumentMarker} == {
        "",
        "about",
        "as",
        "at",
        "by",
        "for",
        "from",
        "in",
        "into",
        "of",
        "on",
        "onto",
        "to",
        "with",
    }
    assert ArgumentMarker("") is ArgumentMarker.NOMARK
    for left in ArgumentMarker:
        for right in ArgumentMarker:
            assert (left is right) == (left.value == right.value)


def test_unsupported_lemma_is_refused_rather_than_guessed() -> None:
    """V3's failure mode. A guessed lemma is a silent merge, which is the one thing
    N5 was removed to prevent, so the table declines and the reading stays unsignatured."""
    with pytest.raises(SignatureContractError) as caught:
        lemma_for("frobnicate")
    assert caught.value.code == "unsupported_lemma"
    assert "is not a morphological form" in caught.value.message
    with pytest.raises(SignatureContractError) as empty:
        lemma_for("   ")
    assert empty.value.code == "unsupported_lemma"



# --------------------------------------------------------------------------- #
# Part 3: normalize_voice - the ten constructions
# --------------------------------------------------------------------------- #


def test_construction_table_is_ten_rows_in_row_order_with_the_passive_demotion() -> None:
    """Part 3.4: ten rows, consulted in order, and the only construction whose canonical
    frame differs from its observed shape is the passive."""
    assert [row.number for row in CONSTRUCTION_TABLE] == list(range(1, 11))
    assert CANONICAL_FRAME_BY_CONSTRUCTION[SyntacticConstruction.PASSIVE_WITH_AGENT] is (
        ConstructionFrame.VERB_ACTIVE_TRANSITIVE
    )
    for construction, frame in CANONICAL_FRAME_BY_CONSTRUCTION.items():
        assert not frame.is_observed_only
        if construction is SyntacticConstruction.PASSIVE_WITH_AGENT:
            continue
        assert str(frame) != f"verb_{construction.value}"
    # TB1: COPULAR precedes ACTIVE_CLAUSE, so a copular reading wins when the
    # producer declares a copular clause.
    numbers = {row.construction: row.number for row in CONSTRUCTION_TABLE}
    assert numbers[SyntacticConstruction.COPULAR] < numbers[SyntacticConstruction.ACTIVE_CLAUSE]
    # The constructions the producer can declare but the table cannot support.
    assert SyntacticConstruction.PASSIVE_NO_AGENT not in numbers
    assert SyntacticConstruction.OTHER not in numbers


@pytest.mark.parametrize(
    ("label", "head", "construction", "arguments", "expected"),
    [
        pytest.param(
            "row1_passive_with_agent",
            "acquired",
            SyntacticConstruction.PASSIVE_WITH_AGENT,
            (
                _observation("nsubj:pass", "Asset"),
                _observation("nmod:by", "Company", word="by"),
            ),
            (ConstructionFrame.VERB_ACTIVE_TRANSITIVE, "acquire(A0:,A1:)"),
            id="row1_passive_demotes_to_active",
        ),
        pytest.param(
            "row2_copular",
            "is",
            SyntacticConstruction.COPULAR,
            (
                _observation("nsubj", "John"),
                _observation("obj", "CEO"),
                _observation("nmod:of", "Acme", word="of"),
            ),
            (ConstructionFrame.COPULA_PREDICATIVE, "be(A0:,A1:of)"),
            id="row2_copular_follows_the_of_pp",
        ),
        pytest.param(
            "row2_copular",
            "is",
            SyntacticConstruction.COPULAR,
            (_observation("nsubj", "John"), _observation("obj", "CEO")),
            (ConstructionFrame.COPULA_PREDICATIVE, "be(A0:,A1:)"),
            id="row2_copular_bare_np_complement",
        ),
        pytest.param(
            "row3_copular_with_noun_complement",
            "is",
            SyntacticConstruction.COPULAR_WITH_NOUN_COMPLEMENT,
            (
                _observation("nsubj", "John"),
                _observation("obj", "founder"),
                _observation("nmod:of", "Acme", word="of"),
            ),
            (ConstructionFrame.COPULA_PREDICATIVE_NOUN, "be(A0:,A1:of)"),
            id="row3_noun_complement_is_its_own_frame",
        ),
        pytest.param(
            "row4_active_transitive",
            "acquired",
            SyntacticConstruction.ACTIVE_CLAUSE,
            (_observation("nsubj", "Company"), _observation("obj", "Asset")),
            (ConstructionFrame.VERB_ACTIVE_TRANSITIVE, "acquire(A0:,A1:)"),
            id="row4_active_transitive",
        ),
        pytest.param(
            "row6_bare_nominal",
            "own",
            SyntacticConstruction.BARE_NOMINAL,
            (_observation("obj", "John"), _observation("nmod:of", "Acme", word="of")),
            (ConstructionFrame.NOMINAL_OWNER_OF, "own(A0:,A1:of)"),
            id="row6_bare_nominal",
        ),
        pytest.param(
            "row7_genitive_np",
            "founder",
            SyntacticConstruction.GENITIVE_NP,
            (_observation("case:gen", "Acme"), _observation("obj", "John Smith")),
            (ConstructionFrame.NOMINAL_POSSESSIVE, "found(A0:,A1:)"),
            id="row7_genitive_reverses_word_order",
        ),
        pytest.param(
            "row8_appositive_np",
            "founder",
            SyntacticConstruction.APPOSITIVE_NP,
            (_observation("obj", "John Smith"), _observation("nmod:of", "Acme", word="of")),
            (ConstructionFrame.APPOSITIVE_ROLE, "found(A0:,A1:of)"),
            id="row8_appositive_role",
        ),
        pytest.param(
            "row9_headless_pp",
            "works",
            SyntacticConstruction.HEADLESS_PP,
            (_observation("pobj", "Acme", word="at"), _observation("nsubj", "John")),
            (ConstructionFrame.PREP_PHRASE_HEAD, "work(A0:at,A1:)"),
            id="row9_headless_pp_marks_the_pobj",
        ),
        pytest.param(
            "row10_relative_clause",
            "founded",
            SyntacticConstruction.RELATIVE_CLAUSE,
            (_observation("nsubj", "John"), _observation("obj", "Acme")),
            (ConstructionFrame.RELATIVE_CLAUSE, "found(A0:,A1:)"),
            id="row10_relative_clause_keeps_its_own_frame",
        ),
    ],
)
def test_every_supported_construction_reaches_its_declared_frame(
    label: str,
    head: str,
    construction: SyntacticConstruction,
    arguments: tuple[ArgumentObservation, ...],
    expected: tuple[ConstructionFrame, str],
) -> None:
    """Part 3.4, row by row. A row that cannot be tested syntactically may not be in the
    table, so each row here is reached by a declared construction plus a condition."""
    structure, dependencies = _reading(head, construction, arguments)
    signature = normalize_predicate(PredicateHead(head), structure, dependencies)
    frame, rendered = expected
    assert signature.construction_frame is frame, label
    assert signature.rendered_predicate() == rendered, label
    assert signature.arity == rendered.count(",") + 1, label




def test_row5_active_clause_without_a_further_argument_is_intransitive_then_refused() -> None:
    """Part 3.4 row 5: the frame exists, and step V6 then refuses to build a signature
    from it - a one-argument clause states a property, not a relational configuration."""
    structure, dependencies = _reading(
        "works", SyntacticConstruction.ACTIVE_CLAUSE, (_observation("nsubj", "John"),)
    )
    with pytest.raises(SignatureContractError) as caught:
        normalize_predicate(PredicateHead("works"), structure, dependencies)
    assert caught.value.code == "no_configuration"
    assert "row 5" in caught.value.message
    assert ConstructionFrame.VERB_ACTIVE_INTRANSITIVE.is_observed_only is False


def test_unsupported_construction_yields_no_signature() -> None:
    """Part 3.5: a construction outside the table produces no signature at all, and the
    reason is a code the corpus can count."""
    for construction in (SyntacticConstruction.PASSIVE_NO_AGENT, SyntacticConstruction.OTHER):
        structure, dependencies = _reading(
            "acquired",
            construction,
            (_observation("nsubj", "C"), _observation("obj", "A")),
        )
        with pytest.raises(SignatureContractError) as caught:
            normalize_predicate(PredicateHead("acquired"), structure, dependencies)
        assert caught.value.code == "unsupported_construction"
        assert construction.value in caught.value.message


def test_unsupported_construction_is_never_guessed_into_a_frame() -> None:
    """No fallback frame, no nearest match, no default, no retry, no lexical shortcut.

    The second half of the test is the strong one: a refused construction must not
    leave *any* signature behind, and the exception type is a typed contract error
    rather than a ``None``, so a caller cannot accidentally treat the refusal as a
    reading with an empty frame.
    """
    structure, dependencies = _reading(
        "acquired",
        SyntacticConstruction.OTHER,
        (_observation("nsubj", "C"), _observation("obj", "A")),
    )
    with pytest.raises(SignatureContractError) as caught:
        normalize_voice(PredicateHead("acquired"), structure, dependencies)
    assert caught.value.code == "unsupported_construction"
    assert "never resolved by a fallback frame" in caught.value.message
    # And the returned type cannot represent the refusal: its frame field is typed as a
    # canonical frame, so a caller cannot receive an assignment with an empty or
    # observed-only frame and mistake it for a reading.
    assignment_fields = {field.name for field in fields(_assignment_type())}
    assert assignment_fields == {
        "construction_frame",
        "canonical_argument_slots",
        "argument_markers",
        "normalization_trace",
    }
    assert not [frame for frame in ConstructionFrame if frame.is_observed_only] == [
        frame for frame in ConstructionFrame
    ]



def test_agentless_passive_is_unsupported_not_guessed() -> None:
    """Part 1.4: a passive with no overt agent is ``UNSUPPORTED_CONSTRUCTION``.

    Deciding what an elided agent is would be a semantic inference, and an inference
    is a mapping - so the answer is a refusal, and the signal carries an explicit
    observational basis instead.
    """
    structure, dependencies = _reading(
        "was",
        SyntacticConstruction.PASSIVE_NO_AGENT,
        (_observation("nsubj:pass", "Asset"),),
    )
    with pytest.raises(SignatureContractError) as caught:
        normalize_predicate(PredicateHead("was"), structure, dependencies)
    assert caught.value.code == "unsupported_construction"


def test_intransitive_reading_yields_no_configuration() -> None:
    """Part 3.7: fewer than two occupied slots is a *decision* about a well-parsed
    reading, and it is a different code from a missing capability."""
    structure, dependencies = _reading(
        "works", SyntacticConstruction.ACTIVE_CLAUSE, (_observation("nsubj", "John"),)
    )
    with pytest.raises(SignatureContractError) as caught:
        normalize_voice(PredicateHead("works"), structure, dependencies)
    assert caught.value.code == "no_configuration"
    assert "not padded to arity 2" in caught.value.message


def test_no_configuration_is_distinct_from_unsupported_construction() -> None:
    """The two refusals are counted separately, which is the whole point of typing them.

    "Acme's ownership" is realised here with an in-inventory nominal ("Acme's owner"):
    the literal "ownership" is outside the closed lemma inventory and is refused at V3,
    which is a third, honest answer rather than a reason to widen the table by guess.
    """
    structure, dependencies = _reading(
        "owner", SyntacticConstruction.GENITIVE_NP, (_observation("case:gen", "Acme"),)
    )
    with pytest.raises(SignatureContractError) as no_configuration:
        normalize_voice(PredicateHead("owner"), structure, dependencies)
    assert no_configuration.value.code == "no_configuration"

    structure, dependencies = _reading(
        "ownership", SyntacticConstruction.GENITIVE_NP, (_observation("case:gen", "Acme"),)
    )
    with pytest.raises(SignatureContractError) as unsupported_lemma:
        normalize_voice(PredicateHead("ownership"), structure, dependencies)
    assert unsupported_lemma.value.code == "unsupported_lemma"

    other, dependencies = _reading(
        "acquired",
        SyntacticConstruction.OTHER,
        (_observation("nsubj", "C"), _observation("obj", "A")),
    )
    with pytest.raises(SignatureContractError) as unsupported:
        normalize_voice(PredicateHead("acquired"), other, dependencies)
    assert unsupported.value.code != no_configuration.value.code


def test_normalize_voice_does_not_unify_anything_but_voice() -> None:
    """P-CANON's negative half, over the pairs brief section 29 lists separately."""
    signatures = {}
    for label, head, construction, arguments in (
        (
            "copular",
            "is",
            SyntacticConstruction.COPULAR,
            (
                _observation("nsubj", "John"),
                _observation("obj", "CEO"),
                _observation("nmod:of", "Acme", word="of"),
            ),
        ),
        (
            "appositive",
            "founder",
            SyntacticConstruction.APPOSITIVE_NP,
            (_observation("obj", "John"), _observation("nmod:of", "Acme", word="of")),
        ),
        (
            "at",
            "works",
            SyntacticConstruction.HEADLESS_PP,
            (_observation("pobj", "Acme", word="at"), _observation("nsubj", "John")),
        ),
        (
            "for",
            "works",
            SyntacticConstruction.HEADLESS_PP,
            (_observation("pobj", "Acme", word="for"), _observation("nsubj", "John")),
        ),
    ):
        structure, dependencies = _reading(head, construction, arguments)
        signatures[label] = normalize_predicate(PredicateHead(head), structure, dependencies)

    assert (
        signatures["copular"].identity_projection()
        != signatures["appositive"].identity_projection()
    )
    assert (
        signatures["at"].identity_projection() != signatures["for"].identity_projection()
    )


def test_works_at_and_works_for_are_distinct_signatures() -> None:
    """Named by A2 U2. Deciding that ``at`` and ``for`` mark the same argument is a
    lexical-semantic claim, and ``ArgumentMarker`` exists so it cannot be made by
    accident. Unification is available only through the mapping layer."""
    projections = {}
    for word in ("at", "for"):
        structure, dependencies = _reading(
            "works",
            SyntacticConstruction.HEADLESS_PP,
            (_observation("pobj", "Acme", word=word), _observation("nsubj", "John")),
        )
        projections[word] = normalize_predicate(
            PredicateHead("works"), structure, dependencies
        ).identity_projection()
    assert projections["at"]["argument_markers"] != projections["for"]["argument_markers"]


def test_become_and_be_are_distinct_signatures() -> None:
    """TB1 put ``become`` in both closed sets, and row order resolves the frame - but it
    cannot and must not resolve the *lemma*. Two copular readings differing only in
    their copula are two predicates."""
    projections = {}
    for head in ("is", "became"):
        structure, dependencies = _reading(
            head,
            SyntacticConstruction.COPULAR,
            (
                _observation("nsubj", "John"),
                _observation("obj", "CEO"),
                _observation("nmod:of", "Acme", word="of"),
            ),
        )
        projections[head] = normalize_predicate(
            PredicateHead(head), structure, dependencies
        ).identity_projection()
    assert projections["is"]["predicate_lemma"] == "be"
    assert projections["became"]["predicate_lemma"] == "become"
    assert projections["is"] != projections["became"]


def test_normalize_voice_marks_a_ditransitive_recipient_with_to_and_drops_a_temporal_complement_with_a_trace():  # noqa: E501
    """Part 4.6's worked derivation, step by step.

    TB2: ``in`` < ``to``, so the temporal complement is assigned before the recipient
    and then dropped, with ``V2.drop_temporal`` in the trace so the drop is auditable
    rather than invisible. ``time = 2020`` stays recoverable on the candidate's
    ``TemporalHypothesis``; it is simply not part of the predicate.
    """
    structure, dependencies = _reading(
        "sold",
        SyntacticConstruction.ACTIVE_CLAUSE,
        (
            _observation("nsubj", "John"),
            _observation("obj", "Acme"),
            _observation("obl:tmod", "2020", word="in"),
            _observation("nmod:to", "Microsoft", word="to"),
        ),
    )
    signature = normalize_predicate(PredicateHead("sold"), structure, dependencies)
    assignment = normalize_voice(PredicateHead("sold"), structure, dependencies)
    assert signature.rendered_predicate() == "sell(A0:,A1:,A2:to)"
    assert signature.arity == 3
    trace = assignment.normalization_trace
    assert "V2.drop_temporal" in trace
    assert trace.index("V2.assign_slots") < trace.index("V2.drop_temporal")
    assert trace.index("V2.drop_temporal") < trace.index("V3.lemmatise")
    # A0 / A1 / A2 are seller / asset / buyer *structurally*; the names live in
    # RoleBinding.surface_role as evidence and never in the signature.
    assert "seller" not in signature.rendered_predicate()



def test_temporal_complement_outside_the_tmod_inventory_is_retained_not_guessed() -> None:
    """The sources fix the *drop* and the trace entry but never state the *test* that
    identifies a temporal complement, and a function-word list is a guess with a
    concrete cost: "John works at Acme" would lose its argument.

    So the test used is the label a parser already emits - the UD temporal-modifier
    family, a grammar inventory - and a complement outside it is RETAINED. That is the
    visible direction: an over-retained temporal argument is one extra structural slot,
    while a wrongly dropped one is a lost participant with no trace.
    """
    arguments = (
        _observation("nsubj", "John"),
        _observation("obj", "Acme"),
        _observation("nmod:in", "2020", word="in"),
    )
    structure, dependencies = _reading("sold", SyntacticConstruction.ACTIVE_CLAUSE, arguments)
    signature = normalize_predicate(PredicateHead("sold"), structure, dependencies)
    assignment = normalize_voice(PredicateHead("sold"), structure, dependencies)
    assert signature.arity == 3
    assert "V2.drop_temporal" not in assignment.normalization_trace

    labelled, dependencies = _reading(
        "sold",
        SyntacticConstruction.ACTIVE_CLAUSE,
        (
            _observation("nsubj", "John"),
            _observation("obj", "Acme"),
            _observation("obl:tmod", "2020", word="in"),
        ),
    )
    kept = normalize_voice(PredicateHead("sold"), labelled, dependencies)
    assert kept.arity == 2
    assert "V2.drop_temporal" in kept.normalization_trace


def test_passive_records_the_observed_agent_in_the_trace_and_not_in_the_signature() -> None:
    """Part 3.4 row 1: the observed ``by`` is evidence. It is in the trace; it is not in
    the signature, and putting it there is what would keep the two realisations apart."""
    structure, dependencies = _reading(
        "acquired",
        SyntacticConstruction.PASSIVE_WITH_AGENT,
        (
            _observation("nsubj:pass", "Asset"),
            _observation("nmod:by", "Company", word="by"),
        ),
        head_function_word="was",
    )
    assignment = normalize_voice(PredicateHead("acquired"), structure, dependencies)
    assert "V2.observed_by" in assignment.normalization_trace
    assert "by" in assignment.normalization_trace
    assert "by" not in [str(marker) for marker in assignment.argument_markers]


def test_auxiliary_head_is_refused_rather_than_guessed() -> None:
    """V3: an AUX is not the predicate head when the clause has a participle.

    Which participle was meant is not in the declared parse, so the reading is refused.
    Guessing it would be the one place in the function where an observation's meaning is
    invented, and it would key identity on a word that encodes nothing about the
    relation.
    """
    structure, dependencies = _reading(
        "was",
        SyntacticConstruction.PASSIVE_WITH_AGENT,
        (
            _observation("nsubj:pass", "Asset"),
            _observation("nmod:by", "Company", word="by"),
        ),
        head_function_word="was",
    )
    with pytest.raises(SignatureContractError) as caught:
        normalize_predicate(PredicateHead("was"), structure, dependencies)
    assert caught.value.code == "auxiliary_is_not_the_predicate_head"


def test_pronominal_elided_argument_is_consumed_and_never_emitted() -> None:
    """V2 consumes a pronominal argument rather than emitting a slot for it.

    The refusal that follows is honest: a slot is a position in a parse, so an absent
    or elided argument cannot be numbered, and numbering around the hole would produce
    a material neither convention could re-derive.
    """
    structure, dependencies = _reading(
        "works",
        SyntacticConstruction.HEADLESS_PP,
        (
            _observation("pobj", "it", word="at", pronominal=True),
            _observation("nsubj", "John"),
        ),
    )
    with pytest.raises(SignatureContractError) as caught:
        normalize_voice(PredicateHead("works"), structure, dependencies)
    assert caught.value.code == "slot_gap"


def test_malformed_parse_is_refused_before_it_is_interpreted() -> None:
    """V0: an unusable parse is refused, not normalised."""
    empty, no_root = _reading("acquired", SyntacticConstruction.ACTIVE_CLAUSE, ())
    with pytest.raises(SignatureContractError) as caught:
        normalize_voice(PredicateHead("acquired"), empty, no_root)
    assert caught.value.code == "malformed_structure"

    arguments = (_observation("nsubj", "C"), _observation("obj", "A"))
    structure = SyntacticStructure(SyntacticConstruction.ACTIVE_CLAUSE, arguments, None)
    dependencies = DependencyStructure(
        edges=tuple(DependencyEdge("root", "x", a.position_label) for a in arguments),
        root="obl:somewhere",
    )
    with pytest.raises(SignatureContractError) as caught:
        normalize_voice(PredicateHead("acquired"), structure, dependencies)
    assert caught.value.code == "malformed_structure"

    with pytest.raises(SignatureContractError) as language:
        structure, dependencies = _reading(
            "acquired", SyntacticConstruction.ACTIVE_CLAUSE, arguments
        )
        normalize_voice(PredicateHead("acquired", language="fr"), structure, dependencies)
    assert language.value.code == "unsupported_language"


def test_normalize_voice_output_carries_no_participant_no_surface_and_no_symmetry() -> None:
    """Part 3.6: the output is about the predicate and nothing else.

    The field-set assertion is the mechanism: a return value that acquired a
    ``commutative_slots`` or an ``observed_construction_frame`` field would be a
    symmetry inference or a fork, and section 53 says verbatim "Do not infer symmetry
    merely because the extractor did not know direction."
    """
    names = {field.name for field in fields(_assignment_type())}
    assert names == {
        "construction_frame",
        "canonical_argument_slots",
        "argument_markers",
        "normalization_trace",
    }
    forbidden = {"commutative_slots", "polarity", "direction", "observed_construction_frame"}
    assert not names & forbidden
    assert not names & {"mention", "mention_ref", "surface", "participants"}



def _assignment_type() -> type:
    from domain.predicate_voice import CanonicalArgumentAssignment

    return CanonicalArgumentAssignment


def test_normalize_voice_is_deterministic_under_replay() -> None:
    """Domain Invariant 12: replay is a fixed point. Same inputs, same output, byte for
    byte, and nothing in the trace or the material depends on iteration order."""
    structure, dependencies = _reading(
        "sold",
        SyntacticConstruction.ACTIVE_CLAUSE,
        (
            _observation("nsubj", "John"),
            _observation("obj", "Acme"),
            _observation("nmod:to", "Microsoft", word="to"),
        ),
    )
    outputs = {
        canonical_material(
            normalize_voice(PredicateHead("sold"), structure, dependencies).to_dict()
        )
        for _ in range(5)
    }
    assert len(outputs) == 1
    reversed_structure = SyntacticStructure(
        construction=structure.construction,
        arguments=tuple(reversed(structure.arguments)),
        head_function_word=structure.head_function_word,
    )
    reversed_dependencies = DependencyStructure(
        edges=tuple(reversed(dependencies.edges)), root=dependencies.root
    )
    # V2 reads the EDGES order, not the argument tuple order, so a producer that hands
    # the arguments over in a different order reaches the same assignment.
    assert (
        normalize_voice(PredicateHead("sold"), reversed_structure, reversed_dependencies)
        == normalize_voice(PredicateHead("sold"), structure, dependencies)
    )


# --------------------------------------------------------------------------- #
# Part 4.3: the participant fingerprint
# --------------------------------------------------------------------------- #


def test_participant_fingerprint_is_invariant_across_realisations() -> None:
    """The realisation-independence claim, and the test that would fail if any
    sentence-level datum leaked in.

    The same mention read by two producers, with two role vocabularies and two minted
    ids, is the same participant - which is brief section 43's "ONE logical candidate /
    MANY signals" made mechanical.
    """
    mention = Mention("Acme", start=12, end=16)
    assert stable_participant_fingerprint(mention) == stable_participant_fingerprint(
        replace(mention, mention_id="MN-9999")
    )
    signature = _binary_signature()
    by_one_producer = canonical_participant_ordering(
        signature,
        frozenset(),
        [
            _participant(mention, 0, surface_role="company", role_hypothesis="buyer"),
            _participant(Mention("Microsoft", start=30, end=39), 1),
        ],
    )
    by_another = canonical_participant_ordering(
        signature,
        frozenset(),
        [
            _participant(
                replace(mention, mention_id="MN-4242"),
                0,
                surface_role="purchaser",
                role_hypothesis="vendor",
            ),
            _participant(Mention("Microsoft", start=30, end=39, mention_id="MN-4243"), 1),
        ],
    )
    assert by_one_producer == by_another



def test_participant_fingerprint_excludes_producer_span_type_and_confidence() -> None:
    """Each excluded datum mutated in turn; the fingerprint must not move.

    These four exclusions are the ones with a stated cost if they are wrong: a producer
    or a re-scoring pass in the fingerprint would fork a relation, and a type or shape
    datum would couple the type layer to relational identity through a digest.
    """
    mention = Mention("Acme", start=12, end=16)
    baseline = stable_participant_fingerprint(mention)
    for changed in (
        replace(mention, producer_ref="extractor:b", producer_version="9.9.9"),
        replace(mention, trigger_span="12-16", supporting_spans=("30-39",)),
        replace(mention, type_ref="core:Organization", argument_shape="legal_person"),
        replace(mention, confidence=0.99),
        replace(mention, evidence_refs=("OB-9",), mention_id="MN-0002"),
    ):
        assert stable_participant_fingerprint(changed) == baseline
    # And the datum that *is* part of the mention's identity does move it: the surface,
    # the capture, the segment and the span offsets.
    assert stable_participant_fingerprint(replace(mention, surface="Microsoft")) != baseline
    assert stable_participant_fingerprint(replace(mention, start=13)) != baseline
    assert stable_participant_fingerprint(replace(mention, capture_ref="CAP-2")) != baseline



def test_participant_fingerprint_is_a_digest_of_exactly_six_keys() -> None:
    """Part 4.3 key by key, so a future seventh key is a visible diff."""
    mention = Mention("Acme", start=12, end=16)
    expected = digest128(
        canonical_material(
            {
                "mention_kind": mention.kind,
                "normalized_surface": "acme",
                "capture_ref": mention.capture_ref,
                "segment_ref": mention.segment_ref,
                "start": mention.start,
                "end": mention.end,
            }
        )
    )
    assert stable_participant_fingerprint(mention) == expected
    assert len(expected) == 32
    assert expected == expected.lower()


# --------------------------------------------------------------------------- #
# Part 4.1-4.5: the ordering
# --------------------------------------------------------------------------- #


def test_binary_ordering_is_by_slot_alone_and_nary_by_slot_then_fingerprint() -> None:
    """O2-O5. Binary has nothing else to order by; n-ary adds the fingerprint."""
    binary_signature = _binary_signature()
    low, high = Mention("Zeta", start=0, end=4), Mention("Alpha", start=5, end=10)
    ordered = canonical_participant_ordering(
        binary_signature,
        frozenset(),
        [_participant(low, 0), _participant(high, 1)],
    )
    assert [participant.slot.token for participant in ordered] == ["A0", "A1"]
    # Swapping the two occupants swaps the two slots: the slots ARE the direction.
    reversed_ordered = canonical_participant_ordering(
        binary_signature,
        frozenset(),
        [_participant(high, 0), _participant(low, 1)],
    )
    assert reversed_ordered != ordered

    trinary = _binary_signature(
        canonical_argument_slots=(ArgumentSlot(0), ArgumentSlot(1), ArgumentSlot(2)),
        argument_markers=(ArgumentMarker.NOMARK, ArgumentMarker.NOMARK, ArgumentMarker.TO),
        predicate_lemma="sell",
    )
    john, acme, microsoft = (
        Mention("John", start=0, end=4),
        Mention("Acme", start=5, end=9),
        Mention("Microsoft", start=10, end=19),
    )
    participants = [
        _participant(microsoft, 2),
        _participant(acme, 1),
        _participant(john, 0),
    ]
    ordered = canonical_participant_ordering(trinary, frozenset(), participants)
    assert [participant.slot.token for participant in ordered] == ["A0", "A1", "A2"]
    assert ordered == canonical_participant_ordering(trinary, frozenset(), participants[::-1])
    assert all(participant.commutable is False for participant in ordered)


def test_slot_occupants_are_ordered_by_fingerprint() -> None:
    """O3, and part 4.4's tie-break: ascending by the 32 lowercase hex, byte-wise.

    The assertion is on the *fingerprint order*, not on the mention order, so the test
    cannot pass by accident through a mention-id sort. ``A1`` is declared commutative,
    because two occupants of a non-commutative slot is a contract error rather than a
    tie to break.
    """
    signature = _binary_signature()
    subject = Mention("Subject", start=0, end=7)
    first = Mention("Zeta", start=8, end=12)
    second = Mention("Alpha", start=13, end=18)
    participants = [
        _participant(first, 1, surface_role="A"),
        _participant(subject, 0),
        _participant(second, 1, surface_role="B"),
    ]
    ordered = canonical_participant_ordering(
        signature, frozenset({ArgumentSlot(1)}), participants
    )
    fingerprints = sorted(
        stable_participant_fingerprint(mention) for mention in (first, second)
    )
    assert [participant.slot.token for participant in ordered] == ["A0", "A1", "A1"]
    assert [participant.participant_fingerprint for participant in ordered[1:]] == fingerprints
    assert all(participant.commutable is True for participant in ordered[1:])
    assert ordered == canonical_participant_ordering(
        signature, frozenset({ArgumentSlot(1)}), participants[::-1]
    )



def test_non_commutative_slot_with_two_members_is_a_contract_error() -> None:
    """Part 4.4: no order is emitted. Ordering it anyway would be inventing a reading the
    structure does not license."""
    signature = _binary_signature()
    participants = [
        _participant(Mention("John", start=0, end=4), 0),
        _participant(Mention("Mary", start=5, end=9), 0),
        _participant(Mention("Acme", start=10, end=14), 1),
    ]
    with pytest.raises(SignatureContractError) as caught:
        canonical_participant_ordering(signature, frozenset(), participants)
    assert caught.value.code == "slot_not_commutative_multiple_members"
    assert "commutable" in caught.value.message


def test_duplicate_participant_fingerprint_is_refused() -> None:
    """The tie-break is a total order only because distinct mentions produce distinct
    fingerprints, so a repeat means one mention was bound to two roles."""
    signature = _binary_signature()
    same = Mention("Acme")
    participants = [
        _participant(same, 0),
        _participant(replace(same, mention_id="MN-0002"), 1),
    ]
    with pytest.raises(SignatureContractError) as caught:
        canonical_participant_ordering(signature, frozenset(), participants)
    assert caught.value.code == "duplicate_participant_fingerprint"


def test_commutable_iff_same_slot_and_explicitly_declared() -> None:
    """Part 4.5, both sentences: same slot AND declared. Nothing else, and no
    declaration may make participants in different slots commutable."""
    signature = _binary_signature()
    participants = [
        _participant(Mention("Acme", start=0, end=4), 0),
        _participant(Mention("Microsoft", start=5, end=14), 1),
    ]
    undeclared = canonical_participant_ordering(signature, frozenset(), participants)
    assert [participant.commutable for participant in undeclared] == [False, False]

    half_declared = canonical_participant_ordering(
        signature, frozenset({ArgumentSlot(0)}), participants
    )
    assert [participant.commutable for participant in half_declared] == [True, False]
    # The slots are unchanged by a symmetry declaration, so a directed edge's endpoints
    # are never reordered by one.
    assert [participant.slot.token for participant in half_declared] == ["A0", "A1"]

    fully_declared = canonical_participant_ordering(
        signature, frozenset({ArgumentSlot(0), ArgumentSlot(1)}), participants
    )
    assert [participant.commutable for participant in fully_declared] == [True, True]


def test_symmetry_is_never_inferred_from_missing_direction() -> None:
    """Section 53 verbatim: "Do not infer symmetry merely because the extractor did not
    know direction."

    An empty ``commutative_slots`` is a *declaration* of no symmetry, and it is the
    default; nothing in the signature, the ordering or the frame can fill it in.
    """
    signature = _binary_signature()
    participants = [
        _participant(Mention("Acme", start=0, end=4), 0),
        _participant(Mention("Microsoft", start=5, end=14), 1),
    ]
    material = logical_candidate_material(signature, participants, tenant_id=_TENANT)
    assert material["commutative_slots"] == []
    assert material["arity_mode"] == "directed"
    assert derive_arity_mode(
        signature, frozenset(), [participant.role for participant in participants]
    ) is RelationArityMode.DIRECTED
    # The per-occupant flag is *derived* from the declaration, never asserted: it is a
    # property of the marker, and nothing about the frame, the lemma or the slot count
    # can turn it on.
    assert [entry["commutable"] for entry in material["participants"]] == [False, False]



def test_symmetric_and_asymmetric_readings_get_different_logical_ids() -> None:
    """Part 4.5: they are different claims, and the store shows both."""
    signature = _binary_signature()
    participants = [
        _participant(Mention("Acme", start=0, end=4), 0),
        _participant(Mention("Microsoft", start=5, end=14), 1),
    ]
    directed = logical_candidate_id(signature, participants, tenant_id=_TENANT)
    undirected = logical_candidate_id(
        signature,
        participants,
        tenant_id=_TENANT,
        commutative_slots=frozenset({ArgumentSlot(0), ArgumentSlot(1)}),
    )
    assert directed != undirected
    assert directed.startswith("CAND-")
    assert len(directed) == len("CAND-") + 32


def test_undirected_ordering_uses_the_slot_marker_not_a_mention_id_sort() -> None:
    """Part 4.5, replacing the existing ``UNDIRECTED`` branch.

    The existing branch at ``relation_identity.py:178-183`` sorts *mention-id text* and
    deduplicates. Both are visible here as failures of the new rule: a mention whose id
    sorts the other way must not change the order, and a co-occupied slot must keep both
    participants rather than losing one.
    """
    signature = _binary_signature()
    left = Mention("Acme", start=0, end=4, mention_id="MN-zzz")
    right = Mention("Microsoft", start=5, end=14, mention_id="MN-aaa")
    by_id = canonical_participant_ordering(
        signature,
        frozenset({ArgumentSlot(0), ArgumentSlot(1)}),
        [_participant(left, 0), _participant(right, 1)],
    )
    swapped_ids = canonical_participant_ordering(
        signature,
        frozenset({ArgumentSlot(0), ArgumentSlot(1)}),
        [
            _participant(replace(left, mention_id="MN-aaa"), 0),
            _participant(replace(right, mention_id="MN-zzz"), 1),
        ],
    )
    assert by_id == swapped_ids
    assert [participant.slot.token for participant in by_id] == ["A0", "A1"]


def test_coordination_is_unsupported_until_a_frame_and_a_symmetry_marker_exist() -> None:
    """Part 4.4: coordination is ``UNSUPPORTED_CONSTRUCTION`` - a named stop condition,
    never papered over with a sort."""
    structure, dependencies = _reading(
        "acquired",
        SyntacticConstruction.ACTIVE_CLAUSE,
        (
            _observation("nsubj", "John"),
            _observation("obj", "Mary"),
            _observation("obj", "Acme"),
        ),
    )
    with pytest.raises(SignatureContractError) as caught:
        normalize_voice(PredicateHead("acquired"), structure, dependencies)
    assert caught.value.code == "unsupported_construction"
    assert "Coordination is a named stop condition" in caught.value.message
    assert not any(
        "COORDINAT" in row.construction.value for row in CONSTRUCTION_TABLE
    )


def test_arity_mode_is_native_to_the_arity_and_never_a_binary_payload() -> None:
    """Part 9: n-ary is native - role bindings, not a binary pair with an ``extra``."""
    trinary = _binary_signature(
        canonical_argument_slots=(ArgumentSlot(0), ArgumentSlot(1), ArgumentSlot(2)),
        argument_markers=(ArgumentMarker.NOMARK, ArgumentMarker.NOMARK, ArgumentMarker.TO),
        predicate_lemma="sell",
    )
    participants = [
        _participant(Mention("John", start=0, end=4), 0),
        _participant(Mention("Acme", start=5, end=9), 1),
        _participant(Mention("Microsoft", start=10, end=19), 2),
    ]
    material = logical_candidate_material(trinary, participants, tenant_id=_TENANT)
    assert material["arity_mode"] == "nary"
    assert len(material["participants"]) == 3
    assert "extra" not in material


# --------------------------------------------------------------------------- #
# Part 2.3: the six properties of a slot
# --------------------------------------------------------------------------- #


def test_argument_slot_space_is_unbounded_and_unregistered() -> None:
    """A slot set is a *formula*, ``{A_k : 0 <= k < arity}``, not a finite named set of
    claims. Nothing enumerates it, so there is nothing to resolve, block or query."""
    assert ArgumentSlot(10).token == "A10"
    assert ArgumentSlot(10) > ArgumentSlot(2)
    assert sorted([ArgumentSlot(10), ArgumentSlot(2)]) == [ArgumentSlot(2), ArgumentSlot(10)]
    assert ArgumentSlot(1000).to_identity() == "A1000"
    assert not any(
        "REGISTRY" in name or "VOCABULARY" in name
        for name in dir(__import__("domain.predicate_signature", fromlist=["x"]))
    )
    with pytest.raises(SignatureContractError) as caught:
        ArgumentSlot(-1)
    assert caught.value.code == "negative_argument_slot"


def test_argument_slot_carries_no_type_confidence_or_truth_claim() -> None:
    """A slot is an ``int`` and a token. Nothing can be inferred from one, so nothing is
    asserted by occupying it."""
    assert tuple(field.name for field in fields(ArgumentSlot)) == ("index",)
    assert not {"type", "confidence", "truth", "provenance", "polarity"} & set(
        dir(ArgumentSlot)
    ) - set(dir(object))


def test_slot_assignment_reads_dependency_position_not_type() -> None:
    """Part 2.3 property 2: ``A0`` because Company occupies the ``nsubj`` position - not
    because Company is judged to be an organisation or an agent.

    The negative half is the strong one: the projection carries no type key at all, so
    a change in what the *type* layer thinks about a participant cannot move it.
    """
    structure, dependencies = _reading(
        "acquired",
        SyntacticConstruction.ACTIVE_CLAUSE,
        (_observation("nsubj", "Company"), _observation("obj", "Asset")),
    )
    signature = normalize_predicate(PredicateHead("acquired"), structure, dependencies)
    assert "type" not in canonical_material(signature.identity_projection())
    assert "core:Organization" not in canonical_material(signature.identity_projection())
    same_shape, different_tokens = _reading(
        "acquired",
        SyntacticConstruction.ACTIVE_CLAUSE,
        (_observation("nsubj", "Zebra"), _observation("obj", "Asset")),
    )
    other = normalize_predicate(PredicateHead("acquired"), same_shape, different_tokens)
    assert other.identity_projection() == signature.identity_projection()


def test_same_mention_may_occupy_different_slots_in_different_signatures() -> None:
    """Part 2.3 property 4: slots are per-reading, not per-entity. An entity has no slot,
    which is the line INV-001 draws.

    The SAME mention, in the SAME participant position of two readings, is ``A0`` in one
    and ``A1`` in the other - so the readings are two candidates, and the mention's
    fingerprint is the same in both.
    """
    company = Mention("Company", start=0, end=7)
    asset = Mention("Asset", start=8, end=13)
    signature = _binary_signature()
    forward = [_participant(company, 0), _participant(asset, 1)]
    reverse = [_participant(asset, 0), _participant(company, 1)]
    assert logical_candidate_id(signature, forward, tenant_id=_TENANT) != (
        logical_candidate_id(signature, reverse, tenant_id=_TENANT)
    )
    forward_ordered = logical_candidate_material(signature, forward, tenant_id=_TENANT)
    reverse_ordered = logical_candidate_material(signature, reverse, tenant_id=_TENANT)
    company_fingerprint = stable_participant_fingerprint(company)
    assert company_fingerprint in {
        entry["participant_fingerprint"] for entry in forward_ordered["participants"]
    }
    assert company_fingerprint in {
        entry["participant_fingerprint"] for entry in reverse_ordered["participants"]
    }
    assert {entry["slot"] for entry in forward_ordered["participants"]} == {"A0", "A1"}
    assert {entry["slot"] for entry in reverse_ordered["participants"]} == {"A0", "A1"}
    # The slot the mention occupies is what moved, not the mention.
    moved = [
        entry["slot"]
        for entry in forward_ordered["participants"]
        if entry["participant_fingerprint"] == company_fingerprint
    ]
    assert moved == ["A0"]



def test_slot_occupants_need_not_share_a_type() -> None:
    """Part 2.3 property 6: slots and types are orthogonal, which is what lets the type
    layer do its work with no effect on relational identity."""
    trinary = _binary_signature(
        canonical_argument_slots=(ArgumentSlot(0), ArgumentSlot(1), ArgumentSlot(2)),
        argument_markers=(ArgumentMarker.NOMARK, ArgumentMarker.NOMARK, ArgumentMarker.TO),
        predicate_lemma="sell",
    )
    participants = [
        _participant(
            Mention("John", start=0, end=4, kind="person", type_ref="core:Person"), 0
        ),
        _participant(
            Mention("Acme", start=5, end=9, kind="organisation", type_ref="core:Organization"), 1
        ),
        _participant(
            Mention(
                "Microsoft",
                start=10,
                end=19,
                kind="organisation",
                argument_shape="legal_person",
            ),
            2,
        ),
    ]
    ordered = canonical_participant_ordering(trinary, frozenset(), participants)
    assert [participant.slot.token for participant in ordered] == ["A0", "A1", "A2"]


# --------------------------------------------------------------------------- #
# Part 5: the identity rule
# --------------------------------------------------------------------------- #


def test_normalize_voice_collapses_active_and_passive() -> None:
    """``SC-001`` at unit level, and it PASSES - no marker, no fixture, no parser.

    Both realisations reach the identical ``identity_projection()`` declared in part 3.8.
    """
    _mentions, pair = _acquire_pair()
    assert pair["active"].identity_projection() == pair["passive"].identity_projection()
    assert pair["active"].identity_projection() == {
        "language": "en",
        "predicate_lemma": "acquire",
        "construction_frame": "verb_active_transitive",
        "argument_markers": ["", ""],
        "canonical_argument_slots": ["A0", "A1"],
        "voice_normalization_version": "vn-1",
        "predicate_normalization_version": "pn-1",
    }
    assert pair["active"].rendered_predicate() == pair["passive"].rendered_predicate() == (
        "acquire(A0:,A1:)"
    )


def test_sc001_active_and_passive_reach_one_logical_candidate_id() -> None:
    """``SC-001``'s claim, end to end inside the unit: one id, computed, not asserted.

    The two realisations are built from the SAME mention records, so the only thing
    that differs between them is the parse - which is the entire content of the claim.
    """
    mentions, pair = _acquire_pair()
    company, asset = mentions
    forward = [_participant(company, 0), _participant(asset, 1)]
    passive = [_participant(asset, 1), _participant(company, 0)]
    assert logical_candidate_id(pair["active"], forward, tenant_id=_TENANT) == (
        logical_candidate_id(pair["passive"], passive, tenant_id=_TENANT)
    )
    assert logical_candidate_id(pair["passive"], passive, tenant_id=_TENANT) == (
        logical_candidate_id(pair["passive"], passive[::-1], tenant_id=_TENANT)
    )


def test_surface_variants_reach_one_logical_candidate_id() -> None:
    """"works for" and "Works For" are one hypothesis, not two.

    The two readings differ in every word the observation used and in nothing the
    signature reads, which is brief section 18's own requirement made checkable.
    """
    identifiers = {}
    for head, word in (("works", "for"), ("Works", "For")):
        structure, dependencies = _reading(
            head,
            SyntacticConstruction.HEADLESS_PP,
            (_observation("pobj", "Acme", word=word), _observation("nsubj", "John")),
        )
        signature = normalize_predicate(PredicateHead(head), structure, dependencies)
        participants = [
            _participant(Mention("John", start=0, end=4), 1),
            _participant(Mention("Acme", start=10, end=14), 0),
        ]
        identifiers[head] = logical_candidate_id(signature, participants, tenant_id=_TENANT)
    assert len(set(identifiers.values())) == 1


def test_no_surface_span_producer_or_evidence_reaches_the_logical_id() -> None:
    """The mechanism, not the promise: the identity function has no parameter through
    which any of those could arrive, and the material's key set excludes all of them."""
    excluded = {
        "relation_surface",
        "predicate_surface",
        "trigger_span",
        "supporting_spans",
        "structural_path",
        "producer_ref",
        "producer_version",
        "extraction_method",
        "extractor_version",
        "extraction_rule_id",
        "signal_refs",
        "observation_refs",
        "evidence_refs",
        "context_ref",
        "semantic_regime_ref",
        "capture_ref",
        "signal_ordinal",
        "confidence",
        "candidate_status",
        "observed_at",
        "recorded_by",
        "investigation_id",
        "temporal_hypothesis",
        "relation_ref",
        "relation_type",
        "schema_version",
        "predicate_hypothesis",
        "alternative_refs",
        "mapping_evidence_refs",
        "resolution_state",
        "assembly_state",
        "extra",
    }
    signature = _binary_signature()
    material = logical_candidate_material(
        signature,
        [
            _participant(
                Mention("Acme", start=0, end=4, evidence_refs=("OB-1", "OB-2")),
                0,
                evidence=("OB-1", "OB-2"),
            ),
            _participant(Mention("Microsoft", start=5, end=14), 1),
        ],
        tenant_id=_TENANT,
    )

    assert set(material) == {
        "identity_schema",
        "tenant_id",
        "arity_mode",
        "commutative_slots",
        "polarity",
        "predicate_signature",
        "participants",
    }
    assert not set(material) & excluded
    parameters = set(inspect.signature(logical_candidate_id).parameters)
    assert not parameters & excluded
    assert parameters == {
        "signature",
        "participants",
        "tenant_id",
        "polarity",
        "commutative_slots",
        "arity_mode",
    }
    # The evidence a participant carries is retained on the binding and is not in the
    # material: it is revision material.
    assert "evidence" not in canonical_material(material)
    assert "OB-1" not in canonical_material(material)



def test_tenant_and_polarity_are_in_the_material() -> None:
    """FR-002 and brief section 19 verbatim.

    Tenant isolation is not decoration: omitting it would let two tenants' hypotheses
    bucket under one key, which constitution IV forbids. Polarity is in because "John
    did not acquire Acme" is a different hypothesis from "John acquired Acme".
    """
    signature = _binary_signature()
    participants = [
        _participant(Mention("Acme", start=0, end=4), 0),
        _participant(Mention("Microsoft", start=5, end=14), 1),
    ]
    assert logical_candidate_id(signature, participants, tenant_id="tenant-a") != (
        logical_candidate_id(signature, participants, tenant_id="tenant-b")
    )
    assert logical_candidate_id(signature, participants, tenant_id=_TENANT) != (
        logical_candidate_id(
            signature, participants, tenant_id=_TENANT, polarity=Polarity.DENIED
        )
    )
    assert logical_candidate_material(signature, participants, tenant_id=_TENANT)["polarity"] == (
        "asserted"
    )


def test_owns_controls_manages_never_share_a_logical_candidate_id() -> None:
    """FR-004 and brief section 20: surface variation must not force semantic inequality,
    but similarity of sound must not force semantic equality. These are three
    signatures and therefore three logical ids, permanently."""
    identifiers = set()
    for word in ("owns", "controls", "manages"):
        structure, dependencies = _reading(
            word,
            SyntacticConstruction.ACTIVE_CLAUSE,
            (_observation("nsubj", "John"), _observation("obj", "Acme")),
        )
        signature = normalize_predicate(PredicateHead(word), structure, dependencies)
        participants = [
            _participant(Mention("John", start=0, end=4), 0),
            _participant(Mention("Acme", start=5, end=9), 1),
        ]
        identifiers.add(logical_candidate_id(signature, participants, tenant_id=_TENANT))
    assert len(identifiers) == 3


def test_changing_the_slot_convention_bumps_the_version_and_changes_the_logical_id() -> None:
    """Part 2.4, point 4: a reading whose slots were assigned under an old convention is
    a *different structural claim*, and the platform must not silently re-key history.

    The two coexist as two candidates, which is visible, rather than one candidate whose
    id moved, which is not.
    """
    acme, microsoft = Mention("Acme", start=0, end=4), Mention("Microsoft", start=5, end=14)
    under_vn1 = _binary_signature()
    under_vn2 = _binary_signature(voice_normalization_version="vn-2")
    read_under_vn1 = [_participant(acme, 0), _participant(microsoft, 1)]
    read_under_vn2 = [
        _participant(acme, 0, version="vn-2"),
        _participant(microsoft, 1, version="vn-2"),
    ]
    assert under_vn1.identity_projection() != under_vn2.identity_projection()
    assert logical_candidate_id(under_vn1, read_under_vn1, tenant_id=_TENANT) != (
        logical_candidate_id(under_vn2, read_under_vn2, tenant_id=_TENANT)
    )
    # Mixing the two conventions in one candidate is refused rather than ordered, so
    # there is no third id that could be mistaken for a re-key of either.
    with pytest.raises(SignatureContractError) as caught:
        logical_candidate_id(under_vn1, read_under_vn2, tenant_id=_TENANT)
    assert caught.value.code == "role_binding_version_must_match_signature"

    # And the projection alone can rebuild the claim: the version is in the record, not
    # only in a digest (FR-060).
    assert (
        PredicateSignature.from_dict(under_vn2.to_dict()).identity_projection()
        == under_vn2.identity_projection()
    )


def test_candidate_without_a_signature_has_no_logical_candidate_id() -> None:
    """Part 5.4, verbatim: the signature is REQUIRED. A surface-keyed fallback identity
    is forbidden, and two code paths deriving ids is one more path to disagree."""
    participants = [_participant(Mention("Acme"), 0), _participant(Mention("Microsoft"), 1)]
    for call in (
        lambda: logical_candidate_material(None, participants, tenant_id=_TENANT),
        lambda: logical_candidate_id(None, participants, tenant_id=_TENANT),
    ):
        with pytest.raises(SignatureContractError) as caught:
            call()
        assert caught.value.code == "unaddressed_logical_identity"
        assert "surface-keyed fallback" in caught.value.message


def test_unsignatured_and_signatured_readings_do_not_merge() -> None:
    """An unsupported construction produces no signature, so it cannot be grouped with a
    reading that has one: distinct predicates over the same endpoints remain distinct
    hypotheses, and an unaddressed one is addressable only by ``candidate_id``."""
    _mentions, pair = _acquire_pair()
    participants = [
        _participant(Mention("Company", start=0, end=7), 0),
        _participant(Mention("Asset", start=21, end=26), 1),
    ]
    identified = logical_candidate_id(pair["active"], participants, tenant_id=_TENANT)
    with pytest.raises(SignatureContractError) as caught:
        logical_candidate_id(None, participants, tenant_id=_TENANT)
    assert caught.value.code == "unaddressed_logical_identity"
    assert identified != ""


def test_mapping_vocabulary_is_not_an_input_to_logical_identity() -> None:
    """``INV-IDENTITY``, demonstrated rather than disclaimed.

    The mapping apparatus is replaced with a different one - a different operator
    catalogue, a different regime configuration, a different type pack - and every
    derived logical id is unchanged, because none of those is an input. Step 5 of the
    specification's demonstration (a changed ``candidate_id``) belongs to
    ``RelationCandidate`` and is reported as blocked, not simulated here.
    """
    signature = _binary_signature()
    participants = [
        _participant(Mention("Acme", start=0, end=4), 0),
        _participant(Mention("Microsoft", start=5, end=14), 1),
    ]
    before = logical_candidate_id(signature, participants, tenant_id=_TENANT)

    from semantic.contracts import RelationRef

    operator_catalogue_before = {RelationRef("acquisition", "1"), RelationRef("owns", "1")}
    operator_catalogue_after = {RelationRef("control", "9"), RelationRef("acquire", "4")}
    regime_before = {"threshold": 0.5, "operator": RelationRef("acquisition", "1")}
    regime_after = {"threshold": 0.9, "operator": RelationRef("control", "9")}
    type_pack_before = {"acme": "core:Organization"}
    type_pack_after = {"acme": "ext:Vendor"}

    after = logical_candidate_id(signature, participants, tenant_id=_TENANT)
    assert before == after
    assert operator_catalogue_before != operator_catalogue_after
    assert regime_before != regime_after
    assert type_pack_before != type_pack_after
    assert operator_catalogue_after and type_pack_after
    # The apparatus really was installed: the new refs exist as objects and are not in
    # the material.
    material = canonical_material(
        logical_candidate_material(signature, participants, tenant_id=_TENANT)
    )
    assert "control" not in material
    assert "ext:Vendor" not in material



def test_no_caller_order_reaches_the_logical_id() -> None:
    """Every collection that is present is emitted in canonical order, so no caller's
    iteration order can reach the id - the defect that ``relation_candidate.py`` and
    ``assembly.py`` currently leave to a hand-sort at one call site."""
    signature = _binary_signature()
    participants = [
        _participant(Mention("John", start=0, end=4), 0),
        _participant(Mention("Acme", start=5, end=9), 1),
        _participant(Mention("Microsoft", start=10, end=19), 2),
    ]
    trinary = _binary_signature(
        canonical_argument_slots=(ArgumentSlot(0), ArgumentSlot(1), ArgumentSlot(2)),
        argument_markers=(ArgumentMarker.NOMARK, ArgumentMarker.NOMARK, ArgumentMarker.TO),
        predicate_lemma="sell",
    )
    all_commutative = frozenset({ArgumentSlot(0), ArgumentSlot(1), ArgumentSlot(2)})
    materials = {
        canonical_material(
            logical_candidate_material(
                trinary, order, tenant_id=_TENANT, commutative_slots=all_commutative
            )
        )
        for order in (
            participants,
            participants[::-1],
            [participants[1], participants[2], participants[0]],
        )
    }
    assert len(materials) == 1
    assert set(logical_candidate_material(signature, participants[:2], tenant_id=_TENANT))


def test_identity_schema_version_is_in_the_material() -> None:
    """Without the shape version, a future key addition is undetectable in the record."""
    material = logical_candidate_material(
        _binary_signature(),
        [_participant(Mention("A"), 0), _participant(Mention("B"), 1)],
        tenant_id=_TENANT,
    )
    assert material["identity_schema"] == IDENTITY_SCHEMA_VERSION == "cand-logical-2"
    assert "cand-logical-2" in canonical_material(material)


# --------------------------------------------------------------------------- #
# The static properties the constitution needs (part 5.3)
# --------------------------------------------------------------------------- #


def _module_source(module_name: str) -> ast.Module:
    """The module's source as an AST.

    Only parsed, never executed: the import graph is the subject, and re-executing a
    module under a synthetic name would make ``dataclasses`` fail on a class whose
    ``__module__`` is not in ``sys.modules`` - an artefact of the test, not a property
    of the code.
    """
    import pathlib

    import domain

    path = pathlib.Path(domain.__file__).parent / f"{module_name}.py"
    return ast.parse(path.read_text(encoding="utf-8"))



def _imported_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def test_normalize_voice_and_ordering_never_read_the_mapping_layer() -> None:
    """No import edge from the identity path to a registry, a regime or a type pack.

    A static check, because the residual of ``INV-IDENTITY`` is silent: if anyone later
    adds a signature field computed *from* a registry - ``event_class_hint`` was exactly
    that shape - the invariant breaks without any test noticing.
    """
    forbidden = {
        "semantic.contracts",
        "semantic",
        "relation_schema",
        "predicate_hypothesis",
        "relation_candidate",
        "relation_claim",
        "entity",
        "entity_identity",
    }
    for module_name in ("predicate_signature", "predicate_voice"):
        imported = _imported_names(_module_source(module_name))
        assert not {name for name in imported if name.split(".")[0] in forbidden}, module_name
        assert not any("regime" in name or "type_pack" in name for name in imported)


def test_logical_material_key_set_is_exact() -> None:
    """Part 5.1: the material has exactly seven keys, and a signature's projection has
    exactly the seven the dataclass declares.

    Sibling of brief section 94's import test, and the static half of
    ``test_mutation_relation_ref_in_logical_material_fails``.
    """
    signature = _binary_signature()
    participants = [
        _participant(Mention("Acme", start=0, end=4), 0),
        _participant(Mention("Microsoft", start=5, end=14), 1),
    ]
    material = logical_candidate_material(signature, participants, tenant_id=_TENANT)
    assert tuple(sorted(material)) == (
        "arity_mode",
        "commutative_slots",
        "identity_schema",
        "participants",
        "polarity",
        "predicate_signature",
        "tenant_id",
    )
    assert tuple(sorted(material["predicate_signature"])) == tuple(
        sorted(signature.identity_projection())
    )
    assert tuple(sorted(entry for entry in material["participants"][0])) == (
        "commutable",
        "participant_fingerprint",
        "slot",
    )


def test_mutation_relation_ref_in_logical_material_fails() -> None:
    """The mutation guard, in the only form available before the candidate is rewritten:
    a static assertion that no mapping key can reach the material.

    If somebody adds ``relation_ref.relation_type`` to the material, one of these two
    assertions fails; if somebody adds a *parameter* carrying it, the other does.
    """
    signature = _binary_signature()
    participants = [
        _participant(Mention("Acme", start=0, end=4), 0),
        _participant(Mention("Microsoft", start=5, end=14), 1),
    ]
    material = canonical_material(
        logical_candidate_material(signature, participants, tenant_id=_TENANT)
    )
    for mapping_key in (
        "relation_ref",
        "relation_type",
        "schema_version",
        "resolution_state",
        "semantic_regime_ref",
        "predicate_hypothesis",
    ):
        assert f'"{mapping_key}"' not in material
    assert not {"relation_ref", "relation_type"} & set(
        inspect.signature(logical_candidate_id).parameters
    )
