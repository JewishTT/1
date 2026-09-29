"""Phase 4A: the signal contract is natively n-ary, names its basis, and has a polarity.

Feature 021, spec FR-008, FR-009, FR-012, FR-013, FR-014, FR-015;
``data-model.md`` part 6; brief §16 (``input.md:1111-1137``);
``repair/ARBITRATION.md`` §5, §6, §14 rule 5; ``repair/A7-migration-021.md`` D2.2–D2.3.

**What this file is for.** Phase 4A is additive, and an additive phase is easy to get wrong in
the one direction that matters: it passes because nothing broke, and the thing it was supposed
to add is quietly absent. Three defects lived here before it, and all three were invisible to
the 256 tests that existed:

1. A signal could hold two mentions, so a four-slot reading parked two participants in
   ``extra`` — a bag no contract, no validation and no identity could see.
2. ``extra`` is excluded from ``_material()``, so two signals differing *only* in declared
   arity collapsed onto one ``signal_id``. A four-ary relation and a binary one over the same
   two mentions were one address.
3. ``signal_asserts_nothing`` required ``relation_surface != '' or relation_ref is not None``,
   which made a surface-less ``CO_OCCURRENCE`` — the platform noticing two mentions near each
   other and declining to name it — structurally impossible to record.

So every test here is written to fail on the pre-4A code, and one of them is a **mutation
test** that removes ``participants`` from the address material and asserts the arity test goes
red. A test that has never failed has never been examined; that is the standard this repo
already holds its constitutional suite to (``test_constitution_has_teeth.py``), and this file
holds its own new guarantees to the same one.

**Nothing was removed in 4A, and three things prove it.** The two scalar endpoint accessors
still read and still construct; ``SignalKind`` still has all fourteen members; and the old
``signal_asserts_nothing`` refusal still fires for the case it was written for — a signal that
named no basis and supplied no words. What narrowed is that a signal which **does** say how it
looked may now have no words at all.
"""

from __future__ import annotations

import dataclasses
import inspect
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest
from domain.mention_occurrence_index import mint_capture_address
from domain.predicate_hypothesis import PredicateHypothesis
from domain.predicate_signature import ArgumentSlot, Polarity
from domain.relation_candidate import SpanRef
from domain.relation_participant import (
    MIN_PARTICIPANTS,
    ParticipantContractError,
    ParticipantEndKind,
    RelationParticipant,
    binary_participants,
)
from domain.signal_basis import (
    MAX_BASIS_TOKEN_LENGTH,
    SIGNAL_BASES,
    SIGNAL_BASES_REQUIRING_PREDICATE_WORDS,
    SignalBasis,
)

from extractors.signals.signal import (
    Neighbourhood,
    RelationSignal,
    SignalContractError,
    SignalKind,
)

pytestmark = pytest.mark.unit

_TENANT = "tenant-a"

#: ``apps/`` — the root the service packages hang off.
APPS = Path(__file__).resolve().parents[2]
INTERPRETATION = APPS / "interpretation"
#: Everything a mutated child run has to import. ``extractors`` needs ``domain`` and
#: ``parsers``; ``domain`` needs ``semantic`` and ``contracts.py``.
_COPIED = (
    ("interpretation", ("extractors", "parsers", "semantic", "contracts.py")),
    ("shared", ("domain",)),
)


def _neighbourhood() -> Neighbourhood:
    return Neighbourhood(
        characters_scanned=42, pairs_considered=0, scope_read="one clause of running text"
    )


def _participant(index: int, *, role: str = "", confidence: float = 0.0) -> RelationParticipant:
    return RelationParticipant(
        mention_ref=f"MN-{index}",
        slot=ArgumentSlot(index),
        role_hypothesis=role,
        ordinal=index,
        confidence=confidence,
    )


def _signal(**over: Any) -> RelationSignal:
    base: dict[str, Any] = {
        "kind": SignalKind.SYNTAX,
        "relation_surface": "sold to",
        "neighbourhood": _neighbourhood(),
        "participants": binary_participants("MN-A", "MN-B"),
        "basis": SignalBasis.EVENT_FRAME,
        "producer_ref": "syntactic/pinned-shallow-clause",
        "context_ref": "CTX-1",
        "semantic_regime_ref": "REG-1",
        "tenant_id": _TENANT,
    }
    return RelationSignal(**{**base, **over})


# --------------------------------------------------------------------------- #
# D1 — native variadic participants
# --------------------------------------------------------------------------- #


def test_the_participant_field_set_is_exactly_seven_fields() -> None:
    """FR-009 names five; FR-012, FR-050 and FR-066 need a sixth, and Phase 4C needed a seventh.

    ``ARBITRATION.md`` §14 rule 5 left three conflicting field lists unresolved. 4A resolved
    them: the union was **six**, and ``argument_shape`` is the field the other list carries.

    **The seventh is ``end_kind``, and it is a different kind of necessity.** The sixth closed a
    *requirement* that had nowhere to go (FR-012's ``QUANTITY`` mapping). The seventh closes a
    *type confusion* C4 had to answer: :attr:`mention_ref` addresses one of two namespaces - a
    ``surface@…`` occurrence the mention layer resolves to an ``MN-``, or a ``capture:<ref>``
    retrieval that is already a durable ``CAP-`` - and until 4C nothing on the participant said
    which, so the binder had to guess from the string. The decision and the rejected
    alternative (a first-class document mention, which would put a second id on one fact and
    have no position to be a mention at) are on
    :class:`domain.relation_participant.ParticipantEndKind`.

    The set is the test that notices a field appearing without a requirement naming it, and it
    will.
    """
    assert [f.name for f in dataclasses.fields(RelationParticipant)] == [
        "mention_ref",
        "slot",
        "role_hypothesis",
        "ordinal",
        "confidence",
        "argument_shape",
        "end_kind",
    ]
    participant = _participant(0)
    assert participant.argument_shape == "entity", (
        "the default shape asserts an ordinary referent; it is a claim, not a blank"
    )
    # And the seventh defaults to *inferred*, not to a value: `None` means "read the address",
    # because the address already says which namespace it is in.
    assert participant.end_kind is ParticipantEndKind.OCCURRENCE
    assert RelationParticipant(
        mention_ref=mint_capture_address("CAP-1"), slot=ArgumentSlot(0)
    ).end_kind is ParticipantEndKind.RETRIEVAL


