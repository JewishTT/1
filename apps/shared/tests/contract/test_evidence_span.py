"""``EvidenceSpanRef`` contract tests (spec 030 contract 02, tasks T028/T034).

Four invariants, all of which are refusals rather than defaults:

* **a span is a typed union, never an integer** -- ``selector=82`` raises. The measured defect
  this replaces was one ``Segment.offset`` field carrying byte offset, segment index and unset
  zero in three producers, all three summed together at ``extractors/lane.py:82-86``;
* **every selector variant round-trips against a stored blob** -- each of the eight resolves to
  the region that produced the derived text, and ``char_span`` does so byte-identically;
* **a mismatched ``selector_semantics_version`` refuses rather than converting** (FR-006);
* **the blob is the identity, the span is a pointer** (R8) -- a disagreeing digest is reported
  stale, not silently preferred and not raised.
"""

from __future__ import annotations

import pytest

from contracts.evidence_span import (
    DOCUMENT_ABSOLUTE_UNITS,
    CharSpan,
    CoordinateSystem,
    EvidenceSpanRef,
    GeometrySpan,
    JsonPathSpan,
    PageBoxSpan,
    SelectorKind,
    SelectorSemanticsVersion,
    SourceLocator,
    SourceLocatorSpan,
    SpanContractError,
    SpanSemanticsMismatch,
    StoredDocument,
    TableCellSpan,
    TimeRangeSpan,
    WarcRecordSpan,
    offset_vocabulary_agrees_with_runtime,
)

pytestmark = pytest.mark.contract

LOCATOR = SourceLocator(uri="https://example.org/report.pdf", fragment="page=7")
BLOB = b"Acme Corp filed at 2026-09-30. Acme Corp filed again at 2026-10-01. Total 4120000 units."

#: ``None`` means "use the version the selector implies"; ``""`` means "the producer said
#: nothing", which is the case under test. A default of ``None`` would hide the difference.
_DEFAULT_VERSION = object()


def _document() -> StoredDocument:
    """A stored blob plus the indexes a producer would have built alongside its spans."""
    return StoredDocument(
        data=BLOB,
        encoding="utf-8",
        index={
            "pages": {
                7: [
                    ((72.0, 144.0, 540.0, 200.0), b"Acme Corp filed at 2026-09-30."),
                    ((72.0, 300.0, 540.0, 360.0), b"Total 4120000 units."),
                ]
            },
            "tables": {
                "tbl-2": {
                    "headers": [
                        ["Region"],
                        ["Region", "Q3 2026"],
                        ["Region", "Q3 2026", "Approved units"],
                    ],
                    "rows": [
                        ["EMEA", "100"],
                        ["EMEA", "100", "4120000"],
                    ],
                }
            },
            "json": {
                "entity": {
                    "name": "Acme Corp",
                    "filing": {"period": "2026-09-30", "units": 4120000},
                }
            },
            "time_ranges": [
                {"start": 0.0, "end": 5.0, "track": "audio", "frame": 12, "text": "Acme Corp "},
                {"start": 5.0, "end": 9.5, "track": "audio", "frame": 25, "text": "filed again."},
                {"start": 0.0, "end": 9.5, "track": "captions", "frame": 1, "text": "[inaudible]"},
            ],
            "geometries": {
                "geo-1": {
                    "feature_ref": "feat-77",
                    "payload": {"type": "Point", "coords": [13.4, 52.5]},
                },
            },
            "warc": {"sha256:rec1": {"offset": 0, "length": 9}},
        },
    )


def _span(selector, *, version=_DEFAULT_VERSION, **kw) -> EvidenceSpanRef:
    document = kw.pop("document", None) or _document()
    if version is _DEFAULT_VERSION:
        version = f"{SelectorKind(selector.kind).value}/1"
    return EvidenceSpanRef(
        observation_ref=kw.pop("observation_ref", "obs-91c4"),
        blob_digest=kw.pop("blob_digest", document.blob_digest()),
        selector=selector,
        source_locator=kw.pop("source_locator", LOCATOR),
        selector_semantics_version=version,
        **kw,
    )


