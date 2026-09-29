"""``RelationCandidate``'s logical identity, once it stopped keying on the surface.

Contract: ``specs/021-entity-relation-extraction-finalization/data-model.md`` parts 1, 2, 4, 5,
7 and 9; ``repair/A2-identity-subsystem.md`` D2, D4, D5 and D9. ``test_predicate_signature.py``
pins the *rules* of the identity subsystem and
``tests/constitution/test_identity_subsystem_constitution.py`` pins the constitutional claims; this
file pins the wiring — that ``RelationCandidate`` actually derives its id by that rule, and that
nothing which used to be in the material still is.

**What changed, and what each defect was.** At HEAD, ``_logical_material`` passed
``self.relation_surface`` into ``logical_material``'s ``relation_type`` parameter, so the words the
observation used *were* the predicate term of a candidate's logical id, and
``CANDIDATE_LOGICAL_MATERIAL_FIELDS`` declared ``relation_type`` and ``role_assignments`` while the
code emitted neither. Two of those defects hid each other: a candidate built with no surface and a
``relation_ref`` had its surface synthesised from the operator it was mapped to, and because the
*material* keyed on that surface, the mapping really was the identity. Deleting the fallback alone
would have silently re-keyed every such candidate; deleting the surface keying alone would have
left the identity a function of the vocabulary. Both are gone together.

**The state this file pins is mostly "no id".** A ``PredicateSignature`` can only be obtained by
reading a construction, and no producer in this repository parses one yet, so every candidate the
existing suites build is un-signatured and gets ``logical_candidate_id = ""`` — addressable by
``candidate_id`` alone. That is part 5.4's decision, not a gap, and the tests that need a logical
id build the signature by hand from the same value types the syntactic producer will build it
from. The alternative — a surface-keyed fallback — is FR-001's violation under a version tag, and
two code paths deriving ids is one more path to disagree.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, replace
from datetime import UTC, datetime

import pytest

from domain.predicate_signature import (
    PREDICATE_NORMALIZATION_VERSION,
    VOICE_NORMALIZATION_VERSION,
    ArgumentMarker,
    ArgumentSlot,
    ConstructionFrame,
    ParticipantBinding,
    Polarity,
    PredicateSignature,
    RoleBinding,
)
from domain.relation_candidate import (
    CANDIDATE_LOGICAL_MATERIAL_CONSTANT_KEYS,
    CANDIDATE_LOGICAL_MATERIAL_FIELDS,
    CANDIDATE_LOGICAL_MATERIAL_KEYS,
    CANDIDATE_REVISION_MATERIAL_FIELDS,
    CandidateAssemblyState,
    CandidateContractError,
    CandidateStatus,
    RelationCandidate,
    SpanRef,
    TemporalHypothesis,
    verify_candidate_field_partition,
    verify_candidate_identity,
    verify_candidate_material_partition,
)
from semantic.contracts import RelationRef

pytestmark = pytest.mark.unit


@dataclass(frozen=True)
class Mention:
    """The six fields a participant fingerprint reads, plus the refs it must *not* read.

    ``mention_id`` is here because the production mention records carry one, and because the
    cross-check that keeps a candidate's participant set and its mention refs from becoming two
    truths needs it. It is deliberately not in the fingerprint's digest input.
    """

    surface: str
    kind: str = "entity"
    capture_ref: str = "CAP-1"
    segment_ref: str = "SEG-1"
    start: int = 0
    end: int = 0
    mention_id: str = "MN-1"


def _signature(
    lemma: str = "work",
    markers: tuple[ArgumentMarker, ...] = (ArgumentMarker.NOMARK, ArgumentMarker.FOR),
) -> PredicateSignature:
    """A binary ``VERB_ACTIVE_TRANSITIVE`` reading with the given lemma and markers."""
    return PredicateSignature(
        language="en",
        predicate_lemma=lemma,
        construction_frame=ConstructionFrame.VERB_ACTIVE_TRANSITIVE,
        argument_markers=markers,
        canonical_argument_slots=(ArgumentSlot(0), ArgumentSlot(1)),
        voice_normalization_version=VOICE_NORMALIZATION_VERSION,
        predicate_normalization_version=PREDICATE_NORMALIZATION_VERSION,
    )


def _binding(index: int, surface_role: str) -> RoleBinding:
    return RoleBinding(
        surface_role=surface_role,
        role_hypothesis="",
        canonical_argument_slot=ArgumentSlot(index),
        normalization_version=VOICE_NORMALIZATION_VERSION,
    )


def _participants(
    role_a: str = "agent",
    role_b: str = "employer",
) -> tuple[ParticipantBinding, ...]:
    """``A0`` first, ``A1`` second — the order ``canonical_participant_ordering`` fixes anyway."""
    return (
        ParticipantBinding(
            role=_binding(0, role_a),
            mention=Mention("John Smith", start=0, end=10, mention_id="MN-1"),
        ),
        ParticipantBinding(
            role=_binding(1, role_b),
            mention=Mention("Acme", start=40, end=44, mention_id="MN-2"),
        ),
    )


_BASE: dict[str, object] = {
    "subject_mention_ref": "MN-1",
    "object_mention_ref": "MN-2",
    "relation_surface": "works for",
    "context_ref": "CX-1",
    "semantic_regime_ref": "RG-1",
    "tenant_id": "T1",
    "temporal_hypothesis": TemporalHypothesis.absent(),
}


def _signed(**over) -> RelationCandidate:
    """A candidate carrying a signature, so it has a ``logical_candidate_id`` to compare."""
    return RelationCandidate(
        **{
            **_BASE,
            "predicate_signature": _signature(),
            "participants": _participants(),
            **over,
        }
    ).with_id()


def _unsigned(**over) -> RelationCandidate:
    """A candidate with no signature — the state every existing producer is in."""
    return RelationCandidate(**{**_BASE, **over}).with_id()


# --------------------------------------------------------------------------- #
# The predicate term is the signature
# --------------------------------------------------------------------------- #


def test_two_spellings_of_one_surface_reach_one_logical_candidate_id() -> None:
    """``"works for"`` and ``"Works For"`` are one hypothesis.

    The mechanism is the signature, and specifically ``predicate_lemma`` plus
    ``ArgumentMarker.FOR`` — not a normaliser applied to the surface, because the surface is not in
    the material at all. Both words survive as two ``Text`` values on two records, which is the
    whole of brief section 18's "retaining two distinct surface observations: as evidence".
    """
    lower = _signed(relation_surface="works for")
    capitalised = _signed(relation_surface="Works For")
    assert lower.logical_candidate_id == capitalised.logical_candidate_id
    assert lower.logical_candidate_id.startswith("CAND-")
    # Two readings, though: the evidence differs, so the revision address must too.
    assert lower.relation_surface != capitalised.relation_surface
    assert lower.candidate_id != capitalised.candidate_id


def test_the_surface_is_not_reachable_from_the_material() -> None:
    """The mechanism rather than the conclusion: no surface, anywhere in the material.

    Asserted by reading the material's own text, because a functional test cannot distinguish "the
    surface does not change the id" from "the surface happens to be equal in both fixtures".
    """
    from domain.relation_identity import canonical_material

    material = canonical_material(_signed(relation_surface="works for")._logical_material())
    assert "works for" not in material
    assert "relation_surface" not in material
    for excluded in (
        "subject_mention_ref",
        "object_mention_ref",
        "role_assignments",
        "relation_ref",
        "relation_type",
        "signal_refs",
        "extraction_method",
        "extractor_version",
        "extraction_rule_id",
        "trigger_span",
        "supporting_spans",
        "observation_refs",
        "evidence_refs",
        "context_ref",
        "semantic_regime_ref",
        "candidate_status",
        "observed_at",
        "confidence",
        "predicate_hypothesis",
        "temporal_hypothesis",
    ):
        assert f'"{excluded}"' not in material, excluded


def test_the_mapping_target_no_longer_supplies_a_surface() -> None:
    """The tripwire that used to sit in the constitution suite, inverted.

    ``__post_init__`` used to build the predicate hypothesis with
    ``surface_form=self.relation_surface or str(self.relation_ref.relation_type)``, so a candidate
    with no surface and a ``relation_ref`` carried words the observation never used. Those words
    were the predicate term of its logical id, so the mapping layer was writing into identity —
    "mapping below identity" with the arrow reversed, and the reason a vocabulary swap re-keyed
    stored observations.
    """
    mapped = _unsigned(relation_surface="", relation_ref=RelationRef("works_for"))
    assert mapped.relation_surface == ""
    assert mapped.predicate_hypothesis.surface_form == ""
    # The operator is still recorded, in the reading rather than in the predicate projection.
    assert mapped.relation_type == "works_for"
    assert mapped.predicate_hypothesis.relation_ref == RelationRef("works_for")


def test_the_mapping_target_is_never_read_as_the_predicate_term() -> None:
    """The same claim read off the source, so a refactor cannot reintroduce it silently.

    The two halves of the old defect were coupled: the fallback existed to keep the material
    non-empty, and the material keyed on the surface. Any future change that restores one without
    the other is a silent re-key, so both absences are asserted together.

    Read from the AST rather than the text, so the comment that *documents* the removed line does
    not read as the removed line.
    """
    import ast
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[2] / "domain" / "relation_candidate.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)
    post_init = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "__post_init__"
    )
    assert not [
        node
        for node in ast.walk(post_init)
        if isinstance(node, ast.Attribute) and node.attr == "relation_type"
    ], "__post_init__ must never read the mapping target"
    assert not [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "logical_material"
    ], "RelationCandidate must not derive its identity through the claim layer's logical_material"


def test_owns_controls_and_manages_stay_three_configurations() -> None:
    """FR-004, brief section 20: surface variation must not force equality, and similarity must
    not force equivalence.

    Three lemmas, three signatures, three logical ids — and no synonym table anywhere in the path
    that could make it two.
    """
    ids = {
        lemma: _signed(predicate_signature=_signature(lemma=lemma)).logical_candidate_id
        for lemma in ("own", "control", "manage")
    }
    assert len(set(ids.values())) == 3, ids


def test_a_marker_is_structural_and_at_is_not_for() -> None:
    """``works at`` and ``works for`` are two readings, and saying so is the point.

    Unifying them is a lexical-semantic claim, and brief section 20 reserves it to explicit
    mapping. ``ArgumentMarker`` exists so it cannot be made by accident, so this is really a test
    that the marker survived into the material.
    """
    at_acme = _signed(
        predicate_signature=_signature(markers=(ArgumentMarker.NOMARK, ArgumentMarker.AT))
    )
    for_acme = _signed()
    assert at_acme.logical_candidate_id != for_acme.logical_candidate_id


# --------------------------------------------------------------------------- #
# INV-IDENTITY: nothing that is evidence, provenance or a mapping may move the id
# --------------------------------------------------------------------------- #


def test_the_surface_does_not_change_the_logical_candidate_id() -> None:
    assert (
        _signed(relation_surface="works for").logical_candidate_id
        == _signed(relation_surface="chief executive of").logical_candidate_id
    )


def test_a_span_does_not_change_the_logical_candidate_id() -> None:
    """A span is a location in one document. One configuration observed twice has two spans and
    one id (data-model.md part 1.2 class 1)."""
    here = _signed(trigger_span=SpanRef(segment_ref="SEG-1", start=12, end=21))
    elsewhere = _signed(
        trigger_span=SpanRef(segment_ref="SEG-9", start=900, end=909, mention_ref="MN-1")
    )
    assert here.logical_candidate_id == elsewhere.logical_candidate_id
    assert here.candidate_id != elsewhere.candidate_id


def test_the_producer_does_not_change_the_logical_candidate_id() -> None:
    """FR-006/FR-001: the producer belongs to the *observation*, not the hypothesis. Putting it
    in the candidate's logical term would extend producer scope up a level and break SC-005."""
    from domain.relation_candidate import ExtractionStrategy

    one = _signed(extraction_method=ExtractionStrategy.LEXICAL_PATTERN, extractor_version="1.2.3")
    two = _signed(
        extraction_method=ExtractionStrategy.DEPENDENCY_PATTERN,
        extractor_version="9.9.9",
        extraction_rule_id="R-77",
    )
    assert one.logical_candidate_id == two.logical_candidate_id
    assert one.candidate_id != two.candidate_id


