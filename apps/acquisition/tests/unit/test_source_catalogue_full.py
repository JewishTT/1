"""Tests for enabling the whole source catalogue.

The point of "turn on every source" is that the catalogue is data, not code, and a
definition that is silently dropped is invisible. These assert the count and the
per-category spread so a regression in the loader is caught rather than discovered
when a query returns nothing.

Basic auth coverage exists because WiGLE (issue #45) was disabled for want of a way to
express a credential *pair*; these pin that shape, including the refusal to send half
a credential.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[2]  # .../apps/acquisition
REPO = APP.parents[1]
sys.path.insert(0, str(APP))
sys.path.insert(0, str(REPO / "apps" / "shared"))

from sources.catalogue import load_catalogue, load_source  # noqa: E402
from sources.executor import _basic_auth  # noqa: E402

ESTORIDES = APP / "sources" / "estorides"

EXPECTED_TOTAL = 145  # 146 files, minus the duplicate hunter_email
EXPECTED_CATEGORIES = 20


def all_definitions() -> list:
    return [load_source(p) for p in sorted(ESTORIDES.rglob("*.yaml"))]


def test_every_definition_loads() -> None:
    """A YAML that fails to parse would otherwise shrink the catalogue silently."""
    defs = all_definitions()
    assert len(defs) == EXPECTED_TOTAL


def test_all_sources_are_enabled() -> None:
    """The whole point: nothing is parked. A disabled definition is a source that
    cannot answer a query and gives no sign of it."""
    disabled = [d.name for d in all_definitions() if not d.enabled]
    assert disabled == []


def test_all_twenty_categories_are_present() -> None:
    categories = {d.category.split(".")[0].strip() for d in all_definitions()}
    assert len(categories) == EXPECTED_CATEGORIES


def test_catalogue_reports_no_rejections() -> None:
    """Every one of the 146 definitions must load cleanly. A rejected definition is a
    source that cannot answer, so the rejection report is the catalogue's real coverage."""
    accepted, rejected = load_catalogue(ESTORIDES)
    assert rejected == {}
    assert len(accepted) == EXPECTED_TOTAL


def test_source_ids_are_unique_across_files() -> None:
    """Regression: hunter_email existed in both 08_knowledge and 16_people, colliding
    on source_id so one silently overwrote the other."""
    accepted, rejected = load_catalogue(ESTORIDES)
    assert "duplicate_source_id" not in rejected
    ids = [d.source_id for d in accepted]
    assert len(ids) == len(set(ids))


def test_every_source_declares_a_url_or_binary() -> None:
    """19 definitions are local CLI tools (kali_amass, holehe, ...) and declare a
    binary rather than an endpoint; the loader accepts either, so must this."""
    missing = [
        d.name
        for d in all_definitions()
        if not (d.tool or {}).get("url") and not (d.tool or {}).get("binary")
    ]
    assert missing == []


def test_local_tool_sources_are_present() -> None:
    """The system_tools category is real work, not a stub category."""
    binaries = [d for d in all_definitions() if (d.tool or {}).get("binary")]
    assert len(binaries) == 19


def test_keyed_sources_name_their_credential() -> None:
    """`requires_key` with no way to name the credential fails at execution time with
    `keyed_source_without_key_env`. Every one must name either a key_env or a pair."""
    unnamed = [
        d.name
        for d in all_definitions()
        if d.requires_key and not d.key_env and not (d.tool or {}).get("basic_auth_env")
    ]
    assert unnamed == []


def test_keyed_and_open_split_is_visible() -> None:
    """Not an assertion about a magic number -- a guard so the split stays honest:
    the count of runnable-without-credentials sources cannot quietly collapse."""
    defs = all_definitions()
    keyed = [d for d in defs if d.requires_key]
    assert len(keyed) == 24
    assert len(defs) - len(keyed) == 121  # runnable with no credential at all


# -- basic auth ---------------------------------------------------------------


def source_stub(**tool):
    from sources.catalogue import SourceDefinition

    base = dict(
        source_id="s", name="s", enabled=True, category="c", description="",
        parser="raw_text", applies_to=(), entity_hints=(), requires_key=True,
        key_env="", contact="none", contact_inferred=False, kind="http",
        kind_inferred=False, os_requirement="any", tool=tool, pagination=None,
        parser_is_identity=False, source_path="",
    )
    base.update({"requires_key": False})
    return SourceDefinition(**base)


def test_no_basic_auth_declared_returns_none() -> None:
    assert _basic_auth(source_stub(url="https://x")) is None


def test_basic_auth_reads_both_env_names(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CH_USER", "alice")
    monkeypatch.setenv("CH_PASS", "s3cret")
    auth = _basic_auth(source_stub(basic_auth_env=["CH_USER", "CH_PASS"]))
    assert auth == ("alice", "s3cret")


def test_basic_auth_refuses_half_a_credential(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sending a blank half of a Basic credential is a 401 at best and a wrong
    account at worst. Report it instead."""
    monkeypatch.setenv("CH_USER", "alice")
    monkeypatch.delenv("CH_PASS", raising=False)
    with pytest.raises(Exception, match="CH_PASS"):
        _basic_auth(source_stub(basic_auth_env=["CH_USER", "CH_PASS"]))


def test_basic_auth_rejects_wrong_arity() -> None:
    with pytest.raises(Exception, match="expected 2"):
        _basic_auth(source_stub(basic_auth_env=["ONLY_ONE"]))


def test_wigle_is_enabled_and_names_its_pair() -> None:
    """The concrete regression: WiGLE was disabled because its auth was inexpressible."""
    defs = {d.name: d for d in all_definitions()}
    wigle = defs["wigle_search"]
    assert wigle.enabled
    assert wigle.tool["basic_auth_env"] == ["WIGLE_API_NAME", "WIGLE_API_TOKEN"]


def test_hunter_is_enabled() -> None:
    defs = {d.name: d for d in all_definitions()}
    assert defs["hunter_email"].enabled