class TestTheSelectorIsATypedUnion:
    """R1: a span is never an integer."""

    def test_a_bare_int_selector_is_refused(self):
        """The measured defect, refused at the line that would introduce it."""
        with pytest.raises(SpanContractError) as e:
            _span(82, version="char_span/1")
        assert "82" in str(e.value)

    def test_the_refusal_names_r1(self):
        with pytest.raises(SpanContractError) as e:
            _span(82, version="char_span/1")
        assert "R1" in str(e.value)

    def test_a_float_selector_is_refused_too(self):
        with pytest.raises(SpanContractError):
            _span(82.0, version="char_span/1")

    def test_a_bare_zero_is_refused_even_though_zero_is_a_real_position(self):
        """``0`` and ``0.0`` are both legitimate *values* inside a typed span and neither is a
        span. The gate is the type, never the number."""
        with pytest.raises(SpanContractError):
            _span(0, version="char_span/1")

    def test_all_eight_variants_are_in_the_union(self):
        assert len(SelectorKind) == 8

    @pytest.mark.parametrize(
        "selector",
        [
            CharSpan(start=0, end=4),
            PageBoxSpan(
                page=7,
                box=(72.0, 144.0, 540.0, 200.0),
                coordinate_system=CoordinateSystem.PDF_POINTS,
            ),
            TableCellSpan(
                table_ref="tbl-2",
                row=1,
                column=2,
                header_path=("Region", "Q3 2026", "Approved units"),
            ),
            JsonPathSpan(pointer="/entity/filing/units"),
            TimeRangeSpan(start=0.0, end=5.0, track="audio"),
            GeometrySpan(feature_ref="feat-77", geometry_ref="geo-1"),
            WarcRecordSpan(record_offset=0, warc_digest="sha256:rec1", record_length=9),
            SourceLocatorSpan(locator=LOCATOR),
        ],
    )
    def test_every_variant_builds_and_serialises_under_its_own_key(self, selector):
        span = _span(selector)
        wire = span.as_dict()["selector"]
        assert list(wire) == [SelectorKind(selector.kind).value]

    @pytest.mark.parametrize(
        "selector",
        [
            CharSpan(start=0, end=4),
            PageBoxSpan(
                page=7,
                box=(72.0, 144.0, 540.0, 200.0),
                coordinate_system=CoordinateSystem.PDF_POINTS,
            ),
            TableCellSpan(
                table_ref="tbl-2",
                row=1,
                column=2,
                header_path=("Region", "Q3 2026", "Approved units"),
            ),
            JsonPathSpan(pointer="/entity/filing/units"),
            TimeRangeSpan(start=0.0, end=5.0, track="audio"),
            GeometrySpan(feature_ref="feat-77", geometry_ref="geo-1"),
            WarcRecordSpan(record_offset=0, warc_digest="sha256:rec1", record_length=9),
            SourceLocatorSpan(locator=LOCATOR),
        ],
    )
    def test_every_variant_resolves_without_an_attribute_error(self, selector):
        """The union is total: no variant may lack ``resolve``, or the gate is a lie."""
        document = _document()
        assert _span(selector, document=document).resolve(document) is not None