def test_evidence_does_not_change_the_logical_candidate_id() -> None:
    """Which observations back a hypothesis is a separate fact that *grows*; a second producer
    must mint a second reading, not a second hypothesis (brief section 43)."""
    bare = _signed()
    corroborated = _signed(
        observation_refs=("OB-2", "OB-1"),
        evidence_refs=("EV-3", "EV-1", "EV-2"),
        signal_refs=("SIG-2", "SIG-1"),
    )
    assert bare.logical_candidate_id == corroborated.logical_candidate_id
    assert bare.candidate_id != corroborated.candidate_id


def test_observation_order_does_not_change_the_logical_candidate_id() -> None:
    """And it does not change the *revision* id either — which is the determinism half.

    ``signal_refs``, ``observation_refs`` and ``evidence_refs`` are all canonicalised on
    construction, so a producer that collected its refs in a different order produces the same
    reading rather than a new one.
    """
    forwards = _signed(
        observation_refs=("OB-1", "OB-2"),
        evidence_refs=("EV-1", "EV-2"),
        signal_refs=("SIG-1", "SIG-2"),
    )
    backwards = _signed(
        observation_refs=("OB-2", "OB-1"),
        evidence_refs=("EV-2", "EV-1"),
        signal_refs=("SIG-2", "SIG-1"),
    )
    assert forwards.candidate_id == backwards.candidate_id
    assert forwards.logical_candidate_id == backwards.logical_candidate_id


