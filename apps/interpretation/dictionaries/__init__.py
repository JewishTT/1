"""Compact country/city/company/name/sanctions dictionaries (spec 007).

Pure-python data tables (real, versioned records) that feed the deterministic
extraction stack: ``countries.py`` / ``cities.py`` / ``companies.py`` carry
RU+EN display names, coordinates and case forms; ``first_names.py`` carries
ru/en given-name lists, ru patronymic and surname endings; ``sanctions.py`` a
hermetic mini OpenSanctions-derived entity table. The mini content-addressed
automatons that extractors actually query are built into ``data/`` by
``build_mini.py`` (offline, via the shared ``datasets.build`` canonicalizer).
"""

from __future__ import annotations

from .build_mini import VERSIONS as VERSIONS
from .cities import CITIES as CITIES
from .cities import CITY_ALIASES as CITY_ALIASES
from .companies import COMPANIES as COMPANIES
from .companies import COMPANY_ALIASES as COMPANY_ALIASES
from .countries import COUNTRIES as COUNTRIES
from .countries import COUNTRY_ALIASES as COUNTRY_ALIASES
from .data import automaton as automaton
from .data import dataset as dataset
from .data import load as load
from .first_names import EN_FIRST_NAMES as EN_FIRST_NAMES
from .first_names import RU_FIRST_NAMES as RU_FIRST_NAMES
from .sanctions import SANCTIONED_ENTITIES as SANCTIONED_ENTITIES

__all__ = [
    "CITIES",
    "CITY_ALIASES",
    "COMPANIES",
    "COMPANY_ALIASES",
    "COUNTRIES",
    "COUNTRY_ALIASES",
    "EN_FIRST_NAMES",
    "RU_FIRST_NAMES",
    "SANCTIONED_ENTITIES",
    "VERSIONS",
    "automaton",
    "dataset",
    "load",
]