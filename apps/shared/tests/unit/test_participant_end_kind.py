"""Phase 4C / C4: a ``capture:`` end is a **retrieval**, and it is typed as one.

Feature 021, spec FR-016, FR-018, FR-094, FR-009; ``repair/ARBITRATION.md`` §8; constitution
Invariant 2.

**The decision, in one place, because it is not recoverable from the code.** A capture end is a
fetch event, not a mention, and Phase 4C had to choose between two answers:

*Rejected — a first-class document mention.* Mint an ``MN-`` for the document a
``<meta name="author">`` tag belongs to. Two reasons it is wrong, and the second is the one that
is easy to miss. First, the capture **already has a durable identity**:
:attr:`domain.capture.Capture.capture_id` is a real content-addressed id, so a second id for the
same fact is the exact defect the occurrence/retrieval split exists to prevent (I-2). Second, and
sharper: a mention is an occurrence *at a span in a segment*, and the retrieval is the **scope**
every such span is measured against — the document would be its own container and its own
content, which is not an occurrence of anything.

*Chosen — a distinct participant kind that is not required to resolve to ``MN-``.*
:class:`domain.relation_participant.ParticipantEndKind` is two members,
``OCCURRENCE``/``RETRIEVAL``, and a ``RETRIEVAL`` end is addressable, already durable, and carried
through a binding unchanged. This file pins the three properties that make the choice a
*contract* rather than a convention: the kind is **inferred from the address** so the five
producers that mint a capture address do not have to restate it; a **stated** kind that
contradicts the address is **refused** so a record cannot lie about which path its end takes; and
the kind is **excluded from identity** because the address already implies it, so nothing here
can re-key a stored signal.
"""

from __future__ import annotations

import pytest

from domain.mention_occurrence_index import (
    mint_capture_address,
    mint_occurrence_address,
)
from domain.predicate_signature import ArgumentSlot
from domain.relation_participant import (
    ParticipantContractError,
    ParticipantEndKind,
    RelationParticipant,
    end_kind_of,
)

pytestmark = pytest.mark.unit

_CAPTURE = mint_capture_address("CAP-1")
#: Addresses reached through the one minter, never spelled out: a test that assembled the string
#: itself would be a second answer to "what does an address look like", and it kept going on
#: saying the retired grammar's shape long after the grammar changed.
_POSITIONED = mint_occurrence_address(label="subject", surface="Acme", start=0, end=4)
_UNPOSITIONED = mint_occurrence_address(label="subject", surface="Acme")


def test_a_capture_address_infers_a_retrieval_and_a_surface_address_infers_an_occurrence() -> None:
    """The inference, on both namespaces, and it is **structural** rather than textual.

    Read off the parsed address type rather than by testing whether the string starts with
    ``capture``, so a document whose first mentioned surface happens to be the word "capture" is
    not promoted to a retrieval — a string test would have made that document's author
    unresolvable, and the error would have named the wrong thing.
    """
    assert end_kind_of(_CAPTURE) is ParticipantEndKind.RETRIEVAL
    assert end_kind_of(_POSITIONED) is ParticipantEndKind.OCCURRENCE
    assert end_kind_of(_UNPOSITIONED) is ParticipantEndKind.OCCURRENCE
    # A real mention id, and an address nobody can read, are both the ordinary end: the mention
    # layer is what they are for, and an unreadable address is not evidence of anything else.
    assert end_kind_of("MN-a2805e4e90d64c77d156d3af8d1e79f2") is ParticipantEndKind.OCCURRENCE
    assert end_kind_of("entity:42") is ParticipantEndKind.OCCURRENCE
    assert end_kind_of("") is ParticipantEndKind.OCCURRENCE
    # Including one written under the retired grammar, which is unreadable and therefore an
    # occurrence. It is *not* a retrieval and it is *not* evidence of a capture, which is the
    # whole answer: an address that cannot be read is not evidence of anything else.
    assert end_kind_of("surface:subject:Acme") is ParticipantEndKind.OCCURRENCE


def test_the_end_kind_is_inferred_when_unstated_and_adopted_when_agreeing() -> None:
    """``None`` means *read the address*, and the five capture-addressing producers rely on it.

    They all build participants without the field, because before 4C there was no field to set.
    Requiring them to state it would be requiring them to restate what their own address already
    says, and a producer that restates it is a producer that can get it wrong.
    """
    inferred = RelationParticipant(mention_ref=_CAPTURE, slot=ArgumentSlot(0))
    assert inferred.end_kind is ParticipantEndKind.RETRIEVAL
    stated = RelationParticipant(
        mention_ref=_CAPTURE, slot=ArgumentSlot(0), end_kind=ParticipantEndKind.RETRIEVAL
    )
    assert stated.end_kind is ParticipantEndKind.RETRIEVAL
    # A string spelling coerces, so a stored or serialised record reloads rather than refusing.
    assert (
        RelationParticipant(
            mention_ref=_CAPTURE, slot=ArgumentSlot(0), end_kind="retrieval"
        ).end_kind
        is ParticipantEndKind.RETRIEVAL
    )


