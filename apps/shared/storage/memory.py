"""In-memory content-addressed object store (hermetic substitute for s3).

Mirrors the ``storage.s3.ObjectStore`` surface used by ``events.observation_gate``
and the lake writer: ``put_raw_dedup`` (idempotent by sha256), ``exists`,
``ref_uri`` — plus introspection helpers so hermetic tests can assert what was
written. Same immutability discipline (I-1): identical bytes → same key; the
gate's three-way split (R-08) is exercised identically to a real backend.
"""

from __future__ import annotations

from datetime import UTC, datetime

from storage.s3 import RawObjectRef, sha256_bytes


class MemoryObjectStore:
    """Pure in-memory ObjectStore for deterministic, docker-free tests."""

    def __init__(self, *, raw_bucket: str = "knowledge") -> None:
        self.raw_bucket = raw_bucket
        self._objects: dict[str, bytes] = {}
        self._meta: dict[str, dict] = {}

    def _ym(self, when: datetime | None = None) -> str:
        return (when or datetime.now(UTC)).strftime("%Y%m")

    def ref_uri(
        self, *, sha256: str, tenant_id: str, year_month: str | None = None, kind: str = "raw"
    ) -> str:
        ym = year_month or self._ym()
        return f"s3://{self.raw_bucket}/{kind}/{tenant_id}/{ym}/{sha256}"

    async def put_raw_dedup(
        self, body: bytes, *, tenant_id: str, meta: dict | None = None
    ) -> tuple[RawObjectRef, bool]:
        digest = sha256_bytes(body)
        ym = self._ym()
        key = f"raw/{tenant_id}/{ym}/{digest}"
        existed = key in self._objects
        if not existed:
            self._objects[key] = body
            if meta:
                self._meta[key] = dict(meta)
        return (
            RawObjectRef(
                uri=self.ref_uri(sha256=digest, tenant_id=tenant_id, year_month=ym),
                sha256=digest,
                size=len(body),
                tenant_prefix=f"{tenant_id}/{ym}",
                year_month=ym,
            ),
            existed,
        )

    async def exists(self, key: str) -> bool:
        return key in self._objects

    async def get(
        self, *, sha256: str, tenant_id: str, year_month: str | None = None
    ) -> bytes | None:
        ym = year_month or self._ym()
        return self._objects.get(f"raw/{tenant_id}/{ym}/{sha256}")

    # Generic keyed objects (data-lake manifests / row-groups): explicitly keyed,
    # not content-addressed — the lake layer owns key layout.
    async def put_object(
        self, key: str, body: bytes, *, tenant_id: str = "", meta: dict | None = None
    ) -> None:
        self._objects[key] = body
        if meta:
            self._meta[key] = dict(meta)

    async def get_object(self, key: str) -> bytes | None:
        return self._objects.get(key)

    async def exists_object(self, key: str) -> bool:
        return key in self._objects

    def keys(self) -> list[str]:
        return sorted(self._objects)

    def count(self) -> int:
        return len(self._objects)
