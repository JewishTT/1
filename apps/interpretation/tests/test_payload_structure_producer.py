"""S3, S4, S5: relation signals from structure, resolved mentions, and truncation that propagates.

Feature 021 brief §16 (``SignalBasis`` answers "how do you know?"), §25 (a producer below mention
extraction), §26 (:mod:`domain.mention_occurrence_index` is the mention seam); spec FR-008
(``participants`` is canonical and variadic), FR-009 (``RelationParticipant``'s six fields), FR-014
(``basis``), FR-016/FR-018/FR-019 (mention binding), FR-041…FR-043 (the neighbourhood);
``ARBITRATION`` §8; constitution IV (fail-closed) and VI (determinism, Domain Invariant 12).

**What is being tested, and why each of these is a property rather than a shape.**

* **S3 — structure, with the basis named.** A JSON object is binary: a container states a member,
  basis ``ATTRIBUTE_KEY``. A JSON array is a **member set**, and a member set is *not* n-ary: one
  binary signal per element, basis ``DOM_RELATION``. Empty, singleton and many are each asserted
  against the rule this stage's docstring states, because those are the two array cases that make
  most array code wrong.
* **S4 — mentions are resolved, not assumed.** Every participant carries a real ``MN-`` resolved
  through :class:`domain.mention_occurrence_index.MentionOccurrenceIndex`, checked here against the
  index's **own** inverse rather than a re-derivation. A record whose address cannot be resolved is
  **excluded and counted**, and the counting is what makes the exclusion checkable.
* **S5 — truncation propagates.** A bounded walk's signals must be indistinguishable from a whole
  payload's *only if* someone throws the address away, and the test proves it the only way that
  counts: by showing the two do not share a ``signal_id``.
* **Determinism.** The same payload in two child interpreters with different ``PYTHONHASHSEED``
  values, because an in-process comparison cannot see a set or dict iteration order.
"""

from __future__ import annotations

import ast
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

import pytest
from domain.signal_basis import SignalBasis

from extractors.payload.structure import (
    INDEPENDENCE_FAMILY,
    MAX_CONTAINER_SURFACE_BYTES,
    MAX_PAIRS_CONSIDERED,
    PRECISION_BOUNDED,
    PRECISION_WHOLE,
    PRODUCER_REF,
    PRODUCER_VERSION,
    SIGNAL_REFUSAL_CODES,
    MemberOutcome,
    MemberOutcomeCode,
    MemberSetKind,
    PayloadReading,
    PayloadStructureExtractor,
    ReadingContractError,
    SignalRefusalCode,
    payload_occurrence_index,
    read_payload_structure,
)
from extractors.signals.mentions import deferred_occurrence
from extractors.signals.protocol import ExtractionScope, run_producer
from extractors.signals.signal import SignalContractError, SignalKind
from parsers.payload import (
    ObservedField,
    ParseBounds,
    ValueType,
    bind_records,
    default_registry,
)

pytestmark = pytest.mark.unit

APPS = Path(__file__).resolve().parents[2]
INTERPRETATION = APPS / "interpretation"
_COPIED = (
    ("interpretation", ("extractors", "parsers", "semantic", "contracts.py")),
    ("shared", ("domain", "semantic")),
)

CAPTURE = "CAP-7d2f0c1a9b3e4d5f6a7b8c9d0e1f2a3b"
SEGMENT = "SEG-body-1"
EXTRACTOR = "parsers/payload"

_BODY = b'{"registrant": {"email": "jane@acme.example", "name": "Acme Ltd"}}'


def _scope(document_ref: str = CAPTURE) -> ExtractionScope:
    return ExtractionScope(
        tenant_id="tenant-a",
        context_ref="CTX-1",
        semantic_regime_ref="RG-1",
        document_ref=document_ref,
    )


def parse(body: bytes, **over: object):
    arguments: dict[str, object] = {
        "body": body,
        "content_type": "application/json",
        "declared_parser": "structured_fields",
    }
    arguments.update(over)
    return default_registry().parse(**arguments)


def reading_of(
    body: bytes,
    *,
    capture_ref: str = CAPTURE,
    segment_ref: str = SEGMENT,
    extractor_ref: str = EXTRACTOR,
    bound_capture_ref: str | None = None,
    bound_extractor_ref: str | None = None,
    **over: object,
) -> PayloadReading:
    """A payload, its bytes, and a binding a caller produced for the *same* three-key scope."""
    payload = parse(body, **over)
    bound = bind_records(
        payload,
        capture_ref=bound_capture_ref or capture_ref,
        segment_ref=segment_ref,
        extractor_ref=bound_extractor_ref or extractor_ref,
    )
    return PayloadReading(
        payload=payload,
        body=body,
        bound=bound,
        capture_ref=capture_ref,
        segment_ref=segment_ref,
        extractor_ref=extractor_ref,
    )


def structural(body: bytes, *, scope: ExtractionScope | None = None, **over: object):
    return read_payload_structure(reading_of(body, **over), scope=scope or _scope())


def container_address(reading: PayloadReading, record: ObservedField) -> str:
    """The address this stage mints for a container, recomputed by the test from the bytes.

    The test does not take the stage's word for it: it slices the payload with the parser's own
    :meth:`ParsedPayload.read_span` and mints with the producer-side contract, so a stage that
    addressed a container somewhere else fails here.
    """
    text = reading.payload.read_span(reading.body, record)
    label = "json_object_container" if text[:1] == "{" else "json_array_container"
    start, end = record.byte_span
    return deferred_occurrence(label=label, surface=text, start=start, end=end)


