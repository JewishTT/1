"""P4: every addressable record reaches the mention index, and no record is dropped.

Feature 021 brief §25 and §26; spec FR-016, FR-018, FR-019; ``ARBITRATION`` §8;
constitution IV (fail-closed) and VI (determinism, Domain Invariant 12).

**What is being tested.** The parser layer sits *below* mention extraction, so it may not mint
an identity (brief §25, FR-019) — it mints a **deferred occurrence address**, and
:class:`domain.mention_occurrence_index.MentionOccurrenceIndex` is the one place ``MN-`` ids
are written. The properties here are: the address a record carries resolves to the mention that
record's own occurrence addresses; a record with no address is **refused with a name** rather
than dropped; and the two are counted so a caller can tell "the payload said nothing" from "the
payload said something we could not address".

The address round trip is checked against the index's **own** inverse
(:meth:`MentionOccurrenceIndex.require_occurrence`) and its **own** mint
(:meth:`MentionOccurrenceIndex.mention_id_for`), not against a re-implementation of either —
a test that recomputed the expected id itself would agree with a bug in the same direction.
"""

from __future__ import annotations

import pytest
from domain.mention_occurrence_index import (
    MentionBindingError,
    MentionOccurrence,
)
from domain.relation_participant import ParticipantEndKind

from parsers.payload import (
    ADDRESS_REFUSAL_CODES,
    ObservedField,
    ParseBounds,
    PayloadContractError,
    PayloadLabel,
    ValueType,
    bind_records,
    default_registry,
    occurrence_index,
)

pytestmark = pytest.mark.unit

CAPTURE = "CAP-7d2f0c1a9b3e4d5f6a7b8c9d0e1f2a3b"
SEGMENT = "SEG-body-1"
EXTRACTOR = "parsers/payload"

_BODY = (
    b'{"ip": "10.0.0.1", "count": 3, "live": true, "gone": null, '
    b'"tags": ["alpha", "beta"], "owner": {"name": "Acme"}}'
)


def parse(body: bytes = _BODY, **over: object):
    arguments: dict[str, object] = {
        "body": body,
        "content_type": "application/json",
        "declared_parser": "structured_fields",
    }
    arguments.update(over)
    return default_registry().parse(**arguments)


# --------------------------------------------------------------------------- #
# The round trip
# --------------------------------------------------------------------------- #


def test_every_addressable_record_resolves_through_the_mention_index() -> None:
    payload = parse()
    bound = bind_records(
        payload, capture_ref=CAPTURE, segment_ref=SEGMENT, extractor_ref=EXTRACTOR
    )
    index = occurrence_index(
        payload.records,
        capture_ref=CAPTURE,
        segment_ref=SEGMENT,
        extractor_ref=EXTRACTOR,
    )
    assert bound.bound, "the payload produced no addressable records at all"
    for entry in bound.bound:
        resolved = index.require_occurrence(entry.address)
        assert resolved.mention_id == entry.mention_id
        assert resolved.key.span == entry.byte_span
        assert resolved.label == str(PayloadLabel.JSON_FIELD) or resolved.label in (
            "json_field",
            "json_element",
        )
    # The id is the index's own mint from the index's own key, not a re-derivation here.
    for entry, record in zip(bound.bound, payload.addressable(), strict=True):
        expected = index.mention_id_for(
            MentionOccurrence(
                kind="payload-occurrence",
                surface=record.value,
                start=record.byte_span[0],
                end=record.byte_span[1],
            )
        )
        assert entry.mention_id == expected


def test_the_binding_partitions_the_records_so_nothing_is_dropped() -> None:
    """``len(bound) + len(refusals) == len(records)`` is the mechanical form of the promise."""
    payload = parse()
    bound = bind_records(
        payload, capture_ref=CAPTURE, segment_ref=SEGMENT, extractor_ref=EXTRACTOR
    )
    assert len(bound.bound) + len(bound.refusals) == len(payload.records)
    bound_fields = {entry.field for entry in bound.bound}
    assert bound_fields == {record.field for record in payload.addressable()}
    # Every unaddressable record shows up as a refusal, with the code from the closed vocabulary.
    codes = {refusal.code for refusal in bound.refusals}
    assert codes <= set(ADDRESS_REFUSAL_CODES)
    assert "field_value_is_nested" in codes
    assert "field_value_is_null" in codes


