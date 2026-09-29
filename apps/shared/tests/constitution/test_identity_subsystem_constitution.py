"""The identity subsystem's constitutional properties, as distinct from its unit rules.

``test_predicate_signature.py`` pins the *rules*: one test per normalisation rule, one per
row of the construction table, one per step of the ordering. This file pins the things that
are about the constitution rather than about any one rule, and that therefore cannot be
asserted from inside the subsystem:

* **INV-IDENTITY** - changing the mapping vocabulary does not change the historical logical
  identity of an already-extracted relational observation. A docstring is not a mechanism, so
  the mechanism is a static import-edge check plus a demonstration over a swapped apparatus.
* **Domain Invariant 12** - determinism under replay. Checked by reading the source, because
  the failure mode (``uuid4``, ``datetime.now``, a dict-order dependence) is invisible in a
  functional test that happens to pass.
* **The identity/mapping boundary** - one sentence, and the import graph that enforces it.
* **The live blockers that remain** at the *claim* layer: ``relation_identity.py``'s
  ``UNDIRECTED`` branch sorts by mention-id text through a ``set``, and
  ``RelationRoleBinding.role`` is free text, so ``purchaser`` vs ``buyer`` still forks an
  ``RL-`` id there. Both are the same shapes this wave removed at the candidate layer, and both
  are a claim-layer migration rather than a code fix: changing them re-keys every stored
  ``RL-``/``RC-`` id, and no data migration is this wave's to write. They are **tripwired**, so
  the report cannot quietly go stale.

The two candidate-layer blockers this file used to carry — a predicate surface synthesised from
the mapping target, and an identity that keyed on the raw surface — are **resolved**. Their
tripwires went red when they were fixed and were deleted; their content now lives, inverted, in
``apps/shared/tests/unit/test_candidate_logical_identity.py``.

Every assertion here is static or structural on purpose: the constitutional claims are about
what *cannot* be reached, and the only way to show that is to enumerate the paths.
"""

from __future__ import annotations

import ast
import inspect
from dataclasses import dataclass, fields, replace
from pathlib import Path
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
    PredicateSignature,
    RoleBinding,
    SignatureContractError,
    canonical_participant_ordering,
    logical_candidate_id,
    logical_candidate_material,
)
from domain.relation_identity import canonical_material, digest128

pytestmark = pytest.mark.unit

_DOMAIN = Path(__file__).resolve().parents[2] / "domain"

#: The two modules this wave owns. Named as data so the checks below cannot drift onto
#: some other file and pass there.
_IDENTITY_MODULES = ("predicate_signature.py", "predicate_voice.py")

#: Anything whose *existence* in an import path would make the mapping layer an input to
#: identity. A registry, a regime, a type pack, a relation catalogue, or the modules that
#: define them.
_FORBIDDEN_IMPORT_ROOTS = frozenset(
    {
        "semantic",
        "relation_candidate",
        "relation_claim",
        "predicate_hypothesis",
        "relation_schema",
        "entity",
        "entity_identity",
        "graph_invariant",
    }
)

#: Module-local names whose presence in the identity path would reintroduce a
#: non-determinism source. Constitution Domain Invariant 12, and SC-010.
_FORBIDDEN_CALLS = frozenset(
    {"uuid4", "uuid1", "now", "utcnow", "time", "random", "shuffle", "token"}
)


@dataclass(frozen=True, slots=True)
class Mention:
    """The six fields the fingerprint reads, plus nothing a fingerprint may read."""

    surface: str
    kind: str = "entity"
    capture_ref: str = "CAP-1"
    segment_ref: str = "SEG-1"
    start: int = 0
    end: int = 0
    mention_id: str = "MN-0001"
    type_ref: str = ""
    confidence: float = 0.0
    producer_ref: str = ""
    argument_shape: str = ""
    extra: dict[str, Any] | None = None


def _tree(module_name: str) -> ast.Module:
    return ast.parse((_DOMAIN / module_name).read_text(encoding="utf-8"))


def _imported_modules(module_name: str) -> set[str]:
    imported: set[str] = set()
    for node in ast.walk(_tree(module_name)):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    return imported


def _called_names(module_name: str) -> set[str]:
    called: set[str] = set()
    for node in ast.walk(_tree(module_name)):
        if isinstance(node, ast.Call):
            function = node.func
            if isinstance(function, ast.Name):
                called.add(function.id)
            elif isinstance(function, ast.Attribute):
                called.add(function.attr)
    return called