# --------------------------------------------------------------------------- #
# S3: ATTRIBUTE_KEY — a container states a member
# --------------------------------------------------------------------------- #


def test_an_attribute_key_signal_names_two_resolved_mentions_and_leaves_the_operator_unset() -> None:
    result = structural(_BODY)
    assert len(result.signals) == 2
    signal = result.signals[0]
    assert signal.basis is SignalBasis.ATTRIBUTE_KEY
    assert signal.kind is SignalKind.ATTRIBUTE
    assert signal.relation_ref is None, (
        "a key is not an operator; setting relation_ref would be this producer claiming to know "
        "the predicate, which is the fabrication relation_signal's own docstring forbids"
    )
    assert signal.arity == 2, "a JSON object is binary: a container and a field"
    assert [p.slot.token for p in signal.participants] == ["A0", "A1"]
    for participant in signal.participants:
        assert participant.mention_ref.startswith("MN-"), (
            "a participant must be a resolved mention, not a deferred address this stage assumed"
        )


def test_every_participant_resolves_back_through_the_indexs_own_inverse() -> None:
    """Checked against :meth:`MentionOccurrenceIndex.require_occurrence`, not a re-derivation.

    A test that recomputed the expected id itself would agree with a bug in the same direction, so
    the expectation comes from the address each record carries and the index the reading built.
    """
    reading = reading_of(_BODY)
    result = read_payload_structure(reading, scope=_scope())
    index = payload_occurrence_index(reading)
    by_path = {entry.field: entry for entry in reading.bound.bound}
    assert len(result.signals) == len(by_path), "one signal per addressable member, and no other"
    for signal in result.signals:
        member_path = signal.extra["field_path"]
        container_path = signal.extra["container_path"]
        container_record = next(
            record for record in reading.payload.records if record.field == container_path
        )
        container_resolved = index.require_occurrence(container_address(reading, container_record))
        assert signal.participants[0].mention_ref == container_resolved.mention_id
        member_resolved = index.require_occurrence(by_path[member_path].address)
        assert signal.participants[1].mention_ref == member_resolved.mention_id
        assert member_resolved.mention_id == by_path[member_path].mention_id, (
            "this stage's index and the caller's binding must mint the same mention id, or they "
            "were built for different scopes"
        )


def test_the_signals_are_in_document_order_and_carry_a_document_order_ordinal() -> None:
    result = structural(_BODY)
    assert [s.extra["field_path"] for s in result.signals] == [
        '$["registrant"]["email"]',
        '$["registrant"]["name"]',
    ]
    assert [s.signal_ordinal for s in result.signals] == [0, 1]


def test_the_container_mention_is_a_mention_of_the_containers_own_bytes() -> None:
    """The subject end is real text at a real position, and that is checkable by slicing.

    A container has no value of its own — the parser says so — so a subject end for it has to be
    built from something the payload states. It is the container's own text at the container's own
    byte span, which means ``ParsedPayload.read_span`` returns the mention's surface, and a
    synthetic key-path "surface" that appears nowhere in the bytes is not an option.
    """
    reading = reading_of(_BODY)
    result = read_payload_structure(reading, scope=_scope())
    index = payload_occurrence_index(reading)
    container = next(r for r in reading.payload.records if r.field == '$["registrant"]')
    text = reading.payload.read_span(reading.body, container)
    assert text.startswith("{") and text.endswith("}")
    resolved = index.require_occurrence(container_address(reading, container))
    assert resolved.occurrence.surface == text
    assert resolved.occurrence.start == container.byte_span[0]
    assert resolved.occurrence.end == container.byte_span[1]
    assert all(
        signal.participants[0].mention_ref == resolved.mention_id for signal in result.signals
    )


def test_relation_surface_is_the_payloads_own_key_path_and_not_an_invented_verb() -> None:
    """There is no verb in a JSON document, and filling the field with one is a fabrication.

    ``relation_surface`` is the key path the observation is about — a real artifact of the
    payload's grammar, not a word this producer chose. ``relation_surface_kind`` names that in the
    record, and the notes say the same thing in prose.
    """
    result = structural(_BODY)
    signal = result.signals[0]
    assert signal.relation_surface == '$["registrant"]["email"]'
    assert signal.extra["relation_surface_kind"] == "key_path"
    assert signal.predicate_hypothesis is not None
    assert signal.predicate_hypothesis.relation_ref is None
    assert "key path" in signal.notes
    assert "declines to name the operator" in signal.notes


def test_the_neighbourhood_states_what_was_actually_read() -> None:
    """A structural producer reads a container and a member, and compares no pair of mentions."""
    result = structural(_BODY)
    neighbourhood = result.signals[0].neighbourhood
    assert neighbourhood.pairs_considered == 0
    assert "No other document" in neighbourhood.scope_read
    assert neighbourhood.is_exhaustive is False
    assert "read once for the whole container" in neighbourhood.notes
    reading = reading_of(_BODY)
    container = next(r for r in reading.payload.records if r.field == '$["registrant"]')
    member = next(r for r in reading.payload.records if r.field == '$["registrant"]["email"]')
    assert neighbourhood.characters_scanned == (
        container.byte_span[1] - container.byte_span[0]
        + member.byte_span[1] - member.byte_span[0]
    )