def test_the_slot_is_structural_and_a_bare_role_name_is_refused() -> None:
    """The reason ``slot`` exists: two producers guessing different role names must agree.

    ``slot`` is an :class:`ArgumentSlot`, so "seller" and "vendor" cannot both be written
    into the identity term. ``role_hypothesis`` is where a free-text guess lives, and it is
    evidence only — see :meth:`RelationParticipant.to_identity`.
    """
    with pytest.raises(ParticipantContractError) as excinfo:
        RelationParticipant(mention_ref="MN-A", slot="seller")  # type: ignore[arg-type]
    assert excinfo.value.code == "participant_slot_type"
    # A free-text guess is still allowed, as evidence: it is excluded from the address, not
    # from the record. A reader may find it useful; no identity term may depend on it.
    guessed = RelationParticipant(
        mention_ref="MN-A", slot=ArgumentSlot(0), role_hypothesis="seller"
    )
    assert guessed.role_hypothesis == "seller"
    assert "role_hypothesis" not in guessed.to_identity()


def test_role_hypothesis_confidence_and_argument_shape_stay_out_of_the_address() -> None:
    """A2 D4.3's exclusions, asserted on the real projection rather than on a docstring.

    Each of the three has a stated reason for being out, and each is a different failure if it
    creeps back in: a role name forks one reading into two on a spelling difference, a
    confidence change re-keys a relation on every re-scoring pass, and a shape reclassification
    couples the type layer's edits to the relation layer's digest.
    """
    reference = _signal(participants=tuple(_participant(i) for i in range(3)))
    for field in ("role_hypothesis", "confidence", "argument_shape"):
        restated = tuple(
            RelationParticipant(
                mention_ref=p.mention_ref,
                slot=p.slot,
                role_hypothesis="seller" if field == "role_hypothesis" else p.role_hypothesis,
                ordinal=p.ordinal,
                confidence=0.99 if field == "confidence" else p.confidence,
                argument_shape="value" if field == "argument_shape" else p.argument_shape,
            )
            for p in reference.participants
        )
        mutated = _signal(participants=restated)
        assert mutated.participants != reference.participants, f"{field} was not applied"
        assert mutated.signal_id == reference.signal_id, (
            f"{field} reached the address material. It is a projection or a referent fact, and "
            "putting it in the identity term is the defect A2 D4.3 enumerates"
        )


@pytest.mark.parametrize("arity", [2, 3, 4, 5])
def test_nary_signals_round_trip_losslessly(arity: int) -> None:
    """build → store → read → an **identical object**, at every arity the contract allows.

    The whole record, not just the ends: ``role_hypothesis``, ``confidence``,
    ``argument_shape`` and ``end_kind`` are the fields a lossy round trip would drop, and
    FR-008's obligation is losslessness. ``signal_id`` is re-derived on the way back and must
    land on the same address, because a record that rebuilds to a different object is a record
    whose stored reference now points at something nobody recorded.

    ``end_kind`` is the Phase 4C one and it is the field most likely to be dropped, because
    every ``MN-`` participant infers the same value and an inferred field looks free. It is
    not: an end whose kind is lost on a round trip re-infers correctly here only by luck, and a
    ``capture:`` end silently reclassified as an occurrence would be sent to the mention layer
    to be refused there.
    """
    original = _signal(participants=tuple(_participant(i) for i in range(arity)))
    restored = RelationSignal.from_dict(original.to_dict())
    assert restored == original
    assert restored.signal_id == original.signal_id
    assert restored.arity == arity
    assert [p.mention_ref for p in restored.participants] == [
        f"MN-{i}" for i in range(arity)
    ]
    # The record carries the full projection; the address is taken over the narrow one.
    assert original.to_dict()["participants"][0] == {
        "mention_ref": "MN-0",
        "slot": {"index": 0},
        "role_hypothesis": "",
        "ordinal": 0,
        "confidence": 0.0,
        "argument_shape": "entity",
        "end_kind": "occurrence",
    }
    assert original._material()["participants"][0] == {
        "mention_ref": "MN-0",
        "slot": "A0",
        "ordinal": 0,
    }


def test_arity_below_two_is_refused_with_a_named_code() -> None:
    """A one-participant reading states a property of one thing, not a relation.

    The named code matters more than the refusal: ``signal_arity_below_two`` can be counted by
    reason, so a corpus answer to "how much of what we read is not a relational configuration"
    is a number rather than a silence (A2 D3.7, ``NO_CONFIGURATION``).
    """
    with pytest.raises(SignalContractError) as excinfo:
        _signal(participants=(_participant(0),))
    assert excinfo.value.code == "signal_arity_below_two"
    assert str(MIN_PARTICIPANTS) in str(excinfo.value)