def _signature(lemma: str = "acquire", arity: int = 2) -> PredicateSignature:
    markers = (ArgumentMarker.NOMARK,) * arity
    return PredicateSignature(
        language="en",
        predicate_lemma=lemma,
        construction_frame=ConstructionFrame.VERB_ACTIVE_TRANSITIVE,
        argument_markers=markers,
        canonical_argument_slots=tuple(ArgumentSlot(index) for index in range(arity)),
        voice_normalization_version=VOICE_NORMALIZATION_VERSION,
        predicate_normalization_version=PREDICATE_NORMALIZATION_VERSION,
    )


def _participants(arity: int = 2) -> list[ParticipantBinding]:
    return [
        ParticipantBinding(
            role=RoleBinding(
                surface_role="the words the observation used",
                role_hypothesis="",
                canonical_argument_slot=ArgumentSlot(index),
                normalization_version=VOICE_NORMALIZATION_VERSION,
            ),
            mention=Mention(surface=f"participant-{index}", start=index * 10, end=index * 10 + 5),
        )
        for index in range(arity)
    ]


# --------------------------------------------------------------------------- #
# INV-IDENTITY
# --------------------------------------------------------------------------- #


def test_the_identity_subsystem_imports_no_mapping_artefact() -> None:
    """The boundary, enforced as an import graph rather than asserted in prose.

    ``INV-IDENTITY`` holds *because* the mapping is not an input. The residual of that is
    silent - a field computed from a registry, and ``event_class_hint`` was exactly that
    shape - so the check is the import edge, not a review convention.
    """
    for module_name in _IDENTITY_MODULES:
        imported = _imported_modules(module_name)
        offenders = {
            name for name in imported if name.split(".")[0] in _FORBIDDEN_IMPORT_ROOTS
        }
        assert offenders == set(), f"{module_name} imports {sorted(offenders)}"
        assert not any("regime" in name for name in imported), module_name
        assert not any("vocab" in name or "registry" in name for name in imported), module_name


def test_the_identity_subsystem_reads_no_mapping_artefact_by_attribute() -> None:
    """The same claim for attribute access, because ``import module`` hides the other half.

    A lookup like ``REGISTRY[lemma]`` or ``SEMANTIC_REGIME.ref`` would be an import the
    static check above cannot see, and it is precisely the shape that would make a
    signature's predicate term a function of the vocabulary.
    """
    forbidden_attributes = {
        "RelationRef",
        "relation_ref",
        "relation_type",
        "resolution_state",
        "semantic_regime",
        "regime_ref",
        "vocabulary_version",
        "type_pack",
        "registry",
        "lookup",
        "resolve",
    }
    for module_name in _IDENTITY_MODULES:
        attributes = {
            node.attr for node in ast.walk(_tree(module_name)) if isinstance(node, ast.Attribute)
        }
        offenders = attributes & forbidden_attributes
        assert not offenders, f"{module_name}: {sorted(offenders)}"


def test_mapping_swap_leaves_every_derived_logical_id_unchanged() -> None:
    """``INV-IDENTITY`` demonstrated, steps 1-4 of part 5.3.

    The whole mapping apparatus is replaced - a different operator catalogue, a different
    regime configuration, a different type pack - and every derived id is unchanged, along
    with the count of distinct ids and the partition they induce. Step 5 (a *changed*
    ``candidate_id``) needs ``RelationCandidate`` and is reported as blocked; see
    ``test_the_candidate_surface_synthesised_from_the_mapping_target_is_a_known_blocker``.
    """
    from semantic.contracts import RelationRef

    signature = _signature()
    participants = _participants()
    corpus = [
        (signature, participants),
        (_signature(lemma="acquire"), _participants()),
        (_signature(lemma="sell"), _participants()),
        (_signature(lemma="control"), _participants()),
    ]

    def derived() -> list[str]:
        return [
            logical_candidate_id(item_signature, item_participants, tenant_id="tenant-a")
            for item_signature, item_participants in corpus
        ]

    before = derived()
    catalogue_before = {RelationRef("acquisition", "1"), RelationRef("owns", "1")}
    regime_before = {"threshold": 0.5, "operator": RelationRef("acquisition", "1")}
    type_pack_before = {"acme": "core:Organization", "john": "core:Person"}

    catalogue_after = {RelationRef("control", "9"), RelationRef("acquire", "4")}
    regime_after = {"threshold": 0.95, "operator": RelationRef("control", "9")}
    type_pack_after = {"acme": "ext:Vendor", "john": "ext:Individual"}

    after = derived()

    # The apparatus really was different, and the apparatus is not an argument.
    assert catalogue_before != catalogue_after
    assert regime_before != regime_after
    assert type_pack_before != type_pack_after
    assert set(inspect.signature(logical_candidate_id).parameters).isdisjoint(
        {"catalogue", "regime", "type_pack", "relation_ref"}
    )
    # Step 4: every id unchanged, the count unchanged, the partition unchanged.
    assert after == before
    assert len(set(after)) == len(set(before))
    partition_before = {candidate_id: before.count(candidate_id) for candidate_id in set(before)}
    partition_after = {candidate_id: after.count(candidate_id) for candidate_id in set(after)}
    assert partition_after == partition_before


