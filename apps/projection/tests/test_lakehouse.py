r"""ObservationLake tests (feature 010, slice 3) — the data-lake.

Pins: content-addressed idempotency (I-1/I-11), provenance on every row (I-12),
partition manifest rebuild (\`rows\` reconstructs from durable objects only),
tenant isolation, and hermetic operation over the memory store (no docker).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from storage.memory import MemoryObjectStore

from lakehouse.river.lake import ObservationLake, ObservationRow, ProjectionRebuildableError


def _row(
    oid: str = "obs-1", tenant: str = "ten-1", uri: str = "http://a/b", sha: str = "aa" * 32
) -> ObservationRow:
    return ObservationRow(
        observation_id=oid,
        tenant_id=tenant,
        event_id="ev-1",
        uri=uri,
        content_type="text/html",
        sha256=sha,
        size_bytes=128,
        collected_at="2026-09-20T10:00:00Z",
        status="collected",
        source_id="src-1",
        work_id="wk-1",
        meta={"kind": "web", "score": 0.7},
    )


class TestObservationLake:
    async def test_append_and_rebuild_rows(self):
        store = MemoryObjectStore()
        lake = ObservationLake(store)
        assert await lake.append_row(_row(sha="a" * 64)) is True
        assert await lake.row_count("ten-1", "202609") == 1

        rebuilt = await lake.rows("ten-1", "202609")
        assert len(rebuilt) == 1
        r = rebuilt[0]
        assert r.observation_id == "obs-1"
        assert r.meta["score"] == 0.7

    async def test_exact_repeat_idempotent(self):
        store = MemoryObjectStore()
        lake = ObservationLake(store)
        r = _row(sha="b" * 64)
        assert await lake.append_row(r) is True
        assert await lake.append_row(r) is False  # I-11: same content, no second copy
        assert store.count() == 2  # 1 row csv + 1 manifest, never a doppelganger
        assert await lake.row_count("ten-1", "202609") == 1

    async def test_different_content_same_id_appends(self):
        store = MemoryObjectStore()
        lake = ObservationLake(store)
        assert await lake.append_row(_row(oid="obs-2", sha="c" * 64)) is True
        # same observation id but different content -> different sha -> distinct row
        assert await lake.append_row(_row(oid="obs-2", sha="d" * 64)) is True
        assert await lake.row_count("ten-1", "202609") == 2

    async def test_rows_carry_provenance_fields(self):
        store = MemoryObjectStore()
        lake = ObservationLake(store)
        await lake.append_row(_row())
        r = (await lake.rows("ten-1", "202609"))[0]
        assert r.event_id == "ev-1"
        # I-12: provenance is reconstructible (observation_id + event_id)
        assert r.observation_id == "obs-1"

    async def test_tenant_isolation(self):
        store = MemoryObjectStore()
        lake = ObservationLake(store)
        await lake.append_row(_row(oid="a", tenant="ten-1"))
        await lake.append_row(_row(oid="b", tenant="ten-2"))
        assert await lake.row_count("ten-1", "202609") == 1
        assert await lake.row_count("ten-2", "202609") == 1
        assert (await lake.rows("ten-1", "202609"))[0].observation_id == "a"

    async def test_missing_partition_rejects(self):
        store = MemoryObjectStore()
        lake = ObservationLake(store)
        try:
            await lake.rows("nobody", "209901")
            assert False, "expected ProjectionRebuildableError"
        except ProjectionRebuildableError:
            pass

    async def test_partition_snapshot(self):
        store = MemoryObjectStore()
        lake = ObservationLake(store)
        await lake.append_row(_row())
        snap = await lake.partition_at("ten-1", "202609")
        assert snap["manifest"]["rows"]
        assert len(snap["rows"]) == 1

    async def test_manifest_is_json_addressable(self):
        store = MemoryObjectStore()
        lake = ObservationLake(store)
        await lake.append_row(_row())
        key = f"{lake.MANIFESTS_PREFIX}/ten-1/202609.json"
        body = await store.get_object(key)
        assert body and body.startswith(b"{")
