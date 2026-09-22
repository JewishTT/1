"""Contract tests for document adapters + metadata (spec 007, T023, extractor-adapter.md)."""

from __future__ import annotations

import hashlib
from pathlib import Path

from extractors.lane import extract_deterministic

FIXTURES = Path(__file__).resolve().parents[4] / "bench" / "fixtures" / "extraction"


def _read(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


class TestPdfAdapter:
    def test_pdf_metadata_segments_only(self):
        result = extract_deterministic(_read("sample.pdf"))
        assert result.content_type == "application/pdf"
        texts = [s.text for s in result.segments]
        assert all(seg.kind == "doc_meta" for seg in result.segments)
        assert any("Sergey Ivanov" in t for t in texts)
        assert any("cognitive-fixtures" in t for t in texts)
        assert result.mentions == []  # blank image page -> no body mentions

    def test_pdf_artifact_is_hash_addressed(self):
        blob = _read("sample.pdf")
        result = extract_deterministic(blob)
        assert result.artifact_sha == hashlib.sha256(blob).hexdigest()


class TestDocxAdapter:
    def test_docx_body_and_metadata_merge(self):
        result = extract_deterministic(_read("sample.docx"))
        assert result.quarantined is False
        kinds = {m.kind for m in result.mentions}
        assert {"person", "email", "place"} <= kinds
        assert any(
            m.kind == "person" and m.value == "Sergey Ivanov" for m in result.mentions
        )
        assert any(
            m.kind == "email" and m.value == "sergey@example-ivanov.ru"
            for m in result.mentions
        )

    def test_docx_places_carry_coordinates(self):
        result = extract_deterministic(_read("sample.docx"))
        kazan = next(m for m in result.mentions if m.value == "Kazan")
        assert kazan.dictionary == "geonames@2026.08"
        coords = kazan.evidence["coords"]
        assert abs(coords["lat"] - 55.7963) < 1e-3


class TestImageAdapter:
    def test_exif_geo_reverse_resolves_to_place(self):
        result = extract_deterministic(_read("sample_exif.jpg"))
        assert result.content_type == "image/jpeg"
        hits = [m for m in result.mentions if m.kind == "place"]
        assert hits
        place = hits[0]
        assert place.source == "coords"  # coords evidence, not dictionary window
        assert abs(place.evidence["exact_coords"]["lat"] - 55.7963) < 1e-3
        assert abs(place.evidence["exact_coords"]["lon"] - 49.1088) < 1e-3
        assert place.evidence["dictionary"] == "geonames@2026.08"


class TestUnclaimedArtifact:
    def test_corrupt_binary_is_reported_not_dropped(self):
        result = extract_deterministic(_read("corrupt.bin"))
        assert result.reason and result.reason.startswith("no-extraction-adapter")
        assert result.quarantined is False
        assert result.mentions == []