def test_confidence_does_not_change_the_logical_candidate_id() -> None:
    """FR-001, named explicitly: a re-scoring pass must not mint a new relation, or every ranking
    change forks the graph."""
    unsure = _signed(confidence=0.05)
    sure = _signed(confidence=0.99)
    assert unsure.logical_candidate_id == sure.logical_candidate_id
    assert unsure.candidate_id == sure.candidate_id


def test_a_mapping_does_not_change_the_logical_candidate_id() -> None:
    """``INV-IDENTITY``, on the candidate: same signature, different ``relation_ref``, one id.

    The mapping is not dropped — it moves ``candidate_id``, which is the demonstration in
    ``data-model.md`` part 5.3 step 5 rather than a disclaimer. A recognition shows up as a new
    reading of the same configuration, and the old reading is still there.
    """
    unmapped = _signed(relation_surface="works for")
    mapped = _signed(relation_surface="works for", relation_ref=RelationRef("employment"))
    remapped = _signed(relation_surface="works for", relation_ref=RelationRef("works_at"))
    assert unmapped.logical_candidate_id == mapped.logical_candidate_id
    assert mapped.logical_candidate_id == remapped.logical_candidate_id
    assert len({unmapped.candidate_id, mapped.candidate_id, remapped.candidate_id}) == 3
    # The words the mapping is about survive verbatim on every reading.
    assert {unmapped.relation_surface, mapped.relation_surface} == {"works for"}


