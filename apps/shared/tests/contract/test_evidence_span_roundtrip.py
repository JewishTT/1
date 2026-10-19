"""A span survives storage (FR-016, WP5).

A finding's evidence chain is stored as JSON. Until this suite existed, the span contract
was **write-only**: it had `as_dict()` and no inverse, so a stored chain could not be turned
back into typed spans, and one of the eight selector kinds could not be serialised at all.

Both are defects of the same shape — the contract looked complete from the producing side and
was unusable from the reading side, which is exactly where a citation is consumed. These tests
enumerate the union rather than sampling it: a new selector kind that is added to the union and
forgotten in the inverse map fails here.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))

from contracts.evidence_span import (
    CharSpan,
    CoordinateSystem,
    EvidenceSpanRef,
    GeometrySpan,
    JsonPathSpan,
    PageBoxSpan,
    SelectorKind,
    SourceLocator,
    SourceLocatorSpan,
    SpanContractError,
    TableCellSpan,
    TimeRangeSpan,
    _SELECTOR_CLASSES,
    WarcRecordSpan,
)

pytestmark = pytest.mark.contract

LOCATOR = SourceLocator(uri="https://example.test/report", fragment="sec-2")
DIGEST = "sha256:" + "a" * 64

SELECTORS = {
    SelectorKind.CHAR_SPAN: (CharSpan(start=10, end=42, encoding="utf-8", units="document_char"), "char_span/1"),
    SelectorKind.PAGE_BOX: (
        PageBoxSpan(page=3, box=(1.0, 2.0, 30.0, 40.0), coordinate_system=CoordinateSystem.PDF_POINTS),
        "page_box/1",
    ),
    SelectorKind.TABLE_CELL: (
        TableCellSpan(table_ref="tbl-1", row=4, column=2, header_path=("Revenue", "2020")),
        "table_cell/1",
    ),
    SelectorKind.JSON_PATH: (JsonPathSpan(pointer="/records/0/name"), "json_path/1"),
    SelectorKind.TIME_RANGE: (TimeRangeSpan(start=12.5, end=19.0, track="mixed", frame=None), "time_range/1"),
    SelectorKind.GEOMETRY: (GeometrySpan(feature_ref="F-1", geometry_ref="G-1"), "geometry/1"),
    SelectorKind.WARC_RECORD: (
        WarcRecordSpan(record_offset=1024, warc_digest=DIGEST, record_length=2048),
        "warc_record/1",
    ),
    SelectorKind.SOURCE_LOCATOR: (SourceLocatorSpan(locator=LOCATOR), "source_locator/1"),
}


def _span(kind: SelectorKind) -> EvidenceSpanRef:
    selector, version = SELECTORS[kind]
    return EvidenceSpanRef(
        observation_ref="OB-1",
        blob_digest=DIGEST,
        selector=selector,
        source_locator=LOCATOR,
        selector_semantics_version=version,
    )


def test_the_selector_map_covers_every_kind() -> None:
    assert set(_SELECTOR_CLASSES) == set(SelectorKind), (
        "a selector kind with no entry in _SELECTOR_CLASSES can be produced and never read back"
    )


@pytest.mark.parametrize("kind", list(SelectorKind), ids=[k.value for k in SelectorKind])
def test_every_selector_kind_round_trips_through_json(kind: SelectorKind) -> None:
    original = _span(kind)

    wire = json.loads(json.dumps(original.as_dict()))
    restored = EvidenceSpanRef.from_dict(wire)

    assert restored == original
    assert restored.selector == original.selector
    assert restored.content_key() == original.content_key()


def test_the_source_locator_selector_is_serialisable() -> None:
    """It was not: a nested dataclass leaked into the payload and ``json.dumps`` failed."""
    wire = json.loads(json.dumps(_span(SelectorKind.SOURCE_LOCATOR).as_dict()))

    assert wire["selector"]["source_locator"]["locator"] == {
        "uri": LOCATOR.uri,
        "fragment": LOCATOR.fragment,
    }


def test_an_unknown_selector_kind_is_refused() -> None:
    payload = _span(SelectorKind.CHAR_SPAN).as_dict()
    payload["selector"] = {"byte_offset": {"start": 1}}

    with pytest.raises(SpanContractError):
        EvidenceSpanRef.from_dict(payload)


def test_a_flattened_selector_is_refused() -> None:
    payload = _span(SelectorKind.CHAR_SPAN).as_dict()
    payload["selector"] = {"start": 1, "end": 2}

    with pytest.raises(SpanContractError):
        EvidenceSpanRef.from_dict(payload)


def test_a_tampered_span_id_is_refused() -> None:
    payload = _span(SelectorKind.CHAR_SPAN).as_dict()
    payload["span_id"] = "sha256:" + "f" * 64

    with pytest.raises(SpanContractError):
        EvidenceSpanRef.from_dict(payload)


def test_a_missing_semantics_version_is_refused() -> None:
    payload = _span(SelectorKind.CHAR_SPAN).as_dict()
    payload["selector_semantics_version"] = ""

    with pytest.raises(SpanContractError):
        EvidenceSpanRef.from_dict(payload)


def test_a_non_mapping_payload_is_refused() -> None:
    with pytest.raises(SpanContractError):
        EvidenceSpanRef.from_dict(82)  # type: ignore[arg-type]