def test_the_two_occurrences_of_one_surface_are_two_mentions() -> None:
    """FR-018's five keys: a position is part of the key, so two positions are two mentions."""
    payload = parse(b'{"a": "Acme", "b": "Acme"}')
    bound = bind_records(
        payload, capture_ref=CAPTURE, segment_ref=SEGMENT, extractor_ref=EXTRACTOR
    )
    assert len(bound.bound) == 2
    assert bound.bound[0].mention_id != bound.bound[1].mention_id
    assert bound.bound[0].byte_span != bound.bound[1].byte_span


def test_the_same_bytes_bound_twice_mint_the_same_ids() -> None:
    """constitution VI / Domain Invariant 12, and the property that makes an ``MN-`` a join key."""
    first = bind_records(
        parse(), capture_ref=CAPTURE, segment_ref=SEGMENT, extractor_ref=EXTRACTOR
    )
    second = bind_records(
        parse(), capture_ref=CAPTURE, segment_ref=SEGMENT, extractor_ref=EXTRACTOR
    )
    assert first.mention_ids == second.mention_ids
    assert first.to_dict() == second.to_dict()


def test_the_extractor_key_is_one_of_the_five_keys_a_mention_is_minted_from() -> None:
    """The same payload read by two instruments is two sets of mentions, not one shared set."""
    payload = parse()
    as_json = bind_records(
        payload, capture_ref=CAPTURE, segment_ref=SEGMENT, extractor_ref="parsers/payload"
    )
    as_text = bind_records(
        payload, capture_ref=CAPTURE, segment_ref=SEGMENT, extractor_ref="some/other/reader"
    )
    assert not set(as_json.mention_ids) & set(as_text.mention_ids)


def test_a_text_payloads_lines_are_addressable_occurrences_too() -> None:
    payload = default_registry().parse(
        body=b"first line\nsecond line\n", content_type="text/plain", parser_is_identity=True
    )
    bound = bind_records(
        payload, capture_ref=CAPTURE, segment_ref=SEGMENT, extractor_ref=EXTRACTOR
    )
    assert [entry.value for entry in bound.bound] == ["first line", "second line"]
    assert all(entry.end_kind is ParticipantEndKind.OCCURRENCE for entry in bound.bound)


def test_an_empty_string_value_is_kept_counted_and_refused_by_name() -> None:
    payload = parse(b'{"a": ""}')
    bound = bind_records(
        payload, capture_ref=CAPTURE, segment_ref=SEGMENT, extractor_ref=EXTRACTOR
    )
    assert bound.bound == ()
    assert [refusal.code for refusal in bound.refusals] == [
        "field_value_is_nested",
        "field_surface_empty",
    ]
    assert len(payload.records) == 2, "the container record and the empty value both survive"


# --------------------------------------------------------------------------- #
# Pluggability is a test: a record with no address is refused by name
# --------------------------------------------------------------------------- #


def test_a_record_with_no_span_is_refused_by_name_rather_than_dropped() -> None:
    """P4's pluggability claim, in the form the task states it: **refused, not dropped**."""
    record = ObservedField(
        field='$["a"]',
        value="10.0.0.1",
        value_type=ValueType.STRING,
        byte_span=None,
        depth=1,
        label=PayloadLabel.JSON_FIELD,
        address_refusal="field_has_no_byte_span",
    )
    assert record not in (), "the record exists; the question is whether it is addressable"
    assert record.addressable is False
    with pytest.raises(PayloadContractError) as raised:
        record.require_address()
    assert raised.value.code == "field_has_no_byte_span"
    assert "field_has_no_byte_span" in str(raised.value)