class TestEveryVariantRoundTripsAgainstAStoredBlob:
    """The contract's machine-checked round-trip requirement, once per selector variant."""

    def test_char_span_returns_the_exact_substring_byte_identically(self):
        document = _document()
        start = BLOB.index(b"Acme Corp")
        span = _span(CharSpan(start=start, end=start + len(b"Acme Corp")), document=document)
        resolved = span.resolve(document)
        assert resolved.value == "Acme Corp"
        assert resolved.raw == b"Acme Corp"
        assert document.data[start : start + len(b"Acme Corp")] == resolved.raw

    def test_warc_record_returns_the_bytes_at_its_offset(self):
        record = BLOB[:9]
        document = StoredDocument(
            data=record,
            index={"warc": {"sha256:rec1": {"offset": 0, "length": 9}}},
        )
        span = _span(
            WarcRecordSpan(record_offset=0, warc_digest="sha256:rec1", record_length=9),
            document=document,
        )
        assert span.resolve(document).raw == record

    def test_char_span_applies_no_normalisation(self):
        """R6: normalisation produces additional candidate forms, never a rewritten span.

        The blob holds three different byte sequences for three different casings and two
        different codepoints. A span over the first four characters must return the first four
        characters, byte for byte -- not the NFC-folded, case-folded or transliterated form.
        """
        raw = "CAFÉ Café cafe".encode()
        document = StoredDocument(data=raw)
        span = _span(CharSpan(start=0, end=4), document=document)
        resolved = span.resolve(document)
        assert resolved.value == "CAFÉ"
        assert resolved.raw == "CAFÉ".encode()
        assert resolved.raw == raw[: len(resolved.raw)]

    def test_page_box_returns_the_text_of_the_region_it_meets(self):
        document = _document()
        span = _span(
            PageBoxSpan(
                page=7,
                box=(72.0, 144.0, 540.0, 200.0),
                coordinate_system=CoordinateSystem.PDF_POINTS,
            ),
            document=document,
        )
        assert span.resolve(document).value == "Acme Corp filed at 2026-09-30."
        assert span.resolve(document).detail["overlap"] == 1.0

    def test_table_cell_returns_the_cell_named_by_its_header_path(self):
        document = _document()
        span = _span(
            TableCellSpan(
                table_ref="tbl-2",
                row=1,
                column=2,
                header_path=("Region", "Q3 2026", "Approved units"),
            ),
            document=document,
        )
        assert span.resolve(document).value == "4120000"

    def test_json_path_returns_the_named_field(self):
        document = _document()
        span = _span(JsonPathSpan(pointer="/entity/filing/period"), document=document)
        assert span.resolve(document).value == "2026-09-30"

    def test_time_range_returns_the_matching_track_only(self):
        document = _document()
        span = _span(TimeRangeSpan(start=0.0, end=5.0, track="audio"), document=document)
        assert span.resolve(document).value == "Acme Corp "

    def test_geometry_returns_the_original_representation(self):
        document = _document()
        span = _span(GeometrySpan(feature_ref="feat-77", geometry_ref="geo-1"), document=document)
        assert span.resolve(document).value["type"] == "Point"

    def test_source_locator_is_pointer_only_and_says_so(self):
        """The one variant with no bytes behind it must not pretend to have resolved.

        Returning an empty string would have read as "the region was empty", which is a claim
        about the source. It returns the locator and marks itself pointer-only instead.
        """
        document = _document()
        resolved = _span(SourceLocatorSpan(locator=LOCATOR), document=document).resolve(document)
        assert resolved.is_pointer_only is True
        assert resolved.value == LOCATOR.uri
        assert resolved.detail["re_fetch_required"] is True

    def test_a_span_that_does_not_resolve_raises_rather_than_returning_empty(self):
        document = _document()
        span = _span(JsonPathSpan(pointer="/entity/missing"), document=document)
        with pytest.raises(SpanContractError) as e:
            span.resolve(document)
        assert "does not resolve" in str(e.value)


class TestSemanticsVersionIsMandatoryAndChecked:
    def test_an_absent_version_is_refused(self):
        with pytest.raises(SpanContractError) as e:
            _span(CharSpan(start=0, end=4), version="")
        assert "mandatory" in str(e.value)

    def test_a_version_without_a_kind_is_refused(self):
        with pytest.raises(SpanContractError) as e:
            _span(CharSpan(start=0, end=4), version="1")
        assert "does not name" in str(e.value)

    def test_a_version_naming_an_unknown_kind_is_refused(self):
        with pytest.raises(SpanContractError) as e:
            _span(CharSpan(start=0, end=4), version="pixel_cluster/1")
        assert "unknown selector kind" in str(e.value)

    def test_a_version_that_disagrees_with_the_selector_present_is_refused(self):
        with pytest.raises(SpanContractError) as e:
            _span(CharSpan(start=0, end=4), version="table_cell/2")
        assert "does not match the selector present" in str(e.value)

    def test_the_refusal_is_at_construction_not_at_read_time(self):
        """A consumer three services away must never be the one who discovers this."""
        with pytest.raises(SpanContractError):
            EvidenceSpanRef(
                observation_ref="obs-1",
                blob_digest="sha256:x",
                selector=JsonPathSpan(pointer="/a"),
                source_locator=LOCATOR,
                selector_semantics_version="char_span/1",
            )

    def test_a_mismatched_version_refuses_to_compare(self):
        left = _span(CharSpan(start=0, end=4), version="char_span/1")
        right = _span(CharSpan(start=0, end=4), version="char_span/2")
        with pytest.raises(SpanSemanticsMismatch) as e:
            left.require_comparable_with(right)
        assert "char_span/1" in str(e.value) and "char_span/2" in str(e.value)

    def test_comparison_of_two_different_selector_kinds_is_also_refused(self):
        left = _span(CharSpan(start=0, end=4))
        right = _span(JsonPathSpan(pointer="/a"))
        assert left.is_comparable_with(right) is False

    def test_a_span_is_comparable_with_an_identically_versioned_span(self):
        left = _span(CharSpan(start=0, end=4))
        right = _span(CharSpan(start=0, end=4))
        left.require_comparable_with(right)

    def test_there_is_no_conversion_to_fall_back_on(self):
        """No ``convert``, no ``align``, no ``coerce``: the absence is the guarantee."""
        forbidden = {"convert", "align", "coerce", "normalize", "to_selector"}
        public = {name for name in dir(EvidenceSpanRef) if not name.startswith("_")}
        assert forbidden & public == set()

    def test_version_zero_is_not_a_version(self):
        with pytest.raises(SpanContractError):
            SelectorSemanticsVersion(kind=SelectorKind.CHAR_SPAN, version=0)


