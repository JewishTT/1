"""Deterministic entity search surface unit tests."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_APPS_DIR = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_APPS_DIR / "shared"))
sys.path.insert(0, str(_APPS_DIR))

from acquisition.entity_search import (  # noqa: E402
    EntitySearchSurface,
    build_entity_search_surface,
)


def test_surface_is_independent_of_mapping_insertion_order() -> None:
    first = build_entity_search_surface(
        "entity-1",
        {"name": "Acme", "domain": "acme.test", "email": "ops@acme.test"},
    )
    second = build_entity_search_surface(
        "entity-1",
        {"email": " ops@acme.test ", "domain": " acme.test ", "name": " Acme "},
    )

    assert first == second
    assert first.identifiers == (
        ("domain", "acme.test"),
        ("email", "ops@acme.test"),
        ("name", "Acme"),
    )


def test_surface_contains_web_queries_and_common_crawl_plan() -> None:
    surface = build_entity_search_surface(
        "entity-2",
        {"url": "https://acme.test/docs", "domain": "acme.test", "name": "Acme"},
    )

    assert surface.entity_id == "entity-2"
    assert {query.text for query in surface.queries} == {
        '"Acme"',
        '"https://acme.test/docs"',
        "acme.test",
    }
    assert {query.intent for query in surface.queries} >= {"entity", "domain"}
    assert surface.cc_plan is not None
    assert surface.cc_plan.kind == "url"
    assert surface.cc_plan.url_query == "https://acme.test/docs"
    assert surface.cc_plan.surt_prefix == "http://test,acme,"
    assert surface.cc_plan.limit == 50


def test_empty_identity_returns_explicit_empty_surface() -> None:
    surface = build_entity_search_surface("entity-3", {"phone": "  "})

    assert surface == EntitySearchSurface("entity-3", (), (), None)
    assert not surface
    assert surface.as_dict() == {
        "entity_id": "entity-3",
        "identifiers": {},
        "queries": [],
        "cc_plan": None,
    }


def test_surface_is_bounded_frozen_and_json_serializable() -> None:
    surface = build_entity_search_surface(
        "entity-4",
        {"name": "Acme", "email": "a@acme.test", "domain": "acme.test"},
        max_queries=1,
    )

    assert len(surface.queries) == 1
    assert json.dumps(surface.as_dict(), sort_keys=True)
    try:
        surface.entity_id = "changed"  # type: ignore[misc]
    except AttributeError:
        return
    raise AssertionError("EntitySearchSurface must be frozen")