def test_a_signal_with_no_ends_at_all_is_refused() -> None:
    """The only remaining shape that supplies no end, and it is refused with 4A's code.

    ``signal_asserts_nothing`` is not what refuses this one, and that is worth pinning: the
    4A narrowing moved the *basis*, not the floor on naming an end. Phase 4B removed the
    scalar constructor parameters, so ``participants`` is a required argument and omitting it
    is a :class:`TypeError` from the generated ``__init__`` — the refusal below is what a
    caller who *passes* an empty tuple gets, and the test pins that it is still a named
    refusal rather than a signal with no ends in it.
    """
    with pytest.raises(TypeError):
        RelationSignal(  # type: ignore[call-arg]
            kind=SignalKind.CO_OCCURRENCE,
            relation_surface="adjacent",
            neighbourhood=_neighbourhood(),
            tenant_id=_TENANT,
        )
    with pytest.raises(SignalContractError) as excinfo:
        _signal(participants=())
    assert excinfo.value.code == "signal_mentions_required"
    assert "Phase 4B" in str(excinfo.value)


def test_the_binary_accessors_are_derived_over_the_canonical_tuple() -> None:
    """FR-008: the two scalars survive as derived properties and nothing else.

    There is no longer an "old construction path" to agree with - Phase 4B deleted it, which
    is the point of the deletion: a second way to build a signal is a second way for the
    record and the address to disagree. So the property is asserted against the tuple it
    reads, and the absence of the constructor parameter is asserted separately by
    :func:`test_the_deprecated_endpoint_constructor_parameters_are_gone`. If the property ever
    stops being a projection of ``participants[0]``, this fails and the record is no longer
    derived from its own canonical representation.
    """
    signal = _signal(participants=binary_participants("MN-A", "MN-B"))
    assert signal.subject_mention_ref == "MN-A"
    assert signal.object_mention_ref == "MN-B"
    assert signal.subject_mention_ref == signal.participants[0].mention_ref
    assert signal.object_mention_ref == signal.participants[1].mention_ref
    assert [p.slot.token for p in signal.participants] == ["A0", "A1"]


def test_the_deprecated_endpoints_are_not_stored_fields() -> None:
    """Not fields and, since Phase 4B, not constructor parameters either.

    ``dataclasses.fields()`` not listing them is what makes ``test_the_address_is_derived_not_
    carried`` in the constitutional suite meaningful for a signal, and what keeps them out of
    any future ``asdict``-based serialisation as a second, conflicting copy. Since 4B they
    are also absent from the ``__init__`` signature, which is asserted in
    :func:`test_the_deprecated_endpoint_constructor_parameters_are_gone`.
    """
    field_names = [f.name for f in dataclasses.fields(RelationSignal)]
    assert "subject_mention_ref" not in field_names
    assert "object_mention_ref" not in field_names
    assert "participants" in field_names
    for name in ("subject_mention_ref", "object_mention_ref"):
        assert isinstance(getattr(RelationSignal, name), property)


def test_the_deprecated_endpoint_constructor_parameters_are_gone() -> None:
    """**The Phase 4B deletion, asserted on the mechanism rather than in a comment.**

    There is exactly one way to build a :class:`RelationSignal`. ``subject_mention_ref=`` and
    ``object_mention_ref=`` are not accepted, so the seven production sites that used them had
    to move onto ``participants=`` in the same commit, and no caller can drift back onto a path
    the platform no longer maintains. Both halves are asserted together because either alone
    is weak: a parameter that is accepted and ignored would keep the old spelling alive, and a
    parameter that is silently honoured is the second source of truth the deletion exists to
    remove.
    """
    parameters = inspect.signature(RelationSignal.__init__).parameters
    assert "subject_mention_ref" not in parameters
    assert "object_mention_ref" not in parameters
    assert "participants" in parameters
    with pytest.raises(TypeError):
        _signal(
            participants=binary_participants("MN-A", "MN-B"),
            subject_mention_ref="MN-A",  # type: ignore[call-arg]
        )


def test_no_derived_property_shadows_a_field_default() -> None:
    """The trap :func:`_install_derived_endpoint_accessors` exists for, re-asserted.

    ``@dataclass`` reads a field's default off the class attribute of the same name, so a
    ``@property`` declared in the class body under a field's name *becomes* that field's
    default. A signal would then come out with a participant whose ``mention_ref`` is
    ``'<property object at 0x...>'``: nothing raises, the record is well formed, the address is
    stable, and the mention it names does not exist. The two endpoint names are properties and
    no longer fields, so they are safe; this asserts the general property rather than the two
    names, so a future property added under a *field's* name fails here.
    """
    properties = {
        name
        for name, value in vars(RelationSignal).items()
        if isinstance(value, property)
    }
    field_names = {f.name for f in dataclasses.fields(RelationSignal)}
    assert not properties & field_names, (
        f"{sorted(properties & field_names)} are both a derived property and a stored field; "
        "@dataclass takes the default off the class attribute, so the property object would "
        "become the field's default and every signal on that field would carry a descriptor "
        "where a value belongs"
    )
    # And the two endpoint accessors are still data descriptors, so `getattr` finds them on
    # an instance and `dataclasses.replace` - which the registry's `_stamp` travels - reads
    # the derived values rather than raising.
    signal = _signal()
    assert isinstance(RelationSignal.subject_mention_ref, property)
    replaced = dataclasses.replace(signal, signal_id="")
    assert replaced.subject_mention_ref == signal.participants[0].mention_ref
    assert replaced.object_mention_ref == signal.participants[1].mention_ref
    assert replaced.signal_id == signal.signal_id, (
        "replace() must re-derive the same address: the endpoints are derived from the tuple "
        "and contribute nothing of their own"
    )