def test_the_producer_declares_what_it_reads_what_it_cannot_read_and_what_it_refuses() -> None:
    declaration = PayloadStructureExtractor(reading_of(_BODY)).declares()
    assert declaration.producer_ref == PRODUCER_REF
    assert declaration.producer_version == PRODUCER_VERSION
    assert declaration.independence_family == INDEPENDENCE_FAMILY
    assert declaration.max_pairs_considered == MAX_PAIRS_CONSIDERED
    assert set(declaration.kinds) == {SignalKind.ATTRIBUTE, SignalKind.STRUCTURAL}
    assert "unary" in declaration.cannot_read
    assert "verb" in declaration.cannot_read
    assert "relation_ref" in declaration.notes


def test_every_emitted_signal_is_within_the_declared_pair_ceiling() -> None:
    """``assert_bounded`` runs on the way out, so a producer cannot lie about its extent."""
    producer = PayloadStructureExtractor(reading_of(_BODY))
    signals = run_producer(producer, (producer.reading.payload,), scope=_scope())
    assert signals
    ceiling = producer.declares().max_pairs_considered
    assert all(signal.neighbourhood.pairs_considered <= ceiling for signal in signals)


# --------------------------------------------------------------------------- #
# S3: DOM_RELATION — an array is a member set, not an n-ary relation
# --------------------------------------------------------------------------- #


def test_an_empty_member_set_emits_no_signal_and_is_recorded_as_empty() -> None:
    """The first of the two cases that make array code wrong.

    An empty array is a fact the payload states — a key whose value is a set with nothing in it.
    Emitting nothing is right; emitting nothing *silently* is not, so the set is recorded with its
    path and its emptiness and a caller can tell it from a key that was never there.
    """
    result = structural(b'{"aliases": []}')
    assert result.signals == ()
    assert len(result.member_sets) == 1
    entry = result.member_sets[0]
    assert entry.key_path == '$["aliases"]'
    assert entry.kind is MemberSetKind.EMPTY
    assert entry.element_paths == ()
    outcomes = {o.key_path: o.code for o in result.member_outcomes}
    assert outcomes['$["aliases"]'] is MemberOutcomeCode.EMPTY_CONTAINER


def test_a_singleton_member_set_is_still_a_member_set_and_not_a_scalar() -> None:
    """The second of the two cases.

    ``["jane"]`` is a one-element list, not a string. Code that collapses a one-element list onto
    its element reports a payload that stated a set as though it stated a value, and the
    distinction is unrecoverable afterwards. Here it is one signal of exactly the shape the
    many-element case produces, and the singleton kind is recorded.
    """
    result = structural(b'{"aliases": ["jane"]}')
    assert len(result.signals) == 1
    signal = result.signals[0]
    assert signal.basis is SignalBasis.DOM_RELATION
    assert signal.kind is SignalKind.STRUCTURAL
    assert signal.arity == 2, "one element is one binary membership, not a one-ary relation"
    assert signal.relation_ref is None
    assert result.member_sets[0].kind is MemberSetKind.SINGLETON
    assert result.member_sets[0].element_paths == ('$["aliases"][0]',)


def test_a_many_element_member_set_is_one_binary_signal_per_element() -> None:
    result = structural(b'{"aliases": ["a", "b", "c"]}')
    assert len(result.signals) == 3
    assert all(signal.arity == 2 for signal in result.signals)
    assert all(signal.basis is SignalBasis.DOM_RELATION for signal in result.signals)
    assert result.member_sets[0].kind is MemberSetKind.MANY
    assert result.member_sets[0].element_paths == (
        '$["aliases"][0]',
        '$["aliases"][1]',
        '$["aliases"][2]',
    )


def test_ordinal_distinguishes_array_positions_and_is_in_the_signal_address() -> None:
    """The position the payload states wins over the position in the tuple, and it is hashed.

    ``RelationParticipant.ordinal`` is documented as *position as observed*, so an array element
    carries its index. ``to_identity`` includes ``ordinal``, so two elements of one array are two
    signals — and the second half of this test proves it by moving the ordinal and watching the
    address change, which is the assertion that would catch ``ordinal`` being dropped from the
    identity projection.
    """
    result = structural(b'{"aliases": ["a", "b"]}')
    first, second = result.signals
    assert [p.ordinal for p in first.participants] == [0, 0]
    assert [p.ordinal for p in second.participants] == [0, 1]
    assert first.signal_id != second.signal_id
    moved = replace(
        first,
        participants=(
            first.participants[0],
            replace(first.participants[1], ordinal=second.participants[1].ordinal),
        ),
        signal_id="",
    )
    assert moved.participants[1].mention_ref == first.participants[1].mention_ref
    assert moved.signal_id != first.signal_id, (
        "moving a participant's ordinal did not change the address, so a payload's array positions "
        "are not part of what the signal says it observed"
    )


def test_a_nested_array_is_still_binary_at_each_level() -> None:
    result = structural(b'{"rows": [["a", "b"], ["c"]]}')
    assert len(result.signals) == 3
    assert all(signal.arity == 2 for signal in result.signals)
    assert [entry.kind for entry in result.member_sets] == [
        MemberSetKind.MANY,
        MemberSetKind.MANY,
        MemberSetKind.SINGLETON,
    ]


