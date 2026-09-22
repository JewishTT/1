"""Company / organization dictionary (spec 007, org extractor).

Real entities in RU and EN markets; ``aliases`` hold common display variants
(including declined Russian forms for narrative extraction).
"""

from __future__ import annotations

COMPANIES: list[dict] = [
    {"name": "Академия Наук", "aliases": ["Академия Наук", "Академии Наук", "Академию Наук", "Академией Наук"], "domain": "ras.ru", "country": "RU"},
    {"name": "Сбербанк", "aliases": ["Сбербанк", "Сбербанка", "Сбербанке", "Сбер", "ПАО Сбербанк"], "domain": "sberbank.ru", "country": "RU"},
    {"name": "Газпром", "aliases": ["Газпром", "Газпрома", "Газпроме", "ПАО Газпром"], "domain": "gazprom.ru", "country": "RU"},
    {"name": "Роснефть", "aliases": ["Роснефть", "Роснефти", "НК Роснефть"], "domain": "rosneft.ru", "country": "RU"},
    {"name": "Яндекс", "aliases": ["Яндекс", "Яндекса", "Яндексе", "Yandex"], "domain": "yandex.ru", "country": "RU"},
    {"name": "Mail.ru Group", "aliases": ["Mail.ru Group", "Мейл.ру", "VK Company"], "domain": "vk.company", "country": "RU"},
    {"name": "Казанский федеральный университет", "aliases": ["Казанский федеральный университет", "Казанского федерального университета", "Казанском федеральном университете", "КФУ"], "domain": "kpfu.ru", "country": "RU"},
    {"name": "Московский государственный университет", "aliases": ["Московский государственный университет", "МГУ", "Московского государственного университета"], "domain": "msu.ru", "country": "RU"},
    {"name": "РЖД", "aliases": ["РЖД", "Российские железные дороги", "ОАО РЖД"], "domain": "rzd.ru", "country": "RU"},
    {"name": "Аэрофлот", "aliases": ["Аэрофлот", "Аэрофлота", "ПАО Аэрофлот"], "domain": "aeroflot.ru", "country": "RU"},
    {"name": "Ростех", "aliases": ["Ростех", "Ростеха", "ГК Ростех"], "domain": "rostec.ru", "country": "RU"},
    {"name": "Лаборатория Касперского", "aliases": ["Лаборатория Касперского", "Лаборатории Касперского", "Kaspersky"], "domain": "kaspersky.ru", "country": "RU"},
    {"name": "Google", "aliases": ["Google", "Гугл", "Alphabet"], "domain": "google.com", "country": "US"},
    {"name": "Microsoft", "aliases": ["Microsoft", "Майкрософт", "Microsoft Corporation"], "domain": "microsoft.com", "country": "US"},
    {"name": "Apple", "aliases": ["Apple", "Apple Inc.", "Эпл"], "domain": "apple.com", "country": "US"},
    {"name": "Amazon", "aliases": ["Amazon", "Amazon.com", "Амазон"], "domain": "amazon.com", "country": "US"},
    {"name": "IBM", "aliases": ["IBM", "International Business Machines"], "domain": "ibm.com", "country": "US"},
    {"name": "Intel", "aliases": ["Intel", "Intel Corporation"], "domain": "intel.com", "country": "US"},
    {"name": "OpenAI", "aliases": ["OpenAI", "OpenAI Inc."], "domain": "openai.com", "country": "US"},
    {"name": "Meta", "aliases": ["Meta", "Facebook", "Meta Platforms"], "domain": "meta.com", "country": "US"},
    {"name": "Siemens", "aliases": ["Siemens", "Сименс", "Siemens AG"], "domain": "siemens.com", "country": "DE"},
    {"name": "Volkswagen", "aliases": ["Volkswagen", "Фольксваген", "Volkswagen AG"], "domain": "volkswagen.com", "country": "DE"},
    {"name": "Lufthansa", "aliases": ["Lufthansa", "Люфтганза", "Deutsche Lufthansa AG"], "domain": "lufthansa.com", "country": "DE"},
    {"name": "Alibaba", "aliases": ["Alibaba", "Alibaba Group", "Алибаба"], "domain": "alibaba.com", "country": "CN"},
    {"name": "Huawei", "aliases": ["Huawei", "Хуавэй", "Huawei Technologies"], "domain": "huawei.com", "country": "CN"},
    {"name": "Sberbank CIB", "aliases": ["Sberbank CIB", "Сбербанк CIB"], "domain": "sberbank-cib.ru", "country": "RU"},
    {"name": "Tinkoff", "aliases": ["Tinkoff", "Тинькофф", "Тинькофф Банк"], "domain": "tinkoff.ru", "country": "RU"},
    {"name": "Wildberries", "aliases": ["Wildberries", "Вайлдберриз", "Ozon"], "domain": "wildberries.ru", "country": "RU"},
]


def company_aliases() -> list[dict]:
    out: list[dict] = []
    for rec in COMPANIES:
        payload = {
            "kind": "company",
            "name": rec["name"],
            "domain": rec["domain"],
            "country": rec["country"],
        }
        for term in {rec["name"], *rec["aliases"]}:
            if term:
                out.append({"term": term, "payload": payload})
    return out


COMPANY_ALIASES: list[dict] = company_aliases()