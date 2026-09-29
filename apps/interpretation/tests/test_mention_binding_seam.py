"""The mention-binding seam: a producer's deferred address becomes a real ``MN-``, or it is refused.

Feature 021, brief §25 and §26, spec FR-016, FR-018, FR-019, FR-020, FR-073, FR-094;
``repair/ARBITRATION.md`` §8; ``data-model.md`` part 10.1.

**What this file is.** Phase 4B moved the seven producers off fabricated participant references and
onto deferred occurrence addresses — then ``surface@<start>-<end>:<label>:<surface>``, now the
injective form :func:`domain.mention_occurrence_index.mint_occurrence_address` writes — and that was the
right call: a producer sits below mention extraction, so a producer that minted a mention identity
would be inventing a durable record id from a string match (brief §25, FR-019). But a shape a
producer mints and a shape the platform needs are not the same shape, and nothing resolved between
them. ``participant.mention_ref`` is documented as "a reference *into the mention index*" and there
was no mention index. This file exercises the other half:
:func:`extractors.signals.mentions.bind_participant_addresses` and
:class:`domain.mention_occurrence_index.MentionOccurrenceIndex` behind it.

**Three things are pinned, and the third is the one that makes the other two mean something.**

1. **The producer's contract is unchanged.** The addresses are still deferred, still minted by
   :mod:`extractors.signals.mentions` and by nothing else, and still not ``MN-``-prefixed. The
   binding happens in a separate call, so a producer's signature does not grow an index parameter
   and a producer run with no index available is still a legal producer run.
2. **Fail-closed.** An address that does not resolve is refused with
   ``participant_address_unresolved``, naming the signal, the address and the underlying code. This
   is the part with teeth: an unresolved address that reaches assembly is a participant that
   addresses nothing — it groups under its own string, corroborates nothing, and reports as though
   it had been read. The platform's own answer to that is to refuse and say so (I-3, constitution
   IV), and a warning would be the failure with extra steps.
3. **No inversion.** The binder reaches :mod:`domain`, which is strictly below
   :mod:`apps.interpretation`; it does not reach the composition root
   (:mod:`semantic_path.execution`, which imports both :mod:`extractors.registry` and
   :mod:`graph.relation_store`) and it imports no graph, claim, admission or projection symbol at
   all. :func:`test_the_producer_side_imports_nothing_above_the_extraction_layer` is a source scan
   for that, because an import that has been made cannot be un-made by a docstring.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from domain.mention_occurrence_index import (
    DEFERRED_ADDRESS_VERSION,
    DEFERRED_CAPTURE_PREFIX,
    DEFERRED_OCCURRENCE_PREFIX,
    MENTION_ID_PREFIX,
    MentionBindingError,
    MentionOccurrence,
    MentionOccurrenceIndex,
    mint_capture_address,
)
from domain.predicate_signature import ArgumentSlot
from domain.relation_participant import RelationParticipant
from domain.signal_basis import SignalBasis

from extractors.signals.lexical import LexicalCueExtractor, lexical_signals
from extractors.signals.links import HyperlinkExtractor
from extractors.signals.mentions import (
    PRODUCER_OCCURRENCE_KIND,
    BoundParticipants,
    bind_participant_addresses,
    bind_producer_signals,
    deferred_capture,
    deferred_occurrence,
    producer_occurrence_index,
    read_occurrence,
)
from extractors.signals.metadata import metadata_signals
from extractors.signals.protocol import ExtractionScope, run_producer
from extractors.signals.signal import Neighbourhood, RelationSignal, SignalContractError, SignalKind

pytestmark = pytest.mark.unit

#: ``apps/interpretation`` — the producer app. The scan below reads its whole source tree.
APP = Path(__file__).resolve().parents[1]

_TENANT = "tenant-a"
_CAPTURE = "CAP-1"
_SEGMENT = "seg-1"
_NB = Neighbourhood(characters_scanned=64, pairs_considered=0, scope_read="one document")


def _scope(**over: str) -> ExtractionScope:
    base = {
        "tenant_id": _TENANT,
        "context_ref": "ctx-1",
        "semantic_regime_ref": "regime-1",
        "document_ref": _CAPTURE,
    }
    return ExtractionScope(**{**base, **over})


def _index(*occurrences: MentionOccurrence, **over: str) -> MentionOccurrenceIndex:
    return MentionOccurrenceIndex(
        occurrences=occurrences,
        capture_ref=_CAPTURE,
        segment_ref=_SEGMENT,
        extractor_ref="deterministic-extractor-set",
        **over,
    )


def _signal(*refs: str, surface: str = "CEO of", producer_ref: str = "prose/one") -> RelationSignal:
    """A signal whose two ends carry ``refs`` verbatim, so the binder is exercised on the addresses
    the producers actually mint rather than on a convenient fixture.

    :func:`RelationSignal.subject_mention_ref` and friends are derived from ``participants``, so
    building the tuple is the whole of the construction — there is no second place a participant
    reference can be hiding.
    """
    return RelationSignal(
        participants=tuple(
            RelationParticipant(
                mention_ref=reference, slot=ArgumentSlot(index), ordinal=index
            )
            for index, reference in enumerate(refs)
        ),
        kind=SignalKind.SYNTAX,
        relation_surface=surface,
        basis=SignalBasis.PREDICATE_TEXT,
        neighbourhood=_NB,
        producer_ref=producer_ref,
        context_ref="ctx-1",
        semantic_regime_ref="regime-1",
        tenant_id=_TENANT,
        extra={"capture_ref": _CAPTURE},
    )


def _ends(first: str, second: str) -> tuple[str, str]:
    return first, second


# --------------------------------------------------------------------------- #
# A deferred address resolves; a capture end passes through
# --------------------------------------------------------------------------- #


def test_a_producer_address_resolves_to_a_real_mention_id() -> None:
    """The seam, on a real producer's output and against an index built from the same text.

    The lexical producer is the case worth having, because its addresses are the positioned form
    and both of its ends are addressed in the document at their own offsets. The index is built
    from those offsets — from the addresses themselves, read back through
    :func:`read_occurrence` — so this asserts the whole chain: mint an address, publish an inverse,
    resolve it, and get an id the mention layer could have minted for the same occurrence.
    """
    text = "John Smith became CEO of Acme."
    signals = lexical_signals([text], scope=_scope())
    assert len(signals) == 1
    signal = signals[0]
    addresses = [participant.mention_ref for participant in signal.participants]

    occurrences = []
    for participant in signal.participants:
        label, surface, span = read_occurrence(participant.mention_ref)
        assert span is not None, participant.mention_ref
        assert text[span[0] : span[1]] == surface, participant.mention_ref
        assert label in {"subject", "object"}, label
        occurrences.append(
            MentionOccurrence(kind="org", surface=surface, start=span[0], end=span[1])
        )
    index = _index(*occurrences)

    bound = bind_participant_addresses([signal], index)
    assert len(bound) == 1
    one = bound[0]
    assert isinstance(one, BoundParticipants)
    assert one.signal_id == signal.signal_id
    # Parallel to ``signal.participants``, position for position: a participant's slot is what says
    # which end is which, and a flattened mapping would leave a reader to re-derive it.
    assert len(one.mention_ids) == len(signal.participants) == 2
    assert all(mention_id.startswith(MENTION_ID_PREFIX) for mention_id in one.mention_ids)
    assert one.refs == tuple(addresses)
    assert one.capture_refs == ()
    # And the ids are the ones the index minted for those very occurrences.
    assert list(one.mention_ids) == [
        index.mention_id_for(occurrence) for occurrence in occurrences
    ]
    assert one.to_dict()["mention_ids"] == list(one.mention_ids)


def test_a_capture_end_passes_through_as_the_capture_it_already_is() -> None:
    """The metadata producer's document end, and why it is not a mention.

    ``<meta name="author" content="…">`` gives one end that is the *retrieval* rather than an
    occurrence. A capture id is a real content-addressed durable id
    (:class:`domain.capture.Capture`), so this end is already addressable and minting a mention for
    it would put a second identity on one fact (I-2). So it is carried through unchanged, and
    recorded as a capture ref so a reader can tell which end was which without parsing the string.
    """
    head = '<head><meta name="author" content="jane@acme.example"></head>'
    signals = metadata_signals([head], scope=_scope())
    assert signals
    signal = signals[0]
    capture_end, value_end = (p.mention_ref for p in signal.participants)
    assert capture_end == mint_capture_address(_CAPTURE)
    _label, surface, span = read_occurrence(value_end)
    assert span is not None and head[span[0] : span[1]] == surface

    index = _index(
        MentionOccurrence(kind="value", surface=surface, start=span[0], end=span[1])
    )
    bound = bind_participant_addresses([signal], index)[0]
    assert bound.mention_ids == (capture_end, index.mention_id_for(
        MentionOccurrence(kind="value", surface=surface, start=span[0], end=span[1])
    ))
    assert bound.capture_refs == (_CAPTURE,)
    # The index refuses a capture address as a *mention*, with the stop condition named, and the
    # binder never asks it to: the two ends take different paths and that is visible in the record.
    with pytest.raises(MentionBindingError) as refused:
        index.require_occurrence(capture_end)
    assert refused.value.code == "mention_capture_is_not_a_mention"
    assert "STOP" in str(refused.value)


# --------------------------------------------------------------------------- #
# Fail-closed
# --------------------------------------------------------------------------- #


def test_an_unresolvable_address_is_refused_and_names_the_signal() -> None:
    """The refusal, and everything it has to name for an operator to act on it.

    Four things or the message is not actionable: **which signal** (by its content address, so the
    record can be found), **which producer** (so the code that needs fixing can be found), **which
    address**, and **which of the index's codes** fired — because "did not resolve" covers a
    coverage gap and an ambiguity, and those are different bugs.
    """
    orphan = _signal(
        *_ends(
            deferred_occurrence(label="subject", surface="Nobody", start=0, end=6),
            deferred_occurrence(label="object", surface="Acme", start=19, end=23),
        )
    )
    index = _index(MentionOccurrence(kind="org", surface="Acme", start=19, end=23))
    with pytest.raises(SignalContractError) as caught:
        bind_participant_addresses([orphan], index)
    assert caught.value.code == "participant_address_unresolved"
    message = str(caught.value)
    assert orphan.signal_id in message
    assert "prose/one" in message
    assert "Nobody" in message
    assert "mention_occurrence_unresolved" in message


def test_an_ambiguous_address_is_refused_rather_than_guessed() -> None:
    """Two occurrences of one surface, and the unpositioned form is refused for it.

    A syntactic producer's addresses carry no character offsets, so its reference names a surface
    and nothing else. Where the segment holds that surface once, the reference resolves. Where it
    holds it twice, resolving would mean picking a position the producer never stated — and the
    index refuses with ``mention_occurrence_ambiguous`` rather than taking the first, which is the
    failure the ``STOP`` in the message names.
    """
    index = _index(
        MentionOccurrence(kind="org", surface="Acme", start=0, end=4),
        MentionOccurrence(kind="org", surface="Acme", start=20, end=24),
    )
    signal = _signal(
        *_ends(
            deferred_occurrence(label="nsubj", surface="Acme"),
            deferred_occurrence(label="obj", surface="Acme"),
        )
    )
    with pytest.raises(SignalContractError) as caught:
        bind_participant_addresses([signal], index)
    assert caught.value.code == "participant_address_unresolved"
    assert "mention_occurrence_ambiguous" in str(caught.value)
    assert "do not take the first match" in str(caught.value)

    # One occurrence is not ambiguous, so the unpositioned form still binds.
    unique = _index(MentionOccurrence(kind="org", surface="Acme", start=0, end=4))
    bound = bind_participant_addresses([signal], unique)[0]
    assert bound.mention_ids == (unique.mention_id_for(
        MentionOccurrence(kind="org", surface="Acme", start=0, end=4)
    ),) * 2


def test_the_binding_is_order_independent() -> None:
    """Constitution VI, and it is a property of the function rather than of the caller's sorting.

    Signals are bound in a content-derived order, so the same set of signals produces the same
    tuple of bindings whatever order it arrived in — and the same ``mention_ids`` per signal, which
    is the part a reordering would actually corrupt.
    """
    one = _signal(
        *_ends(
            deferred_occurrence(label="s", surface="Acme", start=0, end=4),
            deferred_occurrence(label="o", surface="Acme", start=0, end=4),
        )
    )
    two = _signal(
        *_ends(
            deferred_occurrence(label="s", surface="Microsoft", start=5, end=14),
            deferred_occurrence(label="o", surface="Microsoft", start=5, end=14),
        ),
        surface="acquired",
        producer_ref="prose/two",
    )
    index = _index(
        MentionOccurrence(kind="org", surface="Acme", start=0, end=4),
        MentionOccurrence(kind="org", surface="Microsoft", start=5, end=14),
    )
    forwards = bind_participant_addresses([one, two], index)
    backwards = bind_participant_addresses([two, one], index)
    assert forwards == backwards
    # The order is the binder's own content order, and its key is ``(producer_ref, signal_id)``.
    # The assertion used to sort on ``signal_id`` alone, which is a *third* key: it held only
    # while two unrelated digests happened to fall the way the producer refs did, and an address
    # encoding change moved them apart without anything being wrong. Sorting on the documented key
    # is what makes this fail if the binder ever sorts on anything else.
    assert [bound.signal_id for bound in forwards] == [
        signal.signal_id
        for signal in sorted((one, two), key=lambda s: (s.producer_ref, s.signal_id))
    ]


# --------------------------------------------------------------------------- #
# The producer-side contract is unchanged, and nothing above it is imported
# --------------------------------------------------------------------------- #


# --------------------------------------------------------------------------- #
# C3: the golden path's own addressing, registered and bound
# --------------------------------------------------------------------------- #


def test_a_producer_occurrence_binds_without_being_re_addressed() -> None:
    """The reconciliation, and the specific thing it is *not*.

    The mention layer addresses whole entity spans at extractor granularity and a producer
    addresses the cue group that matched, so for ``"John Smith became CEO of Acme."`` the
    mention layer's subject span is ``John Smith`` at ``[0, 10)`` and the lexical producer's
    subject is ``CEO`` at ``[18, 21)``. They do not coincide and they were never going to: they
    are two observations of the document, read by two instruments, and
    :class:`MentionOccurrenceKey`'s five keys exist to keep them apart.

    So the binding **registers the producer's own read** and resolves through that, rather than
    re-addressing the producer's end onto the mention layer's span. The assertion that matters
    is the negative one: the bound id is *not* the id the mention layer minted for the same
    person, and the two are not interchangeable. Presenting a producer's end as the mention
    layer's would be the orchestrator inventing a position nobody read.
    """
    text = "John Smith became CEO of Acme."
    signal = lexical_signals([text], scope=_scope())[0]
    mention_layer = _index(
        MentionOccurrence(kind="person", surface="John Smith", start=0, end=10),
        MentionOccurrence(kind="org", surface="CEO", start=18, end=21),
    )
    # The mention layer's read of the subject and the producer's read of its subject are two
    # occurrences with two ids. Presenting the producer's end as the mention layer's would be
    # the orchestrator inventing a position nobody read, so the negative assertion is the point.
    assert mention_layer.read_occurrence(
        deferred_occurrence(label="subject", surface="John Smith", start=0, end=10)
    ).mention_id != mention_layer.read_occurrence(
        deferred_occurrence(label="subject", surface="CEO", start=18, end=21)
    ).mention_id

    bound = bind_producer_signals([signal], capture_ref=_CAPTURE, segment_ref=_SEGMENT)[0]
    for participant in bound.participants:
        assert participant.mention_ref.startswith(MENTION_ID_PREFIX), participant.mention_ref
    # The producer's own read, at the producer's own span, under the producer's own scope.
    _label, surface, span = read_occurrence(signal.participants[0].mention_ref)
    assert (surface, span) == ("CEO", (18, 21))
    registered = MentionOccurrence(
        kind=PRODUCER_OCCURRENCE_KIND, surface=surface, start=span[0], end=span[1]
    )
    expected = MentionOccurrenceIndex(
        capture_ref=_CAPTURE,
        segment_ref=_SEGMENT,
        extractor_ref=signal.producer_ref,
        occurrences=[registered],
    ).mention_id_for(registered)
    assert bound.participants[0].mention_ref == expected
    # A derived id, so the record is new — and it says which address it came from, because an
    # address nobody can recover from the record is a record nobody can audit (I-3).
    assert bound.signal_id != signal.signal_id
    assert bound.extra["bound_participants"] == tuple(
        p.mention_ref for p in signal.participants
    )
    assert signal.participants[0].mention_ref in bound.notes
    # And nothing else about the end moved: the slot says which end this is, and the role
    # hypothesis and ordinal are what the producer read, neither of which is a function of the
    # mention id the end became.
    assert [p.slot for p in bound.participants] == [p.slot for p in signal.participants]
    assert [p.role_hypothesis for p in bound.participants] == [
        p.role_hypothesis for p in signal.participants
    ]


def test_binding_is_order_independent_and_pairs_back_to_the_input() -> None:
    """Constitution VI on the binder, and the property a caller depends on to zip the result.

    The returned tuple is in **input** order so a caller can pair it against what it passed in,
    and the pairing is by the *pre-binding* id, because that is the only handle the caller has —
    the bound signal's own id is a different string. Two processes handed the same signals in
    different orders get the same bindings, and the same answers in the same slots.
    """
    signals = (
        _signal(
            deferred_occurrence(label="subject", surface="Acme", start=0, end=4),
            deferred_occurrence(label="object", surface="Microsoft", start=5, end=14),
            producer_ref="prose/one",
        ),
        _signal(
            deferred_occurrence(label="subject", surface="Initech", start=0, end=7),
            deferred_occurrence(label="object", surface="Acme", start=8, end=12),
            surface="acquired",
            producer_ref="prose/two",
        ),
    )
    forwards = bind_producer_signals(
        signals, capture_ref=_CAPTURE, segment_ref=_SEGMENT
    )
    backwards = bind_producer_signals(
        list(reversed(signals)), capture_ref=_CAPTURE, segment_ref=_SEGMENT
    )
    assert forwards == backwards, "the binding must not depend on the order the signals arrived in"
    assert [b.signal_id for b in forwards] == [b.signal_id for b in backwards]
    # Input order, paired position for position, and each bound signal records the address it
    # came from so the pairing is checkable from the records alone.
    assert [b.extra["bound_participants"] for b in forwards] == [
        tuple(p.mention_ref for p in s.participants) for s in signals
    ]
    assert forwards[0] != signals[0], "a bound signal is a new record"


def test_an_unpositioned_address_resolves_only_where_the_surface_is_unique() -> None:
    """The rule, on both sides, and neither side is a guess.

    The syntactic producer's positions are clause-relative token indices, so its addresses are the
    unpositioned form with no character span: there is nothing to *register*, so a
    per-producer index cannot hold them and the only index with positions for the segment is the
    mention layer's. There an unpositioned address resolves when the segment holds that surface
    **exactly once** — and is refused when it holds it more than once, because resolving would
    mean picking a position the producer never stated. The index will not choose an order to
    break that tie and neither does this.
    """
    signal = _signal(
        deferred_occurrence(label="nsubj", surface="Acme"),
        deferred_occurrence(label="obj", surface="Microsoft"),
    )
    once = _index(
        MentionOccurrence(kind="org", surface="Acme", start=0, end=4),
        MentionOccurrence(kind="org", surface="Microsoft", start=5, end=14),
    )
    bound = bind_producer_signals(
        [signal], capture_ref=_CAPTURE, segment_ref=_SEGMENT, mention_index=once
    )[0]
    assert all(p.mention_ref.startswith(MENTION_ID_PREFIX) for p in bound.participants)
    assert len({p.mention_ref for p in bound.participants}) == 2, (
        "two distinct surfaces in one segment resolve to two distinct mentions"
    )

    twice = _index(
        MentionOccurrence(kind="org", surface="Acme", start=0, end=4),
        MentionOccurrence(kind="org", surface="Acme", start=20, end=24),
        MentionOccurrence(kind="org", surface="Microsoft", start=5, end=14),
    )
    with pytest.raises(SignalContractError) as caught:
        bind_producer_signals(
            [signal], capture_ref=_CAPTURE, segment_ref=_SEGMENT, mention_index=twice
        )
    assert caught.value.code == "participant_address_unresolved"
    assert "mention_occurrence_ambiguous" in str(caught.value)
    assert "do not take the first match" in str(caught.value)


def test_an_unpositioned_address_with_no_index_is_refused_by_name() -> None:
    """The stop condition, stated where an operator will read it.

    Refusing with ``mention_occurrence_unresolved`` because the index is empty would be true
    and useless — it would send an operator to register an occurrence when the real problem is
    that this producer has no positions at all. The code names the producer's own limitation and
    the two ways out.
    """
    signal = _signal(
        deferred_occurrence(label="nsubj", surface="Acme"),
        deferred_occurrence(label="obj", surface="Microsoft"),
    )
    with pytest.raises(SignalContractError) as caught:
        bind_producer_signals([signal], capture_ref=_CAPTURE, segment_ref=_SEGMENT)
    assert caught.value.code == "participant_occurrence_unpositioned"
    message = str(caught.value)
    assert "unpositioned" in message
    assert "clause-relative token indices" in message
    assert "do not pick a position" in message
    assert "deferred_occurrence(..., start=, end=)" in message


def test_binding_refuses_a_blank_capture_rather_than_minting_under_an_invented_scope() -> None:
    """A mention address is five keys and the capture is the first of them.

    Binding without one would mint ids that cannot say which retrieval produced them — the
    collision the capture key was added to prevent, arriving by another route (FR-018). The
    refusal names the fix rather than defaulting a scope, because a placeholder index resolves
    nothing while looking as though it had been consulted.
    """
    signal = lexical_signals(["John Smith became CEO of Acme."], scope=_scope())[0]
    for blank in ("", "   "):
        with pytest.raises(SignalContractError) as caught:
            bind_producer_signals([signal], capture_ref=blank, segment_ref=_SEGMENT)
        assert caught.value.code == "participant_capture_required"
        assert "STOP" in str(caught.value)
    with pytest.raises(SignalContractError) as no_segment:
        bind_producer_signals([signal], capture_ref=_CAPTURE, segment_ref="")
    assert no_segment.value.code == "participant_segment_required"


def test_a_capture_end_survives_binding_unchanged_and_is_not_minted() -> None:
    """C4's decision, exercised through the binding the golden path actually uses.

    The metadata producer's document end is a **retrieval**, not an occurrence: a capture id is
    already a real content-addressed durable id (:class:`domain.capture.Capture`), so minting a
    mention for it would put a second identity on one fact (I-2). It passes through as itself,
    and the mention layer's index is never asked about it — asking would be asking for a
    binding that was never made.
    """
    head = '<head><meta name="author" content="jane@acme.example"></head>'
    signal = metadata_signals([head], scope=_scope())[0]
    capture_end, value_end = (p.mention_ref for p in signal.participants)
    assert capture_end == mint_capture_address(_CAPTURE)
    _label, _surface, span = read_occurrence(value_end)
    assert span is not None, value_end
    bound = bind_producer_signals(
        [signal], capture_ref=_CAPTURE, segment_ref=_SEGMENT
    )[0]
    assert bound.participants[0].mention_ref == capture_end
    assert bound.participants[0].mention_ref.startswith(f"{DEFERRED_CAPTURE_PREFIX}:")
    assert not bound.participants[0].mention_ref.startswith(MENTION_ID_PREFIX)
    assert bound.participants[1].mention_ref.startswith(MENTION_ID_PREFIX)
    assert bound.extra["bound_participants"] == (capture_end, value_end)


def test_a_producer_contradicting_itself_over_its_own_occurrences_is_refused() -> None:
    """Two ends claiming one position with different surfaces is a contradiction, not a merge.

    The per-producer index is built by registering what the producer read, so a producer that
    read two different strings at the same offsets is caught by the index's own
    ``mention_span_disagreement`` — and the index is right to: choosing between them is the
    arbiter's decision and not the binder's. Asserted because "register what the producer read"
    is a decision that could have been "register what the producer read, mostly".
    """
    signal = _signal(
        deferred_occurrence(label="subject", surface="Acme", start=0, end=4),
        deferred_occurrence(label="object", surface="Acme Corp", start=0, end=4),
    )
    with pytest.raises(SignalContractError) as caught:
        bind_producer_signals([signal], capture_ref=_CAPTURE, segment_ref=_SEGMENT)
    assert caught.value.code == "participant_address_unresolved"
    assert "mention_span_disagreement" in str(caught.value)
    assert "STOP" in str(caught.value)


def test_two_producers_get_two_indexes_and_never_collide() -> None:
    """One index per ``(capture, segment, extractor)``, which is the collision the key prevents.

    Two producers reading the same text at the same offsets are two mentions, not one, because
    the extractor ref is one of the five keys. If the binding pooled them, the second producer
    would either be refused as a ``kind`` disagreement or would address the first producer's
    mention — and FR-034's independence count would be wrong in both directions.
    """
    scope = _scope()
    text = "John Smith became CEO of Acme."
    prose = run_producer(LexicalCueExtractor(), [text], scope=scope)
    markup = run_producer(
        HyperlinkExtractor(), ['<p>See <a href="https://acme.example/team">the team</a>.</p>'],
        scope=scope,
    )
    prose_bound = bind_producer_signals(
        prose, capture_ref=_CAPTURE, segment_ref=_SEGMENT
    )[0]
    markup_bound = bind_producer_signals(
        markup, capture_ref=_CAPTURE, segment_ref=_SEGMENT
    )[0]
    assert prose_bound.participants[0].mention_ref != markup_bound.participants[0].mention_ref
    assert prose_bound.participants[0].mention_ref.startswith(MENTION_ID_PREFIX)
    assert markup_bound.participants[0].mention_ref.startswith(MENTION_ID_PREFIX)
    # Binding them together is a *grouping* decision a caller may make; what must not happen
    # is one producer's occurrence being minted under the other's extractor key.
    with pytest.raises(SignalContractError) as pooled:
        producer_occurrence_index(
            (*prose, *markup), capture_ref=_CAPTURE, segment_ref=_SEGMENT
        )
    assert pooled.value.code == "producer_scope_ambiguous"
    for ref in ("lexical/cue-phrase", "structural/hyperlink"):
        assert ref in pooled.value.message, pooled.value.message


def test_the_parser_addresses_its_arguments_through_the_one_minter() -> None:
    """**This test used to be the tripwire for a live defect, and is now the tripwire for its fix.**

    :mod:`parsers.shallow` used to build ``f"surface:{label}:{address}"`` itself while the grammar
    defined ``label`` as the text up to the first ``:``. Its labels are dependency arcs and several
    contain the separator — ``nmod:of``, ``nmod:in``, ``nmod:by``, ``nsubj:pass`` — so it minted
    ``surface:nmod:of:acme``, which the grammar read as label ``nmod`` and surface ``of:acme``: a
    *different address from the one the parser meant*, and one the index could not find. The
    platform could not tell a misparse from a surface that genuinely contains a colon, so the
    answer was fail-closed and this file recorded the defect so it could not be forgotten.

    What replaced it is not a narrower rule — not a ban on colons, not a rarer separator, not a
    restriction on what a label may be — but an **injective encoding**: the parser mints through
    :func:`domain.mention_occurrence_index.mint_occurrence_address`, whose fields are the
    platform's own ``canonical_material`` and whose frame carries that material's ``digest128``.
    So there is no separator in the payload to collide with, and the assertions below are the
    positive form of the old negative one: the addresses now read back as the arcs they are.

    Two halves. The parser's own output, on a clause whose PP adjunct is exactly the label that
    used to break; and a real binding, which under the retired grammar could not have resolved.
    """
    from extractors.signals.syntactic import syntactic_signals

    scope = _scope()
    produced = syntactic_signals(["John is the CEO of Acme."], scope=scope).signals
    assert produced, "the syntactic producer found nothing in a clause it can read"
    read_back = {p.mention_ref: read_occurrence(p.mention_ref) for p in produced[0].participants}
    labels = {entry[0] for entry in read_back.values()}
    assert "nmod:of" in labels, (
        "this test exists because the parser's dependency-arc labels are outside the retired "
        f"address grammar and misparsed; the addresses read back as {read_back} and if the "
        "parser has been fixed this test is the tripwire that says so"
    )
    # The arc is the arc. Under the retired grammar this read back as ``("nmod", "of:acme")``.
    assert read_occurrence(_nmod_arc_ref(produced)) == ("nmod:of", "acme", None)
    # And every address the parser writes is in the *current* encoding, so a consumer that knows
    # the version can refuse the rest rather than guess. The frame's version component is
    # asserted because it is what makes a pre-change store a named refusal; without it the
    # retired strings would have to be recognised some other way.
    for reference in read_back:
        assert f":{DEFERRED_ADDRESS_VERSION}:" in reference, reference

    # And it resolves. The index holds the two overt occurrences, the object end is positioned by
    # the mention layer and the adjunct by its own surface, and a binding that used to be refused
    # with ``of:acme`` in the message now produces two real mention ids.
    index = _index(
        MentionOccurrence(kind="person", surface="John", start=0, end=4),
        MentionOccurrence(kind="org", surface="Acme", start=19, end=23),
    )
    bound = bind_producer_signals(
        produced, capture_ref=_CAPTURE, segment_ref=_SEGMENT, mention_index=index
    )[0]
    assert all(p.mention_ref.startswith(MENTION_ID_PREFIX) for p in bound.participants), (
        [p.mention_ref for p in bound.participants]
    )
    # Two distinct surfaces, two distinct mentions, and the deferred addresses are still readable
    # in the record, so the address that became an id is recoverable.
    assert len({p.mention_ref for p in bound.participants}) == 2
    assert set(bound.extra["bound_participants"]) == set(read_back)


def _nmod_arc_ref(signals: tuple[object, ...]) -> str:
    """The one participant reference whose label is the dependency arc ``nmod:of``."""
    for signal in signals:
        for participant in getattr(signal, "participants", ()):
            if read_occurrence(participant.mention_ref)[0] == "nmod:of":
                return str(participant.mention_ref)
    raise AssertionError(f"no nmod:of argument in {[s.signal_id for s in signals]}")


def test_the_producer_side_contract_is_unchanged_and_still_not_a_mention_id() -> None:
    """brief §25 and FR-019, after the seam: the producer still mints a **deferred** reference.

    Adding a resolver must not quietly upgrade a producer into a mention minter. So the addresses a
    producer emits are still ``surface:``/``capture:``, still produced by
    :mod:`extractors.signals.mentions` and by nothing else, and still never ``MN-``. The binding
    is a separate call over a signal that is already written.

    **The count this asserts is one where it used to be two.** :mod:`parsers.shallow` was a second
    producer-side module holding a ``surface:`` literal, and building the string itself against a
    grammar that split the label on the first ``:`` is what made ``nmod:of`` an address of
    ``of:acme``. The parser now reaches the grammar by importing
    :func:`domain.mention_occurrence_index.mint_occurrence_address`, and the whole-tree scan that
    proves no other module builds an address is
    ``apps/shared/tests/unit/test_mention_occurrence_index.py::test_the_mint_and_the_parse_are_
    defined_once_each_and_nothing_else_builds_an_address``. What is asserted here is the
    producer-package half: five modules hold the literal — and the parser is not among them.
    """
    text = "John Smith became CEO of Acme."
    signal = lexical_signals([text], scope=_scope())[0]
    for reference in (p.mention_ref for p in signal.participants):
        assert reference.startswith(f"{DEFERRED_OCCURRENCE_PREFIX}@")
        assert not reference.startswith(MENTION_ID_PREFIX)
    # And the capture end is a real capture address, not a mention either.
    assert deferred_capture(capture_ref=_CAPTURE) == mint_capture_address(_CAPTURE)
    assert not deferred_capture(capture_ref=_CAPTURE).startswith(MENTION_ID_PREFIX)
    # One module mints the deferred grammar, and the seam did not add a second: the four
    # producers that need one *call* the helper, and :mod:`mentions` is where it is defined.
    package = APP / "extractors" / "signals"
    minters = {
        module.name
        for module in sorted(package.glob("*.py"))
        if "deferred_occurrence(" in module.read_text(encoding="utf-8")
    }
    assert minters == {"lexical.py", "links.py", "mentions.py", "metadata.py", "tables.py"}
    # The parser, which drives the syntactic producer and once minted its own addresses, holds
    # no namespace literal and reaches the domain minter by import instead.
    parser = (APP / "parsers" / "shallow.py").read_text(encoding="utf-8")
    parser_tree = ast.parse(parser)
    assert not [
        node
        for node in ast.walk(parser_tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value not in {
            ast.get_docstring(node, clean=False)
            for node in ast.walk(parser_tree)
            if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef)
        }
        and any(prefix in node.value for prefix in ("surface:", "capture:"))
    ], "parsers/shallow.py builds a deferred address itself, which is the collision"
    assert "mint_occurrence_address(" in parser
    # And the seam's own module mints no ``MN-`` at all - asserted on the AST, because its
    # docstring names the prefix repeatedly and prose is supposed to.
    seam_tree = ast.parse((package / "mentions.py").read_text(encoding="utf-8"))
    docstrings = {
        ast.get_docstring(node, clean=False)
        for node in ast.walk(seam_tree)
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef)
    }
    assert not [
        node
        for node in ast.walk(seam_tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value not in docstrings
        and MENTION_ID_PREFIX in node.value
    ]


def test_the_producer_side_imports_nothing_above_the_extraction_layer() -> None:
    """FR-020 / FR-073 as a source scan, because an import that has been made is not undone by prose.

    Nothing under ``extractors/`` or ``parsers/`` may reach the graph, the claim layer, admission or
    projection. Two reasons and they are different: those layers sit **above** extraction, so the
    edge inverts the layering; and a producer that imported a claim symbol could decide something
    that belongs to admission with no ``ResolutionDecisionRecord`` behind it. The scan reads
    ``import`` / ``from`` statements, so a docstring *naming* a forbidden module — which several of
    these modules do, at length, because they are all about not doing it — cannot read as a use.
    """
    forbidden = ("graph", "db", "services", "admission", "projection", "api", "semantic_path")
    offenders: list[str] = []
    for root in (APP / "extractors", APP / "parsers"):
        for module in sorted(root.rglob("*.py")):
            tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
            for node in ast.walk(tree):
                names: list[str] = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    names = [node.module]
                for name in names:
                    if name.split(".")[0] in forbidden:
                        offenders.append(f"{module.name}:{node.lineno} imports {name}")
    assert not offenders, "a producer reaches above the extraction layer:\n  " + "\n  ".join(
        sorted(offenders)
    )
    # And the seam's own module imports only downward: the domain value types, the signal contract
    # it shares with its own package, and the standard library.
    from extractors.signals import mentions as seam

    imported = {
        node.module or ""
        for node in ast.walk(ast.parse(Path(seam.__file__).read_text(encoding="utf-8")))
        if isinstance(node, ast.ImportFrom)
    }
    assert imported <= {
        "__future__",
        "collections.abc",
        "dataclasses",
        "domain.mention_occurrence_index",
        # Phase 4C: the binder reads the participant's own declared end kind (C4's decision)
        # rather than sniffing the address, and that value type lives in `domain`. Still
        # strictly downward — `domain` is below both apps.
        "domain.relation_participant",
        "extractors.signals.signal",
    }, imported
    # Nothing from the composition root, which is the inversion the location exists to avoid.
    assert "semantic_path" not in imported