def test_one_mention_in_two_slots_is_a_self_connection() -> None:
    """The pre-4A rule generalised rather than duplicated.

    Before, only the two scalar ends were compared. With ``participants`` the rule has to
    cover every pair, because at arity 3 the repeat can be anywhere in the tuple and
    ``participants[0]`` vs ``participants[1]`` would miss it.
    """
    with pytest.raises(SignalContractError) as excinfo:
        _signal(
            participants=(
                _participant(0),
                _participant(1),
                RelationParticipant(mention_ref="MN-0", slot=ArgumentSlot(2)),
            )
        )
    assert excinfo.value.code == "signal_self_connection"


def test_a_participant_with_no_mention_is_refused() -> None:
    """An unnamed end is a lost end with no trace, so the code stays ``signal_mentions_required``."""
    with pytest.raises(ParticipantContractError) as excinfo:
        RelationParticipant(mention_ref="  ", slot=ArgumentSlot(0))
    assert excinfo.value.code == "participant_mention_required"


@pytest.mark.parametrize(
    "over,code",
    [
        ({"slot": "seller"}, "participant_slot_type"),
        ({"ordinal": -1}, "participant_ordinal_negative"),
        ({"ordinal": "first"}, "participant_ordinal_type"),
        ({"confidence": 1.5}, "participant_confidence_range"),
        ({"argument_shape": ""}, "participant_argument_shape_required"),
    ],
)
def test_every_participant_refusal_is_named(over: dict[str, Any], code: str) -> None:
    """A refusal nobody can count is a silent drop, so every one of these carries a code."""
    kwargs: dict[str, Any] = {"mention_ref": "MN-A", "slot": ArgumentSlot(0), **over}
    with pytest.raises(ParticipantContractError) as excinfo:
        RelationParticipant(**kwargs)
    assert excinfo.value.code == code


# --------------------------------------------------------------------------- #
# D2 — the observational basis
# --------------------------------------------------------------------------- #


def test_the_basis_vocabulary_is_exactly_the_nine_the_brief_names() -> None:
    """``input.md:1125-1137``, as the column values migration ``021`` stores.

    A7 D2.3 pins these nine literals into a CHECK constraint. If the domain enum and the
    migration's whitelist ever disagree, every signal with the extra basis is refused by the
    database and no test in this file would notice — so the set is pinned here from the brief.
    """
    assert [basis.value for basis in SIGNAL_BASES] == [
        "predicate_text",
        "dom_relation",
        "table_slot",
        "hyperlink",
        "citation",
        "proximity",
        "metadata_field",
        "event_frame",
        "attribute_key",
    ]
    assert len(SIGNAL_BASES) == 9
    # The column is sized from the longest token; a tenth basis could not be stored.
    assert max(len(basis.value) for basis in SIGNAL_BASES) <= MAX_BASIS_TOKEN_LENGTH
    assert SIGNAL_BASES_REQUIRING_PREDICATE_WORDS == {SignalBasis.PREDICATE_TEXT}


@pytest.mark.parametrize("basis", list(SIGNAL_BASES))
def test_every_basis_is_constructible(basis: SignalBasis) -> None:
    """All nine, with the words they claim. See the next test for the eight that need none."""
    signal = _signal(kind=SignalKind.CO_OCCURRENCE, basis=basis)
    assert signal.basis is basis
    assert signal.signal_id


@pytest.mark.parametrize(
    "basis", [b for b in SIGNAL_BASES if b not in SIGNAL_BASES_REQUIRING_PREDICATE_WORDS]
)
def test_the_eight_bases_without_predicate_words_are_constructible(basis: SignalBasis) -> None:
    """The acceptance case, and the test that **had** to fail before 4A.

    ``signal_asserts_nothing`` required ``relation_surface != '' or relation_ref is not None``,
    so every one of these constructions raised. The brief's example is verbatim —
    ``John Smith`` and ``Acme Corporation`` appearing together yields
    ``kind = CO_OCCURRENCE``, ``relation_surface = ""``, and calls that valid — and FR-013
    requires it to be constructible, persistable and assemblable.

    Eight and not nine, because :attr:`SignalBasis.PREDICATE_TEXT` is the one basis that
    obliges a surface and is refused without one, which
    ``test_predicate_text_with_no_words_is_still_refused`` asserts. A fix that special-cased
    proximity would pass the brief's example and leave the other seven impossible, which is
    why this is parameterised over the whole surface-less set.
    """
    signal = _signal(
        kind=SignalKind.CO_OCCURRENCE,
        relation_surface="",
        relation_ref=None,
        basis=basis,
    )
    assert signal.basis is basis
    assert signal.relation_surface == ""
    assert signal.relation_ref is None
    assert signal.arity == 2
    assert signal.signal_id
    # Legal with no words *and* legal with them: the basis widened what is permitted, it did
    # not make the surface optional for everyone.
    with_words = _signal(kind=SignalKind.CO_OCCURRENCE, basis=basis)
    assert with_words.relation_surface == "sold to"