def test_a_container_whose_own_elements_are_containers_states_no_membership_of_its_own() -> None:
    """An array of objects states that it holds objects, not what the objects are.

    Each inner object states its own members. The outer set's own members are containers with no
    value of their own, so they are excluded and counted as containers rather than joining a
    membership signal with a surface they do not have.
    """
    result = structural(b'{"rows": [{"a": 1}, {"a": 2}]}')
    assert [s.extra["field_path"] for s in result.signals] == [
        '$["rows"][0]["a"]',
        '$["rows"][1]["a"]',
    ]
    assert [s.extra["container_path"] for s in result.signals] == [
        '$["rows"][0]',
        '$["rows"][1]',
    ]
    assert [s.basis for s in result.signals] == [SignalBasis.ATTRIBUTE_KEY] * 2
    outcomes = {o.key_path: o.code for o in result.member_outcomes}
    assert outcomes['$["rows"][0]'] is MemberOutcomeCode.CONTAINER_STATES_MEMBERS
    assert outcomes['$["rows"]'] is MemberOutcomeCode.CONTAINER_STATES_MEMBERS


# --------------------------------------------------------------------------- #
# S4: an end that cannot be resolved is excluded, and counted
# --------------------------------------------------------------------------- #


def test_a_record_whose_surface_normalises_to_nothing_is_excluded_and_counted() -> None:
    """``"..."`` normalises away, so the mention index refuses the address it carries.

    The exclusion is the correct outcome and the *count* is the point: a record that vanished would
    be indistinguishable from a payload that did not have one. This is the subtler of the two
    refusal shapes — the record has a well-formed address, and the index is what says no.
    """
    result = structural(b'{"dots": "...", "ip": "10.0.0.1"}')
    assert [s.extra["field_path"] for s in result.signals] == ['$["ip"]']
    # The root container is refused an address by the parser too, and the binding says so.
    assert [r.code for r in result.mention_refusals] == [
        "field_value_is_nested",
        "record_address_mint_refused",
    ]
    assert "dots" in result.mention_refusals[1].detail
    outcomes = {o.key_path: o.code for o in result.member_outcomes}
    assert outcomes['$["dots"]'] is MemberOutcomeCode.END_NOT_RESOLVED
    assert "mention_occurrence_surface_required" in result.refusal_details
    assert all(p.mention_ref.startswith("MN-") for s in result.signals for p in s.participants)


def test_a_record_whose_address_the_parser_refused_is_excluded_and_counted() -> None:
    """``null`` is the parser's own refusal, and it arrives with no address at all."""
    result = structural(b'{"gone": null, "ip": "10.0.0.1"}')
    assert [s.extra["field_path"] for s in result.signals] == ['$["ip"]']
    assert [r.code for r in result.mention_refusals] == [
        "field_value_is_nested",
        "field_value_is_null",
    ]
    outcomes = {o.key_path: o.code for o in result.member_outcomes}
    assert outcomes['$["gone"]'] is MemberOutcomeCode.VALUE_END_NOT_ADDRESSABLE
    refused = [r for r in result.signal_refusals if r.key_path == '$["gone"]']
    assert [r.code for r in refused] == [SignalRefusalCode.VALUE_END_NOT_ADDRESSABLE.value]
    assert "field_value_is_null" in refused[0].detail


def test_a_signal_is_never_built_from_a_binding_whose_ids_came_from_another_reading() -> None:
    """The cross-check, tested directly rather than through a mismatched scope.

    :class:`PayloadReading` already refuses a binding whose ``(capture, segment, extractor)`` triple
    disagrees with the reading's own, so the reachable case for this check is subtler: a
    :class:`BoundPayload` that *claims* the right scope and carries ids minted under another one.
    That is a hand-assembled record, a re-bound table, or a future refactor — and nothing about such
    a record looks wrong, because the ids are well formed and the scope strings agree. The only
    place the disagreement is visible is a comparison against the address each record carries,
    resolved through this reading's own index, which is what this stage performs.

    Without that check the signals would carry this stage's correct ids while the reading's
    ``bound`` table told a later stage something else, and the two would disagree with no trace.
    """
    reading = reading_of(_BODY)
    doctored = replace(
        reading.bound,
        bound=(
            replace(reading.bound.bound[0], mention_id="MN-0000000000000000000000000000000"),
            *reading.bound.bound[1:],
        ),
    )
    result = read_payload_structure(replace(reading, bound=doctored), scope=_scope())
    assert [s.extra["field_path"] for s in result.signals] == ['$["registrant"]["name"]'], (
        "the cross-check is per record, and the one member whose id agrees is still stated"
    )
    codes = {r.code for r in result.signal_refusals}
    assert codes == {SignalRefusalCode.MENTION_ID_SCOPE_MISMATCH.value}
    assert all(r.key_path for r in result.signal_refusals)
    outcomes = {o.key_path: o.code for o in result.member_outcomes}
    assert outcomes['$["registrant"]["email"]'] is MemberOutcomeCode.MENTION_ID_SCOPE_MISMATCH
    assert outcomes['$["registrant"]["name"]'] is MemberOutcomeCode.SIGNAL_EMITTED


