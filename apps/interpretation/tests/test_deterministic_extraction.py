"""Deterministic entity-extraction tests (spec 007, `apps/interpretation`).

Own story locus: contracts + lane + normalization + adapters. Runs hermetically
against the committed fixtures (``bench/fixtures/extraction/``) and the
hermetic mini datasets — never touches the network or the live stack (NFR-1,
FR-10, C-7). All fixtures are byte-addressed (content-addressed store), so
reruns are byte-identical (FR-8, US3).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

import dictionaries
from extractors.language import decode_bytes, detect_language
from extractors.normalize import normalize_pass, normalize_person_name
from extractors.persons import extract_persons
from extractors.types import ExtractionResult, TypedMention

FIXTURES = Path(__file__).resolve().parents[3] / "bench" / "fixtures" / "extraction"


def _read(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def _bio_ru() -> str:
    return _read("bio_ru.txt").decode("utf-8")


def _bio_en() -> str:
    return _read("bio_en.txt").decode("utf-8")


# --------------------------------------------------------------------------- #
# Datasets: hermetic, content-addressed, version-stamped (US4/T004-T007)
# --------------------------------------------------------------------------- #


class TestDatasets:
    @pytest.mark.parametrize("kind", ["geonames", "sanctions", "first_names", "surnames", "companies"])
    def test_automaton_matches_built_mini_manifest(self, kind):
        meta, automaton = dictionaries.automaton(kind)
        assert meta.version == dictionaries.VERSIONS[kind]
        assert automaton is not None
        assert isinstance(meta.sha256, str) and len(meta.sha256) == 64

    def test_content_addressed_rebuild_is_byte_identical(self, tmp_path):
        """Rebuilding the datasets is deterministic: fresh build has the same
        sha256 as the committing-friendly meta sidecar (FR-8)."""
        from dictionaries.build_mini import build_all

        fresh = tmp_path / "datasets"
        fresh.mkdir()
        build_all(out_dir=fresh)
        for kind, version in dictionaries.VERSIONS.items():
            meta, _ = dictionaries.automaton(kind)
            payload = (fresh / f"{kind}_{version}.jsonl").read_bytes()
            assert meta.sha256 == hashlib.sha256(payload).hexdigest()


# --------------------------------------------------------------------------- #
# Charset + language (US5/T026-T027)
# --------------------------------------------------------------------------- #


class TestEncodingAndLanguage:
    def test_cp1251_page_decodes(self):
        text, charset = decode_bytes(_read("cp1251_page.html"))
        assert "1251" in charset
        assert "Родился в Казани" in text.replace("\n", " ")

    def test_detect_language(self):
        assert detect_language(_bio_ru()) == "ru"
        assert detect_language(_bio_en()) == "en"


# --------------------------------------------------------------------------- #
# Persons contract (US2/T014)
# --------------------------------------------------------------------------- #


class TestPersonsContract:
    def test_ru_comma_and_declension(self):
        mentions = extract_persons(
            "Сергеем Ивановым из Казани написал И. О. Смирнов."
        )
        values = {m.value: m for m in mentions}
        declined = values["Сергеем Ивановым"]
        assert declined.source == "pattern"
        assert declined.confidence < 0.7  # declined pattern — honest degradation
        initials = values["И. О. Смирнов"]
        assert initials.evidence.get("initials") == ["И", "О"]

    def test_en_two_word_person_ru_side(self):
        mentions = extract_persons("Sergey Ivanov was born in Kazan.")
        hit = next(m for m in mentions if m.value == "Sergey Ivanov")
        assert hit.lang == "en"


# --------------------------------------------------------------------------- #
# Normalization (US3/T020-T022)
# --------------------------------------------------------------------------- #


class TestNormalization:
    def test_canonical_collapses_declined_and_latin_forms(self):
        ru = normalize_person_name("Сергеем Ивановым")
        assert ru.canonical == "Иванов Сергей"
        assert ru.latin == "Ivanov Sergey"
        latin = normalize_person_name("Sergey Ivanov")
        assert latin.canonical == "Иванов Сергей"
        assert latin.latin == "Ivanov Sergey"

    def test_full_three_part_name(self):
        m = normalize_person_name("Иванов Сергей Петрович")
        assert m.canonical == "Иванов Сергей Петрович"
        assert (m.given, m.family, m.patronymic) == ("Сергей", "Иванов", "Петрович")

    def test_initials_hypothesis(self):
        evidence: dict = {}
        m = normalize_person_name("И. О. Иванов", initials=("И", "О"), evidence=evidence)
        assert m.hypothesis is True
        assert m.family == "Иванов"
        assert "expansion_hypotheses" in evidence

    def test_pass_attaches_cooccurrence_and_hashes(self):
        ms = [
            TypedMention(kind="person", value="Сергей Иванов", extractor="persons", lang="ru"),
            TypedMention(kind="person", value="Ольга Петрова", extractor="persons", lang="ru"),
            TypedMention(kind="email", value="sergey@example-ivanov.ru", extractor="contacts"),
        ]
        out = normalize_pass(ms)
        by_value = {m.value: m for m in out}
        assert by_value["Сергей Иванов"].normalized.canonical == "Иванов Сергей"
        assert "contact_hashes" in by_value["Сергей Иванов"].evidence
        expected = hashlib.sha1(b"sergey@example-ivanov.ru").hexdigest()
        assert expected in by_value["Сергей Иванов"].evidence["contact_hashes"]
        # co-occurrence keys come from the *lemmatized* canonical forms; the
        # declined "Петрова" lemmatizes to dictionary form "Петров" (pymorphy3).
        assert by_value["Сергей Иванов"].evidence["co_occurrence"] == ["Петров Ольга"]
        assert by_value["Ольга Петрова"].evidence["co_occurrence"] == ["Иванов Сергей"]


# --------------------------------------------------------------------------- #
# Lane: determinism, cp1251 parity, boilerplate exclusion, tier notes (T008-T027)
# --------------------------------------------------------------------------- #


def _lane(blob: bytes) -> ExtractionResult:
    from extractors.lane import extract_deterministic

    return extract_deterministic(blob)


class TestLane:
    def test_artifact_sha_recorded(self):
        result = _lane(_read("profile.html"))
        assert result.artifact_sha == hashlib.sha256(_read("profile.html")).hexdigest()

    def test_bio_ru_en_parity(self):
        ru = _lane(_read("bio_ru.txt"))
        en = _lane(_read("bio_en.txt"))
        assert ru.content_type == "text/plain"
        ru_persons = {m.normalized.canonical for m in ru.mentions if m.kind == "person" and m.normalized}
        en_persons = {m.normalized.canonical for m in en.mentions if m.kind == "person" and m.normalized}
        # RU fixture names carry patronymics; the EN twin is two-word only.
        assert any(c.startswith("Иванов Сергей") for c in ru_persons)
        assert any(c.startswith("Иванов Сергей") for c in en_persons)
        assert {m.kind for m in ru.mentions} == {m.kind for m in en.mentions}

    def test_cp1251_parity_and_boilerplate_exclusion(self):
        result = _lane(_read("cp1251_page.html"))
        assert result.content_type == "text/html"
        joined = "\n".join(s.text for s in result.segments)
        assert "О сайте" not in joined
        persons = [m for m in result.mentions if m.kind == "person"]
        assert any(m.normalized and m.normalized.canonical.startswith("Иванов Сергей") for m in persons)

    def test_profile_full_lane_merges_structure_and_body(self):
        result = _lane(_read("profile.html"))
        assert not result.quarantined
        kinds = {m.kind for m in result.mentions}
        assert {"person", "place", "email", "phone"} <= kinds
        persons = [m for m in result.mentions if m.kind == "person" and m.normalized]
        assert any(m.normalized.canonical == "Иванов Сергей Петрович" for m in persons)
        structured_mentions = [m for m in result.mentions if m.extractor == "structured"]
        assert any("https://github.com/sivanov" in m.evidence.get("sameAs", []) for m in structured_mentions)

    def test_unclaimed_corrupt_artifact_is_reported(self):
        result = _lane(_read("corrupt.bin"))
        assert result.reason.startswith("no-extraction-adapter")
        assert result.mentions == []


# --------------------------------------------------------------------------- #
# Tier notes (US5/T027): deterministic + honest per-language tiers
# --------------------------------------------------------------------------- #


class TestTiers:
    def test_pack_notes_stable(self):
        from extractors.language import pack_note

        assert pack_note("ru") == "pymorphy3@ru"
        assert pack_note("en") == "nameparser@en"
        assert pack_note("zh") == "tier3-dictionary@zh"  # CJK -> tier3, no double tag
        assert pack_note("zz") == "tier3-dictionary@zz"  # unknown alphabet -> tier3