def test_a_record_with_neither_an_address_nor_a_refusal_is_refused_as_malformed() -> None:
    """Both empty is not "unaddressable" — it is a record that does not say which it is."""
    record = ObservedField(
        field='$["a"]',
        value="10.0.0.1",
        value_type=ValueType.STRING,
        byte_span=(0, 10),
        depth=1,
        label=PayloadLabel.JSON_FIELD,
    )
    with pytest.raises(PayloadContractError) as raised:
        record.require_address()
    assert raised.value.code == "field_address_missing"


def test_a_record_carrying_both_an_address_and_a_refusal_is_refused_on_construction() -> None:
    """Two answers to one question is the state a caller cannot resolve, so it never exists."""
    with pytest.raises(PayloadContractError) as raised:
        ObservedField(
            field='$["a"]',
            value="x",
            value_type=ValueType.STRING,
            byte_span=(0, 3),
            depth=1,
            label=PayloadLabel.JSON_FIELD,
            address="surface@0-3:1:0:[\"json_field\",\"x\",0,3]",
            address_refusal="field_surface_empty",
        )
    assert raised.value.code == "field_address_state_invalid"


def test_a_value_with_no_nameable_surface_costs_itself_and_not_the_payload() -> None:
    """``"..."`` normalises to nothing, so the index refuses it — by name, and only it.

    This is the case the whole binding is shaped around: one value with no nameable surface must
    cost that value its mention id and nothing else, because the alternative is a payload whose
    record set is short for a reason nobody can see.
    """
    payload = parse(b'{"dots": "...", "ip": "10.0.0.1"}')
    bound = bind_records(
        payload, capture_ref=CAPTURE, segment_ref=SEGMENT, extractor_ref=EXTRACTOR
    )
    assert len(bound.bound) == 1, "one value must not cost the payload its other mentions"
    assert bound.bound[0].field == '$["ip"]'
    assert [refusal.code for refusal in bound.refusals] == [
        "field_value_is_nested",
        "record_address_mint_refused",
    ]
    assert "mention_occurrence_surface_required" in bound.refusals[1].detail


def test_a_blank_scope_is_refused_rather_than_defaulted() -> None:
    """A scope that defaults is a scope that can quietly name a different retrieval."""
    for blank in ({"capture_ref": ""}, {"segment_ref": " "}, {"extractor_ref": ""}):
        arguments = {
            "capture_ref": CAPTURE,
            "segment_ref": SEGMENT,
            "extractor_ref": EXTRACTOR,
            **blank,
        }
        with pytest.raises(MentionBindingError) as raised:
            bind_records(parse(), **arguments)
        assert raised.value.code == "mention_index_scope_required"


def test_binding_an_empty_payload_returns_an_empty_table_rather_than_failing() -> None:
    payload = parse(b"", content_type="application/json")
    bound = bind_records(
        payload, capture_ref=CAPTURE, segment_ref=SEGMENT, extractor_ref=EXTRACTOR
    )
    assert bound.bound == ()
    assert bound.refusals == ()
    assert bound.mention_ids == ()


def test_a_bounded_payload_binds_what_it_read_and_nothing_it_did_not() -> None:
    """Bounds stop the walk; the binding must not read past where the walk stopped."""
    body = b"[" + b",".join(b'"v%d"' % index for index in range(100)) + b"]"
    payload = default_registry().parse(
        body=body,
        content_type="application/json",
        declared_parser="structured_fields",
        bounds=ParseBounds(max_nodes=10, max_records_per_value_type=1000, max_depth=64),
    )
    bound = bind_records(
        payload, capture_ref=CAPTURE, segment_ref=SEGMENT, extractor_ref=EXTRACTOR
    )
    assert payload.truncated is True
    assert len(payload.records) < 102
    assert len(bound.bound) == len(payload.addressable())
    assert len(bound.bound) + len(bound.refusals) == len(payload.records)