def test_mapping_change_moves_candidate_id_and_not_logical_candidate_id() -> None:
    """Step 5 in isolation, in the only form this wave can express.

    The mapping is not an input, so it cannot move the logical id - and that is enforced
    by the *signature of the function*, not by a convention: passing a mapping keyword is
    a ``TypeError``, so there is no call at all that could include one. That a *new
    reading* of the same hypothesis is recorded elsewhere is ``RelationCandidate``'s
    revision material, and is not simulated here: a test that constructed a fake revision
    to prove it would be asserting the fake, not the code.
    """
    signature = _signature()
    participants = _participants()
    before = logical_candidate_id(signature, participants, tenant_id="tenant-a")
    for leaked in (
        "relation_ref",
        "relation_type",
        "resolution_state",
        "schema_version",
        "predicate_hypothesis",
        "semantic_regime_ref",
    ):
        with pytest.raises(TypeError):
            logical_candidate_id(
                signature, participants, tenant_id="tenant-a", **{leaked: "anything"}
            )
    assert logical_candidate_id(signature, participants, tenant_id="tenant-a") == before



# --------------------------------------------------------------------------- #
# The material, exactly
# --------------------------------------------------------------------------- #


def test_logical_material_key_set_is_exact() -> None:
    """Part 5.1: exactly seven keys, and the projection under one of them.

    Sibling of brief section 94's six-symbol import test, and the static half of the
    mutation guard below. A key added without a decision is a decision nobody made.
    """
    material = logical_candidate_material(
        _signature(), _participants(), tenant_id="tenant-a", polarity="asserted"
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
    assert set(material["predicate_signature"]) == {
        field.name for field in fields(PredicateSignature)
    }
    assert material["identity_schema"] == IDENTITY_SCHEMA_VERSION
    assert isinstance(material["commutative_slots"], list)
    assert all(isinstance(token, str) for token in material["commutative_slots"])


def test_mutation_relation_ref_in_logical_material_fails() -> None:
    """The mutation guard. Add ``relation_ref.relation_type`` to the material and this
    fails; add a parameter carrying it and this fails too.

    Brief section 94, verbatim: "This is essential because otherwise someone will
    reintroduce the old FR-040 violation in six months."
    """
    material = canonical_material(
        logical_candidate_material(_signature(), _participants(), tenant_id="tenant-a")
    )
    for mapping_key in (
        "relation_ref",
        "relation_type",
        "schema_version",
        "resolution_state",
        "alternative_refs",
        "mapping_evidence_refs",
        "semantic_regime_ref",
    ):
        assert f'"{mapping_key}"' not in material
    parameters = set(inspect.signature(logical_candidate_id).parameters)
    assert not parameters & {"relation_ref", "relation_type", "predicate_hypothesis"}
    # And the projection itself, which is the only predicate term, carries no mapping key.
    assert not set(_signature().identity_projection()) & {
        "relation_ref",
        "relation_type",
        "event_class_hint",
        "resolution_state",
    }


def test_no_caller_order_reaches_the_logical_id() -> None:
    """Every collection in the material is emitted in canonical order, so a caller's
    iteration order cannot reach the id.

    This is the defect ``relation_candidate.py:1180-1205`` and ``assembly.py`` currently
    leave to a hand-sort at one call site: determinism that holds only because one
    particular caller remembered.
    """
    trinary = _signature(lemma="sell", arity=3)
    participants = _participants(3)
    every_slot_commutative = frozenset({ArgumentSlot(0), ArgumentSlot(1), ArgumentSlot(2)})
    permutations = (
        participants,
        list(reversed(participants)),
        [participants[2], participants[0], participants[1]],
        [participants[1], participants[2], participants[0]],
    )
    materials = {
        canonical_material(
            logical_candidate_material(
                trinary,
                order,
                tenant_id="tenant-a",
                commutative_slots=every_slot_commutative,
            )
        )
        for order in permutations
    }
    assert len(materials) == 1
    ordering = canonical_participant_ordering(trinary, every_slot_commutative, participants)
    assert [participant.slot.index for participant in ordering] == [0, 1, 2]


def test_candidate_without_a_signature_has_no_logical_candidate_id() -> None:
    """Part 5.4: the signature is required, and there is no surface-keyed fallback.

    ``verify_candidate_identity()`` refusing an unaddressed logical id is
    ``RelationCandidate``'s half and is reported as blocked; the half this wave owns is
    that the material cannot even be built without a signature.
    """
    participants = _participants()
    with pytest.raises(SignatureContractError) as caught:
        logical_candidate_id(None, participants, tenant_id="tenant-a")
    assert caught.value.code == "unaddressed_logical_identity"
    assert "verify_candidate_identity" in caught.value.message


def test_verify_candidate_identity_refuses_an_unaddressed_logical_id() -> None:
    """The named test, in the form the current code admits.

    The refusal code ``unaddressed_logical_identity`` is *this* wave's, and it is
    reachable here. The candidate-level twin - a stored candidate whose
    ``logical_candidate_id`` is ``""`` - cannot be written until the candidate carries a
    signature, which is part 7's change and out of scope here; the assertion below pins
    the code name so the two halves cannot diverge when it lands.
    """
    with pytest.raises(SignatureContractError) as caught:
        logical_candidate_material(None, _participants(), tenant_id="tenant-a")
    assert caught.value.code == "unaddressed_logical_identity"
    # An unaddressed reading has no id at all, and the platform's own material never
    # carries one: the prefix is added only by the deriving function.
    material = logical_candidate_material(_signature(), _participants(), tenant_id="a")
    assert not any(
        isinstance(value, str) and value.startswith("CAND-") for value in material.values()
    )



# --------------------------------------------------------------------------- #
# Domain Invariant 12: determinism
# --------------------------------------------------------------------------- #


def test_replay_is_a_fixed_point_and_no_clock_or_random_source_is_reachable() -> None:
    """SC-010. Read from the source, because a functional test cannot see a ``uuid4`` in
    a branch it does not take."""
    for module_name in _IDENTITY_MODULES:
        called = _called_names(module_name)
        offenders = called & _FORBIDDEN_CALLS
        assert not offenders, f"{module_name} calls {sorted(offenders)}"
        imported = _imported_modules(module_name)
        assert not {"random", "secrets", "uuid", "time", "datetime"} & imported, module_name

    signature = _signature()
    participants = _participants()
    ids = {
        logical_candidate_id(signature, participants, tenant_id="tenant-a") for _ in range(25)
    }
    assert len(ids) == 1
    # The same function twice over the same value, in a fresh process-local dict order.
    assert canonical_material(logical_candidate_material(
        signature, participants, tenant_id="tenant-a"
    )) == canonical_material(logical_candidate_material(
        signature, dict(enumerate(participants)).values(), tenant_id="tenant-a"
    ))


def test_the_lemma_table_is_a_mapping_and_not_a_row_type() -> None:
    """``Mapping[str, str]`` is the whole of the type. There is no row that maps one base
    lemma onto a different base lemma, so the forbidden table has nowhere to live."""
    assert not hasattr(LEMMA_TABLE, "append")
    assert all(
        isinstance(surface, str) and isinstance(lemma, str)
        for surface, lemma in LEMMA_TABLE.items()
    )
    assert digest128(canonical_material(sorted(LEMMA_TABLE.items()))) == LEMMA_TABLE_DIGEST
    # Every value is a lemma the inventory or a pin declares; nothing new is introduced,
    # which is what makes a cross-lemma fold unrepresentable.
    assert set(LEMMA_TABLE.values()) <= set(LEMMA_INVENTORY) | set(
        PINNED_IRREGULAR_FORMS.values()
    )



def test_one_normaliser_and_one_lemma_table_in_the_identity_subsystem() -> None:
    """Part 1.6: there is exactly one normaliser in the platform, and it is versioned.

    Counted as *definitions* rather than as a name, so a second implementation under
    another name is still caught.
    """
    defined: dict[str, set[str]] = {}
    for module_name in _IDENTITY_MODULES:
        names = {
            node.name
            for node in ast.walk(_tree(module_name))
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        }
        defined[module_name] = names
    assert {name for name in defined["predicate_signature.py"] if "normalize" in name} == {
        "normalize_surface_for_fingerprint",
    }
    assert {name for name in defined["predicate_voice.py"] if "normalize" in name} == {
        "normalize_predicate",
        "normalize_voice",
    }
    lemmas = [
        node
        for module_name in _IDENTITY_MODULES
        for node in ast.walk(_tree(module_name))
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id.startswith("LEMMA_TABLE")
            for target in node.targets
        )
    ]
    assert lemmas, "the committed lemma table must exist"


