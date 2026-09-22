"""Contract tests for normalization (spec 007, T020-T022)."""

from __future__ import annotations

import hashlib

from extractors.normalize import normalize_pass, normalize_person_name
from extractors.types import TypedMention


class TestCanonicalization:
    def test_declined_ru_canonicalizes(self):
        m = normalize_person_name("Сергеем Ивановым")
        assert m.canonical == "Иванов Сергей"
        assert (m.given, m.family) == ("Сергей", "Иванов")
        assert m.latin == "Ivanov Sergey"

    def test_latin_name_round_trips_to_ru_canonical(self):
        m = normalize_person_name("Sergey Ivanov")
        assert m.canonical == "Иванов Сергей"
        assert m.latin == "Ivanov Sergey"

    def test_full_three_part_name(self):
        m = normalize_person_name("Иванов Сергей Петрович")
        assert m.canonical == "Иванов Сергей Петрович"
        assert (m.given, m.family, m.patronymic) == ("Сергей", "Иванов", "Петрович")

    def test_family_first_two_word_order_disambiguated(self):
        """'Иванов Сергей' (family-first, e.g. og.profile) keeps roles correct:
        morphology roles must overrule the naive given/family surface order."""
        m = normalize_person_name("Иванов Сергей")
        assert m.canonical == "Иванов Сергей"
        assert (m.given, m.family) == ("Сергей", "Иванов")

    def test_same_person_all_forms_share_canonical(self):
        forms = ["Иванов Сергей Петрович", "Иванов Сергей", "Сергеем Ивановым", "Sergey Ivanov"]
        canonicals = {normalize_person_name(f).canonical for f in forms}
        assert "Иванов Сергей" in canonicals


class TestInitials:
    def test_initials_are_hypothesis(self):
        evidence: dict = {}
        m = normalize_person_name("И. О. Иванов", initials=("И", "О"), evidence=evidence)
        assert m.hypothesis is True
        assert m.family == "Иванов"
        assert "expansion_hypotheses" in evidence
        assert m.canonical == "И. О. Иванов (иниц. И.О.)"


class TestTransformChain:
    def test_lemma_transform_is_recorded(self):
        m = normalize_person_name("Сергеем Ивановым")
        assert any("pymorphy3" in t and "lemma" in t for t in m.transforms)

    def test_latin_transform_uses_inverse_transliteration(self):
        m = normalize_person_name("Sergey Ivanov")
        assert any("translit" in t for t in m.transforms)


class TestNormalizePass:
    def test_pass_attaches_co_occurrence_and_hashes(self):
        ms = [
            TypedMention(kind="person", value="Сергей Иванов", extractor="persons", lang="ru"),
            TypedMention(kind="person", value="Ольга Петрова", extractor="persons", lang="ru"),
            TypedMention(kind="email", value="sergey@example-ivanov.ru", extractor="contacts"),
        ]
        out = normalize_pass(ms)
        by_value = {m.value: m for m in out}
        sergey = by_value["Сергей Иванов"]
        assert sergey.normalized.canonical == "Иванов Сергей"
        assert "contact_hashes" in sergey.evidence
        expected = hashlib.sha1(b"sergey@example-ivanov.ru").hexdigest()
        assert expected in sergey.evidence["contact_hashes"]
        # co-occurrence uses lemmatized canonical keys ("Петрова" -> "Петров").
        assert sergey.evidence["co_occurrence"] == ["Петров Ольга"]

    def test_pass_records_morphology_pack(self):
        out = normalize_pass([TypedMention(kind="person", value="Ольга Иванова", extractor="persons", lang="ru")])
        assert out[0].lang_pack == "pymorphy3@ru"

    def test_pass_is_deterministic(self):
        ms = [
            TypedMention(kind="person", value="Сергей Иванов", extractor="persons", lang="ru"),
            TypedMention(kind="email", value="sergey@example-ivanov.ru", extractor="contacts"),
        ]
        one = [m.to_dict() for m in normalize_pass(ms)]
        two = [m.to_dict() for m in normalize_pass(ms)]
        assert one == two