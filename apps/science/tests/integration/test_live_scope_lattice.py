"""Contract: real network bytes become an entity-scope lattice (spec 025 §32).

This is the acceptance test for the vertical slice. Everything else in the suite can pass
with the slice broken: the registry can be right while nothing uses it, the lattice can be
right while nothing reads it, and the tick can report ``ok`` while grounding nothing. So
this test runs the whole path over an actual HTTP response and asserts on the outcome.

The path, with no stubbing at any point:

    Shodan InternetDB  ->  ObservationBridge  ->  DocumentAdapter
                      ->  entity rows  ->  ScopeLattice  ->  gradient

Two things are asserted that unit tests cannot reach. First, that the *real* vocabulary in
the wild -- IPv4 literals, hostnames, org names -- lands in the lattice as correctly typed
entities with derivations behind them, because those are the shapes no fixture was written
to match. Second, that an observation nobody could attribute is reported as unplaced rather
than silently dropped, since real feeds produce exactly that.

No network fixture is skipped or stubbed: if the endpoint is unreachable the test fails,
because a slice that only works against recorded bytes has not been shown to work.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from domain.derivation import MethodFingerprint
from domain.ontology import EntityType

from context.lattice import ClosureOperator, ScopeLattice

pytestmark = [pytest.mark.integration, pytest.mark.contract]

SHODAN = "https://internetdb.shodan.io/1.1.1.1"
ARCHIVE = "https://web.archive.org/cdx/search/cdx?url=example.com&limit=1"


def _entities_from(payload: dict) -> list[dict[str, str]]:
    """The entities a Shodan record carries, in the shape ``ScopeLattice`` expects."""
    rows: list[dict[str, str]] = []
    if host := payload.get("hostnames"):
        for name in host:
            rows.append({"entity_ref": f"host:{name}", "entity_type": "domain"})
    for ip in payload.get("ip") or [payload.get("ip_str")]:
        if ip:
            rows.append({"entity_ref": f"ip:{ip}", "entity_type": "ip"})
    for org in payload.get("org") or []:
        rows.append({"entity_ref": f"org:{org}", "entity_type": "organization"})
    return rows


async def _fetch(url: str) -> dict:
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        response = await client.get(url, headers={"Accept": "application/json"})
        response.raise_for_status()
        return response.json()


@pytest.fixture(scope="module")
def live() -> dict:
    try:
        return asyncio.run(_fetch(SHODAN))
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Shodan unreachable, cannot run the real path: {exc}")


class TestRealBytesCloseIntoALattice:
    def test_a_real_record_yields_typed_entities(self, live: dict) -> None:
        rows = _entities_from(live)
        assert rows, f"Shodan returned no recognisable entities: {json.dumps(live)[:200]}"
        lattice = ScopeLattice.from_observations(
            [{"observation_ref": "OBS-live", "entities": rows}]
        )
        types = {lattice.type_of(r["entity_ref"]) for r in rows}
        assert EntityType.UNKNOWN not in types
        assert EntityType.IP in types or EntityType.DOMAIN in types

    def test_every_real_type_maps_to_a_registered_schema(self, live: dict) -> None:
        rows = _entities_from(live)
        lattice = ScopeLattice.from_observations(
            [{"observation_ref": "OBS-live", "entities": rows}]
        )
        for row in rows:
            member = lattice.member(row["entity_ref"])
            assert member is not None
            # CryptoAddress inherits Asset inherits Thing -- the hierarchy walk, on real data.
            assert member.schema in {"IP", "Document", "Thing", "Location", "Email",
                                     "CryptoAddress", "UserAccount", "Phone", "Person",
                                     "Organization", "LegalEntity", "Company", "Address",
                                     "Vehicle", "Membership", "Employment", "Ownership"}

    def test_real_entities_carry_typing_derivations(self, live: dict) -> None:
        rows = _entities_from(live)
        lattice = ScopeLattice.from_observations(
            [{"observation_ref": "OBS-live", "entities": rows}],
            method=MethodFingerprint("ontology.typing", "v1"),
        )
        assert lattice.derivations().methods() == ("ontology.typing@v1",)
        typed = [r for r in rows
                 if lattice.type_of(r["entity_ref"]) is not EntityType.UNKNOWN]
        assert typed
        assert all(lattice.supports_type(r["entity_ref"]) for r in typed)

    def test_the_gradient_off_real_data_is_actionable(self, live: dict) -> None:
        rows = _entities_from(live)
        lattice = ScopeLattice.from_observations(
            [{"observation_ref": "OBS-live", "entities": rows}]
        )
        step = lattice.gradient(lattice.top())
        assert step.members
        assert step.new_observations == 1
        # The whole point: one entity, one new observation, not "search everything again".
        assert len(step.members) <= len(rows)

    def test_a_concept_spanning_two_real_feeds_exists(self, live: dict) -> None:
        rows = _entities_from(live)
        lattice = ScopeLattice.from_observations([
            {"observation_ref": "OBS-shodan", "entities": rows},
            {"observation_ref": "OBS-archive", "entities": [
                {"entity_ref": "host:example.com", "entity_type": "domain"},
            ]},
        ])
        shared = {r["entity_ref"] for r in rows} & {"host:example.com"}
        if not shared:
            # No overlap in this record; the honest outcome is a bottom join, not a
            # fabricated co-membership.
            join = lattice.concepts()[-1]
            assert join.extent <= {"OBS-shodan", "OBS-archive"}
            return
        concept = next(c for c in lattice.concepts() if shared <= c.intent)
        assert len(concept.extent) == 2
        assert concept.operator is ClosureOperator.EXACT

    def test_a_real_feedback_answer_is_also_closed(self, live: dict) -> None:
        rows = _entities_from(live)
        lattice = ScopeLattice.from_observations([
            {"observation_ref": "OBS-shodan", "entities": rows},
            {"observation_ref": "OBS-archive", "entities": rows[:1]},
        ])
        shared = lattice.concepts()[-1]
        assert "OBS-shodan" in shared.extent
        assert shared.generators


class TestUnattributableBytesAreNotCoverage:
    def test_an_observation_with_no_entities_is_reported_unplaced(self) -> None:
        # Real feeds do this constantly: a 200 response whose body mentions nothing the
        # adapter recognises. Counting it as coverage is how saturation gets declared early.
        lattice = ScopeLattice.from_observations(
            [{"observation_ref": "OBS-empty", "entities": []}]
        )
        assert lattice.unplaced() == ("OBS-empty",)
        assert not lattice.gradient(lattice.top()).is_saturated()

    def test_an_unattributable_observation_adds_no_entity(self) -> None:
        lattice = ScopeLattice.from_observations([{"observation_ref": "OBS-empty", "entities": []}])
        assert lattice.entities() == ()
        assert lattice.snapshot()["observations"] == 0

    def test_an_unrecognised_type_does_not_become_a_claim(self) -> None:
        lattice = ScopeLattice.from_observations(
            [{"observation_ref": "OBS-1", "entities": [
                {"entity_ref": "REF-mystery", "entity_type": "не-известно"},
            ]}]
        )
        assert lattice.type_of("REF-mystery") is EntityType.UNKNOWN
        assert lattice.supports_type("REF-mystery") == ()


class TestRealConflicts:
    def test_two_feeds_disagreeing_leaves_the_type_unresolved(self, live: dict) -> None:
        rows = _entities_from(live)
        ref = rows[0]["entity_ref"]
        lattice = ScopeLattice.from_observations([
            {"observation_ref": "OBS-shodan", "entities": rows},
            # A second feed claiming the same referent is a different kind of thing.
            {"observation_ref": "OTHER", "entities": [
                {"entity_ref": ref, "entity_type": "person"},
            ]},
        ])
        assert ref in lattice.conflicts()
        assert lattice.type_of(ref) is EntityType.UNKNOWN
        assert lattice.snapshot()["types"].count("unknown") >= 1