def test_a_container_whose_own_text_is_over_the_ceiling_is_excluded_and_counted() -> None:
    """Boundedness, stated rather than assumed.

    A container's mention is addressed at its own bytes, so the extent of the read is the extent
    of the container. Past :data:`MAX_CONTAINER_SURFACE_BYTES` the stage declines rather than mint
    a mention of a quarter of a megabyte of JSON, and every member that would have named it is
    refused **by name** — a caller who hits this can see the ceiling, raise it, and know why the
    payload produced nothing.
    """
    wide = b'{"a": 1, "pad": "' + b"x" * (MAX_CONTAINER_SURFACE_BYTES + 16) + b'"}'
    result = structural(wide)
    assert result.signals == ()
    assert "container_surface_too_large" in result.refusal_codes
    outcomes = {o.key_path: o.code for o in result.member_outcomes}
    assert outcomes['$["a"]'] is MemberOutcomeCode.CONTAINER_SURFACE_TOO_LARGE
    assert outcomes['$["pad"]'] is MemberOutcomeCode.CONTAINER_SURFACE_TOO_LARGE
    assert result.truncated is False, "a ceiling of this stage is not the parser's truncation"


def test_a_container_whose_bytes_lie_outside_the_supplied_body_is_refused_not_guessed() -> None:
    """Fail-closed on a record and a body that disagree.

    ``ParsedPayload.read_span`` raises for a span past the end of a body, and the stage catches it
    and refuses the end. The alternative — reading the nearest bytes — would address a position
    nobody read, which is the one thing a mention must never be.
    """
    reading = reading_of(_BODY)
    broken = PayloadReading(
        payload=reading.payload,
        body=_BODY[:8],
        bound=reading.bound,
        capture_ref=CAPTURE,
        segment_ref=SEGMENT,
        extractor_ref=EXTRACTOR,
    )
    result = read_payload_structure(broken, scope=_scope())
    assert result.signals == ()
    assert "container_text_unavailable" in result.refusal_codes
    assert "field_byte_span_outside_payload" in result.refusal_details


def test_a_top_level_scalar_is_a_document_root_and_nothing_else() -> None:
    """A payload that is one string has a root, and a root is not a member of anything."""
    result = structural(b'"just a string"')
    assert result.signals == ()
    assert [o.code for o in result.member_outcomes] == [MemberOutcomeCode.DOCUMENT_ROOT]


# --------------------------------------------------------------------------- #
# S4: the reading is a partition, so nothing is dropped
# --------------------------------------------------------------------------- #


def test_every_record_gets_exactly_one_outcome_and_every_signal_is_one_of_them() -> None:
    """The mechanical form of "no record is dropped", carried across from the parser layer.

    ``len(member_outcomes) == len(payload.records)`` is checkable; "nothing was lost" is not. A
    scalar member is then either the object end of exactly one signal or named in a refusal, so
    the two sets of counts cannot both be right while the records are not.
    """
    result = structural(
        b'{"registrant": {"email": "a@b.c", "tags": [], "n": 1}, "zebra": "z", "gone": null}'
    )
    records = result.payload.records
    assert [o.key_path for o in result.member_outcomes] == [r.field for r in records]
    assert len(result.member_outcomes) == len(records)
    emitted = {
        o.key_path for o in result.member_outcomes if o.code is MemberOutcomeCode.SIGNAL_EMITTED
    }
    assert len(emitted) == len(result.signals) == 3
    named = {r.key_path for r in result.signal_refusals}
    scalars = {r.field for r in records if r.depth and r.value_type is not ValueType.NESTED}
    assert scalars <= emitted | named, (
        f"scalar members with neither a signal nor a named refusal: "
        f"{sorted(scalars - emitted - named)}"
    )
    assert emitted <= {s.extra["field_path"] for s in result.signals}


def test_a_record_whose_container_the_walk_never_closed_is_refused_rather_than_orphan_joined() -> None:
    """A bounded walk discards the containers it did not close, and their children are orphans."""
    result = structural(
        b"[" + b",".join(b"%d" % n for n in range(40)) + b"]",
        bounds=ParseBounds(max_nodes=8, max_records_per_value_type=100, max_depth=8),
    )
    assert result.signals == ()
    assert "container_record_absent" in result.refusal_codes
    assert result.member_outcomes
    assert all(
        outcome.code is MemberOutcomeCode.CONTAINER_RECORD_ABSENT
        for outcome in result.member_outcomes
    )
    assert len(result.member_outcomes) == len(result.payload.records)


def test_a_payload_that_is_not_json_is_refused_by_name_rather_than_read_as_structure() -> None:
    """A text payload's records are lines, and a line is not a key."""
    body = b"first line\nsecond line\n"
    payload = default_registry().parse(
        body=body, content_type="text/plain", parser_is_identity=True
    )
    bound = bind_records(
        payload, capture_ref=CAPTURE, segment_ref=SEGMENT, extractor_ref=EXTRACTOR
    )
    result = read_payload_structure(
        PayloadReading(
            payload=payload,
            body=body,
            bound=bound,
            capture_ref=CAPTURE,
            segment_ref=SEGMENT,
            extractor_ref=EXTRACTOR,
        ),
        scope=_scope(),
    )
    assert result.signals == ()
    assert [r.code for r in result.signal_refusals] == ["payload_not_structured"] * len(
        payload.records
    )
    assert {r.code for r in result.hypotheses.refusals} >= {"key_path_unreadable"}


def test_the_refusal_vocabulary_is_closed_and_every_member_outcome_is_a_declared_member() -> None:
    result = structural(b'{"a": {"b": 1}, "c": []}')
    assert set(SIGNAL_REFUSAL_CODES) == {code.value for code in SignalRefusalCode}
    for outcome in result.member_outcomes:
        assert isinstance(outcome, MemberOutcome)
        assert outcome.code in set(MemberOutcomeCode)
        assert outcome.code.value in {
            code.value for code in MemberOutcomeCode if code is outcome.code
        }


