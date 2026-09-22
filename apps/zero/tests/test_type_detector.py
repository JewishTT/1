"""Unit tests for Layer 1 type detector (spec/010 §0.1): all 8 types + scoring."""

from __future__ import annotations

import pytest

from zero.type_detector import (
    InputType,
    TypeCandidate,
    TypeDetector,
    make_soundex,
)


def test_detects_domain(detector: TypeDetector) -> None:
    seed = detector.detect("microsoft.com")
    assert seed.detected_type is InputType.DOMAIN
    assert seed.raw_value == "microsoft.com"


def test_detects_email(detector: TypeDetector) -> None:
    seed = detector.detect("john.doe@example.com")
    assert seed.detected_type is InputType.EMAIL
    assert seed.confidence > 0


def test_detects_username(detector: TypeDetector) -> None:
    seed = detector.detect("octocat")
    assert seed.detected_type is InputType.USERNAME


def test_username_excludes_dot_and_space(detector: TypeDetector) -> None:
    assert detector.detect("john .doe").detected_type is not InputType.USERNAME
    assert detector.detect("has space").detected_type is not InputType.USERNAME


def test_detects_phone(detector: TypeDetector) -> None:
    seed = detector.detect("+12025550199")
    assert seed.detected_type is InputType.PHONE


def test_detects_url(detector: TypeDetector) -> None:
    seed = detector.detect("https://github.com/octocat")
    assert seed.detected_type is InputType.URL


def test_detects_image_bytes(detector: TypeDetector) -> None:
    jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 48
    seed = detector.detect(jpeg)
    assert seed.detected_type is InputType.IMAGE
    assert seed.confidence > 0.8


def test_detects_document_pdf(detector: TypeDetector) -> None:
    pdf = b"%PDF-1.4" + b"\n%EOF"
    seed = detector.detect(pdf)
    assert seed.detected_type is InputType.DOCUMENT


def test_detects_document_docx_zip_magic(detector: TypeDetector) -> None:
    docx = b"PK\x03\x04" + b"\x00" * 48
    seed = detector.detect(docx)
    assert seed.detected_type is InputType.DOCUMENT


def test_detects_unknown_bytes(detector: TypeDetector) -> None:
    seed = detector.detect(b"\x00\x01\x02random")
    assert seed.detected_type is InputType.UNKNOWN


def test_detects_free_text_name(detector: TypeDetector) -> None:
    seed = detector.detect("Иван Петров")
    assert seed.detected_type is InputType.NAME
    assert detector.detect("John Doe").detected_type is InputType.NAME


def test_detects_shorter_names_too(detector: TypeDetector) -> None:
    assert detector.detect("Anna-Marie O'Neill").detected_type is InputType.NAME


def test_empty_input_is_unknown(detector: TypeDetector) -> None:
    assert detector.detect("  ").detected_type is InputType.UNKNOWN
    assert detector.detect("").detected_type is InputType.UNKNOWN


def test_confidence_uses_spec_formula(detector: TypeDetector) -> None:
    value = "microsoft.com"
    expected = min(1.0, InputType.DOMAIN.base_score * min(len(value) / 50.0, 1.0) * 1.0)
    assert detector.confidence(InputType.DOMAIN, value) == pytest.approx(expected, abs=1e-9)


def test_confidence_dns_bonus(dns_true: TypeDetector) -> None:
    value = "cloudflare.com"
    base = dns_true.confidence(InputType.DOMAIN, value)
    with_bonus = dns_true.confidence(InputType.DOMAIN, value, dns_domain=value)
    assert with_bonus > base
    assert with_bonus == pytest.approx(
        min(1.0, InputType.DOMAIN.base_score * min(len(value) / 50.0, 1.0) * (1.1)), abs=1e-9
    )


def test_confidence_capped_at_one(detector: TypeDetector) -> None:
    long_value = "x" * 200
    assert detector.confidence(InputType.DOMAIN, long_value) <= 1.0


def test_format_mismatch_gives_zero(detector: TypeDetector) -> None:
    assert detector.confidence(InputType.DOMAIN, "not-a-domain", format_match=False) == 0.0


def test_candidates_ranked_descending(detector: TypeDetector) -> None:
    candidates = detector.candidates("microsoft.com")
    scores = [candidate.confidence for candidate in candidates]
    assert scores == sorted(scores, reverse=True)
    assert all(isinstance(candidate, TypeCandidate) for candidate in candidates)


def test_deterministic_across_runs(detector: TypeDetector) -> None:
    first = detector.candidates("alice@example.com")
    second = detector.candidates("alice@example.com")
    assert [(c.input_type, c.confidence, c.reason) for c in first] == [
        (c.input_type, c.confidence, c.reason) for c in second
    ]


def test_seed_id_is_content_stable(detector: TypeDetector) -> None:
    assert detector.detect("bob@ex.org").seed_id == detector.detect("bob@ex.org").seed_id
    assert detector.detect("bob@ex.org").seed_id != detector.detect("bob@ex.com").seed_id


def test_filename_hint_metadata(detector: TypeDetector) -> None:
    seed = detector.detect("", filename="cover-photo.jpg")
    assert seed.metadata == {"input_bytes": False, "extension": ".jpg", "file_hint": "image"}


def test_soundex_classic_examples() -> None:
    assert make_soundex("Smith") == make_soundex("Smythe") == "S530"
    assert make_soundex("Robert") == make_soundex("Rupert") == "R163"