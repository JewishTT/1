"""Contract tests for versioned dictionary extraction (spec 007, T015).

Covers the sanctions matcher (person/org with entity-id evidence), the
companies layer (via orgs extractor), and the geonames gazetteer — all
hermetic, backed by the built mini datasets (FR-8, NFR-1, C-7).
"""

from __future__ import annotations

from dictionaries import VERSIONS, automaton
from extractors.dictionary_entities import extract_dictionary_entities
from extractors.orgs import extract_organizations
from extractors.places import extract_places


class TestSanctionsDictionary:
    def test_sanctions_person_and_organization(self):
        mentions = extract_dictionary_entities("Владимир Путин заявил, что ФСБ работает.")
        by_value = {m.value: m for m in mentions}
        person = by_value["Владимир Путин"]
        assert person.kind == "person"
        assert person.dictionary == f"sanctions@{VERSIONS['sanctions']}"
        assert person.source == "dictionary"
        assert person.confidence == 1.0
        assert person.evidence["entity_id"] == "Q7747"
        org = by_value["ФСБ"]
        assert org.kind == "org"
        assert org.evidence["entity_id"] == "Q1635254"

    def test_sanctions_mentions_never_resolve(self):
        mentions = extract_dictionary_entities("Владимир Путин присутствовал на встрече.")
        assert {m.extractor for m in mentions} == {"sanctions"}
        for m in mentions:
            assert m.normalized is None  # dictionary layer does not resolve (I-2)

    def test_offset_is_byte_based(self):
        mentions = extract_dictionary_entities("  Владимир Путин")
        hit = next(m for m in mentions if m.value == "Владимир Путин")
        assert hit.offset == 2
        assert hit.end_offset == 2 + len("Владимир Путин".encode())

    def test_dataset_sidecars_are_hash_stamped(self):
        for kind, version in VERSIONS.items():
            meta, automaton_ = automaton(kind)
            assert meta.version == version
            assert len(meta.sha256) == 64
            assert automaton_ is not None


class TestCompanyDictionary:
    def test_company_match_stamped_with_link(self):
        mentions = extract_organizations("Сбербанк и Яндекс объявили о партнёрстве.")
        by_value = {m.value: m for m in mentions}
        assert by_value["Сбербанк"].dictionary == f"companies@{VERSIONS['companies']}"
        assert by_value["Сбербанк"].source == "dictionary"
        assert by_value["Сбербанк"].evidence["domain"] == "sberbank.ru"
        assert by_value["Яндекс"].evidence["country"] == "RU"


class TestGeonamesGazetteer:
    def test_city_match_with_coordinates(self):
        mentions = extract_places("родился в Казани, переехал в Москву.")
        by_value = {m.value: m for m in mentions}
        kazan = by_value["Казани"]
        assert kazan.dictionary == f"geonames@{VERSIONS['geonames']}"
        assert kazan.evidence["geo_id"] == "geo-551487"
        assert kazan.evidence["country"] == "RU"
        coords = kazan.evidence["coords"]
        assert abs(coords["lat"] - 55.7963) < 1e-3
        assert abs(coords["lon"] - 49.1088) < 1e-3

    def test_st_petersburg_multiword_alias(self):
        mentions = extract_places("Он работает в Санкт-Петербурге.")
        hit = next(m for m in mentions if m.value == "Санкт-Петербурге")
        assert hit.evidence["geo_id"] == "geo-498677"