# --------------------------------------------------------------------------- #
# S5: truncation propagates, and a bounded read cannot pass for a whole one
# --------------------------------------------------------------------------- #

_BOUNDED_BODY = b'{"a": {"x": 1}, "b": 2, "c": 3, "d": 4}'
_BOUNDED = {"bounds": ParseBounds(max_nodes=5, max_records_per_value_type=100, max_depth=8)}


def test_a_truncated_payload_carries_its_truncation() -> None:
    result = structural(_BOUNDED_BODY, **_BOUNDED)
    assert result.truncated is True
    assert result.truncation_reason == "nodes_visited"
    assert result.bound_hit is not None
    assert result.bound_hit.ceiling == 5
    assert result.to_dict()["truncated"] is True
    whole = structural(_BOUNDED_BODY)
    assert whole.truncated is False
    assert whole.truncation_reason == ""
    assert whole.bound_hit is None


def test_a_truncated_payload_cannot_be_mistaken_for_a_whole_one() -> None:
    """The load-bearing half, and the reason truncation is in the address and not only in a field.

    ``Neighbourhood`` is part of a signal's identity material, so a bounded read and a whole read
    of the same structure cannot share a ``signal_id``. The first assertions are the end-to-end
    statement; the last proves the *mechanism*, by flipping the one field that carries the
    distinction and watching the address move.
    """
    bounded = structural(_BOUNDED_BODY, **_BOUNDED)
    assert len(bounded.signals) == 1, "the fixture must emit a signal for the assertion to bite"
    signal = bounded.signals[0]
    assert signal.neighbourhood.precision == PRECISION_BOUNDED
    assert signal.neighbourhood.is_exhaustive is False
    assert "nodes_visited" in signal.neighbourhood.notes
    assert signal.extra["payload_truncated"] is True
    whole = structural(_BOUNDED_BODY)
    assert whole.signals[0].neighbourhood.precision == PRECISION_WHOLE
    assert whole.signals[0].extra["payload_truncated"] is False
    assert not {s.signal_id for s in bounded.signals} & {s.signal_id for s in whole.signals}
    relabelled = replace(
        signal,
        neighbourhood=replace(signal.neighbourhood, precision=PRECISION_WHOLE, notes=""),
        signal_id="",
    )
    assert relabelled.signal_id != signal.signal_id, (
        "truncation reached a field but not the address, so a bounded read is indistinguishable "
        "from a whole one to anything that keys on signal_id"
    )


def test_a_whole_payload_never_claims_an_exhaustive_scan() -> None:
    """Absence is not claimed from a record set, because the record set is not the document.

    A payload can be a partial body the source chose to send, and nothing on the path from bytes to
    records can tell that from a complete one, so ``is_exhaustive`` is ``False`` on every signal
    this stage emits and a reader is left to weigh it.
    """
    result = structural(b'{"a": 1, "b": {"c": 2}}')
    assert result.signals
    assert all(not signal.neighbourhood.is_exhaustive for signal in result.signals)


# --------------------------------------------------------------------------- #
# Determinism
# --------------------------------------------------------------------------- #

_FINGERPRINT = '''
import hashlib
import json
import sys

from extractors.payload.structure import PayloadReading, read_payload_structure
from extractors.signals.protocol import ExtractionScope
from parsers.payload import bind_records, default_registry

CAPTURE = "CAP-7d2f0c1a9b3e4d5f6a7b8c9d0e1f2a3b"
SEGMENT = "SEG-body-1"
EXTRACTOR = "parsers/payload"

body = open(sys.argv[1], "rb").read()
payload = default_registry().parse(
    body=body, content_type="application/json", declared_parser="structured_fields"
)
bound = bind_records(
    payload, capture_ref=CAPTURE, segment_ref=SEGMENT, extractor_ref=EXTRACTOR
)
result = read_payload_structure(
    PayloadReading(
        payload=payload,
        body=body,
        bound=bound,
        capture_ref=CAPTURE,
        segment_ref=SEGMENT,
        extractor_ref=EXTRACTOR,
    ),
    scope=ExtractionScope(
        tenant_id="tenant-a",
        context_ref="CTX-1",
        semantic_regime_ref="RG-1",
        document_ref=CAPTURE,
    ),
)
blob = json.dumps(result.to_dict(), sort_keys=True, ensure_ascii=False)
print(hashlib.sha256(blob.encode("utf-8")).hexdigest())
print("|".join(signal.signal_id for signal in result.signals))
'''


def test_the_same_payload_read_in_two_processes_with_different_hash_seeds_is_identical() -> None:
    """constitution VI / Domain Invariant 12, measured across process boundaries.

    Two child interpreters with ``PYTHONHASHSEED`` pinned differently is the only way to show that
    nothing from records to signals depends on set or dict iteration order: an in-process
    comparison cannot see it, because the seed is fixed for the whole run.
    """
    with tempfile.TemporaryDirectory(prefix="payload-structure-determinism-") as directory:
        sample = Path(directory) / "payload.json"
        sample.write_bytes(
            b'{"registrant": {"email": "a@b.c", "email_count": 2}, "aliases": ["x", "y"], "z": 1}'
        )
        script = Path(directory) / "fingerprint.py"
        script.write_text(_FINGERPRINT, encoding="utf-8")
        outputs: list[str] = []
        for seed in ("0", "12345"):
            env = dict(os.environ)
            env["PYTHONPATH"] = str(INTERPRETATION)
            env["PYTHONHASHSEED"] = seed
            completed = subprocess.run(
                [sys.executable, str(script), str(sample)],
                capture_output=True,
                text=True,
                cwd=str(INTERPRETATION),
                env=env,
                check=False,
            )
            assert completed.returncode == 0, completed.stderr[-3000:]
            outputs.append(completed.stdout)
    assert outputs[0] == outputs[1], (
        "the same payload produced different signals in two processes with different hash seeds, "
        "so something on the path depends on iteration order"
    )
    lines = outputs[0].splitlines()
    assert lines[1].count("SIG-") == 5, f"expected five signals, got {lines[1]!r}"