def test_predicate_text_with_no_words_is_still_refused() -> None:
    """The one basis that obliges a surface, and why the obligation is arithmetic.

    "I read the words between the participants" with nothing to show for it is the only claim
    in the vocabulary that is impossible, so it is refused under its own name rather than
    under the old generic one. Every other basis can be observed with no predicate words at
    all — a table slot, a hyperlink, a citation, a metadata field, an event frame, an
    attribute key, a DOM relation, proximity — which is exactly why the rule is not the old
    one.
    """
    with pytest.raises(SignalContractError) as excinfo:
        _signal(kind=SignalKind.CO_OCCURRENCE, relation_surface="", basis=SignalBasis.PREDICATE_TEXT)
    assert excinfo.value.code == "signal_predicate_text_basis_requires_words"
    # And the same signal with words is fine, so the refusal is about the words and not the kind.
    assert _signal(basis=SignalBasis.PREDICATE_TEXT).signal_id


def test_a_signal_with_no_basis_and_no_words_is_still_refused() -> None:
    """The old invariant, un-narrowed, for the case it was actually written for.

    ``apps/shared/tests/constitution`` asserts this same code; this test is here so the
    *narrowing* is visible from the signal's own suite. The distinction the phase draws is
    precise: no basis and no words is an unrecorded gap, a basis and no words is a recorded
    observation, and only the second is new.
    """
    with pytest.raises(SignalContractError) as excinfo:
        _signal(
            kind=SignalKind.CO_OCCURRENCE,
            relation_surface="",
            relation_ref=None,
            basis=None,
        )
    assert excinfo.value.code == "signal_asserts_nothing"
    assert "co_occurrence" in str(excinfo.value)


def test_an_unrecognised_basis_is_refused_with_the_vocabulary_in_the_message() -> None:
    """A basis nobody can enumerate is a basis nobody can audit (FR-014)."""
    with pytest.raises(SignalContractError) as excinfo:
        _signal(basis="vibes")  # type: ignore[arg-type]
    assert excinfo.value.code == "signal_basis_unknown"
    for basis in SIGNAL_BASES:
        assert basis.value in str(excinfo.value)


# --------------------------------------------------------------------------- #
# D3 / D4 — the address material, and the mutation that proves the guard has teeth
# --------------------------------------------------------------------------- #


def test_two_signals_differing_only_in_stated_arity_get_different_addresses() -> None:
    """The defect this phase exists to fix, stated as its own test.

    ``extra`` is excluded from ``_material()``, and ``extra`` is where arity lived, so before
    4A a four-slot reading and a two-slot reading of the same two mentions derived the *same*
    ``signal_id``. The stored rows differed; the addresses did not. That is a silent merge of
    a four-ary relation with a binary one, and it is invisible to every consumer keyed on the
    id.
    """
    binary = _signal(participants=binary_participants("MN-A", "MN-B"))
    quaternary = _signal(
        participants=(
            binary_participants("MN-A", "MN-B")[0],
            binary_participants("MN-A", "MN-B")[1],
            _participant(2),
            _participant(3),
        )
    )
    # Same first two ends, same surface, same channel, same producer: the *only* difference is
    # that one declares two more participants.
    assert quaternary.subject_mention_ref == binary.subject_mention_ref
    assert quaternary.object_mention_ref == binary.object_mention_ref
    assert quaternary.relation_surface == binary.relation_surface
    assert quaternary.kind is binary.kind
    assert quaternary.producer_ref == binary.producer_ref
    assert quaternary.arity != binary.arity
    assert quaternary.signal_id != binary.signal_id, (
        "two signals declaring different arities over the same two mentions addressed to one "
        "signal_id. Declared shape is part of what was seen, so it is part of the address"
    )


def test_a_participants_slot_or_ordinal_change_moves_the_address() -> None:
    """The three keys of a participant's identity projection, each on its own.

    Which end, which position in the reading, and where in a tie. Anything else on a
    participant — a role name, a confidence, a referent shape — is tested *not* to move it, in
    ``test_role_hypothesis_confidence_and_argument_shape_stay_out_of_the_address``.
    """
    reference = _signal(participants=tuple(_participant(i) for i in range(3)))
    for label, restated in (
        (
            "mention",
            (_participant(0), _participant(1), _participant(9)),
        ),
        (
            "slot",
            (
                _participant(0),
                _participant(1),
                RelationParticipant(mention_ref="MN-2", slot=ArgumentSlot(3), ordinal=2),
            ),
        ),
        (
            "ordinal",
            (
                _participant(0),
                _participant(1),
                RelationParticipant(mention_ref="MN-2", slot=ArgumentSlot(2), ordinal=7),
            ),
        ),
    ):
        assert _signal(participants=restated).signal_id != reference.signal_id, (
            f"a participant's {label} did not reach the address material"
        )


def test_the_basis_is_in_the_address_material() -> None:
    """How a producer saw something is a fact about the observation.

    Two producers that saw the same two ends by different means — a parsed event frame and a
    table slot — are two observations. One address for both would make the platform unable to
    say how many times it read words and how many times it read a grid.
    """
    by_frame = _signal(basis=SignalBasis.EVENT_FRAME)
    by_slot = _signal(basis=SignalBasis.TABLE_SLOT)
    assert by_frame._material()["basis"] == "event_frame"
    assert by_frame.signal_id != by_slot.signal_id


