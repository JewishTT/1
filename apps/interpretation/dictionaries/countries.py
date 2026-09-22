"""Country dictionary: real RU/EN names + ISO codes (spec 007, US2 gazetteer).

Each record: ``iso2`` (ISO alpha-2), ``iso3`` (alpha-3), ``name_en``,
``name_ru``, ``alternates`` (extra display names used in text). Terms are
matched case-insensitively by the place gazetteer; the two-letter ISO codes
are excluded from bare-text matching (too many false positives) but kept for
structured-data resolution.
"""

from __future__ import annotations

COUNTRIES: list[dict] = [
    {"iso2": "RU", "iso3": "RUS", "name_en": "Russia", "name_ru": "Россия", "alternates": ["РФ", "Российская Федерация", "Russian Federation"]},
    {"iso2": "US", "iso3": "USA", "name_en": "United States", "name_ru": "США", "alternates": ["Соединённые Штаты", "Соединённые Штаты Америки", "United States of America"]},
    {"iso2": "CN", "iso3": "CHN", "name_en": "China", "name_ru": "Китай", "alternates": ["КНР", "Китайская Народная Республика", "People's Republic of China"]},
    {"iso2": "DE", "iso3": "DEU", "name_en": "Germany", "name_ru": "Германия", "alternates": ["ФРГ", "Федеративная Республика Германия"]},
    {"iso2": "FR", "iso3": "FRA", "name_en": "France", "name_ru": "Франция", "alternates": ["Французская Республика"]},
    {"iso2": "GB", "iso3": "GBR", "name_en": "United Kingdom", "name_ru": "Великобритания", "alternates": ["UK", "Соединённое Королевство"]},
    {"iso2": "IT", "iso3": "ITA", "name_en": "Italy", "name_ru": "Италия", "alternates": ["Итальянская Республика"]},
    {"iso2": "ES", "iso3": "ESP", "name_en": "Spain", "name_ru": "Испания", "alternates": ["Испанское королевство"]},
    {"iso2": "UA", "iso3": "UKR", "name_en": "Ukraine", "name_ru": "Украина", "alternates": ["Украина"]},
    {"iso2": "BY", "iso3": "BLR", "name_en": "Belarus", "name_ru": "Беларусь", "alternates": ["Белоруссия", "Республика Беларусь"]},
    {"iso2": "KZ", "iso3": "KAZ", "name_en": "Kazakhstan", "name_ru": "Казахстан", "alternates": ["Республика Казахстан"]},
    {"iso2": "JP", "iso3": "JPN", "name_en": "Japan", "name_ru": "Япония", "alternates": ["Япония"]},
    {"iso2": "IN", "iso3": "IND", "name_en": "India", "name_ru": "Индия", "alternates": ["Республика Индия"]},
    {"iso2": "BR", "iso3": "BRA", "name_en": "Brazil", "name_ru": "Бразилия", "alternates": ["Федеративная Республика Бразилия"]},
    {"iso2": "TR", "iso3": "TUR", "name_en": "Türkiye", "name_ru": "Турция", "alternates": ["Turkey", "Турецкая Республика"]},
    {"iso2": "IL", "iso3": "ISR", "name_en": "Israel", "name_ru": "Израиль", "alternates": ["Государство Израиль"]},
    {"iso2": "SE", "iso3": "SWE", "name_en": "Sweden", "name_ru": "Швеция", "alternates": ["Королевство Швеция"]},
    {"iso2": "NO", "iso3": "NOR", "name_en": "Norway", "name_ru": "Норвегия", "alternates": ["Королевство Норвегия"]},
    {"iso2": "FI", "iso3": "FIN", "name_en": "Finland", "name_ru": "Финляндия", "alternates": ["Финляндская Республика"]},
    {"iso2": "PL", "iso3": "POL", "name_en": "Poland", "name_ru": "Польша", "alternates": ["Республика Польша"]},
    {"iso2": "EE", "iso3": "EST", "name_en": "Estonia", "name_ru": "Эстония", "alternates": ["Эстонская Республика"]},
    {"iso2": "LV", "iso3": "LVA", "name_en": "Latvia", "name_ru": "Латвия", "alternates": ["Латвийская Республика"]},
    {"iso2": "LT", "iso3": "LTU", "name_en": "Lithuania", "name_ru": "Литва", "alternates": ["Литовская Республика"]},
    {"iso2": "GE", "iso3": "GEO", "name_en": "Georgia", "name_ru": "Грузия", "alternates": ["Georgia (country)"]},
    {"iso2": "AM", "iso3": "ARM", "name_en": "Armenia", "name_ru": "Армения", "alternates": ["Республика Армения"]},
    {"iso2": "AZ", "iso3": "AZE", "name_en": "Azerbaijan", "name_ru": "Азербайджан", "alternates": ["Азербайджанская Республика"]},
    {"iso2": "UZ", "iso3": "UZB", "name_en": "Uzbekistan", "name_ru": "Узбекистан", "alternates": ["Республика Узбекистан"]},
    {"iso2": "MD", "iso3": "MDA", "name_en": "Moldova", "name_ru": "Молдова", "alternates": ["Молдавия", "Республика Молдова"]},
    {"iso2": "GR", "iso3": "GRC", "name_en": "Greece", "name_ru": "Греция", "alternates": ["Греческая Республика"]},
    {"iso2": "NL", "iso3": "NLD", "name_en": "Netherlands", "name_ru": "Нидерланды", "alternates": ["Голландия"]},
    {"iso2": "CH", "iso3": "CHE", "name_en": "Switzerland", "name_ru": "Швейцария", "alternates": ["Швейцарская Конфедерация"]},
    {"iso2": "CA", "iso3": "CAN", "name_en": "Canada", "name_ru": "Канада", "alternates": ["Канада"]},
    {"iso2": "AU", "iso3": "AUS", "name_en": "Australia", "name_ru": "Австралия", "alternates": ["Австралийский Союз"]},
    {"iso2": "MX", "iso3": "MEX", "name_en": "Mexico", "name_ru": "Мексика", "alternates": ["Мексиканские Соединённые Штаты"]},
    {"iso2": "ZA", "iso3": "ZAF", "name_en": "South Africa", "name_ru": "ЮАР", "alternates": ["Южно-Африканская Республика"]},
]


def country_aliases() -> list[dict]:
    """Expand records to alias -> country payload (deterministic order).

    Name resolution is deterministic across runs: records are iterated in the
    source order above and each record contributes its en/ru name and
    alternates (ISO codes included — gate on term length happens at match time).
    """
    out: list[dict] = []
    for rec in COUNTRIES:
        payload = {
            "kind": "country",
            "iso2": rec["iso2"],
            "iso3": rec["iso3"],
            "name_en": rec["name_en"],
            "name_ru": rec["name_ru"],
            "geo_id": f"country-{rec['iso2'].lower()}",
        }
        for term in {rec["name_en"], rec["name_ru"], rec["iso2"], rec["iso3"], *rec["alternates"]}:
            if term:
                out.append({"term": term, "payload": payload})
    return out


COUNTRY_ALIASES: list[dict] = country_aliases()