def test_two_readings_of_one_payload_are_byte_identical() -> None:
    first = structural(_BODY)
    second = structural(_BODY)
    assert first.to_dict() == second.to_dict()
    assert first.content_key() == second.content_key()
    assert [s.signal_id for s in first.signals] == [s.signal_id for s in second.signals]


# --------------------------------------------------------------------------- #
# The reading refuses rather than assuming
# --------------------------------------------------------------------------- #


def test_a_reading_bound_under_another_scope_is_refused_before_anything_is_emitted() -> None:
    """The scope cross-check is on the reading, so it fires before a single record is read."""
    payload = parse(_BODY)
    other = bind_records(
        payload, capture_ref="CAP-someone-else", segment_ref=SEGMENT, extractor_ref=EXTRACTOR
    )
    with pytest.raises(ReadingContractError) as raised:
        PayloadReading(
            payload=payload,
            body=_BODY,
            bound=other,
            capture_ref=CAPTURE,
            segment_ref=SEGMENT,
            extractor_ref=EXTRACTOR,
        )
    assert raised.value.code == "reading_scope_disagrees_with_binding"


def test_a_blank_scope_is_refused_rather_than_defaulted() -> None:
    for blank in ("", "   "):
        with pytest.raises(ReadingContractError) as raised:
            PayloadReading(
                payload=reading_of(_BODY).payload,
                body=_BODY,
                bound=reading_of(_BODY).bound,
                capture_ref=blank,
                segment_ref=SEGMENT,
                extractor_ref=EXTRACTOR,
            )
        assert raised.value.code == "reading_scope_required"


def test_a_reading_bound_for_a_different_record_set_is_refused() -> None:
    one = reading_of(_BODY)
    two = reading_of(b'{"a": 1}')
    with pytest.raises(ReadingContractError) as raised:
        PayloadReading(
            payload=two.payload,
            body=two.body,
            bound=one.bound,
            capture_ref=CAPTURE,
            segment_ref=SEGMENT,
            extractor_ref=EXTRACTOR,
        )
    assert raised.value.code == "reading_binding_does_not_partition_records"


def test_a_scope_that_names_no_capture_is_refused_rather_than_producing_untraceable_signals() -> None:
    with pytest.raises(SignalContractError) as raised:
        structural(_BODY, scope=_scope(document_ref=""))
    assert raised.value.code == "payload_reading_capture_required"


def test_the_stage_never_writes_an_entity_or_a_resolution_prefix() -> None:
    """No ``ENT-`` and no ``RES-`` reach the record, checked over the AST rather than by eye."""
    package = INTERPRETATION / "extractors" / "payload"
    forbidden = frozenset({"ENT-", "RES-", "REL-"})
    offenders: list[str] = []
    for module in sorted(package.rglob("*.py")):
        tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
        prose = _docstrings(tree)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and node.value in forbidden
                and node.value not in prose
            ):
                offenders.append(f"{module.name}:{node.lineno} literal {node.value!r}")
    assert not offenders, "an identity prefix reached the record: " + ", ".join(offenders)


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
# Mutation: a refused-address record joins a signal
# --------------------------------------------------------------------------- #

_PROLOGUE = '''
import sys

from extractors.payload.structure import PayloadReading, read_payload_structure
from extractors.signals.protocol import ExtractionScope
from parsers.payload import ParseBounds, bind_records, default_registry

CAPTURE = "CAP-guard"


def read(body, **over):
    payload = default_registry().parse(
        body=body, content_type="application/json", declared_parser="structured_fields", **over
    )
    bound = bind_records(
        payload, capture_ref=CAPTURE, segment_ref="SEG-1", extractor_ref="parsers/payload"
    )
    return read_payload_structure(
        PayloadReading(
            payload=payload,
            body=body,
            bound=bound,
            capture_ref=CAPTURE,
            segment_ref="SEG-1",
            extractor_ref="parsers/payload",
        ),
        scope=ExtractionScope(
            tenant_id="t", context_ref="c", semantic_regime_ref="r", document_ref=CAPTURE
        ),
    )
'''

_REFUSAL_GUARD = (
    _PROLOGUE
    + '''
failures = []
try:
    result = read(b'{"dots": "...", "ip": "10.0.0.1"}')
except Exception as exc:  # a crash is a refusal by another name, and still not a reading
    print("GUARD_FAIL the reading raised instead of excluding and counting: "
          + f"{type(exc).__name__} {exc}")
    raise SystemExit(1)
paths = [s.extra["field_path"] for s in result.signals]
if '$["dots"]' in paths:
    failures.append("a record whose address could not be resolved joined a signal")
if paths != ['$["ip"]']:
    failures.append(f"the payload's signals changed shape: {paths}")
if "record_address_mint_refused" not in result.refusal_codes:
    failures.append("the exclusion stopped being counted")
if "end_not_resolved" not in result.refusal_codes:
    failures.append("the stage stopped naming its own reason for excluding the record")
print("GUARD_OK" if not failures else "GUARD_FAIL " + "; ".join(failures))
raise SystemExit(0 if not failures else 1)
'''
)


