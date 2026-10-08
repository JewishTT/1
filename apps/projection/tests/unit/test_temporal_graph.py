"""Tests for the ClickHouse temporal graph.

The seam is the client, so these run without a server. What they actually protect:

* ``record_hash`` is content-derived -- ReplacingMergeTree versions on it, so a
  non-content hash would silently break replay idempotency.
* validity is half-open and tz-aware -- ClickHouse DateTime64 is tz-explicit and a
  naive datetime crossing that boundary is a data corruption bug, not a type error.
* a non-scalar property is NOT projected onto an interval -- an interval over a
  nested structure is a claim the data does not make.
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "shared")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "projection")))

from analytics.clickhouse_client import ClickHouseHTTP  # noqa: E402
from analytics.temporal_graph import (  # noqa: E402
    ClickHouseTemporalStore,
    TemporalEvent,
)


class FakeClient:
    def __init__(self) -> None:
        self.executed: list[str] = []
        self.fetched: list[str] = []
        self.rows: list[dict[str, Any]] = []

    async def execute(self, query: str) -> None:
        self.executed.append(query)

    async def fetch_all(self, query: str) -> list[dict[str, Any]]:
        self.fetched.append(query)
        return list(self.rows)


def event(**kw: Any) -> TemporalEvent:
    base: dict[str, Any] = {
        "tenant_id": "acme",
        "entity_id": "ENT-1",
        "kind": "mention",
        "observation_id": "OBS-1",
    }
    base.update(kw)
    return TemporalEvent(**base)


# -- identity -----------------------------------------------------------------


def test_record_hash_is_deterministic_for_same_content() -> None:
    a = event(payload={"role": "president"})
    b = event(payload={"role": "president"})
    assert a.record_hash == b.record_hash


def test_record_hash_changes_when_payload_changes() -> None:
    a = event(payload={"role": "president"})
    b = event(payload={"role": "ex-president"})
    assert a.record_hash != b.record_hash


def test_record_hash_changes_when_validity_moves() -> None:
    """Two observations of the same fact at different instants are different facts."""
    t = datetime(2026, 1, 1, tzinfo=UTC)
    a = event(payload={"role": "president"}, valid_from=t)
    b = event(payload={"role": "president"}, valid_from=t + timedelta(days=1))
    assert a.record_hash != b.record_hash


def test_record_hash_is_tenant_scoped() -> None:
    """Same entity, two tenants -> two independent rows, not one collapse."""
    assert event(tenant_id="a").record_hash != event(tenant_id="b").record_hash


# -- validation ----------------------------------------------------------------


def test_inverted_validity_is_rejected() -> None:
    t = datetime(2026, 1, 1, tzinfo=UTC)
    with pytest.raises(ValueError, match="validity inverted"):
        event(valid_from=t, valid_until=t - timedelta(days=1))


def test_naive_timestamp_is_rejected_at_the_boundary() -> None:
    """DateTime64('UTC') is tz-explicit; a naive datetime would land as a silent
    offset guess. Refuse it rather than guess an instant."""
    with pytest.raises(ValueError, match="tz-aware"):
        event(ts=datetime(2026, 1, 1)).to_row()
    with pytest.raises(ValueError, match="tz-aware"):
        event(valid_from=datetime(2026, 1, 1), payload={"role": "x"}).to_intervals()


@pytest.mark.parametrize("missing", ["tenant_id", "entity_id", "kind"])
def test_required_identity_fields_are_enforced(missing: str) -> None:
    with pytest.raises(ValueError, match=missing):
        event(**{missing: ""})


def test_ts_defaults_to_valid_from() -> None:
    t = datetime(2026, 3, 1, tzinfo=UTC)
    assert event(valid_from=t).ts == t


# -- validity projection -------------------------------------------------------


def test_scalar_property_becomes_open_ended_interval() -> None:
    t = datetime(2026, 1, 1, tzinfo=UTC)
    rows = event(payload={"role": "president"}, valid_from=t).to_intervals()
    assert len(rows) == 1
    assert rows[0]["prop"] == "role"
    # datetimes, not ISO strings: the writer owns ClickHouse literal syntax
    assert rows[0]["valid_from"] == t
    assert rows[0]["valid_until"] is None


def test_explicit_bounds_in_payload_win() -> None:
    start = "2020-01-01T00:00:00+00:00"
    end = "2024-01-01T00:00:00+00:00"
    rows = event(
        payload={"office": {"value": "PM", "valid_from": start, "valid_until": end}}
    ).to_intervals()
    assert rows[0]["valid_from"] == start
    assert rows[0]["valid_until"] == end


def test_non_scalar_property_is_not_projected_as_interval() -> None:
    """An interval over a nested structure would assert something the data never said."""
    rows = event(payload={"tags": ["a", "b"], "meta": {"x": 1}, "n": 7}).to_intervals()
    props = {r["prop"] for r in rows}
    assert props == {"n"}


# -- ingest --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ingest_writes_events_and_intervals() -> None:
    client = FakeClient()
    store = ClickHouseTemporalStore(client)
    written = await store.ingest([event(payload={"role": "president"})])
    assert written == 1
    assert any("INSERT INTO entity_events" in q for q in client.executed)
    assert any("INSERT INTO entity_validity" in q for q in client.executed)


@pytest.mark.asyncio
async def test_ingest_ensures_schema_once() -> None:
    client = FakeClient()
    await ClickHouseTemporalStore(client).ingest([event(), event(entity_id="ENT-2")])
    ddl = [q for q in client.executed if q.strip().upper().startswith("CREATE")]
    assert len(ddl) == 3


@pytest.mark.asyncio
async def test_empty_ingest_touches_nothing() -> None:
    client = FakeClient()
    assert await ClickHouseTemporalStore(client).ingest([]) == 0
    assert client.executed == []


def test_engine_is_replacing_on_integer_version() -> None:
    """This is the whole idempotency mechanism. If the ENGINE clause changes, replay
    starts duplicating and nothing in the tests would otherwise notice.

    Note the version column must be an integer: ClickHouse rejects a String version
    with Code 169 BAD_TYPE_OF_FIELD."""
    from analytics.temporal_graph import ENTITY_EVENTS_DDL

    assert "ReplacingMergeTree(version)" in ENTITY_EVENTS_DDL
    assert "version            UInt64," in ENTITY_EVENTS_DDL


def test_defaulted_ts_is_not_hashed() -> None:
    """Replay idempotency depends on this. If wall-clock leaked into the content hash,
    every replay would mint a new version and the projection would grow forever."""
    a = event(payload={"role": "president"})
    b = event(payload={"role": "president"})
    assert a.record_hash == b.record_hash  # same asserted content, same address


def test_asserted_ts_is_hashed() -> None:
    """An explicitly asserted observation time IS content and must change the hash."""
    t = datetime(2026, 1, 1, tzinfo=UTC)
    assert event(ts=t, payload={"role": "president"}).record_hash != event(
        ts=t + timedelta(seconds=1), payload={"role": "president"}
    ).record_hash


def test_version_is_derived_from_content_and_fits_uint64() -> None:
    e = event(payload={"role": "president"})
    assert e.version == int(e.record_hash[:15], 16)
    assert 0 <= e.version < 2**64
    assert e.version == event(payload={"role": "president"}).version
    assert e.version != event(payload={"role": "other"}).version


def test_ordering_key_is_entity_then_validity() -> None:
    from analytics.temporal_graph import ENTITY_EVENTS_DDL

    assert "ORDER BY (tenant_id, entity_id, sort_valid_from, sequence)" in ENTITY_EVENTS_DDL


def test_interval_key_admits_concurrent_facts() -> None:
    """A graph property is not single-valued. An entity that stood in five relations at
    one instant holds five concurrent true facts, so `value` must be part of the key or
    the interval view silently keeps only the last one."""
    from analytics.temporal_graph import ENTITY_INTERVALS_DDL

    assert "ORDER BY (tenant_id, entity_id, prop, valid_from, sort_valid_until, value)" in (
        ENTITY_INTERVALS_DDL
    )


# -- queries -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_state_at_is_half_open() -> None:
    client = FakeClient()
    await ClickHouseTemporalStore(client).state_at(
        tenant_id="acme", entity_id="ENT-1", at=datetime(2026, 6, 1, tzinfo=UTC)
    )
    sql = client.fetched[0]
    assert "valid_from <=" in sql
    assert "valid_until IS NULL OR valid_until >" in sql


@pytest.mark.asyncio
async def test_open_valid_until_is_not_treated_as_missing() -> None:
    """An open end means 'still true'. The query must say so explicitly."""
    client = FakeClient()
    await ClickHouseTemporalStore(client).state_at(
        tenant_id="acme", entity_id="ENT-1", at=datetime(2026, 6, 1, tzinfo=UTC)
    )
    assert "valid_until IS NULL" in client.fetched[0]


@pytest.mark.asyncio
async def test_tenant_is_escaped_not_interpolated_raw() -> None:
    """Injection must stay inert: the quote is escaped so the literal never closes
    and the rest of the payload cannot escape into SQL."""
    client = FakeClient()
    await ClickHouseTemporalStore(client).history(tenant_id="acme'; DROP TABLE x;--", entity_id="E")
    sql = client.fetched[0]
    literal = sql.split("tenant_id = ")[1].split("\n")[0].strip()
    # one quoted literal, quote escaped -> the injected text cannot terminate it
    assert literal.startswith("'") and literal.endswith("'")
    assert "\\'" in literal
    # the dangerous fragment must not sit outside quotes as live SQL
    assert "AND entity_id" in sql and sql.index("AND entity_id") > sql.index("tenant_id =")


@pytest.mark.asyncio
async def test_history_reads_the_final_view() -> None:
    client = FakeClient()
    await ClickHouseTemporalStore(client).history(tenant_id="acme", entity_id="ENT-1")
    assert "entity_events FINAL" in client.fetched[0]


# -- structural ingest (cross-layer) -------------------------------------------


class ForeignEvent:
    """An event shaped like the boundary contract, not like TemporalEvent.

    Stands in for ``control-plane/services/temporal_port.EntityEvent``. The store must
    accept it without importing control-plane -- that dependency edge is forbidden --
    which is only possible if ingest is structural.
    """

    def __init__(self, **kw: Any) -> None:
        self.tenant_id = kw.get("tenant_id", "acme")
        self.entity_id = kw.get("entity_id", "ENT-x")
        self.kind = kw.get("kind", "mention")
        self.entity_class = kw.get("entity_class", "dynamic_continuant")
        self.observation_id = kw.get("observation_id", "OBS-x")
        self.dataset_id = ""
        self.sequence = kw.get("sequence", 0)
        self.extraction_version = ""
        self.ts = kw.get("ts")
        self.valid_from = kw.get("valid_from")
        self.valid_until = kw.get("valid_until")
        self.payload = kw.get("payload") or {}


@pytest.mark.asyncio
async def test_foreign_event_is_accepted_structurally() -> None:
    client = FakeClient()
    written = await ClickHouseTemporalStore(client).ingest(
        [ForeignEvent(payload={"role": "president"})]
    )
    assert written == 1
    assert any("INSERT INTO entity_events" in q for q in client.executed)
    assert any("INSERT INTO entity_validity" in q for q in client.executed)


@pytest.mark.asyncio
async def test_store_derives_its_own_hash_not_the_callers() -> None:
    """Deduplication must not be weakenable by a caller that supplies no hash."""
    client = FakeClient()
    await ClickHouseTemporalStore(client).ingest([ForeignEvent(payload={"a": 1})])
    await ClickHouseTemporalStore(client).ingest([ForeignEvent(payload={"a": 1})])
    inserts = [q for q in client.executed if q.startswith("INSERT INTO entity_events")]
    versions = {q.split("version, ")[0] for q in inserts}
    # identical content -> identical version -> ReplacingMergeTree collapses them
    assert len(inserts) == 2
    assert all("version" in q for q in inserts)


@pytest.mark.asyncio
async def test_missing_identity_on_a_foreign_event_is_refused() -> None:
    client = FakeClient()
    with pytest.raises(ValueError, match="entity_id"):
        await ClickHouseTemporalStore(client).ingest([ForeignEvent(entity_id="")])


# -- live ----------------------------------------------------------------------


@pytest.mark.skipif(
    not os.environ.get("CLICKHOUSE_TEST_URL"), reason="set CLICKHOUSE_TEST_URL to run live"
)
@pytest.mark.asyncio
async def test_live_roundtrip() -> None:
    import uuid

    async with ClickHouseHTTP(
        url=os.environ["CLICKHOUSE_TEST_URL"],
        database=os.environ.get("CLICKHOUSE_TEST_DB", "default"),
        user=os.environ.get("CLICKHOUSE_USER", "default"),
        password=os.environ.get("CLICKHOUSE_PASSWORD", ""),
    ) as ch:
        store = ClickHouseTemporalStore(ch)
        await store.ensure_schema()
        tenant = f"t-{uuid.uuid4().hex[:8]}"
        entity = f"ENT-{uuid.uuid4().hex[:8]}"
        t0 = datetime(2026, 1, 1, tzinfo=UTC)
        t1 = datetime(2026, 6, 1, tzinfo=UTC)
        await store.ingest([
            TemporalEvent(
                tenant_id=tenant, entity_id=entity, kind="mention",
                observation_id="OBS-live",
                payload={"role": "president"}, valid_from=t0, valid_until=t1,
            ),
            TemporalEvent(
                tenant_id=tenant, entity_id=entity, kind="mention",
                observation_id="OBS-live2", payload={"role": "former"}, valid_from=t1,
            ),
        ])
        await store.ingest([
            TemporalEvent(
                tenant_id=tenant, entity_id=entity, kind="mention",
                observation_id="OBS-live",
                payload={"role": "president"}, valid_from=t0, valid_until=t1,
            )
        ])  # replay must collapse, not duplicate

        # inside the first interval only the first belief holds
        at0 = await store.state_at(tenant_id=tenant, entity_id=entity, at=t0 + timedelta(days=1))
        assert [r["value"] for r in at0] == ["president"]

        # half-open: valid_until is exclusive, so after t1 only the second holds
        at1 = await store.state_at(tenant_id=tenant, entity_id=entity, at=t1 + timedelta(days=1))
        assert [r["value"] for r in at1] == ["former"]

        # exactly at the boundary the earlier one has already ended
        boundary = await store.state_at(tenant_id=tenant, entity_id=entity, at=t1)
        assert [r["value"] for r in boundary] == ["former"]

        # the log is faithful: both asserted intervals are still on record
        hist = await store.history(tenant_id=tenant, entity_id=entity)
        assert len(hist) == 2

        entities = await store.current_entities(tenant_id=tenant)
        assert entities and entities[0]["entity_id"] == entity