def test_a_stated_end_kind_that_contradicts_the_address_is_refused() -> None:
    """The half that makes the field a contract: a record may not lie about its own end kind.

    A participant that says ``occurrence`` while addressing a retrieval is a record that will be
    handed to the mention layer, which will refuse it with
    ``mention_capture_is_not_a_mention`` — and nothing there says the record lied. The other
    direction is the one that would fabricate: saying ``retrieval`` about a real occurrence
    would carry an unresolvable participant through a binding and report it as though it had been
    read. Caught here, where the record and the contradiction are both in view.
    """
    with pytest.raises(ParticipantContractError) as as_occurrence:
        RelationParticipant(
            mention_ref=_CAPTURE, slot=ArgumentSlot(0), end_kind=ParticipantEndKind.OCCURRENCE
        )
    assert as_occurrence.value.code == "participant_end_kind_mismatch"
    assert _CAPTURE in str(as_occurrence.value)
    assert "second identity" in str(as_occurrence.value)

    with pytest.raises(ParticipantContractError) as as_retrieval:
        RelationParticipant(
            mention_ref=_POSITIONED,
            slot=ArgumentSlot(0),
            end_kind=ParticipantEndKind.RETRIEVAL,
        )
    assert as_retrieval.value.code == "participant_end_kind_mismatch"

    with pytest.raises(ParticipantContractError) as unknown:
        RelationParticipant(
            mention_ref=_CAPTURE, slot=ArgumentSlot(0), end_kind="mentionish"  # type: ignore[arg-type]
        )
    assert unknown.value.code == "participant_end_kind_unknown"
    assert "occurrence, retrieval" in str(unknown.value)


def test_the_end_kind_is_recorded_but_is_not_identity_material() -> None:
    """Recorded, so a reader need not parse a prefix; excluded, so nothing here re-keys.

    Two properties and they pull in opposite directions, which is why both are asserted. The
    field is **in** :meth:`RelationParticipant.to_dict` because FR-008's obligation is
    losslessness and an end whose kind is dropped on a round trip re-infers correctly only by
    luck. It is **out** of :meth:`RelationParticipant.to_identity` because
    :attr:`mention_ref` already implies it — a fourth identity key for a fact the third one says
    is a value that can disagree with what it summarises, and the exclusions on the other fields
    are each reasoned rather than tidy for exactly this reason.
    """
    participant = RelationParticipant(mention_ref=_CAPTURE, slot=ArgumentSlot(0))
    assert participant.to_dict()["end_kind"] == "retrieval"
    assert RelationParticipant.from_dict(participant.to_dict()) == participant
    assert "end_kind" not in participant.to_identity()
    assert participant.to_identity() == {
        "mention_ref": _CAPTURE,
        "slot": "A0",
        "ordinal": 0,
    }


def test_a_retrieval_end_is_never_mintable_and_the_refusal_names_the_stop_condition() -> None:
    """The index's own answer, unchanged — this phase gave the *participant* a type, not the
    index a new behaviour.

    :meth:`domain.mention_occurrence_index.MentionOccurrenceIndex.require_occurrence` still
    refuses a ``capture:`` address with ``mention_capture_is_not_a_mention``, and the message
    still carries the ``STOP``. What changed is that nothing on the extraction path *asks* — the
    binder reads :attr:`ParticipantEndKind` and passes the end through — so the refusal becomes a
    backstop rather than a routine outcome. It is asserted here so that a later "simplification"
    that routes retrievals back through the occurrence path fails loudly.
    """
    from domain.mention_occurrence_index import (
        MentionBindingError,
        MentionOccurrence,
        MentionOccurrenceIndex,
    )

    index = MentionOccurrenceIndex(
        capture_ref="CAP-1",
        segment_ref="SEG-1",
        extractor_ref="deterministic-extractor-set",
        occurrences=[MentionOccurrence(kind="org", surface="Acme", start=0, end=4)],
    )
    assert index.read_capture(_CAPTURE) == "CAP-1"
    with pytest.raises(MentionBindingError) as refused:
        index.require_occurrence(_CAPTURE)
    assert refused.value.code == "mention_capture_is_not_a_mention"
    assert "STOP" in str(refused.value)
    assert "do not mint an MN-" in str(refused.value)
