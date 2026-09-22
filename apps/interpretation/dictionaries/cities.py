"""City gazetteer: real cities with coordinates, RU+EN names and ru case forms.

Coordinates are approximate geographic references (GeoNames-style). The
``case_ru`` list covers the declined prepositional/accusative forms used in
running Russian text (pymorphy3-infflected during dataset build; the table
below records the nominative forms and the builder derives the rest).
"""

from __future__ import annotations

CITIES: list[dict] = [
    {"geo_id": "geo-524901", "name": "Moscow", "name_ru": "Москва", "country": "RU", "iso2": "RU", "lat": 55.7558, "lon": 37.6173, "case_ru": ["Москва", "Москвы", "Москве", "Москву", "Москвой"]},
    {"geo_id": "geo-551487", "name": "Kazan", "name_ru": "Казань", "country": "RU", "iso2": "RU", "lat": 55.7963, "lon": 49.1088, "case_ru": ["Казань", "Казани", "Казани", "Казань", "Казанью"]},
    {"geo_id": "geo-498677", "name": "Saint Petersburg", "name_ru": "Санкт-Петербург", "country": "RU", "iso2": "RU", "lat": 59.9311, "lon": 30.3609, "case_ru": ["Санкт-Петербург", "Санкт-Петербурга", "Санкт-Петербургу", "Санкт-Петербурге", "Санкт-Петербургом", "Питер", "Петербург", "Петербурге"]},
    {"geo_id": "geo-1496747", "name": "Novosibirsk", "name_ru": "Новосибирск", "country": "RU", "iso2": "RU", "lat": 55.0084, "lon": 82.9357, "case_ru": ["Новосибирск", "Новосибирска", "Новосибирске", "Новосибирском"]},
    {"geo_id": "geo-1486209", "name": "Yekaterinburg", "name_ru": "Екатеринбург", "country": "RU", "iso2": "RU", "lat": 56.8389, "lon": 60.6057, "case_ru": ["Екатеринбург", "Екатеринбурга", "Екатеринбурге", "Екатеринбургом"]},
    {"geo_id": "geo-520555", "name": "Nizhny Novgorod", "name_ru": "Нижний Новгород", "country": "RU", "iso2": "RU", "lat": 56.2965, "lon": 43.9361, "case_ru": ["Нижний Новгород", "Нижнего Новгорода", "Нижнем Новгороде"]},
    {"geo_id": "geo-1496153", "name": "Krasnoyarsk", "name_ru": "Красноярск", "country": "RU", "iso2": "RU", "lat": 56.0097, "lon": 92.8526, "case_ru": ["Красноярск", "Красноярска", "Красноярске"]},
    {"geo_id": "geo-1486209", "name": "Ufa", "name_ru": "Уфа", "country": "RU", "iso2": "RU", "lat": 54.7348, "lon": 55.9579, "case_ru": ["Уфа", "Уфы", "Уфе", "Уфу"]},
    {"geo_id": "geo-2013348", "name": "Vladivostok", "name_ru": "Владивосток", "country": "RU", "iso2": "RU", "lat": 43.1056, "lon": 131.8735, "case_ru": ["Владивосток", "Владивостока", "Владивостоке"]},
    {"geo_id": "geo-1489425", "name": "Tomsk", "name_ru": "Томск", "country": "RU", "iso2": "RU", "lat": 56.4977, "lon": 84.9744, "case_ru": ["Томск", "Томска", "Томске"]},
    {"geo_id": "geo-2013159", "name": "Irkutsk", "name_ru": "Иркутск", "country": "RU", "iso2": "RU", "lat": 52.2978, "lon": 104.2964, "case_ru": ["Иркутск", "Иркутска", "Иркутске"]},
    {"geo_id": "geo-2643743", "name": "London", "name_ru": "Лондон", "country": "GB", "iso2": "GB", "lat": 51.5074, "lon": -0.1278, "case_ru": ["Лондон", "Лондона", "Лондоне", "Лондоном"]},
    {"geo_id": "geo-2950159", "name": "Berlin", "name_ru": "Берлин", "country": "DE", "iso2": "DE", "lat": 52.52, "lon": 13.405, "case_ru": ["Берлин", "Берлина", "Берлине"]},
    {"geo_id": "geo-2968815", "name": "Paris", "name_ru": "Париж", "country": "FR", "iso2": "FR", "lat": 48.8566, "lon": 2.3522, "case_ru": ["Париж", "Парижа", "Париже"]},
    {"geo_id": "geo-5128581", "name": "New York City", "name_ru": "Нью-Йорк", "country": "US", "iso2": "US", "lat": 40.7128, "lon": -74.006, "case_ru": ["Нью-Йорк", "Нью-Йорка", "Нью-Йорке"]},
    {"geo_id": "geo-1816670", "name": "Beijing", "name_ru": "Пекин", "country": "CN", "iso2": "CN", "lat": 39.9042, "lon": 116.4074, "case_ru": ["Пекин", "Пекина", "Пекине"]},
    {"geo_id": "geo-3169070", "name": "Rome", "name_ru": "Рим", "country": "IT", "iso2": "IT", "lat": 41.9028, "lon": 12.4964, "case_ru": ["Рим", "Рима", "Риме"]},
    {"geo_id": "geo-2510769", "name": "Madrid", "name_ru": "Мадрид", "country": "ES", "iso2": "ES", "lat": 40.4168, "lon": -3.7038, "case_ru": ["Мадрид", "Мадрида", "Мадриде"]},
    {"geo_id": "geo-703448", "name": "Kyiv", "name_ru": "Киев", "country": "UA", "iso2": "UA", "lat": 50.4501, "lon": 30.5234, "case_ru": ["Киев", "Киева", "Киеве", "Київ"]},
    {"geo_id": "geo-625144", "name": "Minsk", "name_ru": "Минск", "country": "BY", "iso2": "BY", "lat": 53.9006, "lon": 27.559, "case_ru": ["Минск", "Минска", "Минске"]},
    {"geo_id": "geo-1526384", "name": "Almaty", "name_ru": "Алматы", "country": "KZ", "iso2": "KZ", "lat": 43.222, "lon": 76.8512, "case_ru": ["Алматы", "Алма-Ата", "Алматы"]},
    {"geo_id": "geo-1850147", "name": "Tokyo", "name_ru": "Токио", "country": "JP", "iso2": "JP", "lat": 35.6762, "lon": 139.6503, "case_ru": ["Токио", "Токио"]},
    {"geo_id": "geo-6167865", "name": "Toronto", "name_ru": "Торонто", "country": "CA", "iso2": "CA", "lat": 43.6532, "lon": -79.3832, "case_ru": ["Торонто", "Торонто"]},
    {"geo_id": "geo-2078025", "name": "Sydney", "name_ru": "Сидней", "country": "AU", "iso2": "AU", "lat": -33.8688, "lon": 151.2093, "case_ru": ["Сидней", "Сиднея", "Сиднее"]},
    {"geo_id": "geo-2648579", "name": "Glasgow", "name_ru": "Глазго", "country": "GB", "iso2": "GB", "lat": 55.8642, "lon": -4.2518, "case_ru": ["Глазго", "Глазго"]},
    {"geo_id": "geo-4930956", "name": "Boston", "name_ru": "Бостон", "country": "US", "iso2": "US", "lat": 42.3601, "lon": -71.0589, "case_ru": ["Бостон", "Бостона", "Бостоне"]},
]


def _city_aliases() -> list[dict]:
    """Expand every city (incl. case forms + English names) to gazetteer terms."""
    out: list[dict] = []
    for city in CITIES:
        payload = {
            "kind": "city",
            "geo_id": city["geo_id"],
            "name": city["name"],
            "name_ru": city["name_ru"],
            "country": city["country"],
            "iso2": city["iso2"],
            "lat": city["lat"],
            "lon": city["lon"],
        }
        terms = {city["name"], city["name_ru"], *city["case_ru"]}
        for term in terms:
            if term:
                out.append({"term": term, "payload": payload})
    return out


CITY_ALIASES: list[dict] = _city_aliases()