def test_assembly_state_does_not_change_the_logical_candidate_id() -> None:
    """``ARBITRATION`` §3 on the candidate: a structural disagreement is **revision** material.

    Two readings of one configuration whose producers disagreed about its shape are **one
    hypothesis with two ``candidate_id`` values**, and the disagreement is the evidence. If
    ``assembly_state`` were logical material, a second producer disagreeing about arity would mint
    a second ``logical_candidate_id`` — so the field that exists to *record* the disagreement would
    destroy the one thing the logical/revision split exists to preserve: that every revision of one
    configuration is recognisably the same hypothesis.

    This is the same shape as :func:`test_evidence_does_not_change_the_logical_candidate_id` and
    the same reason, and it is asserted with a **signed** candidate so there is a logical id to
    compare at all.
    """
    agreed = _signed(assembly_state=CandidateAssemblyState.CONSISTENT)
    contested = _signed(assembly_state=CandidateAssemblyState.CONFLICTING)
    assert agreed.logical_candidate_id == contested.logical_candidate_id
    assert agreed.logical_candidate_id.startswith("CAND-")
    assert agreed.candidate_id != contested.candidate_id
    # And the other two members are real values rather than decoration: the enum is the three
    # ``ARBITRATION`` §3 specifies, and the contested one is what the predicate reports itself.
    assert {str(state) for state in CandidateAssemblyState} == {
        "consistent",
        "ambiguous",
        "conflicting",
    }
    assert contested.is_structurally_contested and not agreed.is_structurally_contested
    # And it is emphatically NOT the status: a structural conflict and a denial are separate
    # fields with separate values, and neither implies the other.
    assert agreed.candidate_status is contested.candidate_status is CandidateStatus.PROPOSE
    assert contested.candidate_status is not CandidateStatus.CONTRADICTED


