"""Build the frozen labelled identity pair corpus (spec 030 T076, DON-ER-001).

Two clearly separated halves, because conflating them is how a benchmark becomes unfalsifiable:

**Authored** (``AUTHORED_PAIRS`` below) — hand-written cases. Every record names the kind of
real-world situation it stands for: transliteration of a person's name across registries, a
company alias, a surname changed on marriage, a shared office or a shared firm mailbox, a
registration number reformatted, two people with the same name and the same building, and cases
where the only thing separating two records is a national identifier that differs by one digit.
These are *authored*, not sampled: they are constructed to exercise a failure mode, and they are
labelled ``provenance: "authored"`` because no capture was made and no real person is in them.
They are realistic, not representative — see ``README.md`` for what that costs.

**Synthetic** (:func:`synthetic_pairs`) — deterministic template expansion. No RNG: every variant
is fixed in the table, so ``--verify`` reproduces the slice byte for byte. Each synthetic pair
records ``provenance: "synthetic"`` and a ``generator`` string naming the function that made it.

Both halves share the shape emitted by :func:`_pair`:

    pair_id, label, category, provenance, generator, rationale, ambiguity_reason,
    left, right

where ``label`` is ``match`` | ``non_match`` | ``ambiguous`` and each side is a record with a
``span_ref`` conforming to spec 030 contract 02 (R4: an identity candidate must carry the span
of each side's evidence, or be explicitly rendered un-grounded).

**Ambiguous cases are not optional.** A corpus with no ambiguous pairs cannot measure a false-merge
rate honestly, because the hard cases get quietly excluded and the rate that comes out describes
only the easy remainder. Ambiguous pairs are labelled ``ambiguous`` and are excluded from *both*
the match and the non-match denominators by every measurement script; counting them either way
would measure the label set, not the matcher.

Run::

    python build_corpus.py             # writes pairs.jsonl
    python build_corpus.py --verify    # re-derives and compares; non-zero exit on drift
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
CORPUS = HERE / "pairs.jsonl"

SELECTOR_SEMANTICS_VERSION = "document_char/1"

LABELS = ("match", "non_match", "ambiguous")


def rec(
    record_id: str,
    name: str,
    *,
    email: str | None = None,
    phone: str | None = None,
    org: str | None = None,
    address: str | None = None,
    id_number: str | None = None,
    birth_date: str | None = None,
    aliases: list[str] | None = None,
    lineage_root: str | None = None,
    observation_ref: str = "",
    uri: str = "",
    source_text: str | None = None,
    entity_type: str = "person",
) -> dict[str, Any]:
    """One record. ``source_text`` is the evidence; the span and digest point into it."""
    text = source_text if source_text is not None else " | ".join(
        str(v) for v in (name, email, phone, org, address, id_number, birth_date) if v
    )
    start = text.index(name) if name and name in text else 0
    return {
        "record_id": record_id,
        "entity_type": entity_type,
        "name": name,
        "email": email,
        "phone": phone,
        "org": org,
        "address": address,
        "id_number": id_number,
        "birth_date": birth_date,
        "aliases": list(aliases or []),
        # What this document ultimately derives from. T080: corroboration counts these, not
        # hostnames — twenty mirrors of one press release are one source wearing twenty hats.
        "lineage_root": lineage_root or f"LR-{record_id}",
        "source_text": text,
        "blob_digest": "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "span_ref": {
            "observation_ref": observation_ref or f"obs-{record_id}",
            "blob_digest": "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "selector": {
                "char_span": {
                    "start": start,
                    "end": start + len(name),
                    "encoding": "utf-8",
                }
            },
            "source_locator": {"uri": uri or f"https://corpus.example/records/{record_id}", "fragment": ""},
            "selector_semantics_version": SELECTOR_SEMANTICS_VERSION,
        },
    }


def _pair(
    pair_id: str,
    label: str,
    category: str,
    left: dict[str, Any],
    right: dict[str, Any],
    rationale: str,
    *,
    provenance: str = "authored",
    generator: str | None = None,
    ambiguity_reason: str | None = None,
) -> dict[str, Any]:
    if label not in LABELS:
        raise ValueError(f"label must be one of {LABELS}, got {label!r}")
    if label == "ambiguous" and not ambiguity_reason:
        raise ValueError(f"{pair_id}: an ambiguous pair must say what makes it ambiguous")
    if label != "ambiguous" and ambiguity_reason:
        raise ValueError(f"{pair_id}: only an ambiguous pair carries an ambiguity_reason")
    return {
        "pair_id": pair_id,
        "label": label,
        "ambiguous": label == "ambiguous",
        "category": category,
        "provenance": provenance,
        "generator": generator,
        "rationale": rationale,
        "ambiguity_reason": ambiguity_reason,
        "left": left,
        "right": right,
    }


# --------------------------------------------------------------------------------------
# Authored records
# --------------------------------------------------------------------------------------

R_VLADIMIR_CYR = rec(
    "R-V01", "Владимир Петров",
    email="v.petrov@nordwind.example", phone="+7 921 555 0122", org="Nordwind Logistics",
    address="12 Leningradskaya, Saint Petersburg", id_number="RU-771234", birth_date="1979-04-11",
    lineage_root="LR-nordwind-employee-register", uri="https://corpus.example/ru/nordwind/register",
)
R_VLADIMIR_LAT = rec(
    "R-V02", "Vladimir Petrov",
    email="v.petrov@nordwind.example", phone="+7 921 555 0122", org="Nordwind Logistics LLC",
    address="12 Leningradskaya St, Saint Petersburg", id_number="RU-771234", birth_date="1979-04-11",
    lineage_root="LR-nordwind-press-kit", uri="https://corpus.example/intl/nordwind/press-kit",
)
R_VLADIMIR_OTHER = rec(
    "R-V03", "Vladimir Petrov",
    email="v.petrov@kestrel.example", phone="+44 20 7123 4567", org="Kestrel Analytics",
    address="17 Farringdon Road, London", id_number="GB-998211", birth_date="1979-04-11",
    lineage_root="LR-company-registries", uri="https://corpus.example/gb/kestrel/directors",
)

R_ANNA_UML = rec(
    "R-A01", "Anna Müller",
    email="a.mueller@weberkontor.example", phone="+49 30 1234567", org="Weber Kontor GmbH",
    address="Kurfuerstendamm 210, Berlin", id_number="DE-4455210", birth_date="1985-09-02",
    lineage_root="LR-weber-annual-report", uri="https://corpus.example/de/weber/annual-report-2019",
)
R_ANNA_UE = rec(
    "R-A02", "Anna Mueller",
    email="a.mueller@weberkontor.example", phone="+49 30 1234567", org="Weber Kontor GmbH",
    address="Kurfuerstendamm 210, Berlin", id_number="DE-4455210", birth_date="1985-09-02",
    lineage_root="LR-weber-trade-press", uri="https://corpus.example/de/weber/trade-press",
)
R_ANNA_SURNAME_FIRST = rec(
    "R-A03", "Mueller Anna",
    email="a.mueller@weberkontor.example", phone="+49 30 1234567", org="Weber Kontor GmbH",
    address="Kurfuerstendamm 210, Berlin", id_number="DE-4455210", birth_date="1985-09-02",
    aliases=["A. Mueller"], lineage_root="LR-weber-annual-report",
    uri="https://corpus.example/de/weber/annual-report-2019",
)
R_ANNA_OTHER = rec(
    "R-A04", "Anna Mueller",
    email="a.mueller@brandt-partners.example", phone="+49 69 9876543", org="Brandt Partners",
    address="Neue Mainzer Str. 52, Frankfurt", id_number="DE-7788990", birth_date="1991-04-17",
    lineage_root="LR-company-registries", uri="https://corpus.example/de/brandt/registry",
)

R_LUKASZ = rec(
    "R-L01", "Lukasz Nowak",
    email="l.nowak@wislapaper.example", phone="+48 122 345678", org="Wisla Paper Sp. z o.o.",
    address="Marszalkowska 1, Warszawa", id_number="PL-88231144", birth_date="1991-12-30",
    lineage_root="LR-wisla-employee-register", uri="https://corpus.example/pl/wisla/register",
)
R_LUKASZ_DIACRITIC = rec(
    "R-L02", "Łukasz Nowak",
    email="l.nowak@wislapaper.example", phone="+48 122 345678", org="Wisla Paper Sp. z o.o.",
    address="Marszalkowska 1, Warsaw", id_number="PL-88231144", birth_date="1991-12-30",
    lineage_root="LR-wisla-trade-fair", uri="https://corpus.example/intl/wisla/fair-2021",
)

R_JOSE = rec(
    "R-J01", "Jose Garcia",
    email="j.garcia@alhambra.example", phone="+34 600 111222", org="Alhambra Ingenieria",
    address="Gran Via 31, Madrid", id_number="ES-11223344", birth_date="1968-07-19",
    lineage_root="LR-alhambra-directory", uri="https://corpus.example/es/alhambra/directory",
)
R_JOSE_DIACRITIC = rec(
    "R-J02", "José García",
    email="j.garcia@alhambra.example", phone="+34 600 111222", org="Alhambra Ingenieria",
    address="Gran Vía 31, Madrid", id_number="ES-11223344", birth_date="1968-07-19",
    lineage_root="LR-alhambra-registry", uri="https://corpus.example/es/alhambra/registry",
)

R_SOREN = rec(
    "R-S01", "Soren Dahl",
    email="soren.dahl@nordvind.example", phone="+47 912 34567", org="Nordvind Marine AS",
    address="Bryggen 9, Bergen", id_number="NO-55667788", birth_date="1972-02-14",
    lineage_root="LR-nordvind-employee-register", uri="https://corpus.example/no/nordvind/register",
)
R_SOREN_DIACRITIC = rec(
    "R-S02", "Søren Dahl",
    email="soren.dahl@nordvind.example", phone="+47 912 34567", org="Nordvind Marine AS",
    address="Bryggen 9, Bergen", id_number="NO-55667788", birth_date="1972-02-14",
    lineage_root="LR-nordvind-safety-notice", uri="https://corpus.example/no/nordvind/safety-notice",
)

R_STEFAN = rec(
    "R-T01", "Stefan Ionescu",
    email="s.ionescu@carpathia.example", phone="+40 721 234567", org="Carpathia Logistics SRL",
    address="Bulevardul Unirii 4, Bucuresti", id_number="RO-33901122", birth_date="1988-05-05",
    lineage_root="LR-carpathia-registry", uri="https://corpus.example/ro/carpathia/registry",
)
R_STEFAN_DIACRITIC = rec(
    "R-T02", "Ștefan Ionescu",
    email="s.ionescu@carpathia.example", phone="+40 721 234567", org="Carpathia Logistics SRL",
    address="Bulevardul Unirii 4, Bucuresti", id_number="RO-33901122", birth_date="1988-05-05",
    lineage_root="LR-carpathia-press-kit", uri="https://corpus.example/intl/carpathia/press-kit",
)

R_AHMED = rec(
    "R-H01", "Ahmed Al-Sayed",
    email="a.alsayed@nilewire.example", phone="+20 100 1234567", org="Nile Wire",
    address="26 Talaat Harb St, Cairo", id_number="EG-77889900", birth_date="1983-11-23",
    lineage_root="LR-nilewire-directory", uri="https://corpus.example/eg/nilewire/directory",
)
R_AHMED_PUNCT = rec(
    "R-H02", "Ahmed Alsayed",
    email="a.alsayed@nilewire.example", phone="+20 100 1234567", org="Nile Wire",
    address="26 Talaat Harb St, Cairo", id_number="EG-77889900", birth_date="1983-11-23",
    lineage_root="LR-nilewire-registry", uri="https://corpus.example/eg/nilewire/registry",
)

R_MARIA_OLD = rec(
    "R-M01", "Maria Kovac",
    email="m.kovac@jadranska.example", phone="+385 91 234567", org="Jadranska Brodogradnja",
    address="Obala kneza Branimira 3, Split", id_number="HR-11223344", birth_date="1990-03-08",
    lineage_root="LR-jadranska-registry-2018", uri="https://corpus.example/hr/jadranska/registry-2018",
)
R_MARIA_NEW = rec(
    "R-M02", "Maria Horvat",
    email="m.horvat@jadranska.example", phone="+385 91 234567", org="Jadranska Brodogradnja",
    address="Obala kneza Branimira 3, Split", id_number="HR-11223344", birth_date="1990-03-08",
    aliases=["née Kovač"], lineage_root="LR-jadranska-registry-2024",
    uri="https://corpus.example/hr/jadranska/registry-2024",
)
R_MARIJA = rec(
    "R-M03", "Marija Horvat",
    email="marija.horvat@jadranska.example", phone="+385 91 234568", org="Jadranska Brodogradnja",
    address="Obala kneza Branimira 3, Split", id_number="HR-55667788", birth_date="1994-03-08",
    lineage_root="LR-jadranska-registry-2024", uri="https://corpus.example/hr/jadranska/registry-2024",
)

R_ACME_LTD = rec(
    "R-C01", "Acme Industrial Ltd", email="info@acme.example", phone="+44 20 7123 4567",
    org="Acme Industrial Ltd", address="1 Finsbury Square, London", id_number="GB-01002003",
    entity_type="organisation", lineage_root="LR-companies-house",
    uri="https://corpus.example/gb/companies-house/acme",
)
R_ACME_LLC = rec(
    "R-C02", "Acme Industries LLC", email="info@acme.example", phone="+1 212 555 0143",
    org="Acme Industries LLC", address="1 Finsbury Square, London", id_number="GB-01002-003",
    entity_type="organisation", lineage_root="LR-acme-press-release",
    uri="https://corpus.example/us/acme/press-release",
)
R_BOREALIS = rec(
    "R-C03", "Borealis Trading BV", email="info@borealis.example", phone="+31 20 555 8899",
    org="Borealis Trading BV", address="Herengracht 100, Amsterdam", id_number="NL-22334455",
    entity_type="organisation", lineage_root="LR-kvk-register", uri="https://corpus.example/nl/kvk/borealis",
)
R_BOREALIS_DOTTED = rec(
    "R-C04", "Borealis Trading B.V.", email="info@borealis.example", phone="+31 20 555 8899",
    org="Borealis Trading B.V.", address="Herengracht 100, Amsterdam", id_number="NL-22334455",
    entity_type="organisation", lineage_root="LR-borealis-website", uri="https://corpus.example/nl/borealis/site",
)
R_CARBON_EX = rec(
    "R-C05", "Carbon Exemplar Ltd", email="hello@carbonexemplar.example", phone="+44 20 7123 9999",
    org="Carbon Exemplar Ltd", address="1 Finsbury Square, London", id_number="GB-77889900",
    entity_type="organisation", lineage_root="LR-companies-house",
    uri="https://corpus.example/gb/companies-house/carbonexemplar",
)
R_CYAN_CO = rec(
    "R-C06", "Cyan Co-operative", email="hello@cyan.example", phone="+44 20 7123 8888",
    org="Cyan Co-operative", address="1 Finsbury Square, London", id_number="GB-55667788",
    entity_type="organisation", lineage_root="LR-companies-house",
    uri="https://corpus.example/gb/companies-house/cyan",
)

R_PAVEL_A = rec(
    "R-P01", "Pavel Sokolov",
    email="p.sokolov@tekhnolab.example", phone="+7 921 555 0222", org="Tekhnolab",
    address="12 Leningradskaya, Saint Petersburg", id_number="RU-44112233", birth_date="1995-06-01",
    lineage_root="LR-tekhnolab-badge-office", uri="https://corpus.example/ru/tekhnolab/badges",
)
R_PAVEL_B = rec(
    "R-P02", "Pavel Sokolov",
    email="p.sokolov@tekhnolab.example", phone="+7 921 555 0222", org="Tekhnolab",
    address="12 Leningradskaya, Saint Petersburg", id_number="RU-99887766", birth_date="1983-06-01",
    lineage_root="LR-tekhnolab-conference-list", uri="https://corpus.example/intl/tekhnolab/2023",
)
R_IRINA_A = rec(
    "R-P03", "Irina Volkova",
    email="i.volkova@tekhnolab.example", phone="+7 921 555 0333", org="Tekhnolab",
    address="12 Leningradskaya, Saint Petersburg", id_number="RU-11223344", birth_date="1992-08-17",
    lineage_root="LR-tekhnolab-badge-office", uri="https://corpus.example/ru/tekhnolab/badges",
)
R_IRINA_B = rec(
    "R-P04", "Irina Volkova",
    email="i.volkova@tekhnolab.example", phone="+7 921 555 0333", org="Tekhnolab",
    address="12 Leningradskaya, Saint Petersburg", id_number="RU-11223345", birth_date="1992-08-17",
    lineage_root="LR-tekhnolab-registry-export", uri="https://corpus.example/ru/tekhnolab/export",
)

R_ELENA_A = rec(
    "R-E01", "Elena Marchetti",
    email="e.marchetti@vialuce.example", phone="+39 06 55501234", org="Via Luce",
    address="Via Nazionale 44, Roma", id_number="IT-44556677", birth_date="1975-03-09",
    lineage_root="LR-vialuce-directory", uri="https://corpus.example/it/vialuce/directory",
)
R_ELENA_B = rec(
    "R-E02", "Elena Marchetti",
    email="e.marchetti@vialuce.example", phone="+39 06 55501234", org="Via Luce",
    address="Via Nazionale 44, Roma", id_number="IT-44556677", birth_date="1978-03-09",
    lineage_root="LR-vialuce-claims-extract", uri="https://corpus.example/it/vialuce/claims",
)
R_ELENA_C = rec(
    "R-E03", "Elena Marchetti",
    email="e.marchetti@vialuce.example", phone="+39 06 55501234", org="Via Luce",
    address="Via Nazionale 44, Roma", id_number="IT-44556678", birth_date="1975-03-09",
    lineage_root="LR-vialuce-directory", uri="https://corpus.example/it/vialuce/directory",
)

R_HANA_A = rec(
    "R-N01", "Hana Novotna",
    org="Zeleny Kridlo", address="Vodickova 12, Praha", id_number="CZ-55667788",
    birth_date="1994-02-08", lineage_root="LR-zeleny-contract-register",
    uri="https://corpus.example/cz/zeleny/contracts",
)
R_HANA_B = rec(
    "R-N02", "Hana Novotná",
    org="Zeleny Kridlo", address="Vodickova 12, Praha", id_number="CZ-55667788",
    birth_date="1994-02-08", lineage_root="LR-zeleny-exhibit-list",
    uri="https://corpus.example/cz/zeleny/exhibits",
)
R_HANA_C = rec(
    "R-N03", "Hana Novotna",
    org="Zeleny Kridlo", address="Vodickova 12, Praha", id_number="CZ-55667789",
    birth_date="1988-02-08", lineage_root="LR-zeleny-exhibit-list",
    uri="https://corpus.example/cz/zeleny/exhibits",
)

R_TOMASZ_A = rec(
    "R-K01", "Tomasz Wieczorek",
    org="Warta Ceramika", address="Wielkopolska 3, Poznan", id_number="PL-44556677",
    lineage_root="LR-warta-aggregator-a", uri="https://corpus.example/pl/aggregator-a/warta",
)
R_TOMASZ_B = rec(
    "R-K02", "Tomasz Wieczorek",
    org="Warta Ceramika", address="Wielkopolska 3, Poznan", id_number="PL-44556677",
    lineage_root="LR-warta-aggregator-b", uri="https://corpus.example/pl/aggregator-b/warta",
)

R_JOERG = rec(
    "R-G01", "Jörg Böhm",
    email="j.boehm@salzberg.example", phone="+43 6622 12345", org="Salzberg Chemie",
    address="Mozartplatz 3, Salzburg", id_number="AT-77889900", birth_date="1969-10-01",
    lineage_root="LR-salzberg-partner-list", uri="https://corpus.example/at/salzberg/partners",
)
R_JOERG_LATIN = rec(
    "R-G02", "Joerg Boehm",
    email="j.boehm@salzberg.example", phone="+43 6622 12345", org="Salzberg Chemie",
    address="Mozartplatz 3, Salzburg", id_number="AT-77889901", birth_date="1969-10-01",
    lineage_root="LR-salzberg-newsletter", uri="https://corpus.example/intl/salzberg/newsletter",
)

R_SERGEI_OLD = rec(
    "R-U01", "Sergei Sokolov",
    email="s.sokolov@vega.example", phone="+380 44 5551234", org="Vega Systems",
    address="5 Kulneva, Kyiv", id_number="UA-33445566", birth_date="1970-01-01",
    lineage_root="LR-vega-employee-register", uri="https://corpus.example/ua/vega/register",
)
R_SERGEI_YOUNG = rec(
    "R-U02", "Sergei Sokolov",
    email="s.sokolov@vega.example", phone="+380 44 5551234", org="Vega Systems",
    address="5 Kulneva, Kyiv", id_number="UA-33445577", birth_date="2001-01-01",
    lineage_root="LR-vega-internship-list", uri="https://corpus.example/ua/vega/interns",
)

R_LENA_F = rec(
    "R-F01", "Lena Fedorova",
    email="office@fedorova-partners.example", phone="+7 495 5551234", org="Fedorova & Partners",
    address="8 Prechistenskaya, Moscow", id_number="RU-55667788", birth_date="1980-05-09",
    lineage_root="LR-fedorova-website", uri="https://corpus.example/ru/fedorova/site",
)
R_NINA_F = rec(
    "R-F02", "Nina Fedorova",
    email="office@fedorova-partners.example", phone="+7 495 5551234", org="Fedorova & Partners",
    address="8 Prechistenskaya, Moscow", id_number="RU-55667789", birth_date="1984-05-09",
    lineage_root="LR-fedorova-website", uri="https://corpus.example/ru/fedorova/site",
)
R_LENA_F2 = rec(
    "R-F03", "Lena Fedorova",
    email="office@fedorova-partners.example", phone="+7 495 5551234", org="Fedorova & Partners",
    address="8 Prechistenskaya, Moscow", id_number="RU-55667790", birth_date="1980-05-09",
    lineage_root="LR-registry-extract-2022", uri="https://corpus.example/ru/fedorova/registry-2022",
)

R_RANIA_OLD = rec(
    "R-R01", "Rania Haddad",
    email="rania@levant-data.example", phone="+961 1 555123", org="Levant Data",
    address="14 Bliss St, Beirut", id_number="LB-22334455",
    lineage_root="LR-levant-website", uri="https://corpus.example/lb/levant/site",
)
R_RANIA_NEW = rec(
    "R-R02", "Rania Al-Haddad",
    email="rania.haddad@levant-data.example", org="Levant Data",
    address="14 Bliss St, Beirut",
    lineage_root="LR-levant-conference-list", uri="https://corpus.example/lb/levant/speakers",
)

R_WANG_LATIN = rec(
    "R-W01", "Wang Wei",
    email="w.wang@zhonghe.example", phone="+86 21 5555 1234", org="Zhonghe Trading",
    address="88 Nanjing Rd, Shanghai", id_number="CN-310115198001010011", birth_date="1980-01-01",
    lineage_root="LR-zhonghe-website", uri="https://corpus.example/cn/zhonghe/en/team",
)
R_WANG_HAN = rec(
    "R-W02", "王伟",
    email="w.wang@zhonghe.example", phone="+86 21 5555 1234", org="中合贸易",
    address="上海南京路 88 号", id_number="CN-310115198001010011", birth_date="1980-01-01",
    lineage_root="LR-zhonghe-registry", uri="https://corpus.example/cn/zhonghe/registry",
)

R_ALICE = rec(
    "R-Z01", "Alice Brown",
    email="alice.brown@acme-delta.example", phone="+1 415 5550101", org="Acme Delta",
    address="500 Harrison St, San Francisco", id_number="US-CA-4455667", birth_date="1986-06-15",
    lineage_root="LR-acme-delta-directory", uri="https://corpus.example/us/acme-delta/directory",
)
R_BOB = rec(
    "R-Z02", "Bob Green",
    email="bob.green@acme-delta.example", phone="+1 415 5550102", org="Acme Delta",
    address="500 Harrison St, San Francisco", id_number="US-CA-4455668", birth_date="1983-02-20",
    lineage_root="LR-acme-delta-directory", uri="https://corpus.example/us/acme-delta/directory",
)
R_KARIM = rec(
    "R-Z03", "Karim Haddad",
    email="karim.haddad@nile-solar.example", phone="+20 111 2223333", org="Nile Solar",
    address="7 Talaat Harb St, Cairo", id_number="EG-11223344", birth_date="1993-10-05",
    lineage_root="LR-nile-solar-directory", uri="https://corpus.example/eg/nile-solar/directory",
)
R_YUSUF = rec(
    "R-Z04", "Yusuf Khalil",
    email="y.khalil@levant-logistics.example", phone="+961 3 555444", org="Levant Logistics",
    address="2 Abdel Kader St, Beirut", id_number="LB-99887766", birth_date="1979-08-30",
    lineage_root="LR-levant-logistics-registry", uri="https://corpus.example/lb/levant-logistics/registry",
)

R_PASSPORT_A = rec(
    "R-PP01", "Ingrid Halvorsen",
    email="i.halvorsen@fjord.example", phone="+47 555 12345", org="Fjord Analytics",
    address="3 Bryggen, Bergen", id_number="AB1234567", birth_date="1982-07-04",
    lineage_root="LR-fjord-badge-office", uri="https://corpus.example/no/fjord/badges",
)
R_PASSPORT_B = rec(
    "R-PP02", "Ingrid Halvorsen",
    email="i.halvorsen@fjord.example", phone="+47 555 12345", org="Fjord Analytics",
    address="3 Bryggen, Bergen", id_number="AB 1234567", birth_date="1982-07-04",
    lineage_root="LR-fjord-badge-office", uri="https://corpus.example/no/fjord/badges",
)
R_INGRID_OTHER = rec(
    "R-PP03", "Ingrid Halvorsen",
    email="i.halvorsen@nordvind.example", phone="+47 555 99999", org="Nordvind Marine AS",
    address="Bryggen 9, Bergen", id_number="AB7654321", birth_date="1982-07-04",
    lineage_root="LR-nordvind-employee-register", uri="https://corpus.example/no/nordvind/register",
)


AUTHORED_PAIRS: list[dict[str, Any]] = [
    # -- transliteration variants ----------------------------------------------------------------
    _pair("ID-A001", "match", "transliteration_variant", R_VLADIMIR_CYR, R_VLADIMIR_LAT,
          "Same national id and phone. Cyrillic name vs Latin transliteration across a domestic "
          "registry and an English press kit; org gains an LLC suffix, address gains 'St'."),
    _pair("ID-A002", "match", "transliteration_variant", R_ANNA_UML, R_ANNA_UE,
          "Umlaut vs ue in an annual report and a trade-press mention. Everything else identical."),
    _pair("ID-A003", "match", "transliteration_variant", R_ANNA_UML, R_ANNA_SURNAME_FIRST,
          "German 'Nachname, Vorname' ordering. Same id; a token-order-blind matcher sees two "
          "different-looking strings for one person."),
    _pair("ID-A004", "match", "transliteration_variant", R_LUKASZ, R_LUKASZ_DIACRITIC,
          "Polish l-slash, same national id and email."),
    _pair("ID-A005", "match", "transliteration_variant", R_JOSE, R_JOSE_DIACRITIC,
          "Spanish accents stripped in one registry, present in the other. Same id."),
    _pair("ID-A006", "match", "transliteration_variant", R_SOREN, R_SOREN_DIACRITIC,
          "Norwegian stroke-slash o. Same id and phone."),
    _pair("ID-A007", "match", "transliteration_variant", R_STEFAN, R_STEFAN_DIACRITIC,
          "Romanian comma-below s. Same id and phone."),
    _pair("ID-A008", "match", "transliteration_variant", R_AHMED, R_AHMED_PUNCT,
          "Hyphen dropped from a family name across two Egyptian registries. Same id."),
    _pair("ID-A009", "match", "transliteration_variant", R_WANG_LATIN, R_WANG_HAN,
          "Pinyin vs Han characters and English vs Chinese org and address. Same id and email; "
          "a matcher that folds to ASCII sees no name signal at all."),
    _pair("ID-A010", "match", "transliteration_variant", R_PASSPORT_A, R_PASSPORT_B,
          "Passport number with and without its separator, from the same badge-office export."),

    # -- company alias ----------------------------------------------------------------------------
    _pair("ID-A011", "match", "company_alias", R_BOREALIS, R_BOREALIS_DOTTED,
          "Legal-form abbreviation written out ('BV' vs 'B.V.') on the company website versus "
          "the KvK register. Same company number."),
    _pair("ID-A012", "match", "old_new_identifier", R_ACME_LTD, R_ACME_LLC,
          "Same company number reformatted (01002003 vs 01002-003) and a subsidiary reading. "
          "The press release and the Companies House filing describe one entity in two legal "
          "clothes; whether it is a merge depends on the jurisdiction, which the corpus cannot "
          "resolve — hence the label 'match' is on the company number, and a reviewer would "
          "still want to see it."),
    _pair("ID-A013", "match", "name_change", R_MARIA_OLD, R_MARIA_NEW,
          "Surname changed on marriage; the same national id appears under both names in the "
          "2018 and 2024 registry snapshots."),

    # -- same name, different person ---------------------------------------------------------------
    _pair("ID-A014", "non_match", "same_name_different_person", R_VLADIMIR_LAT, R_VLADIMIR_OTHER,
          "Same name, same date of birth, different national id, different country, different "
          "employer. The date of birth is shared, which is the trap: a do-anything sensible rule "
          "on name+dob still fuses two people here."),
    _pair("ID-A015", "non_match", "same_name_different_person", R_ANNA_UE, R_ANNA_OTHER,
          "Same name, different employer, different city, different national id."),
    _pair("ID-A016", "non_match", "same_name_different_person", R_MARIA_NEW, R_MARIJA,
          "Near-identical name (Marija/Maria) at the same employer in the same building; "
          "national id and date of birth both differ."),
    _pair("ID-A017", "non_match", "same_name_different_person", R_PASSPORT_A, R_INGRID_OTHER,
          "Same name and same date of birth, different employer, different passport number."),

    # -- shared address ----------------------------------------------------------------------------
    _pair("ID-A018", "non_match", "shared_address", R_PAVEL_A, R_PAVEL_B,
          "Two Pauls Sokolovs registered at one co-working address on the same badge system. "
          "Name, employer, address and email all identical; national id and date of birth both "
          "differ. This is the pair that fuses two people if the matcher only sees what the "
          "matcher's fields can see."),
    _pair("ID-A019", "non_match", "shared_address", R_ACME_LTD, R_CARBON_EX,
          "Two unrelated companies registered at one London address. Different company numbers, "
          "different contact points; only the building is shared."),
    _pair("ID-A020", "non_match", "shared_address", R_CARBON_EX, R_CYAN_CO,
          "Three organisations at 1 Finsbury Square. Distinct company numbers; a name-only "
          "matcher would be one token away from fusing them."),

    # -- conflicting dates --------------------------------------------------------------------------
    _pair("ID-A021", "non_match", "conflicting_dates", R_ELENA_A, R_ELENA_C,
          "Same person-shaped record, same email and phone, national id differs in the last "
          "digit and the date of birth is identical. Two of the three matchable fields are exact."),
    _pair("ID-A022", "match", "old_new_identifier", R_HANA_A, R_HANA_B,
          "Same national id and same employer; the only difference is a diacritic on the surname "
          "and which of two registries the row was read from."),

    # -- incomplete fields --------------------------------------------------------------------------
    _pair("ID-A023", "non_match", "incomplete_fields", R_HANA_A, R_HANA_C,
          "Two records with no email and no phone at all — the fields a Fellegi-Sunter profile "
          "leans on. Employer and street agree; national id and year of birth do not. Nothing "
          "in the matchable field set can see the disagreement."),
    _pair("ID-A024", "ambiguous", "ambiguous", R_TOMASZ_A, R_TOMASZ_B,
          "Byte-identical on every field both aggregators publish, from two vendors. One person "
          "listed twice, or the same name at one employer listed twice — the corpus cannot tell, "
          "and neither can any matcher.",
          ambiguity_reason="Two aggregators listing one person, and two people who are genuinely "
          "identical on every published field, are the same observation."),

    # -- explicit ambiguous -------------------------------------------------------------------------
    _pair("ID-A025", "ambiguous", "ambiguous", R_IRINA_A, R_IRINA_B,
          "Identical in every field except the last digit of a national id (…344 vs …345). "
          "Either a transcription error in the export or two people sharing a name, an employer, "
          "a phone number and a desk.",
          ambiguity_reason="A one-digit identifier difference is either a typo or a person; the "
          "published evidence contains nothing that distinguishes them."),
    _pair("ID-A026", "ambiguous", "ambiguous", R_ELENA_A, R_ELENA_B,
          "Same id, same contact, three-year date-of-birth gap. Could be a keying error, or two "
          "sisters who share everything visible.",
          ambiguity_reason="Date-of-birth disagreement against an identical national id has no "
          "reading that the evidence settles."),
    _pair("ID-A027", "ambiguous", "ambiguous", R_JOERG, R_JOERG_LATIN,
          "Latin transliteration of an umlaut name, same email and phone, national ids differ in "
          "the last digit only.",
          ambiguity_reason="Transliteration plus a one-digit id difference: renaming or two "
          "people, indistinguishable in the published record."),
    _pair("ID-A028", "ambiguous", "ambiguous", R_SERGEI_OLD, R_SERGEI_YOUNG,
          "Identical name, employer, mailbox and phone; ids differ and the dates of birth are "
          "thirty-one years apart. The shared mailbox and the shared surname are equally "
          "explained by father and son.",
          ambiguity_reason="Parent and child sharing a surname, an employer and a mailbox, or one "
          "person recorded twice with a birth-date typo."),
    _pair("ID-A029", "ambiguous", "ambiguous", R_LENA_F, R_NINA_F,
          "Two different first names, one shared firm mailbox, one shared address. Firm staff "
          "genuinely do share a contact address; so do two records for the same person indexed "
          "under a different given name.",
          ambiguity_reason="A shared firm mailbox supports either 'two staff' or 'one person, two "
          "given-name variants'; the record does not distinguish them."),
    _pair("ID-A030", "ambiguous", "ambiguous", R_LENA_F, R_LENA_F2,
          "Same name, mailbox, address and date of birth, three different national ids across "
          "three extracts.",
          ambiguity_reason="Three identifiers for one person is either three extracts disagreeing "
          "or three people who share all four visible fields."),
    _pair("ID-A031", "ambiguous", "ambiguous", R_RANIA_OLD, R_RANIA_NEW,
          "Name change plus a changed email, with no identifier on either side and no date of "
          "birth in either record.",
          ambiguity_reason="A marriage and an email change, or two people with the same employer "
          "and employer-only identifiers."),

    # -- true negatives ------------------------------------------------------------------------------
    _pair("ID-A032", "non_match", "true_negative", R_ALICE, R_BOB,
          "Same employer domain and the same building. Nothing else is shared: name, email, "
          "phone, id and date of birth all differ."),
    _pair("ID-A033", "non_match", "true_negative", R_KARIM, R_YUSUF,
          "Same first name, both Middle Eastern, both in the region. Different employers, "
          "different cities, different ids. A phonetic matcher on the surname alone will not "
          "save you here."),
    _pair("ID-A034", "non_match", "true_negative", R_KARIM, R_AHMED_PUNCT,
          "Same country, same city street, different employer and different id."),
    _pair("ID-A035", "non_match", "true_negative", R_BOB, R_CYAN_CO,
          "A person and an organisation at the same address with a near-matching token in the "
          "name. Entity type alone rules it out; a name-only matcher does not look at type."),
]


# --------------------------------------------------------------------------------------
# Synthetic slice
# --------------------------------------------------------------------------------------

#: Deterministic perturbation templates. No RNG: every expansion is fixed, so the slice is
#: reproducible byte for byte and a reviewer can read exactly what was generated.
SYNTHETIC_VARIANTS: tuple[tuple[str, str, str, str], ...] = (
    # (suffix, name_a, name_b, transformation)
    ("01", "Marta Silva", "Marta Silva", "identity"),
    ("02", "Marta Silva", "Marta da Silva", "name_particle_added"),
    ("03", "Marta Silva", "Marta Silua", "character_transposition"),
    ("04", "Marta Silva", "Marta Silva", "identity"),
    ("05", "Ola Nowicka", "Ola Nowicka", "identity"),
    ("06", "Ola Nowicka", "Ola Nowicka", "identity"),
    ("07", "Ola Nowicka", "Ola Nöwicka", "umlaut_variant"),
    ("08", "Ola Nowicka", "Ola Nowik", "truncation"),
    ("09", "Petra Kral", "Petra Kral", "identity"),
    ("10", "Petra Kral", "Petra Král", "accent_variant"),
    ("11", "Petra Kral", "Petra Kral", "identity"),
    ("12", "Petra Kral", "Petra Kral", "identity"),
)


def synthetic_pairs() -> list[dict[str, Any]]:
    """Template expansion, no randomness, seed-free by construction.

    Two families. *Collision* pairs put different people in one shared office so the matchable
    fields agree; *identity* pairs are one record re-emitted with a surface perturbation.
    Labels are assigned from the template table, not from what a matcher does with them.
    """
    generated: list[dict[str, Any]] = []
    organisations = (
        ("Teknomir Sp. z o.o.", "Ul. Polna 4, Gdansk", "PL-22445566"),
        ("Baltline OY", "Satamakatu 8, Helsinki", "FI-11223344"),
        ("Vistula Metals SA", "Zamoyskiego 3, Lublin", "PL-55667788"),
        ("Sunds Gjutar AB", "Storgatan 12, Malmo", "SE-44556677"),
        ("Oder Logistik GmbH", "Odrallee 5, Szczecin", "DE-33445566"),
        ("Bratislava Trading s.r.o.", "Obchodna 11, Bratislava", "SK-77889900"),
        ("Moskva Service LLC", "Tverskaya 7, Moscow", "RU-66778899"),
        ("Sakhalin Line", "Korfu 2, Yuzhno-Sakhalinsk", "RU-44556677"),
        ("Gdansk Marine", "Dluga 45, Gdansk", "PL-99001122"),
        ("Riga Freight AS", "Kalku iela 3, Riga", "LV-22334455"),
        ("Tallinn Timber OU", "Narva maantee 7, Tallinn", "EE-55667788"),
        ("Kaunas Metal UAB", "Laisves al. 9, Kaunas", "LT-33445566"),
    )

    for suffix, name_a, name_b, transformation in SYNTHETIC_VARIANTS:
        org, address, id_number = organisations[int(suffix) - 1]
        same_person = transformation in ("identity", "name_particle_added")
        left = rec(
            f"R-S{suffix}A", name_a, email=f"m{seed_digits(suffix)}@synthetic.example",
            phone=f"+48 61 555 {int(suffix):04d}", org=org, address=address,
            id_number=id_number if same_person else rotate_last(id_number),
            birth_date="1990-01-01" if same_person else "1992-01-01",
            lineage_root=f"LR-synthetic-org-{org}",
            uri=f"https://corpus.example/synthetic/{org.lower().replace(' ', '-')}/listing-a",
        )
        right = rec(
            f"R-S{suffix}B", name_b, email=f"m{seed_digits(suffix)}@synthetic.example",
            phone=f"+48 61 555 {int(suffix):04d}", org=org, address=address,
            id_number=id_number if same_person else rotate_last(id_number),
            birth_date="1990-01-01" if same_person else "1992-01-01",
            lineage_root=f"LR-synthetic-org-{org}",
            uri=f"https://corpus.example/synthetic/{org.lower().replace(' ', '-')}/listing-b",
        )
        if transformation == "truncation":
            right["id_number"] = ""
            right["birth_date"] = ""
            right["email"] = ""
        ambiguous = transformation in ("umlaut_variant", "accent_variant")
        label = "ambiguous" if ambiguous else ("match" if same_person else "non_match")
        generated.append(
            _pair(
                f"ID-S{suffix}", label, f"synthetic_{transformation}", left, right,
                f"Template {transformation!r}: same employer and address in a synthetic "
                "listing corpus, differing only in the name surface"
                + ("; treated as ambiguous because the variant and the identity are not "
                   "separated by any other field."
                   if ambiguous else "."),
                provenance="synthetic",
                generator=f"build_corpus.py:synthetic_pairs()[SYNTHETIC_VARIANTS[{int(suffix) - 1}]]",
                ambiguity_reason=(
                    f"The name variant ({transformation}) and the two-people reading are both "
                    "consistent with every field in the record."
                    if ambiguous
                    else None
                ),
            )
        )

    for index, (name, org, city) in enumerate(
        (("Ada Kern", "Kern Instruments", "Gdansk"), ("Bo Lindqvist", "Lindqvist Marine", "Helsinki")),
        start=1,
    ):
        generated.append(
            _pair(
                f"ID-S9{index}", "non_match", "synthetic_true_negative",
                rec(f"R-S9{index}A", name, email=f"u{index}@synthetic.example",
                    org=org, address=f"Kaigi 1, {city}", id_number=f"XX-{9000000 + index}",
                    birth_date="1970-03-03", lineage_root=f"LR-synthetic-org-{org}",
                    uri="https://corpus.example/synthetic/control-a"),
                rec(f"R-S9{index}B", name.replace(" ", " "), email=f"v{index}@synthetic.example",
                    org=f"{org} Oy", address=f"Kaigi 2, {city}", id_number=f"XX-{9000009 + index}",
                    birth_date="1971-04-04", lineage_root=f"LR-synthetic-org-{org} Oy",
                    uri="https://corpus.example/synthetic/control-b"),
                "Synthetic control: same surname, different given name, different organisation "
                "and id. Nothing is shared except the family name.",
                provenance="synthetic",
                generator="build_corpus.py:synthetic_pairs()[true_negative_controls]",
            )
        )
    return generated


def seed_digits(suffix: str) -> str:
    return f"{int(suffix):03d}"


def rotate_last(id_number: str) -> str:
    """Change only the final character, so ids differ by one and the collision stays hard."""
    if not id_number:
        return ""
    return id_number[:-1] + ("7" if id_number[-1] != "7" else "8")


# --------------------------------------------------------------------------------------
# Assembly
# --------------------------------------------------------------------------------------


def all_pairs() -> list[dict[str, Any]]:
    pairs = sorted(AUTHORED_PAIRS + synthetic_pairs(), key=lambda p: p["pair_id"])
    seen: set[str] = set()
    for pair in pairs:
        if pair["pair_id"] in seen:
            raise ValueError(f"duplicate pair_id {pair['pair_id']}")
        seen.add(pair["pair_id"])
    return pairs


def render(pairs: list[dict[str, Any]]) -> str:
    return "".join(json.dumps(p, ensure_ascii=False, sort_keys=True) + "\n" for p in pairs)


def summarise(pairs: list[dict[str, Any]]) -> dict[str, Any]:
    labels: dict[str, int] = {label: 0 for label in LABELS}
    provenance: dict[str, int] = {}
    categories: dict[str, int] = {}
    records: set[str] = set()
    for pair in pairs:
        labels[pair["label"]] += 1
        provenance[pair["provenance"]] = provenance.get(pair["provenance"], 0) + 1
        categories[pair["category"]] = categories.get(pair["category"], 0) + 1
        records.add(pair["left"]["record_id"])
        records.add(pair["right"]["record_id"])
    return {
        "pairs": len(pairs),
        "records": len(records),
        "labels": labels,
        "provenance": provenance,
        "categories": dict(sorted(categories.items())),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true", help="compare against pairs.jsonl, write nothing")
    args = parser.parse_args(argv)

    pairs = all_pairs()
    rendered = render(pairs)
    if args.verify:
        if not CORPUS.exists():
            print(f"missing {CORPUS}", file=sys.stderr)
            return 2
        on_disk = CORPUS.read_text(encoding="utf-8")
        if on_disk != rendered:
            print("pairs.jsonl has drifted from the generator", file=sys.stderr)
            return 1
    else:
        CORPUS.write_text(rendered, encoding="utf-8")

    print(json.dumps(summarise(pairs), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())