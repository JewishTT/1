"""Badge façade (T095): match-by-badges, alias resolution, capability gap."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from badges import BadgeFacade, BadgeGap, BadgeNotFoundError, EngineBadge


def test_default_surface_covers_http() -> None:
    facade = BadgeFacade().seed_defaults()
    candidates = facade.match_by_badges({"http", "headers"})
    assert any(c.engine == "http" for c in candidates)


def test_alias_resolution_selects_engine() -> None:
    facade = BadgeFacade().seed_defaults()
    resolved = facade.resolve_task({"task_id": "t1", "required_badges": {"common-crawl"}})
    assert isinstance(resolved, EngineBadge)
    assert resolved.engine == "bulk"


def test_capability_gap_is_explicit() -> None:
    facade = BadgeFacade()
    gap = facade.resolve({"harpoon"})
    assert isinstance(gap, BadgeGap)
    assert "harpoon" in gap.missing


def test_no_silent_misroute_on_unknown_alias() -> None:
    facade = BadgeFacade().seed_defaults()
    gap = facade.resolve({"zzz-nonexistent"})
    assert isinstance(gap, BadgeGap)


def test_register_rejects_unknown_badge_token() -> None:
    facade = BadgeFacade()
    try:
        facade.register("mystery", badges={"zzz"})
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_badge_not_found_from_aliases() -> None:
    facade = BadgeFacade().seed_defaults()
    try:
        facade.badge("cucumber")
    except BadgeNotFoundError:
        return
    raise AssertionError("expected BadgeNotFoundError")


def test_engines_for_badge() -> None:
    facade = BadgeFacade().seed_defaults()
    assert "browser" in facade.engines_for("javascript")
    assert "archival" in facade.engines_for("warc")


def test_from_adapters_best_effort() -> None:
    facade = BadgeFacade().from_adapters()
    assert len(facade) > 0
    http = facade.resolve({"etag"})
    assert isinstance(http, EngineBadge)