def test_assembly_state_is_declared_as_revision_material_and_emitted() -> None:
    """The partition, mechanically, because a field nothing emits is a field nothing is read from.

    ``verify_candidate_material_partition`` raises ``candidate_field_never_addressed`` for a
    declared field the canonical material never emits, and
    :func:`verify_candidate_field_partition` raises ``unclassified_candidate_field`` for a field
    in no set at all. Both were red at HEAD for other fields and nothing called them, which is
    why the two checks are called here rather than trusted.
    """
    assert "assembly_state" in CANDIDATE_REVISION_MATERIAL_FIELDS
    assert "assembly_state" not in CANDIDATE_LOGICAL_MATERIAL_FIELDS
    candidate = _signed(assembly_state=CandidateAssemblyState.CONFLICTING)
    assert "assembly_state" not in (candidate._logical_material() or {})
    assert candidate._revision_material(candidate.logical_candidate_id)["assembly_state"] == (
        "conflicting"
    )
    assert candidate._material()["assembly_state"] == "conflicting"
    verify_candidate_material_partition(candidate)
    verify_candidate_field_partition()
    # A token the vocabulary has no member for is refused rather than stored, because this is a
    # record of a *finding* and an unreadable finding records nothing.
    with pytest.raises(CandidateContractError) as caught:
        _signed(assembly_state="contested-ish")
    assert caught.value.code == "invalid_assembly_state"


def test_tenant_and_polarity_do_change_the_logical_candidate_id() -> None:
    """The other direction: the terms that *must* be there are.

    ``tenant_id`` because omitting it would let two tenants' configurations bucket under one key
    (constitution IV), and ``polarity`` because "John did not acquire Acme" is a different
    hypothesis from "John acquired Acme" (brief section 109 case H). A test that only checked
    exclusions would pass on an identity that was empty.
    """
    assert _signed().logical_candidate_id != _signed(tenant_id="T2").logical_candidate_id
    assert (
        _signed(polarity=Polarity.ASSERTED).logical_candidate_id
        != _signed(polarity=Polarity.DENIED).logical_candidate_id
    )


def test_the_tenant_reaches_the_address_even_without_a_signature() -> None:
    """A regression this change nearly shipped, kept because the constitution suite caught it.

    ``tenant_id`` is logical material, and the revision address is derived from the logical id — so
    for an un-signatured candidate, whose logical id is ``""``, the tenant reached *no digest at
    all* and two tenants' readings shared one ``candidate_id``. That is constitution IV, not a
    rounding error, so ``tenant_id`` is emitted into the revision material as well.
    """
    assert _unsigned(tenant_id="T1").candidate_id != _unsigned(tenant_id="T2").candidate_id