# --------------------------------------------------------------------------- #
# The live blockers: the CLAIM layer
# --------------------------------------------------------------------------- #
#
# Both blockers below were tripwires when the candidate layer still carried this wave's defects.
# They are re-pointed at the claim layer, which has the same two shapes and is not this file's to
# change: ``logical_material`` sorts ``UNDIRECTED`` members by mention-id text through a ``set``,
# and ``RelationRoleBinding.role`` is free text. See the report's items 4 and 5, and
# ``data-model.md`` part 4.7 items 1-4 plus ``repair/A2-identity-subsystem.md`` U8.
#
# The two candidate-layer tripwires this file used to carry —
# ``test_the_candidate_surface_synthesised_from_the_mapping_target_is_a_known_blocker`` and
# ``test_the_candidate_identity_still_keys_on_the_raw_surface`` — went red when their blockers were
# fixed and were deleted. Their content now lives, inverted, in
# ``apps/shared/tests/unit/test_candidate_logical_identity.py``:
# ``test_the_mapping_target_no_longer_supplies_a_surface``,
# ``test_the_mapping_target_is_never_read_as_the_predicate_term`` and
# ``test_the_surface_is_not_reachable_from_the_material``.


def test_the_claim_layer_role_binding_is_still_free_text() -> None:
    """Part 4.7 item 4, recorded and not applied: ``RelationRoleBinding.role`` is free
    text, so ``purchaser`` vs ``buyer`` still forks an id at the *claim* layer.

    Owned by the claim layer, not by this wave, and A2 U8 records the same boundary. The
    tripwire keeps the deferred item visible.
    """
    from domain.relation_claim import RelationRoleBinding

    role_fields = {field.name: field.type for field in fields(RelationRoleBinding)}
    assert "role" in role_fields
    assert "canonical_argument_slot" not in role_fields
    binding = RelationRoleBinding(role="purchaser", member_ref="ENT-A")
    assert binding.role == "purchaser"