def test_a_surface_a_span_and_a_confidence_are_not_in_the_address_material() -> None:
    """Confidence was already excluded before 4A, and span and surface are excluded on the
    participant projection this phase added.

    Read on the *participant* — the material 4A adds — plus the signal's own
    ``producer_confidence``. A2 D4.3's exclusions: "the sentence, span, trigger, supporting
    spans", "confidence". ``producer_confidence`` was excluded by this module's own docstring
    before 4A, and the constitutional suite
    (``test_two_producers_reading_the_same_thing_are_two_signals``) pins it: a producer being
    more sure of the same reading is not a second observation.

    **The scope of this claim, stated rather than implied.** ``RelationSignal._material`` *does*
    still carry ``relation_surface``, ``trigger_span`` and ``supporting_spans`` — it did before
    4A and it does now, because a signal is content-addressed on what was *observed*, raw words
    and locations included, and removing them is a removal this phase may not perform. What 4A
    adds is ``participants``, ``basis`` and ``polarity``, and the claim above is that the
    material those additions introduce keeps no surface, no span and no confidence. A change
    that strips the signal-level fields is a 4C/Phase-5 question about the signal's own
    revision material, not something this phase could do additively.
    """
    reference = _signal(participants=tuple(_participant(i) for i in range(3)))
    material = reference._material()
    for absent in ("producer_confidence", "notes", "signal_ordinal", "predicate_hypothesis"):
        assert absent not in material, f"{absent} is in the address material"
    # Confidence at the participant level, moved: the address does not notice.
    surer = _signal(
        participants=tuple(
            RelationParticipant(
                mention_ref=p.mention_ref,
                slot=p.slot,
                ordinal=p.ordinal,
                confidence=0.99,
            )
            for p in reference.participants
        ),
        producer_confidence=0.99,
    )
    assert surer.participants != reference.participants
    assert surer.signal_id == reference.signal_id, (
        "confidence in the address would let one producer's re-scoring manufacture "
        "corroboration, and a shape or role change would fork a relation on a type-layer edit"
    )


def test_the_producer_stays_in_the_address_material() -> None:
    """The other half of FR-034, and the reason three docstrings had to be corrected.

    ``producer_ref`` is in the material and must stay: FR-034 counts independent *sources*, and
    a reader is identified by who it is. Leave it out and two readers of one page collapse into
    one observation, so the platform reports corroboration it does not have. The docstrings
    that claimed the opposite — in this module's header, in the class docstring and in
    ``dedupe_by_content`` — were wrong, and they were wrong in the direction that looks like a
    safety feature. The constitutional suite already guards the behaviour; this pins the
    intent so the docstring and the code cannot drift apart again.
    """
    assert "producer_ref" in _signal()._material()
    first = _signal(producer_ref="lexical/cue-window")
    second = _signal(producer_ref="structural/table-slot")
    assert first.signal_id != second.signal_id
    assert first._material()["producer_ref"] == "lexical/cue-window"


def test_polarity_is_a_field_and_reaches_the_address_material() -> None:
    """A denial and an assertion are opposite claims, and an address cannot tell them apart.

    A kind answering "how did you see it" with an answer about *what was seen* is a different
    question (FR-011, FR-012). Phase 4C deleted that kind, so :attr:`RelationSignal.polarity`
    is the only place a signal can be denied and this field has to carry the whole of it.
    """
    asserted = _signal()
    denied = _signal(polarity=Polarity.DENIED)
    assert asserted.polarity is Polarity.ASSERTED
    assert denied.polarity is Polarity.DENIED
    assert denied.is_denied and not asserted.is_denied
    assert denied._material()["polarity"] == "denied"
    assert denied.signal_id != asserted.signal_id, (
        "'Acme did not acquire Beta' and 'Acme acquired Beta' are opposite claims; an address "
        "that cannot tell them apart makes a denial and an assertion the same row"
    )
    # A producer states it; it is not derived from the channel and not inferred from the surface.
    assert "polarity" in [f.name for f in dataclasses.fields(RelationSignal)]
    round_tripped = RelationSignal.from_dict(denied.to_dict())
    assert round_tripped.polarity is Polarity.DENIED
    assert round_tripped == denied


def test_the_negation_kind_is_gone_and_the_denial_survives_it() -> None:
    """The 4C deletion, and the assertion that nothing was lost with it.

    ``SignalKind.NEGATION`` was "present because the alternative is worse" - without it, "Acme
    did not acquire Beta" is either dropped, losing an observed fact, or recorded as an
    acquisition, which is a lie. Phase 4A built the landing place (the ``polarity`` field) and
    Phase 4B proved it end to end through the syntactic producer; 4C removes the member. So the
    point of this test is that the *removal* is what makes the field load-bearing: there is one
    way to say it, and the value the member used to hold is still recordable.
    """
    assert "NEGATION" not in SignalKind.__members__
    assert "QUANTITY" not in SignalKind.__members__
    assert "COREFERENCE" not in SignalKind.__members__
    # The three literals are refused as kinds, by name, rather than silently coerced - a stored
    # 020-era row carrying one of them must be told the truth about why it will not load.
    for removed in ("negation", "quantity", "coreference"):
        with pytest.raises(ValueError):
            SignalKind(removed)
    # And the denial is fully expressible through the field that replaced it.
    denied = _signal(relation_surface="did not acquire", polarity=Polarity.DENIED)
    assert denied.is_denied
    assert denied.signal_id != _signal(relation_surface="did not acquire").signal_id
    # A denial the vocabulary cannot name is still a denial, and the surface is what says so -
    # re-keyed onto the field, and appended **once**, so the record survives a round trip.
    assert denied.notes == "denied, predicate unresolved"
    assert RelationSignal.from_dict(denied.to_dict()) == denied