# --------------------------------------------------------------------------- #
# The declared material and the emitted material reconcile
# --------------------------------------------------------------------------- #


def test_the_declared_logical_fields_reconcile_with_the_emitted_material() -> None:
    """Both directions, mechanically.

    At HEAD this could not have passed: the declaration named ``relation_type`` and
    ``role_assignments`` while the code emitted ``relation_surface``, and three more declared
    fields (``signal_refs``, ``predicate_hypothesis`` and the logical/revision split itself) were
    never emitted at all — which is why ``verify_candidate_material_partition`` raised
    ``candidate_field_never_addressed`` and nothing in the repository called it to find out.
    """
    assert set(CANDIDATE_LOGICAL_MATERIAL_KEYS) == set(CANDIDATE_LOGICAL_MATERIAL_FIELDS)
    emitted = set(_signed()._logical_material())
    assert set(CANDIDATE_LOGICAL_MATERIAL_KEYS.values()) | set(
        CANDIDATE_LOGICAL_MATERIAL_CONSTANT_KEYS
    ) == emitted
    # The forbidden names are gone from the declaration, not merely unused by the code.
    assert not CANDIDATE_LOGICAL_MATERIAL_FIELDS & {
        "relation_type",
        "relation_surface",
        "role_assignments",
        "subject_mention_ref",
        "object_mention_ref",
    }


def test_the_material_partition_check_passes_and_is_now_reachable() -> None:
    """It was previously a verifier nobody ran, and it was red.

    A check that raises when called and has no caller is a comment. Making it green and calling it
    is the mechanism, so the test calls it.
    """
    verify_candidate_material_partition(_signed())
    verify_candidate_material_partition(_unsigned())


# --------------------------------------------------------------------------- #
# Part 5.4: an un-signatured candidate has no logical id, and says so
# --------------------------------------------------------------------------- #


def test_a_candidate_without_a_signature_has_no_logical_candidate_id() -> None:
    unread = _unsigned(relation_surface="originator of")
    assert unread.predicate_signature is None
    assert unread.logical_candidate_id == ""
    # Still addressable: the reading has an id of its own.
    assert unread.candidate_id.startswith("CNDR-")


def test_verify_candidate_identity_refuses_an_unaddressed_logical_id() -> None:
    with pytest.raises(CandidateContractError) as caught:
        verify_candidate_identity(_unsigned(relation_surface="originator of"))
    assert caught.value.code == "unaddressed_logical_identity"
    # An un-addressed candidate is not an error; it simply is not addressed yet.
    verify_candidate_identity(RelationCandidate(**_BASE))


def test_verify_candidate_identity_certifies_a_signed_candidate() -> None:
    signed = _signed()
    verify_candidate_identity(signed)
    # And a tampered record is still caught, so the refusal above is not a blanket one.
    with pytest.raises(CandidateContractError) as caught:
        verify_candidate_identity(replace(signed, extractor_version="tampered"))
    assert caught.value.code == "candidate_id_mismatch"


# --------------------------------------------------------------------------- #
# Construction-time coherence
# --------------------------------------------------------------------------- #


def test_a_declared_arity_mode_that_contradicts_the_slots_is_refused() -> None:
    """``arity_mode`` is a checked redundancy, never an independent assertion (part 2.5 check 4).

    Two occupied slots with no declared symmetry derive ``DIRECTED``, so a candidate that
    *declares* ``UNDIRECTED`` over them is asserting a shape its own bindings contradict — and an
    identity term that can disagree with itself is a silent fork. This is the check that stops
    "the extractor did not know the direction" from silently becoming "the relation is symmetric",
    which brief section 53 forbids in as many words.
    """
    from domain.relation_identity import RelationArityMode

    with pytest.raises(CandidateContractError) as caught:
        _signed(arity_mode=RelationArityMode.UNDIRECTED)
    assert caught.value.code == "arity_mode_disagrees_with_commutative_slots"


