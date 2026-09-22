"""Contract tests for charset/language parity across twins (spec 007, T026)."""

from __future__ import annotations

from pathlib import Path

from extractors.lane import extract_deterministic
from extractors.language import decode_bytes, detect_language, pack_note
from extractors.translit import from_latin, universal

FIXTURES = Path(__file__).resolve().parents[4] / "bench" / "fixtures" / "extraction"


def _read(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


class TestCharsetDecode:
    def test_cp1251_page_decodes_cleanly(self):
        text, charset = decode_bytes(_read("cp1251_page.html"))
        assert "1251" in charset
        assert "Родился в Казани" in text.replace("\n", " ")

    def test_utf8_passthrough(self):
        text, charset = decode_bytes(_read("bio_ru.txt"))
        assert "utf" in charset
        assert "Иванов" in text


class TestLanguageDetection:
    def test_ru_en_round_trip(self):
        assert detect_language(_read("bio_ru.txt").decode("utf-8")) == "ru"
        assert detect_language(_read("bio_en.txt").decode("utf-8")) == "en"


class TestLanguageParity:
    def test_bio_twins_produce_same_kind_set(self):
        ru = extract_deterministic(_read("bio_ru.txt"))
        en = extract_deterministic(_read("bio_en.txt"))
        assert ru.content_type == en.content_type == "text/plain"
        assert {m.kind for m in ru.mentions} == {m.kind for m in en.mentions}

    def test_both_twins_are_deterministic(self):
        for name in ("bio_ru.txt", "bio_en.txt"):
            blob = _read(name)
            first = extract_deterministic(blob).to_dict()
            second = extract_deterministic(blob).to_dict()
            assert first == second, name


class TestCrossAlphabetTiers:
    def test_cjk_is_tier3_not_tier2(self):
        assert pack_note("zh") == "tier3-dictionary@zh"

    def test_unknown_alphabet_is_tier3(self):
        assert pack_note("zz") == "tier3-dictionary@zz"

    def test_transliteration_is_script_agnostic(self):
        assert universal("Иванов Сергей") == "Ivanov Sergey"
        assert from_latin("Ivanov") == "Иванов"

    def test_zh_structure_mentions_deterministic_and_never_tier1(self):
        """CJK artifact: structure mentions come through unchanged and the
        morphology note is an honest tier-3 typed absence, never pymorphy3."""
        html = (
            "<html><head><meta charset='utf-8'>"
            "<script type='application/ld+json'>"
            '{"@type":"Person","name":"\u674e\u534e","url":"https://example-cn.dev/lihua"}'
            "</script></head><body><h1>\u674e\u534e</h1></body></html>"
        ).encode("utf-8")
        first = extract_deterministic(html)
        second = extract_deterministic(html)
        assert first.to_dict() == second.to_dict()
        person = next(m for m in first.mentions if m.kind == "person")
        assert person.extractor == "structured"
        assert person.source == "structure"
        assert person.normalized is not None and person.normalized.canonical == "李华"
        assert person.lang_pack is not None
        assert person.lang_pack.startswith("tier")
        assert "pymorphy3" not in person.lang_pack