class TestZeroIsNotNoPosition:
    def test_a_negative_start_is_refused(self):
        """-1 is the extractor's explicit 'not found' and must never be stored as a span."""
        with pytest.raises(SpanContractError) as e:
            CharSpan(start=-1, end=4)
        assert "not found" in str(e.value)

    def test_position_zero_is_still_addressable(self):
        assert CharSpan(start=0, end=4).start == 0

    def test_an_empty_range_is_refused(self):
        with pytest.raises(SpanContractError):
            CharSpan(start=4, end=4)

    def test_a_backwards_range_is_refused(self):
        with pytest.raises(SpanContractError):
            CharSpan(start=9, end=3)

    def test_unset_units_are_refused(self):
        """A producer that never computed a position has no span to emit."""
        with pytest.raises(SpanContractError) as e:
            CharSpan(start=0, end=4, units="unset")
        assert "unset" in str(e.value)

    def test_segment_index_units_are_refused(self):
        """A segment index is not a document position and must never be added to one."""
        with pytest.raises(SpanContractError):
            CharSpan(start=0, end=4, units="segment_index")

    def test_the_unit_vocabulary_is_the_runtime_offset_semantics_rebasable_set(self):
        """Not a second enum. ``OffsetSemantics`` in the interpretation layer owns the
        vocabulary and this must not have forked from it."""
        assert offset_vocabulary_agrees_with_runtime() is not False
        assert DOCUMENT_ABSOLUTE_UNITS == frozenset({"document_char", "document_byte"})


class TestCoordinatesCarryTheirFrame:
    def test_a_box_without_a_coordinate_system_is_refused(self):
        with pytest.raises((SpanContractError, ValueError)):
            PageBoxSpan(page=1, box=(0.0, 0.0, 1.0, 1.0), coordinate_system="")

    def test_an_unknown_frame_is_refused(self):
        with pytest.raises(ValueError):
            PageBoxSpan(
                page=1,
                box=(0.0, 0.0, 1.0, 1.0),
                coordinate_system="points_but_which_ones",
            )

    def test_an_inverted_box_is_refused(self):
        with pytest.raises(SpanContractError) as e:
            PageBoxSpan(
                page=1,
                box=(10.0, 10.0, 5.0, 5.0),
                coordinate_system=CoordinateSystem.PDF_POINTS,
            )
        assert "empty or inverted" in str(e.value)

    def test_a_non_finite_coordinate_is_refused(self):
        with pytest.raises(SpanContractError):
            PageBoxSpan(
                page=1,
                box=(0.0, 0.0, float("inf"), 1.0),
                coordinate_system=CoordinateSystem.PDF_POINTS,
            )

    def test_two_boxes_in_different_frames_do_not_report_an_overlap(self):
        left = PageBoxSpan(
            page=1, box=(0.0, 0.0, 10.0, 10.0), coordinate_system=CoordinateSystem.PDF_POINTS
        )
        right = PageBoxSpan(
            page=1, box=(0.0, 0.0, 10.0, 10.0), coordinate_system=CoordinateSystem.PIXEL_TOP_LEFT
        )
        with pytest.raises(SpanSemanticsMismatch) as e:
            left.overlaps(right)
        assert "different frames" in str(e.value)