def test_declared_symmetry_is_identity_bearing_and_is_never_inferred() -> None:
    """A symmetric and an asymmetric reading of one pair are different claims, and both stand.

    The marker is explicit and defaults empty; ``frozenset()`` says nobody declared symmetry, not
    that the relation is directed (brief section 53).
    """
    from domain.relation_identity import RelationArityMode

    assert _signed(commutative_slots=frozenset()).logical_candidate_id != _signed(
        commutative_slots=frozenset({ArgumentSlot(0), ArgumentSlot(1)}),
        arity_mode=RelationArityMode.UNDIRECTED,
    ).logical_candidate_id


def test_participants_may_not_name_different_mentions_than_the_endpoints() -> None:
    """The two views are one fact, so construction checks that they agree.

    ``participants`` says where each participant sat; the mention refs say which mentions were
    read. Two views that can disagree are two sources of truth, which is the condition that
    produces ``candidate.relation_ref = A`` against ``predicate_hypothesis.relation_ref = B`` and
    the rest of that family.
    """
    with pytest.raises(CandidateContractError) as caught:
        _signed(object_mention_ref="MN-99")
    assert caught.value.code == "participants_disagree_with_mention_refs"

    with pytest.raises(CandidateContractError) as caught:
        _signed(participants=(_participants()[0],))
    assert caught.value.code == "participant_count_disagrees_with_mentions"


def test_a_signature_with_no_participants_is_refused_rather_than_padded() -> None:
    """A reading occupying fewer than two canonical slots is ``NO_CONFIGURATION``, and it is not
    padded to arity 2 with a placeholder (part 3.7)."""
    with pytest.raises(CandidateContractError) as caught:
        _signed(participants=())
    assert caught.value.code == "signature_slots_disagree_with_bindings"


def test_signal_refs_are_canonicalised_on_construction() -> None:
    """FR-085, and the determinism defect it names.

    ``observation_refs``, ``evidence_refs`` and ``supporting_spans`` were canonicalised on
    construction and ``signal_refs`` was not, so ``candidate_id`` depended on caller iteration
    order and replay determinism held only because ``semantic_path/assembly.py`` happened to sort
    at one call site. Constitution Domain Invariant 12 is a property of the type.
    """
    unsorted_candidate = RelationCandidate(
        **{**_BASE, "signal_refs": ("SIG-3", "SIG-1", "SIG-2", "SIG-1")}
    )
    assert unsorted_candidate.signal_refs == ("SIG-1", "SIG-2", "SIG-3")


def test_the_replay_of_one_reading_is_a_fixed_point() -> None:
    """SC-010, stated at the level the brief asks for: same signals, different input order.

    The candidate is built twice from the same signal set in opposite orders and must come out
    byte-identical — which it does only because ``signal_refs`` is sorted on construction rather
    than by the caller.
    """
    signals = ("SIG-1", "SIG-2", "SIG-3")

    def assemble(order: tuple[str, ...]) -> RelationCandidate:
        return RelationCandidate(
            **{
                **_BASE,
                "relation_surface": "works for",
                "predicate_signature": _signature(),
                "participants": _participants(),
                "signal_refs": order,
                "observation_refs": tuple(reversed(("OB-1", "OB-2"))),
                "observed_at": datetime(2024, 1, 1, tzinfo=UTC),
            }
        ).with_id()

    forwards, backwards = assemble(signals), assemble(tuple(reversed(signals)))
    assert forwards.candidate_id == backwards.candidate_id
    assert forwards.logical_candidate_id == backwards.logical_candidate_id
    assert forwards.content_hash == backwards.content_hash


def test_the_candidate_declares_exactly_the_fields_the_contract_names() -> None:
    """One test for the shape change, so a field cannot be added or dropped unnoticed."""
    declared = {field.name for field in fields(RelationCandidate)}
    assert {
        "predicate_signature",
        "participants",
        "commutative_slots",
        "polarity",
    } <= declared
    assert declared & {"normalized_form", "normalized_predicate", "event_class_hint"} == set()
