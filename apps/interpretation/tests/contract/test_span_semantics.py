"""Span-semantics regression tests (spec 030 T058, contract 02 R2).

These pin a defect that was present for the whole life of the extraction lane and that
no existing test caught.

``extractors/lane.py`` used to do::

    m.offset += seg.offset
    if m.end_offset:
        m.end_offset += seg.offset

``Segment.offset`` carried three incompatible meanings across the four extraction
adapters, and the extractor produces **character** offsets:

    plaintext.py:59    offset=0                              (unset)
    registry.py:327    offset=i from enumerate()              (segment index)
    registry.py:353    offset=i from a row loop               (segment index)
    registry.py:383    offset=len(segments)                   (segment index)
    registry.py:404+   offset=0                              (unset)
    html_full.py       _locate(...)                          (was a BYTE offset)
    structured.py      _offset_of(...) + len(...encode())    (byte offset)
    documents.py       offset=0                              (unset)

Adding a segment index or an unset 0 to a character offset produces a number that looks
like a position and points nowhere. Nothing raised, so the whole suite stayed green over
a wrong answer.

The same file had a second defect: ``_locate`` returned ``len(text[:idx].encode("utf-8"))``
-- a byte length -- while ``str.find`` had already produced a character index, and it
returned ``0`` for "not found", which is indistinguishable from a real position 0.
"""

from __future__ import annotations

import pytest

from extractors.lane import extract_deterministic
from extractors.types import TypedMention
from parsers.html_full import _locate
from parsers.registry import OffsetSemantics, Segment

pytestmark = pytest.mark.unit


class TestOffsetSemanticsAreDeclared:
    """Every segment position states what it counts, or is honestly UNSET."""

    def test_default_is_unset_not_zero(self):
        """A producer that never computed a position must not look like position 0."""
        seg = Segment(text="hello", offset=0)
        assert seg.offset_semantics == OffsetSemantics.UNSET
        assert seg.offsets_known is False

    def test_rebase_refuses_unset(self):
        seg = Segment(text="hello", offset=0)
        assert seg.rebase_to_document(3, 8) == (None, None)

    def test_rebase_refuses_segment_index(self):
        """A segment index is not a document position and must never be added to one."""
        seg = Segment(text="hello", offset=7, offset_semantics=OffsetSemantics.SEGMENT_INDEX)
        assert seg.offsets_known is True  # the producer was honest about which kind it is
        assert seg.rebase_to_document(3, 8) == (None, None)

    def test_rebase_accepts_document_absolute(self):
        seg = Segment(text="hello", offset=100, offset_semantics=OffsetSemantics.DOCUMENT_CHAR)
        assert seg.rebase_to_document(3, 8) == (103, 108)

    def test_rebase_open_ended(self):
        seg = Segment(text="hello", offset=100, offset_semantics=OffsetSemantics.DOCUMENT_CHAR)
        assert seg.rebase_to_document(3, None) == (103, None)

    @pytest.mark.parametrize("semantics", sorted(OffsetSemantics.ALL))
    def test_all_semantics_are_documented(self, semantics):
        assert semantics in OffsetSemantics.ALL


class TestLocateIsCharNotByte:
    """`_locate` was returning a byte length over a character index."""

    def test_returns_character_index_not_byte_length(self):
        text = "prefix ééé target paragraph here"
        idx = _locate("target paragraph", text)
        assert idx == text.find("target paragraph")
        # The old implementation returned the utf-8 byte length, which is larger.
        assert idx != len(text[:idx].encode("utf-8"))

    def test_not_found_is_minus_one_not_zero(self):
        """0 is a real position. Returning it for 'not found' manufactures provenance."""
        assert _locate("nowhere at all in this text", "completely different content") == -1

    def test_position_zero_is_still_distinguishable_from_not_found(self):
        text = "target paragraph appears immediately"
        assert _locate("target paragraph", text) == 0
        assert _locate("absent phrase", text) == -1


class TestUnresolvedSpansAreNotZeroed:
    """An ungroundable mention must render as ungrounded, not as position 0."""

    def test_mention_carries_resolution_state(self):
        m = TypedMention(kind="person", value="X", offset=-1, end_offset=-1)
        assert m.span_semantics == "unresolved"
        assert m.span_resolved is False
        assert m.span_reason is not None

    def test_resolved_mention_reports_resolved(self):
        m = TypedMention(kind="person", value="X", offset=42, end_offset=43)
        assert m.span_semantics == "document_char"
        assert m.span_resolved is True
        assert m.span_reason is None

    def test_dict_carries_semantics_and_reason(self):
        m = TypedMention(
            kind="person",
            value="X",
            offset=-1,
            end_offset=-1,
            span_semantics="unresolved",
            span_reason="segment offset is an index",
        )
        d = m.to_dict()
        assert d["span_semantics"] == "unresolved"
        assert d["span_reason"] == "segment offset is an index"
        assert d["offset"] == -1

    def test_dict_is_deterministic_with_the_new_fields(self):
        a = TypedMention(kind="p", value="v", offset=1, end_offset=2).to_dict()
        b = TypedMention(kind="p", value="v", offset=1, end_offset=2).to_dict()
        assert a == b
        assert list(a) == sorted(a)


class TestLaneDoesNotAddAnIndexToAnOffset:
    """The arithmetic defect itself, exercised through the public lane."""

    def test_offsets_are_never_negative_for_a_resolved_producer(self):
        result = extract_deterministic(b"Alice Smith met Bob Jones in Berlin on Tuesday.")
        for m in result.mentions:
            if m.span_resolved:
                assert m.offset >= 0, f"resolved mention {m.value!r} got a negative offset"

    def test_every_mention_declares_its_span_semantics(self):
        result = extract_deterministic(b"Some text mentioning Alice Smith plainly.")
        for m in result.mentions:
            assert m.span_semantics in ("document_char", "unresolved")

    def test_no_mention_gets_a_bare_zero_offset_while_claiming_to_be_resolved(self):
        """The exact failure being pinned: a fabricated 0 that looks like position 0."""
        result = extract_deterministic(b"Content mentioning Carol Danvers here.")
        for m in result.mentions:
            if m.offset == 0 and m.end_offset == 0 and m.span_resolved:
                pytest.fail(
                    f"mention {m.value!r} resolved to offset 0/0 -- indistinguishable from "
                    "an unlocated mention"
                )