def test_the_existing_undirected_branch_still_sorts_by_mention_id_text() -> None:
    """Part 4.7 items 1-3, recorded and not applied.

    ``domain.relation_identity.logical_material`` still sorts ``sorted({str(p) for p in
    participants})`` - by mention-id text, and through a ``set``, so it deduplicates. The
    replacement is specified in part 4.1 and implemented in
    :func:`canonical_participant_ordering`; wiring it into the claim layer changes every
    stored ``RL-`` id and needs the claim-layer owner's field split (item 4), which A2 U8
    puts outside this job's ownership. The tripwire keeps the deferral visible.
    """
    from domain.relation_identity import logical_material

    material = logical_material("undirected", "co_occurs_with", ("ENT-B", "ENT-A", "ENT-A"))
    assert material["members"] == ["ENT-A", "ENT-B"]
    assert logical_material("directed", "works_for", ("ENT-B", "ENT-A"))["subject"] == "ENT-B"
    # The replacement does the two things the old branch cannot: it preserves multiplicity
    # and it orders by a slot rather than by a mention-id text sort.
    signature = _signature()
    participants = [
        replace(participant, mention=replace(participant.mention, mention_id=""))
        for participant in _participants()
    ]
    ordering = canonical_participant_ordering(signature, frozenset(), participants)
    assert len(ordering) == 2
    assert [participant.slot.index for participant in ordering] == [0, 1]
