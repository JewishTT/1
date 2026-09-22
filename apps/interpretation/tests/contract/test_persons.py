"""Contract tests for the deterministic stack (spec 007, T014)."""

from __future__ import annotations

from extractors.persons import extract_persons
from extractors.types import TypedMention


class TestPersonsContract:
    def test_ru_comma_and_declension(self):
        mentions = extract_persons(
            "Иванов, Сергей Петрович родился в Казани, где живет Ольга Иванова."
        )
        values = {m.value: m for m in mentions}
        head = values["Иванов, Сергей Петрович"]
        # Dictionary run "Иванов Сергей Петрович" — highest-evidence source.
        assert head.source == "dictionary"
        assert head.confidence >= 0.9
        assert head.evidence.get("shape") == "ru"
        assert all(isinstance(m, TypedMention) for m in mentions)

    def test_declined_form_is_honest_low_confidence(self):
        mentions = extract_persons("Сергеем Ивановым из Казани написал И. О. Смирнов.")
        values = {m.value: m for m in mentions}
        declined = values["Сергеем Ивановым"]
        assert declined.source == "pattern"
        assert declined.confidence < 0.7  # declined pattern — honest degradation

    def test_initials_flag_hypothesis(self):
        mentions = extract_persons("И. О. Смирнов подписал документ.")
        hit = next(m for m in mentions if m.value == "И. О. Смирнов")
        assert hit.evidence.get("initials") == ["И", "О"]
        assert hit.source == "dictionary"

    def test_latin_two_word_name(self):
        mentions = extract_persons("Sergey Ivanov was born in Kazan.")
        hit = next(m for m in mentions if m.value == "Sergey Ivanov")
        assert hit.lang == "en"
        assert hit.source == "morph"
        assert hit.evidence.get("shape") == "latin"

    def test_byte_offsets_are_deterministic_and_monotonic(self):
        mentions = extract_persons("Иванов, Сергей Петрович и И. О. Смирнов.")
        offsets = [(m.offset, m.end_offset) for m in mentions]
        assert all(0 <= a < b for a, b in offsets)
        assert [a for a, _ in offsets] == sorted(a for a, _ in offsets)
        again = extract_persons("Иванов, Сергей Петрович и И. О. Смирнов.")
        assert [m.to_dict() for m in mentions] == [m.to_dict() for m in again]

    def test_kind_and_extractor_annotations(self):
        mentions = extract_persons("Ольга Петрова живёт в Санкт-Петербурге.")
        assert {m.kind for m in mentions} == {"person"}
        assert {m.extractor for m in mentions} == {"persons"}