def _mutated_structure(find: str, replace_with: str) -> Path:
    root = Path(tempfile.mkdtemp(prefix="payload-structure-mutation-"))
    for package, members in _COPIED:
        for member in members:
            source = APPS / package / member
            if source.is_dir():
                shutil.copytree(
                    source, root / source.name, ignore=shutil.ignore_patterns("__pycache__")
                )
            elif source.exists():
                shutil.copy2(source, root / source.name)
    target = (root / "extractors" / "payload" / "structure.py").resolve()
    text = target.read_text(encoding="utf-8")
    assert find in text, f"mutation anchor not found in structure.py: {find[:70]!r}"
    target.write_text(text.replace(find, replace_with, 1), encoding="utf-8")
    return root


def _child_env(root: Path) -> dict[str, str]:
    """The current environment with only ``PYTHONPATH`` redirected, for the Windows reason the
    other mutation harnesses record: a hand-built env without ``System32`` breaks Winsock."""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root)
    return env


def test_the_unmutated_structure_stage_satisfies_both_guards() -> None:
    for guard in (_REFUSAL_GUARD, _TRUNCATION_GUARD):
        completed = subprocess.run(
            [sys.executable, "-c", guard],
            capture_output=True,
            text=True,
            cwd=str(INTERPRETATION),
            env=_child_env(INTERPRETATION),
            check=False,
        )
        assert completed.returncode == 0, completed.stdout + completed.stderr[-3000:]
        assert "GUARD_OK" in completed.stdout, completed.stdout


def test_letting_a_refused_address_record_join_a_signal_fails_the_guard() -> None:
    """The mutation: drop the one guard that ends the member loop when an end cannot be resolved.

    The record here is ``"..."``, which has a well-formed address and is refused by the *index*
    rather than by the parser, so it reaches the member loop looking addressable. With the guard
    gone the loop falls through to signal construction — and the reason the outcome is a **crash**
    rather than a plausible wrong signal is worth recording: ``RelationParticipant`` refuses a
    blank ``mention_ref`` and ``RelationSignal`` refuses one mention in two slots. The exclusion
    is therefore guarded three times over, and this test proves the outermost guard is the one
    that fires.
    """
    root = _mutated_structure("        if failure is not None:\n", "        if False:\n")
    try:
        completed = subprocess.run(
            [sys.executable, "-c", _REFUSAL_GUARD],
            capture_output=True,
            text=True,
            cwd=str(root),
            env=_child_env(root),
            check=False,
        )
    finally:
        shutil.rmtree(root, ignore_errors=True)
    assert completed.returncode != 0, (
        f"a record that cannot be resolved joining a signal did NOT fail the guard: "
        f"{completed.stdout!r}"
    )
    assert "raised instead of excluding" in completed.stdout, (
        f"the mutation failed for a reason the guard did not anticipate: {completed.stdout!r} "
        f"{completed.stderr[-2000:]!r}"
    )


_TRUNCATION_GUARD = (
    _PROLOGUE
    + '''
from extractors.payload.structure import PRECISION_BOUNDED

failures = []
result = read(
    b'{"a": {"x": 1}, "b": 2, "c": 3, "d": 4}',
    bounds=ParseBounds(max_nodes=5, max_records_per_value_type=100, max_depth=8),
)
if not result.truncated:
    failures.append("the reading does not carry the parser's truncation")
if result.truncation_reason != "nodes_visited":
    failures.append(f"truncation_reason is {result.truncation_reason!r}")
for signal in result.signals:
    if signal.neighbourhood.precision != PRECISION_BOUNDED:
        failures.append(
            f"{signal.signal_id} is at precision {signal.neighbourhood.precision!r} and its "
            "payload was bounded"
        )
    if signal.extra.get("payload_truncated") is not True:
        failures.append(f"{signal.signal_id} does not record that its payload was truncated")
print("GUARD_OK" if not failures else "GUARD_FAIL " + "; ".join(failures))
raise SystemExit(0 if not failures else 1)
'''
)


def test_dropping_truncated_propagation_fails_the_guard() -> None:
    """The mutation: report every read at the same precision whatever stopped the walk.

    ``truncated`` is a property of the record set and would still be readable on the reading, so
    the mutation is invisible to anything that only asks the payload. What it destroys is the
    per-signal statement — and the address, because ``Neighbourhood`` is in the identity material
    and a bounded read then shares a ``signal_id`` with the whole read of the same structure.
    """
    root = _mutated_structure(
        "            precision=PRECISION_BOUNDED if truncated else PRECISION_WHOLE,",
        "            precision=PRECISION_WHOLE,",
    )
    try:
        completed = subprocess.run(
            [sys.executable, "-c", _TRUNCATION_GUARD],
            capture_output=True,
            text=True,
            cwd=str(root),
            env=_child_env(root),
            check=False,
        )
    finally:
        shutil.rmtree(root, ignore_errors=True)
    assert completed.returncode != 0, (
        f"dropping truncated propagation did NOT fail the guard: {completed.stdout!r}"
    )
    assert "its payload was bounded" in completed.stdout, completed.stdout
