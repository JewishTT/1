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
from storage.s3 import sha256_bytes  # type: ignore[attr-defined]


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
    """Object-store surface needed for immutable, rebuildable lake rows."""

    async def put_immutable_object(
        self, key: str, body: bytes, *, tenant_id: str = "", meta: dict | None = None
    ) -> bool: ...
    async def get_object(self, key: str) -> bytes | None: ...
    async def list_objects(self, prefix: str) -> list[str]: ...


class ObservationLake:
    """Rebuildable observation lake over an injected object store.

    Each observation is one immutable content-addressed CSV object under lake/rows.
    Rebuild lists a tenant/month prefix and validates every row object's hash.
    Legacy mutable manifests remain readable during rolling upgrades.
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

    async def _legacy_manifest(self, tenant_id: str, ym: str) -> LakeManifest | None:
        """Read and validate a pre-upgrade manifest without mutating it."""
        body = await self._store.get_object(self._manifest_key(tenant_id, ym))
        if body is None:
            return None
        manifest = LakeManifest.from_record(json.loads(body.decode("utf-8")))
        if manifest.tenant_id != tenant_id or manifest.year_month != ym:
            raise ProjectionRebuildableError(
                f"lake manifest scope mismatch for requested {tenant_id}/{ym}"
            )
        return manifest

    async def _promote_legacy_rows(self, tenant_id: str, ym: str) -> None:
        """Copy every legacy manifest row to immutable objects before a new append."""
        legacy = await self._legacy_manifest(tenant_id, ym)
        if legacy is None:
            return
        for record in legacy.rows:
            row = ObservationRow.from_record(record)
            if row.tenant_id != tenant_id:
                raise ProjectionRebuildableError("legacy lake manifest contains cross-tenant row")
            row_month = self._partition_of(row.collected_at)
            if row_month != ym:
                raise ProjectionRebuildableError("legacy lake manifest contains cross-partition row")
            body = self._encode_rows([row])
            digest = sha256_bytes(body)
            await self._store.put_immutable_object(
                self._rows_key(tenant_id, ym, digest),
                body,
                tenant_id=tenant_id,
                meta={
                    "kind": "observation-row",
                    "observation_id": row.observation_id,
                    "event_id": row.event_id,
                },
            )

    async def _partition_rows(
        self, tenant_id: str, ym: str
    ) -> tuple[list[ObservationRow], bool]:
        """Reconstruct rows from objects and any unpromoted legacy manifest entries."""
        prefix = f"{self.ROWS_PREFIX}/{tenant_id}/{ym}/"
        keys = [
            key for key in await self._store.list_objects(prefix)
            if key.endswith(".csv")
        ]
        by_digest: dict[str, ObservationRow] = {}
        for key in keys:
            body = await self._store.get_object(key)
            if body is None:
                raise ProjectionRebuildableError(f"listed lake row disappeared: {key}")
            expected_digest = key.rsplit("/", 1)[-1][:-4]
            if sha256_bytes(body) != expected_digest:
                raise ProjectionRebuildableError(f"lake row checksum mismatch: {key}")
            decoded = self._decode_rows(body)
            if len(decoded) != 1:
                raise ProjectionRebuildableError(
                    f"lake row object must contain exactly one row: {key}"
                )
            row = decoded[0]
            if row.tenant_id != tenant_id or self._partition_of(row.collected_at) != ym:
                raise ProjectionRebuildableError(f"lake row partition mismatch: {key}")
            by_digest[expected_digest] = row

        legacy = await self._legacy_manifest(tenant_id, ym)
        if legacy is not None:
            for record in legacy.rows:
                row = ObservationRow.from_record(record)
                if row.tenant_id != tenant_id:
                    raise ProjectionRebuildableError(
                        "legacy lake manifest contains cross-tenant row"
                    )
                row_month = self._partition_of(row.collected_at)
                if row_month != ym:
                    raise ProjectionRebuildableError(
                        "legacy lake manifest contains cross-partition row"
                    )
                digest = sha256_bytes(self._encode_rows([row]))
                by_digest.setdefault(digest, row)

        found_partition = bool(keys) or legacy is not None
        rows = sorted(
            by_digest.values(),
            key=lambda item: (item.observation_id, item.sha256, item.event_id),
        )
        return rows, found_partition

    async def append_row(self, row: ObservationRow) -> bool:
        """Append one immutable row; retries converge without shared-index writes."""
        if not row.tenant_id.strip() or not row.observation_id.strip() or not row.event_id.strip():
            raise ValueError("tenant_id, observation_id and event_id are required")
        ym = self._partition_of(row.collected_at)
        if ym is None:
            raise ValueError(f"collected_at must be an ISO-8601 timestamp: {row.collected_at!r}")

        # Rolling-upgrade safety: never hide legacy rows when the first new object
        # appears. Promotion is itself idempotent and safe to retry after a crash.
        await self._promote_legacy_rows(row.tenant_id, ym)
        body = self._encode_rows([row])
        digest = sha256_bytes(body)
        return await self._store.put_immutable_object(
            self._rows_key(row.tenant_id, ym, digest),
            body,
            tenant_id=row.tenant_id,
            meta={
                "kind": "observation-row",
                "observation_id": row.observation_id,
                "event_id": row.event_id,
            },
        )

    async def rows(self, tenant_id: str, ym: str | None = None) -> list[ObservationRow]:
        """Rebuild one tenant partition from durable row objects."""
        ym = ym or self._ym()
        rows, exists = await self._partition_rows(tenant_id, ym)
        if not exists:
            raise ProjectionRebuildableError(f"no lake partition for {tenant_id}/{ym}")
        return rows

    async def row_count(self, tenant_id: str, ym: str | None = None) -> int:
        ym = ym or self._ym()
        rows, _exists = await self._partition_rows(tenant_id, ym)
        return len(rows)

    async def partition_at(self, tenant_id: str, ym: str) -> dict:
        """Build an addressable manifest snapshot from immutable rows, without writes."""
        rows = await self.rows(tenant_id, ym)
        manifest = LakeManifest(
            tenant_id=tenant_id,
            year_month=ym,
            rows=tuple(row.as_record() for row in rows),
        )
        return {
            "tenant_id": tenant_id,
            "year_month": ym,
            "manifest": manifest.as_record(),
            "rows": [row.as_record() for row in rows],
        }