def test_the_polarity_domain_is_the_platforms_own_and_its_width_is_still_unresolved() -> None:
    """FR-015 wants two members; ``relation_candidate.py`` documents three. Still unresolved.

    This asserts the *current* surface rather than the *desired* one, deliberately. FR-015
    requires ``Polarity`` to be "closed and is ``{ASSERTED, DENIED}`` — two members, not
    three", and narrowing the enum is a deletion. **Phase 4C did not make it**, and the
    reason is on the record rather than in a shrug: the same enum types
    :attr:`domain.relation_candidate.RelationCandidate.polarity` and that file's docstring says
    "``Polarity.UNCERTAIN`` is the explicit value for a held-open reading", and ``A2``'s band
    (FR-174…FR-178) owns that vocabulary — so narrowing it here would be a second owner editing
    a second owner's answer. It was not made redundant by 4A or 4B, and 4C's remit is the
    redundancy they created.

    So 4A reused :class:`domain.predicate_signature.Polarity` and did **not** declare a
    signal-local two-member copy. A local ``SignalPolarity`` would have been the tidier-looking
    answer, would have passed every other test in this file, and would have made the conflict
    invisible and unfixable — two answers to one question, which is the failure this
    repository's whole identity design is against. The test therefore pins the exact surface
    the outstanding task has to change: these three assertions, and the field docstring that
    cites the conflict.
    """
    assert {p.value for p in Polarity} == {"asserted", "denied", "uncertain"}
    # The signal field is the platform enum, not a copy: `is` works on the members.
    held_open = _signal(polarity=Polarity("uncertain"))
    assert held_open.polarity is Polarity.UNCERTAIN
    assert held_open.signal_id != _signal().signal_id
    # And the narrower axis FR-015 names as the right home for "held open" exists and is
    # separate — which is why the conflict above is a question about this field's width, not
    # a hole in it.
    assert "resolution_state" in {f.name for f in dataclasses.fields(PredicateHypothesis)}


def test_the_declared_arity_is_the_participant_tuple_and_is_said_in_the_record() -> None:
    """One source per fact, in the layer that needs it.

    The declared shape enters the address as the participant tuple, and its length *is* the
    arity. There is no second ``arity`` key in the material to disagree with it; the count is
    stated only in :meth:`RelationSignal.to_dict`, which is the projection a reader opens.

    An earlier version carried both, and the effect was measurable rather than aesthetic: the
    mutation test below could not reproduce the defect, because with ``arity`` still in the
    material, removing ``participants`` left the two signals distinguishable and the mutation
    appeared to guard nothing. Redundancy in a content address is not free — it can hide the
    thing a test is looking for.
    """
    quaternary = _signal(participants=tuple(_participant(i) for i in range(4)))
    material = quaternary._material()
    assert "arity" not in material
    assert len(material["participants"]) == 4
    assert quaternary.arity == 4
    assert quaternary.to_dict()["arity"] == 4


def test_the_synthetic_producer_fields_still_reach_the_address() -> None:
    """A trigger span and supporting spans were in the material before 4A and still are.

    Asserted so that "4A added three keys" cannot later be read as "4A re-derived the
    derivation": the pre-existing key set is unchanged, and only ``participants``, ``arity``,
    ``basis`` and ``polarity`` were added to it.
    """
    material = _signal(
        trigger_span=SpanRef(segment_ref="SEG-1", start=0, end=4),
        supporting_spans=(SpanRef(segment_ref="SEG-1", start=6, end=10),),
        stated_axes=(),
    )._material()
    assert material["trigger_span"]["segment_ref"] == "SEG-1"
    assert material["trigger_span"]["start"] == 0
    assert material["trigger_span"]["end"] == 4
    assert [span["segment_ref"] for span in material["supporting_spans"]] == ["SEG-1"]
    assert [span["end"] for span in material["supporting_spans"]] == [10]
    for key in (
        "tenant_id",
        "subject_mention_ref",
        "object_mention_ref",
        "kind",
        "relation_surface",
        "relation_ref",
        "direction",
        "producer_ref",
        "producer_version",
        "context_ref",
        "semantic_regime_ref",
        "capture_ref",
        "stated_axes",
        "neighbourhood",
    ):
        assert key in material, f"{key} left the address material in Phase 4A"


# --------------------------------------------------------------------------- #
# The mutation test: prove the arity guard has teeth
# --------------------------------------------------------------------------- #


def _mutated_signal_module(find: str, replace: str) -> Path:
    """A throwaway copy of the two packages with one edit applied to ``signal.py``.

    The copy is flat — ``domain``, ``extractors``, ``parsers`` and ``semantic`` side by side —
    because that is the single ``PYTHONPATH`` entry a child interpreter needs, and a faithful
    directory layout would need three for no gain. The repository is never written to; this is
    the same discipline ``test_constitution_has_teeth.py`` uses, for the same reason.
    """
    root = Path(tempfile.mkdtemp(prefix="signal-mutation-"))
    for package, members in _COPIED:
        for member in members:
            source = APPS / package / member
            if source.is_dir():
                shutil.copytree(source, root / source.name, ignore=shutil.ignore_patterns(
                    "__pycache__"
                ))
            elif source.exists():
                shutil.copy2(source, root / source.name)
    target = (root / "extractors" / "signals" / "signal.py").resolve()
    text = target.read_text(encoding="utf-8")
    assert find in text, f"mutation anchor not found in signal.py: {find[:70]!r}"
    target.write_text(text.replace(find, replace, 1), encoding="utf-8")
    return root


