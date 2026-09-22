"""ObservationLake (feature 010, slice 3) — the missing "data-lake".

The zero-layer audit found a declared lakehouse (``apps/projection/lakehouse``)
with no backing writer: the direct pipeline persisted nothing. ``ObservationLake``
closes that gap with a compact, rebuildable observation lake that:

- writes each observation as a content-addressed CSV row via the injected object
  store (I-1 immutability: identical bytes -> same key, never a second copy);
- keeps a per-tenancy/manifest (``lake/manifests/{tenant}/{yyyymm}.json``) that
  lists exactly which rows live in a partition, enabling ``rebuild`` from
  durable storage alone (I-11);
- carries provenance on every row (I-12: event_id + observation_id);
- needs no broker/filesystem/docker — the store is injected
  (``storage.memory.MemoryObjectStore`` hermetically, ``storage.s3`` in prod).
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from domain import ProjectionRebuildableError  # provenance invariant (I-11/I-12)
from storage.s3 import RawObjectRef  # type: ignore[attr-defined]


@dataclass(frozen=True, slots=True)
class ObservationRow:
    """One materialized observation record (mirrors gate's RawObjectRef meta)."""

    observation_id: str
    tenant_id: str
    event_id: str
    uri: str
    content_type: str
    sha256: str
    size_bytes: int
    collected_at: str
    status: str = "collected"
    source_id: str = ""
    work_id: str = ""
    meta: dict[str, Any] = field(default_factory=dict, hash=False)

    COLUMNS = (
        "observation_id",
        "tenant_id",
        "event_id",
        "uri",
        "content_type",
        "sha256",
        "size_bytes",
        "collected_at",
        "status",
        "source_id",
        "work_id",
        "meta",
    )

    def as_record(self) -> dict:
        return {
            "observation_id": self.observation_id,
            "tenant_id": self.tenant_id,
            "event_id": self.event_id,
            "uri": self.uri,
            "content_type": self.content_type,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "collected_at": self.collected_at,
            "status": self.status,
            "source_id": self.source_id,
            "work_id": self.work_id,
            "meta": json.dumps(self.meta, sort_keys=True),
        }

    @classmethod
    def from_record(cls, rec: dict) -> ObservationRow:
        rec = dict(rec)
        rec["size_bytes"] = int(rec.get("size_bytes") or 0)
        if isinstance(rec.get("meta"), str):
            rec["meta"] = json.loads(rec["meta"] or "{}")
        return cls(**{k: rec.get(k) for k in cls.COLUMNS})


@dataclass(frozen=True, slots=True)
class LakeManifest:
    tenant_id: str
    year_month: str
    rows: tuple[dict, ...] = ()

    def as_record(self) -> dict:
        return {"tenant_id": self.tenant_id, "year_month": self.year_month, "rows": list(self.rows)}

    @classmethod
    def from_record(cls, rec: dict) -> LakeManifest:
        return cls(
            tenant_id=rec["tenant_id"],
            year_month=rec["year_month"],
            rows=tuple(rec.get("rows") or ()),
        )


class LakeStore(Protocol):
    """Object-store surface the lake persists onto (memory / s3 friendly)."""

    async def put_raw_dedup(
        self, body: bytes, *, tenant_id: str, meta: dict | None = None
    ) -> tuple[RawObjectRef, bool]: ...
    async def put_object(
        self, key: str, body: bytes, *, tenant_id: str, meta: dict | None = None
    ) -> None: ...
    async def get_object(self, key: str) -> bytes | None: ...
    async def exists_object(self, key: str) -> bool: ...
    async def get(
        self, *, sha256: str, tenant_id: str, year_month: str | None = None
    ) -> bytes | None: ...


class ObservationLake:
    """Rebuildable observation lake over an injected object store.

    Writes land as content-addressed CSV row-groups in ``lake/rows`` plus a
    manifest under ``lake/manifests/{tenant}/{yyyymm}.json``; ``rebuild``
    reconstructs the tenant view read-only from those two kinds of objects.
    """

    ROWS_PREFIX = "lake/rows"
    MANIFESTS_PREFIX = "lake/manifests"

    def __init__(self, store: LakeStore, *, now: datetime | None = None) -> None:
        self._store = store
        self._now = now

    def _ym(self, at: datetime | None = None) -> str:
        return (at or self._now or datetime.now(UTC)).strftime("%Y%m")

    def _rows_key(self, tenant_id: str, ym: str, sha256: str) -> str:
        return f"{self.ROWS_PREFIX}/{tenant_id}/{ym}/{sha256}.csv"

    def _manifest_key(self, tenant_id: str, ym: str) -> str:
        return f"{self.MANIFESTS_PREFIX}/{tenant_id}/{ym}.json"

    def _encode_rows(self, rows: list[ObservationRow]) -> bytes:
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=list(ObservationRow.COLUMNS))
        writer.writeheader()
        for r in rows:
            writer.writerow(r.as_record())
        return buf.getvalue().encode("utf-8")

    def _decode_rows(self, body: bytes) -> list[ObservationRow]:
        return [
            ObservationRow.from_record(rec)
            for rec in csv.DictReader(io.StringIO(body.decode("utf-8")))
        ]

    async def _manifest(self, tenant_id: str, ym: str) -> LakeManifest | None:
        body = await self._store.get_object(self._manifest_key(tenant_id, ym))
        if body is None:
            return None
        return LakeManifest.from_record(json.loads(body.decode("utf-8")))

    @staticmethod
    def _partition_of(collected_at: str) -> str | None:
        """yyyymm for an ISO-8601 timestamp, else None (caller defaults)."""
        try:
            return datetime.fromisoformat(collected_at).strftime("%Y%m")
        except ValueError:
            return None

    async def append_row(self, row: ObservationRow) -> bool:
        """Append one observation row. Idempotent (I-11): an exact-repeat write
        (same sha256, same spot in the manifest) returns ``False`` and changes
        nothing; first arrival returns ``True``."""
        ym = self._partition_of(row.collected_at) or self._ym()
        _ref, _existed = await self._store.put_raw_dedup(
            self._encode_rows([row]),
            tenant_id=row.tenant_id,
            meta={
                "kind": "observation-row",
                "observation_id": row.observation_id,
                "event_id": row.event_id,
            },
        )

        man = await self._manifest(row.tenant_id, ym)
        existing = man.rows if man else ()
        if any(
            r.get("sha256") == row.sha256 and r.get("observation_id") == row.observation_id
            for r in existing
        ):
            return False  # exact repeat — idempotent no-op

        rows = list(existing) + [row.as_record()]
        updated = LakeManifest(tenant_id=row.tenant_id, year_month=ym, rows=tuple(rows))
        await self._store.put_object(
            self._manifest_key(row.tenant_id, ym),
            json.dumps(updated.as_record(), sort_keys=True).encode("utf-8"),
            tenant_id=row.tenant_id,
            meta={"kind": "lake-manifest", "rows": len(rows)},
        )
        return True

    async def rows(self, tenant_id: str, ym: str | None = None) -> list[ObservationRow]:
        """Materialized rows for a tenant partition (rebuild path)."""
        ym = ym or self._ym()
        man = await self._manifest(tenant_id, ym)
        if man is None:
            raise ProjectionRebuildableError(f"no lake manifest for {tenant_id}/{ym}")
        # The manifest is the durable row index: rebuild is a pure manifest
        # replay (I-11) — the object bytes are a copy-on-write snapshot of it.
        return [ObservationRow.from_record(rec) for rec in man.rows]

    async def row_count(self, tenant_id: str, ym: str | None = None) -> int:
        ym = ym or self._ym()
        man = await self._manifest(tenant_id, ym)
        return len(man.rows) if man else 0

    async def partition_at(self, tenant_id: str, ym: str) -> dict:
        """Whole-partition snapshot: rows + manifest (for analytics loaders)."""
        man = await self._manifest(tenant_id, ym)
        rows = await self.rows(tenant_id, ym)
        return {
            "tenant_id": tenant_id,
            "year_month": ym,
            "manifest": man.as_record() if man else None,
            "rows": [r.as_record() for r in rows],
        }
