"""Hermetic mini OpenSanctions-derived dictionary (spec 007, US2/T015).

Content is derived from the public OpenSanctions dataset (CC-BY 4.0) and is a
*test fixture*: a handful of high-confidence entities, shipped in-repo so the
sanctions automaton, version stamp and entity-id evidence are testable fully
offline (FR-8, FR-10). The payload records the canonical OpenSanctions-style
id and schema; extraction emits mentions with ``dictionary=sanctions@<version>``
without resolving or scoring anyone (B-1).
"""

from __future__ import annotations

SANCTIONED_ENTITIES: list[dict] = [
    {
        "id": "Q7747", "schema": "Person", "name": "Vladimir Putin",
        "aliases": ["Путин Владимир Владимирович", "Владимир Путин", "Путин", "Putin Vladimir Vladimirovich"],
    },
    {
        "id": "Q968290", "schema": "Person", "name": "Dmitry Peskov",
        "aliases": ["Песков Дмитрий Сергеевич", "Дмитрий Песков", "Песков", "Peskov Dmitry"],
    },
    {
        "id": "Q112324544", "schema": "Person", "name": "Mikhail Mishustin",
        "aliases": ["Мишустин Михаил Владимирович", "Михаил Мишустин", "Мишустин", "Mishustin Mikhail"],
    },
    {
        "id": "Q5804604", "schema": "Person", "name": "Sergey Shoigu",
        "aliases": ["Шойгу Сергей Кужугетович", "Сергей Шойгу", "Шойгу", "Shoigu Sergey"],
    },
    {
        "id": "Q1635254", "schema": "Organization", "name": "Federal Security Service (FSB)",
        "aliases": ["ФСБ", "Федеральная служба безопасности", "FSB"],
    },
    {
        "id": "Q1098916", "schema": "Organization", "name": "Roscosmos",
        "aliases": ["Роскосмос", "Государственная корпорация по космической деятельности Роскосмос"],
    },
]


def sanctioned_entries() -> list[dict]:
    out: list[dict] = []
    for rec in SANCTIONED_ENTITIES:
        payload = {
            "id": rec["id"],
            "schema": rec["schema"],
            "name": rec["name"],
            "source": "opensanctions-mini-fixture",
        }
        for term in {rec["name"], *rec["aliases"]}:
            if term:
                out.append({"term": term, "payload": payload})
    return out