def _child_env(root: Path) -> dict[str, str]:
    """The current environment with only ``PYTHONPATH`` redirected.

    Inherited rather than hand-built, for the reason ``test_constitution_has_teeth.py`` records:
    a hand-built ``PATH`` without System32 is not a smaller environment on Windows, it is a
    broken one, and every child fails with a Winsock error that looks like a test failure.
    """
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root)
    return env


_ARITY_COLLAPSE_SCRIPT = """
from extractors.signals.signal import (
    Neighbourhood, RelationSignal, SignalKind,
)
from domain.predicate_signature import ArgumentSlot
from domain.relation_participant import RelationParticipant
from domain.signal_basis import SignalBasis

nb = Neighbourhood(characters_scanned=42, pairs_considered=0, scope_read="one clause")
def participant(i):
    return RelationParticipant(mention_ref=f"MN-{i}", slot=ArgumentSlot(i), ordinal=i)
def signal(participants):
    return RelationSignal(
        kind=SignalKind.SYNTAX, relation_surface="sold to", neighbourhood=nb,
        participants=participants, basis=SignalBasis.EVENT_FRAME,
        producer_ref="p/1", context_ref="C1", semantic_regime_ref="R1",
        tenant_id="t",
    )
binary = signal((participant(0), participant(1)))
quaternary = signal(tuple(participant(i) for i in range(4)))
print("ARITY_COLLAPSE" if binary.signal_id == quaternary.signal_id else "ARITY_DISTINCT")
"""


def test_dropping_participants_from_the_material_collapses_arity_and_is_caught() -> None:
    """The mutation test, and the reason the arity assertion is believed.

    The defect 4A fixes was that ``_material()`` excluded ``extra`` — where arity lived — so
    two signals of different declared arity derived one address. This removes ``participants``
    from the material and asserts the arity distinction **disappears**: the mutated contract
    reproduces the pre-4A bug exactly, and
    ``test_two_signals_differing_only_in_stated_arity_get_different_addresses`` is the guard
    that must notice.

    A guard that has never been observed to fail has not been shown to guard anything, and this
    is the cheapest possible way to observe it: one dict key, checked from a separate
    interpreter so the mutation is applied to a copy rather than to the repository.
    """
    root = _mutated_signal_module(
        '            "participants": [p.to_identity() for p in self.participants],\n',
        "",
    )
    try:
        completed = subprocess.run(
            [sys.executable, "-c", _ARITY_COLLAPSE_SCRIPT],
            capture_output=True,
            text=True,
            cwd=str(root),
            env=_child_env(root),
            # The child's exit status is the *subject* of this test, not an error here: a
            # mutation that merely broke the import would prove nothing, and the returncode is
            # asserted on the next line.
            check=False,
        )
    finally:
        shutil.rmtree(root, ignore_errors=True)
    assert completed.returncode == 0, (
        "the mutated copy did not run, so the mutation proved nothing: "
        f"{completed.stderr[-2000:]}"
    )
    assert "ARITY_COLLAPSE" in completed.stdout, (
        "removing `participants` from the address material did not collapse arity, so the "
        f"guarded defect has been fixed by something else. Child said: {completed.stdout!r}"
    )


def test_the_unmutated_contract_keeps_arity_distinct() -> None:
    """The other half of the check, and the half that is easy to skip.

    If arity already collapsed before the mutation, "the mutation collapsed it" would be
    meaningless and the test above would pass while guarding nothing at all. Same script, same
    interpreter, unmutated source.
    """
    completed = subprocess.run(
        [sys.executable, "-c", _ARITY_COLLAPSE_SCRIPT],
        capture_output=True,
        text=True,
        cwd=str(INTERPRETATION),
        env=_child_env(INTERPRETATION),
        check=False,
    )
    assert completed.returncode == 0, completed.stderr[-2000:]
    assert "ARITY_DISTINCT" in completed.stdout, (
        f"arity already collapsed on the unmutated source: {completed.stdout!r}"
    )


def test_dropping_polarity_from_the_material_collapses_a_denial_and_is_caught() -> None:
    """The second mutation, for the second addition to the material.

    Same discipline for the other reason 4A touched the address. A denial that shares an
    address with an assertion is the defect FR-015 exists to prevent, and it is as silent as
    the arity one: two rows, one id, opposite meanings.
    """
    script = _ARITY_COLLAPSE_SCRIPT.replace(
        "print(\"ARITY_COLLAPSE\" if binary.signal_id == quaternary.signal_id else "
        "\"ARITY_DISTINCT\")",
        "from domain.predicate_signature import Polarity\n"
        "denied = signal((participant(0), participant(1)))\n"
        "denied = RelationSignal(\n"
        "    kind=SignalKind.SYNTAX, relation_surface='sold to', neighbourhood=nb,\n"
        "    participants=(participant(0), participant(1)), basis=SignalBasis.EVENT_FRAME,\n"
        "    polarity=Polarity.DENIED, producer_ref='p/1', context_ref='C1',\n"
        "    semantic_regime_ref='R1', tenant_id='t')\n"
        "print('POLARITY_COLLAPSE' if binary.signal_id == denied.signal_id else "
        "'POLARITY_DISTINCT')",
    )
    root = _mutated_signal_module('            "polarity": str(self.polarity),\n', "")
    try:
        completed = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            cwd=str(root),
            env=_child_env(root),
            check=False,
        )
    finally:
        shutil.rmtree(root, ignore_errors=True)
    assert completed.returncode == 0, completed.stderr[-2000:]
    assert "POLARITY_COLLAPSE" in completed.stdout, (
        "removing `polarity` from the address material did not collapse a denial onto its "
        f"assertion. Child said: {completed.stdout!r}"
    )