class TestTableCellsNeedAHeaderPath:
    def test_an_empty_header_path_is_refused(self):
        with pytest.raises(SpanContractError) as e:
            TableCellSpan(table_ref="tbl-2", row=1, column=2, header_path=())
        assert "filter" in str(e.value)

    def test_a_blank_header_path_component_is_refused(self):
        with pytest.raises(SpanContractError):
            TableCellSpan(table_ref="tbl-2", row=1, column=2, header_path=("Region", "  "))

    def test_a_column_that_disagrees_with_its_own_header_path_is_refused_at_resolve(self):
        """The filter-dependent address contract 02 forbids.

        Detected at resolve rather than at construction, and necessarily so: the span does not
        carry the table, so only the stored document can say which column the header path names.
        """
        document = _document()
        span = _span(
            TableCellSpan(
                table_ref="tbl-2",
                row=1,
                column=1,
                header_path=("Region", "Q3 2026", "Approved units"),
            ),
            document=document,
        )
        with pytest.raises(SpanSemanticsMismatch) as e:
            span.resolve(document)
        assert "refusing to pick one" in str(e.value)

    def test_a_header_path_that_does_not_exist_in_the_table_is_refused_at_resolve(self):
        document = _document()
        span = _span(
            TableCellSpan(
                table_ref="tbl-2", row=1, column=1, header_path=("Region", "Q4 2026")
            ),
            document=document,
        )
        with pytest.raises(SpanContractError) as e:
            span.resolve(document)
        assert "not a column path" in str(e.value)


class TestTheBlobIsTheIdentity:
    """R8: the span is a pointer; the blob digest is the identity."""

    def test_a_matching_digest_is_fresh(self):
        document = _document()
        span = _span(CharSpan(start=0, end=4), document=document)
        assert span.check_blob(document).is_stale is False

    def test_a_mismatched_digest_is_reported_stale_with_both_digests(self):
        document = _document()
        span = _span(CharSpan(start=0, end=4), blob_digest="sha256:something-else")
        check = span.check_blob(document)
        assert check.is_stale is True
        assert check.declared_digest == "sha256:something-else"
        assert check.stored_digest == document.blob_digest()

    def test_a_stale_span_is_reported_not_raised(self):
        """A stale span is a finding to surface, not an outage to cause."""
        document = _document()
        span = _span(CharSpan(start=0, end=4), blob_digest="sha256:something-else")
        assert span.check_blob(document).status == "stale"

    def test_a_warc_offset_that_no_longer_addresses_its_record_refuses(self):
        """The blob wins: reading whatever is at the old offset is how provenance is forged."""
        document = StoredDocument(
            data=b"AAAABBBB",
            index={"warc": {"sha256:rec1": {"offset": 4, "length": 4}}},
        )
        span = _span(
            WarcRecordSpan(record_offset=0, warc_digest="sha256:rec1", record_length=4),
            document=document,
        )
        with pytest.raises(SpanSemanticsMismatch) as e:
            span.resolve(document)
        assert "refusing to read whatever" in str(e.value)

    def test_a_geometry_that_belongs_to_another_feature_is_not_reattributed(self):
        document = _document()
        span = _span(
            GeometrySpan(feature_ref="feat-999", geometry_ref="geo-1"), document=document
        )
        with pytest.raises(SpanSemanticsMismatch) as e:
            span.resolve(document)
        assert "refusing to reattribute" in str(e.value)


class TestIdentityIsStableAndFreeOfProcessState:
    def test_the_content_key_is_stable_across_two_identical_spans(self):
        assert _span(CharSpan(start=0, end=4)).content_key() == _span(
            CharSpan(start=0, end=4)
        ).content_key()

    def test_the_content_key_changes_when_the_semantics_version_changes(self):
        assert _span(CharSpan(start=0, end=4), version="char_span/1").content_key() != _span(
            CharSpan(start=0, end=4), version="char_span/2"
        ).content_key()

    def test_the_content_key_changes_when_the_position_changes(self):
        assert _span(CharSpan(start=0, end=4)).content_key() != _span(
            CharSpan(start=1, end=5)
        ).content_key()

    def test_the_serialised_form_carries_no_object_repr(self):
        wire = _span(CharSpan(start=0, end=4)).as_dict()
        assert "object at 0x" not in str(wire)
        assert "0x" not in wire["blob_digest"]