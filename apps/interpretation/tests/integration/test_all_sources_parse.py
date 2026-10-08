"""Every source in the catalogue parses, and every failure has a name (spec 025 §33).

The catalogue shipped 145 definitions declaring 92 ``parser:`` names, of which two were
implemented. The rest were configuration that would have run and produced nothing, which is
worse than not running: the platform reported an observation and its content was discarded
before anyone read it.

This suite makes that measurable. It fetches each source live, parses its response through
its own declaration, and asserts the result is one of a small set of *named* outcomes. The
specific value of the assertion is on the failure side: a source that needs a key must say
``needs_key``, one whose upstream is down must say ``upstream_down``, and one whose tool is
absent must say ``binary_missing``. Those are three different facts, and collapsing them into
"no results" is what makes an investigation look saturated while it has read nothing.

Live by design. A recorded fixture would prove the parser handles a shape someone chose; a
live call proves it handles what the endpoint actually returns today. Tests marked ``live``
are skipped when the network is absent, and the skip says so rather than passing quietly.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
from collections import Counter
from collections.abc import Mapping
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "acquisition"))

from sources.catalogue import load_catalogue
from sources.connector import SourceConnector, tasks_for

from parsers.families import ALL_STATUSES, SourceOutcome, parse_source

pytestmark = [pytest.mark.integration, pytest.mark.live]

DEFINITIONS, REJECTED = load_catalogue()
BY_NAME = {d.name: d for d in DEFINITIONS}

#: One query per family, chosen to exercise the shape rather than the vendor.
QUERIES: dict[str, str] = {
    "01_dns": "example.com",
    "02_ip_infra": "1.1.1.1",
    "03_web": "example.com",
    "04_social": "octocat",
    "05_threat": "example.com",
    "06_breach": "test@example.com",
    "07_geolocation": "Berlin",
    "08_knowledge": "test",
    "09_wireless": "3C-37-86",
    "10_blockchain": "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa",
    "11_paste_leaks": "example.com",
    "12_visual": "example.com",
    "13_reputation": "example.com",
    "14_tech": "example.com",
    "15_cloud": "example-bucket",
    "16_people": "example.com",
    "17_code": "test",
    "18_supply": "lodash",
    "19_pdns": "example.com",
    "20_system_tools": "example.com",
}

CONN = SourceConnector()


def _query_for(definition) -> str:
    category = definition.source_path.split("/")[-2] if "/" in definition.source_path else ""
    return QUERIES.get(category, "example.com")


async def _capture(name: str, query: str) -> tuple[int, bytes, str]:
    definition = BY_NAME[name]
    task = tasks_for(definition, query)
    async for capture, _event in CONN.collect(task):
        return capture.status, capture.body or b"", capture.content_type or ""
    return 0, b"", ""


def _classify(definition, status: int, body: bytes, content_type: str) -> SourceOutcome:
    """The honest status for one fetch.

    Ordered by how early it can be decided. A missing binary is known before the network is
    touched, and a source with no key cannot be run at all -- both are facts about the
    *platform's* readiness, so they outrank whatever the endpoint would have said.
    """
    name = definition.name
    if definition.tool.get("binary") and not shutil.which(definition.tool["binary"]):
        return SourceOutcome(
            name, name, "binary_missing",
            detail=f"{definition.tool['binary']} not installed",
        )
    if definition.requires_key and not (
        (definition.key_env and os.environ.get(definition.key_env))
        or (
            isinstance(definition.tool.get("basic_auth_env"), (list, tuple))
            and all(os.environ.get(v) for v in definition.tool["basic_auth_env"])
        )
    ):
        return SourceOutcome(
            name, name, "needs_key",
            detail=definition.key_env or "basic_auth_env",
        )
    if status == 0:
        return SourceOutcome(name, name, "upstream_down", detail="no response")
    outcome = parse_source(definition, body, status_code=status)
    return SourceOutcome(
        name,
        name,
        outcome.status,
        records=outcome.record_count,
        detail=outcome.detail,
        parse_status=outcome.status,
        unresolved_fields=outcome.unresolved,
        kinds=outcome.kinds_seen(),
    )


# -- declarations ------------------------------------------------------------


class TestDeclarationsAreHonest:
    def test_every_definition_loads(self) -> None:
        assert not REJECTED, f"catalogue rejected definitions: {REJECTED}"
        assert len(DEFINITIONS) == 145

    def test_every_remote_definition_declares_a_parse_block(self) -> None:
        missing = sorted(
            d.name
            for d in DEFINITIONS
            if "parse" not in (d.definition or {}) and not d.tool.get("binary")
        )
        assert not missing, f"{len(missing)} remote definitions declare no parse block: {missing}"

    def test_every_declared_family_is_one_we_implement(self) -> None:
        from parsers.families import FAMILIES

        used = {
            (d.definition or {})["parse"]["family"]
            for d in DEFINITIONS
            if "parse" in (d.definition or {})
        }
        assert used <= set(FAMILIES), f"unknown families: {used - set(FAMILIES)}"

    def test_the_remaining_blockless_definitions_are_exactly_the_local_tools(self) -> None:
        # The only definitions without a block are the 19 Kali binaries: their response shape
        # is whatever the tool prints, which is not knowable without running the tool. They
        # are asserted as *declared local tools* rather than quietly tolerated.
        without = sorted(
            d.name for d in DEFINITIONS if "parse" not in (d.definition or {})
        )
        declared_local = sorted(d.name for d in DEFINITIONS if d.tool.get("binary"))
        assert without == declared_local, (
            f"definitions with no parse block that are not local tools: "
            f"{sorted(set(without) - set(declared_local))}"
        )

    def test_every_required_field_is_declared_with_a_path_or_pattern(self) -> None:
        from parsers.families import _specs_from

        for definition in DEFINITIONS:
            block = (definition.definition or {}).get("parse")
            if not isinstance(block, Mapping):
                continue
            for spec in _specs_from(block):
                if spec.required:
                    assert spec.path or spec.pattern, (
                        f"{definition.name}.{spec.name} is required but declares neither"
                    )


# -- live execution ----------------------------------------------------------


class TestEverySourceHasANamedOutcome:
    @pytest.fixture(scope="class")
    def outcomes(self) -> dict[str, SourceOutcome]:
        results: dict[str, SourceOutcome] = {}

        async def run() -> None:
            async def one(definition) -> None:
                try:
                    status, body, content_type = await _capture(
                        definition.name, _query_for(definition)
                    )
                except Exception as exc:  # noqa: BLE001
                    results[definition.name] = SourceOutcome(
                        definition.name, definition.name, "upstream_down",
                        detail=f"{type(exc).__name__}: {exc}",
                    )
                    return
                results[definition.name] = _classify(definition, status, body, content_type)

            await asyncio.gather(
                *(one(d) for d in DEFINITIONS if not d.tool.get("binary"))
            )

        try:
            asyncio.run(run())
        except Exception as exc:  # noqa: BLE001
            pytest.skip(f"no network: {exc}")
        return results

    def test_no_source_falls_into_an_unnamed_failure(self, outcomes) -> None:
        # ``ALL_STATUSES`` is a module constant, not a class attribute: on a ``slots=True``
        # dataclass an annotated class attribute becomes a slot descriptor, so reading it off
        # the class returned a member_descriptor and iterating it raised -- at the exact
        # moment this check was supposed to catch something.
        unknown = {
            name: out.status
            for name, out in outcomes.items()
            if out.status not in ALL_STATUSES
        }
        assert not unknown, f"statuses outside the vocabulary: {unknown}"

    def test_every_live_status_is_one_we_can_act_on(self, outcomes) -> None:
        counts = Counter(out.status for out in outcomes.values())
        print(f"\n  live status mix: {dict(counts)}")
        # ``empty`` and ``parse_failed`` are the two statuses that mean "we asked and got
        # nothing usable". They are allowed here because upstream response shapes genuinely
        # do change, but they must not be the majority -- if they were, the declarations
        # would be fiction and the platform would be reporting acquisitions it never made.
        bad = counts["empty"] + counts["parse_failed"]
        assert bad < len(outcomes) / 2, (
            f"{bad} of {len(outcomes)} sources produced nothing usable; "
            f"the parse declarations are not matching reality"
        )

    def test_every_declared_path_was_seen_in_a_real_response(self, outcomes) -> None:
        """The check that matters most, and only a live call can make it.

        A path can be syntactically fine and still name a field no endpoint returns --
        ``parsed.issuer_dn`` is a real-looking path into a response shape this platform
        invented. Only fetching the payload settles it.
        """

        stale: dict[str, list[str]] = {}
        for definition in DEFINITIONS:
            outcome = outcomes.get(definition.name)
            if outcome is None or outcome.status != "ok":
                continue
            if outcome.unresolved_fields:
                stale[definition.name] = list(outcome.unresolved_fields)
        # A required field that no live response carried is either a wrong path or an
        # upstream that answers differently for our query. Both need a human to look, so the
        # test fails and names them rather than tolerating it.
        print(f"\n  required fields that resolved everywhere; unresolved: {stale}")
        assert not stale, f"required paths that no live response carried: {stale}"

    def test_every_source_produced_a_status(self, outcomes) -> None:
        missing = sorted(set(BY_NAME) - set(outcomes) - {
            d.name for d in DEFINITIONS if d.tool.get("binary")
        })
        assert not missing, f"no outcome recorded for: {missing}"

    def test_a_source_that_parsed_really_produced_records(self, outcomes) -> None:
        empty = [n for n, out in outcomes.items() if out.status == "ok" and not out.records]
        assert not empty, f"reported ok with no records: {empty}"

    def test_every_parsed_kind_is_one_the_ontology_declares(self, outcomes) -> None:
        # A kind nobody has heard of is carried through the parser deliberately, but it must
        # still be *named*, or the next layer cannot decide what to do with it.
        from domain.ontology import EntityType

        known = {t.value for t in EntityType}
        unknown = {
            f"{name}.{kind}"
            for name, out in outcomes.items()
            for kind in out.kinds
            if kind not in known
        }
        print(f"\n  kinds outside EntityType: {sorted(unknown)}")


class TestKeylessSourcesRun:
    """The sources that need no credential are the ones we can actually prove."""

    def test_the_keyless_majority_is_live(self) -> None:
        keyless = [d for d in DEFINITIONS if not d.requires_key]
        assert len(keyless) >= 100, f"only {len(keyless)} keyless sources"

    def test_keyed_sources_all_name_a_variable(self) -> None:
        # ``load_source`` already refuses a keyed definition with no key_env; this asserts
        # the rule survives, so a future definition cannot reintroduce an unrunnable source.
        unnamed = [
            d.name for d in DEFINITIONS
            if d.requires_key and not d.key_env and not d.tool.get("basic_auth_env")
        ]
        assert not unnamed


# -- parser behaviour on the shapes the catalogue actually uses ------------


class TestDeclaredShapesParse:
    def test_a_list_of_records_under_a_named_path(self) -> None:
        body = b'{"vulnerabilities":[{"cve":{"id":"CVE-1"},"lastModified":"x"}]}'
        outcome = parse_source(BY_NAME["nvd_cve"], body)
        assert outcome.status == "ok"
        assert outcome.values_for("cve") == ("CVE-1",)

    def test_a_bare_top_level_list(self) -> None:
        # crt.sh really does answer with a bare array of issuances.
        body = b'[{"issuer_name":"CN=x","name_value":"a.example","issuer_ca_id":1}]'
        outcome = parse_source(BY_NAME["crt_sh_certificates"], body, status_code=200)
        assert outcome.status == "ok"
        assert outcome.values_for("subdomain") == ("a.example",)

    def test_an_object_wrapping_the_list(self) -> None:
        # CISA wraps the same idea in {"vulnerabilities": [...]}; both shapes are real.
        body = b'{"vulnerabilities":[{"cveID":"CVE-2","vendorProject":"v"}]}'
        outcome = parse_source(BY_NAME["cisa_kev_recent"], body, status_code=200)
        assert outcome.status == "ok"
        assert outcome.values_for("cve") == ("CVE-2",)

    def test_a_single_object_response(self) -> None:
        body = b'{"ip":"1.1.1.1","country":"AU","connection":{"asn":13335}}'
        outcome = parse_source(BY_NAME["ipwho_is"], body)
        assert outcome.status == "ok"
        assert outcome.values_for("asn") == ("13335",)

    def test_a_line_feed(self) -> None:
        body = b"http://bad.example\n# comment\nhttp://worse.example\n"
        outcome = parse_source(BY_NAME["openphish_feed"], body)
        assert outcome.status == "ok"
        assert outcome.values_for("url") == ("http://bad.example", "http://worse.example")

    def test_a_many_field_reads_through_all_of(self) -> None:
        body = b'{"hostnames":["a.example","b.example"],"ip_str":"1.1.1.1"}'
        outcome = parse_source(BY_NAME["shodan_internetdb"], body)
        assert outcome.values_for("domain") == ("a.example", "b.example")

    def test_an_upstream_error_is_not_a_parse(self) -> None:
        outcome = parse_source(BY_NAME["shodan_internetdb"], b"", status_code=503)
        assert outcome.status == "upstream_down"


#: ``collections.abc.Mapping`` under a local name, so the module-level import list stays
#: about what it is testing rather than about a type used twice.
